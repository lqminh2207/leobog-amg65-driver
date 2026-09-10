# LEOBOG AMG65 Studio (macOS)

Phần mềm tùy biến và điều khiển bàn phím cơ **LEOBOG AMG65** dành riêng cho hệ điều hành **macOS**, được dịch ngược và tái thiết kế từ bản driver Windows chính hãng (`AMG65 Driver-1.0.3.1.exe`).

---

## Tính Năng Nổi Bật

1. **Giao diện WebHID hiện đại (Zero-Install)**:
   - Không cần cài đặt phần mềm phức tạp hay lo sợ macOS Gatekeeper chặn ứng dụng không rõ nguồn gốc.
   - Giao diện tối Dark Mode chuẩn Mac với kính mờ (Glassmorphism) và hiệu ứng RGB sống động.

2. **Gán phím trực quan (Key Remap)**:
   - Hiển thị mô phỏng chính xác layout 65% của bàn phím LEOBOG AMG65 theo tọa độ đồ họa gốc.
   - Bấm trực tiếp vào phím bất kỳ để gán lại tính năng: Chữ cái, số, phím F1-F12, phím điều hướng, phím điều khiển đa phương tiện (Media & Audio) hoặc phím tắt hệ thống.
   - Hỗ trợ đổi chức năng 2 chiều cho Núm xoay âm lượng (Volume Rotary Knob).
   - Hỗ trợ Tầng phím mặc định (Layer 0) và Tầng phím Fn (Layer 1).

3. **Phòng điều khiển LED RGB (Lighting Studio)**:
   - Tùy chỉnh đầy đủ 20 chế độ LED tích hợp sẵn (Sóng RGB, Thở, Lấp lánh, Mưa rơi, Lan tỏa, Gợn sóng, Tắt LED...).
   - Điều chỉnh độ sáng và tốc độ chuyển động theo thời gian thực.
   - Bảng màu tùy chỉnh RGB Color Picker hoặc chọn nhanh các dải màu phong cách Cyberpunk / Neon.

4. **Đồng bộ giờ cho Màn hình phụ LCD 1.14 inch**:
   - Khắc phục triệt để lỗi màn hình bàn phím bị sai giờ hoặc đứng kim khi dùng trên Mac.
   - Nút bấm **"Đồng Bộ Giờ Mac"** tự động gửi gói tin cập nhật chính xác ngày, giờ, phút, giây từ macOS vào phím.

5. **Theo dõi trạng thái & Dung lượng pin**:
   - Hiển thị phần trăm pin thực tế và biểu tượng đang sạc pin qua cổng USB.

---

## Cách Khởi Chạy Ứng Dụng Trên Mac

### Cách 1: Bấm đúp vào tệp khởi chạy
Vào thư mục `LEOBOG-AMG65-Mac` (nằm trong thư mục `Downloads` của bạn) và **bấm đúp chuột vào file `start.command`**.

### Cách 2: Chạy từ Terminal
```bash
cd /Volumes/Transcend/choc/campaigns-stack/leobog-amg65-mac
python3 server.py
```
Ứng dụng sẽ tự động mở trang web tại địa chỉ `http://localhost:8080` trên trình duyệt Google Chrome / Edge / Brave.

---

## Hướng Dẫn Kết Nối Bàn Phím
1. Cắm bàn phím LEOBOG AMG65 vào máy Mac bằng cáp USB-C (gạt cần về chế độ cắm dây **Wired Mode**).
2. Mở ứng dụng trên trình duyệt Chrome / Brave / Edge / Arc.
3. Nhấn nút **"Kết Nối Bàn Phím"** ở góc trên bên phải.
4. Một hộp thoại của trình duyệt sẽ hiện ra, chọn **"LEOBOG AMG65"** và nhấn **"Connect"**.
5. Bàn phím sẽ chuyển sang trạng thái xanh **"Đã kết nối"** và bạn có thể tùy chỉnh mọi tính năng ngay lập tức!
