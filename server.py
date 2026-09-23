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
import ctypes.util
import subprocess
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

LED_ROWS, LED_COLS = 5, 63
LED_COUNT = LED_ROWS * LED_COLS


def led_device_index(row, col):
    # Panel is wired in 14-column blocks (last one 7 wide), row-major inside each block
    if col < 56:
        return (col // 14) * 70 + row * 14 + col % 14
    return 280 + row * 7 + (col - 56)


LIVE_INTERVAL = 1.0
DEVICE_LOCK = threading.RLock()

# 3x5 glyphs for the clock layer, one bit per pixel, MSB left
FONT_3X5 = {
    "0": [0b111, 0b101, 0b101, 0b101, 0b111], "1": [0b010, 0b110, 0b010, 0b010, 0b111],
    "2": [0b111, 0b001, 0b111, 0b100, 0b111], "3": [0b111, 0b001, 0b111, 0b001, 0b111],
    "4": [0b101, 0b101, 0b111, 0b001, 0b001], "5": [0b111, 0b100, 0b111, 0b001, 0b111],
    "6": [0b111, 0b100, 0b111, 0b101, 0b111], "7": [0b111, 0b001, 0b010, 0b010, 0b010],
    "8": [0b111, 0b101, 0b111, 0b101, 0b111], "9": [0b111, 0b101, 0b111, 0b001, 0b111],
    ":": [0b000, 0b010, 0b000, 0b010, 0b000], " ": [0b000, 0b000, 0b000, 0b000, 0b000],
}


def cpu_ticks():
    libc = ctypes.CDLL(ctypes.util.find_library("c"))

    class CpuLoad(ctypes.Structure):
        _fields_ = [("ticks", ctypes.c_uint * 4)]  # user, system, idle, nice

    count = ctypes.c_uint(4)
    info = CpuLoad()
    if libc.host_statistics(libc.mach_host_self(), 3, ctypes.byref(info), ctypes.byref(count)) != 0:
        return None
    t = list(info.ticks)
    return t[0] + t[1] + t[3], t[2]


def memory_percent():
    out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3).stdout
    pages = {}
    for line in out.splitlines():
        key, _, value = line.partition(":")
        digits = value.strip().rstrip(".")
        if digits.isdigit():
            pages[key.strip()] = int(digits)
    used = sum(pages.get(k, 0) for k in ("Pages active", "Pages wired down", "Pages occupied by compressor"))
    total = used + sum(pages.get(k, 0) for k in ("Pages free", "Pages inactive", "Pages speculative"))
    return 100.0 * used / total if total else 0.0


def net_bytes():
    out = subprocess.run(["netstat", "-ib"], capture_output=True, text=True, timeout=3).stdout
    seen, rx, tx = set(), 0, 0
    for line in out.splitlines()[1:]:
        f = line.split()
        if len(f) < 10 or f[0] == "lo0" or f[0] in seen:
            continue
        seen.add(f[0])
        try:
            rx += int(f[6])
            tx += int(f[9])
        except ValueError:
            pass
    return rx, tx


DOCK_BADGE_SCRIPT = """
tell application "System Events" to tell process "Dock"
  set out to ""
  repeat with e in UI elements of list 1
    set b to ""
    try
      set b to value of attribute "AXStatusLabel" of e as text
    end try
    if b is not "" and b is not "missing value" then set out to out & (name of e) & "\t" & b & "\n"
  end repeat
  return out
end tell
"""

# Dock badge colours; anything else falls back to cyan
APP_COLORS = {
    "slack": "#e01e5a", "mail": "#0a84ff", "messages": "#30d158", "discord": "#5865f2",
    "telegram": "#2aabee", "messenger": "#a334fa", "notion": "#ffffff", "zalo": "#0068ff",
    "google chrome": "#f4b400", "brave browser": "#fb542b", "system settings": "#8e8e93",
}
DEFAULT_APP_COLOR = "#00f0ff"


