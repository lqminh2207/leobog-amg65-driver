// LEOBOG AMG65 Driver Bridge for macOS
// Bridges both local native USB driver (zero-permission) and WebHID API

export class LeobogDriver {
  constructor() {
    this.isConnected = false;
    this.battery = null;
    this.isCharging = false;
    this.useNativeBackend = true;
    this.device = null;
    this.onStatusChange = null;
    this.onBatteryUpdate = null;
    this.onLog = null;

    // Start auto polling backend
    this.startBackendPolling();
  }

  log(msg, type = "info") {
    console.log(`[LEOBOG Driver] ${msg}`);
    if (this.onLog) this.onLog(msg, type);
  }

  async startBackendPolling() {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        if (data.connected) {
          this.useNativeBackend = true;
          this.isConnected = true;
          this.battery = data.battery;
          this.isCharging = data.charging;
          this.log(`Đã kết nối trực tiếp với ${data.device} qua Native Driver (Pin: ${this.battery}%)!`, "success");
          if (this.onStatusChange) this.onStatusChange(true, data);
          if (this.onBatteryUpdate) this.onBatteryUpdate(this.battery, this.isCharging);
          return;
        }
      }
    } catch (e) {}

    // Poll every 5s if disconnected
    setTimeout(() => {
      if (!this.isConnected) this.startBackendPolling();
    }, 4000);
  }

  async autoConnect() {
    return await this.startBackendPolling();
  }

  async connect() {
    this.log("Đang kiểm tra kết nối với bàn phím...", "info");
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data = await res.json();
        if (data.connected) {
          this.useNativeBackend = true;
          this.isConnected = true;
          this.battery = data.battery;
          this.isCharging = data.charging;
          this.log(`Đã kết nối thành công với ${data.device}!`, "success");
          if (this.onStatusChange) this.onStatusChange(true, data);
          if (this.onBatteryUpdate) this.onBatteryUpdate(this.battery, this.isCharging);
          return true;
        }
      }
    } catch (err) {
      this.log(`Lỗi kết nối Native Driver: ${err.message}`, "warn");
    }

    // Fallback: WebHID
    if (!navigator.hid) {
      alert("Không tìm thấy bàn phím! Hãy chắc chắn bàn phím LEOBOG AMG65 đã cắm cáp USB vào máy Mac.");
      return false;
    }

    try {
      const devices = await navigator.hid.requestDevice({
        filters: [{ vendorId: 0x0c45, productId: 0x800a }]
      });
      if (!devices || devices.length === 0) return false;

      const target = devices.find(d => 
        d.collections && d.collections.some(c => c.usagePage === 0xff68 || c.usagePage === 65384)
      ) || devices[devices.length - 1];

      if (!target.opened) await target.open();
      this.device = target;
      this.isConnected = true;
      this.useNativeBackend = false;
      this.log(`Đã kết nối qua WebHID với ${target.productName || "LEOBOG AMG65"}!`, "success");
      if (this.onStatusChange) this.onStatusChange(true, target);
      return true;
    } catch (e) {
      this.log(`Lỗi WebHID: ${e.message}`, "error");
      return false;
    }
  }

  async disconnect() {
    this.isConnected = false;
    this.device = null;
    this.log("Đã ngắt kết nối.", "info");
    if (this.onStatusChange) this.onStatusChange(false, null);
  }

  // Synchronize Mac Time
  async syncTime() {
    this.log("Đang đồng bộ giờ máy Mac vào màn hình LCD bàn phím...", "info");
    if (this.useNativeBackend) {
      const res = await fetch("/api/sync-time", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        const now = new Date();
        this.log(`Đã đồng bộ giờ thành công: ${now.toLocaleTimeString("vi-VN")}`, "success");
        return true;
      }
    }
    throw new Error("Không thể đồng bộ giờ");
  }

  // Set Lighting
  async setLighting({ mode = 1, brightness = 4, speed = 3, r = 0, g = 255, b = 255, isRainbow = true }) {
    this.log(`Đang áp dụng hiệu ứng LED Mode ${mode}...`, "info");
    if (this.useNativeBackend) {
      const res = await fetch("/api/lighting", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, brightness, speed, r, g, b, isRainbow })
      });
      const data = await res.json();
      if (data.success) {
        this.log("Đã đổi hiệu ứng LED thành công!", "success");
        return true;
      }
    }
    throw new Error("Không thể đổi hiệu ứng LED");
  }

  // Remap key
    async uploadLcdImage(base64Data) {
    this.log("Đang xử lý và truyền dữ liệu tới bộ nhớ Flash của màn hình...", "info");
    if (this.useNativeBackend) {
      const res = await fetch("/api/upload-lcd", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: base64Data })
      });
      const data = await res.json();
      if (data.success) {
        this.log(`Đã nạp thành công ${data.frames} khung hình (${data.blocks} blocks) vào màn hình LCD!`, "success");
        return data;
      } else {
        throw new Error(data.error || "Không thể nạp ảnh vào màn hình");
      }
    }
    throw new Error("Chưa kết nối tới bàn phím");
  }

  async remapKey(keyIndex, newKeyCode) {
    this.log(`Đang gán phím (Index ${keyIndex} -> 0x${newKeyCode.toString(16)})...`, "info");
    if (this.useNativeBackend) {
      const res = await fetch("/api/remap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyIndex, newKeyCode })
      });
      const data = await res.json();
      if (data.success) {
        this.log("Đã lưu gán phím thành công vào bàn phím!", "success");
        return true;
      }
    }
    throw new Error("Không thể gán phím");
  }

  async readConfig() {
    if (this.useNativeBackend) {
      const res = await fetch("/api/config");
      const data = await res.json();
      if (data.success) {
        this.log("Đã đọc cấu hình phím thành công từ bộ nhớ bàn phím.", "success");
        return data.config;
      }
    }
    return null;
  }

  async saveConfig() {
    this.log("Cấu hình phím đã được lưu tự động!", "success");
    return true;
  }
}
