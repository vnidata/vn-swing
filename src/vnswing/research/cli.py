"""
CLI nghiên cứu và tối ưu hóa Walk-Forward cho vnswing.
Hỗ trợ tham số bảo vệ Holdout (--holdout-start, --unlock-holdout).
"""
import argparse
from pathlib import Path
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
import yaml

from vnswing.features.indicators import FeatureEngine
from vnswing.backtest.metrics import deflated_sharpe, perf
from vnswing.research.walkforward import walk_forward


def parse_args(args=None):
    ap = argparse.ArgumentParser(description="V-DBO Walk-Forward Research Engine")
    ap.add_argument("--data", type=str, help="Đường dẫn file dữ liệu giá (parquet hoặc csv)")
    ap.add_argument("--index", type=str, help="Đường dẫn file chỉ số VN-Index (parquet hoặc csv)")
    ap.add_argument("--price-scale", type=float, default=1.0, help="1000 nếu giá tính theo nghìn đồng")
    ap.add_argument("--config", type=str, default="configs/base.yaml", help="Đường dẫn file config")
    ap.add_argument("--train", type=int, default=3, help="Số năm huấn luyện")
    ap.add_argument("--test", type=int, default=1, help="Số năm kiểm định OOS")
    ap.add_argument("--jobs", type=int, default=1, help="Số luồng song song")
    ap.add_argument("--synthetic", action="store_true", help="Dùng dữ liệu mô phỏng để kiểm tra")
    ap.add_argument("--fast", action="store_true", help="Lưới nhỏ để chạy nhanh")
    ap.add_argument("--mode", default="brk", choices=["brk", "pb"], help="Chế độ chiến lược (brk hoặc pb)")
    ap.add_argument("--start-date", type=str, default=None, help="Ngày bắt đầu (YYYY-MM-DD)")
    ap.add_argument("--end-date", type=str, default=None, help="Ngày kết thúc (YYYY-MM-DD)")
    ap.add_argument("--holdout-start", type=str, default="2025-01-01", help="Mốc khóa Holdout cứng")
    ap.add_argument("--unlock-holdout", action="store_true", help="Mở khóa phân vùng Holdout (chỉ dùng ở Gate G4)")
    ap.add_argument("--variant", type=str, default="A1", help="Mã định danh biến thể thử nghiệm")
    return ap.parse_args(args)


