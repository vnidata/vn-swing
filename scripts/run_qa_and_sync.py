"""Script tổng hợp cho Subagent QA & Data Engineer:
1. Đồng bộ và cập nhật dữ liệu thị trường mới nhất
2. Kiểm định tính toàn vẹn dữ liệu (Data Integrity Audit)
3. Chạy toàn bộ bộ kiểm thử tính năng (Pytest Regression Suite)
4. Xác thực payload Web Dashboard (web/data/signals.json & web/index.html)
5. Xuất báo cáo tóm tắt tình trạng hệ thống
"""

import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

# Thiết lập UTF-8 encoding an toàn trên Windows console
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent


def audit_market_data():
    print("\n--- [BƯỚC 1/4] KIỂM ĐỊNH TÍNH TOÀN VẸN DỮ LIỆU THỊ TRƯỜNG ---")
    adj_dir = ROOT / "data" / "adjusted"
    px_path = adj_dir / "prices.parquet"
    idx_path = adj_dir / "index.parquet"

    if not px_path.exists() or not idx_path.exists():
        print(f"[LỖI] Thiếu file dữ liệu: {px_path} hoặc {idx_path}")
        return False, {}

    df_px = pd.read_parquet(px_path)
    df_idx = pd.read_parquet(idx_path)

    # 1. Kiểm tra ngày
    max_px_date = str(pd.to_datetime(df_px["date"]).max().date())
    min_px_date = str(pd.to_datetime(df_px["date"]).min().date())
    max_idx_date = str(pd.to_datetime(df_idx["date"]).max().date())
    min_idx_date = str(pd.to_datetime(df_idx["date"]).min().date())

    symbols = df_px["symbol"].unique()
    total_rows = len(df_px)

    # 2. Kiểm tra Null / NaN
    null_cols = df_px[["open", "high", "low", "close", "volume"]].isna().sum()
    has_nulls = null_cols.sum() > 0

    # 3. Kiểm tra logic giá
    invalid_prices = (
        (df_px["close"] <= 0)
        | (df_px["high"] < df_px["low"])
        | (df_px["close"] > df_px["high"] * 1.001)
        | (df_px["close"] < df_px["low"] * 0.999)
    ).sum()

    print(f"  • VN-Index: {min_idx_date} -> {max_idx_date} ({len(df_idx):,} phiên)")
    print(f"  • Cổ phiếu HOSE: {min_px_date} -> {max_px_date} ({len(symbols)} mã, {total_rows:,} dòng)")
    print(f"  • Kiểm tra Null/NaN: {'[CẢNH BÁO] Có giá trị thiếu' if has_nulls else '[OK] 0 Null/NaN'}")
    print(f"  • Kiểm tra logic giá: {'[CẢNH BÁO] ' + str(invalid_prices) + ' dòng sai' if invalid_prices > 0 else '[OK] Không có lỗi logic giá'}")

    passed = (not has_nulls) and (invalid_prices == 0)
    meta = {
        "max_px_date": max_px_date,
        "max_idx_date": max_idx_date,
        "symbols_count": len(symbols),
        "total_rows": total_rows,
        "has_nulls": bool(has_nulls),
        "invalid_prices": int(invalid_prices),
    }
    return passed, meta


def run_unit_tests():
    print("\n--- [BƯỚC 2/4] CHẠY BỘ KIỂM THỬ TÍNH NĂNG (PYTEST SUITE) ---")
    cmd = [sys.executable, "-m", "pytest", "-v", "tests/"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout)
    if res.returncode != 0:
        print("[FAIL] Kiểm thử tính năng có lỗi!")
        if res.stderr:
            print(res.stderr)
        return False
    print("[SUCCESS] Toàn bộ unit tests & quant integrity tests đều PASS!")
    return True


