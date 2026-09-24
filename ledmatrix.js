// LED matrix (5 x 63 RGB) frame editor
const ROWS = 5;
const COLS = 63;
const CELL = 14;
const OFF = "#000000";
const PALETTE = ["#00f0ff", "#ff007f", "#a855f7", "#10b981", "#fbbf24", "#3b82f6", "#ff3b30", "#ffffff"];
const MAX_FRAMES = { animation: 260, boot: 200 };

const blankFrame = () => new Array(ROWS * COLS).fill(OFF);

export class LedMatrixEditor {
  constructor(app) {
    this.app = app;
    this.driver = app.driver;
    this.frames = [blankFrame()];
    this.current = 0;
    this.tool = "paint";
    this.painting = null;
    this.playTimer = null;

    this.canvas = document.getElementById("ledCanvas");
    this.ctx = this.canvas.getContext("2d");
    this.canvas.width = COLS * CELL;
    this.canvas.height = ROWS * CELL;
    this.colorInput = document.getElementById("ledColor");
    this.frameLabel = document.getElementById("ledFrameLabel");
    this.status = document.getElementById("ledStatus");

    this.initPalette();
    this.attachEvents();
    this.render();
  }

  get frame() {
    return this.frames[this.current];
  }

  initPalette() {
    const palette = document.getElementById("ledPalette");
    PALETTE.forEach(color => {
      const swatch = document.createElement("div");
      swatch.className = "color-swatch";
      swatch.style.background = color;
      swatch.style.color = color;
      swatch.addEventListener("click", () => {
        this.colorInput.value = color;
        this.setTool("paint");
      });
      palette.appendChild(swatch);
    });
  }

  attachEvents() {
    const $ = id => document.getElementById(id);

    this.canvas.addEventListener("contextmenu", e => e.preventDefault());
    this.canvas.addEventListener("pointerdown", e => {
      this.stop();
      const erase = e.button === 2 || this.tool === "erase";
      this.painting = erase ? OFF : this.colorInput.value;
      this.canvas.setPointerCapture(e.pointerId);
      this.paintAt(e);
    });
    this.canvas.addEventListener("pointermove", e => {
      if (this.painting) this.paintAt(e);
    });
    this.canvas.addEventListener("pointerup", () => { this.painting = null; });
    this.canvas.addEventListener("pointercancel", () => { this.painting = null; });

    document.querySelectorAll(".led-tool").forEach(btn => {
      btn.addEventListener("click", () => this.setTool(btn.dataset.tool));
    });
    $("ledFill").addEventListener("click", () => {
      this.frame.fill(this.colorInput.value);
      this.render();
    });
    $("ledClear").addEventListener("click", () => {
      this.frame.fill(OFF);
      this.render();
    });

    $("ledPrev").addEventListener("click", () => this.goto(this.current - 1));
    $("ledNext").addEventListener("click", () => this.goto(this.current + 1));
    $("ledAddFrame").addEventListener("click", () => this.insertFrame(blankFrame()));
    $("ledDupFrame").addEventListener("click", () => this.insertFrame([...this.frame]));
    $("ledDelFrame").addEventListener("click", () => {
      if (this.frames.length === 1) {
        this.frame.fill(OFF);
      } else {
        this.frames.splice(this.current, 1);
        this.current = Math.min(this.current, this.frames.length - 1);
      }
      this.render();
    });
    $("ledDelAllFrames").addEventListener("click", () => {
      if (!confirm(`Xoá tất cả ${this.frames.length} khung hình trong trình vẽ? (Hiệu ứng đã nạp trong phím không bị ảnh hưởng)`)) return;
      this.stop();
      this.frames = [blankFrame()];
      this.current = 0;
      this.render();
    });
    $("ledPlay").addEventListener("click", () => (this.playTimer ? this.stop() : this.play()));

    $("ledImport").addEventListener("click", () => $("ledFileInput").click());
    $("ledFileInput").addEventListener("change", e => this.importFile(e.target.files[0]));

    const speed = $("ledSpeed");
    const brightness = $("ledBrightness");
    // Same geometric curve as matrix_speed_word() in server.py; shown relative to the slowest level
    const showSpeed = () => {
      const word = Math.round(101 * (2 / 101) ** ((Number(speed.value) - 1) / 99));
      $("ledSpeedVal").textContent = `${speed.value} (×${(101 / word).toFixed(1)})`;
    };
    speed.addEventListener("input", showSpeed);
    showSpeed();
    brightness.addEventListener("input", () => { $("ledBrightnessVal").textContent = `${brightness.value}%`; });

    const liveMode = $("ledLiveMode");
    const liveStatus = $("ledLiveStatus");
    liveMode.addEventListener("change", async () => {
      try {
        await this.driver.ledMatrixLive(liveMode.value);
        const label = liveMode.options[liveMode.selectedIndex].text;
        liveStatus.textContent = liveMode.value === "off" ? "Đã tắt lớp trực tiếp." : `Đang hiển thị: ${label}`;
      } catch (err) {
        liveStatus.textContent = "Lỗi: " + err.message;
        this.app.showToast("Lỗi: " + err.message, "error");
        liveMode.value = "off";
      }
    });

    // Music palette: applied to the running layer in place, remembered for next time
    const palette = $("musicPalette");
    const musicColor = $("musicColor");
    const syncMusicOptions = () => {
      $("musicOptions").style.display = liveMode.value === "music" ? "" : "none";
      musicColor.style.display = palette.value === "single" ? "" : "none";
    };
    const pushMusicOptions = async () => {
      syncMusicOptions();
      try {
        await this.driver.ledMatrixLive(liveMode.value === "music" ? "music" : liveMode.value,
                                        { palette: palette.value, color: musicColor.value });
      } catch (err) {
        this.app.showToast("Lỗi: " + err.message, "error");
      }
    };
    palette.addEventListener("change", pushMusicOptions);
    musicColor.addEventListener("change", pushMusicOptions);
    liveMode.addEventListener("change", syncMusicOptions);
    this.setMusicOptions = (name, color) => {
      if (name) palette.value = name;
      if (color) musicColor.value = color;
      syncMusicOptions();
    };

    // Manual LED writes stop the live layer on the server; keep the selector in sync
    const resetLive = () => {
      if (liveMode.value === "off") return;
      liveMode.value = "off";
      liveStatus.textContent = "Đã tắt lớp trực tiếp.";
    };

    $("ledPreview").addEventListener("click", () => this.run($("ledPreview"), async () => {
      resetLive();
      await this.driver.ledMatrixLive("off");
      await this.driver.ledMatrixPreview(this.frame);
      return "Đang hiển thị thử khung hiện tại trên phím (chưa lưu).";
    }));
    $("ledOff").addEventListener("click", () => this.run($("ledOff"), async () => {
      resetLive();
      this.setStatus(this.matrixOff ? "Đang bật lại màn LED..." : "Đang tắt màn LED...");
      return this.toggleOff();
    }));
    $("ledUpload").addEventListener("click", () => this.run($("ledUpload"), async () => {
      resetLive();
      const target = $("ledTarget").value;
      const limit = MAX_FRAMES[target];
      if (this.frames.length > limit) {
        this.app.showToast(`Chỉ nạp ${limit} khung đầu tiên (giới hạn của vị trí này).`, "info");
      }
      this.setStatus(`Đang nạp ${Math.min(this.frames.length, limit)} khung hình...`);
      const res = await this.driver.ledMatrixUpload({
        frames: this.frames.slice(0, limit),
        speed: Number(speed.value),
        brightness: Number(brightness.value),
        target
      });
      return `Đã nạp ${res.frames} khung hình vào màn LED!`;
    }));
  }

