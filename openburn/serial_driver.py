"""
GRBL Serial Communication Driver
"""
import time
import threading

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

def get_available_ports():
    if not serial or not hasattr(serial, "tools"):
        return []
    try:
        return [{"port": p.device, "description": p.description} for p in serial.tools.list_ports.comports()]
    except Exception:
        return []

class GrblSerial:
    def __init__(self):
        self.ser = None
        self.port = None
        self.baudrate = 115200
        self.is_connected = False
        self.lock = threading.Lock()
        self.rx_thread = None
        self.stop_event = threading.Event()
        self.on_state_callback = None
        self.on_log_callback = None

    def connect(self, port, baudrate=115200):
        if serial is None:
            raise RuntimeError("pyserial is not installed. Run: pip install pyserial")
        self.disconnect()
        with self.lock:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
            self.port = port
            self.baudrate = baudrate
            self.is_connected = True
            self.stop_event.clear()

            # Wake up GRBL: reset controller
            self.ser.write(b"\r\n\r\n")
            time.sleep(1.0)
            self.ser.reset_input_buffer()

        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.rx_thread.start()
        return True

    def disconnect(self):
        self.stop_event.set()
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self.is_connected = False

    def send_line(self, line):
        if not self.is_connected or not self.ser:
            return False
        with self.lock:
            clean = line.strip()
            if not clean:
                return True
            self.ser.write((clean + "\n").encode("utf-8"))
            if self.on_log_callback:
                self.on_log_callback(f"> {clean}")
            return True

    def jog(self, dx, dy, feed=1000):
        # GRBL Jog syntax
        cmd = f"$J=G91 G21 X{dx:g} Y{dy:g} F{feed:g}"
        return self.send_line(cmd)

    def home(self):
        return self.send_line("$H")

    def zero(self):
        return self.send_line("G92 X0 Y0")

    def _rx_loop(self):
        buf = ""
        while not self.stop_event.is_set() and self.is_connected:
            try:
                data = self.ser.read(100)
                if data:
                    buf += data.decode("utf-8", errors="ignore")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            if self.on_log_callback:
                                self.on_log_callback(f"< {line}")
                else:
                    time.sleep(0.01)
            except Exception:
                break
        self.is_connected = False