def run_web_sync_and_validation():
    print("\n--- [BƯỚC 3/4] ĐỒNG BỘ TÍN HIỆU & KIỂM TRA PAYLOAD WEB DASHBOARD ---")
    cmd = [sys.executable, "src/vnswing/ops/web_sync.py"]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout)
    if res.returncode != 0:
        print(f"[LỖI] Web sync thất bại: {res.stderr}")
        return False

    signals_path = ROOT / "web" / "data" / "signals.json"
    if not signals_path.exists():
        print(f"[LỖI] Không tìm thấy file {signals_path}")
        return False

    with open(signals_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    required_keys = ["sync_time", "market_date", "regime", "entries", "exits", "chart", "trade_history", "trade_summary"]
    missing = [k for k in required_keys if k not in payload]
    if missing:
        print(f"[LỖI] Payload thiếu các key: {missing}")
        return False

    trade_count = len(payload.get("trade_history", []))
    print(f"[HỢP LỆ] Payload đầy đủ thông tin: {signals_path.name}")
    print(f"  • Phiên thị trường: {payload.get('market_date')}")
    print(f"  • Trạng thái Regime: {payload.get('regime', {}).get('badge')}")
    print(f"  • Số lệnh tra cứu 2025-2026: {trade_count} lệnh")
    return True


def validate_web_frontend():
    print("\n--- [BƯỚC 4/4] KIỂM TRA CÚ PHÁP GIAO DIỆN FRONTEND (NODE.JS) ---")
    html_path = ROOT / "web" / "index.html"
    if not html_path.exists():
        print(f"[LỖI] Không tìm thấy {html_path}")
        return False

    test_js = """
const fs = require('fs');
const html = fs.readFileSync('web/index.html', 'utf8');
const scripts = html.match(/<script[\\s\\S]*?<\\/script>/gi) || [];
for (let i = 0; i < scripts.length; i++) {
  const code = scripts[i].replace(/<\\/?script.*?>/gi, '').trim();
  if (code && !scripts[i].includes('src=')) {
    try {
      new Function(code);
    } catch (e) {
      console.error(`Syntax error in script tag ${i}:`, e.message);
      process.exit(1);
    }
  }
}
console.log('All inline scripts parsed without syntax errors.');
"""
    cmd = ["node", "-e", test_js]
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(res.stdout)
    if res.returncode != 0:
        print(f"[LỖI CÚ PHÁP JS] {res.stderr}")
        return False
    print("[GIAO DIỆN HỢP LỆ] Toàn bộ mã nguồn JavaScript Web đều chuẩn xác.")
    return True


def main():
    print("=" * 70)
    print(f"[*] VN-SWING QA & DATA AUTOMATION AUDITOR | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    data_ok, meta = audit_market_data()
    tests_ok = run_unit_tests()
    web_sync_ok = run_web_sync_and_validation()
    fe_ok = validate_web_frontend()

    print("\n" + "=" * 70)
    print("BẢNG TỔNG KẾT KIỂM THỬ & DỮ LIỆU:")
    print("=" * 70)
    print(f"1. Dữ liệu thị trường (Data Integrity):  {'[PASS]' if data_ok else '[FAIL]'}")
    print(f"2. Kiểm thử tính năng (Pytest Suite):     {'[PASS]' if tests_ok else '[FAIL]'}")
    print(f"3. Đồng bộ & Payload Web (Signals JSON):  {'[PASS]' if web_sync_ok else '[FAIL]'}")
    print(f"4. Cú pháp giao diện (Frontend Scripts):  {'[PASS]' if fe_ok else '[FAIL]'}")
    print("-" * 70)

    all_pass = data_ok and tests_ok and web_sync_ok and fe_ok
    if all_pass:
        print("[SUCCESS] KẾT LUẬN: HỆ THỐNG ĐẠT CHUẨN ĐỊNH LƯỢNG - SẴN SÀNG TRIỂN KHAI!")
        sys.exit(0)
    else:
        print("[WARNING] KẾT LUẬN: PHÁT HIỆN LỖI CẦN XỬ LÝ TRƯỚC KHI DEPLOY.")
        sys.exit(1)


if __name__ == "__main__":
    main()
