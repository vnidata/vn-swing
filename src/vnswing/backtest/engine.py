"""
Engine thực thi backtest cho chiến lược V-DBO.
Hỗ trợ chế độ tái lập 100% kết quả legacy và các tính năng mở rộng sửa giới hạn:
- Khớp lệnh ATO có xác suất (ato_fill_prob)
- Thanh lý mã hủy niêm yết có chiết khấu (delist_haircut)
- Không look-ahead: tín hiệu tại đóng cửa t, khớp tại mở cửa t+1
"""
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd
from vnswing.features.indicators import FeatureEngine
from vnswing.signals.breakout import generate_breakout_signals, generate_pullback_signals


def backtest(
    F: FeatureEngine,
    p: Tuple,
    cfg: Dict[str, Any],
    i0: int,
    i1: int,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, List[Tuple[int, float]]]:
    """
    Thực hiện backtest vòng lặp theo từng phiên từ i0 đến i1.
    p = (n_in, n_out, m, vm, k, clv, rs)
    """
    n_in, n_out, m, vm, k, clv, rs = p
    mode = cfg.get("mode", "brk")
    min_adtv = cfg.get("min_adtv", 1e10)

    # 1. Sinh ma trận tín hiệu và sức mạnh
    if mode == "brk":
        sig, strength = generate_breakout_signals(F, n_in, m, vm, clv, rs, min_adtv)
    else:
        sig, strength = generate_pullback_signals(F, n_in, m, vm, clv, rs, min_adtv)

    ll = F.exit_line(mode, n_out)
    T = F.C.shape[0]
    i0 = max(i0, 1)
    i1 = min(i1, T)

    cash = float(cfg.get("init_cash", 1e9))
    min_hold = int(cfg.get("min_hold", 3))
    limit = float(cfg.get("limit", 0.07))
    buy_cost = float(cfg.get("buy_cost", 0.0030))
    sell_cost = float(cfg.get("sell_cost", 0.0040))
    max_pos = int(cfg.get("max_pos", 10))
    max_w = float(cfg.get("max_w", 0.15))
    adtv_frac = float(cfg.get("adtv_frac", 0.03))
    lot = int(cfg.get("lot", 100))
    delist_haircut = float(cfg.get("delist_haircut", 0.0))
    ato_fill_prob = float(cfg.get("ato_fill_prob", 1.0))

    pos: Dict[int, Dict[str, Any]] = {}
    pend_exit: Set[int] = set()
    pend_entry: List[int] = []
    trades: List[Tuple[int, float]] = []

    eq = np.full(T, np.nan)
    eq[i0 - 1] = cash
    ks = k if k < 50 else 3.0

    for t in range(i0, i1):
        o, cprev = F.O[t], F.C[t - 1]

        # ---------------------------------------------------------------------
        # 1) Khớp lệnh THOÁT tại giá mở cửa (ATO) phiên t
        # ---------------------------------------------------------------------
        for j in list(pend_exit):
            P = pos[j]
            # Kiểm tra thời gian giữ tối thiểu
            if (t - P["ei"]) < min_hold or np.isnan(o[j]) or np.isnan(cprev[j]):
                continue

            # Mở cửa ở sàn -> không thể bán được, tiếp tục giữ chờ phiên sau
            if o[j] <= cprev[j] * (1.0 - limit + 0.002):
                continue

            # Kiểm tra xác suất khớp ATO nếu cấu hình < 1.0
            if ato_fill_prob < 1.0 and rng is not None:
                if rng.random() > ato_fill_prob:
                    continue

            px = o[j] * (1.0 - sell_cost)
            cash += P["sh"] * px
            trades.append((t - P["ei"], float(px / P["px0"] - 1.0)))
            del pos[j]
            pend_exit.discard(j)

        # ---------------------------------------------------------------------
        # 2) Khớp lệnh MUA tại giá mở cửa (ATO) phiên t
        # ---------------------------------------------------------------------
        if pend_entry:
            eqv = cash + sum(P["sh"] * P["last"] for P in pos.values())
            for j in pend_entry:
                if len(pos) >= max_pos:
                    break
                if j in pos or np.isnan(o[j]) or np.isnan(cprev[j]) or np.isnan(F.atr[t - 1][j]):
                    continue
                # Mở cửa ở trần -> không thể mua được
                if o[j] >= cprev[j] * (1.0 + limit - 0.002):
                    continue

                # Kiểm tra xác suất khớp ATO
                if ato_fill_prob < 1.0 and rng is not None:
                    if rng.random() > ato_fill_prob:
                        continue

                risk_ps = ks * F.atr[t - 1][j]
                sh = cfg.get("risk_pct", 0.01) * eqv / risk_ps if risk_ps > 0 else 0
                cap = min(max_w * eqv, adtv_frac * F.adtv[t - 1][j])
                sh = min(sh, cap / o[j], cash / (o[j] * (1.0 + buy_cost)))
                sh = np.floor(sh / lot) * lot

                if sh < lot:
                    continue

                cash -= sh * o[j] * (1.0 + buy_cost)
                pos[j] = dict(sh=sh, ei=t, px0=o[j] * (1.0 + buy_cost), hc=o[j], last=o[j])

        pend_entry = []

        # ---------------------------------------------------------------------
        # 3) Cuối phiên t: Cập nhật giá đóng cửa, sinh tín hiệu thoát / vào lệnh
        # ---------------------------------------------------------------------
        c = F.C[t]

        # Kiểm tra hủy niêm yết (nếu dữ liệu mã chuyển thành NaN liên tục)
        delisted_symbols = []
        for j, P in list(pos.items()):
            if np.isnan(c[j]):
                if delist_haircut > 0.0:
                    # Thanh lý cưỡng bức với haircut
                    rec_px = P["last"] * (1.0 - delist_haircut)
                    cash += P["sh"] * rec_px
                    trades.append((t - P["ei"], float(rec_px / P["px0"] - 1.0)))
                    delisted_symbols.append(j)
                continue

            P["last"] = c[j]
            P["hc"] = max(P["hc"], c[j])

            if j in pend_exit:
                continue

            # Điều kiện thoát lệnh: đóng cửa < đáy kênh N_out hoặc trailing stop ATR
            if c[j] < ll[t][j] or (k < 50 and c[j] < P["hc"] - k * F.atr[t][j]):
                pend_exit.add(j)

        for j in delisted_symbols:
            del pos[j]
            pend_exit.discard(j)

        eq[t] = cash + sum(P["sh"] * P["last"] for P in pos.values())

        # Sinh ứng viên vào lệnh cho phiên tiếp theo
        if len(pos) < max_pos:
            cand = np.where(sig[t])[0]
            cand = [j for j in cand[np.argsort(-strength[t][cand])] if j not in pos]
            pend_entry = cand[: max_pos * 2]

    ret = eq[i0:i1] / np.r_[eq[i0 - 1], eq[i0:i1 - 1]] - 1.0
    return ret, trades


