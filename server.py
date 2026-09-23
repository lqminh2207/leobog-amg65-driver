#!/usr/bin/env python3
import http.server
import socketserver
import json
import os
import sys
import datetime
import time
import io
import base64
import ctypes
import threading

try:
    import hid
except ImportError:
    print("hidapi chua duoc cai dat. Vui long chay: pip install hidapi")
    sys.exit(1)

try:
    from PIL import Image, ImageSequence, ImageOps
except ImportError:
    print("Pillow chua duoc cai dat. Vui long chay: pip install Pillow")
    sys.exit(1)

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

VENDOR_ID = 0x0C45   # SONiX
PRODUCT_ID = 0x800A  # LEOBOG AMG65

BLOCK_SIZE = 4096

DEVICE_LOCK = threading.RLock()


def ack_ok(resp):
    # Reply echoes the command; status is byte 3 (0x01 ok, 0xFF busy)
    return bool(resp) and len(resp) > 3 and resp[3] == 0x01


def send_cmd(h, pkt, tag="cmd"):
    full = [0x00] + list(pkt) + [0x00] * (64 - len(pkt))
    for _ in range(2):  # retry once when the device reports busy
        h.write(bytes(full[:65]))
        time.sleep(0.002)
        resp = h.read(64, timeout_ms=200)
        print(f"[{tag}] {bytes(pkt[:10]).hex(' ')} -> {bytes(resp[:8]).hex(' ') if resp else 'no reply'}")
        if not (resp and len(resp) > 3 and resp[3] == 0xFF):
            break
    return resp


def pad_blocks(payload):
    total_blocks = (len(payload) + BLOCK_SIZE - 1) // BLOCK_SIZE
    return total_blocks, bytes(payload) + bytes([0xFF]) * (total_blocks * BLOCK_SIZE - len(payload))


def load_flash_lib():
    dylib_path = os.path.join(DIRECTORY, "libusbflash.dylib")
    if not os.path.exists(dylib_path):
        raise RuntimeError("Chua tim thay libusbflash.dylib")
    return ctypes.CDLL(dylib_path)


def flash_stream(h, open_pkt, padded_data, tag):
    """Config mode, open a flash session with open_pkt, stream 4096-byte blocks to EP6 with per-block ack, commit."""
    total_blocks = len(padded_data) // BLOCK_SIZE
    flash_lib = load_flash_lib()

    if not ack_ok(send_cmd(h, [0x04, 0x18], tag)):
        raise RuntimeError("Ban phim khong vao che do cau hinh (04 18)")
    if not ack_ok(send_cmd(h, list(open_pkt) + [total_blocks & 0xFF, (total_blocks >> 8) & 0xFF], tag)):
        raise RuntimeError(f"Ban phim tu choi phien nap ({open_pkt[0]:02x} {open_pkt[1]:02x})")

    ret = flash_lib.leobog_flash_open()
    if ret != 0:
        raise RuntimeError(f"Khong the mo cong USB Interface 3 cua ban phim (ma loi {ret})")
    try:
        buf = (ctypes.c_uint8 * len(padded_data)).from_buffer_copy(padded_data)
        base = ctypes.addressof(buf)
        for i in range(total_blocks):
            for _ in range(2):
                h.read(64, timeout_ms=10)
            ret = flash_lib.leobog_flash_write_block(ctypes.c_void_p(base + i * BLOCK_SIZE))
            if ret != 0:
                raise RuntimeError(f"Loi ghi block {i + 1}/{total_blocks} (ma loi {ret})")
            time.sleep(0.005)
            for _ in range(100):
                resp = h.read(64, timeout_ms=600)
                if i == 0 or not ack_ok(resp):
                    print(f"[{tag}] block {i + 1}/{total_blocks} -> {bytes(resp[:8]).hex(' ') if resp else 'no reply'}")
                if ack_ok(resp):
                    break
            else:
                raise RuntimeError(f"Ban phim khong xac nhan block {i + 1}/{total_blocks}")
            if i == 0:
                time.sleep(0.5)  # first block triggers a flash erase
    finally:
        flash_lib.leobog_flash_close()

    send_cmd(h, [0x04, 0x02], tag)
    return total_blocks


def decode_data_url(data_url):
    return base64.b64decode(data_url.split(",", 1)[1] if "," in data_url else data_url)

class KeyboardController:
    def __init__(self):
        self.device_info = None

    def find_device_path(self):
        devices = hid.enumerate()
        for d in devices:
            if d.get("vendor_id") == VENDOR_ID and d.get("product_id") == PRODUCT_ID:
                # Preferred interface: interface_number == 2 or usage_page == 0xFF68
                if d.get("usage_page") == 0xFF68 or d.get("interface_number") == 2:
                    return d["path"]
        for d in devices:
            if d.get("vendor_id") == VENDOR_ID and d.get("product_id") == PRODUCT_ID:
                return d["path"]
        return None

    def send_checksum_cmd(self, payload):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
        h = hid.device()
        try:
            h.open_path(path)
            buf = [0] * 32
            for i in range(min(len(payload), 32)):
                buf[i] = payload[i]
            checksum = sum(buf[:32]) & 0xFF
            pkt = [0x00] + buf + [checksum] + [0x00] * 31
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
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
        
        m = int(mode) & 0xFF
        if m == 0 and not is_rainbow and brightness == 0:
            m = 19

        br = int(brightness)
        if 0 <= br <= 4:
            br = br + 1
        br = max(1, min(5, br))
        if m == 19:
            br = 0

        sp = int(speed)
        if 0 <= sp <= 4:
            sp = sp + 1
        sp = max(1, min(5, sp))

        red = max(0, min(255, int(r)))
        green = max(0, min(255, int(g)))
        blue = max(0, min(255, int(b)))
        rainbow_flag = 1 if is_rainbow else 0

        h = hid.device()
        try:
            h.open_path(path)

            def send_raw(payload):
                pkt = [0x00] + list(payload) + [0x00] * (64 - len(payload))
                h.write(bytes(pkt[:65]))
                time.sleep(0.015)
                return h.read(64, timeout_ms=100)

            # Sequence 1: 0x13 Primary Lighting Protocol
            send_raw([0x04, 0x18])
            send_raw([0x04, 0x13, 0, 0, 0, 0, 0, 0, 1])
            p1 = [0] * 64
            p1[0] = m
            p1[1] = red
            p1[2] = green
            p1[3] = blue
            p1[8] = rainbow_flag
            p1[9] = br
            p1[10] = sp
            p1[11] = 0
            p1[14] = 0xAA
            p1[15] = 0x55
            send_raw(p1)
            send_raw([0x04, 0x02])
            send_raw([0x04, 0xF0])

            # Sequence 2: 0x17 Secondary Global Protocol
            send_raw([0x04, 0x18])
            send_raw([0x04, 0x17, m, 0, 0, 0, 0, 0, 1])
            p2 = [0] * 64
            p2[0] = 0
            p2[1] = 1
            p2[2] = 0
            p2[5] = rainbow_flag
            p2[6] = sp
            p2[7] = br
            p2[8] = red
            p2[9] = green
            p2[10] = blue
            p2[62] = 0xAA
            p2[63] = 0x55
            send_raw(p2)
            send_raw([0x04, 0x02])
            send_raw([0x04, 0xF0])

            return {"success": True, "mode": m, "brightness": br, "speed": sp}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            except Exception:
                pass

    def upload_lcd_image(self, data_url, slot=1):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}

        try:
            im = Image.open(io.BytesIO(decode_data_url(data_url)))
        except Exception as e:
            return {"success": False, "error": f"Loi doc file anh: {str(e)}"}

        # 1. Prepare frames & RGB565 buffer (little-endian, 240x135, top-down)
        frames_rgb565 = bytearray()
        delays = []
        frame_count = 0
        max_frames = 130

        try:
            for frame in ImageSequence.Iterator(im):
                if frame_count >= max_frames:
                    break
                frame_count += 1

                # Firmware delay unit is 2 ms
                duration = frame.info.get("duration", 100) or 100
                delays.append(max(1, min(255, duration // 2)))

                f_rgb = frame.convert("RGB")
                f_resized = ImageOps.fit(f_rgb, (240, 135), method=Image.Resampling.LANCZOS)

                for r, g, b in f_resized.getdata():
                    val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                    frames_rgb565.append(val & 0xFF)
                    frames_rgb565.append((val >> 8) & 0xFF)
        except Exception as e:
            return {"success": False, "error": f"Loi chuyen doi RGB565: {str(e)}"}

        if frame_count == 0:
            return {"success": False, "error": "Khong co khung hinh hop le"}

        # 2. Build Flash Buffer with 256-byte header
        header = bytearray([0xFF] * 256)
        header[0] = frame_count
        for i, d in enumerate(delays):
            header[i + 1] = d
        full_payload = header + frames_rgb565
        total_blocks, padded_data = pad_blocks(full_payload)

        # 3. Handshake and Flash Sequence (mirrors the official Windows driver)
        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            flash_stream(h, [0x04, 0x72, slot, 0, 0, 0, 0, 0], padded_data, "lcd")

            # Select the uploaded slot for display (wired-mode packet, also sets the clock)
            now = datetime.datetime.now()
            send_cmd(h, [0x04, 0x18], "lcd")
            send_cmd(h, [0x04, 0x28, 0, 0, 0, 0, 0, 0, 0x01], "lcd")
            sel = [0] * 64
            sel[1] = slot
            sel[2] = 0x5A
            sel[3:9] = [now.year % 2000, now.month, now.day, now.hour, now.minute, now.second]
            sel[10] = (now.weekday() + 1) % 7
            sel[62] = 0xAA
            sel[63] = 0x55
            send_cmd(h, sel, "lcd")
            send_cmd(h, [0x04, 0x02], "lcd")

            return {
                "success": True,
                "frames": frame_count,
                "blocks": total_blocks,
                "bytes": len(full_payload)
            }
        except Exception as e:
            try:
                send_cmd(h, [0x04, 0x02], "lcd")
            except Exception:
                pass
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def read_config(self):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
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
            return {"success": False, "error": "Ban phim chua duoc cam"}
        
        h = hid.device()
        try:
            h.open_path(path)
            prep = [0x00] + [0x00] * 64
            prep[1] = 0x04
            prep[2] = 0x18
            h.write(bytes(prep[:65]))
            time.sleep(0.04)

            for b in range(8):
                block = cfg[b * 64 : (b + 1) * 64]
                pkt = [0x00] + block
                h.write(bytes(pkt[:65]))
                time.sleep(0.01)

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
            mode = data.get("mode", 5)
            brightness = data.get("brightness", 4)
            speed = data.get("speed", 3)
            r = data.get("r", 255)
            g = data.get("g", 0)
            b = data.get("b", 0)
            is_rainbow = data.get("isRainbow", True)
            res = controller.set_lighting(mode, brightness, speed, r, g, b, is_rainbow)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/upload-lcd":
            image_data = data.get("image", "")
            if not image_data:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "Khong co du lieu anh"}).encode("utf-8"))
                return
            res = controller.upload_lcd_image(image_data)
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
