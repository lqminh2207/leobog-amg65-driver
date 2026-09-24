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
import re
import secrets
import hmac
import shutil

try:
    import hid
except ImportError:
    print("hidapi chua duoc cai dat. Vui long chay: pip install hidapi")
    sys.exit(1)

try:
    from PIL import Image, ImageSequence, ImageOps, ImageEnhance
except ImportError:
    print("Pillow chua duoc cai dat. Vui long chay: pip install Pillow")
    sys.exit(1)

PORT = 8080

if getattr(sys, "frozen", False):  # inside the .app bundle
    DIRECTORY = sys._MEIPASS
else:
    DIRECTORY = os.path.dirname(os.path.abspath(__file__))
# Shared by the .app and dev runs: the keymap is write-only on the keyboard, so two
# diverging configs would let one of them wipe the other's remaps
CONFIG_DIR = os.path.expanduser("~/Library/Application Support/LEOBOG AMG65 Studio")
os.makedirs(CONFIG_DIR, exist_ok=True)

# Every /api call must carry this; it only reaches the page we serve ourselves
API_TOKEN = secrets.token_urlsafe(24)

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


def ioreg_number(args, key):
    out = subprocess.run(["ioreg"] + args, capture_output=True, text=True, timeout=5).stdout
    m = re.search(r'"%s"\s*=\s*(\d+)' % re.escape(key), out)
    return int(m.group(1)) if m else None


def gpu_percent():
    return ioreg_number(["-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"], "Device Utilization %") or 0


def idle_seconds():
    ns = ioreg_number(["-c", "IOHIDSystem", "-d", "4", "-w", "0"], "HIDIdleTime")
    return ns / 1e9 if ns is not None else 0.0


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
        if "1743" in err or "Not authorized" in err:
            raise RuntimeError("Chua cho phep dieu khien System Events (Cai dat > Quyen rieng tu > Tu dong hoa)")
        raise RuntimeError(err.splitlines()[-1] if err else "Khong doc duoc badge tren Dock")
    badges = {}
    for line in proc.stdout.splitlines():
        name, _, badge = line.partition("\t")
        if name and badge:
            badges[name.strip()] = badge.strip()
    return badges


def boost_led_frame(img):
    """Averaging a big image down to 63x5 mixes bright strokes into dark backgrounds.
    Stretch contrast (hue kept), saturate, lift mid-tones, and turn near-black fully off."""
    img = ImageOps.autocontrast(img, cutoff=1, preserve_tone=True)
    img = ImageEnhance.Color(img).enhance(1.8)
    img = img.point(lambda v: round(255 * (v / 255) ** 0.6))
    out = [(0, 0, 0) if max(px) < 40 else px for px in img.getdata()]
    img.putdata(out)
    return img


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

    MODES = ("cpu", "gpu", "ram", "net", "clock", "notify")

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
        self.error = None

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
        elif self.mode == "gpu":
            draw_bar(frame, gpu_percent(), range(LED_ROWS))
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
            if self.controller.reminding:
                self.stop_event.wait(0.5)
                continue
            try:
                res = self.controller.led_matrix_preview(self.render())
                self.error = None if res.get("success") else res.get("error")
            except Exception as e:
                self.error = str(e)
            if self.error:
                print(f"[led] live {self.mode}: {self.error}")
            # reading Dock badges spawns osascript, so poll it less often
            self.stop_event.wait(3.0 if self.mode == "notify" else LIVE_INTERVAL)


USER_CONFIG_PATH = os.path.join(CONFIG_DIR, "user_config.json")
LEGACY_CONFIG_PATH = os.path.join(DIRECTORY, "user_config.json")
if not os.path.exists(USER_CONFIG_PATH) and os.path.exists(LEGACY_CONFIG_PATH):
    shutil.copy2(LEGACY_CONFIG_PATH, USER_CONFIG_PATH)

# key_index == light_index for every key on this board (from the driver's KeyboardLayout.xml).
# 74 is the "/" key: our layout has it, the driver's XML omits it.
KEY_INDEXES = [
    0, 13, 14, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 32, 33, 34, 35, 36, 37, 38, 39, 40,
    41, 42, 43, 44, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 64, 65, 66, 67, 68, 69, 70,
    71, 72, 73, 74, 75, 76, 80, 81, 82, 83, 85, 87, 88, 89, 90, 91, 92, 104, 105, 106, 108
]
REMAP_SLOTS = 128

# Firmware range confirmed on hardware: 7 is brightest, 8+ wraps to dim
MAX_LED_BRIGHTNESS = 7

