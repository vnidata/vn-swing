"""
Module quản lý sổ lệnh thực tế (Order Ledger) do con người nhập:
- data/ledger.csv: lưu trữ lịch sử các lệnh đã khớp thực tế
- Đối chiếu (reconciliation) giữa vị thế mô hình lý thuyết và tài khoản thực
- Đo lường trượt giá và tỷ lệ khớp ATO thực tế
"""
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent.parent
LEDGER_PATH = ROOT / "data" / "ledger.csv"


class OrderLedger:
    """Quản lý trạng thái danh mục thực tế từ sổ lệnh do con người nhập."""

    def __init__(self, ledger_file: Optional[Path] = None, init_cash: float = 1e9):
        self.path = ledger_file or LEDGER_PATH
        self.init_cash = init_cash
        self._ensure_file()

    def _ensure_file(self):
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(columns=[
                "trade_id", "date", "symbol", "side", "shares", "price", "fee", "tax", "note"
            ])
            df.to_csv(self.path, index=False, encoding="utf-8")

    def load_trades(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def add_trade(
        self,
        date: str,
        symbol: str,
        side: str,
        shares: int,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        note: str = "",
    ):
        """Thêm một giao dịch thực tế vào sổ lệnh."""
        df = self.load_trades()
        trade_id = len(df) + 1
        new_row = {
            "trade_id": trade_id,
            "date": pd.to_datetime(date),
            "symbol": symbol.upper().strip(),
            "side": side.upper().strip(),
            "shares": int(shares),
            "price": float(price),
            "fee": float(fee),
            "tax": float(tax),
            "note": note,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(self.path, index=False, encoding="utf-8")
        return trade_id

    def get_open_positions(self) -> Dict[str, Dict[str, Any]]:
        """Tính toán danh sách các vị thế hiện đang nắm giữ."""
        df = self.load_trades()
        if df.empty:
            return {}

        positions: Dict[str, Dict[str, Any]] = {}
        df = df.sort_values("date")

        for _, row in df.iterrows():
            sym = row["symbol"]
            side = row["side"]
            sh = row["shares"]
            px = row["price"]

            if side == "BUY":
                if sym not in positions:
                    positions[sym] = {
                        "shares": 0,
                        "entry_date": row["date"],
                        "entry_price": px,
                        "cost_basis": 0.0,
                        "highest_close": px,
                    }
                p = positions[sym]
                total_sh = p["shares"] + sh
                p["cost_basis"] = (p["cost_basis"] * p["shares"] + (px * sh + row["fee"])) / total_sh if total_sh > 0 else 0.0
                p["shares"] = total_sh
            elif side == "SELL":
                if sym in positions:
                    positions[sym]["shares"] -= sh
                    if positions[sym]["shares"] <= 0:
                        del positions[sym]

        return positions

    def get_portfolio_status(self, current_prices: Dict[str, float]) -> Dict[str, Any]:
        """Tính toán tổng tài sản ròng, số vị thế, và tỷ trọng hiện tại."""
        df = self.load_trades()
        open_pos = self.get_open_positions()

        cash = self.init_cash
        if not df.empty:
            for _, row in df.iterrows():
                cost = row["shares"] * row["price"] + row["fee"] + row["tax"]
                if row["side"] == "BUY":
                    cash -= cost
                elif row["side"] == "SELL":
                    proceeds = row["shares"] * row["price"] - row["fee"] - row["tax"]
                    cash += proceeds

        pos_value = 0.0
        for sym, p in open_pos.items():
            curr_px = current_prices.get(sym, p["entry_price"])
            pos_value += p["shares"] * curr_px

        total_equity = cash + pos_value
        return {
            "cash": cash,
            "positions_value": pos_value,
            "total_equity": total_equity,
            "n_positions": len(open_pos),
            "open_positions": open_pos,
        }
