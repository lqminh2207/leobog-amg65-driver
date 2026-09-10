// LEOBOG AMG65 WebHID Driver
// Implements the reverse-engineered USB HID protocol for macOS

export class LeobogDriver {
  constructor() {
    this.device = null;
    this.isConnected = false;
    this.battery = null;
    this.isCharging = false;
    this.configBuffer = new Uint8Array(512);
    this.pendingResolvers = [];
    this.onStatusChange = null;
    this.onBatteryUpdate = null;
    this.onLog = null;

    this.filters = [
      {
        vendorId: 0x0c45, // SONiX
        productId: 0x800a, // LEOBOG AMG65
        usagePage: 0xff68, // Vendor Defined Page
        usage: 0x0061
      }
    ];
  }

  log(msg, type = "info") {
    console.log(`[LEOBOG Driver] ${msg}`);
    if (this.onLog) this.onLog(msg, type);
  }

  async autoConnect() {
    if (!navigator.hid) {
      this.log("Trình duyệt này không hỗ trợ WebHID. Hãy dùng Google Chrome, Microsoft Edge, hoặc Brave trên macOS.", "error");
      return false;
    }

    try {
      const devices = await navigator.hid.getDevices();
      const matched = devices.find(d => 
        d.vendorId === 0x0c45 && 
        d.productId === 0x800a &&
        d.collections.some(c => c.usagePage === 0xff68 && c.usage === 0x0061)
      );

      if (matched) {
        this.log("Tìm thấy bàn phím đã ghép nối trước đó. Đang kết nối lại...", "info");
        return await this._openDevice(matched);
      }
    } catch (err) {
      this.log(`Lỗi khi auto-connect: ${err.message}`, "warn");
    }
    return false;
  }

  async connect() {
    if (!navigator.hid) {
      alert("Trình duyệt không hỗ trợ WebHID API!\nVui lòng sử dụng Google Chrome, Edge, Arc hoặc Brave trên macOS.");
      return false;
    }

    try {
      const devices = await navigator.hid.requestDevice({ filters: this.filters });
      if (!devices || devices.length === 0) {
        this.log("Người dùng đã hủy chọn thiết bị.", "warn");
        return false;
      }

      return await this._openDevice(devices[0]);
    } catch (err) {
      this.log(`Không thể kết nối thiết bị: ${err.message}`, "error");
      return false;
    }
  }

  async _openDevice(device) {
    try {
      if (!device.opened) {
        await device.open();
      }

      this.device = device;
      this.isConnected = true;
      this.log(`Đã kết nối thành công với ${device.productName || "LEOBOG AMG65"}!`, "success");

      this.device.addEventListener("inputreport", (event) => {
        this._handleInputReport(event);
      });

      if (this.onStatusChange) this.onStatusChange(true, device);

      // Query initial battery & status
      setTimeout(() => this.getBattery(), 300);
      // Auto sync time to screen clock
      setTimeout(() => this.syncTime(), 800);
      // Read initial keymap
      setTimeout(() => this.readConfig(), 1200);

      return true;
    } catch (err) {
      this.log(`Lỗi khi mở cổng HID: ${err.message}`, "error");
      this.isConnected = false;
      if (this.onStatusChange) this.onStatusChange(false, null);
      return false;
    }
  }

  async disconnect() {
    if (this.device) {
      try {
        await this.device.close();
      } catch (e) {}
    }
    this.device = null;
    this.isConnected = false;
    this.log("Đã ngắt kết nối với bàn phím.", "info");
    if (this.onStatusChange) this.onStatusChange(false, null);
  }

  _handleInputReport(event) {
    const { data } = event;
    const bytes = new Uint8Array(data.buffer);
    
    // Check if any promise is waiting for a response
    if (this.pendingResolvers.length > 0) {
      const resolver = this.pendingResolvers.shift();
      resolver(bytes);
    }

    // Battery / Status packet: starts with 0x20 0x01
    if (bytes[0] === 0x20 && bytes[1] === 0x01) {
      const rawBattery = bytes[3];
      if (rawBattery === 0xff) {
        this.battery = 100;
        this.isCharging = true;
      } else {
        this.battery = Math.min(100, Math.max(0, rawBattery));
        this.isCharging = false;
      }
      this.log(`Cập nhật pin: ${this.battery}% ${this.isCharging ? "(Đang cắm dây sạc)" : ""}`, "info");
      if (this.onBatteryUpdate) this.onBatteryUpdate(this.battery, this.isCharging);
    }
  }

  // Send packet with 32-byte checksum protocol
  async sendChecksumCommand(buf32) {
    if (!this.isConnected || !this.device) {
      throw new Error("Bàn phím chưa được kết nối");
    }

    const payload = new Uint8Array(64);
    for (let i = 0; i < 32; i++) {
      payload[i] = buf32[i] || 0;
    }

    // Compute checksum (sum of first 32 bytes & 0xFF)
    let sum = 0;
    for (let i = 0; i < 32; i++) {
      sum = (sum + payload[i]) & 0xff;
    }
    payload[32] = sum;

    // Report ID 0x00
    await this.device.sendReport(0x00, payload);
  }

  // Send 64-byte raw packet
  async sendRawReport(bytes) {
    if (!this.isConnected || !this.device) {
      throw new Error("Bàn phím chưa được kết nối");
    }
    const payload = new Uint8Array(64);
    payload.set(bytes.slice(0, 64));
    await this.device.sendReport(0x00, payload);
  }

