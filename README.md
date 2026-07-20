# DCA EMA200 — Chứng chỉ quỹ (Fmarket)

Web nội bộ theo dõi điểm mua DCA cho các quỹ mở VN, port từ chỉ báo TradingView **DCA EMA200** (chỉ giữ phần MUA — bỏ gợi ý bán, EMA200W, phân kì RSI vì NAV quỹ chỉ có giá close hàng ngày).

## Cấu trúc

- `funds.txt` — danh sách quỹ theo dõi (mỗi dòng 1 mã, `#` là comment)
- `fetch_data.py` — tải NAV lịch sử từ API Fmarket → `data/*.json`
- `index.html` — toàn bộ web (chart + logic chỉ báo chạy trên trình duyệt)
- `data/` — dữ liệu JSON (tự sinh, commit vào repo)
- `.github/workflows/update-data.yml` — tự cập nhật NAV mỗi ngày

## Chạy thử trên máy

```bash
pip install requests
python fetch_data.py          # tải NAV thật (thay dữ liệu mẫu)
python -m http.server 8000    # phải chạy qua HTTP, không mở file:// trực tiếp
# mở http://localhost:8000
```

## Deploy cho nhóm (khuyến nghị: GitHub Pages, miễn phí)

1. Tạo repo GitHub (private cũng được nếu có GitHub Pro/Team; public thì Pages miễn phí).
2. Push toàn bộ thư mục này lên.
3. **Settings → Pages** → Source: branch `main`, thư mục `/ (root)` → Save.
4. **Actions** → chạy tay workflow "Cập nhật NAV hàng ngày" lần đầu để có dữ liệu thật.
5. Chia link `https://<user>.github.io/<repo>/` cho nhóm.

Workflow tự chạy 19:30 giờ VN các ngày trong tuần (sau khi Fmarket cập nhật NAV). Muốn đổi giờ, sửa dòng `cron` trong `update-data.yml` (giờ UTC = giờ VN − 7).

Ngoài GitHub Pages có thể dùng Cloudflare Pages / Vercel — trỏ vào repo là xong. Muốn giới hạn người xem: Cloudflare Access (miễn phí ≤50 user) hoặc để repo private + Vercel password.

## Thêm / bớt quỹ

Sửa `funds.txt`, chạy lại `fetch_data.py` (hoặc đợi workflow chạy). Web tự nhận danh sách mới.

- Để **theo dõi toàn bộ quỹ cổ phiếu** trên Fmarket: để 1 dòng `ALL_STOCK` trong `funds.txt` (script tự lấy hết, tự cập nhật khi có quỹ mới).
- Để theo dõi vài quỹ cụ thể: liệt kê từng mã shortName (vd `DCDS`), mỗi dòng 1 mã.
- Có thể trộn: `ALL_STOCK` + thêm mã quỹ trái phiếu/cân bằng muốn theo dõi.

## Logic chỉ báo (port từ Pine)

- **EMA200 / SD200** tính trên NAV close (EMA đệ quy từ giá trị đầu, khớp `ewm(span=200, adjust=False)` của pandas).
- **Tín hiệu mua**: mỗi `X` phiên (chu kỳ DCA). Hai **chế độ mua**: *Mua mọi lúc* (mua cả khi giá trên & dưới EMA200) hoặc *Chỉ mua khi NAV < EMA200*. Tín hiệu dựa trên NAV **phiên trước** (`close[1]`, `ema[1]`, `sd[1]`), khớp lệnh tại NAV **phiên nay** — giữ nguyên tinh thần fix lookahead của bản Pine ("hôm qua đóng nến thấy tín hiệu → hôm nay đặt lệnh", phù hợp cơ chế khớp NAV kỳ tới của quỹ mở).
- **Hệ số nhân động**: theo **bước nhảy %EMA** (gợi ý sẵn: BTC 5%, quỹ/ETF/vàng 3% — nhớ riêng từng tài sản, vẫn chỉnh tay được). Dưới EMA200: mỗi bước rẻ hơn → **+1x** (vd bước 3%, NAV dưới 9% → x3), sàn 1.0x. Trên EMA200 (chỉ ở chế độ *Mua mọi lúc*): mỗi bước đắt hơn → **−0.1x**, **sàn 0.1x** (mua ít dần khi đắt); ở chế độ *Chỉ mua dưới EMA200* thì trên EMA200 = không mua. Tắt hệ số → luôn 1x. Làm tròn 1 chữ số thập phân.
- **So với VNINDEX (theo DCA)**: chạy cùng chiến lược DCA, cùng tham số, trên VNINDEX để so % lãi — biết quỹ đang win/thua chỉ số bao nhiêu điểm %.
- **Tăng trưởng NAV so với VN-Index theo khung** (YTD/1Y/3Y/5Y/10Y): so thuần % tăng giá NAV quỹ vs % tăng VN-Index (mua & giữ, KHÔNG phải tài khoản mô phỏng). Khung dài kèm %/năm. Khung nào thiếu dữ liệu (quỹ mới, hoặc chỉ số chưa đủ lịch sử) để trống. Nguồn VNINDEX lấy tự động, thử lần lượt TCBS → DNSE Entrade → VNDirect (nguồn nào sống thì dùng).
- **Portfolio**: tổng vốn, lượng CCQ, giá vốn TB, % lãi, đáy P&L/vốn, IRR (money-weighted, bisection, chỉ hiện khi ≥1 năm), lumpsum, mục tiêu tích lũy.
- Mỗi người tự chỉnh tham số trên web (lưu localStorage riêng từng máy) — không cần chạy lại script.

> Công cụ tham khảo nội bộ, không phải khuyến nghị đầu tư.
