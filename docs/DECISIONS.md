# Nhật Ký Quyết Định Kiến Trúc & Phương Pháp Luận (ADR)

Mọi quyết định quan trọng về kiến trúc hệ thống, xử lý dữ liệu và phương pháp định lượng được ghi lại tại đây kèm lý do và chữ ký đồng thuận.

---

## ADR-001: Lựa chọn Kiến trúc Module Hóa & Định Dạng Dữ Liệu Parquet
* **Ngày:** 12/10/2026
* **Bối cảnh:** File nguyên mẫu `legacy/vn_donchian_wf.py` viết theo dạng script đơn khối (monolithic), khó mở rộng và kiểm thử đơn vị.
* **Quyết định:** Tách thành package `vnswing` với các module chuyên trách (`data`, `features`, `signals`, `backtest`, `research`, `ops`). Toàn bộ dữ liệu giá và chỉ số lưu dưới định dạng Apache Parquet (Snappy compression) để tối ưu tốc độ đọc/ghi cột và nén dung lượng.
* **Hậu quả:** Tăng tính tái sử dụng, cho phép viết 15 test cases độc lập và dễ dàng tích hợp CLI.

---

## ADR-002: Khóa Cứng Phân Vùng Holdout (2025-01-01 đến nay)
* **Ngày:** 12/10/2026
* **Bối cảnh:** Nguy cơ overfitting và p-hacking khi nhà nghiên cứu liên tục tinh chỉnh tham số trên toàn bộ dữ liệu.
* **Quyết định:** Toàn bộ dữ liệu từ `2025-01-01` trở đi bị khóa cứng ở cấp Engine/CLI (`--holdout-start 2025-01-01`). Mọi lệnh cố tình chạy qua ngày này sẽ ném ngoại lệ chặn lại, trừ khi có cờ tường minh `--unlock-holdout` và chỉ chạy duy nhất 1 lần tại Gate G4 sau khi người dùng ký duyệt đóng băng tham số.
* **Hậu quả:** Đảm bảo tính khách quan tuyệt đối của giai đoạn Out-Of-Sample cuối cùng.

---

## ADR-003: Xử Lý Mã Hủy Niêm Yết / Đình Chỉ (Delisting Haircut)
* **Ngày:** 12/10/2026
* **Bối cảnh:** Trong code gốc, khi dữ liệu mã kết thúc bằng NaN (hủy niêm yết), vị thế bị giữ nguyên giá đóng cửa cuối cùng mãi mãi, làm sai lệch hiệu suất danh mục.
* **Quyết định:** Thiết lập quy tắc thanh lý bắt buộc: nếu mã biến mất khỏi bảng giá mà không có giao dịch, ghi giảm giá trị theo tỷ lệ `delist_haircut = 0.50` (mất 50% giá trị tại ngày đóng cửa cuối) và thu hồi tiền mặt còn lại về danh mục.
* **Hậu quả:** Phản ánh rủi ro thanh lý cổ phiếu hủy niêm yết sát với thực tế thị trường Việt Nam.

---

## ADR-004: Mô Hình Khớp Lệnh ATO & Quy Tắc Giữ Lệnh Bảo Thủ
* **Ngày:** 12/10/2026
* **Bối cảnh:** Thực tế thị trường Việt Nam cho phép bán cổ phiếu từ chiều ngày T+2, tuy nhiên khớp lệnh trong phiên chiều có thể gặp rủi ro biến động giá nhanh hoặc trượt giá lớn.
* **Quyết định:** Thiết kế hệ thống sinh tín hiệu tại phiên đóng cửa $t$ và thực hiện lệnh tại phiên ATO $t+1$. Quy định thời gian giữ tối thiểu `min_hold = 3` phiên (bán tại ATO phiên $t+3$) để đảm bảo tính bảo thủ cao nhất và hoàn toàn triệt tiêu rủi ro sai sót giờ thanh toán.
