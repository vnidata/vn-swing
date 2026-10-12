"""
Module Walk-Forward Optimization & Plateau Smoothing.
Bảo vệ phân vùng Holdout nghiêm ngặt (chặn truy cập >= holdout_start).
Ghi nhận đầy đủ thông tin thử nghiệm vào registry/trials.jsonl để tính DSR.
"""
from datetime import datetime
import itertools
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from vnswing.backtest.engine import backtest
from vnswing.backtest.metrics import deflated_sharpe, perf
from vnswing.features.indicators import FeatureEngine


def smooth_scores(axes: List[List[Any]], scores: Dict[Tuple, float]) -> Dict[Tuple, float]:
    """
    Tính điểm làm mượt cao nguyên (Plateau Smoothing):
    Điểm của mỗi tổ hợp = trung bình Sharpe của chính nó và các láng giềng 1 bước trên từng trục.
    Giúp chọn vùng tham số ổn định, tránh các đỉnh nhọn overfit.
    """
    out = {}
    for p, s in scores.items():
        vals = [s]
        for d, ax in enumerate(axes):
            i = ax.index(p[d])
            for di in (-1, 1):
                if 0 <= i + di < len(ax):
                    q = list(p)
                    q[d] = ax[i + di]
                    neighbor_key = tuple(q)
                    if neighbor_key in scores:
                        vals.append(scores[neighbor_key])
        out[p] = float(np.mean(vals))
    return out


def run_grid(
    F: FeatureEngine,
    grid: List[Tuple],
    cfg: Dict[str, Any],
    i0: int,
    i1: int,
    n_jobs: int = 1,
) -> Dict[Tuple, float]:
    """Chạy backtest cho toàn bộ lưới tham số trong một khoảng thời gian."""
    min_trades = cfg.get("min_trades", 20)
    rf = cfg.get("rf", 0.05)

    def one(p: Tuple) -> Tuple[Tuple, float]:
        ret, tr = backtest(F, p, cfg, i0, i1)
        s = perf(ret, rf)["sharpe"] if len(tr) >= min_trades else -5.0
        return p, float(s)

    if n_jobs > 1:
        from joblib import Parallel, delayed
        res = Parallel(n_jobs=n_jobs)(delayed(one)(p) for p in grid)
    else:
        res = [one(p) for p in grid]
    return dict(res)


def walk_forward(
    F: FeatureEngine,
    axes: List[List[Any]],
    cfg: Dict[str, Any],
    train_years: int = 3,
    test_years: int = 1,
    n_jobs: int = 1,
    holdout_start: Optional[str] = "2025-01-01",
    unlock_holdout: bool = False,
    registry_path: Optional[Path] = None,
    variant_id: str = "A1",
) -> Tuple[pd.Series, List[Tuple], Dict[Tuple, float], int]:
    """
    Quy trình Walk-Forward trượt từng năm:
    - Khóa cứng holdout nếu chạm vào ngày holdout_start mà chưa có unlock_holdout.
    - Lưu vết trial vào registry.
    """
    grid = list(itertools.product(*axes))
    yrs = F.dates.year.values
    uy = sorted(set(yrs))
    first = lambda y: int(np.argmax(yrs >= y)) if (yrs >= y).any() else len(yrs)

    oos_ret = []
    picks = []
    last_scores = None

    ty = uy[0] + train_years

    while ty <= uy[-1]:
        # Kiểm tra hàng rào bảo vệ Holdout
        if holdout_start is not None and not unlock_holdout:
            holdout_dt = pd.to_datetime(holdout_start)
            if pd.to_datetime(f"{ty}-01-01") >= holdout_dt:
                print(f"[HOLDOUT LOCK] Dừng walk-forward trước năm {ty} vì thuộc vùng Holdout ({holdout_start}). Cần --unlock-holdout để mở.")
                break

        i_tr0 = first(ty - train_years)
        i_tr1 = first(ty)
        i_te1 = first(ty + test_years)

        # Chạy grid trên tập Train
        scores = run_grid(F, grid, cfg, i_tr0, i_tr1, n_jobs)
        sm = smooth_scores(axes, scores)
        best = max(sm, key=sm.get)

        # Kiểm định Out-Of-Sample trên tập Test
        ret, tr = backtest(F, best, cfg, i_tr1, i_te1)
        test_dates = F.dates[max(i_tr1, 1) : min(i_te1, len(F.dates))]
        oos_ret.append(pd.Series(ret, index=test_dates))

        train_sharpe = scores[best]
        smooth_sharpe = sm[best]
        oos_metrics = perf(ret, cfg.get("rf", 0.05))
        oos_sharpe = oos_metrics["sharpe"]

        picks.append((ty, best, train_sharpe, smooth_sharpe, oos_sharpe, len(tr)))
        last_scores = scores

        # Ghi log trial vào registry/trials.jsonl
        if registry_path is not None:
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            trial_record = {
                "trial_id": f"{variant_id}-{ty}",
                "variant": variant_id,
                "mode": cfg.get("mode", "brk"),
                "params": {
                    "n_in": best[0],
                    "n_out": best[1],
                    "m": best[2],
                    "vm": best[3],
                    "k": best[4],
                    "clv": best[5],
                    "rs": best[6],
                },
                "window": {
                    "train": [str(F.dates[i_tr0].date()), str(F.dates[i_tr1 - 1].date())],
                    "test": [str(F.dates[i_tr1].date()), str(F.dates[min(i_te1 - 1, len(F.dates) - 1)].date())],
                },
                "metrics": {
                    "sharpe_train": round(train_sharpe, 4),
                    "sharpe_smooth": round(smooth_sharpe, 4),
                    "sharpe_oos": round(oos_sharpe, 4),
                    "n_trades_oos": len(tr),
                    "cagr_oos": round(oos_metrics["cagr"], 4),
                    "mdd_oos": round(oos_metrics["mdd"], 4),
                },
                "created_at": datetime.now().isoformat(),
            }
            with open(registry_path, "a", encoding="utf-8") as rf:
                rf.write(json.dumps(trial_record) + "\n")

        ty += test_years

    combined_oos = pd.concat(oos_ret) if oos_ret else pd.Series(dtype=float)
    return combined_oos, picks, last_scores, len(grid)