def dock_badges():
    """{app name: badge text} for every Dock icon showing a badge. Needs Accessibility permission."""
    proc = subprocess.run(["osascript", "-e", DOCK_BADGE_SCRIPT], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        if "assistive access" in err or "1719" in err:
            raise RuntimeError("Chua cap quyen Tro nang (Accessibility) cho ung dung chay server")
        raise RuntimeError(err.splitlines()[-1] if err else "Khong doc duoc badge tren Dock")
    badges = {}
    for line in proc.stdout.splitlines():
        name, _, badge = line.partition("\t")
        if name and badge:
            badges[name.strip()] = badge.strip()
    return badges


def blank_frame():
    return ["#000000"] * (LED_ROWS * LED_COLS)


def heat_color(fraction):
    # green -> amber -> red
    r = int(255 * min(1.0, fraction * 2))
    g = int(255 * min(1.0, (1.0 - fraction) * 2))
    return "#%02x%02x00" % (r, g)


def draw_bar(frame, percent, rows, color=None):
    lit = int(round(LED_COLS * max(0.0, min(100.0, percent)) / 100.0))
    for row in rows:
        for col in range(lit):
            frame[row * LED_COLS + col] = color or heat_color(col / (LED_COLS - 1))


def draw_text(frame, text, color, left=None, top=0):
    width = len(text) * 4 - 1
    left = (LED_COLS - width) // 2 if left is None else left
    for i, ch in enumerate(text):
        glyph = FONT_3X5.get(ch)
        if not glyph:
            continue
        for row, bits in enumerate(glyph):
            for bit in range(3):
                col = left + i * 4 + bit
                if bits & (1 << (2 - bit)) and 0 <= col < LED_COLS and top + row < LED_ROWS:
                    frame[(top + row) * LED_COLS + col] = color


def draw_badges(frame, badges):
    """One coloured slot per app with a Dock badge: the number if it has one, a bar otherwise."""
    apps = sorted(badges)[:4]
    if not apps:
        return
    width = LED_COLS // len(apps)
    for i, app in enumerate(apps):
        color = APP_COLORS.get(app.lower(), DEFAULT_APP_COLOR)
        start = i * width
        digits = "".join(ch for ch in badges[app] if ch.isdigit())[:3]
        if digits:
            text_width = len(digits) * 4 - 1
            draw_text(frame, digits, color, left=start + max(0, (width - 1 - text_width) // 2))
        else:
            for row in range(1, 4):  # dot badge (no count): a solid bar
                for col in range(start, start + width - 1):
                    frame[row * LED_COLS + col] = color


class LiveLedWorker(threading.Thread):
    """Renders a live layer on the Mac and pushes one 04 35 frame per second."""

    MODES = ("cpu", "ram", "net", "clock", "notify")

    def __init__(self, controller, mode):
        super().__init__(daemon=True)
        self.controller = controller
        self.mode = mode
        self.stop_event = threading.Event()
        self.prev_cpu = cpu_ticks()
        self.prev_net = net_bytes() if mode == "net" else None
        self.peak = 1.0
        self.prev_badges = None
        self.flash_ticks = 0

    def cpu_percent(self):
        now = cpu_ticks()
        if not now or not self.prev_cpu:
            return 0.0
        busy = now[0] - self.prev_cpu[0]
        idle = now[1] - self.prev_cpu[1]
        self.prev_cpu = now
        return 100.0 * busy / (busy + idle) if busy + idle else 0.0

    def render(self):
        frame = blank_frame()
        if self.mode == "cpu":
            draw_bar(frame, self.cpu_percent(), range(LED_ROWS))
        elif self.mode == "ram":
            draw_bar(frame, memory_percent(), range(LED_ROWS))
        elif self.mode == "net":
            rx, tx = net_bytes()
            down, up = rx - self.prev_net[0], tx - self.prev_net[1]
            self.prev_net = (rx, tx)
            self.peak = max(self.peak * 0.9, down, up, 64 * 1024)
            draw_bar(frame, 100.0 * down / self.peak, (0, 1), "#00f0ff")
            draw_bar(frame, 100.0 * up / self.peak, (3, 4), "#ff007f")
        elif self.mode == "notify":
            badges = dock_badges()
            if self.prev_badges is not None and badges != self.prev_badges:
                self.flash_ticks = 4  # blink for a few seconds on any change
            self.prev_badges = badges
            if self.flash_ticks:
                self.flash_ticks -= 1
                if self.flash_ticks % 2:
                    return frame  # blank half of the blink
            draw_badges(frame, badges)
        elif self.mode == "clock":
            now = datetime.datetime.now()
            draw_text(frame, now.strftime("%H:%M" if now.second % 2 else "%H %M"), "#00f0ff")
        return frame

    def run(self):
        while not self.stop_event.is_set():
            try:
                res = self.controller.led_matrix_preview(self.render())
                if not res.get("success"):
                    print(f"[led] live {self.mode} stopped: {res.get('error')}")
                    break
            except Exception as e:
                print(f"[led] live {self.mode} stopped: {e}")
                break
            # reading Dock badges spawns osascript, so poll it less often
            self.stop_event.wait(3.0 if self.mode == "notify" else LIVE_INTERVAL)




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


def parse_rgb(value):
    if isinstance(value, str):
        v = value.lstrip("#")
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    r, g, b = value
    return int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF


def decode_data_url(data_url):
    return base64.b64decode(data_url.split(",", 1)[1] if "," in data_url else data_url)

class KeyboardController:
    def __init__(self):
        self.device_info = None
        self.live_worker = None

    def set_live_layer(self, mode):
        if self.live_worker:
            self.live_worker.stop_event.set()
            self.live_worker = None
        if mode in LiveLedWorker.MODES:
            if not self.find_device_path():
                return {"success": False, "error": "Ban phim chua duoc cam"}
            self.live_worker = LiveLedWorker(self, mode)
            self.live_worker.start()
        elif mode not in ("off", None, ""):
            return {"success": False, "error": f"Khong ho tro lop '{mode}'"}
        return {"success": True, "mode": mode}

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
        DEVICE_LOCK.acquire()
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
            finally:
                DEVICE_LOCK.release()

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
        DEVICE_LOCK.acquire()
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
            finally:
                DEVICE_LOCK.release()

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

    def led_matrix_preview(self, pixels):
        """Show one frame live (not saved). pixels: 315 colors, row-major 5x63."""
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
        if len(pixels) != LED_COUNT:
            return {"success": False, "error": f"Can {LED_COUNT} diem anh"}

        buf = bytearray(1024)
        for row in range(LED_ROWS):
            for col in range(LED_COLS):
                dev = led_device_index(row, col)
                buf[dev * 3:dev * 3 + 3] = bytes(parse_rgb(pixels[row * LED_COLS + col]))
        buf[946] = 0xAA
        buf[947] = 0x55

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            if not ack_ok(send_cmd(h, [0x04, 0x18], "led")):
                raise RuntimeError("Ban phim khong vao che do cau hinh (04 18)")
            if not ack_ok(send_cmd(h, [0x04, 0x35, 0, 0, 0, 0, 0, 0, 0x0F], "led")):
                raise RuntimeError("Ban phim tu choi lenh hien thi LED (04 35)")
            for _ in range(2):
                h.read(64, timeout_ms=10)
            for i in range(16):
                h.write(bytes([0x00]) + bytes(buf[i * 64:(i + 1) * 64]))
                h.read(64, timeout_ms=500)
            send_cmd(h, [0x04, 0x02], "led")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def led_matrix_upload(self, frames, speed=10, brightness=100, target="animation"):
        """Save an animation to the keyboard. frames: list of 315-color frames, row-major 5x63."""
        self.set_live_layer("off")
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}

        opcode, max_frames = (0x31, 200) if target == "boot" else (0x33, 260)
        frames = frames[:max_frames]
        if not frames or any(len(f) != LED_COUNT for f in frames):
            return {"success": False, "error": f"Moi khung hinh can {LED_COUNT} diem anh"}

        speed = max(1, min(100, int(speed)))
        scale = max(0, min(100, int(brightness))) / 100.0

        payload = bytearray(4 + len(frames) * LED_COUNT * 3 + 3)
        payload[0:2] = len(frames).to_bytes(2, "little")
        payload[2:4] = (0x66 - speed).to_bytes(2, "little")
        for fi, frame in enumerate(frames):
            base = 4 + fi * LED_COUNT * 3
            for row in range(LED_ROWS):
                for col in range(LED_COLS):
                    r, g, b = parse_rgb(frame[row * LED_COLS + col])
                    off = base + led_device_index(row, col) * 3
                    payload[off:off + 3] = bytes((int(r * scale), int(g * scale), int(b * scale)))
        payload[-2] = 0xAA
        payload[-1] = 0x55
        total_blocks, padded_data = pad_blocks(payload)

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            flash_stream(h, [0x04, opcode, 0, 0, 0, 0, 0, 0], padded_data, "led")
            send_cmd(h, [0x04, 0xF0], "led")
            return {"success": True, "frames": len(frames), "blocks": total_blocks}
        except Exception as e:
            try:
                send_cmd(h, [0x04, 0x02], "led")
            except Exception:
                pass
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def led_matrix_from_image(self, data_url, max_frames=260):
        """Downscale an image/GIF to 5x63 frames for the editor."""
        try:
            im = Image.open(io.BytesIO(decode_data_url(data_url)))
            frames, delays = [], []
            for frame in ImageSequence.Iterator(im):
                if len(frames) >= max_frames:
                    break
                small = ImageOps.fit(frame.convert("RGB"), (LED_COLS, LED_ROWS), method=Image.Resampling.BOX)
                frames.append(["#%02x%02x%02x" % px for px in small.getdata()])
                delays.append(frame.info.get("duration", 100) or 100)
            return {"success": True, "frames": frames, "delays": delays}
        except Exception as e:
            return {"success": False, "error": f"Loi doc file anh: {str(e)}"}

    def read_config(self):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
        h = hid.device()
        DEVICE_LOCK.acquire()
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
            finally:
                DEVICE_LOCK.release()

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
        elif self.path == "/api/led-matrix/preview":
            res = controller.led_matrix_preview(data.get("pixels", []))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/led-matrix/upload":
            res = controller.led_matrix_upload(data.get("frames", []), data.get("speed", 10),
                                               data.get("brightness", 100), data.get("target", "animation"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/led-matrix/live":
            res = controller.set_live_layer(data.get("mode", "off"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/led-matrix/import":
            res = controller.led_matrix_from_image(data.get("image", ""))
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