  // The keyboard has no off command, so off = matrix brightness 0; the stored animation is kept
  async toggleOff() {
    const off = !this.matrixOff;
    await this.driver.ledMatrixBrightness(off ? { value: 0 } : { restore: true });
    this.matrixOff = off;
    document.getElementById("ledOff").textContent = off ? "Bật Lại Màn LED Ma Trận" : "Tắt Màn LED Ma Trận";
    return off ? "Đã tắt màn LED ma trận (hiệu ứng trong phím vẫn được giữ)." : "Đã bật lại màn LED ma trận.";
  }

  async run(button, task) {
    this.stop();
    button.disabled = true;
    try {
      const message = await task();
      this.setStatus(message);
      this.app.showToast(message, "success");
    } catch (err) {
      this.setStatus("Lỗi: " + err.message);
      this.app.showToast("Lỗi: " + err.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async importFile(file) {
    if (!file) return;
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    try {
      const res = await this.driver.ledMatrixImport(dataUrl, document.getElementById("ledBoost").checked);
      this.frames = res.frames;
      this.current = 0;
      this.render();
      this.app.showToast(`Đã nhập ${res.frames.length} khung hình từ ${file.name}`, "success");
    } catch (err) {
      this.app.showToast("Lỗi: " + err.message, "error");
    }
    document.getElementById("ledFileInput").value = "";
  }

  setTool(tool) {
    this.tool = tool;
    document.querySelectorAll(".led-tool").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.tool === tool);
    });
  }

  setStatus(text) {
    this.status.textContent = text;
  }

  paintAt(e) {
    const rect = this.canvas.getBoundingClientRect();
    const col = Math.floor(((e.clientX - rect.left) / rect.width) * COLS);
    const row = Math.floor(((e.clientY - rect.top) / rect.height) * ROWS);
    if (col < 0 || col >= COLS || row < 0 || row >= ROWS) return;
    const idx = row * COLS + col;
    if (this.frame[idx] === this.painting) return;
    this.frame[idx] = this.painting;
    this.drawCell(row, col);
  }

  goto(index) {
    const n = this.frames.length;
    this.current = ((index % n) + n) % n;
    this.render();
  }

  insertFrame(frame) {
    this.frames.splice(this.current + 1, 0, frame);
    this.current += 1;
    this.render();
  }

  // Browser preview only; the keyboard's own playback speed comes from the speed slider
  play() {
    if (this.frames.length < 2) return;
    document.getElementById("ledPlay").textContent = "■ Dừng";
    this.playTimer = setInterval(() => this.goto(this.current + 1), 100);
  }

  stop() {
    if (!this.playTimer) return;
    clearInterval(this.playTimer);
    this.playTimer = null;
    document.getElementById("ledPlay").textContent = "▶ Phát thử";
  }

  drawCell(row, col) {
    const color = this.frame[row * COLS + col];
    const x = col * CELL;
    const y = row * CELL;
    this.ctx.fillStyle = "#05070a";
    this.ctx.fillRect(x, y, CELL, CELL);
    this.ctx.beginPath();
    this.ctx.arc(x + CELL / 2, y + CELL / 2, CELL / 2 - 1.5, 0, Math.PI * 2);
    this.ctx.fillStyle = color === OFF ? "#1a1f29" : color;
    this.ctx.fill();
  }

  render() {
    for (let row = 0; row < ROWS; row++) {
      for (let col = 0; col < COLS; col++) this.drawCell(row, col);
    }
    this.frameLabel.textContent = `Khung ${this.current + 1} / ${this.frames.length}`;
  }
}
