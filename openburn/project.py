"""
§2: Project files (.lbrn and .lbrn2) parser and writer
§4: CutSetting registry
"""
import json
import xml.etree.ElementTree as ET
from .geometry import XForm

class CutSetting:
    """§4 Parameter registry"""
    def __init__(self, **kwargs):
        self.type = kwargs.get("type", kwargs.get("Type", "Cut"))
        self.index = int(kwargs.get("index", kwargs.get("Index", 0)))
        self.name = str(kwargs.get("name", kwargs.get("Name", f"C{self.index:02d}")))
        self.priority = int(kwargs.get("priority", kwargs.get("Priority", self.index)))
        self.speed = float(kwargs.get("speed", kwargs.get("Speed", 100.0)))
        self.maxPower = float(kwargs.get("maxPower", kwargs.get("MaxPower", 20.0)))
        self.minPower = float(kwargs.get("minPower", kwargs.get("MinPower", 10.0)))
        self.numPasses = int(kwargs.get("numPasses", kwargs.get("NumPasses", 1)))
        self.zOffset = float(kwargs.get("zOffset", kwargs.get("ZOffset", 0.0)))
        self.zStep = float(kwargs.get("zStep", kwargs.get("ZStep", 0.0)))
        self.lineInterval = float(kwargs.get("lineInterval", kwargs.get("LineInterval", 0.1)))
        self.dpi = float(kwargs.get("dpi", kwargs.get("DPI", 254.0)))
        # priority for dpi over lineInterval if given
        if "dpi" in kwargs or "DPI" in kwargs:
            self.lineInterval = 25.4 / self.dpi
        self.scanAngle = float(kwargs.get("scanAngle", kwargs.get("ScanAngle", 0.0)))
        self.bidirectional = bool(int(kwargs.get("bidirectional", kwargs.get("Bidirectional", 1))))
        self.crosshatch = bool(int(kwargs.get("crosshatch", kwargs.get("Crosshatch", 0))))
        self.overscan = float(kwargs.get("overscan", kwargs.get("Overscan", 2.5)))
        self.overscanEnabled = bool(int(kwargs.get("overscanEnabled", kwargs.get("OverscanEnabled", 1))))
        self.kerf = float(kwargs.get("kerf", kwargs.get("Kerf", 0.0)))
        self.doAirAssist = bool(int(kwargs.get("doAirAssist", kwargs.get("DoAirAssist", 0))))
        self.output = bool(int(kwargs.get("output", kwargs.get("Output", 1))))
        self.ditherMode = kwargs.get("ditherMode", kwargs.get("DitherMode", "Floyd-Steinberg"))
        self.ditherThreshold = int(kwargs.get("ditherThreshold", kwargs.get("DitherThreshold", 128)))

    def to_dict(self):
        return {
            "Type": self.type,
            "Index": self.index,
            "Name": self.name,
            "Priority": self.priority,
            "Speed": self.speed,
            "MaxPower": self.maxPower,
            "MinPower": self.minPower,
            "NumPasses": self.numPasses,
            "ZOffset": self.zOffset,
            "ZStep": self.zStep,
            "LineInterval": self.lineInterval,
            "ScanAngle": self.scanAngle,
            "Bidirectional": self.bidirectional,
            "Crosshatch": self.crosshatch,
            "Overscan": self.overscan,
            "OverscanEnabled": self.overscanEnabled,
            "Kerf": self.kerf,
            "DoAirAssist": self.doAirAssist,
            "Output": self.output,
            "DitherMode": self.ditherMode,
            "DitherThreshold": self.ditherThreshold
        }

class Shape:
    def __init__(self, shape_type, cut_index=0, xform=None, **kwargs):
        self.type = shape_type
        self.cut_index = int(cut_index)
        self.xform = xform if isinstance(xform, XForm) else XForm(xform)
        self.props = kwargs
        self.children = kwargs.get("children", [])

