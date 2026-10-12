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
