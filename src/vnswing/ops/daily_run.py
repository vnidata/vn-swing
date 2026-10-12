"""
Script vận hành hằng ngày (Daily Operations Runner) — Lịch chạy ~15:30 - 16:15.
1. Cập nhật dữ liệu giá cuối phiên từ DNSE vào data/adjusted/
2. Kiểm tra chất lượng dữ liệu (dừng pipeline nếu có lỗi nghiêm trọng)
3. Tính toán đặc trưng, xác định Regime thị trường
4. Quét tín hiệu VÀO LỆNH mới và THOÁT LỆNH / NÂNG STOP cho vị thế hiện tại
5. Xuất reports/daily/YYYY-MM-DD_signals.csv và phát bản tin qua alerts.py
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vnswing.features.indicators import FeatureEngine
from vnswing.signals.breakout import generate_breakout_signals
from vnswing.ops.ledger import OrderLedger
from vnswing.ops.alerts import publish_daily_alert


def run_daily_pipeline(target_date: str = None, config_path: str = "configs/base.yaml"):
    print(f"=== [OPS] BẮT ĐẦU VẬN HÀNH QUÉT TÍN HIỆU NGÀY ({target_date or 'Hôm nay'}) ===")

    # 1. Nạp cấu hình
    cfg_file = ROOT / config_path
    with open(cfg_file, "r", encoding="utf-8") as f:
        full_cfg = yaml.safe_load(f)

    # 2. Nạp dữ liệu giá và chỉ số
    adj_dir = ROOT / "data" / "adjusted"
    prices_path = adj_dir / "prices.parquet"
    index_path = adj_dir / "index.parquet"

    if not prices_path.exists() or not index_path.exists():
        raise FileNotFoundError("Thiếu dữ liệu trong data/adjusted/. Vui lòng chạy Phase 1 trước!")

    df_px = pd.read_parquet(prices_path)
    df_idx = pd.read_parquet(index_path)

    # Format wide
    W = {
        c: df_px.pivot(index="date", columns="symbol", values=c).sort_index()
        for c in ["open", "high", "low", "close", "volume"]
    }
    df_idx["date"] = pd.to_datetime(df_idx["date"])
    idx_close = df_idx.set_index("date")["close"].sort_index().reindex(W["close"].index).ffill()

    dates = W["close"].index
    if target_date is not None:
        target_dt = pd.to_datetime(target_date)
        if target_dt not in dates:
            # Chọn ngày giao dịch gần nhất trước hoặc bằng target_date
            valid_dates = dates[dates <= target_dt]
            if len(valid_dates) == 0:
                raise ValueError(f"Không có ngày giao dịch nào trước hoặc bằng {target_date}")
            target_dt = valid_dates[-1]
    else:
        target_dt = dates[-1]

    t_idx = int(np.where(dates == target_dt)[0][0])
    date_str = str(target_dt.date())
    print(f" -> Ngày phân tích tín hiệu: {date_str} (Phiên index: {t_idx}/{len(dates)})")

    # 3. Tính toán đặc trưng
    F = FeatureEngine(W, idx_close)

    # 4. Trạng thái Regime thị trường VN-Index
    # Sử dụng SMA100 mặc định
    m_regime = 100
    idx_sma = F.idx.rolling(m_regime, min_periods=m_regime).mean().iloc[t_idx]
    current_idx_val = F.idx.iloc[t_idx]
    regime_active = bool(current_idx_val > idx_sma) if not np.isnan(idx_sma) else True
    regime_detail = (
        f"VN-Index đóng cửa tại {current_idx_val:,.1f} điểm "
        f"({'TRÊN' if regime_active else 'DƯỚI'} đường SMA{m_regime}: {idx_sma:,.1f} điểm)"
    )

    # 5. Đọc trạng thái sổ lệnh danh mục thực tế
    ledger = OrderLedger(init_cash=float(full_cfg["portfolio"]["init_cash"]))
    latest_prices = {sym: float(W["close"].iloc[t_idx][sym]) for sym in W["close"].columns if not np.isnan(W["close"].iloc[t_idx][sym])}
    portfolio_status = ledger.get_portfolio_status(latest_prices)
    open_positions = portfolio_status["open_positions"]
    open_symbols = set(open_positions.keys())

    max_positions = int(full_cfg["portfolio"]["max_positions"])
    free_slots = max(0, max_positions - len(open_symbols))
    eq = portfolio_status["total_equity"]

    # 6. Quét tín hiệu THOÁT / NÂNG STOP cho các vị thế đang giữ
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
        entry_dt = pos_info["entry_date"]
        hold_sessions = int((dates[t_idx] - entry_dt).days) # Ước lượng hoặc đếm số phiên

        # Kiểm tra điều kiện thoát
        exit_triggered = False
        exit_reason = ""
        if curr_c < ll_val:
            exit_triggered = True
            exit_reason = f"Đóng cửa ({curr_c:,.0f}) thủng đáy {n_out} phiên ({ll_val:,.0f})"
        elif curr_c < trailing_stop:
            exit_triggered = True
            exit_reason = f"Đóng cửa ({curr_c:,.0f}) chạm Trailing Stop ({trailing_stop:,.0f})"

        if exit_triggered:
            exits.append({
                "symbol": sym,
                "action": "EXIT",
                "reason": exit_reason,
                "close": curr_c,
                "new_stop": max(trailing_stop, ll_val),
                "shares": pos_info["shares"],
            })
        else:
            # Cập nhật nâng trailing stop nếu giá tăng
            exits.append({
                "symbol": sym,
                "action": "TRAILING_UPDATE",
                "reason": f"Duy trì vị thế, stop theo ATR: {trailing_stop:,.0f}",
                "close": curr_c,
                "new_stop": trailing_stop,
                "shares": pos_info["shares"],
            })

    # 7. Quét tín hiệu VÀO LỆNH mới
    entries = []
    if free_slots > 0 and regime_active:
        n_in = 20
        vm = 1.3
        clv_min = 0.65
        rs_top = 0.5
        min_adtv = float(full_cfg["universe"]["min_adtv_vnd"])

        sig_mask, strength_mat = generate_breakout_signals(
            F, n_in=n_in, m=m_regime, vm=vm, clv=clv_min, rs=rs_top, min_adtv=min_adtv
        )

        candidates = np.where(sig_mask[t_idx])[0]
        # Loại các mã đã có trong danh mục
        candidates = [c for c in candidates if F.symbols[c] not in open_symbols]
        # Xếp hạng theo độ mạnh tín hiệu
        candidates = sorted(candidates, key=lambda c: -strength_mat[t_idx, c])

        # Chọn tối đa theo số vị thế trống
        selected = candidates[:free_slots]

        hh_vals = F.hh(n_in)
        for c in selected:
            sym = F.symbols[c]
            curr_c = F.C[t_idx, c]
            atr_v = F.atr[t_idx, c]
            break_lvl = hh_vals[t_idx, c]
            stop_suggested = curr_c - k_atr * atr_v
            risk_ps = k_atr * atr_v

            # Tính toán phân bổ vốn
            risk_pct = float(full_cfg["portfolio"]["risk_pct"])
            max_w = float(full_cfg["portfolio"]["max_weight"])
            adtv_frac = float(full_cfg["universe"]["adtv_frac_cap"])
            lot = int(full_cfg["market"]["lot"])

            sh = risk_pct * eq / risk_ps if risk_ps > 0 else 0
            cap_val = min(max_w * eq, adtv_frac * F.adtv[t_idx, c])
            sh = min(sh, cap_val / curr_c, portfolio_status["cash"] / (curr_c * 1.003))
            sh = int(np.floor(sh / lot) * lot)

            if sh >= lot:
                val = sh * curr_c
                w = val / eq if eq > 0 else 0.0
                risk_vnd = sh * risk_ps

                # Cảnh báo rủi ro
                cprev = F.C[t_idx - 1, c] if t_idx > 0 else curr_c
                limit_up_px = cprev * 1.07
                warning = ""
                if curr_c >= limit_up_px * 0.995:
                    warning = "Đóng cửa sát trần (cẩn trọng ATO phiên sau)"

                entries.append({
                    "symbol": sym,
                    "close": curr_c,
                    "break_level": break_lvl,
                    "atr": atr_v,
                    "stop_loss": stop_suggested,
                    "shares": sh,
                    "value": val,
                    "weight": w,
                    "risk_vnd": risk_vnd,
                    "adtv": F.adtv[t_idx, c],
                    "warning": warning,
                })

    # 8. Lưu tín hiệu ra file CSV reports/daily/YYYY-MM-DD_signals.csv
    daily_dir = ROOT / "reports" / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    csv_file = daily_dir / f"{date_str}_signals.csv"

    rows = []
    for e in entries:
        rows.append({
            "date": date_str, "type": "ENTRY", "symbol": e["symbol"], "close": e["close"],
            "stop_loss": e["stop_loss"], "suggested_shares": e["shares"], "order_value": e["value"],
            "weight": e["weight"], "adtv": e["adtv"], "warning": e["warning"]
        })
    for ex in exits:
        rows.append({
            "date": date_str, "type": ex["action"], "symbol": ex["symbol"], "close": ex["close"],
            "stop_loss": ex["new_stop"], "suggested_shares": ex["shares"], "order_value": 0.0,
            "weight": 0.0, "adtv": 0.0, "warning": ex["reason"]
        })

    if rows:
        pd.DataFrame(rows).to_csv(csv_file, index=False, encoding="utf-8")
        print(f" -> Đã lưu tín hiệu vào: {csv_file}")
    else:
        print(f" -> Không có tín hiệu mới (File CSV trống).")

    # 9. Xuất bản bản tin (Telegram + Console)
    publish_daily_alert(
        date_str=date_str,
        regime_active=regime_active,
        regime_detail=regime_detail,
        entries=entries,
        exits=exits,
        portfolio_status=portfolio_status,
    )

    return entries, exits


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, default=None, help="Ngày chạy tín hiệu (YYYY-MM-DD), mặc định ngày mới nhất")
    a = ap.parse_args()
    run_daily_pipeline(target_date=a.date)
