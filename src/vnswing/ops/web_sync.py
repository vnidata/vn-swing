"""
Module đồng bộ dữ liệu Web Dashboard và phát tín hiệu tự động.
Hỗ trợ cả chạy định kỳ trên GitHub Actions (15 phút/lần) và chạy local.
Xuất dữ liệu ra web/data/signals.json và nhúng trực tiếp vào web/index.html để mở offline.
"""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd
import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vnswing.features.indicators import FeatureEngine
from vnswing.signals.breakout import generate_breakout_signals
from vnswing.ops.ledger import OrderLedger
from vnswing.ops.alerts import publish_daily_alert


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_latest_intraday_price(symbol: str, is_index: bool = False) -> Optional[Dict[str, Any]]:
    """Lấy thanh nến 15 phút hoặc nến ngày gần nhất từ DNSE Entrade."""
    endpoint = "index" if is_index else "stock"
    now_ts = int(time.time())
    start_ts = int((datetime.now() - timedelta(days=5)).timestamp())
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{endpoint}?from={start_ts}&to={now_ts}&symbol={symbol}&resolution=15"

    try:
        r = requests.get(url, headers=HEADERS, verify=False, timeout=8)
        if r.status_code == 200:
            d = r.json()
            if "t" in d and len(d["t"]) > 0:
                scale = 1.0 if is_index else 1000.0
                return {
                    "timestamp": d["t"][-1],
                    "open": float(d["o"][-1]) * scale,
                    "high": float(d["h"][-1]) * scale,
                    "low": float(d["l"][-1]) * scale,
                    "close": float(d["c"][-1]) * scale,
                    "volume": float(d["v"][-1]),
                }
    except Exception:
        pass
    return None


