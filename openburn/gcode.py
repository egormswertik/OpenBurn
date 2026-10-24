"""
§6: Trajectory Planner and GRBL G-code Generator
"""
import math
from .geometry import (
    XForm, is_ccw, polygon_area, point_in_polygon,
    approx_bezier, approx_ellipse
)
from .fill import generate_scan_lines, calculate_overscan_distance
from .raster import decode_png, to_grayscale, apply_dither, grayscale_to_power
from .profile import DeviceProfile
import base64

def fmt(v):
    """Format coordinates: up to 3 decimal places, strip trailing zeros, no -0"""
    if abs(v) < 1e-4:
        return "0"
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s

class GCodeBuilder:
    def __init__(self, profile):
        self.profile = profile
        self.lines = []
        self.current_feed = None
        self.current_power = None
        self.laser_on = False
        self.z_changed = False
        self.last_move_was_rapid = True # Initial state requires S on next G1

    def append(self, line):
        self.lines.append(line)

    def rapid(self, x=None, y=None, z=None):
        parts = ["G0"]
        if x is not None: parts.append(f"X{fmt(x)}")
        if y is not None: parts.append(f"Y{fmt(y)}")
        if z is not None: parts.append(f"Z{fmt(z)}")
        self.append(" ".join(parts))
        self.last_move_was_rapid = True

    def plunge_z(self, z):
        self.append(f"G1 Z{fmt(z)} F300")
        self.current_feed = None # §6.5 must restore working feed on next G1
        self.z_changed = True

    def cut_move(self, x=None, y=None, target_feed=None, target_power=None):
        parts = ["G1"]
        if x is not None: parts.append(f"X{fmt(x)}")
        if y is not None: parts.append(f"Y{fmt(y)}")
        
        # Power modality
        need_power = False
        if target_power is not None:
            if target_power != self.current_power or self.last_move_was_rapid:
                need_power = True
                self.current_power = target_power
        if need_power:
            parts.append(f"S{self.current_power}")

        # Feed modality
        if target_feed is not None:
            if target_feed != self.current_feed:
                parts.append(f"F{target_feed}")
                self.current_feed = target_feed

        self.append(" ".join(parts))
        self.last_move_was_rapid = False

    def arc(self, cw, x, y, i, j, target_feed=None, target_power=None):
        cmd = "G2" if cw else "G3"
        parts = [cmd, f"X{fmt(x)}", f"Y{fmt(y)}", f"I{fmt(i)}", f"J{fmt(j)}"]
        if target_power is not None:
            if target_power != self.current_power or self.last_move_was_rapid:
                parts.append(f"S{target_power}")
                self.current_power = target_power
        if target_feed is not None:
            if target_feed != self.current_feed:
                parts.append(f"F{target_feed}")
                self.current_feed = target_feed
        self.append(" ".join(parts))
        self.last_move_was_rapid = False