DEFAULT_SETTINGS = {
    "gameMode": 0, "disableAltTab": 0, "disableAltF4": 0, "disableWin": 0,
    "fnToggle": 0, "sleepLight": 1, "ledBrightness": 7,
}


def modifier_mask(usage):
    # 0xE0..0xE7 (Ctrl/Shift/Alt/Gui) collapse into one modifier bit
    return 1 << (usage - 0xE0) if 0xE0 <= usage <= 0xE7 else 0


def remap_entry(kind, code, entry=None, macros=None):
    """One 4-byte slot of the 04 11 table: {type, p1, p2, p3}."""
    code = int(code)
    if kind == "macro":  # code = macro id; mode 0 once, 1 N times, 2 until pressed again
        ids = [m["id"] for m in macros or []]
        if code not in ids:
            return [0x00, 0x00, 0x00, 0x00]
        entry = entry or {}
        mode = int(entry.get("mode", 0))
        count = max(1, min(255, int(entry.get("count", 1)))) if mode == 1 else 0
        return [0x06, ids.index(code), mode, count]
    if kind == "disable":
        return [0x05, 0x03, 0x00, 0x00]
    if kind == "modifier":
        return [0x02, modifier_mask(code), 0x00, 0x00]
    if kind == "media":
        return [0x03, code & 0xFF, 0x00, 0x00]
    if kind == "consumer":  # 16-bit consumer usage (calculator, browser, mail...)
        return [0x03, code & 0xFF, (code >> 8) & 0xFF, 0x00]
    if kind == "shortcut":  # code = (modifier mask << 8) | usage
        return [0x02, (code >> 8) & 0xFF, code & 0xFF, 0x00]
    if kind == "mouse":  # code = (01 button mask | 03 wheel) << 8 | value
        return [0x01, (code >> 8) & 0xFF, code & 0xFF, 0x00]
    return [0x02, 0x00, code & 0xFF, 0x00]  # plain key


MACRO_BLOB_SIZE = 0xE00
MACRO_INDEX_SLOTS = 100
MACRO_EVENT_TYPES = {"delay": 0x50, "down": 0xB0, "up": 0x30, "mdown": 0x90, "mup": 0x10}
AUTO_DELAY = [0x0A, 0x00, 0x00, 0x50]  # the driver's implicit 10 ms gap


def macro_event_bytes(event):
    kind = event["t"]
    if kind == "delay":
        ms = max(0, min(0xFFFF, int(event["ms"])))
        return [ms & 0xFF, ms >> 8, 0x00, 0x50]
    value = int(event.get("k", event.get("b", 0))) & 0xFF
    return [0x00, 0x00, value, MACRO_EVENT_TYPES[kind]]


def build_macro_blob(macros):
    """Index table (100 x 4 B, absolute LE offsets) then per macro: 8-byte header with the
    event count, 4-byte events, back to back. Returns (blob, packet count N)."""
    if len(macros) > MACRO_INDEX_SLOTS:
        raise RuntimeError(f"Toi da {MACRO_INDEX_SLOTS} macro")
    blob = bytearray(MACRO_BLOB_SIZE + 64)
    off = MACRO_INDEX_SLOTS * 4
    for i, macro in enumerate(macros):
        events = []
        for event in macro.get("events", []):
            if event["t"] != "delay" and events and events[-1][3] != 0x50:
                events.append(AUTO_DELAY)
            events.append(macro_event_bytes(event))
        if not events:
            blob[i * 4:i * 4 + 4] = b"\xff\xff\xff\xff"
            continue
        size = 8 + 4 * len(events)
        if off + size > MACRO_BLOB_SIZE - 128:
            raise RuntimeError("Tong do dai macro vuot bo nho ban phim")
        blob[i * 4:i * 4 + 2] = off.to_bytes(2, "little")
        blob[off:off + 2] = len(events).to_bytes(2, "little")
        for j, ev in enumerate(events):
            blob[off + 8 + j * 4:off + 12 + j * 4] = bytes(ev)
        off += size
    n = off // 64 + (2 if off % 64 else 1)  # one packet more than needed, like the driver
    blob[n * 64 - 2] = 0xAA
    blob[n * 64 - 1] = 0x55
    return blob, n


class ConfigError(RuntimeError):
    pass


def read_json_object(path):
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def load_user_config():
    # Never fall back to defaults on a bad file: the next remap would wipe the keyboard
    if not os.path.exists(USER_CONFIG_PATH):
        data = {}
    else:
        try:
            data = read_json_object(USER_CONFIG_PATH)
        except Exception:
            try:
                data = read_json_object(USER_CONFIG_PATH + ".bak")
            except Exception:
                raise ConfigError(f"File cau hinh bi hong: {USER_CONFIG_PATH}. Hay nhap lai ho so da xuat.")
    data.setdefault("keymap", {})
    data.setdefault("keyColors", {})
    data.setdefault("settings", dict(DEFAULT_SETTINGS))
    data.setdefault("macros", [])
    return data


