"""
Module phát cảnh báo tín hiệu hằng ngày (Daily Alerts & Digest).
Xuất bản thông báo qua Telegram Bot và in bảng tóm tắt định dạng chuẩn ra Terminal.
"""
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def build_signal_digest(
    date_str: str,
    regime_active: bool,
    regime_detail: str,
    entries: List[Dict[str, Any]],
    exits: List[Dict[str, Any]],
    portfolio_status: Dict[str, Any],
) -> str:
    """Định dạng bản tin tóm tắt cuối phiên (Telegram / Console Digest)."""
    eq = portfolio_status.get("total_equity", 1e9)
    cash = portfolio_status.get("cash", 1e9)
    n_pos = portfolio_status.get("n_positions", 0)

    regime_badge = "🟢 BẬT (Cho phép mua mới)" if regime_active else "🔴 TẮT (Chỉ quản trị thoát lệnh, không mua mới)"

    lines = [
        f"📢 **BẢN TIN TÍN HIỆU SWING HOSE (V-DBO) — {date_str}**",
        "─" * 45,
        f"**1. Trạng Thái Thị Trường (Regime):** {regime_badge}",
        f"   * {regime_detail}",
        "",
        f"**2. Danh Mục Hiện Tại:** {n_pos}/10 vị thế | Tiền mặt: {cash:,.0f} VND | Tổng NAV: {eq:,.0f} VND",
        "",
        "**3. TÍN HIỆU VÀO LỆNH (Khớp ATO phiên sau):**",
    ]

    if not entries:
        lines.append("   *(Không có tín hiệu vào lệnh mới hôm nay)*")
    else:
        for i, e in enumerate(entries, 1):
            flag_str = f" ⚠️ {e['warning']}" if e.get("warning") else ""
            lines.extend([
                f"   **{i}. {e['symbol']}**{flag_str}",
                f"      • Giá đóng cửa: {e['close']:,.0f} VND (Mức phá: {e['break_level']:,.0f})",
                f"      • Stop đề xuất: {e['stop_loss']:,.0f} VND (ATR14: {e['atr']:,.0f})",
                f"      • Khối lượng gợi ý: **{e['shares']:,}** CP (Lô 100)",
                f"      • Giá trị lệnh: {e['value']:,.0f} VND ({e['weight']:.1%} vốn | Rủi ro: {e['risk_vnd']:,.0f} VND)",
                f"      • ADTV 60P: {e['adtv']:,.0f} VND",
            ])

    lines.extend([
        "",
        "**4. TÍN HIỆU THOÁT / NÂNG TRAILING STOP:**",
    ])

    if not exits:
        lines.append("   *(Không có vị thế chạm điểm thoát hoặc nâng stop hôm nay)*")
    else:
        for i, ex in enumerate(exits, 1):
            action_tag = "🔴 BÁN HẾT ATO" if ex["action"] == "EXIT" else "🔵 NÂNG STOP"
            lines.extend([
                f"   **{i}. {ex['symbol']}** — {action_tag}",
                f"      • Lý do: {ex['reason']}",
                f"      • Giá thị trường: {ex['close']:,.0f} VND | Stop mới: {ex['new_stop']:,.0f} VND",
                f"      • Khối lượng nắm giữ: {ex['shares']:,} CP",
            ])

    lines.extend([
        "",
        "─" * 45,
        "📌 *Lưu ý: Hệ thống không tự động đặt lệnh. Con người vui lòng xem xét, tự đặt lệnh và cập nhật giá khớp thực tế vào data/ledger.csv.*",
    ])

    return "\n".join(lines)


def send_telegram_alert(message: str) -> bool:
    """Gửi bản tin qua Telegram Bot nếu có cấu hình biến môi trường."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[ALERTS] Lỗi gửi Telegram: {e}")
        return False


def publish_daily_alert(
    date_str: str,
    regime_active: bool,
    regime_detail: str,
    entries: List[Dict[str, Any]],
    exits: List[Dict[str, Any]],
    portfolio_status: Dict[str, Any],
) -> str:
    """Xuất bản cảnh báo ra Console, file lưu trữ và Telegram."""
    digest_text = build_signal_digest(
        date_str, regime_active, regime_detail, entries, exits, portfolio_status
    )

    # In ra Terminal
    print("\n" + digest_text + "\n")

    # Lưu file text bản tin mới nhất
    daily_dir = ROOT / "reports" / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    with open(daily_dir / f"{date_str}_digest.txt", "w", encoding="utf-8") as f:
        f.write(digest_text)

    # Gửi qua Telegram
    sent = send_telegram_alert(digest_text)
    if sent:
        print("[ALERTS] Đã gửi bản tin thành công qua Telegram Bot!")
    else:
        print("[ALERTS] Bản tin đã được lưu tại reports/daily/ (Chưa cấu hình Telegram Bot Token).")

    return digest_text
