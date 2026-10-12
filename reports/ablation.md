# Báo Cáo Ma Trận Đối Chứng (Ablation Matrix Report)

* **Thời điểm chạy:** 2026-10-12 14:15:08
* **Khoảng thời gian OOS:** 2015-01-01 đến 2024-12-31 (10 năm walk-forward OOS)
* **Tổng số thử nghiệm tích lũy (N cho DSR):** 100 trials
* **Chuẩn chi phí:** Mua 0.30%, Bán 0.40% (bao gồm thuế 0.1% và trượt giá)

## 1. Bảng Hiệu Suất 11 Biến Thể Đối Chứng

| ID | Biến Thể | CAGR Ròng | Sharpe OOS | MaxDD | Calmar | Số Lệnh | Sharpe Dương | DSR (N=100) | Phí 1.5x Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| **B0** | VN-Index Buy & Hold | 8.9% | 0.29 | -45.3% | 0.20 | 0 | - | - | - |
| **B1** | Equal-weight Universe | 0.7% | -0.07 | -61.5% | 0.01 | 0 | - | - | - |
| **B2** | Trend MA20/50 Benchmark | 103.7% | 2.91 | -17.8% | 5.84 | - | - | - | - |
| **A1** | Breakout thuần (Lõi) | 0.8% | **-0.06** | -55.4% | 0.01 | 468 | 40% | **0.00** | -0.11 |
| **A2** | A1 + Regime VN-Index | 2.3% | **0.00** | -61.4% | 0.04 | 348 | 50% | **0.00** | -0.18 |
| **A3** | A2 + Volume Filter | -1.4% | **-0.18** | -64.0% | -0.02 | 357 | 40% | **0.00** | -0.26 |
| **A4** | A3 + CLV Filter | -5.3% | **-0.36** | -74.5% | -0.07 | 368 | 40% | **0.00** | -0.29 |
| **A5** | A4 + RS Rank Filter | -0.7% | **-0.15** | -63.5% | -0.01 | 372 | 40% | **0.00** | -0.23 |
| **A6** | A5 + Chandelier ATR Stop (Full Breakout) | -1.1% | **-0.18** | -53.0% | -0.02 | 373 | 50% | **0.00** | -0.19 |
| **P1** | Pullback thuần (Lõi) | -3.7% | **-0.29** | -64.2% | -0.06 | 644 | 40% | **0.00** | -0.24 |
| **P2** | Full Pullback (+ Regime + Vol + CLV + RS + Stop) | -1.3% | **-0.30** | -41.2% | -0.03 | 337 | 30% | **0.00** | -0.51 |

## 2. Đối Chiếu Tiêu Chí Vượt Gate G3 (Gate G3 Audit)

Tiêu chuẩn định lượng cố định:
1. **Sharpe OOS > VN-Index B&H (0.29):** Sau chi phí thực tế.
2. **Tỷ lệ năm OOS có Sharpe dương $\ge 60\%$.**
3. **DSR $\ge 0.90$ (với N cộng dồn=100).**
4. **Tổng số lệnh OOS ghép lại $\ge 150$ lệnh.**
5. **Kết quả không đổi dấu khi chi phí tăng $+50\%$ (phí $\times 1.5$).**

### Đánh giá từng biến thể Breakout:
* **A1 (Breakout Thuần):** Nền tảng swing trading.
* **A2 (+Regime):** Đóng góp của bộ lọc xu hướng thị trường VN-Index.
* **A3 (+Volume):** Đóng góp của lọc dòng tiền phiên bùng nổ.
* **A4 (+CLV):** Đóng góp vị trí đóng cửa nến.
* **A5 (+RS):** Đóng góp của phân vị Relative Strength dẫn dắt.
* **A6 (Full Breakout):** Bộ lọc đầy đủ kèm Trailing Stop ATR.
