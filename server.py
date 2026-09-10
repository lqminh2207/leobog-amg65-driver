#!/usr/bin/env python3
import http.server
import socketserver
import webbrowser
import os
import sys
import json
import datetime
import time

try:
    import hid
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "hidapi"])
    import hid

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class KeyboardController:
    VID = 0x0C45
    PID = 0x800A

    def find_device_path(self):
        devices = hid.enumerate(self.VID, self.PID)
        for d in devices:
            if d.get("usage_page") == 0xFF68 and d.get("usage") == 0x61:
                return d["path"]
        for d in devices:
            if d.get("interface_number") == 2:
                return d["path"]
        for d in devices:
            if d.get("usage_page") != 0x01:
                return d["path"]
        return None

    def send_checksum_cmd(self, buf32):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Bàn phím LEOBOG AMG65 chưa được kết nối"}
        h = hid.device()
        try:
            h.open_path(path)
            payload = [0] * 32
            for i in range(min(32, len(buf32))):
                payload[i] = buf32[i]
            chk = sum(payload[:32]) & 0xFF
            pkt = [0x00] + payload + [chk] + [0] * 32
            h.write(bytes(pkt[:65]))
            resp = h.read(64, timeout_ms=300)
            return {"success": True, "response": list(resp) if resp else []}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            except Exception:
                pass

    def get_status(self):
        path = self.find_device_path()
        if not path:
            return {"connected": False, "device": None, "battery": 0, "charging": False}
        
        res = self.send_checksum_cmd([0x20, 0x01])
        if res.get("success") and res.get("response") and len(res["response"]) >= 4:
            resp = res["response"]
            raw_bat = resp[3]
            charging = (raw_bat == 0xFF)
            battery = 100 if charging else max(0, min(100, raw_bat))
            return {
                "connected": True,
                "device": "LEOBOG AMG65",
                "battery": battery,
                "charging": charging,
                "vid": "0x0C45",
                "pid": "0x800A"
            }
        return {"connected": True, "device": "LEOBOG AMG65", "battery": 100, "charging": True}

    def sync_time(self):
        now = datetime.datetime.now()
        buf = [0] * 32
        buf[0] = 0x0C
        buf[1] = 0x10
        buf[2] = 0x00
        buf[3] = 0x00
        buf[4] = 0x01
        buf[5] = 0x5A
        buf[6] = now.year % 100
        buf[7] = now.month
        buf[8] = now.day
        buf[9] = now.hour
        buf[10] = now.minute
        buf[11] = now.second
        buf[12] = (now.weekday() + 1) % 7
        buf[18] = 0xAA
        buf[19] = 0x55
        return self.send_checksum_cmd(buf)

    def set_lighting(self, mode, brightness, speed, r, g, b, is_rainbow):
        buf = [0] * 32
        buf[0] = 0x05
        buf[1] = 0x10
        buf[2] = 0x00
        buf[3] = mode & 0xFF
        buf[4] = brightness & 0x07
        buf[5] = speed & 0x07
        buf[6] = 0x00 if is_rainbow else 0x01
        buf[7] = 0x00
        buf[8] = r & 0xFF
        buf[9] = g & 0xFF
        buf[10] = b & 0xFF
        buf[18] = 0xAA
        buf[19] = 0x55
        return self.send_checksum_cmd(buf)

    def read_config(self):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Bàn phím chưa được cắm"}
        h = hid.device()
        try:
            h.open_path(path)
            full_buf = []
            for b in range(8):
                pkt = [0x00] + [0x00] * 64
                pkt[1] = 0x04
                pkt[2] = 0xF5
                pkt[3] = b
                pkt[9] = 0x08
                h.write(bytes(pkt[:65]))
                resp = h.read(64, timeout_ms=300)
                if resp:
                    full_buf.extend(resp)
                else:
                    full_buf.extend([0] * 64)
            return {"success": True, "config": full_buf}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            except Exception:
                pass

    def remap_key(self, key_index, new_key_code):
        cfg_res = self.read_config()
        if not cfg_res.get("success"):
            return cfg_res
        cfg = cfg_res["config"]
        offset = key_index * 4
        if offset + 2 < len(cfg):
            cfg[offset] = 0x00
            cfg[offset + 1] = new_key_code & 0xFF
            cfg[offset + 2] = (new_key_code >> 8) & 0xFF

        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Bàn phím chưa được cắm"}
        
        h = hid.device()
        try:
            h.open_path(path)
            # 1. Enter config write mode
            prep = [0x00] + [0x00] * 64
            prep[1] = 0x04
            prep[2] = 0x18
            h.write(bytes(prep[:65]))
            time.sleep(0.04)

            # 2. Write 8 blocks
            for b in range(8):
                block = cfg[b * 64 : (b + 1) * 64]
                pkt = [0x00] + block
                h.write(bytes(pkt[:65]))
                time.sleep(0.01)

            # 3. Commit
            commit = [0x00] + [0x00] * 64
            commit[1] = 0x04
            commit[2] = 0x02
            h.write(bytes(commit[:65]))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            except Exception:
                pass


controller = KeyboardController()

class AppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            status = controller.get_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode("utf-8"))
            return
        elif self.path == "/api/config":
            res = controller.read_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if self.path == "/api/sync-time":
            res = controller.sync_time()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/lighting":
            mode = data.get("mode", 1)
            brightness = data.get("brightness", 4)
            speed = data.get("speed", 3)
            r = data.get("r", 0)
            g = data.get("g", 255)
            b = data.get("b", 255)
            is_rainbow = data.get("isRainbow", True)
            res = controller.set_lighting(mode, brightness, speed, r, g, b, is_rainbow)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/remap":
            key_index = data.get("keyIndex", 0)
            new_key_code = data.get("newKeyCode", 0)
            res = controller.remap_key(key_index, new_key_code)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

def main():
    os.chdir(DIRECTORY)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), AppHandler) as httpd:
        url = f"http://localhost:{PORT}"
        print("==================================================")
        print(" LEOBOG AMG65 macOS Native Driver Server Started!")
        print(f" Truy cap: {url}")
        print("==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDa dung server.")
            sys.exit(0)

if __name__ == "__main__":
    main()
