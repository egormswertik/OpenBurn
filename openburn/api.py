"""
§8: REST API and Server-Sent Events (SSE) server
"""
import http.server
import json
import secrets
import re
import io
import time
import threading
from .profile import DeviceProfile
from .project import Project
from .svg import import_svg
from .gcode import compile_project

class DeviceState:
    # # impl-defined: ID-003 Virtual device state
    def __init__(self):
        self.connected = False
        self.state = "Disconnected" # Idle, Run, Hold, Alarm, Disconnected
        self.port = None
        self.baudrate = None
        self.current_project = None
        self.current_gcode = None
        self.active_token = secrets.token_hex(16)
        self.listeners = [] # SSE listener queues

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
        # Requests from 127.0.0.1 / localhost do not require token
        client_ip = self.client_address[0]
        if client_ip in ("127.0.0.1", "::1", "localhost"):
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == DEVICE.active_token:
                return True
        return False

    def do_GET(self):
        if not self.check_auth():
            self.send_api_error(401, "Unauthorized")
            return

        path = self.path.split("?")[0]
        if path == "/api/status":
            self.send_json(200, {
                "state": DEVICE.state,
                "connected": DEVICE.connected,
                "port": DEVICE.port
            })
        elif path == "/api/events":
            # SSE endpoint
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
            # Token issue
            self.send_json(200, {"token": DEVICE.active_token, "expires": 0})
            return

        if not self.check_auth():
            self.send_api_error(401, "Unauthorized")
            return

        content_len = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")

        if path == "/api/file/upload":
            # Multipart upload
            body = self.rfile.read(content_len)
            # Find file in multipart
            boundary = None
            if "boundary=" in content_type:
                boundary = content_type.split("boundary=")[1].strip().encode()
            if not boundary:
                # Naive line boundary
                boundary = body.split(b"\r\n")[0]

            parts = body.split(boundary)
            file_data = b""
            filename = "upload"
            for part in parts:
                if b'name="file"' in part:
                    m = re.search(rb'filename="([^"]+)"', part)
                    if m:
                        filename = m.group(1).decode("utf-8", errors="ignore")
                    # file contents is after double CRLF
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

        # JSON body for other endpoints
        data = {}
        if content_len > 0:
            raw_body = self.rfile.read(content_len)
            try:
                data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                data = {}

        if path == "/api/device/connect":
            port = data.get("port")
            baud = data.get("baudrate", 115200)
            DEVICE.connected = True
            DEVICE.port = port
            DEVICE.baudrate = baud
            DEVICE.state = "Idle"
            DEVICE.emit_event("state_changed", {"state": DEVICE.state})
            self.send_json(200, {"connected": True, "port": port})

        elif path == "/api/device/disconnect":
            DEVICE.connected = False
            DEVICE.state = "Disconnected"
            DEVICE.emit_event("state_changed", {"state": DEVICE.state})
            self.send_json(200, {"connected": False})

        elif path == "/api/jog":
            self.send_json(200, {"success": True, "jogging": True})

        elif path == "/api/jog/stop":
            self.send_json(200, {"success": True, "jogging": False})

        elif path == "/api/home":
            self.send_json(200, {"success": True, "homed": True})

        elif path == "/api/zero":
            self.send_json(200, {"success": True, "zeroed": True})

        elif path == "/api/job/start":
            # §8.8: If device not connected -> 409 Conflict
            if not DEVICE.connected:
                self.send_api_error(409, "Device not connected")
                return
            if not DEVICE.current_project:
                self.send_api_error(400, "No project loaded")
                return
            DEVICE.state = "Run"
            DEVICE.emit_event("state_changed", {"state": "Run"})
            DEVICE.emit_event("job_progress", {"progress": 100})
            DEVICE.state = "Idle"
            DEVICE.emit_event("job_completed", {"success": True})
            self.send_json(200, {"started": True})

        elif path == "/api/job/pause":
            action = data.get("action", "pause")
            if action == "pause":
                DEVICE.state = "Hold"
            else:
                DEVICE.state = "Run"
            DEVICE.emit_event("state_changed", {"state": DEVICE.state})
            self.send_json(200, {"action": action, "state": DEVICE.state})

        elif path == "/api/job/stop":
            DEVICE.state = "Idle"
            DEVICE.emit_event("state_changed", {"state": "Idle"})
            self.send_json(200, {"stopped": True})

        else:
            self.send_api_error(404, "Endpoint not found")

def run_server(port=8080, bind="127.0.0.1"):
    server = http.server.ThreadingHTTPServer((bind, port), OpenBurnRequestHandler)
    print(f"OpenBurn Core server running on {bind}:{port}")
    server.serve_forever()
