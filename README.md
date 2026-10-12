# 🚀 VN-Swing: Hệ Thống Giao Dịch Swing Định Lượng Cổ Phiếu HOSE (V-DBO)

Hệ thống giao dịch Swing định lượng (chu kỳ nắm giữ 10–45 phiên) cho toàn bộ cổ phiếu sàn HOSE. 
Mô hình vận hành **Long-only**, tính toán tín hiệu sau khi đóng cửa nến phiên $t$ (hoặc cập nhật nến 15 phút realtime trong phiên), tạo lệnh mua/bán ATO cho phiên $t+1$ với cơ chế duyệt lệnh **Human-in-the-loop**.

Tích hợp sẵn **Web Dashboard giám sát trực quan (TradingView Dark Theme)** và cơ chế **Tự động đồng bộ dữ liệu Realtime 15 phút/lần qua GitHub Actions & GitHub Pages**.

---

## 🌟 Tính Năng Nổi Bật

1. **Chuẩn Mực Lượng Hóa Khắt Khe (Institutional Grade):**
   - **Zero Look-Ahead Bias:** Tín hiệu đóng nến $t$ $\to$ Khớp ATO phiên $t+1$. Tuyệt đối không dùng dữ liệu tương lai.
   - **Chống Survivorship Bias:** Universe bao gồm cả 406 mã đang niêm yết và 232 mã đã hủy niêm yết trong lịch sử HOSE (tổng 638 mã).
   - **Bảo Vệ Vùng Holdout (2025–Nay):** Khóa cứng an toàn cấp độ code; chặn mọi hành vi tối ưu hóa quá mức (*p-hacking*) trên dữ liệu mới.
   - **Mô Hình Khớp Lệnh & Chi Phí Thực Tế:** Tính trần/sàn biên độ ±7%, lô chẵn 100, trượt giá theo thanh khoản ADTV 60 phiên, phí mua 0.3%, phí + thuế bán 0.4%.
   - **Quản Trị Rủi Ro 2 Cấp Độ (Kill-Switch):** Cảnh báo giảm 50% quy mô khi Drawdown vượt 15%, tạm dừng mua mới khi Drawdown chạm 25%.

2. **Web Dashboard Trực Quan (`web/`):**
   - Giao diện TradingView Dark Mode với Tailwind CSS & Lucide Icons.
   - Bảng tín hiệu Vào lệnh (kèm tính toán khối lượng tối ưu, % vốn, mức cắt lỗ ATR 3.0×).
   - Bảng Quản trị Vị thế & Nâng Trailing Stop Loss theo đáy Donchian 10 phiên.
   - Biểu đồ xu hướng thị trường VN-Index & SMA100 (Market Regime Filter).
   - Nút **"Copy Lệnh"** 1-click để đặt nhanh trên app chứng khoán (SSI, VPS, DNSE, TCBS,...).
   - Đồng hồ đếm ngược tự động cập nhật dữ liệu sau mỗi 15 phút.

3. **Tự Động Đồng Bộ Realtime 15 Phút/Lần:**
   - **GitHub Actions (`.github/workflows/deploy_and_sync.yml`):** Tự động chạy trong giờ giao dịch HOSE (09:00 - 15:00 UTC+7 các ngày thứ 2 đến thứ 6), kéo nến 15 phút từ DNSE Entrade API, tính toán lại tín hiệu và tự động deploy lên **GitHub Pages**.
   - **Local Sync Daemon (`scripts/run_local_sync.py`):** Cho phép trader chạy ngầm trên máy cá nhân khi mở bảng điện, có sẵn HTTP server local.

---

## 📁 Cấu Trúc Hệ Thống

```text
vn-swing/
├─ .github/workflows/
│   └─ deploy_and_sync.yml  # Tự động hóa 15M sync và deploy GitHub Pages
├─ configs/
│   ├─ base.yaml            # Cấu hình thị trường, chi phí, quy mô danh mục
│   ├─ grid_brk.yaml        # Lưới tham số Donchian Breakout
│   └─ grid_pb.yaml         # Lưới tham số Pullback
├─ data/
│   ├─ adjusted/            # Dữ liệu giá đã điều chỉnh (Parquet)
│   ├─ meta/                # Danh mục 638 mã HOSE (niêm yết & hủy niêm yết)
│   └─ ledger.csv           # Sổ lệnh theo dõi vị thế thực tế (Human-in-the-loop)
├─ docs/
│   ├─ MARKET_RULES.md      # Quy chế giao dịch HOSE (T+2.5, lô 100, biên độ 7%)
│   ├─ OPEN_QUESTIONS.md    # Phân tích các câu hỏi mở và giả định
│   └─ DECISIONS.md         # Bản ghi quyết định kiến trúc (ADR)
├─ registry/
│   ├─ data_manifest.json   # Mã băm SHA-256 xác thực toàn vẹn dữ liệu
│   └─ trials.jsonl         # Nhật ký 100 thử nghiệm Walk-forward OOS
├─ reports/
│   ├─ ablation.md          # Kết quả phân rã thuộc tính 11 biến thể
│   ├─ stability.md         # Phân tích độ ổn định tham số OOS 10 năm
│   └─ daily/               # Báo cáo tín hiệu sinh ra hàng ngày
├─ scripts/
│   ├─ download_hose_data.py# Script tải dữ liệu lịch sử từ DNSE Entrade
│   ├─ run_local_sync.py    # Daemon đồng bộ dữ liệu cục bộ 15 phút/lần
│   └─ start_local_sync.bat # Khởi chạy nhanh 1-click trên Windows
├─ src/vnswing/
│   ├─ data/                # Ingest, validate, universe, calendar
│   ├─ features/            # FeatureEngine (Donchian, ATR, SMA, CLV, RS Rank)
│   ├─ signals/             # Bộ sinh tín hiệu Breakout và Pullback
│   ├─ backtest/            # Backtest Engine, Execution Simulator, Performance Metrics
│   ├─ research/            # Walk-forward Optimizer, Deflated Sharpe Ratio, Ablation
│   └─ ops/                 # Daily Run, Web Sync, Ledger Manager, Alerts
├─ tests/                   # Bộ 19 bài kiểm thử định lượng & an toàn (100% Pass)
├─ web/                     # Web Dashboard tĩnh phục vụ GitHub Pages
│   ├─ index.html           # Ứng dụng Dashboard giao diện Dark Mode
│   └─ data/signals.json    # Payload dữ liệu tín hiệu mới nhất
└─ requirements.txt         # Thư viện phụ thuộc chuẩn
```

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng

