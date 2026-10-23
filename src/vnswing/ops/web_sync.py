"""
Module đồng bộ dữ liệu Web Dashboard và phát tín hiệu tự động thời gian thực.
Hỗ trợ cả chạy định kỳ trên GitHub Actions (15 phút/lần) và chạy local.
Tự động cập nhật dữ liệu đến phiên hiện tại và phân tích Xu Hướng Chủ Đạo của thị trường chung.
Xuất dữ liệu ra web/data/signals.json.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from vnswing.data.ingest import fetch_ohlcv_dnse
from vnswing.features.indicators import FeatureEngine
from vnswing.signals.breakout import generate_breakout_signals
from vnswing.ops.ledger import OrderLedger
from vnswing.ops.alerts import publish_daily_alert


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_latest_intraday_price(symbol: str, is_index: bool = False) -> Optional[Dict[str, Any]]:
    """Lấy thanh nến 1-5 phút hoặc nến ngày gần nhất từ DNSE Entrade."""
    endpoint = "index" if is_index else "stock"
    now_ts = int(time.time())
    start_ts = int((datetime.now() - timedelta(days=5)).timestamp())
    url = f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{endpoint}?from={start_ts}&to={now_ts}&symbol={symbol}&resolution=1"

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


def ensure_latest_market_data(df_px: pd.DataFrame, df_idx: pd.DataFrame) -> (pd.DataFrame, pd.DataFrame):
    """
    Tự động kiểm tra và cập nhật nến ngày mới nhất từ sàn nếu dữ liệu cũ hơn ngày hôm nay.
    Giúp hệ thống luôn bám sát phiên hiện tại bất kể chạy ở máy local hay GitHub Actions.
    """
    adj_dir = ROOT / "data" / "adjusted"
    today = datetime.now().date()
    last_idx_date = df_idx["date"].max().date()

    if last_idx_date < today:
        start_date = (last_idx_date + timedelta(days=1)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")
        print(f"[*] Cập nhật dữ liệu từ {start_date} đến {today_str}...")

        # 1. Cập nhật VNINDEX
        new_idx = fetch_ohlcv_dnse("VNINDEX", from_date=start_date, to_date=today_str, is_index=True)
        if new_idx is not None and len(new_idx) > 0:
            df_idx = pd.concat([df_idx, new_idx], ignore_index=True).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
            df_idx.to_parquet(adj_dir / "index.parquet", index=False)
            print(f" -> VN-Index đã được cập nhật đến: {df_idx['date'].max().date()}")

        # 2. Cập nhật cổ phiếu
        symbols = sorted(df_px["symbol"].unique())
        new_stock_dfs = []
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(fetch_ohlcv_dnse, sym, start_date, today_str, False): sym for sym in symbols}
            for fut in as_completed(futures):
                res = fut.result()
                if res is not None and len(res) > 0:
                    new_stock_dfs.append(res)

        if new_stock_dfs:
            df_px = pd.concat([df_px] + new_stock_dfs, ignore_index=True)
            df_px["date"] = pd.to_datetime(df_px["date"])
            df_px = df_px.drop_duplicates(subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
            df_px.to_parquet(adj_dir / "prices.parquet", index=False)
            print(f" -> Cập nhật thành công {len(new_stock_dfs)} mã cổ phiếu đến: {df_px['date'].max().date()}")

    return df_px, df_idx


def analyze_primary_market_trend(
    current_idx: float,
    v_sma20: float,
    v_sma50: float,
    v_sma100: float,
    regime_active: bool
) -> Dict[str, Any]:
    """
    Phân tích Xu Hướng Chủ Đạo của thị trường chung (Dominant / Primary Market Trend)
    dựa trên hệ thống đa khung thời gian: SMA20 (ngắn hạn), SMA50 (trung hạn), SMA100 (dài hạn).
    """
    diff_sma20 = current_idx - v_sma20
    diff_sma50 = current_idx - v_sma50
    diff_sma100 = current_idx - v_sma100

    pct_sma20 = (diff_sma20 / v_sma20 * 100) if v_sma20 > 0 else 0.0
    pct_sma50 = (diff_sma50 / v_sma50 * 100) if v_sma50 > 0 else 0.0
    pct_sma100 = (diff_sma100 / v_sma100 * 100) if v_sma100 > 0 else 0.0

    # Phân loại xu hướng chủ đạo
    if current_idx > v_sma20 and v_sma20 > v_sma50 and v_sma50 > v_sma100:
        trend_status = "TĂNG TRƯỞNG MẠNH (UPTREND)"
        trend_badge = "🟢 UPTREND MẠNH"
        trend_color = "emerald"
        trend_desc = "Cấu trúc tăng giá hoàn hảo (Index > SMA20 > SMA50 > SMA100). Dòng tiền duy trì vị thế dẫn dắt rất mạnh."
        trend_advice = "Ưu tiên giải ngân theo đà tăng (Breakout & Pullback), gia tăng vị thế khi xuất hiện nhịp rung lắc kỹ thuật."
    elif current_idx > v_sma50 and current_idx > v_sma100:
        trend_status = "TĂNG GIÁ TRUNG HẠN"
        trend_badge = "🟢 TĂNG GIÁ TRUNG HẠN"
        trend_color = "emerald"
        trend_desc = "VN-Index duy trì vững chắc trên SMA50 & SMA100. Xu hướng tăng chủ đạo trung hạn được bảo toàn."
        trend_advice = "Cho phép mở vị thế mới có chọn lọc theo đúng tiêu chí định lượng V-DBO."
    elif current_idx > v_sma100 and current_idx <= v_sma20:
        trend_status = "ĐIỀU CHỈNH NGẮN HẠN (PULLBACK)"
        trend_badge = "🟡 ĐIỀU CHỈNH NGẮN HẠN"
        trend_color = "amber"
        trend_desc = "VN-Index tạm thời suy yếu dưới SMA20 nhưng vẫn giữ được ngưỡng hỗ trợ trung - dài hạn SMA100."
        trend_advice = "Thị trường rung lắc tái tích lũy. Hạn chế mua đuổi giá trần, kiên nhẫn chờ tín hiệu cân bằng tại hỗ trợ."
    elif abs(diff_sma50) / v_sma50 < 0.015 and abs(diff_sma100) / v_sma100 < 0.02:
        trend_status = "TÍCH LŨY / ĐI NGANG (SIDEWAYS)"
        trend_badge = "⚪ TÍCH LŨY ĐI NGANG"
        trend_color = "slate"
        trend_desc = "VN-Index dao động biên độ hẹp quanh SMA50 & SMA100. Thị trường phân hóa cao giữa các nhóm ngành."
        trend_advice = "Kiên nhẫn quan sát, chờ tín hiệu dòng tiền bứt phá rõ ràng trước khi nâng quy mô giải ngân."
    else:
        trend_status = "GIẢM GIÁ (DOWNTREND TRUNG HẠN)"
        trend_badge = "🔴 DOWNTREND TRUNG HẠN"
        trend_color = "rose"
        trend_desc = "VN-Index nằm dưới cả SMA50 và SMA100. Xu hướng điều chỉnh giảm chủ đạo đang chiếm ưu thế trên thị trường."
        trend_advice = "TẮT bộ lọc mua mới. Ưu tiên bảo toàn vốn, quản trị chặt trailing stop và hạ tỷ trọng danh mục."

    return {
        "status": trend_status,
        "badge": trend_badge,
        "color": trend_color,
        "description": trend_desc,
        "action_advice": trend_advice,
        "sma20": round(v_sma20, 2),
        "sma50": round(v_sma50, 2),
        "sma100": round(v_sma100, 2),
        "diff_sma20_pts": round(diff_sma20, 2),
        "diff_sma50_pts": round(diff_sma50, 2),
        "diff_sma100_pts": round(diff_sma100, 2),
        "diff_sma20_pct": round(pct_sma20, 2),
        "diff_sma50_pct": round(pct_sma50, 2),
        "diff_sma100_pct": round(pct_sma100, 2),
    }


def generate_web_dashboard_data(config_path: str = "configs/base.yaml") -> Dict[str, Any]:
    print("=== [WEB SYNC] ĐỒNG BỘ DỮ LIỆU TÍN HIỆU THỜI GIAN THỰC ĐẾN HIỆN TẠI ===")
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Đọc config
    with open(ROOT / config_path, "r", encoding="utf-8") as f:
        full_cfg = yaml.safe_load(f)

    # 2. Đọc dữ liệu lịch sử và tự động cập nhật đến hiện tại
    adj_dir = ROOT / "data" / "adjusted"
    df_px = pd.read_parquet(adj_dir / "prices.parquet")
    df_idx = pd.read_parquet(adj_dir / "index.parquet")
    df_px, df_idx = ensure_latest_market_data(df_px, df_idx)

    # 3. Lấy cập nhật realtime nến 15 phút phiên hôm nay cho VN-INDEX
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
            # Cập nhật giá close nến trong ngày hôm nay
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

    # 6. Xác định Hệ Thống Xu Hướng & Regime Thị Trường
    m_regime = 100
    sma20_series = F.idx.rolling(20, min_periods=20).mean()
    sma50_series = F.idx.rolling(50, min_periods=50).mean()
    sma100_series = F.idx.rolling(m_regime, min_periods=m_regime).mean()

    current_idx_val = float(F.idx.iloc[t_idx])
    v_sma20 = float(sma20_series.iloc[t_idx])
    v_sma50 = float(sma50_series.iloc[t_idx])
    v_sma100 = float(sma100_series.iloc[t_idx])

    regime_active = bool(current_idx_val > v_sma100) if not np.isnan(v_sma100) else True
    regime_diff = current_idx_val - v_sma100 if not np.isnan(v_sma100) else 0.0

    primary_trend = analyze_primary_market_trend(
        current_idx=current_idx_val,
        v_sma20=v_sma20,
        v_sma50=v_sma50,
        v_sma100=v_sma100,
        regime_active=regime_active,
    )

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

    # 8. Quét tín hiệu THOÁT / NÂNG STOP (Mô hình Champion: n_out=15, k=3.0)
    exits = []
    n_out = 15
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

    # 9. Quét tín hiệu VÀO LỆNH mới (Mô hình Champion V-DBO Trend Focus: n_in=30, vm=1.2, clv=0.5)
    entries = []
    n_in = 30
    vm = 1.2
    clv_min = 0.50
    rs_top = 0.50
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

    # Lấy top candidates (tối đa 15 mã để hiển thị trên Web)
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

    # 10. Tạo dữ liệu biểu đồ VN-Index đa khung thời gian (60 phiên gần nhất)
    chart_days = min(60, len(dates))
    chart_dates = [str(d.date()) for d in dates[-chart_days:]]
    chart_idx_c = [float(x) for x in F.idx.iloc[-chart_days:].values]
    chart_idx_sma20 = [float(x) if not np.isnan(x) else None for x in sma20_series.iloc[-chart_days:].values]
    chart_idx_sma50 = [float(x) if not np.isnan(x) else None for x in sma50_series.iloc[-chart_days:].values]
    chart_idx_sma100 = [float(x) if not np.isnan(x) else None for x in sma100_series.iloc[-chart_days:].values]

    # Đóng gói dữ liệu tổng thể
    payload = {
        "sync_time": now_str,
        "market_date": analysis_date_str,
        "next_sync_seconds": 300,  # 5 phút
        "regime": {
            "active": regime_active,
            "badge": "BẬT (MUA MỚI)" if regime_active else "TẮT (NGỪNG MUA)",
            "index_value": current_idx_val,
            "sma_value": v_sma100,
            "diff_pts": regime_diff,
            "diff_pct": (regime_diff / v_sma100 * 100) if not np.isnan(v_sma100) and v_sma100 > 0 else 0.0,
            "text": f"VN-Index {'nằm trên' if regime_active else 'nằm dưới'} đường SMA100 ({regime_diff:+,.1f} điểm)",
            "primary_trend": primary_trend,
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
            "sma20": chart_idx_sma20,
            "sma50": chart_idx_sma50,
            "sma100": chart_idx_sma100,
        },
    }

    # 11. Đính kèm Lịch sử lệnh & Hiệu suất khuyến nghị thực tế (2025 - Nay)
    trade_hist_path = ROOT / "data" / "trade_history_2025_2026.json"
    if trade_hist_path.exists():
        try:
            with open(trade_hist_path, "r", encoding="utf-8") as f:
                hist_data = json.load(f)
            payload["trade_history"] = hist_data.get("trades", [])
            payload["trade_summary"] = hist_data.get("metadata", {}).get("summary", {})
            payload["champion_strategy"] = {
                "name": hist_data.get("metadata", {}).get("strategy", "V-DBO Trend Focus"),
                "period": hist_data.get("metadata", {}).get("period", "2025-01-01 to 2026-10-12"),
                "params": hist_data.get("metadata", {}).get("params", {}),
                "metrics": hist_data.get("metadata", {}).get("metrics", {}),
            }
        except Exception as e:
            print(f" [CẢNH BÁO] Không đọc được trade_history_2025_2026.json: {e}")
            payload["trade_history"] = []
            payload["trade_summary"] = {}
            payload["champion_strategy"] = {}

    # Xuất file web/data/signals.json
    web_dir = ROOT / "web"
    web_data_dir = web_dir / "data"
    web_data_dir.mkdir(parents=True, exist_ok=True)
    json_path = web_data_dir / "signals.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f" -> Đã xuất dữ liệu JSON: {json_path}")
    print(f" -> Phiên thị trường: {analysis_date_str}")
    print(f" -> Xu Hướng Chủ Đạo: {primary_trend['badge']} ({primary_trend['status']})")
    print(f" -> Bộ lọc Regime: {'🟢 BẬT' if regime_active else '🔴 TẮT'} ({payload['regime']['text']})")
    print(f" -> Tín hiệu Mua mới: {len(entries)} mã (Được đề xuất vào lệnh: {min(len(entries), free_slots) if regime_active else 0})")
    print(f" -> Tín hiệu Thoát / Trailing: {len(exits)} vị thế")

    # Xuất bản alert telegram nếu có thay đổi quan trọng
    if entries or exits:
        publish_daily_alert(
            date_str=analysis_date_str,
            regime_active=regime_active,
            regime_detail=f"{primary_trend['badge']} — {primary_trend['description']}",
            entries=entries[:free_slots] if regime_active else [],
            exits=exits,
            portfolio_status=portfolio_status,
        )

    return payload


if __name__ == "__main__":
    generate_web_dashboard_data()
