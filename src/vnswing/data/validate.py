"""
Module kiểm tra chất lượng dữ liệu (Data Validation) và sinh Data Manifest.
Ghi nhận mọi cờ bất thường vào reports/data_quality.csv và reports/data_quality.md.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


def validate_ohlcv(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Kiểm tra tính nhất quán của dữ liệu nến:
    - low <= open, close <= high
    - Không giá <= 0
    - Không trùng lặp (date, symbol)
    - |close/close_prev - 1| > 7.5%
    - volume == 0 nhưng giá đổi
    """
    flags = []
    stats = {
        "total_rows": len(df),
        "invalid_ohlc": 0,
        "negative_or_zero_price": 0,
        "price_jump_exceed_limit": 0,
        "zero_vol_price_change": 0,
        "duplicates": 0,
    }

    # 1. Trùng lặp
    dup_mask = df.duplicated(subset=["date", "symbol"], keep=False)
    stats["duplicates"] = int(dup_mask.sum())
    if dup_mask.any():
        for _, row in df[dup_mask].iterrows():
            flags.append({
                "date": row["date"],
                "symbol": row["symbol"],
                "flag_type": "DUPLICATE_KEY",
                "detail": "Trùng lặp khóa (date, symbol)",
            })

    # 2. Giá <= 0
    invalid_px = (df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)
    stats["negative_or_zero_price"] = int(invalid_px.sum())
    if invalid_px.any():
        for _, row in df[invalid_px].iterrows():
            flags.append({
                "date": row["date"],
                "symbol": row["symbol"],
                "flag_type": "ZERO_OR_NEGATIVE_PRICE",
                "detail": f"O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}",
            })

    # 3. Tính nhất quán O, H, L, C
    inconsistent = (df["low"] > df["open"]) | (df["low"] > df["close"]) | (df["high"] < df["open"]) | (df["high"] < df["close"])
    stats["invalid_ohlc"] = int(inconsistent.sum())
    if inconsistent.any():
        for _, row in df[inconsistent].iterrows():
            flags.append({
                "date": row["date"],
                "symbol": row["symbol"],
                "flag_type": "INCONSISTENT_OHLC",
                "detail": f"O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}",
            })

    # 4. Kiểm tra nhảy giá > 7.5% theo từng mã
    df_sorted = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    df_sorted["prev_close"] = df_sorted.groupby("symbol")["close"].shift(1)
    df_sorted["pct_change"] = np.abs(df_sorted["close"] / df_sorted["prev_close"] - 1.0)
    
    jumps = df_sorted[df_sorted["pct_change"] > 0.075]
    stats["price_jump_exceed_limit"] = int(len(jumps))
    for _, row in jumps.iterrows():
        flags.append({
            "date": row["date"],
            "symbol": row["symbol"],
            "flag_type": "PRICE_JUMP_EXCEED_LIMIT",
            "detail": f"Biến động {row['pct_change']:.2%} (Close={row['close']}, Prev={row['prev_close']})",
        })

    # 5. Volume = 0 nhưng giá thay đổi
    zero_vol_change = df_sorted[(df_sorted["volume"] == 0) & (df_sorted["pct_change"] > 0.0001)]
    stats["zero_vol_price_change"] = int(len(zero_vol_change))
    for _, row in zero_vol_change.iterrows():
        flags.append({
            "date": row["date"],
            "symbol": row["symbol"],
            "flag_type": "ZERO_VOLUME_PRICE_CHANGE",
            "detail": f"Volume=0 nhưng giá thay đổi từ {row['prev_close']} sang {row['close']}",
        })

    flags_df = pd.DataFrame(flags)
    return flags_df, stats


def compute_sha256(file_path: Path) -> str:
    """Tính mã băm SHA-256 của file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def generate_data_manifest(
    data_files: Dict[str, Path],
    source: str,
    output_path: Path,
) -> Dict:
    """Sinh file registry/data_manifest.json lưu vết hash và khoảng ngày."""
    manifest = {
        "source": source,
        "created_at": pd.Timestamp.now().isoformat(),
        "files": {},
    }
    for name, p in data_files.items():
        if p.exists():
            df = pd.read_parquet(p)
            dates = pd.to_datetime(df["date"])
            manifest["files"][name] = {
                "path": str(p.name),
                "sha256": compute_sha256(p),
                "rows": len(df),
                "symbols_count": int(df["symbol"].nunique()) if "symbol" in df.columns else 1,
                "date_min": str(dates.min().date()),
                "date_max": str(dates.max().date()),
            }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest
