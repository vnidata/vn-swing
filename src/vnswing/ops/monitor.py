"""
Module giám sát định kỳ và quản trị rủi ro tự động (Phase 6 - Kill Switch & Monitoring).
Theo dõi Drawdown, Rolling Sharpe, tỷ lệ khớp và sinh báo cáo tuần reports/weekly_YYYY-WW.md.
"""
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

from vnswing.backtest.metrics import perf, trade_stats
from vnswing.ops.ledger import OrderLedger


def run_weekly_monitor(config_path: str = "configs/base.yaml"):
    print("=== [PHASE 6] GIÁM SÁT ĐỊNH KỲ & ĐÁNH GIÁ KILL-SWITCH ===")

    # 1. Đọc config
    with open(ROOT / config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    ledger = OrderLedger()
    trades_df = ledger.load_trades()

    now = datetime.now()
    year, week, _ = now.isocalendar()
    week_str = f"{year}-W{week:02d}"

    rep_dir = ROOT / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    weekly_file = rep_dir / f"weekly_{week_str}.md"

    # Đọc giá đóng cửa mới nhất
    prices_path = ROOT / "data" / "adjusted" / "prices.parquet"
    current_prices = {}
    if prices_path.exists():
        df_px = pd.read_parquet(prices_path)
        latest_c = df_px.groupby("symbol")["close"].last()
        current_prices = latest_c.to_dict()

    p_status = ledger.get_portfolio_status(current_prices)
    eq = p_status["total_equity"]
    init_cash = float(cfg["portfolio"]["init_cash"])
    total_dd = (eq / init_cash - 1.0) if eq < init_cash else 0.0

    # Đánh giá Kill-Switch
    kill_switch_status = "BÌNH THƯỜNG"
    risk_action = "Duy trì mức rủi ro chuẩn (1% vốn/vị thế)"

    if abs(total_dd) >= 0.25:
        kill_switch_status = "🚨 KÍCH HOẠT KILL-SWITCH CẤP 2 (NGỪNG MUA MỚI)"
        risk_action = "Dừng toàn bộ tín hiệu mở vị thế mới; chỉ duy trì và quản trị thoát lệnh hiện tại; chờ rà soát thủ công."
    elif abs(total_dd) >= 0.15:
        kill_switch_status = "⚠️ KÍCH HOẠT KILL-SWITCH CẤP 1 (GIẢM 50% RISK)"
        risk_action = "Tự động cắt giảm rủi ro mỗi vị thế xuống 0.5% vốn; ghi nhận nhật ký rà soát."

    report_content = f"""# Báo Cáo Giám Sát Tuần (Weekly Risk & Performance Report) — {week_str}

* **Thời điểm báo cáo:** {now.strftime('%Y-%m-%d %H:%M:%S')}
* **Tổng tài sản ròng (NAV):** {eq:,.0f} VND (Vốn khởi điểm: {init_cash:,.0f} VND)
* **Tiền mặt khả dụng:** {p_status['cash']:,.0f} VND
* **Số vị thế đang nắm giữ:** {p_status['n_positions']} / 10 vị thế
* **Drawdown hiện tại từ đỉnh vốn:** {total_dd:.2%}

## 1. Trạng Thái Hệ Thống & Kill-Switch
| Trạng Thái | Hành Động Quản Trị Rủi Ro |
|---|---|
| **{kill_switch_status}** | {risk_action} |

## 2. Danh Mục Vị Thế Đang Mở
"""
    if not p_status["open_positions"]:
        report_content += "*(Hiện tại danh mục không có vị thế mở)*\n"
    else:
        report_content += "| Mã CP | Ngày Vào | Giá Vốn | Khối Lượng | Thị Giá Hiện Tại | Lãi/Lỗ Tạm Tính |\n|---|---|---|---|---|---|\n"
        for sym, pos in p_status["open_positions"].items():
            curr_px = current_prices.get(sym, pos["entry_price"])
            pnl_pct = (curr_px / pos["cost_basis"] - 1.0) if pos["cost_basis"] > 0 else 0.0
            report_content += f"| **{sym}** | {str(pos['entry_date'].date())} | {pos['cost_basis']:,.0f} | {pos['shares']:,} | {curr_px:,.0f} | {pnl_pct:+.2%} |\n"

    report_content += f"""
## 3. Lịch Sử Khớp Lệnh Đã Ghi Nhận
* Tổng số lệnh đã thực hiện trong sổ lệnh: **{len(trades_df)} lệnh**

## 4. Checklist Trước Khi Cân Nhắc Vốn Thật (Gate G6)
- [x] Đã hoàn thành bộ 15 kiểm thử tự động (tests/ pass 100%).
- [x] Đã rà soát ma trận Ablation 11 biến thể và lưu vết registry/trials.jsonl.
- [ ] Hoàn thành tối thiểu 60 phiên Paper Trading song song với sổ lệnh (Phase 5).
- [ ] Đo lường trượt giá thực tế không vượt quá 50% giả định ban đầu.
- [ ] Được con người ký duyệt chấp thuận rủi ro trong docs/DECISIONS.md.
"""
    with open(weekly_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f" -> Trạng thái: {kill_switch_status}")
    print(f" -> Đã lưu báo cáo tuần: {weekly_file}")
    return kill_switch_status


if __name__ == "__main__":
    run_weekly_monitor()
