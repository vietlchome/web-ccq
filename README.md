# DCA EMA200 — Chứng chỉ quỹ (Fmarket)

Web nội bộ theo dõi điểm mua DCA cho các quỹ mở VN, port từ chỉ báo TradingView **DCA EMA200** (chỉ giữ phần MUA — bỏ gợi ý bán, EMA200W, phân kì RSI vì NAV quỹ chỉ có giá close hàng ngày).

## Cấu trúc

- `funds.txt` — danh sách quỹ theo dõi (mỗi dòng 1 mã, `#` là comment)
- `stocks.txt` — danh sách cổ phiếu theo dõi (`MÃ | Tên | Ngành | Sàn`), mặc định rổ VN30
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

## Thêm / bớt cổ phiếu

Sửa `stocks.txt` (mỗi dòng `MÃ | Tên doanh nghiệp | Ngành | Sàn`, chỉ mã là bắt buộc), chạy lại `fetch_data.py`.
Mặc định là rổ **VN30 kỳ tháng 7/2026** (hiệu lực 03/08/2026). HOSE cơ cấu rổ 2 lần/năm (tháng 1 và 7) → nhớ sửa file sau mỗi kỳ.

**Giá lấy về là giá ĐÃ ĐIỀU CHỈNH** cổ tức/chia tách. Bắt buộc phải vậy: NAV quỹ đã là total-return,
còn giá cổ phiếu thô rơi một nấc đúng ngày GDKHQ — dùng giá thô thì EMA200 thấy một cú "giảm" không có thật
và đẻ ra tín hiệu mua giả. Nguồn: Entrade (chính, ~2017 trở lại đây) → CafeF cột `GiaDieuChinh` (dự phòng, chậm) → TCBS.

Hai bảng Tổng quan và So sánh có **dải nút lọc nhóm** (Tất cả · Quỹ & ETF · Cổ phiếu VN30 · Vàng & Crypto).
Mặc định mở ở nhóm Quỹ & ETF, lựa chọn được nhớ trong localStorage (`dca_ema200_cat`). Lọc chỉ ảnh hưởng hiển thị —
điểm và nhóm A/B/C/D vẫn chấm trên toàn rổ quỹ, bấm nút không làm thứ hạng đổi.

Cổ phiếu là **tài sản tham chiếu**: có chart, tín hiệu DCA, backtest y như quỹ, nhưng **không chấm điểm**
và không vào rổ chuẩn hoá ở tab So sánh — rủi ro một mã đơn lẻ khác hẳn rủi ro danh mục vài chục mã của quỹ,
và 30 mã biến động mạnh sẽ kéo giãn thang percentile làm điểm của các quỹ nhảy loạn.
Panel bên phải đổi thành thông tin doanh nghiệp + chỉ số giá (đỉnh/đáy 52 tuần, %cách đỉnh, %lệch EMA200,
KLGD/GTGD bình quân 20 phiên) — tất cả suy ra từ chính chuỗi giá, không gọi thêm API nào.

## Logic chỉ báo (port từ Pine)

- **EMA200 / SD200** tính trên NAV close (EMA đệ quy từ giá trị đầu, khớp `ewm(span=200, adjust=False)` của pandas).
- **Tín hiệu mua**: mỗi `X` phiên (chu kỳ DCA). Hai **chế độ mua**: *Mua mọi lúc* (mua cả khi giá trên & dưới EMA200) hoặc *Chỉ mua khi NAV < EMA200*. Tín hiệu dựa trên NAV **phiên trước** (`close[1]`, `ema[1]`, `sd[1]`), khớp lệnh tại NAV **phiên nay** — giữ nguyên tinh thần fix lookahead của bản Pine ("hôm qua đóng nến thấy tín hiệu → hôm nay đặt lệnh", phù hợp cơ chế khớp NAV kỳ tới của quỹ mở).
- **Hệ số nhân động**: theo **bước nhảy %EMA** (gợi ý sẵn: BTC 5%, quỹ/ETF/vàng 3% — nhớ riêng từng tài sản, vẫn chỉnh tay được). Dưới EMA200: mỗi bước rẻ hơn → **+1x** (vd bước 3%, NAV dưới 9% → x3), sàn 1.0x. Trên EMA200 (chỉ ở chế độ *Mua mọi lúc*): mỗi bước đắt hơn → **−0.1x**, **sàn 0.1x** (mua ít dần khi đắt); ở chế độ *Chỉ mua dưới EMA200* thì trên EMA200 = không mua. Tắt hệ số → luôn 1x. Làm tròn 1 chữ số thập phân.
- **So với VNINDEX (theo DCA)**: chạy cùng chiến lược DCA, cùng tham số, trên VNINDEX để so % lãi — biết quỹ đang win/thua chỉ số bao nhiêu điểm %.
- **Tăng trưởng NAV so với VN-Index theo khung** (YTD/1Y/3Y/5Y/10Y): so thuần % tăng giá NAV quỹ vs % tăng VN-Index (mua & giữ, KHÔNG phải tài khoản mô phỏng). Khung dài kèm %/năm. Khung nào thiếu dữ liệu (quỹ mới, hoặc chỉ số chưa đủ lịch sử) để trống. Nguồn VNINDEX lấy tự động, thử lần lượt TCBS → DNSE Entrade → VNDirect (nguồn nào sống thì dùng).
- **Portfolio**: tổng vốn, lượng CCQ, giá vốn TB, % lãi, đáy P&L/vốn, IRR (money-weighted, bisection, chỉ hiện khi ≥1 năm), lumpsum, mục tiêu tích lũy.
- Mỗi người tự chỉnh tham số trên web (lưu localStorage riêng từng máy) — không cần chạy lại script.

> Công cụ tham khảo nội bộ, không phải khuyến nghị đầu tư.

## Động cơ backtest (từ 09/2026)

Logic 4 chiến thuật nằm trong `engine.js` (UMD — chạy được cả trên trình duyệt lẫn Node), tách khỏi `index.html` để đối chiếu tự động được với chỉ báo TradingView.

```bash
node test-engine.js          # đối chiếu với TradingView (vàng là mốc chuẩn)
node compare.js FUESSVFL     # so 4 cách trên 1 quỹ
node compare.js --tat-ca     # quét toàn bộ quỹ
```

**Bốn cách** = tổ hợp hai công tắc, có nút bấm nhanh ở đầu cột trái:

| | Lọc EMA200D | Mỏ neo đôi |
|---|---|---|
| Cách 1 | tắt | tắt |
| Cách 2 | bật | tắt |
| Cách 3 | bật | bật |
| Cách 4 | tắt | bật |

**Hai điểm quan trọng đã sửa:**

- *Lịch, không phải điểm dữ liệu.* Quỹ công bố NAV 48–365 lần/năm, nên tính EMA200 trên mảng NAV thô cho ra "EMA200" dài 0,55 năm (BTC) tới 4,2 năm (TBLF) — cùng một dòng code, ý nghĩa lệch 8 lần. Giờ EMA và nhịp DCA chạy trên lưới ngày lịch (`alignToRows`), khớp cách TradingView tính. VCBF-BCF trước đây bắn 11,9% số phiên, đúng ra phải là 27,3%.
- *Mỏ neo đôi.* Hệ số = (độ rẻ so EMA200 ngày ÷ bước ngày) + (độ rẻ so EMA200 tuần ÷ bước tuần), sàn 1x, có trần. Bỏ hẳn phần mua-giảm-dần khi giá trên EMA của bản cũ.

Phí quản lý quỹ KHÔNG trừ trong engine — NAV đã là số ròng sau phí, trừ nữa là tính hai lần. Chỉ `feeBuyPct` (phí mua CCQ) là tham số.
