"""
§3: SVG Importer
"""
import xml.etree.ElementTree as ET
import math
import re
from .geometry import XForm
from .project import Shape
from .palette import match_layer_by_color

def parse_svg_length(val_str, dpi=96.0):
    if not val_str:
        return 0.0
    val_str = str(val_str).strip()
    match = re.match(r"^([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)$", val_str)
    if not match:
        return 0.0
    num = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "mm":
        return num
    elif unit == "cm":
        return num * 10.0
    elif unit == "in":
        return num * 25.4
    elif unit == "pt":
        return num * (25.4 / 72.0)
    elif unit == "pc":
        return num * 12.0 * (25.4 / 72.0)
    elif unit in ("px", ""):
        return num * (25.4 / dpi)
    return num

def parse_color(c_str):
    if not c_str or c_str == "none":
        return None
    c_str = c_str.strip().lower()
    if c_str.startswith("#"):
        hex_str = c_str[1:]
        if len(hex_str) == 3:
            return (int(hex_str[0]*2, 16), int(hex_str[1]*2, 16), int(hex_str[2]*2, 16))
        elif len(hex_str) == 6:
            return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))
    elif c_str.startswith("rgb"):
        m = re.findall(r"\d+", c_str)
        if len(m) >= 3:
            return (int(m[0]), int(m[1]), int(m[2]))
    named = {
        "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
        "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
        "cyan": (0, 255, 255), "magenta": (255, 0, 255), "gray": (128, 128, 128),
        "grey": (128, 128, 128), "orange": (255, 165, 0), "purple": (128, 0, 128)
    }
    return named.get(c_str)

def parse_transform(t_str):
    if not t_str:
        return XForm()
    curr_xf = XForm()
    matches = re.findall(r"([a-zA-Z]+)\s*\(([^)]+)\)", t_str)
    for cmd, args_str in matches:
        args = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", args_str)]
        t_xf = XForm()
        if cmd == "matrix" and len(args) == 6:
            t_xf = XForm([args[0], args[1], args[2], args[3], args[4], args[5]])
        elif cmd == "translate":
            tx = args[0]
            ty = args[1] if len(args) > 1 else 0.0
            t_xf = XForm([1, 0, 0, 1, tx, ty])
        elif cmd == "scale":
            sx = args[0]
            sy = args[1] if len(args) > 1 else sx
            t_xf = XForm([sx, 0, 0, sy, 0, 0])
        elif cmd == "rotate":
            ang = math.radians(args[0])
            ca, sa = math.cos(ang), math.sin(ang)
            if len(args) == 3:
                cx, cy = args[1], args[2]
                t1 = XForm([1, 0, 0, 1, cx, cy])
                tr = XForm([ca, sa, -sa, ca, 0, 0])
                t2 = XForm([1, 0, 0, 1, -cx, -cy])
                t_xf = t2.compose(tr).compose(t1)
            else:
                t_xf = XForm([ca, sa, -sa, ca, 0, 0])
        elif cmd == "skewX":
            ang = math.radians(args[0])
            t_xf = XForm([1, 0, math.tan(ang), 1, 0, 0])
        elif cmd == "skewY":
            ang = math.radians(args[0])
            t_xf = XForm([1, math.tan(ang), 0, 1, 0, 0])
        curr_xf = t_xf.compose(curr_xf)
    return curr_xf

