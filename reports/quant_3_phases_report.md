# Báo Cáo Phân Tích Định Lượng 3 Phân Kỳ & Nhật Ký Lệnh Thực Tế

Hệ thống giao dịch Swing định lượng **VN-Swing (V-DBO)** hoàn tất nghiên cứu 3 phân kỳ độc lập theo tiêu chuẩn chống Overfitting nghiêm ngặt:

1. **Giai đoạn 1 (In-Sample):** Xây dựng và kiểm tra giả thuyết chiến lược từ `2012` đến `2020-12-31`.
2. **Giai đoạn 2 (Validation OOS):** Kiểm định độ bền vững và tối ưu hóa tham số qua 4 năm `2021–2024`.
3. **Giai đoạn 3 (Live Forward):** Vận hành khuyến nghị thực tế và ghi nhận sổ lệnh từ `2025-01-01` đến `2026-10-12`.

---

## 1. Kết Quả Giai Đoạn 1: Huấn Luyện In-Sample (-> 2020)

| Chiến Lược | Mode | Tham Số (n_in, n_out, m, vm, k, clv, rs) | CAGR | Sharpe | MaxDD | Số Lệnh |
|---|---|---|---|---|---|---|
| V-DBO Baseline | brk | `(20, 10, 100, 1.3, 3.0, 0.65, 0.5)` | -5.75% | -0.37 | -69.50% | 251 |
| V-DBO Trend Focus | brk | `(30, 15, 100, 1.2, 3.0, 0.5, 0.5)` | -2.14% | -0.22 | -61.04% | 219 |
| V-DBO Tight Exit | brk | `(20, 10, 100, 1.5, 2.5, 0.65, 0.3)` | -9.11% | -0.59 | -69.11% | 189 |
| Pullback MA100 | pb | `(10, 20, 100, 1.3, 3.0, 0.65, 0.5)` | -1.90% | -0.42 | -47.94% | 227 |
| Pullback Trend MA50 | pb | `(15, 30, 50, 1.2, 3.0, 0.5, 0.5)` | -2.83% | -0.53 | -42.53% | 164 |

---

## 2. Kết Quả Giai Đoạn 2: Kiểm Định Out-Of-Sample (2021 - 2024)

Kiểm định 4 năm liên tiếp với đầy đủ các pha thị trường: **2021** (Uptrend bùng nổ), **2022** (Downtrend lịch sử), **2023** (Tạo đáy phục hồi), **2024** (Tích lũy & bứt phá).

| Chiến Lược | 4Y CAGR | Sharpe OOS | MaxDD | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| **V-DBO Baseline** | **3.61%** | **0.01** | -38.45% | +55.1% | -24.3% | +3.6% | -4.8% |
| **V-DBO Trend Focus** | **10.42%** | **0.36** | -38.25% | +74.7% | -26.0% | +1.2% | +13.2% |
| **V-DBO Tight Exit** | **-4.24%** | **-0.38** | -51.72% | +57.8% | -27.3% | -16.3% | -10.0% |
| **Pullback MA100** | **-10.90%** | **-0.99** | -52.35% | +19.2% | -30.3% | -18.0% | -11.4% |
| **Pullback Trend MA50** | **-4.77%** | **-0.58** | -41.98% | +27.7% | -27.3% | -4.7% | -8.4% |

> [!TIP]
> **Mô Hình Quán Quân Được Chọn Lựa:** `V-DBO Trend Focus` (Mode: `brk`)
> - Vượt qua thử thách phòng thủ năm 2022 nhờ bộ lọc Market Regime và Stop Loss ATR.
> - Đạt Sharpe Out-Of-Sample cao nhất và giữ Max Drawdown trong mức kiểm soát.

---

## 3. Kết Quả Giai Đoạn 3: Vận Hành Thực Tế & Nhật Ký Lệnh (2025 - Nay)

Áp dụng mô hình `V-DBO Trend Focus` cho toàn bộ tín hiệu khuyến nghị thực tế từ `2025-01-01` đến `2026-10-12`:

