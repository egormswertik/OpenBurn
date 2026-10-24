"""
Unit tests for REST API (§8)
"""
import unittest
import threading
import time
import json
import urllib.request
import urllib.error
from openburn.api import OpenBurnRequestHandler, DEVICE, http

class TestOpenBurnAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 18080), OpenBurnRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_status_endpoint(self):
        req = urllib.request.Request("http://127.0.0.1:18080/api/status")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("state", data)
            self.assertIn("connected", data)

    def test_connect_and_token(self):
        req = urllib.request.Request("http://127.0.0.1:18080/api/connect", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("token", data)
            self.assertEqual(data["expires"], 0)

    def test_job_start_without_device_409(self):
        DEVICE.connected = False
        req = urllib.request.Request("http://127.0.0.1:18080/api/job/start", data=b"{}", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 409)
        data = json.loads(ctx.exception.read().decode())
        self.assertEqual(data["message"], "Device not connected")

if __name__ == "__main__":
    unittest.main()
