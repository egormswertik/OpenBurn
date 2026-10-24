"""
§6.3: Fill / Scan generator with overscan and gap handling
"""
import math

def generate_scan_lines(polygons, line_interval, scan_angle=0.0, bidirectional=True):
    """
    §6.3:
    First scanline at Y_0 = Y_min + line_interval / 2.
    Bottom-to-top (+Y).
    Direction of first line: left-to-right (+X).
    scan_angle in degrees: rotate polygons by -scan_angle, scan horizontally, rotate lines back by +scan_angle.
    """
    rad = math.radians(scan_angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    def rot(x, y, c, s):
        return (c * x - s * y, s * x + c * y)

    # Rotate polygons to scan coordinate system
    rot_polys = []
    min_y = float('inf')
    max_y = float('-inf')

    for poly in polygons:
        r_poly = []
        for (x, y) in poly:
            rx, ry = rot(x, y, cos_a, -sin_a)
            r_poly.append((rx, ry))
            if ry < min_y: min_y = ry
            if ry > max_y: max_y = ry
        rot_polys.append(r_poly)

    if min_y >= max_y:
        return []

    y = min_y + line_interval / 2.0
    scan_rows = []
    line_idx = 0

    while y <= max_y + 1e-6:
        # Find intersections with all polygon segments
        intersections = []
        for poly in rot_polys:
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    # compute intersection x
                    t = (y - y1) / (y2 - y1 + 1e-12)
                    ix = x1 + t * (x2 - x1)
                    intersections.append(ix)
        intersections.sort()

        # Pair intersections: [x0, x1], [x2, x3], ...
        segments = []
        for i in range(0, len(intersections) - 1, 2):
            x_start = intersections[i]
            x_end = intersections[i + 1]
            if x_end > x_start:
                segments.append((x_start, x_end))

        if segments:
            # Determine direction: first line left-to-right (+X).
            # If bidirectional, flip alternate lines.
            is_forward = True
            if bidirectional:
                is_forward = (line_idx % 2 == 0)
            else:
                is_forward = True

            if not is_forward:
                # Reverse order of segments and flip each segment
                rev_segs = [(end, start) for (start, end) in reversed(segments)]
                scan_rows.append((y, rev_segs, is_forward))
            else:
                scan_rows.append((y, segments, is_forward))
            line_idx += 1

        y += line_interval

    # Rotate back to original coordinate system
    final_rows = []
    for (ry, segs, is_forward) in scan_rows:
        row_segs = []
        for (rx1, rx2) in segs:
            p1 = rot(rx1, ry, cos_a, sin_a)
            p2 = rot(rx2, ry, cos_a, sin_a)
            row_segs.append((p1, p2))
        final_rows.append({
            "ry": ry,
            "segments": row_segs,
            "is_forward": is_forward,
            "angle_rad": rad
        })
    return final_rows

def calculate_overscan_distance(speed, accel_x, line_length, overscan_pct):
    """
    §6.3:
    d = max(L_line * overscan / 100, (speed)^2 / (2 * acceleration_x))
    """
    d_accel = (speed ** 2) / (2.0 * accel_x)
    d_pct = line_length * (overscan_pct / 100.0)
    return max(d_pct, d_accel)
