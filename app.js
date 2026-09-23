// LEOBOG AMG65 Studio - Application Logic
import { LeobogDriver } from "./driver.js";
import { KEYBOARD_KEYS, LIGHT_MODES, KEY_REMAP_CATEGORIES } from "./layout.js";
import { LedMatrixEditor } from "./ledmatrix.js";

class AppUI {
  constructor() {
    this.driver = new LeobogDriver();
    this.currentLayer = 0;
    this.selectedKey = null;
    this.keyRemapCache = {}; // key_index -> new key name / code
    this.keyColors = {};     // light_index -> "#rrggbb"
    this.paintMode = false;

    this.initElements();
    this.initKeyboardLayout();
    this.initLightingControls();
    this.initRemapModal();
    this.initTabs();
    this.initClock();
    this.attachEvents();
    this.ledMatrix = new LedMatrixEditor(this);
    this.initKeyColorControls();
    this.initSettingsControls();
    this.initProfileControls();
    this.initTftControls();
    this.loadUserConfig();

    // Try auto-connecting on start
    this.driver.autoConnect();
  }

  initElements() {
    this.statusDot = document.getElementById("statusDot");
    this.statusText = document.getElementById("statusText");
    this.batteryFill = document.getElementById("batteryFill");
    this.batteryText = document.getElementById("batteryText");
    this.lcdBatteryText = document.getElementById("lcdBatteryText");
    this.btnConnect = document.getElementById("btnConnect");
    this.btnQuickSync = document.getElementById("btnQuickSync");
    this.btnSyncTimeBig = document.getElementById("btnSyncTimeBig");
    this.lcdClockText = document.getElementById("lcdClockText");
    this.currentMacTimeText = document.getElementById("currentMacTimeText");
    this.keysContainer = document.getElementById("keysContainer");
    this.ambientGlow = document.getElementById("ambientGlow");
    this.logToast = document.getElementById("logToast");
    this.remapModal = document.getElementById("remapModal");
    this.closeRemapModal = document.getElementById("closeRemapModal");
    this.remapKeyTitle = document.getElementById("remapKeyTitle");
    this.remapCategoriesContainer = document.getElementById("remapCategoriesContainer");
    this.knobDial = document.getElementById("knobDial");
  }

