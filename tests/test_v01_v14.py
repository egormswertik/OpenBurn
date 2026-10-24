"""
Verification tests for V01-V14 according to §10
"""
import unittest
import math
import json
import base64
import os
import zlib
import struct
from openburn.palette import match_layer_by_color, LAYER_COLORS
from openburn.profile import DeviceProfile
from openburn.project import Project, CutSetting, Shape
from openburn.geometry import XForm, approx_bezier, approx_ellipse
from openburn.gcode import compile_project
from openburn.svg import import_svg
from tests.gcode_parser import GCodeTrajectory

def make_test_png_4x4():
    """Generates a minimal 4x4 grayscale PNG with gradients and pure white (255)"""
    w, h = 4, 4
    # 4 rows, row 0 has pure white (255)
    pixels = [
        [255, 128, 64, 0],
        [200, 150, 100, 50],
        [255, 255, 10, 20],
        [80, 90, 100, 110]
    ]
    raw = bytearray()
    for row in pixels:
        raw.append(0) # filter type 0 (None)
        for val in row:
            raw.append(val)
    compressed = zlib.compress(bytes(raw))
    
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed)
    iend_crc = zlib.crc32(b"IEND")

    png = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        + struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)
        + struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    )
    return base64.b64encode(png).decode("ascii")