def save_user_config(data):
    tmp = USER_CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if os.path.exists(USER_CONFIG_PATH):
        shutil.copy2(USER_CONFIG_PATH, USER_CONFIG_PATH + ".bak")
    os.replace(tmp, USER_CONFIG_PATH)


KEY_KINDS = {"key", "modifier", "media", "consumer", "shortcut", "mouse", "disable", "macro"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
SIT_REMINDER_MINUTES = (0, 30, 45, 60, 90)


def checked_int(value, lo, hi, what):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{what} khong hop le: {value!r}")
    return value


def validate_macros(macros):
    if not isinstance(macros, list) or len(macros) > MACRO_INDEX_SLOTS:
        raise ValueError("danh sach macro khong hop le")
    clean, ids = [], set()
    for m in macros:
        if not isinstance(m, dict):
            raise ValueError("macro khong hop le")
        mid = checked_int(m.get("id"), 1, 2 ** 53, "ma macro")
        if mid in ids:
            raise ValueError(f"ma macro bi trung: {mid}")
        ids.add(mid)
        events = m.get("events", [])
        if not isinstance(events, list) or len(events) > 800:
            raise ValueError("thao tac macro khong hop le")
        clean_events = []
        for ev in events:
            kind = ev.get("t") if isinstance(ev, dict) else None
            if kind == "delay":
                clean_events.append({"t": "delay", "ms": checked_int(ev.get("ms"), 0, 0xFFFF, "do tre")})
            elif kind in ("down", "up"):
                clean_events.append({"t": kind, "k": checked_int(ev.get("k"), 0, 0xFF, "ma phim")})
            elif kind in ("mdown", "mup"):
                clean_events.append({"t": kind, "b": checked_int(ev.get("b"), 0, 0xFF, "nut chuot")})
            else:
                raise ValueError(f"loai thao tac khong hop le: {kind!r}")
        clean.append({"id": mid, "name": str(m.get("name", ""))[:64], "events": clean_events})
    return clean


def validate_profile(profile):
    """Whitelist every field of an imported profile before anything touches disk or the keyboard."""
    if not isinstance(profile, dict):
        raise ValueError("file khong phai ho so cau hinh")
    out = {}
    if "keymap" in profile:
        if not isinstance(profile["keymap"], dict):
            raise ValueError("gan phim khong hop le")
        out["keymap"] = {}
        for slot, entry in profile["keymap"].items():
            if not str(slot).isdigit() or int(slot) >= REMAP_SLOTS:
                raise ValueError(f"vi tri phim khong hop le: {slot!r}")
            if not isinstance(entry, dict) or entry.get("kind") not in KEY_KINDS:
                raise ValueError(f"gan phim khong hop le o vi tri {slot}")
            clean = {"kind": entry["kind"], "code": checked_int(entry.get("code", 0), 0, 2 ** 53, "ma"),
                     "label": str(entry["label"])[:64] if entry.get("label") else None}
            if "mode" in entry:
                clean["mode"] = checked_int(entry["mode"], 0, 2, "cach chay macro")
            if "count" in entry:
                clean["count"] = checked_int(entry["count"], 0, 255, "so lan lap")
            out["keymap"][str(int(slot))] = clean
    if "keyColors" in profile:
        colors = profile["keyColors"]
        if not isinstance(colors, dict) or not all(
                str(k).isdigit() and isinstance(v, str) and HEX_COLOR.match(v) for k, v in colors.items()):
            raise ValueError("mau tung phim khong hop le")
        out["keyColors"] = {str(k): v for k, v in colors.items()}
    if "settings" in profile:
        settings = profile["settings"]
        if not isinstance(settings, dict):
            raise ValueError("cai dat khong hop le")
        # profiles saved before the 0-7 limit was known may hold up to 10
        out["settings"] = {k: checked_int(v, 0, 10, k) for k, v in settings.items() if k in DEFAULT_SETTINGS}
        if "ledBrightness" in out["settings"]:
            out["settings"]["ledBrightness"] = min(out["settings"]["ledBrightness"], MAX_LED_BRIGHTNESS)
    if "macros" in profile:
        out["macros"] = validate_macros(profile["macros"])
    if "tftSlot" in profile:
        out["tftSlot"] = checked_int(profile["tftSlot"], 1, 5, "o anh")
    if "sitReminder" in profile:
        if profile["sitReminder"] not in SIT_REMINDER_MINUTES:
            raise ValueError("nhac nho khong hop le")
        out["sitReminder"] = profile["sitReminder"]
    return out


def send_table(h, opcode, table, tag):
    """04 18 -> opcode with packet count -> 512 B in eight 64-byte reports -> 04 02 -> 04 F0."""
    if not ack_ok(send_cmd(h, [0x04, 0x18], tag)):
        raise RuntimeError("Ban phim khong vao che do cau hinh (04 18)")
    if not ack_ok(send_cmd(h, [0x04, opcode, 0, 0, 0, 0, 0, 0, 0x08], tag)):
        raise RuntimeError(f"Ban phim tu choi lenh {opcode:02x}")
    for i in range(8):
        h.write(bytes([0x00]) + bytes(table[i * 64:(i + 1) * 64]))
        h.read(64, timeout_ms=200)
    if not ack_ok(send_cmd(h, [0x04, 0x02], tag)):
        raise RuntimeError("Ban phim khong xac nhan luu (04 02)")
    send_cmd(h, [0x04, 0xF0], tag)


class ScreenInfoWorker(threading.Thread):
    """Re-sends the 04 28 packet so the TFT info page shows live CPU/GPU load."""

    INTERVAL = 2.0  # the Windows app refreshes CPU/GPU every 2 s

    def __init__(self, controller):
        super().__init__(daemon=True)
        self.controller = controller
        self.stop_event = threading.Event()
        self.prev_cpu = cpu_ticks()
        self.error = None

    def cpu_percent(self):
        now = cpu_ticks()
        if not now or not self.prev_cpu:
            return 0
        busy, idle = now[0] - self.prev_cpu[0], now[1] - self.prev_cpu[1]
        self.prev_cpu = now
        return round(100.0 * busy / (busy + idle)) if busy + idle else 0

    def run(self):
        while not self.stop_event.wait(self.INTERVAL):
            try:
                res = self.controller.sync_time(info={"cpu": self.cpu_percent(), "gpu": gpu_percent()})
                self.error = None if res.get("success") else res.get("error")
            except Exception as e:
                self.error = str(e)
            if self.error:
                print(f"[screen] info push failed: {self.error}")


class SitReminder(threading.Thread):
    """Nags on the LED matrix after `minutes` of continuous use; a 5-minute break resets the timer."""

    BREAK_SECONDS = 300
    SHOW_SECONDS = 6
    REPEAT_SECONDS = 300

    def __init__(self, controller, minutes):
        super().__init__(daemon=True)
        self.controller = controller
        self.minutes = minutes
        self.stop_event = threading.Event()
        self.active_since = time.time()
        self.last_nag = 0.0
        self.error = None

    def frame(self, lit):
        frame = blank_frame()
        if lit:
            draw_bar(frame, 100, (0, 4), "#ff9500")
            draw_text(frame, str(self.minutes), "#ff3b30", top=0)
        return frame

    def nag(self):
        subprocess.run(["osascript", "-e",
                        f'display notification "Bạn đã ngồi {self.minutes} phút, đứng dậy vận động chút nhé!" '
                        f'with title "LEOBOG AMG65"'], capture_output=True, timeout=5)
        self.controller.reminding = True
        try:
            end = time.time() + self.SHOW_SECONDS
            lit = True
            while time.time() < end and not self.stop_event.is_set():
                self.controller.led_matrix_preview(self.frame(lit))
                lit = not lit
                self.stop_event.wait(0.5)
        finally:
            self.controller.reminding = False

    def run(self):
        while not self.stop_event.wait(10):
            try:
                now = time.time()
                if idle_seconds() >= self.BREAK_SECONDS:
                    self.active_since = now
                    continue
                if now - self.active_since >= self.minutes * 60 and now - self.last_nag >= self.REPEAT_SECONDS:
                    self.last_nag = now
                    self.nag()
                self.error = None
            except Exception as e:
                self.error = str(e)
                print(f"[led] sit reminder failed: {e}")


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
        self.sit_reminder = None
        self.reminding = False
        self.screen_worker = None

    def set_screen_info(self, enabled):
        if self.screen_worker:
            self.screen_worker.stop_event.set()
            self.screen_worker = None
        if enabled:
            self.screen_worker = ScreenInfoWorker(self)
            self.screen_worker.start()
        cfg = load_user_config()
        cfg["tftSysInfo"] = bool(enabled)
        save_user_config(cfg)
        return {"success": True, "enabled": bool(enabled)}

    def select_tft_slot(self, slot):
        slot = max(1, min(5, int(slot)))
        res = self.sync_time(slot=slot)
        if res.get("success"):
            cfg = load_user_config()
            cfg["tftSlot"] = slot
            save_user_config(cfg)
        return res

    def set_sit_reminder(self, minutes):
        minutes = int(minutes or 0)
        if self.sit_reminder:
            self.sit_reminder.stop_event.set()
            self.sit_reminder = None
        if minutes > 0:
            self.sit_reminder = SitReminder(self, minutes)
            self.sit_reminder.start()
        cfg = load_user_config()
        cfg["sitReminder"] = minutes
        save_user_config(cfg)
        return {"success": True, "minutes": minutes}

    def import_profile(self, profile):
        """Validate an exported profile, push it to the keyboard, and save it only if every step worked."""
        try:
            clean = validate_profile(profile)
        except ValueError as e:
            return {"success": False, "error": f"Ho so khong hop le: {e}"}
        cfg = load_user_config()
        cfg.update(clean)

        steps = [("macro", self.upload_macros(cfg["macros"])),
                 ("gan phim", self.apply_keymap(cfg["keymap"], cfg["macros"])),
                 ("cai dat", self.apply_settings(cfg["settings"], save=False))]
        # an empty colour table is not sent: we do not know the keyboard's factory colours
        if cfg["keyColors"]:
            steps.append(("mau tung phim", self.apply_key_colors(cfg["keyColors"], save=False)))
        failed = [f"{name}: {res.get('error')}" for name, res in steps if not res.get("success")]
        if failed:
            return {"success": False, "error": "; ".join(failed)}

        save_user_config(cfg)
        self.set_sit_reminder(cfg.get("sitReminder", 0))
        if "tftSlot" in clean:
            self.select_tft_slot(clean["tftSlot"])
        return {"success": True}

    def factory_reset(self):
        """Keymap and settings back to defaults. Per-key colours are only cleared locally:
        the keyboard's factory colour table is unknown, so we do not overwrite it."""
        self.set_live_layer("off")
        for res in (self.apply_keymap({}), self.apply_settings(DEFAULT_SETTINGS, save=False)):
            if not res.get("success"):
                return res
        cfg = load_user_config()
        cfg.update({"keymap": {}, "keyColors": {}, "settings": dict(DEFAULT_SETTINGS)})
        cfg.pop("ledBrightnessPrev", None)
        save_user_config(cfg)
        return {"success": True}

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

    def get_status(self):
        # No battery read-back exists on the wired interface; the old 20 01 ping was a dongle packet
        if not self.find_device_path():
            return {"connected": False, "device": None, "battery": None, "charging": False}
        return {"connected": True, "device": "LEOBOG AMG65", "battery": None, "charging": False,
                "wired": True, "vid": "0x0C45", "pid": "0x800A", "workers": self.worker_status()}

    def worker_status(self):
        live, sit, screen = self.live_worker, self.sit_reminder, self.screen_worker
        return {
            "live": {"mode": live.mode, "error": live.error} if live else None,
            "sitReminder": {"minutes": sit.minutes, "error": sit.error} if sit else None,
            "tftSysInfo": {"error": screen.error} if screen else None,
        }

    def send_screen_info(self, h, slot, info=None):
        """Wired 04 28 packet: clock plus the values the TFT info pages show; [1] picks the image slot."""
        info = info or {}
        now = datetime.datetime.now()
        pkt = [0] * 64
        pkt[1] = slot
        pkt[2] = 0x5A
        pkt[3:9] = [now.year % 2000, now.month, now.day, now.hour, now.minute, now.second]
        pkt[10] = (now.weekday() + 1) % 7
        pkt[13] = max(0, min(100, int(info.get("cpu", 0))))
        pkt[15] = max(0, min(100, int(info.get("gpu", 0))))
        send_cmd(h, [0x04, 0x18], "screen")
        send_cmd(h, [0x04, 0x28, 0, 0, 0, 0, 0, 0, 0x01], "screen")
        pkt[62] = 0xAA
        pkt[63] = 0x55
        send_cmd(h, pkt, "screen")
        send_cmd(h, [0x04, 0x02], "screen")

    def sync_time(self, slot=None, info=None):
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            if slot is None:
                slot = load_user_config().get("tftSlot", 1)
            h.open_path(path)
            self.send_screen_info(h, slot, info)
            return {"success": True, "slot": slot}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

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

            return {"success": True, "mode": m, "brightness": br, "speed": sp}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def upload_lcd_image(self, data_url, slot=1):
        slot = max(1, min(5, int(slot)))
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

            # Select the uploaded slot for display (also sets the clock)
            self.send_screen_info(h, slot)
            cfg = load_user_config()
            cfg["tftSlot"] = slot
            save_user_config(cfg)

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

    def set_matrix_brightness(self, value):
        """The keyboard has no matrix off command, so off = 04 17 brightness 0."""
        value = max(0, min(MAX_LED_BRIGHTNESS, int(value)))
        cfg = load_user_config()
        current = int(cfg["settings"].get("ledBrightness", DEFAULT_SETTINGS["ledBrightness"]))
        if value == 0:
            self.set_live_layer("off")
            if current > 0:
                cfg["ledBrightnessPrev"] = current
                save_user_config(cfg)
        res = self.apply_settings({"ledBrightness": value})
        if res.get("success"):
            res["brightness"] = value
        return res

    def restore_matrix_brightness(self):
        cfg = load_user_config()
        return self.set_matrix_brightness(cfg.get("ledBrightnessPrev", DEFAULT_SETTINGS["ledBrightness"]))

    def led_matrix_from_image(self, data_url, max_frames=260, boost=False):
        """Downscale an image/GIF to 5x63 frames for the editor."""
        try:
            im = Image.open(io.BytesIO(decode_data_url(data_url)))
            frames, delays = [], []
            for frame in ImageSequence.Iterator(im):
                if len(frames) >= max_frames:
                    break
                small = ImageOps.fit(frame.convert("RGB"), (LED_COLS, LED_ROWS), method=Image.Resampling.BOX)
                if boost:
                    small = boost_led_frame(small)
                frames.append(["#%02x%02x%02x" % px for px in small.getdata()])
                delays.append(frame.info.get("duration", 100) or 100)
            return {"success": True, "frames": frames, "delays": delays}
        except Exception as e:
            return {"success": False, "error": f"Loi doc file anh: {str(e)}"}

    def apply_keymap(self, keymap, macros=None):
        """Send the whole 128-slot remap table; the keyboard cannot read it back, so we always send all of it."""
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}

        if macros is None:
            macros = load_user_config()["macros"]
        table = bytearray(512)
        for index, entry in keymap.items():
            slot = int(index)
            if slot >= REMAP_SLOTS:
                continue
            table[slot * 4:slot * 4 + 4] = bytes(
                remap_entry(entry.get("kind", "key"), entry.get("code", 0), entry, macros))
        table[510] = 0xAA
        table[511] = 0x55

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            send_table(h, 0x11, table, "remap")
            return {"success": True, "keys": len(keymap)}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def remap_key(self, key_index, kind, code, label=None, extra=None):
        try:
            key_index = checked_int(key_index, 0, REMAP_SLOTS - 1, "vi tri phim")
            code = checked_int(code, 0, 2 ** 53, "ma phim")
            if kind not in KEY_KINDS and kind != "default":
                raise ValueError(f"loai gan phim khong hop le: {kind!r}")
            if kind == "key" and code == 0:
                raise ValueError("ma phim rong")
        except ValueError as e:
            return {"success": False, "error": str(e)}
        cfg = load_user_config()
        if kind == "default":
            cfg["keymap"].pop(str(key_index), None)
        else:
            entry = {"kind": kind, "code": int(code), "label": label}
            entry.update({k: v for k, v in (extra or {}).items() if k in ("mode", "count")})
            cfg["keymap"][str(key_index)] = entry
        res = self.apply_keymap(cfg["keymap"])
        if res.get("success"):
            save_user_config(cfg)
        return res

    def upload_macros(self, macros):
        """04 19, 04 15 N, N+1 packets (the driver sends one spare), 04 02."""
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}
        try:
            blob, n = build_macro_blob(macros)
        except Exception as e:
            return {"success": False, "error": str(e)}

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            if not ack_ok(send_cmd(h, [0x04, 0x19], "macro")):
                raise RuntimeError("Ban phim khong vao che do ghi macro (04 19)")
            if not ack_ok(send_cmd(h, [0x04, 0x15, 0, 0, 0, 0, 0, 0, n], "macro")):
                raise RuntimeError("Ban phim tu choi du lieu macro (04 15)")
            time.sleep(0.03)
            for i in range(n + 1):
                h.write(bytes([0x00]) + bytes(blob[i * 64:(i + 1) * 64]))
                resp = h.read(64, timeout_ms=200)
                if i == 0 or i == n:
                    print(f"[macro] packet {i + 1}/{n + 1} -> {bytes(resp[:8]).hex(' ') if resp else 'no reply'}")
            time.sleep(0.03)
            if not ack_ok(send_cmd(h, [0x04, 0x02], "macro")):
                raise RuntimeError("Ban phim khong xac nhan luu macro (04 02)")
            return {"success": True, "packets": n}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def save_macros(self, macros):
        """Upload every macro, then re-send the keymap because deleting a macro shifts the
        indexes keys point at; bindings to deleted macros are dropped."""
        try:
            macros = validate_macros(macros)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        res = self.upload_macros(macros)
        if not res.get("success"):
            return res

        cfg = load_user_config()
        ids = {m["id"] for m in macros}
        keymap = {k: v for k, v in cfg["keymap"].items() if v.get("kind") != "macro" or v.get("code") in ids}
        res = self.apply_keymap(keymap, macros)
        if not res.get("success"):
            return res
        cfg["macros"] = macros
        cfg["keymap"] = keymap
        save_user_config(cfg)
        return {"success": True, "macros": len(macros)}

    def reset_keymap(self):
        cfg = load_user_config()
        cfg["keymap"] = {}
        res = self.apply_keymap({})
        if res.get("success"):
            save_user_config(cfg)
        return res

    def apply_key_colors(self, colors, save=True):
        """04 23 table: {light_index, R, G, B} at light_index*4."""
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}

        table = bytearray(512)
        for light_index in KEY_INDEXES:
            value = colors.get(str(light_index)) or colors.get(light_index) or "#000000"
            r, g, b = parse_rgb(value)
            table[light_index * 4:light_index * 4 + 4] = bytes((light_index, r, g, b))

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            send_table(h, 0x23, table, "keyrgb")
            if save:
                cfg = load_user_config()
                cfg["keyColors"] = {str(k): v for k, v in colors.items()}
                save_user_config(cfg)
            return {"success": True, "keys": len(KEY_INDEXES)}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def read_key_colors(self):
        """Read the per-key colours back with 04 F5 then eight 04 F6 pages."""
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            if not ack_ok(send_cmd(h, [0x04, 0xF5, 0, 0, 0, 0, 0, 0, 0x08], "keyrgb")):
                raise RuntimeError("Ban phim tu choi lenh doc mau (04 F5)")
            for _ in range(2):
                h.read(64, timeout_ms=1)

            data = bytearray()
            for page in range(8):
                h.write(bytes([0x00, 0x04, 0xF6, page, 0, 0, 0, 0, 0x08] + [0] * 56))
                time.sleep(0.006)
                resp = h.read(64, timeout_ms=360)
                if not resp or len(resp) != 64:
                    raise RuntimeError(f"Khong doc duoc trang mau {page + 1}/8")
                data.extend(resp)

            colors = {}
            for light_index in KEY_INDEXES:
                off = light_index * 4
                colors[str(light_index)] = "#%02x%02x%02x" % (data[off + 1], data[off + 2], data[off + 3])
            return {"success": True, "colors": colors}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()

    def apply_settings(self, settings, save=True):
        """04 17 keyboard settings packet."""
        path = self.find_device_path()
        if not path:
            return {"success": False, "error": "Ban phim chua duoc cam"}

        cfg = load_user_config()
        merged = dict(DEFAULT_SETTINGS)
        merged.update({k: int(v) for k, v in cfg["settings"].items() if k in DEFAULT_SETTINGS})
        merged.update({k: int(v) for k, v in settings.items() if k in DEFAULT_SETTINGS})

        pkt = [0] * 64
        pkt[1] = 1 if merged["gameMode"] else 0
        pkt[2] = 1 if merged["disableAltTab"] else 0
        pkt[3] = 1 if merged["disableAltF4"] else 0
        pkt[4] = 1 if merged["disableWin"] else 0
        pkt[5] = 1 if merged["fnToggle"] else 0
        pkt[6] = max(0, min(3, merged["sleepLight"]))
        pkt[7] = max(0, min(MAX_LED_BRIGHTNESS, merged["ledBrightness"]))
        pkt[62] = 0xAA
        pkt[63] = 0x55

        h = hid.device()
        DEVICE_LOCK.acquire()
        try:
            h.open_path(path)
            if not ack_ok(send_cmd(h, [0x04, 0x18], "settings")):
                raise RuntimeError("Ban phim khong vao che do cau hinh (04 18)")
            if not ack_ok(send_cmd(h, [0x04, 0x17, 0, 0, 0, 0, 0, 0, 0x01], "settings")):
                raise RuntimeError("Ban phim tu choi lenh cai dat (04 17)")
            send_cmd(h, pkt, "settings")
            if not ack_ok(send_cmd(h, [0x04, 0x02], "settings")):
                raise RuntimeError("Ban phim khong xac nhan luu cai dat (04 02)")
            if save:
                cfg["settings"] = merged
                save_user_config(cfg)
            return {"success": True, "settings": merged}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            try:
                h.close()
            finally:
                DEVICE_LOCK.release()