def extract_contours(shape, parent_xf=None):
    """
    Extract geometric polygons / loops from shape.
    Returns list of {'type': 'poly'|'circle', 'pts': [...], 'cx':..., 'cy':..., 'r':..., 'cut_index': ...}
    """
    curr_xf = shape.xform.compose(parent_xf) if parent_xf else shape.xform
    cidx = shape.cut_index

    if shape.type == "Group":
        res = []
        for ch in shape.children:
            res.extend(extract_contours(ch, curr_xf))
        return res

    elif shape.type == "Rect":
        w = float(shape.props.get("W", 0))
        h = float(shape.props.get("H", 0))
        cr = float(shape.props.get("Cr", 0))
        # Center is at (0,0) in local coords or dx, dy?
        # In lbrn/lbrn2: Rect local coords are centered at (0,0): [-w/2, -h/2] .. [w/2, h/2]
        # §10 V01: Rect 20x10 at (30, 40) -> XForm is 1 0 0 1 40 45 (or 40, 45 is center, giving 30..50, 40..50)
        # Check: 40 - 20/2 = 30, 40 + 20/2 = 50. 45 - 10/2 = 40, 45 + 10/2 = 50! Exact!
        hw, hh = w * 0.5, h * 0.5
        if cr <= 0:
            local_pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
            pts = [curr_xf.apply(x, y) for x, y in local_pts]
            return [{"type": "poly", "pts": pts, "cut_index": cidx, "closed": True, "shape": shape}]
        else:
            # Rounded rect with Cr
            # §6.2: If Cr > min(W, H)/2, limit to min(W, H)/2
            cr = min(cr, min(w, h) * 0.5)
            # Create discrete contour or segments
            # 4 corners rounded with G3 arcs (CCW)
            # We can approximate corner arcs with chord <= 0.05
            corners = [
                (hw - cr, hh - cr, 0, math.pi / 2),
                (-hw + cr, hh - cr, math.pi / 2, math.pi),
                (-hw + cr, -hh + cr, math.pi, 3 * math.pi / 2),
                (hw - cr, -hh + cr, 3 * math.pi / 2, 2 * math.pi)
            ]
            poly = []
            # Generate CCW points
            # start bottom-right corner and go CCW
            n_sub = max(8, int(math.ceil(cr * 2)))
            for cx, cy, a_start, a_end in [
                (hw - cr, -hh + cr, 3 * math.pi / 2, 2 * math.pi),
                (hw - cr, hh - cr, 0, math.pi / 2),
                (-hw + cr, hh - cr, math.pi / 2, math.pi),
                (-hw + cr, -hh + cr, math.pi, 3 * math.pi / 2)
            ]:
                for s in range(n_sub):
                    ang = a_start + (a_end - a_start) * s / n_sub
                    lx = cx + cr * math.cos(ang)
                    ly = cy + cr * math.sin(ang)
                    poly.append(curr_xf.apply(lx, ly))
            return [{"type": "poly", "pts": poly, "cut_index": cidx, "closed": True, "shape": shape}]

    elif shape.type == "Ellipse":
        rx = float(shape.props.get("Rx", 0))
        ry = float(shape.props.get("Ry", 0))
        m11, m12, m21, m22, dx, dy = curr_xf.m
        is_uniform_scale = (abs(m11 - m22) < 1e-4 and abs(m12) < 1e-4 and abs(m21) < 1e-4) or                            (abs(m11 + m22) < 1e-4 and abs(m12) < 1e-4 and abs(m21) < 1e-4)
        if abs(rx - ry) < 1e-4 and is_uniform_scale:
            # Native circle
            r_world = rx * math.hypot(m11, m12)
            cx, cy = curr_xf.apply(0, 0)
            return [{"type": "circle", "cx": cx, "cy": cy, "r": r_world, "cut_index": cidx, "shape": shape}]
        else:
            # General ellipse -> polyline with chord <= 0.05
            pts = approx_ellipse(rx, ry, curr_xf, tol=0.03)
            return [{"type": "poly", "pts": pts, "cut_index": cidx, "closed": True, "shape": shape}]

    elif shape.type == "Polygon":
        n_sides = int(shape.props.get("NumSides", 6))
        r = float(shape.props.get("R", 10))
        pts = []
        for i in range(n_sides):
            ang = 2.0 * math.pi * i / n_sides
            pts.append(curr_xf.apply(r * math.cos(ang), r * math.sin(ang)))
        return [{"type": "poly", "pts": pts, "cut_index": cidx, "closed": True, "shape": shape}]

    elif shape.type == "Path":
        vl_str = shape.props.get("VertList", "")
        pl_str = shape.props.get("PrimList", "")
        # Parse VertList: V<x> <y>[c0x<..>c0y<..>c1x<..>c1y<..>]
        import re
        verts = []
        matches = re.finditer(r"V([+-]?\d*\.?\d+)\s+([+-]?\d*\.?\d+)(?:c0x([+-]?\d*\.?\d+)c0y([+-]?\d*\.?\d+)c1x([+-]?\d*\.?\d+)c1y([+-]?\d*\.?\d+))?", vl_str)
        for m in matches:
            x = float(m.group(1))
            y = float(m.group(2))
            c0x = float(m.group(3) or 0)
            c0y = float(m.group(4) or 0)
            c1x = float(m.group(5) or 0)
            c1y = float(m.group(6) or 0)
            verts.append({"x": x, "y": y, "c0x": c0x, "c0y": c0y, "c1x": c1x, "c1y": c1y})

        # Parse PrimList: L 0 1, B 0 1
        pl_tokens = pl_str.strip().split()
        subpaths = []
        curr_subpath = []
        i = 0
        while i < len(pl_tokens):
            cmd = pl_tokens[i]
            idx0 = int(pl_tokens[i+1])
            idx1 = int(pl_tokens[i+2])
            i += 3
            v0 = verts[idx0]
            v1 = verts[idx1]
            p0 = curr_xf.apply(v0["x"], v0["y"])
            p3 = curr_xf.apply(v1["x"], v1["y"])

            if cmd == "L":
                if not curr_subpath:
                    curr_subpath.append(p0)
                curr_subpath.append(p3)
            elif cmd == "B":
                # Cubic bezier
                # c1 of v0 and c0 of v1 are relative control points
                p1 = curr_xf.apply(v0["x"] + v0["c1x"], v0["y"] + v0["c1y"])
                p2 = curr_xf.apply(v1["x"] + v1["c0x"], v1["y"] + v1["c0y"])
                pts = approx_bezier(p0, p1, p2, p3, tol=0.02)
                if not curr_subpath:
                    curr_subpath.append(p0)
                curr_subpath.extend(pts)

            # Check if this closes a loop
            if math.hypot(p3[0] - curr_subpath[0][0], p3[1] - curr_subpath[0][1]) < 1e-4 and len(curr_subpath) > 2:
                subpaths.append(curr_subpath[:-1])
                curr_subpath = []

        if curr_subpath:
            subpaths.append(curr_subpath)

        res = []
        for sp in subpaths:
            res.append({"type": "poly", "pts": sp, "cut_index": cidx, "closed": True, "shape": shape})
        return res

    elif shape.type == "Bitmap":
        return [{"type": "bitmap", "shape": shape, "cut_index": cidx}]

    return []

