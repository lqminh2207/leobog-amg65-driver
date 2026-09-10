// LEOBOG AMG65 Studio - Application Logic
import { LeobogDriver } from "./driver.js";
import { KEYBOARD_KEYS, LIGHT_MODES, KEY_REMAP_CATEGORIES } from "./layout.js";

class AppUI {
  constructor() {
    this.driver = new LeobogDriver();
    this.currentLayer = 0;
    this.selectedKey = null;
    this.keyRemapCache = {}; // key_index -> new key name / code

    this.initElements();
    this.initKeyboardLayout();
    this.initLightingControls();
    this.initRemapModal();
    this.initTabs();
    this.initClock();
    this.attachEvents();

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

      const label = this.keyRemapCache[k.key_index] || k.name;
      const fnLabel = k.fn ? `Fn: ${k.fn}` : "";

      keyEl.innerHTML = `
        <span class="key-primary">${label}</span>
        ${fnLabel ? `<span class="key-secondary">${fnLabel}</span>` : ""}
      `;

      keyEl.addEventListener("click", () => this.openRemap(k));
      this.keysContainer.appendChild(keyEl);
    });
  }

  updateKeyboardDisplay() {
    document.querySelectorAll(".keycap").forEach(el => {
      const idx = parseInt(el.dataset.keyIndex);
      const k = KEYBOARD_KEYS.find(item => item.key_index === idx);
      if (!k) return;

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
      opt.textContent = `${m.id}. ${m.name}`;
      select.appendChild(opt);
    });

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

    document.getElementById("btnApplyLighting").addEventListener("click", () => {
      const mode = parseInt(select.value);
      const brightness = parseInt(brightnessRange.value);
      const speed = parseInt(speedRange.value);
      const isRainbow = chkRainbow.checked;
      
      const hex = rgbColorPicker.value;
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);

      this.driver.setLighting({ mode, brightness, speed, r, g, b, isRainbow });
      this.showToast("Đã gửi cài đặt LED tới bàn phím!", "success");
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

    this.closeRemapModal.addEventListener("click", () => {
      this.remapModal.classList.remove("open");
      if (this.selectedKeyElement) this.selectedKeyElement.classList.remove("selected");
    });
  }

  openRemap(key) {
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
    await this.driver.remapKey(this.selectedKey.key_index, remapTarget.code);
    this.showToast(`Đã lưu thành công: ${this.selectedKey.name} -> ${remapTarget.name}!`, "success");
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

    this.driver.onBatteryUpdate = (percent, charging) => {
      this.batteryText.textContent = `${percent}%`;
      this.batteryFill.style.width = `${percent}%`;
      if (this.lcdBatteryText) this.lcdBatteryText.textContent = `${percent}%`;
      
      const infoCharging = document.getElementById("infoChargingStatus");
      if (infoCharging) {
        infoCharging.textContent = charging ? `Đang sạc qua cáp USB (${percent}%)` : `Dùng pin (${percent}%)`;
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

    document.getElementById("tftFileInput").addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (file) {
        document.getElementById("selectedFileName").textContent = file.name;
        this.showToast(`Đã chọn tệp: ${file.name}. Màn hình hỗ trợ chuẩn 135x240 pixel.`, "success");
      }
    });

    // Config Save & Reload
    document.getElementById("btnSaveConfig").addEventListener("click", async () => {
      if (!this.driver.isConnected) {
        alert("Bàn phím chưa được kết nối!");
        return;
      }
      await this.driver.saveConfig();
      this.showToast("Đã lưu cấu hình phím thành công vào bộ nhớ!", "success");
    });

    document.getElementById("btnReloadConfig").addEventListener("click", async () => {
      if (!this.driver.isConnected) {
        alert("Bàn phím chưa được kết nối!");
        return;
      }
      await this.driver.readConfig();
      this.showToast("Đã nạp lại cấu hình gốc từ bàn phím!", "info");
    });
  }
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  window.app = new AppUI();
});
