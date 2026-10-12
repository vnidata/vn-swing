# Các Vấn Đề Cần Làm Rõ (Open Questions)

Theo nguyên tắc cứng #0: Nếu thiếu dữ liệu hoặc chưa chắc chắn, ghi lại tại đây thay vì tự ý giả định.

---

### OQ-001: Cấu hình Kênh Cảnh Báo Telegram
* **Mô tả:** Để gửi bản tin tín hiệu tự động lúc 16:15 hàng ngày, hệ thống cần `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID`.
* **Trạng thái:** Chờ người dùng cung cấp qua biến môi trường. Trong thời gian chờ, hệ thống tự động lưu file CSV tại `reports/daily/` và in bảng tóm tắt ra Terminal.
* **Thời hạn quyết định:** Trước khi kích hoạt Phase 5 (Daily Operations).

---

### OQ-002: Nguồn Dữ Liệu Lịch Sử Cho Mã Hủy Niêm Yết
* **Mô tả:** Thư viện `vnstock` hỗ trợ rất tốt dữ liệu các mã đang niêm yết hiện hành, nhưng dữ liệu của các mã đã hủy niêm yết trong quá khứ (ví dụ: ROS, FLC, KGO,...) cần được kiểm tra xem có đầy đủ OHLCV lịch sử trước ngày hủy niêm yết hay không.
* **Giải pháp dự phòng:** Crawl danh sách quyết định hủy niêm yết từ website HOSE và lưu vào `data/meta/hose_delisted.csv`.
* **Trạng thái:** Đang xác minh trong Phase 1.

---

### OQ-003: Biểu Phí Môi Giới Cụ Thể Của Tài Khoản Người Dùng
* **Mô tả:** Mức phí mặc định đang để là Mua 0.30%, Bán 0.40% (đã bao gồm thuế 0.1% và trượt giá). Nếu người dùng giao dịch ở các CTCK có chính sách Zero-Fee (TCBS, DNSE, VPS gói miễn phí), chi phí có thể giảm xuống Mua 0.15%, Bán 0.25%.
* **Trạng thái:** Sử dụng mức chuẩn bảo thủ (0.30% / 0.40%) và kiểm định độ nhạy $+50\%$ và $+100\%$.