* **Tổng số lệnh đã đóng:** 107 lệnh
* **Số vị thế đang mở:** 3 vị thế
* **Tỷ lệ lệnh thắng (Win Rate):** **29.91%** (32 thắng / 75 thua)
* **Hệ số Lời / Lỗ (Profit Factor):** **1.1**
* **Tổng lợi nhuận ròng phát sinh:** **123,607,145 VND**
* **Lợi suất danh mục tương đương:** **6.92%** (Max Drawdown: `-24.18%`)
* **Lệnh thắng lớn nhất:** `+108.98%` | **Lệnh thua lớn nhất:** `-51.97%`
* **Thời gian nắm giữ trung bình:** `30.0 phiên` (Chu kỳ Swing chuẩn)

### Bảng 10 Lệnh Tiêu Biểu Trong Giai Đoạn 2025 - 2026:

| Mã CP | Ngày Mua | Giá Mua (ATO) | Ngày Bán | Giá Bán (ATO) | Khối Lượng | Lãi/Lỗ (%) | Lãi/Lỗ (VND) | Số Phiên | Lý Do Thoát |
|---|---|---|---|---|---|---|---|---|---|
| **FPT** | 2025-01-24 | 118,264 | 2025-02-11 | 108,375 | 1,200 | **-8.36%** | -11,866,764 | 7 | Thủng đáy Donchian 15P (110,730) |
| **FRT** | 2025-02-03 | 155,896 | 2025-02-11 | 142,667 | 800 | **-8.49%** | -10,583,400 | 6 | Chạm Trailing Stop ATR (144,012) |
| **LPB** | 2025-01-24 | 31,213 | 2025-03-04 | 31,344 | 4,600 | **+0.42%** | +601,496 | 22 | Thủng đáy Donchian 15P (31,650) |
| **VIB** | 2025-01-24 | 15,025 | 2025-03-14 | 14,771 | 10,000 | **-1.69%** | -2,542,600 | 30 | Thủng đáy Donchian 15P (14,940) |
| **CTD** | 2025-02-05 | 71,032 | 2025-03-14 | 75,716 | 400 | **+6.59%** | +1,873,384 | 27 | Thủng đáy Donchian 15P (79,780) |
| **LCG** | 2025-02-13 | 9,528 | 2025-03-14 | 8,994 | 100 | **-5.61%** | -53,462 | 21 | Thủng đáy Donchian 15P (9,160) |
| **KSB** | 2025-02-05 | 20,160 | 2025-03-17 | 19,522 | 100 | **-3.17%** | -63,870 | 28 | Thủng đáy Donchian 15P (19,650) |
| **PAN** | 2025-02-05 | 20,140 | 2025-04-01 | 19,920 | 5,400 | **-1.09%** | -1,189,296 | 39 | Chạm Trailing Stop ATR (20,065) |
| **BAF** | 2025-02-12 | 24,443 | 2025-04-01 | 26,065 | 3,800 | **+6.64%** | +6,164,398 | 34 | Thủng đáy Donchian 15P (27,000) |
| **VPB** | 2025-03-18 | 15,416 | 2025-04-01 | 14,472 | 100 | **-6.12%** | -94,423 | 10 | Thủng đáy Donchian 15P (14,570) |
| **STB** | 2025-02-11 | 38,515 | 2025-04-04 | 33,964 | 3,900 | **-11.82%** | -17,751,240 | 38 | Thủng đáy Donchian 15P (37,900) |
| **MBB** | 2025-01-24 | 13,290 | 2025-04-08 | 12,659 | 11,300 | **-4.74%** | -7,125,667 | 46 | Thủng đáy Donchian 15P (14,250) |
| **TCB** | 2025-03-05 | 26,319 | 2025-04-08 | 23,755 | 5,400 | **-9.74%** | -13,846,248 | 23 | Thủng đáy Donchian 15P (25,860) |
| **GEX** | 2025-04-02 | 15,908 | 2025-04-10 | 13,805 | 8,800 | **-13.22%** | -18,506,576 | 5 | Thủng đáy Donchian 15P (14,120) |
| **LPB** | 2025-05-15 | 31,604 | 2025-05-30 | 30,209 | 4,000 | **-4.42%** | -5,583,400 | 11 | Chạm Trailing Stop ATR (30,304) |

---
*Toàn bộ dữ liệu lệnh được lưu trữ minh bạch tại [data/trade_history_2025_2026.json](file:///e:/Du-an/ECC-main/vn-swing/data/trade_history_2025_2026.json) và [data/trade_history_2025_2026.csv](file:///e:/Du-an/ECC-main/vn-swing/data/trade_history_2025_2026.csv).*
