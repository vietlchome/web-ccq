# -*- coding: utf-8 -*-
"""Chạy thử RIÊNG phần cổ phiếu — không đụng tới quỹ/vàng/BTC nên chỉ mất ~1 phút.
    python test_stocks.py            # thử cả danh sách trong stocks.txt
    python test_stocks.py FPT VCB    # thử vài mã
Không ghi file nào, chỉ in ra màn hình để xem nguồn nào sống.
"""
import sys
from datetime import datetime, timezone

import fetch_data as f


def d(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%d/%m/%Y")


syms = [s.upper() for s in sys.argv[1:]] or [s["symbol"] for s in f.read_stocks()]
print(f"Thử {len(syms)} mã: {', '.join(syms)}\n")

ok, fail = [], []
for sym in syms:
    try:
        rows, vols, src = f.get_stock_prices(sym)
        yrs = (rows[-1][0] - rows[0][0]) / (365.25 * 864e5)
        print(f"{sym:5s} OK  {src:8s} {len(rows):5d} phiên  {d(rows[0][0])} → {d(rows[-1][0])}"
              f"  ({yrs:.1f} năm)  giá cuối {rows[-1][1]:,.0f}đ  KL {vols[-1]:,.0f}")
        ok.append(sym)
    except Exception as e:
        print(f"{sym:5s} LỖI  {e}")
        fail.append(sym)

print(f"\nĐược {len(ok)}/{len(syms)} mã.")
if fail:
    print("Hỏng:", ", ".join(fail))
print("\nKiểm tra nhanh giá điều chỉnh: giá cuối ở trên phải TRÙNG giá đóng cửa hôm nay")
print("trên bảng giá (điều chỉnh chỉ tác động vào quá khứ, phiên mới nhất luôn = giá thật).")
