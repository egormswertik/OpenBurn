"""
CAM Tool Generators: Material Test, Focus Test, Arrays, Utility Geometry
"""
import math
from .project import Shape, CutSetting, Project
from .geometry import XForm

def generate_material_test(min_power=10, max_power=100, p_steps=5,
                           min_speed=500, max_speed=3000, s_steps=5,
                           cell_w=10.0, cell_h=10.0, gap=3.0,
                           start_x=20.0, start_y=20.0, mode="Scan"):
    """
    Generates a 2D matrix calibration grid:
    - X axis: Power steps (min_power -> max_power)
    - Y axis: Speed steps (min_speed -> max_speed)
    """
    proj = Project()
    p_step_val = (max_power - min_power) / max(1, p_steps - 1) if p_steps > 1 else 0
    s_step_val = (max_speed - min_speed) / max(1, s_steps - 1) if s_steps > 1 else 0

    layer_idx = 0
    for r in range(s_steps):
        speed = min_speed + r * s_step_val
        for c in range(p_steps):
            power = min_power + c * p_step_val
            
            # Create a dedicated layer for this cell parameter
            cur_idx = min(29, layer_idx % 30)
            proj.cut_settings[cur_idx] = CutSetting(
                type=mode,
                index=cur_idx,
                name=f"P{int(power)}_S{int(speed)}",
                speed=speed,
                maxPower=power,
                minPower=power,
                priority=layer_idx
            )
            
            cx = start_x + c * (cell_w + gap) + cell_w / 2.0
            cy = start_y + r * (cell_h + gap) + cell_h / 2.0

            cell_shape = Shape(
                "Rect",
                cut_index=cur_idx,
                xform=XForm([1, 0, 0, 1, cx, cy]),
                W=cell_w,
                H=cell_h,
                Cr=0
            )
            proj.shapes.append(cell_shape)
            layer_idx += 1

    return proj

def generate_focus_test(min_z=0.0, max_z=10.0, steps=10,
                        line_len=30.0, gap=4.0, speed=1000.0, power=30.0,
                        start_x=30.0, start_y=30.0):
    """
    Generates stepped focus calibration lines along Z axis
    """
    proj = Project()
    z_step_val = (max_z - min_z) / max(1, steps - 1) if steps > 1 else 0

    for i in range(steps):
        z = min_z + i * z_step_val
        cur_idx = min(29, i % 30)
        proj.cut_settings[cur_idx] = CutSetting(
            type="Cut",
            index=cur_idx,
            name=f"Z_{z:.1f}mm",
            speed=speed,
            maxPower=power,
            minPower=power,
            zOffset=z,
            priority=i
        )

        y = start_y + i * gap
        # Line from (start_x, y) to (start_x + line_len, y)
        line_shape = Shape(
            "Path",
            cut_index=cur_idx,
            xform=XForm([1, 0, 0, 1, 0, 0]),
            VertList=f"V{start_x:.2f} {y:.2f} V{start_x + line_len:.2f} {y:.2f}",
            PrimList="L0 1"
        )
        proj.shapes.append(line_shape)

    return proj

def create_grid_array(shapes, rows=3, cols=3, dx=20.0, dy=20.0):
    """
    Duplicate shapes in a rectangular grid
    """
    new_shapes = []
    for r in range(rows):
        for c in range(cols):
            shift_x = c * dx
            shift_y = r * dy
            for s in shapes:
                old_m = s.xform.m
                new_m = [old_m[0], old_m[1], old_m[2], old_m[3], old_m[4] + shift_x, old_m[5] + shift_y]
                clone = Shape(s.type, cut_index=s.cut_index, xform=XForm(new_m), **s.props)
                new_shapes.append(clone)
    return new_shapes

def create_circular_array(shapes, count=8, cx=100.0, cy=100.0, radius=50.0, rotate_shapes=True):
    """
    Duplicate shapes in a circular radial pattern
    """
    new_shapes = []
    angle_step = 2.0 * math.pi / max(1, count)

    for i in range(count):
        theta = i * angle_step
        px = cx + radius * math.cos(theta)
        py = cy + radius * math.sin(theta)

        for s in shapes:
            old_m = s.xform.m
            # Center of shape
            sx = old_m[4]
            sy = old_m[5]
            
            if rotate_shapes:
                rot = theta
                cos_r = math.cos(rot)
                sin_r = math.sin(rot)
                # Rotate local matrix
                m11 = old_m[0] * cos_r - old_m[1] * sin_r
                m12 = old_m[0] * sin_r + old_m[1] * cos_r
                m21 = old_m[2] * cos_r - old_m[3] * sin_r
                m22 = old_m[2] * sin_r + old_m[3] * cos_r
                new_m = [m11, m12, m21, m22, px, py]
            else:
                new_m = [old_m[0], old_m[1], old_m[2], old_m[3], px, py]

            clone = Shape(s.type, cut_index=s.cut_index, xform=XForm(new_m), **s.props)
            new_shapes.append(clone)

    return new_shapes