  // Synchronize Mac Local Time to Keyboard 1.14" LCD Screen
  async syncTime() {
    this.log("Đang đồng bộ giờ máy Mac vào màn hình LCD bàn phím...", "info");
    const now = new Date();
    const buf = new Uint8Array(32);

    buf[0] = 0x0c;
    buf[1] = 0x10;
    buf[2] = 0x00;
    buf[3] = 0x00;
    buf[4] = 0x01; // active flag
    buf[5] = 0x5a; // magic
    buf[6] = now.getFullYear() % 100; // 26 for 2026
    buf[7] = now.getMonth() + 1;      // 1-12
    buf[8] = now.getDate();           // 1-31
    buf[9] = now.getHours();          // 0-23
    buf[10] = now.getMinutes();       // 0-59
    buf[11] = now.getSeconds();       // 0-59
    buf[12] = (now.getDay() + 6) % 7 + 1; // 1-7 (Mon-Sun)
    
    // Magic trailer
    buf[18] = 0xaa;
    buf[19] = 0x55;

    await this.sendChecksumCommand(buf);
    this.log(`Đã đồng bộ giờ thành công: ${now.toLocaleTimeString("vi-VN")} ${now.toLocaleDateString("vi-VN")}`, "success");
    return true;
  }

  // Query Battery Level
  async getBattery() {
    if (!this.isConnected) return;
    const buf = new Uint8Array(32);
    buf[0] = 0x20;
    buf[1] = 0x01;
    await this.sendChecksumCommand(buf);
  }

  // Set RGB Lighting Mode
  async setLighting({ mode = 1, brightness = 4, speed = 3, r = 0, g = 255, b = 255, isRainbow = true }) {
    this.log(`Đang cài đặt hiệu ứng LED: Mode ${mode}, Độ sáng ${brightness}, Tốc độ ${speed}...`, "info");
    
    const buf = new Uint8Array(32);
    buf[0] = 0x05;
    buf[1] = 0x10;
    buf[2] = 0x00;
    buf[3] = mode & 0xff;
    buf[4] = brightness & 0x07;
    buf[5] = speed & 0x07;
    buf[6] = isRainbow ? 0x00 : 0x01; // 0 = rainbow/cycle, 1 = static custom color
    buf[7] = 0x00;
    buf[8] = r & 0xff;
    buf[9] = g & 0xff;
    buf[10] = b & 0xff;
    
    // Magic trailer
    buf[18] = 0xaa;
    buf[19] = 0x55;

    await this.sendChecksumCommand(buf);
    this.log("Đã áp dụng hiệu ứng LED thành công!", "success");
    return true;
  }

  // Read full 512-byte config buffer (8 blocks of 64 bytes)
  async readConfig() {
    this.log("Đang đọc cấu hình phím từ bộ nhớ bàn phím...", "info");
    try {
      for (let b = 0; b < 8; b++) {
        const req = new Uint8Array(64);
        req[0] = 0x04;
        req[1] = 0xf5;
        req[2] = b;
        req[8] = 0x08;

        const responsePromise = new Promise((resolve) => {
          this.pendingResolvers.push(resolve);
          setTimeout(() => resolve(null), 800);
        });

        await this.sendRawReport(req);
        const resp = await responsePromise;
        if (resp) {
          this.configBuffer.set(resp, b * 64);
        }
      }
      this.log("Đã nạp toàn bộ cấu hình phím thành công.", "success");
      return this.configBuffer;
    } catch (err) {
      this.log(`Lỗi khi đọc cấu hình: ${err.message}`, "warn");
      return null;
    }
  }

  // Remap a specific key
  // keyIndex: matrix key_index from Layout (0..108)
  // newKeyCode: USB HID code (e.g. 0x04 for 'A')
  async remapKey(keyIndex, newKeyCode) {
    this.log(`Remap phím (Index: ${keyIndex}) thành mã 0x${newKeyCode.toString(16)}...`, "info");
    
    const offset = keyIndex * 4;
    if (offset + 2 < this.configBuffer.length) {
      this.configBuffer[offset] = 0x00; // Type
      this.configBuffer[offset + 1] = newKeyCode & 0xff;
      this.configBuffer[offset + 2] = (newKeyCode >> 8) & 0xff;
    }

    // Save and commit to device
    await this.saveConfig();
  }

  // Save current configBuffer to keyboard Flash memory
  async saveConfig() {
    this.log("Đang lưu cấu hình vào bộ nhớ bàn phím...", "info");
    try {
      // 1. Enter config write mode
      const prep = new Uint8Array(64);
      prep[0] = 0x04;
      prep[1] = 0x18;
      await this.sendRawReport(prep);

      // 2. Write 8 blocks
      for (let b = 0; b < 8; b++) {
        const blockData = this.configBuffer.slice(b * 64, (b + 1) * 64);
        const pkt = new Uint8Array(64);
        pkt.set(blockData);
        await this.sendRawReport(pkt);
      }

      // 3. Commit / Save
      const commit = new Uint8Array(64);
      commit[0] = 0x04;
      commit[1] = 0x02;
      await this.sendRawReport(commit);

      this.log("Lưu cấu hình thành công!", "success");
      return true;
    } catch (err) {
      this.log(`Lỗi khi lưu cấu hình: ${err.message}`, "error");
      return false;
    }
  }
}
