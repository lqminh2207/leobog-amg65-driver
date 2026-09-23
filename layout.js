// LEOBOG AMG65 Layout & Key Code Definitions
// Extracted and Reverse-Engineered from AMG65 Driver 1.0.3.1

export const KEYBOARD_WIDTH = 1000;
export const KEYBOARD_HEIGHT = 400;

export const KEYBOARD_KEYS = [
  // Row 0 - Numbers & Top Row
  { code: "0x29", name: "Esc", desc: "Esc", key_index: 0, light_index: 0, row_col: "0#0", x: 39, y: 122, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x1e", name: "1", desc: "!1", key_index: 17, light_index: 17, row_col: "0#1", x: 89, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F1" },
  { code: "0x1f", name: "2", desc: "@2", key_index: 18, light_index: 18, row_col: "0#2", x: 139, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F2" },
  { code: "0x20", name: "3", desc: "#3", key_index: 19, light_index: 19, row_col: "0#3", x: 189, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F3" },
  { code: "0x21", name: "4", desc: "$4", key_index: 20, light_index: 20, row_col: "0#4", x: 239, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F4" },
  { code: "0x22", name: "5", desc: "%5", key_index: 21, light_index: 21, row_col: "0#5", x: 289, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F5" },
  { code: "0x23", name: "6", desc: "^6", key_index: 22, light_index: 22, row_col: "0#6", x: 339, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F6" },
  { code: "0x24", name: "7", desc: "&7", key_index: 23, light_index: 23, row_col: "0#7", x: 389, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F7" },
  { code: "0x25", name: "8", desc: "*8", key_index: 24, light_index: 24, row_col: "0#8", x: 439, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F8" },
  { code: "0x26", name: "9", desc: "(9", key_index: 25, light_index: 25, row_col: "0#9", x: 489, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F9" },
  { code: "0x27", name: "0", desc: ")0", key_index: 26, light_index: 26, row_col: "0#10", x: 539, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F10" },
  { code: "0x2d", name: "-", desc: "_-", key_index: 27, light_index: 27, row_col: "0#11", x: 589, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F11" },
  { code: "0x2e", name: "=", desc: "+=", key_index: 28, light_index: 28, row_col: "0#12", x: 639, y: 122, w: 34, h: 32, fnlayer_disable: 0, fn: "F12" },
  { code: "0x2a", name: "Backspace", desc: "Backspace", key_index: 92, light_index: 92, row_col: "0#13", x: 689, y: 122, w: 83, h: 32, fnlayer_disable: 0 },
  { code: "0x4a", name: "Home", desc: "Home", key_index: 104, light_index: 104, row_col: "0#15", x: 788, y: 122, w: 34, h: 32, fnlayer_disable: 0 },

  // Knob Controls
  { code: "0xE9", name: "Knob CW", desc: "Volume +", key_index: 13, light_index: 13, row_col: "0#16", x: 916, y: 22, w: 46, h: 28, fnlayer_disable: 0, is_knob: true },
  { code: "0xEA", name: "Knob CCW", desc: "Volume -", key_index: 14, light_index: 14, row_col: "0#17", x: 916, y: 56, w: 46, h: 28, fnlayer_disable: 0, is_knob: true },

  // Row 1 - QWERTY
  { code: "0x2b", name: "Tab", desc: "Tab", key_index: 32, light_index: 32, row_col: "1#0", x: 39, y: 171, w: 62, h: 32, fnlayer_disable: 0 },
  { code: "0x14", name: "Q", desc: "Q", key_index: 33, light_index: 33, row_col: "1#1", x: 115, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x1a", name: "W", desc: "W", key_index: 34, light_index: 34, row_col: "1#2", x: 165, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x08", name: "E", desc: "E", key_index: 35, light_index: 35, row_col: "1#3", x: 215, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x15", name: "R", desc: "R", key_index: 36, light_index: 36, row_col: "1#4", x: 265, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x17", name: "T", desc: "T", key_index: 37, light_index: 37, row_col: "1#5", x: 315, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x1c", name: "Y", desc: "Y", key_index: 38, light_index: 38, row_col: "1#6", x: 365, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x18", name: "U", desc: "U", key_index: 39, light_index: 39, row_col: "1#7", x: 415, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x0c", name: "I", desc: "I", key_index: 40, light_index: 40, row_col: "1#8", x: 465, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x12", name: "O", desc: "O", key_index: 41, light_index: 41, row_col: "1#9", x: 515, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x13", name: "P", desc: "P", key_index: 42, light_index: 42, row_col: "1#10", x: 565, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x2f", name: "[", desc: "{[", key_index: 43, light_index: 43, row_col: "1#11", x: 614, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x30", name: "]", desc: "}}", key_index: 44, light_index: 44, row_col: "1#12", x: 664, y: 171, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x31", name: "\\", desc: "|\\", key_index: 60, light_index: 60, row_col: "1#13", x: 714, y: 171, w: 58, h: 32, fnlayer_disable: 0 },
  { code: "0x4c", name: "Del", desc: "Delete", key_index: 106, light_index: 106, row_col: "1#15", x: 788, y: 171, w: 34, h: 32, fnlayer_disable: 0 },

  // Row 2 - ASDF
  { code: "0x39", name: "Caps", desc: "CapsLock", key_index: 48, light_index: 48, row_col: "2#0", x: 39, y: 220, w: 74, h: 32, fnlayer_disable: 0 },
  { code: "0x04", name: "A", desc: "A", key_index: 49, light_index: 49, row_col: "2#1", x: 127, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x16", name: "S", desc: "S", key_index: 50, light_index: 50, row_col: "2#2", x: 177, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x07", name: "D", desc: "D", key_index: 51, light_index: 51, row_col: "2#3", x: 227, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x09", name: "F", desc: "F", key_index: 52, light_index: 52, row_col: "2#4", x: 277, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x0a", name: "G", desc: "G", key_index: 53, light_index: 53, row_col: "2#5", x: 327, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x0b", name: "H", desc: "H", key_index: 54, light_index: 54, row_col: "2#6", x: 377, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x0d", name: "J", desc: "J", key_index: 55, light_index: 55, row_col: "2#7", x: 427, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x0e", name: "K", desc: "K", key_index: 56, light_index: 56, row_col: "2#8", x: 477, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x0f", name: "L", desc: "L", key_index: 57, light_index: 57, row_col: "2#9", x: 527, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x33", name: ";", desc: ":;", key_index: 58, light_index: 58, row_col: "2#10", x: 576, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x34", name: "'", desc: "\"'", key_index: 59, light_index: 59, row_col: "2#11", x: 626, y: 220, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x28", name: "Enter", desc: "Enter", key_index: 76, light_index: 76, row_col: "2#13", x: 675, y: 220, w: 97, h: 32, fnlayer_disable: 0 },
  { code: "0x4b", name: "PgUp", desc: "Page Up", key_index: 105, light_index: 105, row_col: "2#15", x: 788, y: 220, w: 34, h: 32, fnlayer_disable: 0 },

  // Row 3 - ZXCV
  { code: "0xe1", name: "Shift L", desc: "Shift_L", key_index: 64, light_index: 64, row_col: "3#0", x: 39, y: 269, w: 100, h: 32, fnlayer_disable: 0 },
  { code: "0x1d", name: "Z", desc: "Z", key_index: 65, light_index: 65, row_col: "3#2", x: 152, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x1b", name: "X", desc: "X", key_index: 66, light_index: 66, row_col: "3#3", x: 202, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x06", name: "C", desc: "C", key_index: 67, light_index: 67, row_col: "3#4", x: 252, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x19", name: "V", desc: "V", key_index: 68, light_index: 68, row_col: "3#5", x: 302, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x05", name: "B", desc: "B", key_index: 69, light_index: 69, row_col: "3#6", x: 352, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x11", name: "N", desc: "N", key_index: 70, light_index: 70, row_col: "3#7", x: 402, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x10", name: "M", desc: "M", key_index: 71, light_index: 71, row_col: "3#8", x: 452, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x36", name: ",", desc: "<,", key_index: 72, light_index: 72, row_col: "3#9", x: 502, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x37", name: ".", desc: ">.", key_index: 73, light_index: 73, row_col: "3#10", x: 552, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x38", name: "/", desc: "?/", key_index: 74, light_index: 74, row_col: "3#11", x: 601, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0xe5", name: "Shift R", desc: "Shift_R", key_index: 75, light_index: 75, row_col: "3#13", x: 651, y: 269, w: 72, h: 32, fnlayer_disable: 0 },
  { code: "0x52", name: "↑", desc: "Up", key_index: 90, light_index: 90, row_col: "3#14", x: 738, y: 269, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x4e", name: "PgDn", desc: "Page Down", key_index: 108, light_index: 108, row_col: "3#15", x: 788, y: 269, w: 34, h: 32, fnlayer_disable: 0 },

  // Row 4 - Bottom Modifiers
  { code: "0xe0", name: "Ctrl L", desc: "Ctrl_L", key_index: 80, light_index: 80, row_col: "5#0", x: 39, y: 320, w: 48, h: 32, fnlayer_disable: 0 },
  { code: "0xe3", name: "Win / Cmd", desc: "Win_L", key_index: 81, light_index: 81, row_col: "5#1", x: 103, y: 320, w: 48, h: 32, fnlayer_disable: 0 },
  { code: "0xe2", name: "Alt / Opt", desc: "Alt_L", key_index: 82, light_index: 82, row_col: "5#2", x: 166, y: 320, w: 48, h: 32, fnlayer_disable: 0 },
  { code: "0x2c", name: "Space", desc: "Space", key_index: 83, light_index: 83, row_col: "5#6", x: 227, y: 320, w: 296, h: 32, fnlayer_disable: 0 },
  { code: "0xAF", name: "Fn", desc: "Fn", key_index: 85, light_index: 85, row_col: "5#12", x: 539, y: 320, w: 48, h: 32, fnlayer_disable: 1 },
  { code: "0xE4", name: "Ctrl R", desc: "Ctrl_R", key_index: 87, light_index: 87, row_col: "5#11", x: 601, y: 320, w: 48, h: 32, fnlayer_disable: 0 },
  { code: "0x50", name: "←", desc: "Left", key_index: 88, light_index: 88, row_col: "5#13", x: 688, y: 320, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x51", name: "↓", desc: "Down", key_index: 89, light_index: 89, row_col: "5#14", x: 738, y: 320, w: 34, h: 32, fnlayer_disable: 0 },
  { code: "0x4f", name: "→", desc: "Right", key_index: 91, light_index: 91, row_col: "5#15", x: 788, y: 320, w: 34, h: 32, fnlayer_disable: 0 }
];

export const LIGHT_MODES = [
  { id: 5, name: "Sóng RGB (Colourful Wave)", desc: "Dải sóng RGB đa sắc lượn qua các phím", supportsColor: false },
  { id: 6, name: "Thở Nhịp Điệu (Breath)", desc: "Hiệu ứng thở đổi màu hoặc đơn sắc", supportsColor: true },
  { id: 7, name: "Phổ Quang (Spectrum)", desc: "Đổi màu liên tục toàn bộ bàn phím", supportsColor: false },
  { id: 3, name: "Lấp Lánh (Glittering)", desc: "Ánh sáng sao nhấp nháy ngẫu nhiên", supportsColor: true },
  { id: 4, name: "Mưa Rơi (Falling)", desc: "Dải sáng rơi xuống từ trên cao", supportsColor: true },
  { id: 8, name: "Lan Tỏa (Outward)", desc: "Lan tỏa ánh sáng từ phím khi nhấn", supportsColor: true },
  { id: 9, name: "Cuộn Sóng (Scrolling)", desc: "Dải sóng ánh sáng cuộn ngang phím", supportsColor: true },
  { id: 10, name: "Xoay Vòng (Rolling)", desc: "Ánh sáng xoay quanh tâm bàn phím", supportsColor: true },
  { id: 11, name: "Chong Chóng (Rotating)", desc: "Quay tròn như cánh quạt chong chóng", supportsColor: true },
  { id: 12, name: "Phát Nổ (Explode)", desc: "Bùng nổ ánh sáng tại phím vừa gõ", supportsColor: true },
  { id: 13, name: "Tia Sáng (Launch)", desc: "Tia laser bắn sang hai bên khi bấm", supportsColor: true },
  { id: 14, name: "Gợn Sóng (Ripples)", desc: "Gợn sóng nước lan tròn từ phím bấm", supportsColor: true },
  { id: 15, name: "Dòng Chảy (Flowing)", desc: "Dòng ánh sáng chảy mượt mà", supportsColor: true },
  { id: 16, name: "Nhịp Tim (Pulsating)", desc: "Xung ánh sáng đập theo nhịp tim", supportsColor: true },
  { id: 17, name: "Nghiêng Chéo (Tilt)", desc: "Ánh sáng chạy theo góc nghiêng chéo", supportsColor: true },
  { id: 18, name: "Con Thoi (Shuttle)", desc: "Dải sáng con thoi chạy qua lại", supportsColor: true },
  { id: 19, name: "Tắt LED (Close Backlight)", desc: "Tắt hoàn toàn đèn nền", supportsColor: false },
  { id: 0, name: "Tự Chọn 1 (Custom Profile 1)", desc: "Cấu hình tuỳ chỉnh người dùng 1", supportsColor: true },
  { id: 1, name: "Tự Chọn 2 (Custom Profile 2)", desc: "Cấu hình tuỳ chỉnh người dùng 2", supportsColor: true },
  { id: 2, name: "Tự Chọn 3 (Custom Profile 3)", desc: "Cấu hình tuỳ chỉnh người dùng 3", supportsColor: true }
];

export const KEY_REMAP_CATEGORIES = [
  {
    name: "Chữ cái (Letters)",
    keys: [
      { kind: "key", code: 0x04, name: "A" }, { kind: "key", code: 0x05, name: "B" }, { kind: "key", code: 0x06, name: "C" }, { kind: "key", code: 0x07, name: "D" },
      { kind: "key", code: 0x08, name: "E" }, { kind: "key", code: 0x09, name: "F" }, { kind: "key", code: 0x0A, name: "G" }, { kind: "key", code: 0x0B, name: "H" },
      { kind: "key", code: 0x0C, name: "I" }, { kind: "key", code: 0x0D, name: "J" }, { kind: "key", code: 0x0E, name: "K" }, { kind: "key", code: 0x0F, name: "L" },
      { kind: "key", code: 0x10, name: "M" }, { kind: "key", code: 0x11, name: "N" }, { kind: "key", code: 0x12, name: "O" }, { kind: "key", code: 0x13, name: "P" },
      { kind: "key", code: 0x14, name: "Q" }, { kind: "key", code: 0x15, name: "R" }, { kind: "key", code: 0x16, name: "S" }, { kind: "key", code: 0x17, name: "T" },
      { kind: "key", code: 0x18, name: "U" }, { kind: "key", code: 0x19, name: "V" }, { kind: "key", code: 0x1A, name: "W" }, { kind: "key", code: 0x1B, name: "X" },
      { kind: "key", code: 0x1C, name: "Y" }, { kind: "key", code: 0x1D, name: "Z" }
    ]
  },
  {
    name: "Số & Ký tự (Numbers)",
    keys: [
      { kind: "key", code: 0x1E, name: "1 !" }, { kind: "key", code: 0x1F, name: "2 @" }, { kind: "key", code: 0x20, name: "3 #" }, { kind: "key", code: 0x21, name: "4 $" },
      { kind: "key", code: 0x22, name: "5 %" }, { kind: "key", code: 0x23, name: "6 ^" }, { kind: "key", code: 0x24, name: "7 &" }, { kind: "key", code: 0x25, name: "8 *" },
      { kind: "key", code: 0x26, name: "9 (" }, { kind: "key", code: 0x27, name: "0 )" }, { kind: "key", code: 0x2D, name: "- _" }, { kind: "key", code: 0x2E, name: "= +" },
      { kind: "key", code: 0x2F, name: "[ {" }, { kind: "key", code: 0x30, name: "] }" }, { kind: "key", code: 0x31, name: "\\ |" }, { kind: "key", code: 0x33, name: "; :" },
      { kind: "key", code: 0x34, name: "' \"" }, { kind: "key", code: 0x35, name: "` ~" }, { kind: "key", code: 0x36, name: ", <" }, { kind: "key", code: 0x37, name: ". >" },
      { kind: "key", code: 0x38, name: "/ ?" }
    ]
  },
  {
    name: "Phím chức năng (F1 - F12)",
    keys: [
      { kind: "key", code: 0x3A, name: "F1" }, { kind: "key", code: 0x3B, name: "F2" }, { kind: "key", code: 0x3C, name: "F3" }, { kind: "key", code: 0x3D, name: "F4" },
      { kind: "key", code: 0x3E, name: "F5" }, { kind: "key", code: 0x3F, name: "F6" }, { kind: "key", code: 0x40, name: "F7" }, { kind: "key", code: 0x41, name: "F8" },
      { kind: "key", code: 0x42, name: "F9" }, { kind: "key", code: 0x43, name: "F10" }, { kind: "key", code: 0x44, name: "F11" }, { kind: "key", code: 0x45, name: "F12" }
    ]
  },
  {
    name: "Điều hướng & Soạn thảo (Control)",
    keys: [
      { kind: "key", code: 0x29, name: "Esc" }, { kind: "key", code: 0x28, name: "Enter" }, { kind: "key", code: 0x2A, name: "Backspace" },
      { kind: "key", code: 0x2B, name: "Tab" }, { kind: "key", code: 0x2C, name: "Space" }, { kind: "key", code: 0x39, name: "Caps Lock" },
      { kind: "key", code: 0x4C, name: "Delete" }, { kind: "key", code: 0x4A, name: "Home" }, { kind: "key", code: 0x4D, name: "End" },
      { kind: "key", code: 0x4B, name: "Page Up" }, { kind: "key", code: 0x4E, name: "Page Down" }, { kind: "key", code: 0x49, name: "Insert" },
      { kind: "key", code: 0x52, name: "Mũi tên Lên (↑)" }, { kind: "key", code: 0x51, name: "Mũi tên Xuống (↓)" },
      { kind: "key", code: 0x50, name: "Mũi tên Trái (←)" }, { kind: "key", code: 0x4F, name: "Mũi tên Phải (→)" }
    ]
  },
  {
    name: "Phím bổ trợ (Modifiers)",
    keys: [
      { kind: "modifier", code: 0xE0, name: "Left Ctrl" }, { kind: "modifier", code: 0xE1, name: "Left Shift" }, { kind: "modifier", code: 0xE2, name: "Left Alt / Option" },
      { kind: "modifier", code: 0xE3, name: "Left Command / Win" }, { kind: "modifier", code: 0xE4, name: "Right Ctrl" }, { kind: "modifier", code: 0xE5, name: "Right Shift" },
      { kind: "modifier", code: 0xE6, name: "Right Alt / Option" }, { kind: "modifier", code: 0xE7, name: "Right Command / Win" }
    ]
  },
  {
    name: "Đa phương tiện (Media & Audio)",
    keys: [
      { kind: "media", code: 0xE9, name: "Tăng âm lượng (Vol +)" },
      { kind: "media", code: 0xEA, name: "Giảm âm lượng (Vol -)" },
      { kind: "media", code: 0xE2, name: "Tắt tiếng (Mute)" },
      { kind: "media", code: 0xCD, name: "Phát / Dừng (Play/Pause)" },
      { kind: "media", code: 0xB5, name: "Bài tiếp (Next Track)" },
      { kind: "media", code: 0xB6, name: "Bài trước (Prev Track)" },
      { kind: "media", code: 0xB7, name: "Dừng phát (Stop)" }
    ]
  },
  {
    name: "Khôi phục",
    keys: [
      { kind: "default", code: 0x00, name: "Trả về chức năng gốc" }
    ]
  },
  {
    name: "Tiện ích & Ứng dụng (Shortcuts)",
    keys: [
      { kind: "consumer", code: 0x192, name: "Máy tính (Calculator)" },
      { kind: "consumer", code: 0x194, name: "Trình duyệt (Browser)" },
      { kind: "consumer", code: 0x18A, name: "Thư điện tử (Email)" },
      { kind: "disable", code: 0x00, name: "Vô hiệu hóa phím (Disabled)" }
    ]
  }
];
