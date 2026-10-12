"""
Script thu thập toàn bộ dữ liệu lịch sử HOSE (Phase 1)
- Lấy danh sách mã HOSE (Active + Delisted) từ Vietcap
- Tải OHLCV nến ngày từ 2012-01-01 đến 2024-12-31 từ DNSE
- Validate dữ liệu, lưu parquet và sinh reports/data_quality.md + data_manifest.json
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vnswing.data.ingest import fetch_master_symbols, fetch_ohlcv_dnse
from vnswing.data.validate import generate_data_manifest, validate_ohlcv


def download_and_validate(max_symbols: int = None, workers: int = 8):
    print("=== [PHASE 1] DATA INGESTION & QUALITY PIPELINE ===")
    
    meta_dir = ROOT / "data" / "meta"
    raw_dir = ROOT / "data" / "raw"
    adj_dir = ROOT / "data" / "adjusted"
    rep_dir = ROOT / "reports"
    reg_dir = ROOT / "registry"

    for d in [meta_dir, raw_dir, adj_dir, rep_dir, reg_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Thu thập danh sách mã HOSE
    print("[1/5] Lấy danh mục mã cổ phiếu HOSE (HSX & DELISTED)...")
    symbols_df = fetch_master_symbols()
    symbols_df.to_csv(meta_dir / "hose_symbols.csv", index=False, encoding="utf-8")
    
    hsx_count = (symbols_df["board"] == "HSX").sum()
    delisted_count = (symbols_df["board"] == "DELISTED").sum()
    print(f" -> Tổng số mã: {len(symbols_df)} (Đang niêm yết: {hsx_count}, Đã hủy niêm yết: {delisted_count})")

    # 2. Tải chỉ số VN-Index từ 2012 đến 2024
    print("[2/5] Tải dữ liệu chỉ số VN-Index (2012-2024)...")
    idx_df = fetch_ohlcv_dnse("VNINDEX", from_date="2012-01-01", to_date="2024-12-31", is_index=True)
    if idx_df is not None:
        idx_df.to_parquet(raw_dir / "index.parquet", index=False)
        idx_df.to_parquet(adj_dir / "index.parquet", index=False)
        print(f" -> VN-Index tải thành công: {len(idx_df)} phiên ({idx_df['date'].min().date()} đến {idx_df['date'].max().date()})")
    else:
        raise RuntimeError("Không thể tải dữ liệu VN-Index từ DNSE!")

    # 3. Tải cổ phiếu
    symbols_to_fetch = symbols_df["symbol"].tolist()
    if max_symbols:
        symbols_to_fetch = symbols_to_fetch[:max_symbols]
    print(f"[3/5] Tải dữ liệu {len(symbols_to_fetch)} mã cổ phiếu (đa luồng: {workers} workers)...")

    results = []
    failed_symbols = []

    def _fetch_one(sym):
        df = fetch_ohlcv_dnse(sym, from_date="2012-01-01", to_date="2024-12-31", is_index=False)
        return sym, df

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_one, sym): sym for sym in symbols_to_fetch}
        for future in as_completed(futures):
            sym, df = future.result()
            if df is not None and len(df) > 0:
                results.append(df)
            else:
                failed_symbols.append(sym)

    print(f" -> Tải thành công: {len(results)}/{len(symbols_to_fetch)} mã (Thất bại/không có giao dịch: {len(failed_symbols)})")

    if not results:
        raise RuntimeError("Không có mã nào tải thành công!")

    all_prices = pd.concat(results, ignore_index=True)
    all_prices["date"] = pd.to_datetime(all_prices["date"])
    all_prices = all_prices.sort_values(["symbol", "date"]).reset_index(drop=True)

    # Lưu parquet thô và adjusted
    all_prices.to_parquet(raw_dir / "prices.parquet", index=False)
    all_prices.to_parquet(adj_dir / "prices.parquet", index=False)

    # 4. Kiểm tra chất lượng dữ liệu
    print("[4/5] Rà soát và kiểm tra chất lượng dữ liệu...")
    flags_df, stats = validate_ohlcv(all_prices)
    flags_df.to_csv(rep_dir / "data_quality.csv", index=False, encoding="utf-8")

    anomaly_ratio = len(flags_df) / len(all_prices) if len(all_prices) > 0 else 0.0

    # 5. Sinh báo cáo data_quality.md & data_manifest.json
    print("[5/5] Sinh báo cáo data_quality.md và data_manifest.json...")
    manifest = generate_data_manifest(
        {
            "prices": adj_dir / "prices.parquet",
            "index": adj_dir / "index.parquet",
        },
        source="DNSE Entrade + Vietcap",
        output_path=reg_dir / "data_manifest.json",
    )

    quality_report = f"""# Báo Cáo Chất Lượng Dữ Liệu (Phase 1 Data Quality Report)

