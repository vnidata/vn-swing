"""
Module nghiên cứu có kiểm soát (Ablation Study) ma trận 11 biến thể (Phase 3).
Tuân thủ tiêu chí Gate G3 và ghi nhận toàn bộ trial vào registry/trials.jsonl.
"""
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
import yaml

from vnswing.backtest.engine import backtest
from vnswing.backtest.metrics import deflated_sharpe, perf, trade_stats
from vnswing.features.indicators import FeatureEngine
from vnswing.research.walkforward import smooth_scores, walk_forward

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def run_benchmarks(F: FeatureEngine, cfg: Dict[str, Any], start_year: int = 2015, end_year: int = 2024):
    """
    Chạy 3 benchmark:
    - B0: VN-Index buy & hold
    - B1: Equal-weight Eligible Universe (tái cân bằng hàng quý)
    - B2: Trend MA20/50 benchmark
    """
    years = F.dates.year.values
    first_idx = int(np.argmax(years >= start_year))
    last_idx = int(np.argmax(years > end_year)) if (years > end_year).any() else len(years)

    # B0: VN-Index
    idx_ret = F.idx.pct_change().iloc[first_idx:last_idx].fillna(0.0)

    # B1: Equal-weight eligible universe (daily return of eligible stocks)
    eligible = (F.adtv >= cfg["min_adtv"]) & ~np.isnan(F.C)
    ret_stocks = pd.DataFrame(F.C / np.vstack([np.full((1, F.C.shape[1]), np.nan), F.C[:-1]]) - 1.0, index=F.dates, columns=F.symbols)
    ret_stocks = ret_stocks.where(eligible)
    b1_ret = ret_stocks.mean(axis=1).iloc[first_idx:last_idx].fillna(0.0)

    # B2: MA20/50 trend benchmark
    s20 = F.sma(20)
    s50 = F.sma(50)
    trend_sig = (F.C > s50) & (s20 > s50) & eligible
    ret_trend = ret_stocks.where(trend_sig)
    b2_ret = ret_trend.mean(axis=1).iloc[first_idx:last_idx].fillna(0.0)

    return {
        "B0": idx_ret,
        "B1": b1_ret,
        "B2": b2_ret,
    }


def define_ablation_axes():
    """Định nghĩa lưới tham số cho 8 biến thể chiến lược A1-A6, P1, P2."""
    return {
        "A1": {
            "mode": "brk",
            "desc": "Breakout thuần (Lõi)",
            "axes": [[20, 30, 40, 55], [10, 20], [0], [0.0], [99.0], [0.0], [0.0]],
        },
        "A2": {
            "mode": "brk",
            "desc": "A1 + Regime VN-Index",
            "axes": [[20, 30, 40, 55], [10, 20], [100, 150], [0.0], [99.0], [0.0], [0.0]],
        },
        "A3": {
            "mode": "brk",
            "desc": "A2 + Volume Filter",
            "axes": [[20, 30, 40, 55], [10, 20], [100, 150], [1.3], [99.0], [0.0], [0.0]],
        },
        "A4": {
            "mode": "brk",
            "desc": "A3 + CLV Filter",
            "axes": [[20, 30, 40, 55], [10, 20], [100, 150], [1.3], [99.0], [0.65], [0.0]],
        },
        "A5": {
            "mode": "brk",
            "desc": "A4 + RS Rank Filter",
            "axes": [[20, 30, 40, 55], [10, 20], [100, 150], [1.3], [99.0], [0.65], [0.5]],
        },
        "A6": {
            "mode": "brk",
            "desc": "A5 + Chandelier ATR Stop (Full Breakout)",
            "axes": [[20, 30, 40, 55], [10, 20], [100, 150], [1.3], [3.0], [0.65], [0.5]],
        },
        "P1": {
            "mode": "pb",
            "desc": "Pullback thuần (Lõi)",
            "axes": [[10, 15, 20], [20, 50], [0], [0.0], [99.0], [0.0], [0.0]],
        },
        "P2": {
            "mode": "pb",
            "desc": "Full Pullback (+ Regime + Vol + CLV + RS + Stop)",
            "axes": [[10, 15, 20], [20, 50], [100], [1.5], [2.0, 3.0], [0.65], [0.5]],
        },
    }


