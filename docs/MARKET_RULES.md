# Quy Định Và Cơ Chế Thị Trường Chứng Khoán Việt Nam (HOSE)

Tài liệu này chuẩn hóa toàn bộ các ràng buộc pháp lý, quy chế giao dịch và cấu trúc vi mô thị trường áp dụng cho hệ thống giao dịch định lượng swing **V-DBO**.

---

## 1. Phạm Vi Sàn Giao Dịch & Biên Độ Dao Động

* **Sàn giao dịch áp dụng:** Sở Giao dịch Chứng khoán TP. Hồ Chí Minh (HOSE).
* **Mã bị loại trừ:** Toàn bộ cổ phiếu sàn HNX (biên độ $\pm 10\%$) và sàn UPCoM (biên độ $\pm 15\%$) bị loại khỏi universe ở phiên bản này nhằm đảm bảo tính đồng nhất về cấu trúc vi mô, thanh khoản và kiểm soát rủi ro.
* **Biên độ dao động giá hàng ngày:**
  * Cổ phiếu thông thường: $\pm 7.0\%$ so với giá tham chiếu (giá đóng cửa phiên liền trước).
  * Cổ phiếu ngày đầu tiên giao dịch hoặc sau khi tạm ngừng giao dịch trên 25 phiên: $\pm 20.0\%$.
  * *Nguồn quy chế:* Quyết định số 352/QĐ-SGDHCM về Quy chế giao dịch chứng khoán tại HOSE; Thông tư 120/2020/TT-BTC.

---

## 2. Chu Kỳ Thanh Toán & Thời Điểm Hàng Về

* **Chu kỳ hiện hành:** $T+2$ (Chính thức rút ngắn từ chiều ngày $T+2$ từ ngày 29/08/2022 theo Quyết định số 109/QĐ-VSD).
* **Thời điểm được phép bán:** Chứng khoán về tài khoản của nhà đầu tư trước 13:00 ngày $T+2$, do đó nhà đầu tư có thể đặt lệnh bán từ phiên khớp lệnh chiều ngày $T+2$ (thực tế được gọi là "T+2.5").
* **Mô hình hóa bảo thủ trong Engine:**
  * Giữ nguyên giả định bảo thủ: vị thế giữ tối thiểu `min_hold = 3` phiên và chỉ bán tại giá mở cửa (ATO) ngày $t+3$. Điều này loại bỏ hoàn toàn rủi ro bán chậm phiên chiều và sai số thời gian thực thi.
  * *Nguồn quy chế:* Quyết định 109/QĐ-VSD ngày 19/08/2022 của Trung tâm Lưu ký Chứng khoán Việt Nam (VSDC).

---

## 3. Lô Giao Dịch & Bước Giá (Tick Size)

* **Lô giao dịch khớp lệnh:** Lô chẵn 100 cổ phiếu (áp dụng từ ngày 04/01/2021 theo Thông báo của HOSE). Toàn bộ khối lượng lệnh tính toán phải làm tròn xuống bội số của 100 (`floor(sh / 100) * 100`).
* **Bước giá (Tick Size) trên HOSE:**
  * Giá $< 10,000$ VND: Bước giá 10 VND.
  * Giá từ $10,000$ VND đến $49,950$ VND: Bước giá 50 VND.
  * Giá $\ge 50,000$ VND: Bước giá 100 VND.
* *Nguồn quy chế:* Điều 13, Quy chế giao dịch chứng khoán HOSE.

---

## 4. Cơ Chế Khớp Lệnh & Thực Thi Phiên ATO

* **Thời gian giao dịch:**
  * 09:00 – 09:15: Khớp lệnh định kỳ mở cửa (ATO).
  * 09:15 – 11:30: Khớp lệnh liên tục phiên sáng.
  * 13:00 – 14:30: Khớp lệnh liên tục phiên chiều.
  * 14:30 – 14:45: Khớp lệnh định kỳ đóng cửa (ATC).
* **Quy tắc thực thi trong mô hình:**
  * Tín hiệu sinh tại giá đóng cửa phiên $t$ (sau khi kết thúc ATC lúc 14:45).
  * Lệnh thực tế khớp tại giá mở cửa (Open / giá khớp ATO) của phiên $t+1$.
  * **Trần/Sàn (Limit Up / Limit Down):**
    * Nếu giá mở cửa phiên $t+1 \ge \text{Close}_t \times (1 + 0.07 - 0.002)$ (mở cửa ở giá trần $\to$ dư mua trần không có người bán): Không thể mua được. Tín hiệu mua bị hủy bỏ hoặc chuyển thành trạng thái chờ.
    * Nếu giá mở cửa phiên $t+1 \le \text{Close}_t \times (1 - 0.07 + 0.002)$ (mở cửa ở giá sàn $\to$ trắng bên mua): Không thể bán được. Lệnh thoát tiếp tục duy trì trạng thái chờ sang các phiên tiếp theo.
  * **Tỷ lệ khớp ATO (`ato_fill_prob`):** Mô phỏng xác suất khớp $< 100\%$ trong điều kiện thanh khoản mỏng hoặc giá mở cửa biến động mạnh.

---

## 5. Thuế, Phí & Chi Phí Giao Dịch

* **Phí mua (ước tính chuẩn 0.30%):**
  * Phí môi giới CTCK: 0.10% – 0.15% (tùy CTCK và gói dịch vụ).
  * Phí dịch vụ giao dịch nộp Sở/VSDC: ~0.027%.
  * Trượt giá (Slippage) ước lượng: 0.12% – 0.15%.
* **Phí bán (ước tính chuẩn 0.40%):**
  * Thuế TNCN từ chuyển nhượng chứng khoán: **0.10% trên tổng giá trị bán** (Khoản 2 Điều 13 Thông tư 111/2013/TT-BTC).
  * Phí môi giới CTCK: 0.10% – 0.15%.
  * Phí nộp Sở/VSDC: ~0.027%.
  * Trượt giá ước lượng: 0.12% – 0.15%.
* **Kiểm định độ nhạy:** Toàn bộ backtest và walk-forward phải chạy kèm kịch bản chi phí tăng $+50\%$ (mua 0.45%, bán 0.60%) và $+100\%$ (mua 0.60%, bán 0.80%).

---

## 6. Mốc Thời Gian & Sự Kiện Thị Trường Lớn

* **01/2021:** HOSE nâng lô giao dịch từ 10 lên 100 cổ phiếu.
* **08/2022:** Rút ngắn chu kỳ thanh toán xuống $T+2$ (chiều T+2 được bán).
* **11/2024:** Thông tư 68/2024/TT-BTC có hiệu lực bỏ ký quỹ 100% trước giao dịch đối với NĐT nước ngoài (Non-prefunding).
* **2025 – 2026:** Vận hành hệ thống công nghệ thông tin mới (KRX) và lộ trình nâng hạng FTSE Secondary Emerging Market (dự kiến hiệu lực tháng 09/2026).
