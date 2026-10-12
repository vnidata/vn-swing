"""
Script cập nhật dữ liệu lịch sử từ 2025-01-01 đến Hiện Tại (2026-10-12)
- Tải nến ngày VNINDEX và 396 mã HOSE từ DNSE Entrade
- Nối với dữ liệu lịch sử đã có từ 2012
- Lưu vào data/adjusted/ và data/raw/
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vnswing.data.ingest import fetch_ohlcv_dnse


def update_database_to_present(workers: int = 16):
    adj_dir = ROOT / "data" / "adjusted"
    raw_dir = ROOT / "data" / "raw"
    adj_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"=== CẬP NHẬT DỮ LIỆU ĐẾN HIỆN TẠI ({today_str}) ===")

    # 1. Cập nhật VNINDEX
    print("\n[1/3] Đang cập nhật chỉ số VN-Index...")
    idx_path = adj_dir / "index.parquet"
    if idx_path.exists():
        df_idx_old = pd.read_parquet(idx_path)
        last_idx_date = df_idx_old["date"].max()
        start_date = (last_idx_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f" -> Ngày cuối hiện có của VN-Index: {last_idx_date.date()} -> Tải từ {start_date}...")
    else:
        df_idx_old = pd.DataFrame()
        start_date = "2012-01-01"

    df_idx_new = fetch_ohlcv_dnse("VNINDEX", from_date=start_date, to_date=today_str, is_index=True)
    if df_idx_new is not None and len(df_idx_new) > 0:
        df_idx_comb = pd.concat([df_idx_old, df_idx_new], ignore_index=True)
        df_idx_comb = df_idx_comb.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        df_idx_comb.to_parquet(idx_path, index=False)
        df_idx_comb.to_parquet(raw_dir / "index.parquet", index=False)
        print(f" -> Cập nhật VN-Index thành công: {len(df_idx_comb)} phiên (Mới nhất: {df_idx_comb['date'].max().date()}, Close: {df_idx_comb['close'].iloc[-1]:,.2f})")
    else:
        print(" -> VN-Index đã ở phiên mới nhất hoặc không có dữ liệu mới.")

    # 2. Cập nhật cổ phiếu
    print("\n[2/3] Đang cập nhật 396 mã cổ phiếu HOSE...")
    px_path = adj_dir / "prices.parquet"
    if px_path.exists():
        df_px_old = pd.read_parquet(px_path)
        symbols = sorted(df_px_old["symbol"].unique())
        last_px_date = df_px_old["date"].max()
        start_date_px = (last_px_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f" -> Ngày cuối hiện có của cổ phiếu: {last_px_date.date()} -> Tải từ {start_date_px}...")
    else:
        df_px_old = pd.DataFrame()
        start_date_px = "2012-01-01"
        meta_df = pd.read_csv(ROOT / "data" / "meta" / "hose_symbols.csv")
        symbols = meta_df[meta_df["board"] == "HSX"]["symbol"].tolist()

    t0 = time.time()
    results = []
    failed = []

    def _fetch(sym):
        return sym, fetch_ohlcv_dnse(sym, from_date=start_date_px, to_date=today_str, is_index=False)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch, s): s for s in symbols}
        for future in as_completed(futures):
            sym, df = future.result()
            if df is not None and len(df) > 0:
                results.append(df)
            else:
                failed.append(sym)

    elapsed = time.time() - t0
    print(f" -> Đã tải {len(results)}/{len(symbols)} mã có giao dịch mới trong {elapsed:.1f}s (Không có dữ liệu mới: {len(failed)})")

    if results:
        df_new_all = pd.concat(results, ignore_index=True)
        df_px_comb = pd.concat([df_px_old, df_new_all], ignore_index=True)
        df_px_comb["date"] = pd.to_datetime(df_px_comb["date"])
        df_px_comb = df_px_comb.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
        df_px_comb.to_parquet(px_path, index=False)
        df_px_comb.to_parquet(raw_dir / "prices.parquet", index=False)
        print(f" -> Cập nhật thành công: Tổng cộng {len(df_px_comb):,} dòng dữ liệu.")
        print(f" -> Khung thời gian mới: {df_px_comb['date'].min().date()} đến {df_px_comb['date'].max().date()}")

    print("\n[3/3] Hoàn tất cập nhật cơ sở dữ liệu lên phiên hiện tại!")


if __name__ == "__main__":
    update_database_to_present()