class Project:
    def __init__(self):
        self.cut_settings = {} # index -> CutSetting
        self.shapes = []

    def get_setting(self, cut_index):
        if cut_index in self.cut_settings:
            return self.cut_settings[cut_index]
        return CutSetting(index=cut_index)

    @classmethod
    def load_lbrn(cls, path_or_content):
        """§2.1 XML .lbrn loader"""
        proj = cls()
        if path_or_content.strip().startswith("<"):
            root = ET.fromstring(path_or_content)
        else:
            tree = ET.parse(path_or_content)
            root = tree.getroot()

        for cs_elem in root.findall("CutSetting"):
            props = {"type": cs_elem.get("type", "Cut")}
            for child in cs_elem:
                val = child.get("Value")
                props[child.tag] = val
            cs = CutSetting(**props)
            proj.cut_settings[cs.index] = cs

        def parse_shape(elem):
            stype = elem.get("Type")
            cidx = elem.get("CutIndex", "0")
            xf_elem = elem.find("XForm")
            xf = XForm([float(v) for v in xf_elem.text.strip().split()]) if xf_elem is not None and xf_elem.text else XForm()
            props = {}
            for k, v in elem.attrib.items():
                if k not in ("Type", "CutIndex"):
                    props[k] = float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
            if stype == "Path":
                vl = elem.find("VertList")
                pl = elem.find("PrimList")
                props["VertList"] = vl.text.strip() if vl is not None and vl.text else ""
                props["PrimList"] = pl.text.strip() if pl is not None and pl.text else ""
            elif stype == "Bitmap":
                d = elem.find("Data")
                props["Data"] = d.text.strip() if d is not None and d.text else ""
            elif stype == "Group":
                ch_elem = elem.find("Children")
                children = []
                if ch_elem is not None:
                    for ch in ch_elem.findall("Shape"):
                        children.append(parse_shape(ch))
                props["children"] = children
            return Shape(stype, cut_index=cidx, xform=xf, **props)

        for s_elem in root.findall("Shape"):
            proj.shapes.append(parse_shape(s_elem))
        return proj

    @classmethod
    def load_lbrn2(cls, path_or_content):
        """§2.2 JSON .lbrn2 loader"""
        proj = cls()
        if path_or_content.strip().startswith("{"):
            data = json.loads(path_or_content)
        else:
            with open(path_or_content, "r", encoding="utf-8") as f:
                data = json.load(f)

        pages = data.get("Pages", [])
        if pages:
            page = pages[0]
            for cs_data in page.get("CutSettings", []):
                cs = CutSetting(**cs_data)
                proj.cut_settings[cs.index] = cs
            
            def parse_shape_dict(s):
                stype = s.get("Type")
                cidx = s.get("CutIndex", 0)
                xf = XForm(s.get("XForm"))
                props = {k: v for k, v in s.items() if k not in ("Type", "CutIndex", "XForm", "Children")}
                if stype == "Group":
                    props["children"] = [parse_shape_dict(ch) for ch in s.get("Children", [])]
                return Shape(stype, cut_index=cidx, xform=xf, **props)

            for s in page.get("Shapes", []):
                proj.shapes.append(parse_shape_dict(s))
        return proj

    def save_lbrn(self, filepath):
        """§2.1 Write .lbrn (XML)"""
        root = ET.Element("LaserProject", FormatVersion="1", AppVersion="2.2.2")
        for cs in sorted(self.cut_settings.values(), key=lambda c: c.index):
            c_elem = ET.SubElement(root, "CutSetting", type=cs.type)
            d = cs.to_dict()
            for k, v in d.items():
                if k == "Type": continue
                # Lowercase first letter for XML convention in §2.1
                tag = k[0].lower() + k[1:]
                val_str = str(int(v)) if isinstance(v, bool) else str(v)
                ET.SubElement(c_elem, tag, Value=val_str)

        def shape_to_xml(s, parent):
            attribs = {"Type": s.type, "CutIndex": str(s.cut_index)}
            for k, v in s.props.items():
                if k not in ("VertList", "PrimList", "Data", "children"):
                    attribs[k] = str(v)
            se = ET.SubElement(parent, "Shape", **attribs)
            xf_str = " ".join(f"{x:g}" for x in s.xform.m)
            ET.SubElement(se, "XForm").text = xf_str
            if s.type == "Path":
                ET.SubElement(se, "VertList").text = s.props.get("VertList", "")
                ET.SubElement(se, "PrimList").text = s.props.get("PrimList", "")
            elif s.type == "Bitmap":
                ET.SubElement(se, "Data").text = s.props.get("Data", "")
            elif s.type == "Group":
                ch_elem = ET.SubElement(se, "Children")
                for ch in s.children:
                    shape_to_xml(ch, ch_elem)

        for s in self.shapes:
            shape_to_xml(s, root)

        tree = ET.ElementTree(root)
        ET.indent(tree, space="    ")
        with open(filepath, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)

    def save_lbrn2(self, filepath):
        """§2.2 Write .lbrn2 (JSON)"""
        def shape_to_dict(s):
            d = {"Type": s.type, "CutIndex": s.cut_index, "XForm": s.xform.m}
            for k, v in s.props.items():
                if k != "children":
                    d[k] = v
            if s.type == "Group":
                d["Children"] = [shape_to_dict(ch) for ch in s.children]
            return d

        data = {
            "FormatVersion": 1,
            "AppVersion": "2.2.2",
            "Pages": [
                {
                    "Name": "Page 1",
                    "CutSettings": [cs.to_dict() for cs in sorted(self.cut_settings.values(), key=lambda c: c.index)],
                    "Shapes": [shape_to_dict(s) for s in self.shapes]
                }
            ]
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
