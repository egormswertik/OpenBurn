"""
§8: REST API and Server-Sent Events (SSE) server with Web UI serving
"""
import http.server
import json
import secrets
import re
import io
import os
import mimetypes
import time
import threading
from .profile import DeviceProfile
from .project import Project, Shape, CutSetting
from .geometry import XForm
from .svg import import_svg
from .gcode import compile_project
from .serial_driver import GrblSerial, get_available_ports

class DeviceState:
    # # impl-defined: ID-003 Device state with real serial support
    def __init__(self):
        self.connected = False
        self.state = "Disconnected" # Idle, Run, Hold, Alarm, Disconnected
        self.port = None
        self.baudrate = None
        self.profile = DeviceProfile()
        self.current_project = Project()
        self.current_gcode = None
        self.head_x = 0.0
        self.head_y = 0.0
        self.active_token = secrets.token_hex(16)
        self.listeners = [] # SSE listener queues
        self.serial = GrblSerial()
        self.serial.on_log_callback = lambda msg: self.emit_event("log", {"line": msg})

    def emit_event(self, event_type, data):
        payload = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        dead = []
        for q in self.listeners:
            try:
                q(payload)
            except Exception:
                dead.append(q)
        for d in dead:
            if d in self.listeners:
                self.listeners.remove(d)

DEVICE = DeviceState()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "web")

