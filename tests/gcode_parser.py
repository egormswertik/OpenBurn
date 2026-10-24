"""
G-code trajectory parser and property validator for tests
"""
import re
import math

class GCodeTrajectory:
    def __init__(self, gcode_text):
        self.raw_text = gcode_text
        self.lines = gcode_text.strip().splitlines()
        self.moves = [] # list of dicts: {'cmd': 'G0'|'G1'|'G2'|'G3', 'start': (x,y), 'end': (x,y), 's': int, 'f': int, 'z': float, 'arc': (i,j,cw)}
        self.commands = []
        self._parse()

    def _parse(self):
        curr_x, curr_y = 0.0, 0.0
        curr_z = 0.0
        curr_f = 0
        curr_s = 0

        for line in self.lines:
            line = line.strip()
            if not line: continue
            self.commands.append(line)

            tokens = line.split()
            cmd = tokens[0] if tokens else ""

            # Check for coordinates
            x_m = re.search(r"X([+-]?\d*\.?\d+)", line)
            y_m = re.search(r"Y([+-]?\d*\.?\d+)", line)
            z_m = re.search(r"Z([+-]?\d*\.?\d+)", line)
            f_m = re.search(r"F(\d+)", line)
            s_m = re.search(r"S(\d+)", line)
            i_m = re.search(r"I([+-]?\d*\.?\d+)", line)
            j_m = re.search(r"J([+-]?\d*\.?\d+)", line)

            if f_m: curr_f = int(f_m.group(1))
            if s_m: curr_s = int(s_m.group(1))
            if z_m: curr_z = float(z_m.group(1))

            new_x = float(x_m.group(1)) if x_m else curr_x
            new_y = float(y_m.group(1)) if y_m else curr_y

            if cmd in ("G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"):
                norm_cmd = cmd.replace("0", "") if cmd in ("G00", "G01", "G02", "G03") else cmd
                move_data = {
                    "cmd": norm_cmd,
                    "start": (curr_x, curr_y),
                    "end": (new_x, new_y),
                    "s": curr_s,
                    "f": curr_f,
                    "z": curr_z,
                    "line": line
                }
                if norm_cmd in ("G2", "G3"):
                    i_val = float(i_m.group(1)) if i_m else 0.0
                    j_val = float(j_m.group(1)) if j_m else 0.0
                    move_data["arc"] = (i_val, j_val, norm_cmd == "G2")
                self.moves.append(move_data)
                curr_x, curr_y = new_x, new_y

    def get_burn_segments(self):
        """Returns all cutting/burning moves where S > 0 and cmd in (G1, G2, G3)"""
        return [m for m in self.moves if m["cmd"] in ("G1", "G2", "G3") and m["s"] > 0]

    def get_bounding_box(self):
        burns = self.get_burn_segments()
        if not burns:
            return (0, 0, 0, 0)
        xs = [m["start"][0] for m in burns] + [m["end"][0] for m in burns]
        ys = [m["start"][1] for m in burns] + [m["end"][1] for m in burns]
        return (min(xs), max(xs), min(ys), max(ys))