def compile_project(project, profile=None):
    """
    Main CAM compilation entry point.
    Returns G-code as string with LF endings.
    """
    if profile is None:
        profile = DeviceProfile()

    b = GCodeBuilder(profile)

    # §6.1 Prologue
    b.append("G00 G17 G40 G21 G90")

    # Extract all elements
    all_items = []
    for s in project.shapes:
        all_items.extend(extract_contours(s))

    # Group by layer cut_index
    # §4, §10 V13: Layer 30 (T1) and 31 (T2) completely excluded from G-code
    layer_items = {}
    for item in all_items:
        cidx = item["cut_index"]
        if cidx in (30, 31):
            continue
        setting = project.get_setting(cidx)
        if not setting.output:
            continue
        if cidx not in layer_items:
            layer_items[cidx] = []
        layer_items[cidx].append(item)

    # Sort layers by priority (lowest first)
    sorted_layers = sorted(layer_items.keys(), key=lambda c: project.get_setting(c).priority)

    # Laser command mode
    laser_cmd = profile.laser_mode # M4 or M3

    for cidx in sorted_layers:
        setting = project.get_setting(cidx)
        items = layer_items[cidx]
        speed = setting.speed
        feed = round(speed * 60)
        power_pct = setting.maxPower
        power_s = round(power_pct * profile.s_max / 100.0)

        # §6.1 Air assist M8
        if setting.doAirAssist:
            b.append("M8")

        # Determine mode
        # §10 V09: Scan+Cut -> first Scan, then Cut
        modes = []
        if setting.type == "Scan+Cut":
            modes = ["Scan", "Cut"]
        else:
            modes = [setting.type]

        for current_mode in modes:
            for pass_idx in range(1, setting.numPasses + 1):
                # §6.4 Z management
                z_depth = setting.zOffset - (pass_idx - 1) * setting.zStep
                if z_depth != 0.0:
                    b.plunge_z(z_depth)

                if current_mode == "Scan":
                    # Extract closed polygons for filling
                    polys = []
                    for it in items:
                        if it["type"] == "poly":
                            polys.append(it["pts"])
                        elif it["type"] == "circle":
                            # Approximate circle as polygon for scanning
                            cx, cy, r = it["cx"], it["cy"], it["r"]
                            n_pts = max(36, int(math.ceil(2 * math.pi * r)))
                            c_poly = [(cx + r * math.cos(2*math.pi*i/n_pts), cy + r * math.sin(2*math.pi*i/n_pts)) for i in range(n_pts)]
                            polys.append(c_poly)

                    # Generate scanlines
                    scan_rows = generate_scan_lines(polys, setting.lineInterval, setting.scanAngle, setting.bidirectional)
                    # Crosshatch
                    if setting.crosshatch:
                        scan_rows.extend(generate_scan_lines(polys, setting.lineInterval, setting.scanAngle + 90.0, setting.bidirectional))

                    # Process scan rows
                    b.append(laser_cmd)
                    for row in scan_rows:
                        segs = row["segments"]
                        if not segs: continue

                        # Calculate overscan distance
                        # Length of entire row
                        min_x = min(min(p1[0], p2[0]) for p1, p2 in segs)
                        max_x = max(max(p1[0], p2[0]) for p1, p2 in segs)
                        row_len = math.hypot(segs[-1][1][0] - segs[0][0][0], segs[-1][1][1] - segs[0][0][1])
                        overscan_d = 0.0
                        if setting.overscanEnabled:
                            overscan_d = calculate_overscan_distance(speed, profile.acceleration_x, row_len, setting.overscan)

                        # Direction unit vector along line
                        p_start = segs[0][0]
                        p_end = segs[-1][1]
                        line_dx = p_end[0] - p_start[0]
                        line_dy = p_end[1] - p_start[1]
                        dist_full = math.hypot(line_dx, line_dy)
                        ux = line_dx / dist_full if dist_full > 1e-6 else 1.0
                        uy = line_dy / dist_full if dist_full > 1e-6 else 0.0

                        # Move to start of line with overscan
                        start_pos = (p_start[0] - ux * overscan_d, p_start[1] - uy * overscan_d)
                        b.rapid(start_pos[0], start_pos[1])

                        # Acceleration runup G1 S0 F<feed>
                        if overscan_d > 1e-4:
                            b.cut_move(p_start[0], p_start[1], target_feed=feed, target_power=0)

                        # Burn segments
                        for idx_s, (p1, p2) in enumerate(segs):
                            if idx_s > 0:
                                # Gap between segs[idx_s - 1][1] and p1
                                prev_end = segs[idx_s - 1][1]
                                gap = math.hypot(p1[0] - prev_end[0], p1[1] - prev_end[1])
                                if gap <= 5.0:
                                    # §6.3: gap <= 5.0 mm traversed at working feed with S0 (no M5!)
                                    b.cut_move(p1[0], p1[1], target_feed=feed, target_power=0)
                                else:
                                    # gap > 5.0 mm traversed with G0
                                    b.rapid(p1[0], p1[1])
                            else:
                                if math.hypot(start_pos[0] - p1[0], start_pos[1] - p1[1]) > 1e-4 and overscan_d <= 1e-4:
                                    b.rapid(p1[0], p1[1])

                            # Burn p1 -> p2
                            b.cut_move(p2[0], p2[1], target_feed=feed, target_power=power_s)

                        # Deceleration runout G1 S0 F<feed>
                        if overscan_d > 1e-4:
                            end_pos = (p_end[0] + ux * overscan_d, p_end[1] + uy * overscan_d)
                            b.cut_move(end_pos[0], end_pos[1], target_feed=feed, target_power=0)

                elif current_mode == "Cut":
                    # Sort contours: §6.2, §10 V07 Inner-to-Outer
                    # Inner holes are contained inside other contours
                    # Containment tree
                    poly_items = [it for it in items if it["type"] in ("poly", "circle")]
                    # Compute areas
                    for it in poly_items:
                        if it["type"] == "poly":
                            it["area"] = polygon_area(it["pts"])
                        elif it["type"] == "circle":
                            it["area"] = math.pi * (it["r"] ** 2)

                    # Sort by area ascending: smallest inner figures cut first!
                    poly_items.sort(key=lambda it: it["area"])

                    # Determine if an item is a hole (odd depth) or outer perimeter (even depth)
                    for i, it in enumerate(poly_items):
                        depth = 0
                        # Test center or first point
                        test_pt = it["pts"][0] if it["type"] == "poly" else (it["cx"], it["cy"])
                        for j in range(i + 1, len(poly_items)):
                            parent = poly_items[j]
                            if parent["type"] == "poly":
                                if point_in_polygon(test_pt, parent["pts"]):
                                    depth += 1
                            elif parent["type"] == "circle":
                                if math.hypot(test_pt[0] - parent["cx"], test_pt[1] - parent["cy"]) < parent["r"]:
                                    depth += 1
                        it["is_hole"] = (depth % 2 == 1)

                    b.append(laser_cmd)
                    for it in poly_items:
                        is_hole = it["is_hole"]
                        if it["type"] == "circle":
                            cx, cy, r = it["cx"], it["cy"], it["r"]
                            # §6.2: outer perimeters CCW (G3), inner holes CW (G2)
                            # Start at (cx + r, cy)
                            b.rapid(cx + r, cy)
                            cw = is_hole
                            # Full circle arc: end point same as start point, I = -r, J = 0
                            b.arc(cw, cx + r, cy, -r, 0, target_feed=feed, target_power=power_s)

                        elif it["type"] == "poly":
                            pts = list(it["pts"])
                            if not pts: continue
                            # Ensure CCW for outer, CW for hole
                            ccw = is_ccw(pts)
                            if is_hole and ccw:
                                pts.reverse()
                            elif not is_hole and not ccw:
                                pts.reverse()

                            # Cut closed loop
                            p0 = pts[0]
                            b.rapid(p0[0], p0[1])
                            for p in pts[1:]:
                                b.cut_move(p[0], p[1], target_feed=feed, target_power=power_s)
                            # Close to p0
                            b.cut_move(p0[0], p0[1], target_feed=feed, target_power=power_s)

                elif current_mode == "Image":
                    # Raster bitmap
                    for it in items:
                        if it["type"] == "bitmap":
                            shape = it["shape"]
                            data_b64 = shape.props.get("Data", "")
                            png_bytes = base64.b64decode(data_b64)
                            w_px, h_px, img_rgb = decode_png(png_bytes)
                            gray = to_grayscale(img_rgb)
                            dither_mode = setting.ditherMode

                            # Scaling & dimensions
                            # lineInterval or dpi
                            pixel_step = setting.lineInterval
                            # XForm mapping
                            xf = shape.xform
                            b.append(laser_cmd)

                            if dither_mode == "Grayscale":
                                # Analog power modulation
                                for y_idx in range(h_px):
                                    # bottom to top: invert y_idx for CAM table if needed
                                    # in image, row 0 is top. For CAM table: y = (h_px - 1 - y_idx) * pixel_step
                                    py = (h_px - 1 - y_idx) * pixel_step
                                    is_fwd = (y_idx % 2 == 0)
                                    x_range = range(w_px) if is_fwd else range(w_px - 1, -1, -1)
                                    row_burns = []
                                    for x_idx in x_range:
                                        px = x_idx * pixel_step
                                        wp = xf.apply(px, py)
                                        p_s = grayscale_to_power(gray[y_idx][x_idx], setting.minPower, setting.maxPower, profile.s_max)
                                        row_burns.append((wp, p_s))

                                    # Filter runs of burn
                                    first_burn = True
                                    for wp, s_val in row_burns:
                                        if s_val == 0:
                                            # pure white
                                            continue
                                        if first_burn:
                                            b.rapid(wp[0], wp[1])
                                            first_burn = False
                                        b.cut_move(wp[0], wp[1], target_feed=feed, target_power=s_val)

                            else:
                                # Dithered binary
                                bin_grid = apply_dither(gray, dither_mode, setting.ditherThreshold)
                                for y_idx in range(h_px):
                                    py = (h_px - 1 - y_idx) * pixel_step
                                    is_fwd = (y_idx % 2 == 0)
                                    x_range = range(w_px) if is_fwd else range(w_px - 1, -1, -1)
                                    first_burn = True
                                    for x_idx in x_range:
                                        if bin_grid[y_idx][x_idx] == 0: # Black = burn
                                            px = x_idx * pixel_step
                                            wp = xf.apply(px, py)
                                            if first_burn:
                                                b.rapid(wp[0], wp[1])
                                                first_burn = False
                                            b.cut_move(wp[0], wp[1], target_feed=feed, target_power=power_s)

        # §6.1 Air assist M9
        if setting.doAirAssist:
            b.append("M9")

    # §6.4 Return Z to 0 if changed
    if b.z_changed:
        b.append("G1 Z0 F300")

    # §6.1 Epilogue
    b.append("M5")
    if profile.return_to_home:
        b.rapid(0, 0)
    b.append("M2")

    # Origin transformations if necessary
    # §5, §10 V12: origin_mode: Absolute, Current, Top-Left
    raw_gcode = "\n".join(b.lines) + "\n"
    if profile.origin_mode != "Absolute":
        raw_gcode = apply_origin_mode(raw_gcode, profile)

    return raw_gcode

def apply_origin_mode(gcode_str, profile):
    """
    §5, §10 V12:
    - Current: translate relative to (user_origin_x, user_origin_y)
    - Top-Left: y' = bed_height - y
    """
    import re
    lines = gcode_str.splitlines()
    out_lines = []
    for line in lines:
        if line.startswith(("G0", "G1", "G2", "G3")):
            def repl_x(m):
                val = float(m.group(1))
                if profile.origin_mode == "Current":
                    val -= profile.user_origin_x
                return f"X{fmt(val)}"
            def repl_y(m):
                val = float(m.group(1))
                if profile.origin_mode == "Current":
                    val -= profile.user_origin_y
                elif profile.origin_mode == "Top-Left" or profile.origin_corner == "Top-Left":
                    val = profile.bed_height - val
                return f"Y{fmt(val)}"
            line = re.sub(r"X([+-]?\d*\.?\d+)", repl_x, line)
            line = re.sub(r"Y([+-]?\d*\.?\d+)", repl_y, line)
        out_lines.append(line)
    return "\n".join(out_lines) + "\n"