def detailed_backtest(
    F: FeatureEngine,
    p: Tuple,
    cfg: Dict[str, Any],
    i0: int,
    i1: int,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Thực thi backtest chi tiết và ghi nhận toàn bộ nhật ký lệnh (Trade Ledger)
    đầy đủ ngày mua, giá mua, ngày bán, giá bán, PnL %, PnL VND, lý do thoát.
    """
    n_in, n_out, m, vm, k, clv, rs = p
    mode = cfg.get("mode", "brk")
    min_adtv = cfg.get("min_adtv", 1e10)

    # 1. Sinh ma trận tín hiệu
    if mode == "brk":
        sig, strength = generate_breakout_signals(F, n_in, m, vm, clv, rs, min_adtv)
    else:
        sig, strength = generate_pullback_signals(F, n_in, m, vm, clv, rs, min_adtv)

    ll = F.exit_line(mode, n_out)
    T = F.C.shape[0]
    i0 = max(i0, 1)
    i1 = min(i1, T)

    cash = float(cfg.get("init_cash", 1e9))
    min_hold = int(cfg.get("min_hold", 3))
    limit = float(cfg.get("limit", 0.07))
    buy_cost = float(cfg.get("buy_cost", 0.0030))
    sell_cost = float(cfg.get("sell_cost", 0.0040))
    max_pos = int(cfg.get("max_pos", 10))
    max_w = float(cfg.get("max_w", 0.15))
    adtv_frac = float(cfg.get("adtv_frac", 0.03))
    lot = int(cfg.get("lot", 100))
    delist_haircut = float(cfg.get("delist_haircut", 0.0))
    ato_fill_prob = float(cfg.get("ato_fill_prob", 1.0))

    pos: Dict[int, Dict[str, Any]] = {}
    pend_exit: Dict[int, str] = {}  # symbol_idx -> reason
    pend_entry: List[int] = []
    trade_records: List[Dict[str, Any]] = []

    eq = np.full(T, np.nan)
    eq[i0 - 1] = cash
    ks = k if k < 50 else 3.0
    dates = F.dates

    for t in range(i0, i1):
        o, cprev = F.O[t], F.C[t - 1]

        # 1. Khớp lệnh THOÁT tại ATO phiên t
        for j in list(pend_exit.keys()):
            P = pos[j]
            if (t - P["ei"]) < min_hold or np.isnan(o[j]) or np.isnan(cprev[j]):
                continue
            if o[j] <= cprev[j] * (1.0 - limit + 0.002):
                continue
            if ato_fill_prob < 1.0 and rng is not None:
                if rng.random() > ato_fill_prob:
                    continue

            exit_reason = pend_exit[j]
            px = o[j] * (1.0 - sell_cost)
            cash += P["sh"] * px
            pnl_pct = float(px / P["px0"] - 1.0)
            pnl_vnd = float(P["sh"] * (px - P["px0"]))

            trade_records.append({
                "trade_id": f"TRD-{dates[P['ei']].strftime('%Y%m%d')}-{F.symbols[j]}",
                "symbol": F.symbols[j],
                "entry_date": str(dates[P["ei"]].date()),
                "entry_price": round(float(P["px0"]), 1),
                "shares": int(P["sh"]),
                "exit_date": str(dates[t].date()),
                "exit_price": round(float(px), 1),
                "pnl_pct": round(pnl_pct * 100, 2),
                "pnl_vnd": round(pnl_vnd, 0),
                "holding_days": int(t - P["ei"]),
                "exit_reason": exit_reason,
                "status": "CLOSED"
            })
            del pos[j]
            del pend_exit[j]

        # 2. Khớp lệnh MUA tại ATO phiên t
        if pend_entry:
            eqv = cash + sum(P["sh"] * P["last"] for P in pos.values())
            for j in pend_entry:
                if len(pos) >= max_pos:
                    break
                if j in pos or np.isnan(o[j]) or np.isnan(cprev[j]) or np.isnan(F.atr[t - 1][j]):
                    continue
                if o[j] >= cprev[j] * (1.0 + limit - 0.002):
                    continue
                if ato_fill_prob < 1.0 and rng is not None:
                    if rng.random() > ato_fill_prob:
                        continue

                risk_ps = ks * F.atr[t - 1][j]
                sh = cfg.get("risk_pct", 0.01) * eqv / risk_ps if risk_ps > 0 else 0
                cap = min(max_w * eqv, adtv_frac * F.adtv[t - 1][j])
                sh = min(sh, cap / o[j], cash / (o[j] * (1.0 + buy_cost)))
                sh = np.floor(sh / lot) * lot

                if sh < lot:
                    continue

                cash -= sh * o[j] * (1.0 + buy_cost)
                pos[j] = {
                    "sh": sh,
                    "ei": t,
                    "px0": o[j] * (1.0 + buy_cost),
                    "hc": o[j],
                    "last": o[j]
                }

        pend_entry = []

        # 3. Cuối phiên t: Cập nhật giá đóng cửa, sinh tín hiệu thoát / vào lệnh
        c = F.C[t]
        delisted_symbols = []
        for j, P in list(pos.items()):
            if np.isnan(c[j]):
                if delist_haircut > 0.0:
                    rec_px = P["last"] * (1.0 - delist_haircut)
                    cash += P["sh"] * rec_px
                    trade_records.append({
                        "trade_id": f"TRD-{dates[P['ei']].strftime('%Y%m%d')}-{F.symbols[j]}",
                        "symbol": F.symbols[j],
                        "entry_date": str(dates[P["ei"]].date()),
                        "entry_price": round(float(P["px0"]), 1),
                        "shares": int(P["sh"]),
                        "exit_date": str(dates[t].date()),
                        "exit_price": round(float(rec_px), 1),
                        "pnl_pct": round((rec_px / P["px0"] - 1.0) * 100, 2),
                        "pnl_vnd": round(P["sh"] * (rec_px - P["px0"]), 0),
                        "holding_days": int(t - P["ei"]),
                        "exit_reason": "Hủy niêm yết (Haircut thanh lý)",
                        "status": "CLOSED"
                    })
                    delisted_symbols.append(j)
                continue

            P["last"] = c[j]
            P["hc"] = max(P["hc"], c[j])

            if j in pend_exit:
                continue

            # Điều kiện thoát lệnh
            if c[j] < ll[t][j]:
                pend_exit[j] = f"Thủng đáy Donchian {n_out}P ({ll[t][j]:,.0f})"
            elif k < 50 and c[j] < P["hc"] - k * F.atr[t][j]:
                trailing_val = P["hc"] - k * F.atr[t][j]
                pend_exit[j] = f"Chạm Trailing Stop ATR ({trailing_val:,.0f})"

        for j in delisted_symbols:
            del pos[j]
            if j in pend_exit:
                del pend_exit[j]

        eq[t] = cash + sum(P["sh"] * P["last"] for P in pos.values())

        if len(pos) < max_pos:
            cand = np.where(sig[t])[0]
            cand = [j for j in cand[np.argsort(-strength[t][cand])] if j not in pos]
            pend_entry = cand[: max_pos * 2]

    # Ghi nhận các vị thế còn đang mở tại thời điểm kết thúc
    for j, P in pos.items():
        curr_pnl_pct = (P["last"] / P["px0"] - 1.0) * 100
        curr_pnl_vnd = P["sh"] * (P["last"] - P["px0"])
        trade_records.append({
            "trade_id": f"TRD-{dates[P['ei']].strftime('%Y%m%d')}-{F.symbols[j]}",
            "symbol": F.symbols[j],
            "entry_date": str(dates[P["ei"]].date()),
            "entry_price": round(float(P["px0"]), 1),
            "shares": int(P["sh"]),
            "exit_date": "-",
            "exit_price": round(float(P["last"]), 1),
            "pnl_pct": round(curr_pnl_pct, 2),
            "pnl_vnd": round(curr_pnl_vnd, 0),
            "holding_days": int(i1 - 1 - P["ei"]),
            "exit_reason": "Vị thế đang mở",
            "status": "OPEN"
        })

    ret = eq[i0:i1] / np.r_[eq[i0 - 1], eq[i0:i1 - 1]] - 1.0

    # Thống kê tổng hợp lệnh
    closed_trades = [tr for tr in trade_records if tr["status"] == "CLOSED"]
    winning_trades = [tr for tr in closed_trades if tr["pnl_pct"] > 0]
    losing_trades = [tr for tr in closed_trades if tr["pnl_pct"] < 0]

    win_rate = (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0.0
    total_gain = sum(tr["pnl_vnd"] for tr in winning_trades)
    total_loss = abs(sum(tr["pnl_vnd"] for tr in losing_trades))
    profit_factor = (total_gain / total_loss) if total_loss > 0 else (99.0 if total_gain > 0 else 1.0)

    summary = {
        "total_trades": len(closed_trades),
        "open_trades": len(trade_records) - len(closed_trades),
        "win_trades": len(winning_trades),
        "loss_trades": len(losing_trades),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "total_net_pnl_vnd": round(sum(tr["pnl_vnd"] for tr in trade_records), 0),
        "max_win_pct": round(max([tr["pnl_pct"] for tr in closed_trades], default=0.0), 2),
        "max_loss_pct": round(min([tr["pnl_pct"] for tr in closed_trades], default=0.0), 2),
        "avg_hold_days": round(float(np.mean([tr["holding_days"] for tr in closed_trades])), 1) if closed_trades else 0.0,
    }

    return ret, trade_records, summary