controller = KeyboardController()
try:
    _startup_cfg = load_user_config()
    if _startup_cfg.get("sitReminder"):
        controller.set_sit_reminder(_startup_cfg["sitReminder"])
    if _startup_cfg.get("tftSysInfo"):
        controller.set_screen_info(True)
except ConfigError as e:
    print(f"[config] {e}")

class AppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    # No CORS headers: other sites must not be able to drive the keyboard through the user's browser
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        # DNS rebinding: a foreign hostname resolving to 127.0.0.1 still sends its own Host
        return (self.headers.get("Host") or "").lower() in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def token_ok(self):
        return hmac.compare_digest(self.headers.get("X-AMG65-Token", ""), API_TOKEN)

    def serve_index(self):
        with open(os.path.join(DIRECTORY, "index.html"), encoding="utf-8") as f:
            page = f.read().replace("<head>", f'<head>\n  <meta name="api-token" content="{API_TOKEN}">', 1)
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def guarded(self, handler):
        if not self.host_ok():
            return self.send_json(403, {"success": False, "error": "Forbidden host"})
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self.serve_index()
        if path.startswith("/api/") and not self.token_ok():
            return self.send_json(403, {"success": False, "error": "Forbidden"})
        try:
            return handler()
        except Exception as e:
            print(f"[http] {self.command} {self.path} failed: {e}")
            return self.send_json(500, {"success": False, "error": str(e)})

    def do_GET(self):
        return self.guarded(self.handle_get)

    def do_POST(self):
        return self.guarded(self.handle_post)

    def handle_get(self):
        if self.path == "/api/status":
            status = controller.get_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode("utf-8"))
            return
        elif self.path == "/api/user-config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, **load_user_config()}).encode("utf-8"))
            return
        elif self.path == "/api/key-colors":
            res = controller.read_key_colors()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        return super().do_GET()

    def handle_post(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        required = {"/api/remap": ("keyIndex", "kind", "code"), "/api/macros": ("macros",),
                    "/api/key-colors": ("colors",), "/api/profile/import": ("profile",),
                    "/api/led-matrix/upload": ("frames",), "/api/led-matrix/preview": ("pixels",)}
        missing = [k for k in required.get(self.path, ()) if k not in data]
        if missing:
            return self.send_json(400, {"success": False, "error": "Thieu truong: " + ", ".join(missing)})

        if self.path == "/api/sync-time":
            res = controller.select_tft_slot(data["slot"]) if data.get("slot") else controller.sync_time()
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
            res = controller.upload_lcd_image(image_data, data.get("slot", 1))
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
        elif self.path == "/api/led-matrix/brightness":
            if data.get("restore"):
                res = controller.restore_matrix_brightness()
            else:
                res = controller.set_matrix_brightness(data.get("value", 0))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/led-matrix/import":
            res = controller.led_matrix_from_image(data.get("image", ""), boost=bool(data.get("boost")))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path in ("/api/sit-reminder", "/api/profile/import", "/api/factory-reset", "/api/tft/sysinfo",
                           "/api/macros"):
            if self.path == "/api/macros":
                res = controller.save_macros(data["macros"])
            elif self.path == "/api/tft/sysinfo":
                res = controller.set_screen_info(data.get("enabled", False))
            elif self.path == "/api/sit-reminder":
                res = controller.set_sit_reminder(data.get("minutes", 0))
            elif self.path == "/api/profile/import":
                res = controller.import_profile(data.get("profile", {}))
            else:
                res = controller.factory_reset()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/remap/reset":
            res = controller.reset_keymap()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/key-colors":
            res = controller.apply_key_colors(data["colors"])
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/settings":
            res = controller.apply_settings(data.get("settings", {}))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return
        elif self.path == "/api/remap":
            res = controller.remap_key(data["keyIndex"], data["kind"], data["code"], data.get("label"), data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

httpd = None


def shutdown():
    for worker in (controller.live_worker, controller.sit_reminder, controller.screen_worker):
        if worker:
            worker.stop_event.set()
    controller.live_worker = controller.sit_reminder = controller.screen_worker = None
    if httpd:
        httpd.shutdown()


def main():
    global httpd
    os.chdir(DIRECTORY)
    socketserver.TCPServer.allow_reuse_address = True
    # bind to loopback only: this server can reprogram the keyboard
    with socketserver.TCPServer(("127.0.0.1", PORT), AppHandler) as httpd:
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
