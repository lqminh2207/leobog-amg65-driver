// Macro recorder / editor. Events: {t:"down"|"up", k:usage} {t:"delay", ms} {t:"mdown"|"mup", b:mask}
import { KEYBOARD_KEYS } from "./layout.js";

const MAX_RECORDED_GAP = 31000; // the Windows recorder caps real gaps at this
const MOUSE_BUTTONS = { 1: "Chuột trái", 2: "Chuột phải", 4: "Chuột giữa" };

// KeyboardEvent.code -> HID usage
const CODE_TO_USAGE = {
  Enter: 0x28, Escape: 0x29, Backspace: 0x2a, Tab: 0x2b, Space: 0x2c, Minus: 0x2d, Equal: 0x2e,
  BracketLeft: 0x2f, BracketRight: 0x30, Backslash: 0x31, Semicolon: 0x33, Quote: 0x34, Backquote: 0x35,
  Comma: 0x36, Period: 0x37, Slash: 0x38, CapsLock: 0x39, PrintScreen: 0x46, ScrollLock: 0x47, Pause: 0x48,
  Insert: 0x49, Home: 0x4a, PageUp: 0x4b, Delete: 0x4c, End: 0x4d, PageDown: 0x4e,
  ArrowRight: 0x4f, ArrowLeft: 0x50, ArrowDown: 0x51, ArrowUp: 0x52,
  ControlLeft: 0xe0, ShiftLeft: 0xe1, AltLeft: 0xe2, MetaLeft: 0xe3,
  ControlRight: 0xe4, ShiftRight: 0xe5, AltRight: 0xe6, MetaRight: 0xe7
};
for (let i = 0; i < 26; i++) CODE_TO_USAGE[`Key${String.fromCharCode(65 + i)}`] = 0x04 + i;
for (let i = 1; i <= 9; i++) CODE_TO_USAGE[`Digit${i}`] = 0x1d + i;
CODE_TO_USAGE.Digit0 = 0x27;
for (let i = 1; i <= 12; i++) CODE_TO_USAGE[`F${i}`] = 0x39 + i;

const USAGE_NAMES = {
  0xe0: "Ctrl", 0xe1: "Shift", 0xe2: "Option", 0xe3: "⌘ Cmd", 0xe4: "Ctrl phải", 0xe5: "Shift phải",
  0xe6: "Option phải", 0xe7: "⌘ Cmd phải", 0x28: "Enter", 0x29: "Esc", 0x2a: "Backspace", 0x2b: "Tab", 0x2c: "Space",
  0x4f: "→", 0x50: "←", 0x51: "↓", 0x52: "↑"
};
const usageName = usage => {
  if (USAGE_NAMES[usage]) return USAGE_NAMES[usage];
  const code = Object.keys(CODE_TO_USAGE).find(c => CODE_TO_USAGE[c] === usage);
  return code ? code.replace(/^Key|^Digit/, "") : `0x${usage.toString(16)}`;
};

export class MacroEditor {
  constructor(app) {
    this.app = app;
    this.driver = app.driver;
    this.macros = [];
    this.current = -1;
    this.recording = false;
    this.lastEventAt = 0;
    this.held = new Set();
    this.$ = id => document.getElementById(id);

    this.onKey = this.onKey.bind(this);
    this.initKeySelect();
    this.attachEvents();
    this.render();
  }

  get macro() {
    return this.macros[this.current];
  }

  setMacros(macros) {
    this.macros = macros || [];
    this.current = this.macros.length ? 0 : -1;
    this.render();
  }

  initKeySelect() {
    const select = this.$("macroTargetKey");
    KEYBOARD_KEYS.forEach(k => {
      const opt = document.createElement("option");
      opt.value = k.key_index;
      opt.textContent = k.is_knob ? `Núm xoay: ${k.desc}` : k.name;
      select.appendChild(opt);
    });
  }