def generate_web_dashboard_data(config_path: str = "configs/base.yaml") -> Dict[str, Any]:
    print("=== [WEB SYNC] ĐỒNG BỘ DỮ LIỆU TÍN HIỆU REALTIME CHO WEBSITE ===")
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Đọc config
    with open(ROOT / config_path, "r", encoding="utf-8") as f:
        full_cfg = yaml.safe_load(f)

    # 2. Đọc dữ liệu lịch sử đã lưu
    adj_dir = ROOT / "data" / "adjusted"
    df_px = pd.read_parquet(adj_dir / "prices.parquet")
    df_idx = pd.read_parquet(adj_dir / "index.parquet")

    # 3. Lấy cập nhật realtime phiên mới nhất cho VN-INDEX
    latest_idx_bar = fetch_latest_intraday_price("VNINDEX", is_index=True)
    if latest_idx_bar:
        bar_date = pd.to_datetime(latest_idx_bar["timestamp"], unit="s", utc=True).tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize()
        if bar_date > df_idx["date"].max():
            new_idx_row = pd.DataFrame([{
                "date": bar_date, "symbol": "VNINDEX",
                "open": latest_idx_bar["open"], "high": latest_idx_bar["high"],
                "low": latest_idx_bar["low"], "close": latest_idx_bar["close"],
                "volume": latest_idx_bar["volume"],
            }])
            df_idx = pd.concat([df_idx, new_idx_row], ignore_index=True)
        else:
            # Cập nhật giá close trong phiên hôm nay
            df_idx.loc[df_idx["date"] == bar_date, "close"] = latest_idx_bar["close"]
            df_idx.loc[df_idx["date"] == bar_date, "high"] = max(float(df_idx.loc[df_idx["date"] == bar_date, "high"].values[0]), latest_idx_bar["high"])
            df_idx.loc[df_idx["date"] == bar_date, "low"] = min(float(df_idx.loc[df_idx["date"] == bar_date, "low"].values[0]), latest_idx_bar["low"])

    # 4. Format dữ liệu dạng wide
    W = {
        c: df_px.pivot(index="date", columns="symbol", values=c).sort_index()
        for c in ["open", "high", "low", "close", "volume"]
    }
    df_idx["date"] = pd.to_datetime(df_idx["date"])
    idx_close = df_idx.set_index("date")["close"].sort_index().reindex(W["close"].index).ffill()

    dates = W["close"].index
    t_idx = len(dates) - 1
    analysis_date_str = str(dates[t_idx].date())

    # 5. Khởi tạo FeatureEngine
    F = FeatureEngine(W, idx_close)

    # 6. Xác định Regime thị trường
    m_regime = 100
    idx_sma_series = F.idx.rolling(m_regime, min_periods=m_regime).mean()
    idx_sma = idx_sma_series.iloc[t_idx]
    current_idx_val = F.idx.iloc[t_idx]
    regime_active = bool(current_idx_val > idx_sma) if not np.isnan(idx_sma) else True
    regime_diff = current_idx_val - idx_sma if not np.isnan(idx_sma) else 0.0

    # 7. Đọc trạng thái sổ lệnh
    ledger = OrderLedger(init_cash=float(full_cfg["portfolio"]["init_cash"]))
    latest_prices = {sym: float(W["close"].iloc[t_idx][sym]) for sym in W["close"].columns if not np.isnan(W["close"].iloc[t_idx][sym])}
    portfolio_status = ledger.get_portfolio_status(latest_prices)
    open_positions = portfolio_status["open_positions"]
    open_symbols = set(open_positions.keys())

    max_positions = int(full_cfg["portfolio"]["max_positions"])
    free_slots = max(0, max_positions - len(open_symbols))
    eq = portfolio_status["total_equity"]
    init_cash = float(full_cfg["portfolio"]["init_cash"])
    drawdown = (eq / init_cash - 1.0) if eq < init_cash else 0.0

    # 8. Quét tín hiệu THOÁT / NÂNG STOP
    exits = []
    n_out = 10
    k_atr = 3.0
    ll_exit = F.ll(n_out)

    for sym, pos_info in open_positions.items():
        if sym not in F.symbols:
            continue
        s_col = int(np.where(F.symbols == sym)[0][0])
        curr_c = F.C[t_idx, s_col]
        atr_val = F.atr[t_idx, s_col]
        highest_c = max(pos_info["highest_close"], curr_c)
        trailing_stop = highest_c - k_atr * atr_val
        ll_val = ll_exit[t_idx, s_col]

        exit_triggered = False
        exit_reason = ""
        if curr_c < ll_val:
            exit_triggered = True
            exit_reason = f"Đóng cửa ({curr_c:,.0f}) thủng đáy {n_out} phiên ({ll_val:,.0f})"
        elif curr_c < trailing_stop:
            exit_triggered = True
            exit_reason = f"Đóng cửa ({curr_c:,.0f}) chạm Trailing Stop ATR ({trailing_stop:,.0f})"

        pnl_pct = (curr_c / pos_info["cost_basis"] - 1.0) if pos_info["cost_basis"] > 0 else 0.0

        exits.append({
            "symbol": sym,
            "action": "EXIT" if exit_triggered else "HOLD",
            "action_text": "BÁN HẾT ATO" if exit_triggered else "DUY TRÌ VỊ THẾ",
            "reason": exit_reason or f"Nâng Trailing Stop lên {trailing_stop:,.0f} VND",
            "close": float(curr_c),
            "cost_basis": float(pos_info["cost_basis"]),
            "pnl_pct": float(pnl_pct),
            "stop_loss": float(max(trailing_stop, ll_val) if exit_triggered else trailing_stop),
            "shares": int(pos_info["shares"]),
            "entry_date": str(pos_info["entry_date"].date()),
        })

    # 9. Quét tín hiệu VÀO LỆNH mới
    entries = []
    n_in = 20
    vm = 1.3
    clv_min = 0.65
    rs_top = 0.5
    min_adtv = float(full_cfg["universe"]["min_adtv_vnd"])

    sig_mask, strength_mat = generate_breakout_signals(
        F, n_in=n_in, m=m_regime, vm=vm, clv=clv_min, rs=rs_top, min_adtv=min_adtv
    )

    candidates = np.where(sig_mask[t_idx])[0]
    candidates = [c for c in candidates if F.symbols[c] not in open_symbols]
    candidates = sorted(candidates, key=lambda c: -strength_mat[t_idx, c])

    hh_vals = F.hh(n_in)
    risk_pct = float(full_cfg["portfolio"]["risk_pct"])
    max_w = float(full_cfg["portfolio"]["max_weight"])
    adtv_frac = float(full_cfg["universe"]["adtv_frac_cap"])
    lot = int(full_cfg["market"]["lot"])

    # Lấy top candidates (tối đa 15 mã để hiển thị đầy đủ trên Web)
    display_candidates = candidates[:max(15, free_slots * 2)]
    for rank, c in enumerate(display_candidates, 1):
        sym = F.symbols[c]
        curr_c = float(F.C[t_idx, c])
        atr_v = float(F.atr[t_idx, c])
        break_lvl = float(hh_vals[t_idx, c])
        stop_suggested = float(curr_c - k_atr * atr_v)
        risk_ps = float(k_atr * atr_v)

        sh = risk_pct * eq / risk_ps if risk_ps > 0 else 0
        cap_val = min(max_w * eq, adtv_frac * F.adtv[t_idx, c])
        sh = min(sh, cap_val / curr_c, portfolio_status["cash"] / (curr_c * 1.003))
        sh = int(np.floor(sh / lot) * lot)

        cprev = float(F.C[t_idx - 1, c]) if t_idx > 0 else curr_c
        limit_up_px = cprev * 1.07
        warning = ""
        if curr_c >= limit_up_px * 0.995:
            warning = "Đóng cửa sát trần (cẩn trọng ATO)"

        val = sh * curr_c
        w = val / eq if eq > 0 else 0.0

        entries.append({
            "rank": rank,
            "is_recommended": rank <= free_slots and regime_active,
            "symbol": sym,
            "close": curr_c,
            "break_level": break_lvl,
            "strength": float(strength_mat[t_idx, c]),
            "atr": atr_v,
            "stop_loss": stop_suggested,
            "shares": sh,
            "value": val,
            "weight": w,
            "risk_vnd": sh * risk_ps,
            "adtv": float(F.adtv[t_idx, c]),
            "warning": warning,
        })

    # 10. Tạo dữ liệu biểu đồ VN-Index (60 phiên gần nhất)
    chart_days = min(60, len(dates))
    chart_dates = [str(d.date()) for d in dates[-chart_days:]]
    chart_idx_c = [float(x) for x in F.idx.iloc[-chart_days:].values]
    chart_idx_sma = [float(x) if not np.isnan(x) else None for x in idx_sma_series.iloc[-chart_days:].values]

    # Đóng gói dữ liệu tổng thể
    payload = {
        "sync_time": now_str,
        "market_date": analysis_date_str,
        "next_sync_seconds": 900,  # 15 phút
        "regime": {
            "active": regime_active,
            "badge": "BẬT (MUA MỚI)" if regime_active else "TẮT (NGỪNG MUA)",
            "index_value": current_idx_val,
            "sma_value": idx_sma,
            "diff_pts": regime_diff,
            "diff_pct": (regime_diff / idx_sma * 100) if not np.isnan(idx_sma) and idx_sma > 0 else 0.0,
            "text": f"VN-Index {'nằm trên' if regime_active else 'nằm dưới'} đường SMA100 (+{regime_diff:,.1f} điểm)",
        },
        "portfolio": {
            "total_equity": eq,
            "cash": portfolio_status["cash"],
            "positions_value": portfolio_status["positions_value"],
            "n_positions": len(open_symbols),
            "max_positions": max_positions,
            "free_slots": free_slots,
            "drawdown_pct": drawdown * 100,
        },
        "kill_switch": {
            "status": "BÌNH THƯỜNG" if abs(drawdown) < 0.15 else ("CẢNH BÁO CẤP 1 (GIẢM 50% RISK)" if abs(drawdown) < 0.25 else "KÍCH HOẠT CẤP 2 (DỪNG MUA)"),
            "level": 0 if abs(drawdown) < 0.15 else (1 if abs(drawdown) < 0.25 else 2),
            "description": "Rủi ro danh mục trong ngưỡng kiểm soát chuẩn",
        },
        "entries": entries,
        "exits": exits,
        "chart": {
            "labels": chart_dates,
            "index_close": chart_idx_c,
            "sma100": chart_idx_sma,
        },
    }

    # Xuất file web/data/signals.json
    web_dir = ROOT / "web"
    web_data_dir = web_dir / "data"
    web_data_dir.mkdir(parents=True, exist_ok=True)
    json_path = web_data_dir / "signals.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f" -> Đã xuất dữ liệu JSON: {json_path}")
    print(f" -> Tín hiệu Mua mới: {len(entries)} mã (Được đề xuất vào lệnh: {min(len(entries), free_slots)})")
    print(f" -> Tín hiệu Thoát / Trailing: {len(exits)} vị thế")

    # Xuất bản alert telegram nếu có thay đổi quan trọng
    if entries or exits:
        publish_daily_alert(
            date_str=analysis_date_str,
            regime_active=regime_active,
            regime_detail=payload["regime"]["text"],
            entries=entries[:free_slots],
            exits=exits,
            portfolio_status=portfolio_status,
        )

    return payload


if __name__ == "__main__":
    generate_web_dashboard_data()
