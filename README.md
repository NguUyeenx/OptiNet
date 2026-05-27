# ⚡ OptiNet - Giao diện Dashboard Tối ưu hóa & Chẩn đoán Mạng Cao cấp

**OptiNet** là một công cụ tối ưu hóa hiệu năng mạng toàn diện được xây dựng dưới dạng **Web Dashboard cục bộ cao cấp (Local Web Dashboard)** dành cho hệ điều hành Windows. Với phong cách thiết kế **Glassmorphism Cyberpunk Dark Mode** sắc sảo kết hợp với các hoạt ảnh chuyển động 3D mượt mà, OptiNet chẩn đoán sâu các điểm nghẽn mạng, dọn dẹp cấu hình Wi-Fi cũ rác, tối ưu hóa thông số gói tin MTU, vô hiệu hóa các tiến trình chạy ngầm làm tăng ping và áp dụng các tinh chỉnh TCP/IP chuyên sâu cấp hệ thống chỉ với một cú nhấp chuột.

👉 **Kho lưu trữ chính thức:** [https://github.com/NguUyeenx/OptiNet](https://github.com/NguUyeenx/OptiNet)  
👉 **Được phát triển bởi:** **Nguyễn Trọng Nguyễn** ([Facebook](https://www.facebook.com/nguyentrongnguyen245))

---

## 🎨 Điểm nổi bật & Tính năng cốt lõi

### 1. Phân tích Tốc độ & Độ trễ (Speed & Latency Test)
*   Đo lường băng thông Download/Upload thực tế sử dụng cơ chế kiểm tra tin cậy.
*   Chẩn đoán sâu độ ổn định của đường truyền thông qua hai chỉ số cốt lõi: **Độ dao động trễ (Jitter)** và **Tỷ lệ mất gói tin (Packet Loss)**.

### 2. Bộ Tối ưu hóa DNS (DNS Optimizer & Benchmark)
*   Gửi các gói tin UDP truy vấn trực tiếp thời gian thực đến các DNS Server phổ biến nhất thế giới (**Cloudflare DNS, Google DNS, Quad9 DNS, OpenDNS**) và DNS mặc định của nhà mạng (ISP).
*   Đo lường và xếp hạng tốc độ phân giải của các máy chủ DNS.
*   **Áp dụng 1-Click:** Tự động chuyển đổi DNS hệ thống sang DNS có tốc độ phản hồi nhanh nhất chỉ bằng một nút bấm.

### 3. Tinh chỉnh Cấu hình TCP/IP Stack & MTU chuyên sâu
*   **MTU Sweep Test:** Chạy kiểm tra quét phân mảnh gói tin (DF Ping Sweep) bằng thuật toán tìm kiếm nhị phân để tìm ra kích thước MTU tối ưu nhất cho đường truyền của bạn.
*   **Receive-Side Scaling (RSS) & Receive Segment Coalescing (RSC):** Kích hoạt xử lý mạng đa luồng phân phối đều trên các nhân CPU giúp giảm tải và tối ưu CPU khi tải dữ liệu tốc độ cao.
*   **TCP Auto-Tuning & Congestion Control CUBIC:** Tự động tối ưu kích thước cửa sổ nhận dữ liệu thích ứng tốt nhất với hạ tầng mạng và áp dụng thuật toán kiểm soát nghẽn mạng **CUBIC** hiện đại.
*   Kích hoạt **Explicit Congestion Notification (ECN)** giảm thiểu hiện tượng mất gói tin trên đường truyền.

### 4. Tinh chỉnh Giảm Ping Chơi Game (Gaming Lag Tweak)
*   **Bypass Nagle's Algorithm:** Cấu hình Registry hệ thống thiết lập `TcpAckFrequency = 1` (Gửi phản hồi ACK ngay lập tức) và `TCPNoDelay = 1` (Truyền gói tin tức thời) cho toàn bộ các card mạng, loại bỏ hoàn toàn khoảng trễ đệm 200ms của Windows để giảm ping chơi game online xuống mức thấp nhất.
*   **Tắt Multimedia Network Throttling:** Chỉnh sửa Registry `NetworkThrottlingIndex = 0xFFFFFFFF` và `SystemResponsiveness = 0` giúp vô hiệu hóa cơ chế giới hạn gói tin nền của Windows, dành 100% tài nguyên xử lý mạng cho tác vụ chơi game và xem phim.
*   **Khử nhiễu LLMNR:** Tự động vô hiệu hóa dịch vụ phân giải tên cục bộ LLMNR multicast trong Registry giúp loại bỏ lượng lớn gói tin rác liên tục phát tán gây nghẽn mạng nội bộ.
*   **Làm sạch DNS Cache:** Tự động gọi lệnh `ipconfig /flushdns` để làm mới bộ đệm phân giải tên miền.

### 5. Quản lý Tiến trình Tiêu tốn Băng thông (Bandwidth Hogs Manager)
*   Quét và cắm cờ các tiến trình chạy ngầm đáng ngờ có kết nối TCP đang thiết lập (như SearchHost, Widgets, OneDrive, Teams, v.v.).
*   Cho phép người dùng theo dõi chính xác mã PID và **đóng nhanh tiến trình (Terminate)** trực tiếp trên giao diện để giải phóng băng thông.

### 6. Dọn dẹp cấu hình Wi-Fi lịch sử (Wi-Fi Profile Cleaner)
*   Windows lưu lại toàn bộ các mạng Wi-Fi bạn từng kết nối, tích lũy lâu ngày làm chậm thời gian dò quét tìm kiếm mạng của Windows.
*   Quét và phát hiện toàn bộ danh sách Wi-Fi rác cũ (stale profiles) và hỗ trợ **Dọn dẹp hàng loạt 1-Click** để đưa tốc độ quét Wi-Fi về trạng thái nhanh như mới.

---

## 🛠️ Công nghệ Sử dụng (Zero External Dependencies)

Để đảm bảo khả năng tương thích tuyệt đối và khởi chạy ngay tức thì trên mọi máy tính Windows mà **không cần cài đặt thư viện bên ngoài phức tạp**, OptiNet được xây dựng tối giản và hiệu quả cao:
*   **Frontend:** HTML5 Semantic, Vanilla CSS3 (Sử dụng hệ thống lưới CSS Grid đối xứng, biến đổi 3D Parallax Card Tilt khi di chuột, hoạt ảnh xoay chấm lắc 3D Colliding Pendulum trên nút bấm và thanh tiến trình quét mượt mà), Vanilla JavaScript ES6 (Bất đồng bộ Fetch API giao tiếp thời gian thực).
*   **Backend:** Python 3 Standard Libraries (`http.server` làm Web Server gọn nhẹ, `socket` truy vấn UDP DNS trực tiếp, `winreg` chỉnh sửa cấu hình hệ thống chuyên sâu, `subprocess` chạy các lệnh tối ưu hóa, `threading` xử lý chạy đa luồng tránh nghẽn giao diện).

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy

Để chạy công cụ tối ưu hóa mạng OptiNet, hãy thực hiện theo các bước đơn giản sau:

### Bước 1: Tải mã nguồn (Clone Repository)
Mở cửa sổ Terminal hoặc Command Prompt trên Windows của bạn và chạy lệnh:
```bash
git clone https://github.com/NguUyeenx/OptiNet.git
cd OptiNet
```
*(Hoặc bạn có thể tải file ZIP trực tiếp từ GitHub về máy tính và giải nén ra).*

### Bước 2: Khởi chạy Backend với Quyền Quản trị viên (Administrator)
Do việc áp dụng các tham số mạng cấp cao (như thay đổi DNS, MTU hay viết Registry giảm ping) yêu cầu quyền cấu hình hệ thống, bạn cần khởi chạy máy chủ backend bằng quyền **Administrator**:
1. Nhấn nút `Start` trên bàn phím Windows, tìm cụm từ **PowerShell** hoặc **Command Prompt**.
2. Nhấp chuột phải vào ứng dụng và chọn **"Run as Administrator"** (Chạy với quyền quản trị viên).
3. Di chuyển đến thư mục dự án và khởi chạy máy chủ Python bằng cách gõ:
```powershell
cd "C:\Đường_dẫn_đến_thư_mục_chứa_dự_án\OptiNet"
python server.py
```
> [!NOTE]
> Bạn sẽ thấy thông báo khởi động thành công trong terminal:
> `[System Info] Khởi động server thành công trên cổng 8888.`
> `Đường dẫn local: http://localhost:8888`

### Bước 3: Truy cập Giao diện Web Dashboard
Mở trình duyệt web của bạn và truy cập địa chỉ cục bộ sau:
👉 **[http://localhost:8888](http://localhost:8888)**

---

## ⚡ Hướng dẫn Sử dụng & Trải nghiệm
1.  **Quét chẩn đoán ban đầu:** Nhấp vào nút **Scan & Diagnose** để đo tốc độ mạng hiện tại, đo độ ổn định ping, quét MTU và tiến trình chạy ngầm. Trạng thái của hệ thống sẽ là *System Unoptimized* (Chưa tối ưu) màu vàng.
2.  **Tối ưu hệ thống mạng:** Nhấp vào nút **Optimize Now** để kích hoạt toàn bộ các bước dọn Wi-Fi rác, tắt LLMNR, flush DNS, cấu hình TCP/IP stack tối tân và kích hoạt Gaming Lag Tweak giảm ping. Logs tiến độ chạy thời gian thực sẽ hiển thị trực quan trong ô terminal logs.
3.  **Đo kiểm sau tối ưu hóa:** Nhấp lại vào nút **Scan & Diagnose** một lần nữa để chạy kiểm tra sau tối ưu. Sau khi hoàn tất, hệ thống sẽ chuyển sang trạng thái *System Optimized* màu xanh lục bảo phát sáng và hiển thị một **Bảng so sánh hiệu năng Trước & Sau (Performance Analytics)** vô cùng trực quan hiển thị rõ tỷ lệ tăng tốc độ truyền tải và giảm ping của kết nối!

---

## 🔒 Cam kết An toàn & Bảo mật
*   **Mã nguồn mở 100%:** Mọi câu lệnh và khóa Registry được điều chỉnh đều hiển thị công khai và rõ ràng trong tệp `server.py` và `network_utility.py`, cam kết không có mã độc hay can thiệp phá hoại hệ thống.
*   **Bảo mật cục bộ:** Máy chủ chỉ lắng nghe trên máy tính của bạn (`localhost`), đảm bảo dữ liệu chẩn đoán mạng không bao giờ bị truyền ra bên ngoài.

---

## 📄 Bản quyền & Credit
*   Bản quyền dự án thuộc về **OptiNet** &copy; 2026.
*   Được phát triển và thiết kế bởi: **Nguyễn Trọng Nguyễn**.
*   Các liên kết hỗ trợ và kết nối:
    *   **GitHub Repository:** [https://github.com/NguUyeenx/OptiNet](https://github.com/NguUyeenx/OptiNet)
    *   **Facebook cá nhân:** [https://www.facebook.com/nguyentrongnguyen245](https://www.facebook.com/nguyentrongnguyen245)
