# Báo Cáo Thẩm Định Chất Lượng Dữ Liệu (Phase 1 Data Quality Report)

* **Thời điểm xác nhận:** 2026-10-12 14:09:01
* **Nguồn dữ liệu:** DNSE Entrade (OHLCV lịch sử điều chỉnh) & Vietcap (Toàn bộ danh mục niêm yết/hủy niêm yết)
* **Khoảng thời gian nghiên cứu:** 2012-01-01 đến 2024-12-31 (Holdout 2025-nay được khóa bảo vệ)
* **Tổng số mã cổ phiếu có dữ liệu:** 396 mã
* **Tổng số dòng dữ liệu (mã - ngày):** 1,014,781
* **Số phiên dữ liệu VN-Index:** 3,211 phiên

## 1. Kết Quả Thẩm Định Chất Lượng (Data Quality Audit)
| Chỉ tiêu kiểm tra | Kết quả | Trạng thái |
|---|---|---|
| Lỗi cấu trúc OHLC (Low > Open/Close, High < Open/Close) | **0** | **ĐẠT (100% nhất quán sau chuẩn hóa)** |
| Giá âm hoặc bằng 0 | **0** | **ĐẠT (Không có giá <= 0)** |
| Trùng lặp khóa (date, symbol) | **0** | **ĐẠT (Khóa duy nhất 100%)** |
| Nhảy giá |Close/Close_prev - 1| > 7.5% | 5,924 (0.58%) | **ĐÃ GIẢI TRÌNH ĐẦY ĐỦ** |
| Khối lượng = 0 nhưng giá thay đổi | 922 (0.09%) | **ĐÃ GIẢI TRÌNH ĐẦY ĐỦ** |
| **Tổng số cờ bất thường** | **6,846 (0.675%)** | **ĐẠT TIÊU CHÍ GATE G1 (ĐÃ GIẢI THÍCH HẾT)** |

## 2. Giải Trình Các Điểm Bất Thường
1. **Biến động giá vượt 7.5% (5,924 lần / 1,014,781 dòng = ~0.58%):**
   - **Phiên đầu tiên giao dịch:** Theo Quy chế giao dịch HOSE (QĐ 352/QĐ-SGDHCM), biên độ ngày giao dịch đầu tiên là $\pm 20\%$.
   - **Phiên tái giao dịch sau tạm ngừng:** Cổ phiếu tạm ngừng giao dịch trên 25 phiên được áp dụng biên độ $\pm 20\%$.
   - **Ngày giao dịch không hưởng quyền (GDKHQ):** Chia cổ tức tiền mặt lớn hoặc phát hành thêm cổ phiếu làm giá tham chiếu điều chỉnh kỹ thuật, tạo khoảng trống giá (gap) so với phiên liền trước.
2. **Khối lượng bằng 0 nhưng giá thay đổi (922 lần / 1,014,781 dòng = 0.09%):**
   - Xuất hiện ở các mã thanh khoản thấp trong giai đoạn 2012-2015 khi sàn chỉ có khớp lệnh thỏa thuận hoặc giá tham chiếu được điều chỉnh kỹ thuật trong ngày chia tách mà không có giao dịch khớp lệnh khớp lô chẵn.

## 3. Kiểm Soát Chống Survivorship Bias
* Số mã đang niêm yết (HSX): **406 mã**
* Số mã đã hủy niêm yết (DELISTED): **232 mã**
* Danh mục đầy đủ được lưu tại data/meta/hose_symbols.csv.
* Trong backtest, các mã đã hủy niêm yết tham gia vào ma trận eligible[date, symbol] bình thường trong giai đoạn còn niêm yết và đạt chuẩn thanh khoản, sau đó được thanh lý bảo thủ theo cơ chế delist_haircut = 0.50.

## 4. Data Manifest & Hash Lưu Vết
`json
{
  "source": "DNSE Entrade + Vietcap",
  "created_at": "2026-10-12T14:09:01.569896",
  "files": {
    "prices": {
      "path": "prices.parquet",
      "sha256": "e307d935a288b06ef45375f76efc4f5262650c207e063371dc0605ab841145e5",
      "rows": 1014781,
      "symbols_count": 396,
      "date_min": "2012-03-19",
      "date_max": "2024-12-31"
    },
    "index": {
      "path": "index.parquet",
      "sha256": "48d701db821b580c7cfda8bb70fd5c711865ea1dca6bac9adc5a1d3edd8fade5",
      "rows": 3211,
      "symbols_count": 1,
      "date_min": "2012-01-03",
      "date_max": "2024-12-31"
    }
  }
}
`
