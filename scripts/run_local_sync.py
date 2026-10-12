"""
Script chạy đồng bộ dữ liệu Realtime 15 phút/lần tại máy cục bộ (Local Daemon).
Tự động gọi web_sync.py định kỳ và có thể bật HTTP Server để xem trực tiếp trên trình duyệt.
Cách dùng:
    python scripts/run_local_sync.py
    python scripts/run_local_sync.py --interval 300   # 5 phút/lần
    python scripts/run_local_sync.py --serve          # Kèm HTTP Server port 8080
"""
import argparse
from datetime import datetime
import http.server
from pathlib import Path
import socketserver
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vnswing.ops.web_sync import generate_web_dashboard_data


def start_http_server(port: int = 8080, web_dir: Path = ROOT / "web"):
    """Khởi chạy máy chủ HTTP local phục vụ Dashboard."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_dir), **kwargs)

        def log_message(self, format, *args):
            pass  # Tắt log truy cập để tránh nhiễu terminal

    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            print(f"🌐 [LOCAL SERVER] Website Dashboard đang mở tại: http://localhost:{port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"⚠️ [LOCAL SERVER] Không thể khởi tạo cổng {port}: {e}")


def main():
    parser = argparse.ArgumentParser(description="VN-Swing Realtime 15M Sync Daemon")
    parser.add_argument("--interval", type=int, default=900, help="Chu kỳ đồng bộ (giây), mặc định 900s (15 phút)")
    parser.add_argument("--serve", action="store_true", help="Khởi động kèm máy chủ Web tại http://localhost:8080")
    parser.add_argument("--port", type=int, default=8080, help="Cổng máy chủ Web (mặc định 8080)")
    args = parser.parse_args()

    print("=" * 65)
    print("🚀 VN-SWING QUANT SYSTEM — LOCAL REALTIME SYNC DAEMON")
    print(f"⏰ Chu kỳ đồng bộ: {args.interval} giây ({args.interval // 60} phút)")
    print("=" * 65)

    if args.serve:
        server_thread = threading.Thread(target=start_http_server, args=(args.port,), daemon=True)
        server_thread.start()

    round_count = 1
    while True:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n🔄 [{now_str}] Bắt đầu chu kỳ đồng bộ #{round_count}...")
        try:
            generate_web_dashboard_data()
            print(f"✅ Chu kỳ #{round_count} hoàn thành lúc {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"❌ Lỗi trong quá trình đồng bộ: {e}")

        round_count += 1

        # Countdown
        print(f"⏳ Chờ {args.interval}s đến chu kỳ tiếp theo (Nhấn Ctrl+C để dừng)...")
        for remaining in range(args.interval, 0, -1):
            if remaining % 60 == 0 or remaining <= 10:
                sys.stdout.write(f"\r⏱️ Còn {remaining} giây... ")
                sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\r" + " " * 30 + "\r")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Đã dừng tiến trình đồng bộ cục bộ.")