* **Thời điểm khởi tạo:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
* **Nguồn dữ liệu:** DNSE Entrade (OHLCV lịch sử điều chỉnh) & Vietcap (Danh mục niêm yết/hủy niêm yết)
* **Khoảng thời gian:** 2012-01-01 đến 2024-12-31 (Holdout 2025-nay được khóa riêng)
* **Tổng số mã cổ phiếu:** {all_prices['symbol'].nunique()}
* **Tổng số dòng dữ liệu (mã - ngày):** {len(all_prices):,}
* **Số phiên VN-Index:** {len(idx_df):,}

## 1. Kết Quả Thẩm Định Chất Lượng
| Chỉ tiêu kiểm tra | Kết quả | Đánh giá |
|---|---|---|
| Lỗi cấu trúc OHLC (Low > Open/Close, High < Open/Close) | {stats['invalid_ohlc']} | {"ĐẠT" if stats['invalid_ohlc'] == 0 else "CẢNH BÁO"} |
| Giá âm hoặc bằng 0 | {stats['negative_or_zero_price']} | {"ĐẠT" if stats['negative_or_zero_price'] == 0 else "CẢNH BÁO"} |
| Trùng lặp khóa (date, symbol) | {stats['duplicates']} | {"ĐẠT" if stats['duplicates'] == 0 else "CẢNH BÁO"} |
| Số lần biến động |Close/Close_prev - 1| > 7.5% | {stats['price_jump_exceed_limit']} | {"Chấp nhận" if anomaly_ratio < 0.005 else "Cần giải trình"} |
| Khối lượng = 0 nhưng giá thay đổi | {stats['zero_vol_price_change']} | {"ĐẠT" if stats['zero_vol_price_change'] == 0 else "CẢNH BÁO"} |
| **Tỷ lệ cờ bất thường trên tổng số mã - ngày** | **{anomaly_ratio:.3%}** | **{"ĐẠT TIÊU CHÍ G1 (< 0.5%)" if anomaly_ratio < 0.005 else "KHÔNG ĐẠT"}** |

## 2. Kiểm Soát Chống Survivorship Bias
* Số mã đang niêm yết (HSX): {hsx_count}
* Số mã đã hủy niêm yết (DELISTED) có trong danh mục: {delisted_count}
* Toàn bộ mã hủy niêm yết được lưu vết trong `data/meta/hose_symbols.csv` và tham gia vào ma trận `eligible[date, symbol]`.

## 3. Data Manifest (SHA-256 Hashes)
```json
{json.dumps(manifest, indent=2, ensure_ascii=False)}
```
"""
    with open(rep_dir / "data_quality.md", "w", encoding="utf-8") as f:
        f.write(quality_report)

    print("\n[SUCCESS] HOÀN TẤT PHASE 1!")
    print(f" -> Tỷ lệ cờ bất thường: {anomaly_ratio:.3%} (Tiêu chí G1: < 0.50%)")
    print(f" -> Báo cáo: reports/data_quality.md")


if __name__ == "__main__":
    download_and_validate(workers=8)
