"""
Module thu thập dữ liệu giá lịch sử HOSE và VN-Index từ 2012 đến nay.
Nguồn: Vietcap (danh mục niêm yết & hủy niêm yết) + DNSE Entrade (OHLCV lịch sử điều chỉnh).
"""
import datetime
import json
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_master_symbols() -> pd.DataFrame:
    """Lấy danh sách toàn bộ cổ phiếu HOSE (đang niêm yết HSX và đã hủy niêm yết DELISTED)."""
    url = "https://trading.vietcap.com.vn/api/price/symbols/getAll"
    r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
    r.raise_for_status()
    data = r.json()

    records = []
    for item in data:
        board = item.get("board")
        item_type = item.get("type")
        symbol = item.get("symbol")
        if item_type == "STOCK" and board in ("HSX", "DELISTED"):
            records.append({
                "symbol": symbol,
                "board": board,
                "name": item.get("organShortName") or item.get("organName") or symbol,
                "icb": item.get("icbCode2", ""),
            })

    df = pd.DataFrame(records).drop_duplicates(subset=["symbol"]).sort_values("symbol")
    return df


def fetch_ohlcv_dnse(
    symbol: str,
    from_date: str = "2012-01-01",
    to_date: str = "2024-12-31",
    is_index: bool = False,
    price_scale: float = 1000.0,
) -> Optional[pd.DataFrame]:
    """
    Tải chuỗi nến ngày từ API DNSE Entrade.
    Giá trả về từ API DNSE là nghìn đồng (ví dụ 18.56 -> 18,560 VND).
    Hàm nhân với price_scale để chuẩn hóa về VND.
    """
    t0 = int(datetime.datetime.strptime(from_date, "%Y-%m-%d").timestamp())
    t1 = int((datetime.datetime.strptime(to_date, "%Y-%m-%d") + datetime.timedelta(days=1)).timestamp())

    endpoint = "index" if is_index else "stock"
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{endpoint}?from={t0}&to={t1}&symbol={symbol}&resolution=1D"

    for retry in range(3):
        try:
            r = requests.get(url, headers=HEADERS, verify=False, timeout=15)
            if r.status_code == 200:
                d = r.json()
                if "t" not in d or len(d["t"]) == 0:
                    return None
                dates = pd.to_datetime(d["t"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None)
                # Chuẩn hóa về date (bỏ giờ)
                dates = dates.normalize()

                df = pd.DataFrame({
                    "date": dates,
                    "symbol": symbol,
                    "open": np.array(d["o"], dtype=float) * (1.0 if is_index else price_scale),
                    "high": np.array(d["h"], dtype=float) * (1.0 if is_index else price_scale),
                    "low": np.array(d["l"], dtype=float) * (1.0 if is_index else price_scale),
                    "close": np.array(d["c"], dtype=float) * (1.0 if is_index else price_scale),
                    "volume": np.array(d["v"], dtype=float),
                })
                # Loại bỏ bản ghi trùng ngày nếu có
                df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                return df
            elif r.status_code == 404:
                return None
        except Exception:
            time.sleep(1.0)

    return None
