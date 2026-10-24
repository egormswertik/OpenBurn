"""
§2.3, §6.2: Geometry, XForm, Paths, Polygons, Ellipses, Rectangles
"""
import math

class XForm:
    """§2.3 Affine transformation: [m11, m12, m21, m22, dx, dy]"""
    def __init__(self, m=None):
        if m is None:
            self.m = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        else:
            self.m = [float(x) for x in m]

    def apply(self, x, y):
        m11, m12, m21, m22, dx, dy = self.m
        return (m11 * x + m21 * y + dx, m12 * x + m22 * y + dy)

    def compose(self, parent):
        # parent * self
        p11, p12, p21, p22, pdx, pdy = parent.m
        s11, s12, s21, s22, sdx, sdy = self.m
        m11 = p11 * s11 + p21 * s12
        m12 = p12 * s11 + p22 * s12
        m21 = p11 * s21 + p21 * s22
        m22 = p12 * s21 + p22 * s22
        dx = p11 * sdx + p21 * sdy + pdx
        dy = p12 * sdx + p22 * sdy + pdy
        return XForm([m11, m12, m21, m22, dx, dy])

def is_ccw(points):
    """Calculate signed polygon area (Shoelace formula). >0 => CCW"""
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    return area > 0

def polygon_area(points):
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    return abs(area) * 0.5

def point_in_polygon(pt, poly):
    """Ray casting algorithm to determine if pt is inside poly."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)):
            if x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
                inside = not inside
    return inside

def approx_bezier(p0, p1, p2, p3, tol=0.02):
    """
    # impl-defined: ID-001 Adaptive de Casteljau subdivision
    chord tolerance tol <= 0.05 mm
    """
    # Distance from p1 and p2 to chord p0-p3
    x0, y0 = p0
    x3, y3 = p3
    chord_len = math.hypot(x3 - x0, y3 - y0)
    if chord_len < 1e-6:
        d1 = math.hypot(p1[0] - x0, p1[1] - y0)
        d2 = math.hypot(p2[0] - x0, p2[1] - y0)
        dist = max(d1, d2)
    else:
        # Distance of point (px, py) to line (x0, y0)-(x3, y3)
        # |(y3-y0)px - (x3-x0)py + x3*y0 - y3*x0| / chord_len
        def pt_line_dist(p):
            return abs((y3 - y0) * p[0] - (x3 - x0) * p[1] + x3 * y0 - y3 * x0) / chord_len
        dist = max(pt_line_dist(p1), pt_line_dist(p2))

    if dist <= tol:
        return [p3]

    # De Casteljau subdivision at t=0.5
    p01 = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
    p12 = ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)
    p23 = ((p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5)
    p012 = ((p01[0] + p12[0]) * 0.5, (p01[1] + p12[1]) * 0.5)
    p123 = ((p12[0] + p23[0]) * 0.5, (p12[1] + p23[1]) * 0.5)
    p0123 = ((p012[0] + p123[0]) * 0.5, (p012[1] + p123[1]) * 0.5)

    left = approx_bezier(p0, p01, p012, p0123, tol)
    right = approx_bezier(p0123, p123, p23, p3, tol)
    return left + right

def approx_ellipse(rx, ry, xform, tol=0.03):
    """
    # impl-defined: ID-002 Ellipse approximation with chord deviation <= 0.05 mm
    """
    # Calculate number of segments based on curvature
    # Max sagitta for circular arc of radius R with angle step da: R*(1 - cos(da/2)) <= tol
    # da <= 2 * acos(1 - tol / R) approx 2 * sqrt(2 * tol / R)
    max_r = max(rx, ry)
    min_r = min(rx, ry)
    # worst-case radius of curvature is min_r^2 / max_r or max_r^2 / min_r
    # We choose N points uniformly or adaptively
    r_eff = max(rx, ry)
    step = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - tol / max(r_eff, 1e-4))))
    n = max(36, int(math.ceil(2.0 * math.pi / max(step, 0.01))))
    pts = []
    for i in range(n):
        ang = 2.0 * math.pi * i / n
        lx = rx * math.cos(ang)
        ly = ry * math.sin(ang)
        pts.append(xform.apply(lx, ly))
    return pts
