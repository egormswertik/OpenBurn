"""
§5: DeviceProfile and Job settings
"""
import json

class DeviceProfile:
    def __init__(self, **kwargs):
        # §5 Default table
        self.bed_width = float(kwargs.get("bed_width", 400.0))
        self.bed_height = float(kwargs.get("bed_height", 400.0))
        self.origin_corner = kwargs.get("origin_corner", "Bottom-Left")
        self.s_max = int(kwargs.get("s_max", 1000))
        self.acceleration_x = float(kwargs.get("acceleration_x", 2000.0))
        self.acceleration_y = float(kwargs.get("acceleration_y", 2000.0))
        self.rapid_rate = float(kwargs.get("rapid_rate", 200.0))
        self.max_rate_x = float(kwargs.get("max_rate_x", 500.0))
        self.laser_mode = kwargs.get("laser_mode", "M4")
        self.return_to_home = bool(kwargs.get("return_to_home", True))
        self.suppress_comments = bool(kwargs.get("suppress_comments", False))
        self.origin_mode = kwargs.get("origin_mode", "Absolute")
        self.job_origin = int(kwargs.get("job_origin", 6)) # 6 = Bottom-Left
        self.user_origin_x = float(kwargs.get("user_origin_x", 0.0))
        self.user_origin_y = float(kwargs.get("user_origin_y", 0.0))
        self.fill_mode = kwargs.get("fill_mode", "AllAtOnce")

    @classmethod
    def load(cls, path_or_dict):
        if isinstance(path_or_dict, str):
            with open(path_or_dict, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        elif isinstance(path_or_dict, dict):
            return cls(**path_or_dict)
        return cls()