class OpenBurnRequestHandler(http.server.BaseHTTPRequestHandler):
    def send_json(self, status_code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_api_error(self, code, message):
        self.send_json(code, {"error": True, "code": code, "message": message})

    def check_auth(self):
        client_ip = self.client_address[0]
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == DEVICE.active_token:
                return True
        return False

    def serve_static(self, rel_path):
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        safe_path = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
        if not safe_path.startswith(STATIC_DIR) or not os.path.isfile(safe_path):
            self.send_api_error(404, "File not found")
            return
        mime_type, _ = mimetypes.guess_type(safe_path)
        if not mime_type:
            mime_type = "application/octet-stream"
        try:
            with open(safe_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type else mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_api_error(500, str(e))

    def do_GET(self):
        path = self.path.split("?")[0]
        if not path.startswith("/api/"):
            self.serve_static(path)
            return

        if not self.check_auth():
            self.send_api_error(401, "Unauthorized")
            return

        if path == "/api/status":
            self.send_json(200, {
                "state": DEVICE.state,
                "connected": DEVICE.connected,
                "port": DEVICE.port,
                "x": DEVICE.head_x,
                "y": DEVICE.head_y
            })
        elif path == "/api/device/ports":
            ports = get_available_ports()
            self.send_json(200, {"ports": ports})
        elif path == "/api/project":
            p = DEVICE.current_project or Project()
            shapes_data = []
            for s in p.shapes:
                s_dict = {"Type": s.type, "CutIndex": s.cut_index, "XForm": s.xform.m}
                for k, v in s.props.items():
                    if k != "children":
                        s_dict[k] = v
                shapes_data.append(s_dict)
            settings_data = [cs.to_dict() for cs in p.cut_settings.values()]
            self.send_json(200, {
                "shapes": shapes_data,
                "cut_settings": settings_data
            })
        elif path == "/api/profile":
            self.send_json(200, DEVICE.profile.to_dict())
        elif path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            queue_lock = threading.Condition()
            msg_queue = []

            def listener(msg):
                with queue_lock:
                    msg_queue.append(msg)
                    queue_lock.notify()

            DEVICE.listeners.append(listener)
            try:
                while True:
                    with queue_lock:
                        while not msg_queue:
                            queue_lock.wait(timeout=1.0)
                        msgs = list(msg_queue)
                        msg_queue.clear()
                    for m in msgs:
                        self.wfile.write(m.encode("utf-8"))
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                if listener in DEVICE.listeners:
                    DEVICE.listeners.remove(listener)
        else:
            self.send_api_error(404, "Not Found")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/connect":
            self.send_json(200, {"token": DEVICE.active_token, "expires": 0})
            return

        if not self.check_auth():
            self.send_api_error(401, "Unauthorized")
            return

        content_len = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")

        if path == "/api/file/upload":
            body = self.rfile.read(content_len)
            boundary = None
            if "boundary=" in content_type:
                boundary = content_type.split("boundary=")[1].strip().encode()
            if not boundary:
                boundary = body.split(b"\r\n")[0]

            parts = body.split(boundary)
            file_data = b""
            filename = "upload"
            for part in parts:
                if b'name="file"' in part:
                    m = re.search(rb'filename="([^"]+)"', part)
                    if m:
                        filename = m.group(1).decode("utf-8", errors="ignore")
                    hdr_body = part.split(b"\r\n\r\n", 1)
                    if len(hdr_body) == 2:
                        file_data = hdr_body[1].rstrip(b"\r\n--")
                        break

            if not file_data:
                self.send_api_error(400, "Empty upload")
                return

            text_content = file_data.decode("utf-8", errors="ignore")
            if filename.endswith(".lbrn") or "<LaserProject" in text_content:
                proj = Project.load_lbrn(text_content)
            elif filename.endswith(".lbrn2") or text_content.strip().startswith("{"):
                proj = Project.load_lbrn2(text_content)
            elif filename.endswith(".svg") or "<svg" in text_content:
                w, h, shapes = import_svg(text_content)
                proj = Project()
                proj.shapes = shapes
            else:
                self.send_api_error(400, "Unsupported file format")
                return

            DEVICE.current_project = proj
            self.send_json(200, {"success": True, "filename": filename, "shapes_count": len(proj.shapes)})
            return

        data = {}
        if content_len > 0:
            raw_body = self.rfile.read(content_len)
            try:
                data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                data = {}

        if path == "/api/project":
            proj = Project()
            for cs_data in data.get("cut_settings", []):
                cs = CutSetting(**cs_data)
                proj.cut_settings[cs.index] = cs
            for s_data in data.get("shapes", []):
                stype = s_data.get("Type")
                cidx = s_data.get("CutIndex", 0)
                xf = XForm(s_data.get("XForm"))
                props = {k: v for k, v in s_data.items() if k not in ("Type", "CutIndex", "XForm")}
                proj.shapes.append(Shape(stype, cut_index=cidx, xform=xf, **props))
            DEVICE.current_project = proj
            self.send_json(200, {"success": True, "shapes_count": len(proj.shapes)})

        elif path == "/api/profile":
            DEVICE.profile = DeviceProfile(**data)
            self.send_json(200, {"success": True, "profile": DEVICE.profile.to_dict()})

        elif path == "/api/preview" or path == "/api/compile":
            if not DEVICE.current_project:
                self.send_api_error(400, "No project loaded")
                return
            try:
                gcode_text = compile_project(DEVICE.current_project, DEVICE.profile)
                DEVICE.current_gcode = gcode_text
                self.send_json(200, {
                    "success": True,
                    "gcode": gcode_text,
                    "lines_count": len(gcode_text.splitlines())
                })
            except Exception as e:
                self.send_api_error(500, f"Compilation failed: {str(e)}")

        elif path == "/api/device/connect":
            port = data.get("port")
            baud = int(data.get("baudrate", 115200))
            if port and port != "sim":
                try:
                    DEVICE.serial.connect(port, baud)
                except Exception as e:
                    self.send_api_error(500, f"Cannot connect to {port}: {str(e)}")
                    return
            DEVICE.connected = True
            DEVICE.port = port
            DEVICE.baudrate = baud
            DEVICE.state = "Idle"
            DEVICE.emit_event("state_changed", {"state": DEVICE.state})
            self.send_json(200, {"connected": True, "port": port})

        elif path == "/api/device/disconnect":
            DEVICE.serial.disconnect()
            DEVICE.connected = False
            DEVICE.state = "Disconnected"
            DEVICE.emit_event("state_changed", {"state": DEVICE.state})
            self.send_json(200, {"connected": False})

        elif path == "/api/jog":
            dx = float(data.get("x", 0.0))
            dy = float(data.get("y", 0.0))
            feed = float(data.get("feed", 2000.0))
            DEVICE.head_x = max(0.0, min(DEVICE.profile.bed_width, DEVICE.head_x + dx))
            DEVICE.head_y = max(0.0, min(DEVICE.profile.bed_height, DEVICE.head_y + dy))
            DEVICE.serial.jog(dx, dy, feed=feed)
            DEVICE.emit_event("position", {"x": DEVICE.head_x, "y": DEVICE.head_y})
            self.send_json(200, {"success": True, "x": DEVICE.head_x, "y": DEVICE.head_y})

        elif path == "/api/jog/stop":
            DEVICE.serial.send_line("\x85") # GRBL jog cancel realtime byte
            self.send_json(200, {"success": True, "jogging": False})

        elif path == "/api/home":
            DEVICE.head_x = 0.0
            DEVICE.head_y = 0.0
            DEVICE.serial.home()
            DEVICE.emit_event("position", {"x": 0.0, "y": 0.0})
            self.send_json(200, {"success": True, "homed": True})

        elif path == "/api/zero":
            DEVICE.serial.zero()
            self.send_json(200, {"success": True, "zeroed": True})

        elif path == "/api/job/start":
            if not DEVICE.connected:
                self.send_api_error(409, "Device not connected")
                return
            if not DEVICE.current_project:
                self.send_api_error(400, "No project loaded")
                return
            DEVICE.state = "Run"
            DEVICE.emit_event("state_changed", {"state": "Run"})

            gcode_lines = compile_project(DEVICE.current_project, DEVICE.profile).splitlines()

            def stream_gcode_worker():
                total = len(gcode_lines)
                for i, line in enumerate(gcode_lines):
                    if DEVICE.state != "Run" and DEVICE.state != "Hold":
                        break
                    while DEVICE.state == "Hold":
                        time.sleep(0.1)
                    DEVICE.serial.send_line(line)
                    if i % 10 == 0 or i == total - 1:
                        DEVICE.emit_event("job_progress", {"progress": int((i + 1) / total * 100)})
                    time.sleep(0.002)
                DEVICE.state = "Idle"
                DEVICE.emit_event("state_changed", {"state": "Idle"})
                DEVICE.emit_event("job_completed", {"success": True})

            threading.Thread(target=stream_gcode_worker, daemon=True).start()
            self.send_json(200, {"started": True})

        elif path == "/api/job/pause":
            action = data.get("action", "pause")
            if action == "pause":
                DEVICE.state = "Hold"
                DEVICE.serial.send_line("!") # GRBL feed hold
            else:
                DEVICE.state = "Run"
                DEVICE.serial.send_line("~") # GRBL cycle start / resume
            DEVICE.emit_event("state_changed", {"state": DEVICE.state})
            self.send_json(200, {"action": action, "state": DEVICE.state})

        elif path == "/api/job/stop":
            DEVICE.state = "Idle"
            DEVICE.serial.send_line("\x18") # GRBL soft-reset
            DEVICE.emit_event("state_changed", {"state": "Idle"})
            self.send_json(200, {"stopped": True})

        else:
            self.send_api_error(404, "Endpoint not found")

def run_server(port=8080, bind="127.0.0.1"):
    server = http.server.ThreadingHTTPServer((bind, port), OpenBurnRequestHandler)
    print(f"OpenBurn Core server running on http://{bind}:{port}")
    server.serve_forever()