  attachEvents() {
    const $ = this.$;
    $("macroList").addEventListener("change", e => {
      this.stopRecording();
      this.current = Number(e.target.value);
      this.render();
    });
    $("btnMacroNew").addEventListener("click", () => {
      const name = prompt("Tên macro:", `Macro ${this.macros.length + 1}`);
      if (!name) return;
      this.stopRecording();
      const id = Math.max(Date.now(), this.macros.reduce((max, m) => Math.max(max, m.id), 0) + 1);
      this.macros.push({ id, name, events: [] });
      this.current = this.macros.length - 1;
      this.render();
    });
    $("btnMacroRename").addEventListener("click", () => {
      this.stopRecording();
      if (!this.macro) return;
      const name = prompt("Tên mới:", this.macro.name);
      if (name) {
        this.macro.name = name;
        this.render();
      }
    });
    $("btnMacroDelete").addEventListener("click", () => {
      this.stopRecording();
      if (!this.macro || !confirm(`Xoá macro "${this.macro.name}"? Phím đang gán macro này sẽ bị gỡ khi lưu.`)) return;
      this.macros.splice(this.current, 1);
      this.current = Math.min(this.current, this.macros.length - 1);
      this.render();
    });

    $("btnMacroRecord").addEventListener("click", () => (this.recording ? this.stopRecording() : this.startRecording()));
    $("btnMacroClear").addEventListener("click", () => {
      if (!this.macro) return;
      this.macro.events = [];
      this.render();
    });
    $("btnMacroAddDelay").addEventListener("click", () => {
      if (!this.macro) return;
      this.macro.events.push({ t: "delay", ms: Math.max(1, Number($("macroDelayMs").value) || 10) });
      this.render();
    });
    $("btnMacroAddMouse").addEventListener("click", () => {
      if (!this.macro) return;
      const b = Number($("macroMouseButton").value);
      this.macro.events.push({ t: "mdown", b }, { t: "delay", ms: 20 }, { t: "mup", b });
      this.render();
    });
    $("macroEvents").addEventListener("click", e => {
      const btn = e.target.closest("[data-remove]");
      if (!btn || !this.macro) return;
      this.macro.events.splice(Number(btn.dataset.remove), 1);
      this.render();
    });

    $("macroPlayMode").addEventListener("change", e => {
      $("macroPlayCount").style.display = e.target.value === "1" ? "" : "none";
    });

    $("btnMacroSave").addEventListener("click", () => this.run($("btnMacroSave"), async () => {
      this.stopRecording();
      const res = await this.driver.saveMacros(this.macros);
      this.app.keyRemapCache = {};
      await this.app.loadUserConfig();
      return `Đã lưu ${res.macros} macro vào bàn phím.`;
    }));
    $("btnMacroAssign").addEventListener("click", () => this.run($("btnMacroAssign"), async () => {
      if (!this.macro) throw new Error("Chưa chọn macro");
      const keyIndex = Number($("macroTargetKey").value);
      const mode = Number($("macroPlayMode").value);
      const count = Number($("macroPlayCount").value) || 1;
      const label = `Macro: ${this.macro.name}`;
      // the keymap entry points at the macro's position on the keyboard, so upload the macros first
      this.stopRecording();
      await this.driver.saveMacros(this.macros);
      await this.driver.remapKey(keyIndex, "macro", this.macro.id, label, { mode, count });
      this.app.keyRemapCache[keyIndex] = label;
      this.app.updateKeyboardDisplay();
      const keyName = $("macroTargetKey").options[$("macroTargetKey").selectedIndex].text;
      return `Đã lưu macro và gán "${this.macro.name}" cho phím ${keyName}.`;
    }));
  }