def main(args=None):
    a = parse_args(args)
    root = Path(__file__).resolve().parent.parent.parent.parent

    # Đọc cấu hình
    cfg_path = Path(a.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    
    with open(cfg_path, "r", encoding="utf-8") as f:
        full_cfg = yaml.safe_load(f)

    cfg = {
        "mode": a.mode,
        "init_cash": float(full_cfg["portfolio"]["init_cash"]),
        "risk_pct": float(full_cfg["portfolio"]["risk_pct"]),
        "max_pos": int(full_cfg["portfolio"]["max_positions"]),
        "max_w": float(full_cfg["portfolio"]["max_weight"]),
        "rf": float(full_cfg["portfolio"]["rf_annual"]),
        "min_hold": int(full_cfg["market"]["min_hold_sessions"]),
        "limit": float(full_cfg["market"]["price_limit"]),
        "lot": int(full_cfg["market"]["lot"]),
        "buy_cost": float(full_cfg["costs"]["buy_cost"]),
        "sell_cost": float(full_cfg["costs"]["sell_cost"]),
        "min_adtv": float(full_cfg["universe"]["min_adtv_vnd"]),
        "adtv_frac": float(full_cfg["universe"]["adtv_frac_cap"]),
        "delist_haircut": float(full_cfg["execution"]["delist_haircut"]),
        "ato_fill_prob": float(full_cfg["execution"]["ato_fill_prob"]),
        "min_trades": int(full_cfg["research"]["min_trades_train"]),
    }

    # Kiểm tra bảo vệ Holdout nếu end-date chạm holdout mà không có unlock
    if a.end_date is not None and a.holdout_start is not None and not a.unlock_holdout:
        if pd.to_datetime(a.end_date) >= pd.to_datetime(a.holdout_start):
            raise PermissionError(
                f"[HOLDOUT VIOLATION] Yêu cầu end-date ({a.end_date}) vi phạm phân vùng Holdout "
                f"được khóa từ ({a.holdout_start}). Bạn phải có cờ --unlock-holdout được người dùng ký duyệt tại Gate G4."
            )

    if a.synthetic:
        from legacy.vn_donchian_wf import synthetic
        df_px, df_idx = synthetic()
        df_px["date"] = pd.to_datetime(df_px["date"])
        df_idx["date"] = pd.to_datetime(df_idx["date"])
        W = {
            c: df_px.pivot(index="date", columns="symbol", values=c).sort_index()
            for c in ["open", "high", "low", "close", "volume"]
        }
        idx_close = df_idx.set_index("date")["close"].sort_index().reindex(W["close"].index).ffill()
    else:
        if not a.data or not a.index:
            raise ValueError("Cần cung cấp --data và --index nếu không dùng --synthetic.")
        df_px = pd.read_parquet(a.data) if a.data.endswith(".parquet") else pd.read_csv(a.data)
        df_px["date"] = pd.to_datetime(df_px["date"])
        W = {
            c: df_px.pivot(index="date", columns="symbol", values=c).sort_index()
            for c in ["open", "high", "low", "close", "volume"]
        }
        for c in ["open", "high", "low", "close"]:
            W[c] = W[c] * a.price_scale
        df_idx = pd.read_parquet(a.index) if a.index.endswith(".parquet") else pd.read_csv(a.index)
        df_idx["date"] = pd.to_datetime(df_idx["date"])
        idx_close = df_idx.set_index("date")["close"].sort_index().reindex(W["close"].index).ffill()

    # Cắt theo khoảng ngày nếu có
    if a.start_date:
        for c in W:
            W[c] = W[c].loc[a.start_date :]
        idx_close = idx_close.loc[a.start_date :]
    if a.end_date:
        for c in W:
            W[c] = W[c].loc[: a.end_date]
        idx_close = idx_close.loc[: a.end_date]

    F = FeatureEngine(W, idx_close)

    # Đọc lưới tham số
    grid_file = root / "configs" / (f"grid_{a.mode}.yaml")
    with open(grid_file, "r", encoding="utf-8") as gf:
        grid_spec = yaml.safe_load(gf)

    axes_spec = grid_spec["fast_axes"] if a.fast else grid_spec["axes"]
    if a.mode == "brk":
        axes = [
            axes_spec["n_in"],
            axes_spec["n_out"],
            axes_spec["m"],
            axes_spec["vm"],
            axes_spec["k"],
            axes_spec["clv"],
            axes_spec["rs"],
        ]
    else:
        axes = [
            axes_spec["n_in"],
            axes_spec["n_out"],
            axes_spec["m"],
            axes_spec["vm"],
            axes_spec["k"],
            axes_spec["clv"],
            axes_spec["rs"],
        ]

    registry_file = root / "registry" / "trials.jsonl"
    oos, picks, last_scores, n_trials = walk_forward(
        F,
        axes,
        cfg,
        a.train,
        a.test,
        a.jobs,
        holdout_start=a.holdout_start,
        unlock_holdout=a.unlock_holdout,
        registry_path=registry_file,
        variant_id=a.variant,
    )

    print(f"\n--- KẾT QUẢ WALK-FORWARD ({a.variant} - {a.mode}) ---")
    print("Năm | Tham số được chọn (n_in, n_out, m, vm, k, clv, rs) | Sharpe Train | Smooth | Sharpe OOS | Số lệnh OOS")
    for y, p, s, sm, so, n in picks:
        print(f"  {y} | {p} | {s:5.2f} | {sm:5.2f} | {so:5.2f} | {n}")

    if len(picks) > 0 and not oos.empty:
        sh = np.array([x[4] for x in picks])
        print(f"\nPhân phối Sharpe OOS theo năm:")
        print(f"  - Trung vị: {np.median(sh):.2f}")
        print(f"  - Tứ phân vị: {np.percentile(sh, 25):.2f} .. {np.percentile(sh, 75):.2f}")
        print(f"  - Tỷ lệ năm có Sharpe dương: {np.mean(sh > 0):.0%}")
        print(f"  - Tổng số năm kiểm định: {len(sh)}")

        st = perf(oos.values, cfg["rf"])
        ix = F.idx.pct_change().reindex(oos.index)
        sb = perf(ix.values, cfg["rf"])
        var_sr = np.var([v / np.sqrt(252) for v in last_scores.values() if v > -5]) if last_scores else 0.0001
        dsr = deflated_sharpe(oos.values, n_trials, var_sr)

        print(f"\nHiệu suất OOS gộp toàn bộ giai đoạn:")
        print(f"  - CAGR ròng: {st['cagr']:.1%}")
        print(f"  - Sharpe Ratio: {st['sharpe']:.2f}")
        print(f"  - Volatility: {st['vol']:.1%}")
        print(f"  - Max Drawdown: {st['mdd']:.1%}")
        print(f"  - Calmar Ratio: {st['calmar']:.2f}")
        print(f"Chỉ số tham chiếu VN-Index Buy & Hold cùng kỳ:")
        print(f"  - CAGR: {sb['cagr']:.1%}")
        print(f"  - Sharpe: {sb['sharpe']:.2f}")
        print(f"  - Max Drawdown: {sb['mdd']:.1%}")
        print(f"\nDeflated Sharpe Ratio (DSR, N={n_trials}): {dsr:.2f}")

    return oos, picks


if __name__ == "__main__":
    main()