  showToast(message, type = "info") {
    if (!this.logToast) return;
    this.logToast.textContent = message;
    this.logToast.className = "log-toast visible";
    
    if (type === "success") {
      this.logToast.style.borderColor = "var(--accent-emerald)";
      this.logToast.style.color = "var(--accent-emerald)";
    } else if (type === "error") {
      this.logToast.style.borderColor = "var(--accent-red)";
      this.logToast.style.color = "var(--accent-red)";
    } else {
      this.logToast.style.borderColor = "var(--accent-cyan)";
      this.logToast.style.color = "var(--accent-cyan)";
    }

    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => {
      this.logToast.className = "log-toast";
    }, 3500);
  }

  initClock() {
    const updateTime = () => {
      const now = new Date();
      const timeStr = now.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const clockShort = now.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
      const dateStr = `${now.getFullYear()}/${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')}`;
      
      if (this.lcdClockText) this.lcdClockText.textContent = clockShort;
      if (this.currentMacTimeText) this.currentMacTimeText.textContent = timeStr;
      const lcdDate = document.getElementById("lcdDateText");
      if (lcdDate) lcdDate.textContent = dateStr;
    };
    updateTime();
    setInterval(updateTime, 1000);
  }

  initKeyboardLayout() {
    this.keysContainer.innerHTML = "";
    
    KEYBOARD_KEYS.forEach(k => {
      // Don't render knobs inside the main keycap matrix (knob has dedicated widget)
      if (k.is_knob) return;

      const keyEl = document.createElement("div");
      keyEl.className = "keycap";
      keyEl.dataset.keyIndex = k.key_index;
      keyEl.dataset.code = k.code;

      // Position in percentages based on 1000x400 canvas
      keyEl.style.left = `${(k.x / 1000) * 100}%`;
      keyEl.style.top = `${(k.y / 400) * 100}%`;
      keyEl.style.width = `${(k.w / 1000) * 100}%`;
      keyEl.style.height = `${(k.h / 400) * 100}%`;

      if (k.name === "Esc") keyEl.classList.add("accent-esc");
      if (k.name === "Space") keyEl.classList.add("accent-space");
      if (k.name === "Enter") keyEl.classList.add("accent-enter");

      const color = this.keyColors[k.light_index];
      if (color) {
        keyEl.style.color = color;
        keyEl.classList.add("painted");
      }

      const label = this.keyRemapCache[k.key_index] || k.name;
      const fnLabel = k.fn ? `Fn: ${k.fn}` : "";

      keyEl.innerHTML = `
        <span class="key-primary">${label}</span>
        ${fnLabel ? `<span class="key-secondary">${fnLabel}</span>` : ""}
      `;

      keyEl.addEventListener("click", () => {
        if (this.paintMode) this.paintKey(k);
        else this.openRemap(k);
      });
      this.keysContainer.appendChild(keyEl);
    });
  }

  updateKeyboardDisplay() {
    document.querySelectorAll(".keycap").forEach(el => {
      const idx = parseInt(el.dataset.keyIndex);
      const k = KEYBOARD_KEYS.find(item => item.key_index === idx);
      if (!k) return;

      const color = this.keyColors[k.light_index];
      el.style.color = color || "";
      el.classList.toggle("painted", !!color);

      const primary = el.querySelector(".key-primary");
      if (primary) {
        if (this.currentLayer === 1 && k.fn) {
          primary.textContent = k.fn;
          primary.style.color = "var(--accent-amber)";
        } else {
          primary.textContent = this.keyRemapCache[k.key_index] || k.name;
          primary.style.color = "var(--text-primary)";
        }
      }
    });
  }

  initLightingControls() {
    const select = document.getElementById("lightModeSelect");
    if (!select) return;

    select.innerHTML = "";
    LIGHT_MODES.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.name;
      select.appendChild(opt);
    });
    // Default to mode 5 (Colourful Wave)
    select.value = "5";

    const chkRainbow = document.getElementById("chkRainbow");
    const singleColorControls = document.getElementById("singleColorControls");
    const brightnessRange = document.getElementById("brightnessRange");
    const brightnessVal = document.getElementById("brightnessVal");
    const speedRange = document.getElementById("speedRange");
    const speedVal = document.getElementById("speedVal");
    const rgbColorPicker = document.getElementById("rgbColorPicker");
    const hexColorVal = document.getElementById("hexColorVal");

    chkRainbow.addEventListener("change", () => {
      singleColorControls.style.display = chkRainbow.checked ? "none" : "flex";
    });

    brightnessRange.addEventListener("input", (e) => {
      brightnessVal.textContent = `${e.target.value}/4`;
    });

    speedRange.addEventListener("input", (e) => {
      speedVal.textContent = `${e.target.value}/4`;
    });

    rgbColorPicker.addEventListener("input", (e) => {
      hexColorVal.textContent = e.target.value.toUpperCase();
      this.updateAmbientGlow(e.target.value);
    });

    document.querySelectorAll(".color-swatch").forEach(swatch => {
      swatch.addEventListener("click", () => {
        document.querySelectorAll(".color-swatch").forEach(s => s.classList.remove("active"));
        swatch.classList.add("active");
        const color = swatch.dataset.color;
        rgbColorPicker.value = color;
        hexColorVal.textContent = color.toUpperCase();
        this.updateAmbientGlow(color);
      });
    });

    document.getElementById("btnApplyLighting").addEventListener("click", async () => {
      const mode = parseInt(select.value);
      const brightness = parseInt(brightnessRange.value);
      const speed = parseInt(speedRange.value);
      const isRainbow = chkRainbow.checked;
      
      const hex = rgbColorPicker.value;
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);

      try {
        await this.driver.setLighting({ mode, brightness, speed, r, g, b, isRainbow });
        this.showToast("Đã áp dụng hiệu ứng LED thành công!", "success");
      } catch (err) {
        this.showToast("Lỗi cài đặt LED: " + err.message, "error");
      }
    });
  }

  updateAmbientGlow(colorHex) {
    if (!this.ambientGlow) return;
    this.ambientGlow.style.background = `radial-gradient(circle, ${colorHex}55 0%, transparent 70%)`;
  }

  initRemapModal() {
    this.remapCategoriesContainer.innerHTML = "";
    KEY_REMAP_CATEGORIES.forEach(cat => {
      const catDiv = document.createElement("div");
      catDiv.innerHTML = `<div class="remap-category-title">${cat.name}</div>`;
      
      const grid = document.createElement("div");
      grid.className = "remap-keys-grid";

      cat.keys.forEach(k => {
        const btn = document.createElement("button");
        btn.className = "remap-key-btn";
        btn.textContent = k.name;
        btn.addEventListener("click", () => this.applyRemap(k));
        grid.appendChild(btn);
      });

      catDiv.appendChild(grid);
      this.remapCategoriesContainer.appendChild(catDiv);
    });

    // Custom combo: any key from the plain-key categories plus modifier checkboxes
    const comboKey = document.getElementById("comboKey");
    KEY_REMAP_CATEGORIES.filter(c => c.keys.every(k => k.kind === "key")).forEach(cat => {
      const group = document.createElement("optgroup");
      group.label = cat.name;
      cat.keys.forEach(k => {
        const opt = document.createElement("option");
        opt.value = k.code;
        opt.textContent = k.name;
        group.appendChild(opt);
      });
      comboKey.appendChild(group);
    });
    document.getElementById("btnApplyCombo").addEventListener("click", () => {
      const mods = [...document.querySelectorAll(".combo-builder [data-mod]")].filter(c => c.checked);
      const mask = mods.reduce((m, c) => m | Number(c.dataset.mod), 0);
      if (!mask) {
        this.showToast("Chọn ít nhất một phím bổ trợ (⌃ ⇧ ⌥ ⌘).", "info");
        return;
      }
      const symbols = { 1: "⌃", 2: "⇧", 4: "⌥", 8: "⌘" };
      const keyName = comboKey.options[comboKey.selectedIndex].text;
      const name = mods.map(c => symbols[c.dataset.mod]).join(" + ") + " + " + keyName;
      this.applyRemap({ kind: "shortcut", code: (mask << 8) | Number(comboKey.value), name });
    });

    this.closeRemapModal.addEventListener("click", () => {
      this.remapModal.classList.remove("open");
      if (this.selectedKeyElement) this.selectedKeyElement.classList.remove("selected");
    });
  }

  openRemap(key) {
    if (this.currentLayer === 1) {
      this.showToast("Tầng Fn do firmware bàn phím quy định, phần mềm gốc cũng không đổi được.", "info");
      return;
    }
    this.selectedKey = key;
    this.remapKeyTitle.textContent = `Đổi phím: ${key.name}`;
    this.remapKeySubtitle = `Gán lại chức năng cho phím (Tầng ${this.currentLayer}, Index: ${key.key_index})`;

    document.querySelectorAll(".keycap").forEach(el => el.classList.remove("selected"));
    this.selectedKeyElement = document.querySelector(`.keycap[data-key-index="${key.key_index}"]`);
    if (this.selectedKeyElement) this.selectedKeyElement.classList.add("selected");

    this.remapModal.classList.add("open");
  }

  async applyRemap(remapTarget) {
    if (!this.selectedKey) return;
    
    this.keyRemapCache[this.selectedKey.key_index] = remapTarget.name;
    this.updateKeyboardDisplay();
    this.remapModal.classList.remove("open");
    
    if (this.selectedKeyElement) this.selectedKeyElement.classList.remove("selected");

    this.showToast(`Đang gán phím ${this.selectedKey.name} -> ${remapTarget.name}...`, "info");
    try {
      await this.driver.remapKey(this.selectedKey.key_index, remapTarget.kind || "key", remapTarget.code, remapTarget.name);
      if (remapTarget.kind === "default") delete this.keyRemapCache[this.selectedKey.key_index];
      this.showToast(`Đã lưu thành công: ${this.selectedKey.name} -> ${remapTarget.name}!`, "success");
    } catch (err) {
      delete this.keyRemapCache[this.selectedKey.key_index];
      this.updateKeyboardDisplay();
      this.showToast("Lỗi: " + err.message, "error");
    }
  }

  async loadUserConfig() {
    try {
      const res = await fetch("/api/user-config");
      const data = await res.json();
      this.keyColors = data.keyColors || {};
      Object.entries(data.keymap || {}).forEach(([keyIndex, entry]) => {
        const target = KEY_REMAP_CATEGORIES.flatMap(c => c.keys)
          .find(k => k.code === entry.code && (k.kind || "key") === entry.kind);
        const name = target ? target.name : entry.label;
        if (name) this.keyRemapCache[keyIndex] = name;
      });
      this.applySettingsToUI(data.settings || {});
      document.getElementById("sitReminder").value = String(data.sitReminder || 0);
      document.getElementById("tftSlot").value = String(data.tftSlot || 1);
      document.getElementById("chkTftSysInfo").checked = !!data.tftSysInfo;
      this.updateKeyboardDisplay();
    } catch (e) {
      // first run: no saved config yet
    }
  }

  paintKey(key) {
    const color = document.getElementById("keyPaintColor").value;
    this.keyColors[key.light_index] = color;
    this.updateKeyboardDisplay();
    document.getElementById("keyColorStatus").textContent =
      `Đã tô ${key.name}. Bấm "Áp Dụng Màu Lên Phím" để gửi xuống bàn phím.`;
  }

  setPaintMode(on) {
    this.paintMode = on;
    const btn = document.getElementById("btnKeyPaintMode");
    btn.textContent = on ? "Tắt chế độ tô màu" : "Bật chế độ tô màu";
    btn.classList.toggle("active", on);
    const hint = document.getElementById("remapHint");
    if (hint) {
      hint.textContent = on
        ? "Đang ở chế độ TÔ MÀU: bấm vào phím để tô màu đã chọn"
        : "Nhấp vào bất kỳ phím nào để đổi tính năng (Remap)";
    }
  }

  initKeyColorControls() {
    const status = document.getElementById("keyColorStatus");
    document.getElementById("btnKeyPaintMode").addEventListener("click", () => {
      this.setPaintMode(!this.paintMode);
      if (this.paintMode) {
        document.querySelector("[data-tab=tab-remap]").click();
        this.showToast("Đang ở chế độ tô màu: bấm vào phím trên sơ đồ để tô.", "info");
      }
    });

    document.getElementById("btnKeyColorsClear").addEventListener("click", () => {
      this.keyColors = {};
      this.updateKeyboardDisplay();
      status.textContent = 'Đã xoá màu trên sơ đồ. Bấm "Áp Dụng Màu Lên Phím" để gửi xuống bàn phím.';
    });

    document.getElementById("btnKeyColorsApply").addEventListener("click", async () => {
      status.textContent = "Đang gửi bảng màu xuống bàn phím...";
      try {
        const res = await this.driver.applyKeyColors(this.keyColors);
        status.textContent = `Đã gửi màu cho ${res.keys} phím.`;
        this.showToast("Đã áp dụng màu riêng từng phím!", "success");
      } catch (err) {
        status.textContent = "Lỗi: " + err.message;
        this.showToast("Lỗi: " + err.message, "error");
      }
    });

    document.getElementById("btnKeyColorsRead").addEventListener("click", async () => {
      status.textContent = "Đang đọc màu hiện có từ bàn phím...";
      try {
        this.keyColors = await this.driver.readKeyColors();
        this.updateKeyboardDisplay();
        status.textContent = "Đã đọc xong màu từ bàn phím.";
      } catch (err) {
        status.textContent = "Lỗi: " + err.message;
        this.showToast("Lỗi: " + err.message, "error");
      }
    });
  }

  settingsFromUI() {
    const checked = id => (document.getElementById(id).checked ? 1 : 0);
    return {
      gameMode: checked("setGameMode"),
      disableWin: checked("setDisableWin"),
      disableAltTab: checked("setDisableAltTab"),
      disableAltF4: checked("setDisableAltF4"),
      fnToggle: checked("setFnToggle"),
      sleepLight: Number(document.getElementById("setSleepLight").value),
      ledBrightness: Number(document.getElementById("setLedBrightness").value)
    };
  }

  applySettingsToUI(settings) {
    const set = (id, value) => { document.getElementById(id).checked = !!value; };
    set("setGameMode", settings.gameMode);
    set("setDisableWin", settings.disableWin);
    set("setDisableAltTab", settings.disableAltTab);
    set("setDisableAltF4", settings.disableAltF4);
    set("setFnToggle", settings.fnToggle);
    if (settings.sleepLight !== undefined) document.getElementById("setSleepLight").value = settings.sleepLight;
    if (settings.ledBrightness !== undefined) {
      document.getElementById("setLedBrightness").value = settings.ledBrightness;
      document.getElementById("setBrightnessVal").textContent = settings.ledBrightness;
    }
  }

  initSettingsControls() {
    const brightness = document.getElementById("setLedBrightness");
    brightness.addEventListener("input", () => {
      document.getElementById("setBrightnessVal").textContent = brightness.value;
    });

    const status = document.getElementById("settingsStatus");
    document.getElementById("btnApplySettings").addEventListener("click", async () => {
      status.textContent = "Đang lưu cài đặt...";
      try {
        await this.driver.applySettings(this.settingsFromUI());
        status.textContent = "Đã lưu cài đặt vào bàn phím.";
        this.showToast("Đã lưu cài đặt vào bàn phím!", "success");
      } catch (err) {
        status.textContent = "Lỗi: " + err.message;
        this.showToast("Lỗi: " + err.message, "error");
      }
    });
  }

  initTftControls() {
    document.getElementById("btnShowTftSlot").addEventListener("click", async () => {
      const slot = Number(document.getElementById("tftSlot").value);
      try {
        await this.driver.selectTftSlot(slot);
        this.showToast(`Màn hình đang hiển thị ô ${slot}.`, "success");
      } catch (err) {
        this.showToast("Lỗi: " + err.message, "error");
      }
    });
    document.getElementById("chkTftSysInfo").addEventListener("change", async e => {
      try {
        await this.driver.setTftSysInfo(e.target.checked);
        this.showToast(e.target.checked ? "Đang gửi CPU/GPU lên màn hình." : "Đã dừng gửi CPU/GPU.", "success");
      } catch (err) {
        e.target.checked = !e.target.checked;
        this.showToast("Lỗi: " + err.message, "error");
      }
    });
  }

  initProfileControls() {
    const status = document.getElementById("profileStatus");
    const fail = err => {
      status.textContent = "Lỗi: " + err.message;
      this.showToast("Lỗi: " + err.message, "error");
    };

    document.getElementById("sitReminder").addEventListener("change", async e => {
      try {
        const res = await this.driver.setSitReminder(Number(e.target.value));
        this.showToast(res.minutes ? `Sẽ nhắc sau ${res.minutes} phút dùng máy liên tục.` : "Đã tắt nhắc nhở.", "success");
      } catch (err) {
        this.showToast("Lỗi: " + err.message, "error");
      }
    });

    document.getElementById("btnExportProfile").addEventListener("click", async () => {
      try {
        const data = await (await fetch("/api/user-config")).json();
        const { success, ...profile } = data;
        const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `amg65-profile-${new Date().toISOString().slice(0, 10)}.json`;
        link.click();
        URL.revokeObjectURL(link.href);
        status.textContent = "Đã xuất hồ sơ cấu hình.";
      } catch (err) {
        fail(err);
      }
    });

    const fileInput = document.getElementById("profileFileInput");
    document.getElementById("btnImportProfile").addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async e => {
      const file = e.target.files[0];
      fileInput.value = "";
      if (!file) return;
      status.textContent = "Đang nạp hồ sơ vào bàn phím...";
      try {
        await this.driver.importProfile(JSON.parse(await file.text()));
        this.keyRemapCache = {};
        await this.loadUserConfig();
        status.textContent = `Đã nạp hồ sơ từ ${file.name}.`;
        this.showToast("Đã nạp hồ sơ cấu hình vào bàn phím!", "success");
      } catch (err) {
        fail(err);
      }
    });

    document.getElementById("btnFactoryReset").addEventListener("click", async () => {
      if (!confirm("Trả toàn bộ gán phím và cài đặt về mặc định?")) return;
      status.textContent = "Đang khôi phục...";
      try {
        await this.driver.factoryReset();
        this.keyRemapCache = {};
        await this.loadUserConfig();
        status.textContent = "Đã khôi phục cài đặt gốc.";
        this.showToast("Đã khôi phục cài đặt gốc!", "success");
      } catch (err) {
        fail(err);
      }
    });
  }

  initTabs() {
    const tabBtns = document.querySelectorAll(".tab-btn");
    tabBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        tabBtns.forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

        btn.classList.add("active");
        const target = btn.dataset.tab;
        const pane = document.getElementById(target);
        if (pane) pane.classList.add("active");
      });
    });
  }

  attachEvents() {
    // Driver listeners
    this.driver.onStatusChange = (connected, device) => {
      if (connected) {
        this.statusDot.classList.add("connected");
        this.statusText.textContent = "Đã kết nối";
        this.btnConnect.textContent = "Ngắt Kết Nối";
        this.btnConnect.classList.remove("btn-primary");
        this.btnConnect.classList.add("btn-secondary");
        this.showToast(`Bàn phím LEOBOG AMG65 đã sẵn sàng!`, "success");
      } else {
        this.statusDot.classList.remove("connected");
        this.statusText.textContent = "Chưa kết nối";
        this.btnConnect.textContent = "Kết Nối Bàn Phím";
        this.btnConnect.classList.remove("btn-secondary");
        this.btnConnect.classList.add("btn-primary");
        this.batteryText.textContent = "--%";
        this.batteryFill.style.width = "0%";
      }
    };

    // Wired mode has no battery read-back, so percent is null there
    this.driver.onBatteryUpdate = (percent, charging) => {
      const label = percent == null ? "USB" : `${percent}%`;
      this.batteryText.textContent = label;
      this.batteryFill.style.width = percent == null ? "100%" : `${percent}%`;
      if (this.lcdBatteryText) this.lcdBatteryText.textContent = label;

      const infoCharging = document.getElementById("infoChargingStatus");
      if (infoCharging) {
        infoCharging.textContent = percent == null
          ? "Đang cắm dây USB (chế độ có dây không đọc được % pin)"
          : charging ? `Đang sạc qua cáp USB (${percent}%)` : `Dùng pin (${percent}%)`;
      }
    };

    this.driver.onLog = (msg, type) => {
      this.showToast(msg, type);
    };

    // Connect Button
    this.btnConnect.addEventListener("click", () => {
      if (this.driver.isConnected) {
        this.driver.disconnect();
      } else {
        this.driver.connect();
      }
    });

    // Clock Sync Buttons
    const syncTimeHandler = async () => {
      if (!this.driver.isConnected) {
        alert("Vui lòng kết nối bàn phím trước khi đồng bộ giờ!");
        return;
      }
      await this.driver.syncTime();
      this.showToast("Đã đồng bộ giờ Mac thành công vào màn hình bàn phím!", "success");
    };

    this.btnQuickSync.addEventListener("click", syncTimeHandler);
    this.btnSyncTimeBig.addEventListener("click", syncTimeHandler);

    // Layer Switcher
    document.getElementById("layer0Btn").addEventListener("click", () => {
      this.currentLayer = 0;
      document.getElementById("layer0Btn").classList.add("active");
      document.getElementById("layer1Btn").classList.remove("active");
      this.updateKeyboardDisplay();
    });

    document.getElementById("layer1Btn").addEventListener("click", () => {
      this.currentLayer = 1;
      document.getElementById("layer1Btn").classList.add("active");
      document.getElementById("layer0Btn").classList.remove("active");
      this.updateKeyboardDisplay();
    });

    // Rotary Knob Click & Rotation Animation
    let knobAngle = 0;
    this.knobDial.addEventListener("click", () => {
      knobAngle += 30;
      this.knobDial.style.transform = `scale(1.05) rotate(${knobAngle}deg)`;
      this.showToast("Xoay núm âm lượng: Volume +", "info");
    });

    document.getElementById("btnRemapKnobCW").addEventListener("click", () => {
      const knobKey = KEYBOARD_KEYS.find(k => k.code === "0xE9");
      if (knobKey) this.openRemap(knobKey);
    });

    document.getElementById("btnRemapKnobCCW").addEventListener("click", () => {
      const knobKey = KEYBOARD_KEYS.find(k => k.code === "0xEA");
      if (knobKey) this.openRemap(knobKey);
    });

    // TFT Image / GIF selector
    document.getElementById("btnSelectGif").addEventListener("click", () => {
      document.getElementById("tftFileInput").click();
    });

    const tftFileInput = document.getElementById("tftFileInput");
    const selectedFileName = document.getElementById("selectedFileName");
    const lcdPreviewImg = document.getElementById("lcdPreviewImg");
    const lcdPlaceholder = document.getElementById("lcdPlaceholder");
    const lcdFileStats = document.getElementById("lcdFileStats");
    const statDimensions = document.getElementById("statDimensions");
    const statType = document.getElementById("statType");
    const statSize = document.getElementById("statSize");
    const btnUploadLcd = document.getElementById("btnUploadLcd");
    const lcdUploadProgress = document.getElementById("lcdUploadProgress");
    const lcdProgressBar = document.getElementById("lcdProgressBar");
    const lcdProgressPercent = document.getElementById("lcdProgressPercent");
    const lcdProgressText = document.getElementById("lcdProgressText");

    this.currentLcdImageDataUrl = null;

    tftFileInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (!file) return;

      selectedFileName.textContent = file.name;
      const sizeKb = (file.size / 1024).toFixed(1);
      const isGif = file.type === "image/gif" || file.name.toLowerCase().endsWith(".gif");

      const reader = new FileReader();
      reader.onload = (loadEvt) => {
        this.currentLcdImageDataUrl = loadEvt.target.result;

        // Display preview
        lcdPreviewImg.src = this.currentLcdImageDataUrl;
        lcdPreviewImg.style.display = "block";
        lcdPlaceholder.style.display = "none";

        // Read natural image dimensions
        const testImg = new Image();
        testImg.onload = () => {
          statDimensions.textContent = `Gốc: ${testImg.naturalWidth}x${testImg.naturalHeight} px`;
          statType.textContent = isGif ? "GIF động" : "Ảnh tĩnh (PNG/JPG)";
          statSize.textContent = `${sizeKb} KB`;
          lcdFileStats.style.display = "flex";
          btnUploadLcd.disabled = false;
          this.showToast(`Đã tải ảnh: ${file.name} (${testImg.naturalWidth}x${testImg.naturalHeight}). Sẵn sàng nạp!`, "success");
        };
        testImg.src = this.currentLcdImageDataUrl;
      };
      reader.readAsDataURL(file);
    });

    btnUploadLcd.addEventListener("click", async () => {
      if (!this.currentLcdImageDataUrl) return;

      btnUploadLcd.disabled = true;
      lcdUploadProgress.style.display = "flex";
      lcdProgressBar.style.width = "10%";
      lcdProgressPercent.textContent = "10%";
      lcdProgressText.textContent = "Đang chuyển đổi mã màu RGB565...";

      try {
        // Animate progress simulation while upload is happening
        let progress = 15;
        const interval = setInterval(() => {
          if (progress < 85) {
            progress += 5;
            lcdProgressBar.style.width = `${progress}%`;
            lcdProgressPercent.textContent = `${progress}%`;
            if (progress > 30) {
              lcdProgressText.textContent = "Đang ghi dữ liệu vào bộ nhớ Flash của màn hình...";
            }
          }
        }, 150);

        const res = await this.driver.uploadLcdImage(this.currentLcdImageDataUrl, Number(document.getElementById("tftSlot").value));
        clearInterval(interval);

        lcdProgressBar.style.width = "100%";
        lcdProgressPercent.textContent = "100%";
        lcdProgressText.textContent = `Hoàn tất! Đã nạp ${res.frames} khung hình vào bàn phím.`;

        this.showToast(`Đã nạp thành công ${res.frames} khung hình lên màn hình bàn phím!`, "success");

        setTimeout(() => {
          btnUploadLcd.disabled = false;
        }, 2000);
      } catch (err) {
        lcdProgressBar.style.width = "0%";
        lcdProgressText.textContent = "Lỗi khi nạp: " + err.message;
        this.showToast("Lỗi: " + err.message, "error");
        btnUploadLcd.disabled = false;
      }
    });

    // Config Save & Reload
    document.getElementById("btnResetKeymap").addEventListener("click", async () => {
      if (!confirm("Trả tất cả phím đã gán về chức năng gốc?")) return;
      try {
        await this.driver.resetKeymap();
        this.keyRemapCache = {};
        this.updateKeyboardDisplay();
        this.showToast("Đã trả tất cả phím về chức năng gốc.", "success");
      } catch (err) {
        this.showToast("Lỗi: " + err.message, "error");
      }
    });
  }
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  window.app = new AppUI();
});