def import_svg(svg_content):
    root = ET.fromstring(svg_content) if isinstance(svg_content, str) and svg_content.strip().startswith("<") else ET.parse(svg_content).getroot()
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]

    w_attr = root.get("width")
    h_attr = root.get("height")
    vb_attr = root.get("viewBox")
    
    doc_w = parse_svg_length(w_attr) if w_attr else 0.0
    doc_h = parse_svg_length(h_attr) if h_attr else 0.0

    if (doc_w <= 0 or doc_h <= 0) and vb_attr:
        vb_vals = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", vb_attr)]
        if len(vb_vals) == 4:
            doc_w = vb_vals[2] * (25.4 / 96.0)
            doc_h = vb_vals[3] * (25.4 / 96.0)

    if doc_w <= 0: doc_w = 400.0
    if doc_h <= 0: doc_h = 400.0

    scale_x = scale_y = (25.4 / 96.0)
    vb_minx = vb_miny = 0.0
    if vb_attr:
        vb_vals = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", vb_attr)]
        if len(vb_vals) == 4:
            vb_minx, vb_miny, vb_w, vb_h = vb_vals
            scale_x = doc_w / vb_w if vb_w > 0 else scale_x
            scale_y = doc_h / vb_h if vb_h > 0 else scale_y

    shapes = []

    def get_style(elem, parent_style=None):
        st = dict(parent_style or {})
        for k in ("stroke", "fill"):
            v = elem.get(k)
            if v: st[k] = v
        style_attr = elem.get("style")
        if style_attr:
            for item in style_attr.split(";"):
                if ":" in item:
                    k, v = item.split(":", 1)
                    if k.strip() in ("stroke", "fill"):
                        st[k.strip()] = v.strip()
        return st

    def walk_elem(elem, curr_xf, inherited_style):
        st = get_style(elem, inherited_style)
        # transform is not an inheritable style property; it applies locally and chains
        el_xf = parse_transform(elem.get("transform", ""))
        combined_xf = el_xf.compose(curr_xf)

        c = parse_color(st.get("stroke"))
        if c is None:
            c = parse_color(st.get("fill"))
        cut_idx = match_layer_by_color(c)

        tag = elem.tag
        if tag == "g":
            for ch in elem:
                walk_elem(ch, combined_xf, st)
        elif tag == "rect":
            x = float(elem.get("x", 0))
            y = float(elem.get("y", 0))
            w = float(elem.get("width", 0))
            h = float(elem.get("height", 0))
            rx = float(elem.get("rx", elem.get("ry", 0)))
            pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            mapped_pts = []
            for px, py in pts:
                tx, ty = combined_xf.apply(px, py)
                mx = (tx - vb_minx) * scale_x
                my = doc_h - ((ty - vb_miny) * scale_y)
                mapped_pts.append((mx, my))
            v_list = [f"V{p[0]:g} {p[1]:g}c0x0c0y0c1x0c1y0" for p in mapped_pts]
            p_list = ["L 0 1", "L 1 2", "L 2 3", "L 3 0"]
            shapes.append(Shape("Path", cut_index=cut_idx, xform=XForm(), VertList=" ".join(v_list), PrimList=" ".join(p_list)))

        elif tag in ("circle", "ellipse"):
            cx = float(elem.get("cx", 0))
            cy = float(elem.get("cy", 0))
            if tag == "circle":
                rx = ry = float(elem.get("r", 0))
            else:
                rx = float(elem.get("rx", 0))
                ry = float(elem.get("ry", 0))
            tcx, tcy = combined_xf.apply(cx, cy)
            mcx = (tcx - vb_minx) * scale_x
            mcy = doc_h - ((tcy - vb_miny) * scale_y)
            mrx = rx * scale_x
            mry = ry * scale_y
            shapes.append(Shape("Ellipse", cut_index=cut_idx, xform=XForm([1, 0, 0, 1, mcx, mcy]), Rx=mrx, Ry=mry))

        elif tag == "path":
            d_str = elem.get("d", "")
            tokens = re.findall(r"([a-zA-Z])|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", d_str)
            flat = []
            for t in tokens:
                if t[0]: flat.append(t[0])
                elif t[1]: flat.append(float(t[1]))
            
            idx = 0
            curr_x = curr_y = 0.0
            start_x = start_y = 0.0
            v_pts = []
            p_cmds = []

            while idx < len(flat):
                cmd = flat[idx]
                if isinstance(cmd, str):
                    idx += 1
                else:
                    cmd = prev_cmd

                if cmd in ('M', 'm'):
                    x = flat[idx]; y = flat[idx+1]; idx += 2
                    if cmd == 'm':
                        curr_x += x; curr_y += y
                    else:
                        curr_x = x; curr_y = y
                    start_x, start_y = curr_x, curr_y
                    prev_cmd = 'L' if cmd == 'M' else 'l'
                    tx, ty = combined_xf.apply(curr_x, curr_y)
                    mx = (tx - vb_minx) * scale_x
                    my = doc_h - ((ty - vb_miny) * scale_y)
                    v_pts.append((mx, my))

                elif cmd in ('L', 'l'):
                    x = flat[idx]; y = flat[idx+1]; idx += 2
                    if cmd == 'l':
                        curr_x += x; curr_y += y
                    else:
                        curr_x = x; curr_y = y
                    prev_cmd = cmd
                    tx, ty = combined_xf.apply(curr_x, curr_y)
                    mx = (tx - vb_minx) * scale_x
                    my = doc_h - ((ty - vb_miny) * scale_y)
                    v_pts.append((mx, my))
                    p_cmds.append(('L', len(v_pts) - 2, len(v_pts) - 1))

                elif cmd in ('Z', 'z'):
                    curr_x, curr_y = start_x, start_y
                    prev_cmd = cmd
                    p_cmds.append(('L', len(v_pts) - 1, 0))

            if v_pts:
                v_list = [f"V{x:g} {y:g}c0x0c0y0c1x0c1y0" for x, y in v_pts]
                p_list = [f"{t} {i0} {i1}" for t, i0, i1 in p_cmds]
                shapes.append(Shape("Path", cut_index=cut_idx, xform=XForm(), VertList=" ".join(v_list), PrimList=" ".join(p_list)))

    for child in root:
        walk_elem(child, XForm(), {})

    return doc_w, doc_h, shapes