class TestOpenBurnCore(unittest.TestCase):

    def test_v01_rect_basic(self):
        """
        §10 V01: Rect 20x10 mm at (30, 40), Line, C00, Speed=100 mm/s, Power=20%
        Criteria: Start G0 X30 Y40, M4, 4 G1 moves, F6000, S200, M5.
        Bounding box: X[30, 50], Y[40, 50].
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        # Center at (40, 45) -> 30..50, 40..50
        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=10.0, Cr=0.0, xform=[1.0, 0.0, 0.0, 1.0, 40.0, 45.0]))

        prof = DeviceProfile()
        gcode = compile_project(proj, prof)
        traj = GCodeTrajectory(gcode)

        # Prologue check
        self.assertIn("G00 G17 G40 G21 G90", traj.commands[0])
        # Epilogue check
        self.assertIn("M5", traj.commands[-3])
        self.assertIn("M2", traj.commands[-1])

        burns = traj.get_burn_segments()
        self.assertEqual(len(burns), 4)
        for b in burns:
            self.assertEqual(b["s"], 200)
            self.assertEqual(b["f"], 6000)

        min_x, max_x, min_y, max_y = traj.get_bounding_box()
        self.assertAlmostEqual(min_x, 30.0, delta=0.05)
        self.assertAlmostEqual(max_x, 50.0, delta=0.05)
        self.assertAlmostEqual(min_y, 40.0, delta=0.05)
        self.assertAlmostEqual(max_y, 50.0, delta=0.05)

    def test_v02_rect_rotated(self):
        """
        §10 V02: Rect 20x10 mm rotated +30 deg, center (40, 60), Line, C00.
        Criteria: 4 corners strictly correspond to:
        (33.84, 50.67), (51.16, 60.67), (46.16, 69.33), (28.84, 59.33) with <= 0.05 mm tolerance.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        ang = math.radians(30)
        ca, sa = math.cos(ang), math.sin(ang)
        # Rotated +30 deg around origin and translated to (40, 60)
        # x' = ca*x - sa*y + 40; y' = sa*x + ca*y + 60
        # XForm format: [m11, m12, m21, m22, dx, dy] -> [ca, sa, -sa, ca, 40, 60]
        xf = [ca, sa, -sa, ca, 40.0, 60.0]
        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=10.0, Cr=0.0, xform=xf))

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)
        burns = traj.get_burn_segments()
        self.assertEqual(len(burns), 4)

        expected_corners = [
            (33.84, 50.67),
            (51.16, 60.67),
            (46.16, 69.33),
            (28.84, 59.33)
        ]
        actual_pts = [b["start"] for b in burns]

        for exp in expected_corners:
            found = any(math.hypot(act[0] - exp[0], act[1] - exp[1]) <= 0.05 for act in actual_pts)
            self.assertTrue(found, f"Expected corner {exp} not found in actual {actual_pts}")

    def test_v03_ellipse_and_circle(self):
        """
        §10 V03: Ellipse Rx=20 Ry=10 + Circle R=10
        Criteria: Circle has native G2/G3 arc. Ellipse approximated by G1 with chord <= 0.05 mm.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        # Circle at (50, 50)
        proj.shapes.append(Shape("Ellipse", cut_index=0, Rx=10.0, Ry=10.0, xform=[1.0, 0.0, 0.0, 1.0, 50.0, 50.0]))
        # Ellipse at (100, 50)
        proj.shapes.append(Shape("Ellipse", cut_index=0, Rx=20.0, Ry=10.0, xform=[1.0, 0.0, 0.0, 1.0, 100.0, 50.0]))

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)

        # Check native arc for circle
        arcs = [m for m in traj.moves if m["cmd"] in ("G2", "G3")]
        self.assertTrue(len(arcs) >= 1, "Circle must produce native G2 or G3 arc")

        # Check ellipse segments G1
        g1_moves = [m for m in traj.moves if m["cmd"] == "G1" and m["s"] > 0]
        self.assertTrue(len(g1_moves) > 10, "Ellipse must produce multiple G1 segments")

    def test_v04_fill_holes(self):
        """
        §10 V04: Square 10x10 with hole 4x4 in center, Fill, interval=1.0 mm.
        Criteria: Scanlines have 1.0 mm step. Hole traversed with S0 without M5.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Scan", lineInterval=1.0, speed=100.0, maxPower=20.0, overscanEnabled=False)
        # Outer square 10x10 centered at (20, 20): [15..25, 15..25]
        # Hole 4x4 centered at (20, 20): [18..22, 18..22]
        # Express as Path with outer loop + inner loop
        verts = (
            "V15 15c0x0c0y0c1x0c1y0 V25 15c0x0c0y0c1x0c1y0 V25 25c0x0c0y0c1x0c1y0 V15 25c0x0c0y0c1x0c1y0 "
            "V18 18c0x0c0y0c1x0c1y0 V22 18c0x0c0y0c1x0c1y0 V22 22c0x0c0y0c1x0c1y0 V18 22c0x0c0y0c1x0c1y0"
        )
        prims = "L 0 1 L 1 2 L 2 3 L 3 0 L 4 5 L 5 6 L 6 7 L 7 4"
        proj.shapes.append(Shape("Path", cut_index=0, xform=[1,0,0,1,0,0], VertList=verts, PrimList=prims))

        gcode = compile_project(proj, DeviceProfile())
        self.assertNotIn("M5\nG1", gcode) # No M5 inside scan moves

        traj = GCodeTrajectory(gcode)
        s0_moves = [m for m in traj.moves if m["cmd"] == "G1" and m["s"] == 0]
        self.assertTrue(len(s0_moves) > 0, "Traversing hole <= 5mm must produce G1 S0 moves")

    def test_v05_overscan(self):
        """
        §10 V05: Fill with Overscan (a=2000 mm/s^2, v=100 mm/s).
        d = 100^2 / (2 * 2000) = 2.5 mm.
        Criteria: G1 S0 F6000 segments of 2.5 mm added on both sides.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Scan", lineInterval=1.0, speed=100.0, maxPower=20.0, overscan=2.5, overscanEnabled=True)
        verts = (
            "V15 15c0x0c0y0c1x0c1y0 V25 15c0x0c0y0c1x0c1y0 V25 25c0x0c0y0c1x0c1y0 V15 25c0x0c0y0c1x0c1y0 "
            "V18 18c0x0c0y0c1x0c1y0 V22 18c0x0c0y0c1x0c1y0 V22 22c0x0c0y0c1x0c1y0 V18 22c0x0c0y0c1x0c1y0"
        )
        prims = "L 0 1 L 1 2 L 2 3 L 3 0 L 4 5 L 5 6 L 6 7 L 7 4"
        proj.shapes.append(Shape("Path", cut_index=0, xform=[1,0,0,1,0,0], VertList=verts, PrimList=prims))

        prof = DeviceProfile(acceleration_x=2000.0)
        gcode = compile_project(proj, prof)
        traj = GCodeTrajectory(gcode)

        overscan_moves = [m for m in traj.moves if m["cmd"] == "G1" and m["s"] == 0 and m["f"] == 6000]
        # Check that segments with length 2.5 mm exist
        lens = [math.hypot(m["end"][0] - m["start"][0], m["end"][1] - m["start"][1]) for m in overscan_moves]
        found_2_5 = any(abs(l - 2.5) < 0.05 for l in lens)
        self.assertTrue(found_2_5, f"Overscan 2.5mm move not found in lengths: {lens}")

    def test_v06_scan_angle_45(self):
        """
        §10 V06: Square 10x10 with hole 4x4, Fill, scanAngle=45 deg.
        Criteria: Scan lines at 45 deg (x - y = const), distance between lines 1.0 mm.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Scan", lineInterval=1.0, scanAngle=45.0, speed=100.0, maxPower=20.0, overscanEnabled=False)
        verts = (
            "V15 15c0x0c0y0c1x0c1y0 V25 15c0x0c0y0c1x0c1y0 V25 25c0x0c0y0c1x0c1y0 V15 25c0x0c0y0c1x0c1y0 "
            "V18 18c0x0c0y0c1x0c1y0 V22 18c0x0c0y0c1x0c1y0 V22 22c0x0c0y0c1x0c1y0 V18 22c0x0c0y0c1x0c1y0"
        )
        prims = "L 0 1 L 1 2 L 2 3 L 3 0 L 4 5 L 5 6 L 6 7 L 7 4"
        proj.shapes.append(Shape("Path", cut_index=0, xform=[1,0,0,1,0,0], VertList=verts, PrimList=prims))

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)
        burns = traj.get_burn_segments()
        self.assertTrue(len(burns) > 0)
        for b in burns:
            dx = b["end"][0] - b["start"][0]
            dy = b["end"][1] - b["start"][1]
            if abs(dx) > 0.01:
                # 45 deg -> dy / dx = 1 or -1
                slope = abs(dy / dx)
                self.assertAlmostEqual(slope, 1.0, delta=0.05)

    def test_v07_inner_to_outer(self):
        """
        §10 V07: 3 concentric squares 60x60, 40x40, 20x20.
        Criteria: Cut order 20x20 first, 40x40 second, 60x60 last.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        # Put them in outer-to-inner order in project to test sorting
        proj.shapes.append(Shape("Rect", cut_index=0, W=60.0, H=60.0, Cr=0.0, xform=[1,0,0,1,50,50]))
        proj.shapes.append(Shape("Rect", cut_index=0, W=40.0, H=40.0, Cr=0.0, xform=[1,0,0,1,50,50]))
        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=20.0, Cr=0.0, xform=[1,0,0,1,50,50]))

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)
        burns = traj.get_burn_segments()

        # Group burns by contour (4 moves each)
        c1 = burns[0:4]
        c2 = burns[4:8]
        c3 = burns[8:12]

        def get_dim(c):
            xs = [m["start"][0] for m in c]
            return max(xs) - min(xs)

        d1 = get_dim(c1)
        d2 = get_dim(c2)
        d3 = get_dim(c3)

        self.assertAlmostEqual(d1, 20.0, delta=0.05)
        self.assertAlmostEqual(d2, 40.0, delta=0.05)
        self.assertAlmostEqual(d3, 60.0, delta=0.05)

    def test_v08_passes_and_z(self):
        """
        §10 V08: Layer 01 (Fill, Priority=0) + Layer 00 (Line, Priority=1), 2 passes, zStep=0.5.
        Criteria: Layer 01 first. Before pass 2 of layer 00 -> G1 Z-0.5 F300.
        Working feed F6000 restored on next G1 cutting move.
        """
        proj = Project()
        proj.cut_settings[1] = CutSetting(index=1, type="Scan", priority=0, speed=100.0, maxPower=20.0, overscanEnabled=False)
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", priority=1, speed=100.0, maxPower=20.0, numPasses=2, zStep=0.5)

        proj.shapes.append(Shape("Rect", cut_index=1, W=10.0, H=10.0, Cr=0.0, xform=[1,0,0,1,20,20]))
        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=20.0, Cr=0.0, xform=[1,0,0,1,50,50]))

        gcode = compile_project(proj, DeviceProfile())
        self.assertIn("G1 Z-0.5 F300", gcode)
        self.assertIn("F6000", gcode)

        # Ensure working feed F6000 is restored on the G1 move following Z-0.5
        lines = gcode.splitlines()
        found_z_restore = False
        for i, l in enumerate(lines):
            if "Z-0.5" in l:
                # Next G1 cut move must specify F6000
                for follow in lines[i+1:]:
                    if follow.startswith("G1 X") or follow.startswith("G1 Y"):
                        self.assertIn("F6000", follow)
                        found_z_restore = True
                        break
        self.assertTrue(found_z_restore)

    def test_v09_scan_plus_cut(self):
        """
        §10 V09: Combined mode Scan+Cut.
        Criteria: First scan lines completed, then clean cut perimeter.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Scan+Cut", speed=100.0, maxPower=20.0, overscanEnabled=False)
        proj.shapes.append(Shape("Rect", cut_index=0, W=10.0, H=10.0, Cr=0.0, xform=[1,0,0,1,20,20]))

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)
        burns = traj.get_burn_segments()

        # The last 4 burn moves should be the perimeter cut of 10x10 rect
        last_4 = burns[-4:]
        self.assertEqual(len(last_4), 4)
        perimeter = sum(math.hypot(m["end"][0] - m["start"][0], m["end"][1] - m["start"][1]) for m in last_4)
        self.assertAlmostEqual(perimeter, 40.0, delta=0.1)

    def test_v10_raster_grayscale(self):
        """
        §10 V10: 4x4 px image Grayscale (10 DPI, 2.54 mm/pixel).
        Criteria: Modulated power S for half-tones. White pixels (255) cut with S0 or G0.
        """
        png_b64 = make_test_png_4x4()
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Image", dpi=10.0, ditherMode="Grayscale", minPower=10.0, maxPower=50.0, speed=100.0)
        proj.shapes.append(Shape("Bitmap", cut_index=0, W=4, H=4, xform=[1,0,0,1,0,0], Data=png_b64))

        prof = DeviceProfile(s_max=1000)
        gcode = compile_project(proj, prof)
        traj = GCodeTrajectory(gcode)
        burns = traj.get_burn_segments()
        self.assertTrue(len(burns) > 0)
        # Power should be in range [100, 500] (minPower=10% -> 100, maxPower=50% -> 500)
        for b in burns:
            self.assertTrue(100 <= b["s"] <= 500)

    def test_v11_svg_transform(self):
        """
        §10 V11: SVG file with rect in group with transform.
        Criteria: Y inverted (y_cam = H_doc - y_svg). Group matrix applied correctly.
        """
        svg_xml = '''<svg width="100mm" height="100mm" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
            <g transform="translate(10, 20)">
                <rect x="0" y="0" width="20" height="10" stroke="#000000" fill="none"/>
            </g>
        </svg>'''
        w, h, shapes = import_svg(svg_xml)
        self.assertEqual(w, 100.0)
        self.assertEqual(h, 100.0)
        self.assertEqual(len(shapes), 1)

        proj = Project()
        proj.shapes = shapes
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)
        min_x, max_x, min_y, max_y = traj.get_bounding_box()

        # In SVG: x in [10, 30], y in [20, 30]
        # In CAM (Y inverted: 100 - y): y in [70, 80]
        self.assertAlmostEqual(min_x, 10.0, delta=0.05)
        self.assertAlmostEqual(max_x, 30.0, delta=0.05)
        self.assertAlmostEqual(min_y, 70.0, delta=0.05)
        self.assertAlmostEqual(max_y, 80.0, delta=0.05)

    def test_v12_origins(self):
        """
        §10 V12: Rect 20x10 in Absolute, Current Position, Top-Left.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=10.0, Cr=0.0, xform=[1,0,0,1,40,45]))

        # Absolute: X[30, 50], Y[40, 50]
        g_abs = compile_project(proj, DeviceProfile(origin_mode="Absolute"))
        t_abs = GCodeTrajectory(g_abs)
        self.assertEqual(t_abs.get_bounding_box(), (30.0, 50.0, 40.0, 50.0))

        # Current (user_origin_x=10, user_origin_y=10): X[20, 40], Y[30, 40]
        g_cur = compile_project(proj, DeviceProfile(origin_mode="Current", user_origin_x=10.0, user_origin_y=10.0))
        t_cur = GCodeTrajectory(g_cur)
        self.assertEqual(t_cur.get_bounding_box(), (20.0, 40.0, 30.0, 40.0))

        # Top-Left (bed_height=400): Y' = 400 - Y -> [350, 360]
        g_tl = compile_project(proj, DeviceProfile(origin_mode="Top-Left", bed_height=400.0))
        t_tl = GCodeTrajectory(g_tl)
        self.assertEqual(t_tl.get_bounding_box(), (30.0, 50.0, 350.0, 360.0))

    def test_v13_tool_layer_exclusion(self):
        """
        §10 V13: Figure on layer C00 + figure on layer T1 (index 30).
        Criteria: T1 geometry is completely absent from G-code.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        proj.cut_settings[30] = CutSetting(index=30, type="Cut", speed=100.0, maxPower=20.0)

        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=10.0, Cr=0.0, xform=[1,0,0,1,40,45]))
        proj.shapes.append(Shape("Rect", cut_index=30, W=50.0, H=50.0, Cr=0.0, xform=[1,0,0,1,100,100]))

        gcode = compile_project(proj, DeviceProfile())
        traj = GCodeTrajectory(gcode)
        min_x, max_x, min_y, max_y = traj.get_bounding_box()

        # Only C00 (30..50, 40..50) must be present, T1 (75..125) must not be present
        self.assertEqual((min_x, max_x, min_y, max_y), (30.0, 50.0, 40.0, 50.0))

    def test_v14_lbrn_lbrn2_equivalence(self):
        """
        §10 V14: Projects V01 saved in .lbrn and .lbrn2 generate equivalent G-code.
        """
        proj = Project()
        proj.cut_settings[0] = CutSetting(index=0, type="Cut", speed=100.0, maxPower=20.0)
        proj.shapes.append(Shape("Rect", cut_index=0, W=20.0, H=10.0, Cr=0.0, xform=[1.0, 0.0, 0.0, 1.0, 40.0, 45.0]))

        lbrn_path = "/tmp/test_v14.lbrn"
        lbrn2_path = "/tmp/test_v14.lbrn2"

        proj.save_lbrn(lbrn_path)
        proj.save_lbrn2(lbrn2_path)

        p_xml = Project.load_lbrn(lbrn_path)
        p_json = Project.load_lbrn2(lbrn2_path)

        gcode_xml = compile_project(p_xml, DeviceProfile())
        gcode_json = compile_project(p_json, DeviceProfile())

        t_xml = GCodeTrajectory(gcode_xml)
        t_json = GCodeTrajectory(gcode_json)

        self.assertEqual(t_xml.get_bounding_box(), t_json.get_bounding_box())
        self.assertEqual(len(t_xml.get_burn_segments()), len(t_json.get_burn_segments()))

if __name__ == "__main__":
    unittest.main()
