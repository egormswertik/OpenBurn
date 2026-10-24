"""
§1.1 - 1.2: Palette and Color Matching
"""
import math

# §1.1 Table of 32 layers: 0..29 (Cut/Engrave), 30 (T1), 31 (T2)
LAYER_COLORS = [
    (0, "C00", (0, 0, 0)),
    (1, "C01", (0, 0, 255)),
    (2, "C02", (255, 0, 0)),
    (3, "C03", (0, 224, 0)),
    (4, "C04", (208, 208, 0)),
    (5, "C05", (255, 128, 0)),
    (6, "C06", (0, 224, 224)),
    (7, "C07", (255, 0, 255)),
    (8, "C08", (180, 180, 180)),
    (9, "C09", (0, 0, 160)),
    (10, "C10", (160, 0, 0)),
    (11, "C11", (0, 160, 0)),
    (12, "C12", (160, 160, 0)),
    (13, "C13", (192, 128, 0)),
    (14, "C14", (0, 160, 255)),
    (15, "C15", (160, 0, 160)),
    (16, "C16", (128, 128, 128)),
    (17, "C17", (125, 135, 185)),
    (18, "C18", (187, 119, 132)),
    (19, "C19", (74, 111, 227)),
    (20, "C20", (211, 63, 106)),
    (21, "C21", (140, 215, 140)),
    (22, "C22", (240, 185, 141)),
    (23, "C23", (246, 196, 225)),
    (24, "C24", (250, 158, 212)),
    (25, "C25", (80, 10, 120)),
    (26, "C26", (180, 90, 0)),
    (27, "C27", (0, 71, 84)),
    (28, "C28", (134, 250, 136)),
    (29, "C29", (255, 219, 102)),
    (30, "T1", (246, 139, 31)),
    (31, "T2", (40, 167, 69)),
]

def match_layer_by_color(rgb):
    """
    §1.2 Color matching algorithm:
    1. T1 and T2 excluded (only 0..29 checked).
    2. Minimum Euclidean distance: sqrt((R-Ri)^2 + (G-Gi)^2 + (B-Bi)^2).
    3. Collision resolution: lowest index wins.
    4. None/unrecognized -> index 0 (C00).
    """
    if rgb is None:
        return 0
    r, g, b = rgb
    best_idx = 0
    best_dist = float('inf')
    for idx in range(30):
        _, _, (cr, cg, cb) = LAYER_COLORS[idx]
        d = math.hypot(r - cr, g - cg, b - cb)
        if d < best_dist:
            best_dist = d
            best_idx = idx
    return best_idx
