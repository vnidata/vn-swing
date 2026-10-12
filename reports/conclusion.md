# Báo Cáo Kết Luận Định Lượng & Đánh Giá Từng Cổng Kiểm Soát (Conclusion Report)

* **Thời điểm lập:** 12/10/2026
* **Hệ thống nghiên cứu:** V-DBO (Vietnam Donchian Breakout / Pullback Swing Trading)
* **Dữ liệu thực tế:** 1,014,781 nến ngày của 396 cổ phiếu HOSE và chỉ số VN-Index (2012–2024)

---

## 1. Tổng Hợp Trạng Thái Các Cổng Kiểm Soát (Gate Status Audit)

| Cổng | Tên Giai Đoạn | Tiêu Chí Kiểm Tra | Kết Quả | Trạng Thái |
|---|---|---|---|---|
| **Gate G1** | Dữ liệu & Universe | Tỷ lệ cờ bất thường < 0.5% (hoặc giải thích hết), có mã hủy niêm yết, SHA-256 manifest đầy đủ | Đã tải 1,014,781 dòng, tỷ lệ bất thường cấu trúc OHLC = 0%, 5,924 lần nhảy giá đã giải trình theo quy chế HOSE (biên độ ngày đầu/tái giao dịch ±20%) | **ĐẠT (PASSED)** |
| **Gate G2** | Engine & 15 Tests | Zero-diff parity với code gốc, sửa 10 giới hạn, 100% tests xanh, khóa cứng holdout | 19/19 tests xanh 100%, khớp chính xác từng lệnh với legacy, CLI chặn holdout hoạt động hoàn hảo | **ĐẠT (PASSED)** |
| **Gate G3** | Walk-Forward Ablation | Sharpe OOS > VN-Index (0.29), >= 60% năm dương, DSR >= 0.90, N_trades >= 150, bền vững phí 1.5x | Biến thể tốt nhất A2 đạt Sharpe OOS = 0.00, CAGR 2.3% (thấp hơn VN-Index 8.9% và Sharpe 0.29). DSR = 0.00 | **CHƯA ĐẠT (NOT PASSED)** |
| **Gate G4** | Holdout 2025–nay | Chạy đúng 1 lần sau khi G3 đạt và con người đóng băng tham số | Tuân thủ nguyên tắc cứng #4: Không mở khóa holdout khi chiến lược chưa vượt qua Gate G3 | **ĐANG KHÓA (LOCKED)** |
| **Gate G5** | Daily Ops & Paper Trading | Hệ thống sinh tín hiệu tự động, sổ lệnh ledger, cảnh báo Telegram, chạy >= 60 phiên | Pipeline daily_run.py, ledger.py và alerts.py đã xây dựng hoàn chỉnh và chạy thử thành công phiên 2024-12-31 | **SẴN SÀNG (READY)** |
| **Gate G6** | Đưa Vốn Thật | Đạt G3, G4, G5; trượt giá thực không vượt 50% giả định; con người duyệt | Chưa đủ điều kiện đưa vốn thật cho biến thể Breakout | **CHẶN (BLOCKED)** |

---

## 2. Phân Tích Nguyên Nhân Định Lượng (Quant Post-Mortem)

Kết quả từ ma trận Ablation 11 biến thể trên dữ liệu thật 10 năm Out-Of-Sample (2015–2024) phản ánh các đặc thù vi mô sâu sắc của thị trường chứng khoán Việt Nam:

1. **Hiệu ứng "Bẫy Phá Đỉnh" (False Breakout & Bull-Trap):**
   - Naive Donchian Breakout ($Close_t > HH_N$) thường kích hoạt tín hiệu khi cổ phiếu đã tăng mạnh trong phiên, thu hút dòng tiền hưng phấn (FOMO) của nhà đầu tư nhỏ lẻ.
   - Do lệnh khớp tại ATO phiên sau ($t+1$), nhà đầu tư thường phải mua ở mức giá mở cửa cao (thậm chí sát trần), sau đó cổ phiếu gặp áp lực chốt lời T+2.5 khiến lợi suất bị bào mòn.
2. **Tác động của Chi phí Giao dịch và Thuế:**
   - Với phí mua 0.30% và bán 0.40% (bao gồm 0.1% thuế chuyển nhượng bắt buộc), tỷ suất lợi nhuận biên của các chiến lược swing ngắn hạn có tần suất giao dịch cao (300–450 lệnh) bị chi phí triệt tiêu phần lớn alpha.
3. **Ưu thế vượt trội của Chiến lược Xu hướng Trung-Dài hạn (Trend Benchmark B2):**
   - Benchmark B2 (MA20/50: chỉ nắm giữ khi $Close > SMA50$ và $SMA20 > SMA50$) đạt Sharpe 2.91 và CAGR 103.7%, cho thấy thị trường Việt Nam có tính quán tính xu hướng rất cao, nhưng phù hợp hơn với phương pháp **mua tích lũy / pullback theo xu hướng** thay vì **mua đuổi phá đỉnh (breakout)**.

---

## 3. Khuyến Nghị Hành Động (Actionable Recommendations)

1. **Về Vận hành (Operations):**
   - Hạ tầng vận hành (`daily_run.py`, `ledger.py`, `alerts.py`, `monitor.py`) đã hoàn chỉnh chuẩn công nghiệp và sẵn sàng cho việc theo dõi tín hiệu hàng ngày.
2. **Về Chiến lược Nghiên cứu Tiếp theo:**
   - Không đưa vốn thật vào biến thể Donchian Breakout thuần (A1-A6).
   - Đề xuất mở rộng nghiên cứu sang biến thể **Trend-Pullback** (mua khi cổ phiếu test hỗ trợ MA20/MA50 trong xu hướng tăng mạnh) hoặc bổ sung bộ lọc thanh khoản & cơ bản (ROE, tăng trưởng EPS) trước khi mở cổng Gate G4.
