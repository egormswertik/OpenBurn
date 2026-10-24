"""
Vector Operations: Boolean operations, Offset, Tabs/Bridges, Path Joining
Zero dependencies.
"""
import math
from .geometry import XForm, point_in_polygon
from .project import Shape

def join_open_paths(paths, tol=0.1):
    """
    Connects line segments whose endpoints match within tolerance.
    """
    if not paths:
        return []
    
    segments = [list(p) for p in paths if len(p) >= 2]
    joined = []
    
    while segments:
        curr = segments.pop(0)
        extended = True
        while extended:
            extended = False
            for i, other in enumerate(segments):
                # Check head to tail
                d_end_start = math.hypot(curr[-1][0] - other[0][0], curr[-1][1] - other[0][1])
                d_end_end = math.hypot(curr[-1][0] - other[-1][0], curr[-1][1] - other[-1][1])
                d_start_start = math.hypot(curr[0][0] - other[0][0], curr[0][1] - other[0][1])
                d_start_end = math.hypot(curr[0][0] - other[-1][0], curr[0][1] - other[-1][1])
                
                if d_end_start <= tol:
                    curr.extend(other[1:])
                    segments.pop(i)
                    extended = True
                    break
                elif d_end_end <= tol:
                    curr.extend(reversed(other[:-1]))
                    segments.pop(i)
                    extended = True
                    break
                elif d_start_end <= tol:
                    curr = other[:-1] + curr
                    segments.pop(i)
                    extended = True
                    break
                elif d_start_start <= tol:
                    curr = list(reversed(other[1:])) + curr
                    segments.pop(i)
                    extended = True
                    break
        joined.append(curr)
        
    return joined

def offset_polygon(points, delta):
    """
    Inflate (delta > 0) or Deflate (delta < 0) polygon contour by distance delta.
    Computes parallel offset lines for each edge and their intersections.
    """
    n = len(points)
    if n < 3:
        return points
        
    # Check CCW
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x1 * y2 - x2 * y1)
    is_ccw = area > 0
    sign = 1.0 if is_ccw else -1.0
    
    offset_lines = []
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        # Normal pointing outward
        nx = -dy / length * sign * delta
        ny = dx / length * sign * delta
        offset_lines.append(((p1[0] + nx, p1[1] + ny), (p2[0] + nx, p2[1] + ny)))
        
    # Intersect adjacent offset lines
    m = len(offset_lines)
    result = []
    for i in range(m):
        l1 = offset_lines[i]
        l2 = offset_lines[(i + 1) % m]
        # Line 1: p1 -> p2, Line 2: p3 -> p4
        x1, y1 = l1[0]; x2, y2 = l1[1]
        x3, y3 = l2[0]; x4, y4 = l2[1]
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-6:
            result.append(l1[1])
        else:
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
            ix = x1 + t * (x2 - x1)
            iy = y1 + t * (y2 - y1)
            result.append((ix, iy))
            
    return result

def add_tabs_to_contour(points, tab_size=1.0, tab_count=4):
    """
    Creates cut-gaps (bridges/tabs) so the part doesn't fall out of sheet.
    Returns list of open sub-paths with gaps of length tab_size.
    """
    total_len = 0.0
    segments = []
    n = len(points)
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        segments.append((p1, p2, dist))
        total_len += dist
        
    if total_len <= tab_size * tab_count:
        return [points]
        
    step = total_len / tab_count
    tab_positions = [(i + 0.5) * step for i in range(tab_count)]
    
    # Trace along contour and emit segments skipping [pos - tab_size/2, pos + tab_size/2]
    result_paths = []
    curr_path = []
    dist_accum = 0.0
    
    for p1, p2, seg_len in segments:
        if seg_len < 1e-6:
            continue
        p_start_dist = dist_accum
        p_end_dist = dist_accum + seg_len
        
        # Check if tabs fall inside this segment
        tabs_in_seg = [tp for tp in tab_positions if p_start_dist <= tp <= p_end_dist]
        
        if not tabs_in_seg:
            if not curr_path:
                curr_path.append(p1)
            curr_path.append(p2)
        else:
            # Split segment around tabs
            last_p = p1
            for tp in tabs_in_seg:
                # fraction
                t_in = max(0.0, (tp - tab_size/2 - p_start_dist) / seg_len)
                t_out = min(1.0, (tp + tab_size/2 - p_start_dist) / seg_len)
                
                pt_in = (p1[0] + t_in * (p2[0] - p1[0]), p1[1] + t_in * (p2[1] - p1[1]))
                pt_out = (p1[0] + t_out * (p2[0] - p1[0]), p1[1] + t_out * (p2[1] - p1[1]))
                
                if t_in > 0:
                    if not curr_path:
                        curr_path.append(last_p)
                    curr_path.append(pt_in)
                    result_paths.append(curr_path)
                    curr_path = []
                last_p = pt_out
            if last_p != p2:
                curr_path.append(last_p)
                curr_path.append(p2)
                
        dist_accum += seg_len
        
    if curr_path:
        result_paths.append(curr_path)
        
    return result_paths