  async run(button, task) {
    button.disabled = true;
    try {
      const message = await task();
      this.$("macroStatus").textContent = message;
      this.app.showToast(message, "success");
    } catch (err) {
      this.$("macroStatus").textContent = "Lỗi: " + err.message;
      this.app.showToast("Lỗi: " + err.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  startRecording() {
    if (!this.macro) {
      this.app.showToast("Tạo macro trước khi ghi.", "info");
      return;
    }
    this.recording = true;
    this.lastEventAt = 0;
    this.held.clear();
    window.addEventListener("keydown", this.onKey, true);
    window.addEventListener("keyup", this.onKey, true);
    this.render();
  }

  stopRecording() {
    if (!this.recording) return;
    // keys still down when recording ends would stay stuck on playback
    if (this.macro) this.held.forEach(k => this.macro.events.push({ t: "up", k }));
    this.held.clear();
    this.recording = false;
    window.removeEventListener("keydown", this.onKey, true);
    window.removeEventListener("keyup", this.onKey, true);
    this.render();
  }

  pushWithDelay(event) {
    const now = performance.now();
    const mode = this.$("macroDelayMode").value;
    if (this.lastEventAt && mode !== "none") {
      const ms = mode === "real"
        ? Math.min(MAX_RECORDED_GAP, Math.max(1, Math.round(now - this.lastEventAt)))
        : Math.max(1, Number(this.$("macroDelayMs").value) || 10);
      this.macro.events.push({ t: "delay", ms });
    }
    this.lastEventAt = now;
    this.macro.events.push(event);
  }

  onKey(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!this.macro) return this.stopRecording();
    if (e.repeat) return;
    const usage = CODE_TO_USAGE[e.code];
    if (usage === undefined) return;

    if (e.type === "keydown") {
      this.held.add(usage);
      this.pushWithDelay({ t: "down", k: usage });
    } else {
      // macOS sends no keyup for keys released while Cmd is held; release them with Cmd
      if (usage === 0xe3 || usage === 0xe7) {
        this.held.forEach(k => {
          if (k !== usage && !(k >= 0xe0 && k <= 0xe7)) {
            this.pushWithDelay({ t: "up", k });
            this.held.delete(k);
          }
        });
      }
      if (!this.held.has(usage)) return;
      this.held.delete(usage);
      this.pushWithDelay({ t: "up", k: usage });
    }
    this.renderEvents();
  }

  describe(ev) {
    switch (ev.t) {
      case "delay": return `⏱ Chờ ${ev.ms} ms`;
      case "down": return `↓ Nhấn ${usageName(ev.k)}`;
      case "up": return `↑ Nhả ${usageName(ev.k)}`;
      case "mdown": return `🖱↓ Nhấn ${MOUSE_BUTTONS[ev.b] || ev.b}`;
      case "mup": return `🖱↑ Nhả ${MOUSE_BUTTONS[ev.b] || ev.b}`;
      default: return ev.t;
    }
  }

  renderEvents() {
    const list = this.$("macroEvents");
    const events = this.macro ? this.macro.events : [];
    const rows = events.map((ev, i) => {
      const li = document.createElement("li");
      const text = document.createElement("span");
      text.textContent = this.describe(ev);
      const remove = document.createElement("button");
      remove.className = "macro-remove";
      remove.dataset.remove = String(i);
      remove.title = "Xoá";
      remove.textContent = "×";
      li.append(text, remove);
      return li;
    });
    if (!rows.length) {
      const empty = document.createElement("li");
      empty.className = "macro-empty";
      empty.textContent = this.macro ? "Chưa có thao tác nào. Bấm Ghi rồi gõ phím." : "Chưa có macro. Bấm + Tạo macro.";
      rows.push(empty);
    }
    list.replaceChildren(...rows);
    list.scrollTop = list.scrollHeight;
  }

  render() {
    const list = this.$("macroList");
    list.replaceChildren(...this.macros.map((m, i) => new Option(m.name, String(i))));
    if (this.current >= 0) list.value = String(this.current);

    const recordBtn = this.$("btnMacroRecord");
    recordBtn.textContent = this.recording ? "■ Dừng ghi" : "● Ghi thao tác";
    recordBtn.classList.toggle("recording", this.recording);
    this.$("macroRecordHint").style.display = this.recording ? "" : "none";
    this.renderEvents();
  }
}