def run_ablation_study():
    print("=== [PHASE 3] ABLATION STUDY & CONTROLLED WALK-FORWARD ===")
    t0 = time.time()

    # Đọc cấu hình
    with open(ROOT / "configs" / "base.yaml", "r", encoding="utf-8") as f:
        full_cfg = yaml.safe_load(f)

    cfg = {
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

    # Đọc dữ liệu
    print("[1/4] Đang nạp dữ liệu giá và chỉ số HOSE...")
    df_px = pd.read_parquet(ROOT / "data" / "adjusted" / "prices.parquet")
    df_idx = pd.read_parquet(ROOT / "data" / "adjusted" / "index.parquet")

    W = {
        c: df_px.pivot(index="date", columns="symbol", values=c).sort_index()
        for c in ["open", "high", "low", "close", "volume"]
    }
    df_idx["date"] = pd.to_datetime(df_idx["date"])
    idx_close = df_idx.set_index("date")["close"].sort_index().reindex(W["close"].index).ffill()

    F = FeatureEngine(W, idx_close)
    print(f" -> FeatureEngine sẵn sàng trong {time.time() - t0:.2f}s!")

    # 1. Chạy Benchmark B0, B1, B2
    print("[2/4] Tính toán các benchmark tham chiếu (B0, B1, B2)...")
    benchmarks = run_benchmarks(F, cfg, start_year=2015, end_year=2024)
    bench_results = {}
    for b_id, b_ret in benchmarks.items():
        bench_results[b_id] = perf(b_ret.values, cfg["rf"])

    # 2. Chạy 8 biến thể chiến lược Walk-forward (2012-2024, train 3, test 1)
    print("[3/4] Chạy walk-forward 8 biến thể A1-A6, P1, P2 (khoảng OOS 2015-2024)...")
    variants = define_ablation_axes()
    variant_results = {}
    variant_picks = {}
    variant_sensitivity = {}
    reg_file = ROOT / "registry" / "trials.jsonl"

    for var_id, var_info in variants.items():
        t_var = time.time()
        var_cfg = dict(cfg)
        var_cfg["mode"] = var_info["mode"]

        # Chạy walk forward ở mức phí chuẩn 1.0x
        oos_ret, picks, last_scores, n_grid = walk_forward(
            F,
            var_info["axes"],
            var_cfg,
            train_years=3,
            test_years=1,
            n_jobs=4,
            holdout_start="2025-01-01",
            unlock_holdout=False,
            registry_path=reg_file,
            variant_id=var_id,
        )

        metrics = perf(oos_ret.values, cfg["rf"])
        sh_years = np.array([x[4] for x in picks]) if picks else np.array([])
        
        # Độ nhạy chi phí x1.5 và x2.0
        cfg_15 = dict(var_cfg)
        cfg_15["buy_cost"] = cfg["buy_cost"] * 1.5
        cfg_15["sell_cost"] = cfg["sell_cost"] * 1.5
        oos_15, _, _, _ = walk_forward(F, var_info["axes"], cfg_15, 3, 1, 4, "2025-01-01", False)
        sr_15 = perf(oos_15.values, cfg["rf"])["sharpe"]

        cfg_20 = dict(var_cfg)
        cfg_20["buy_cost"] = cfg["buy_cost"] * 2.0
        cfg_20["sell_cost"] = cfg["sell_cost"] * 2.0
        oos_20, _, _, _ = walk_forward(F, var_info["axes"], cfg_20, 3, 1, 4, "2025-01-01", False)
        sr_20 = perf(oos_20.values, cfg["rf"])["sharpe"]

        total_trades = sum(x[5] for x in picks)
        
        variant_results[var_id] = {
            "desc": var_info["desc"],
            "metrics": metrics,
            "total_trades": total_trades,
            "sr_median": float(np.median(sh_years)) if len(sh_years) else 0.0,
            "sr_q25": float(np.percentile(sh_years, 25)) if len(sh_years) else 0.0,
            "sr_q75": float(np.percentile(sh_years, 75)) if len(sh_years) else 0.0,
            "pos_pct": float(np.mean(sh_years > 0)) if len(sh_years) else 0.0,
            "n_years": len(sh_years),
            "sr_10": metrics["sharpe"],
            "sr_15": sr_15,
            "sr_20": sr_20,
            "oos_ret": oos_ret,
        }
        variant_picks[var_id] = picks
        print(f" -> [{var_id}] {var_info['desc']} hoàn thành trong {time.time() - t_var:.1f}s | Sharpe 1.0x: {metrics['sharpe']:.2f}, 1.5x: {sr_15:.2f}, Lệnh: {total_trades}")

    # 3. Tính DSR cộng dồn từ registry
    with open(reg_file, "r", encoding="utf-8") as rf:
        trials = [json.loads(line) for line in rf]
    total_N = len(trials)
    all_oos_sharpes = [t["metrics"]["sharpe_oos"] for t in trials if t["metrics"].get("sharpe_oos") is not None]
    var_sr_daily = np.var([s / np.sqrt(252) for s in all_oos_sharpes]) if all_oos_sharpes else 0.0001

    for var_id in variant_results:
        oos_v = variant_results[var_id]["oos_ret"].values
        dsr_val = deflated_sharpe(oos_v, total_N, var_sr_daily)
        variant_results[var_id]["dsr"] = dsr_val

    # 4. Sinh báo cáo reports/ablation.md và reports/stability.md
    print("[4/4] Xuất bản báo cáo reports/ablation.md và reports/stability.md...")
    
    # Báo cáo Ablation
    ablation_md = f"""# Báo Cáo Ma Trận Đối Chứng (Ablation Matrix Report)

* **Thời điểm chạy:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
* **Khoảng thời gian OOS:** 2015-01-01 đến 2024-12-31 (10 năm walk-forward OOS)
* **Tổng số thử nghiệm tích lũy (N cho DSR):** {total_N:,} trials
* **Chuẩn chi phí:** Mua 0.30%, Bán 0.40% (bao gồm thuế 0.1% và trượt giá)

## 1. Bảng Hiệu Suất 11 Biến Thể Đối Chứng

| ID | Biến Thể | CAGR Ròng | Sharpe OOS | MaxDD | Calmar | Số Lệnh | Sharpe Dương | DSR (N={total_N}) | Phí 1.5x Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| **B0** | VN-Index Buy & Hold | {bench_results['B0']['cagr']:.1%} | {bench_results['B0']['sharpe']:.2f} | {bench_results['B0']['mdd']:.1%} | {bench_results['B0']['calmar']:.2f} | 0 | - | - | - |
| **B1** | Equal-weight Universe | {bench_results['B1']['cagr']:.1%} | {bench_results['B1']['sharpe']:.2f} | {bench_results['B1']['mdd']:.1%} | {bench_results['B1']['calmar']:.2f} | 0 | - | - | - |
| **B2** | Trend MA20/50 Benchmark | {bench_results['B2']['cagr']:.1%} | {bench_results['B2']['sharpe']:.2f} | {bench_results['B2']['mdd']:.1%} | {bench_results['B2']['calmar']:.2f} | - | - | - | - |
"""
    for v_id in ["A1", "A2", "A3", "A4", "A5", "A6", "P1", "P2"]:
        info = variant_results[v_id]
        m = info["metrics"]
        ablation_md += f"| **{v_id}** | {info['desc']} | {m['cagr']:.1%} | **{m['sharpe']:.2f}** | {m['mdd']:.1%} | {m['calmar']:.2f} | {info['total_trades']} | {info['pos_pct']:.0%} | **{info['dsr']:.2f}** | {info['sr_15']:.2f} |\n"

    # Đối chiếu tiêu chí G3
    ablation_md += f"""
## 2. Đối Chiếu Tiêu Chí Vượt Gate G3 (Gate G3 Audit)

Tiêu chuẩn định lượng cố định:
1. **Sharpe OOS > VN-Index B&H ({bench_results['B0']['sharpe']:.2f}):** Sau chi phí thực tế.
2. **Tỷ lệ năm OOS có Sharpe dương $\\ge 60\\%$.**
3. **DSR $\\ge 0.90$ (với N cộng dồn={total_N}).**
4. **Tổng số lệnh OOS ghép lại $\\ge 150$ lệnh.**
5. **Kết quả không đổi dấu khi chi phí tăng $+50\\%$ (phí $\\times 1.5$).**

### Đánh giá từng biến thể Breakout:
* **A1 (Breakout Thuần):** Nền tảng swing trading.
* **A2 (+Regime):** Đóng góp của bộ lọc xu hướng thị trường VN-Index.
* **A3 (+Volume):** Đóng góp của lọc dòng tiền phiên bùng nổ.
* **A4 (+CLV):** Đóng góp vị trí đóng cửa nến.
* **A5 (+RS):** Đóng góp của phân vị Relative Strength dẫn dắt.
* **A6 (Full Breakout):** Bộ lọc đầy đủ kèm Trailing Stop ATR.
"""
    with open(ROOT / "reports" / "ablation.md", "w", encoding="utf-8") as f:
        f.write(ablation_md)

    # Báo cáo Stability
    stability_md = f"""# Báo Cáo Ổn Định Tham Số & Độ Nhạy (Stability & Sensitivity Report)

* **Thời điểm lập:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. Độ Nhạy Chi Phí Giao Dịch
| ID | Biến Thể | Chi Phí Chuẩn (1.0x) | Chi Phí +50% (1.5x) | Chi Phí +100% (2.0x) | Đánh Giá Độ Nhạy |
|---|---|---|---|---|---|
"""
    for v_id in ["A1", "A2", "A3", "A4", "A5", "A6", "P1", "P2"]:
        info = variant_results[v_id]
        resil = "Bền vững" if info["sr_15"] > 0 else "Dễ vỡ trước chi phí"
        stability_md += f"| **{v_id}** | {info['desc']} | {info['sr_10']:.2f} | {info['sr_15']:.2f} | {info['sr_20']:.2f} | {resil} |\n"

    stability_md += f"""
## 2. Tham Số Được Chọn Theo Từng Cửa Sổ Walk-Forward (A6 - Full Breakout)
| Năm Test | Cửa Sổ Train | n_in | n_out | Regime (m) | Vol Mult | ATR k | CLV | RS | Sharpe Train | Smooth | Sharpe OOS | Số Lệnh |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
"""
    for y, p, s, sm, so, n in variant_picks.get("A6", []):
        stability_md += f"| **{y}** | {y-3}..{y-1} | {p[0]} | {p[1]} | {p[2]} | {p[3]} | {p[4]} | {p[5]} | {p[6]} | {s:.2f} | {sm:.2f} | {so:.2f} | {n} |\n"

    with open(ROOT / "reports" / "stability.md", "w", encoding="utf-8") as f:
        f.write(stability_md)

    print("\n[SUCCESS] HOÀN TẤT PHASE 3!")
    print(f" -> Báo cáo: reports/ablation.md")
    print(f" -> Báo cáo: reports/stability.md")


if __name__ == "__main__":
    run_ablation_study()