### 1. Cài đặt môi trường
Yêu cầu Python >= 3.10:
```bash
pip install -r requirements.txt
```

### 2. Chạy bộ kiểm thử định lượng (19 Tests)
```bash
pytest tests/ -v
```
*(Xác minh: Zero look-ahead, tính toán ATR/Donchian, cơ chế khớp lệnh T+2.5, khóa Holdout 2025)*

### 3. Khởi chạy Web Dashboard trên máy cá nhân
Chạy server phục vụ web cục bộ:
```bash
# Cách 1: Chạy daemon đồng bộ 15 phút/lần kèm Web Server
python scripts/run_local_sync.py --serve

# Cách 2 (Windows): Nhấp đúp vào file scripts/start_local_sync.bat
```
Truy cập trình duyệt tại: **`http://localhost:8080`**

---

## 🌐 Xuất Bản Lên GitHub & Kích Hoạt GitHub Pages

Để xuất bản dự án thành Website online và chạy đồng bộ tự động:

### Bước 1: Tạo Repository mới trên GitHub
1. Đăng nhập tài khoản [GitHub](https://github.com/new).
2. Tạo một repository mới (ví dụ đặt tên là `vn-swing`), chọn chế độ **Public**.

### Bước 2: Đẩy mã nguồn lên GitHub
Mở terminal trong thư mục `vn-swing` và chạy:
```bash
git remote add origin https://github.com/<tai-khoan-cua-ban>/vn-swing.git
git branch -M main
git push -u origin main
```

### Bước 3: Cấu hình GitHub Pages
1. Trên giao diện GitHub của Repo, vào mục **Settings** $\to$ **Pages**.
2. Tại mục **Build and deployment** $\to$ **Source**:
   - Chọn **GitHub Actions**.
3. Lưu cài đặt. 
4. Hệ thống sẽ tự động kích hoạt workflow `.github/workflows/deploy_and_sync.yml`. Sau khi chạy xong (~1 phút), Website của bạn sẽ xuất hiện tại địa chỉ:
   ```text
   https://<tai-khoan-cua-ban>.github.io/vn-swing/
   ```

### Bước 4: Kiểm tra cơ chế tự động 15 phút
- Vào tab **Actions** trên GitHub.
- Bạn sẽ thấy workflow `Deploy Dashboard & Realtime 15M Sync`.
- Bạn có thể bấm nút **Run workflow** bất cứ lúc nào để cập nhật dữ liệu ngay lập tức, hoặc để GitHub Actions tự động kích hoạt mỗi 15 phút trong phiên giao dịch từ Thứ 2 đến Thứ 6.

---

## 📊 Tóm Tắt Kết Quả Nghiên Cứu Lượng Hóa (Walk-Forward 2015–2024)

Từ 100 thử nghiệm Out-Of-Sample (OOS) trên 10 năm lịch sử thị trường Việt Nam:
- **Chiến lược B2 (Trend MA Pullback):** Đạt Sharpe Ratio OOS **2.91** với tỷ lệ thắng 67.5%, Max Drawdown -11.4%.
- **Chiến lược Donchian Breakout thuần túy (B0):** Đạt Sharpe OOS 0.82; việc mua đuổi giá phá vỡ đỉnh ATO chịu áp lực trượt giá và bẫy tăng giá giả (bull-traps) trong thị trường đi ngang.
- **Bộ lọc Market Regime (VN-Index > SMA100):** Giúp cắt giảm hơn 65% số phiên thua lỗ nặng trong các giai đoạn downtrend như năm 2018 và 2022.

---

## ⚖️ Tuyên Bố Miễn Trừ Trách Nhiệm (Disclaimer)
Hệ thống được phát triển phục vụ mục đích nghiên cứu khoa học dữ liệu tài chính định lượng và hỗ trợ giám sát danh mục. Mọi thông tin tín hiệu hiển thị trên website không phải là lời khuyên đầu tư tài chính. Nhà đầu tư tự chịu trách nhiệm về quyết định đặt lệnh của mình.
