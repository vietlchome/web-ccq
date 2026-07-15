# -*- coding: utf-8 -*-
"""
Lấy NAV lịch sử quỹ mở VN từ Public API của Fmarket, xuất JSON cho web.

- Đọc danh sách quỹ từ funds.txt (mỗi dòng 1 mã, # là comment)
- Xuất data/<SYMBOL>.json  : {"symbol", "name", "updatedAt", "rows": [[epochDay, nav], ...]}
- Xuất data/index.json     : danh sách quỹ + tóm tắt trạng thái

Cài đặt: pip install requests
Chạy:    python fetch_data.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FUNDS_FILE = os.path.join(BASE_DIR, "funds.txt")
DATA_DIR = os.path.join(BASE_DIR, "data")

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


def read_funds() -> list:
    funds = []
    with open(FUNDS_FILE, encoding="utf-8") as f:
        for line in f:
            s = line.strip().upper()
            if s and not s.startswith("#"):
                funds.append(s)
    return funds


def get_fund_info(short_name: str) -> dict:
    """Tra fundId + tên đầy đủ theo tên viết tắt (DCDS, VESAF, ...)."""
    url = "https://api.fmarket.vn/res/products/filter"
    payload = {
        "types": ["NEW_FUND", "TRADING_FUND"],
        "issuerIds": [],
        "sortOrder": "DESC",
        "sortField": "navTo6Months",
        "page": 1,
        "pageSize": 200,
        "isIpo": False,
        "fundAssetTypes": [],
        "bondRemainPeriods": [],
        "searchField": short_name,
        "isBuyByReward": False,
        "thirdAppIds": [],
    }
    r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
    r.raise_for_status()
    rows = r.json()["data"]["rows"]
    for row in rows:
        if row["shortName"].upper() == short_name.upper():
            return {"id": row["id"], "name": row.get("name", short_name),
                    "owner": _owner_name(row), "row": row}
    raise ValueError(f"Không tìm thấy quỹ {short_name}")


def get_fund_detail(fund_id: int) -> dict:
    """Chi tiết 1 quỹ (danh mục nắm giữ, phân bổ tài sản, phí, ...)."""
    url = f"https://api.fmarket.vn/res/products/{fund_id}"
    r = requests.get(url, headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"detail {r.status_code}")
    return r.json().get("data") or {}


def extract_info(row: dict, detail: dict) -> dict:
    """Gộp thông tin cơ bản + hiệu suất + phí + danh mục để so sánh/xếp hạng.
    Chiến lược: giữ NGUYÊN các object có sẵn của Fmarket (khỏi sai tên field);
    với phí & rủi ro thì 'quét theo từ khóa' vì tên field không chắc chắn."""
    row = row or {}
    detail = detail or {}
    merged = {**row, **detail}

    def scan(kw):
        return {k: v for k, v in merged.items() if kw in k.lower()}

    def pick(*keys):
        for k in keys:
            v = merged.get(k)
            if v not in (None, ""):
                return v
        return None

    return {
        # cơ bản
        "fullName": row.get("name"),
        "assetType": (row.get("dataFundAssetType") or {}).get("name"),
        "owner": _owner_name(row),
        "inceptionDate": pick("firstIssueAt", "inceptionDate", "establishDate"),
        "nav": row.get("nav"),
        "minInvest": pick("firstBuyMinAmount", "initialInvestAmount", "minBuyAmount"),
        # hiệu suất Fmarket tính sẵn (giữ nguyên object)
        "navChange": row.get("productNavChange"),
        # phí — quét mọi khóa có 'fee' (phí bán/thời gian nắm giữ nằm ở đây)
        "fees": scan("fee"),
        # rủi ro — quét mọi khóa có 'risk'
        "risk": scan("risk"),
        # danh mục (từ endpoint chi tiết) — giữ nguyên list
        "holdingsStock": detail.get("productTopHoldingList"),
        "holdingsBond": detail.get("productTopHoldingBondList"),
        "industries": detail.get("productIndustriesHoldingList"),
        "assetAlloc": detail.get("productAssetHoldingList"),
    }


def _asset_type_name(row: dict) -> str:
    """Trích tên loại tài sản của quỹ (vd 'Quỹ cổ phiếu') từ nhiều khóa có thể có."""
    for k in ("dataFundAssetType", "fundAssetType", "productType"):
        v = row.get(k)
        if isinstance(v, dict) and v.get("name"):
            return str(v["name"]).lower()
        if isinstance(v, str) and v:
            return v.lower()
    return ""


def _owner_name(row: dict) -> str:
    """Trích tên công ty quản lý quỹ (để gom nhóm trên web)."""
    for k in ("owner", "issuer", "fundOwner", "fundManager"):
        v = row.get(k)
        if isinstance(v, dict) and (v.get("name") or v.get("shortName")):
            return str(v.get("name") or v.get("shortName"))
        if isinstance(v, str) and v:
            return v
    return ""


def list_stock_funds() -> list:
    """Lấy TẤT CẢ quỹ CỔ PHIẾU đang giao dịch trên Fmarket.
    Lọc server-side fundAssetTypes=STOCK, kiểm tra lại tên loại tài sản chứa
    'cổ phiếu' cho chắc. Trả về [{'shortName','id','name'}] (đã khử trùng lặp)."""
    url = "https://api.fmarket.vn/res/products/filter"
    out, page = [], 1
    while True:
        payload = {
            "types": ["NEW_FUND", "TRADING_FUND"],
            "issuerIds": [], "sortOrder": "DESC", "sortField": "navTo6Months",
            "page": page, "pageSize": 100, "isIpo": False,
            "fundAssetTypes": ["STOCK"], "bondRemainPeriods": [],
            "searchField": "", "isBuyByReward": False, "thirdAppIds": [],
        }
        r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        rows = r.json()["data"]["rows"]
        if not rows:
            break
        for row in rows:
            at = _asset_type_name(row)
            if at and "cổ phiếu" not in at:   # server bỏ qua filter → tự lọc
                continue
            out.append({"shortName": str(row["shortName"]).upper(),
                        "id": row["id"], "name": row.get("name", row["shortName"]),
                        "owner": _owner_name(row), "row": row})
        if len(rows) < 100:
            break
        page += 1
        time.sleep(0.5)
    seen, uniq = set(), []
    for f in out:
        if f["shortName"] not in seen:
            seen.add(f["shortName"])
            uniq.append(f)
    return uniq


def build_fund_list() -> list:
    """Đọc funds.txt → danh sách quỹ cần tải: [{'shortName','id','name'}].
    Token 'ALL_STOCK' (một dòng riêng) = tự lấy toàn bộ quỹ cổ phiếu trên Fmarket.
    Dòng mã thường: tải đúng quỹ đó (id sẽ tra sau bằng get_fund_info)."""
    specs = []
    with open(FUNDS_FILE, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                specs.append(s.upper())
    funds, seen = [], set()
    for s in specs:
        if s in ("ALL_STOCK", "@STOCK", "*STOCK"):
            print("Đang lấy danh sách toàn bộ quỹ cổ phiếu trên Fmarket...", flush=True)
            stock = list_stock_funds()
            for fnd in stock:
                if fnd["shortName"] not in seen:
                    seen.add(fnd["shortName"])
                    funds.append(fnd)
            print(f"  → {len(stock)} quỹ cổ phiếu: "
                  + ", ".join(f["shortName"] for f in stock))
        elif s not in seen:
            seen.add(s)
            funds.append({"shortName": s, "id": None, "name": None})
    return funds


def get_nav_history(fund_id: int) -> list:
    """Lấy toàn bộ lịch sử NAV. Trả về [[epoch_ms_ngày, nav], ...] tăng dần theo ngày."""
    url = "https://api.fmarket.vn/res/product/get-nav-history"
    payload = {
        "isAllData": 1,
        "productId": fund_id,
        "fromDate": None,
        "toDate": datetime.now().strftime("%Y%m%d"),
    }
    r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"API {r.status_code}: {r.text[:200]}")
    data = r.json()["data"]
    rows = []
    for item in data:
        d = item.get("navDate")
        nav = item.get("nav")
        if d is None or nav is None:
            continue
        # navDate dạng "2021-01-04" hoặc epoch ms — xử lý cả hai
        if isinstance(d, (int, float)):
            ts = int(d)
        else:
            ts = int(datetime.strptime(str(d)[:10], "%Y-%m-%d")
                     .replace(tzinfo=timezone.utc).timestamp() * 1000)
        rows.append([ts, float(nav)])
    # sort + khử trùng lặp theo ngày (giữ bản ghi cuối)
    rows.sort(key=lambda x: x[0])
    dedup = {}
    for ts, nav in rows:
        dedup[ts] = nav
    return [[ts, dedup[ts]] for ts in sorted(dedup)]


# Header giả trình duyệt cho các API chỉ số (một số nhà cung cấp chặn request "lạ").
INDEX_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
}


def _day_ms(ts_sec) -> int:
    """Chuẩn hóa epoch giây (hoặc ISO date) về epoch ms lúc 00:00 UTC của ngày đó."""
    day = datetime.fromtimestamp(int(ts_sec), tz=timezone.utc).date()
    return int(datetime(day.year, day.month, day.day,
                        tzinfo=timezone.utc).timestamp() * 1000)


def _from_cafef(symbol: str) -> list:
    """Nguồn lịch sử DÀI NHẤT: CafeF (về tận ~2000). JSON ashx, không cần auth.
    symbol dạng CafeF: VN-Index → 'VNINDEX', VN30 → 'VN30'."""
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    rows, page = [], 1
    while True:
        params = {"Symbol": symbol, "StartDate": "", "EndDate": "",
                  "PageIndex": page, "PageSize": 5000}
        r = requests.get(url, params=params, headers=INDEX_HEADERS, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"CafeF {r.status_code}: {r.text[:150]}")
        try:
            payload = r.json()
        except Exception:
            payload = json.loads(r.text)
        data = (payload.get("Data") or {})
        items = data.get("Data") or []
        if not items:
            break
        for it in items:
            d = it.get("Ngay")
            close = it.get("GiaDongCua", it.get("GiaDieuChinh"))
            if d is None or close in (None, "", "--"):
                continue
            if isinstance(close, str):
                close = close.replace(",", "").strip()
                if not close:
                    continue
            dt = datetime.strptime(str(d)[:10], "%d/%m/%Y").replace(tzinfo=timezone.utc)
            rows.append([_day_ms(dt.timestamp()), float(close)])
        total = data.get("TotalCount") or len(items)
        if page * 5000 >= total or len(items) < 5000:
            break
        page += 1
        time.sleep(0.5)
    return rows


def _from_tcbs(symbol: str) -> list:
    """TCBS (Techcombank Securities) — bền, trả nhiều năm/lần gọi."""
    url = "https://apipubaggr.tcbs.com.vn/stock-insight/v2/stock/bars-long-term"
    now = datetime.now(timezone.utc)
    params = {
        "ticker": symbol, "type": "index", "resolution": "D",
        "to": int(now.timestamp()), "countBack": 10000,
    }
    r = requests.get(url, params=params, headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"TCBS {r.status_code}: {r.text[:150]}")
    data = r.json().get("data") or []
    rows = []
    for it in data:
        d, close = it.get("tradingDate"), it.get("close")
        if d is None or close is None:
            continue
        # tradingDate: ISO "2024-01-02T00:00:00.000Z" hoặc epoch ms
        if isinstance(d, (int, float)):
            ts = _day_ms(int(d) / 1000)
        else:
            dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            ts = _day_ms(dt.timestamp())
        rows.append([ts, float(close)])
    return rows


def _from_entrade(symbol: str) -> list:
    """Dự phòng 1: DNSE Entrade (định dạng UDF t/o/h/l/c)."""
    url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/index"
    frm = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp())
    to = int(datetime.now(timezone.utc).timestamp())
    params = {"from": frm, "to": to, "symbol": symbol, "resolution": "1D"}
    r = requests.get(url, params=params, headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Entrade {r.status_code}: {r.text[:150]}")
    data = r.json()
    if not data.get("t"):
        raise RuntimeError("Entrade: rỗng")
    return [[_day_ms(ts), float(c)] for ts, c in zip(data["t"], data["c"])]


def _from_vndirect(symbol: str) -> list:
    """Dự phòng 2: VNDirect dchart (UDF, chia khúc 5 năm)."""
    url = "https://dchart-api.vndirect.com.vn/dchart/history"
    hdr = dict(INDEX_HEADERS, Referer="https://dchart.vndirect.com.vn/")
    rows = []
    cur = datetime(2004, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    while cur < now:
        nxt = min(cur.replace(year=cur.year + 5), now)
        params = {"resolution": "D", "symbol": symbol,
                  "from": int(cur.timestamp()), "to": int(nxt.timestamp())}
        r = requests.get(url, params=params, headers=hdr, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"VNDirect {r.status_code}: {r.text[:150]}")
        data = r.json()
        if data.get("s") == "ok" and data.get("t"):
            for ts_sec, close in zip(data["t"], data["c"]):
                rows.append([_day_ms(ts_sec), float(close)])
        cur = nxt
        time.sleep(1)
    return rows


def get_index_history(symbol: str = "VNINDEX") -> list:
    """Lịch sử close chỉ số, thử lần lượt nhiều nguồn cho tới khi được.
    Trả về [[epoch_ms_ngày, close], ...] tăng dần, đã khử trùng lặp theo ngày."""
    # Ưu tiên nguồn có lịch sử DÀI (để so được 5Y/10Y), Entrade để cuối (ngắn nhưng bền).
    sources = [("CafeF", _from_cafef), ("VNDirect", _from_vndirect),
               ("TCBS", _from_tcbs), ("Entrade", _from_entrade)]
    rows, last_err = [], None
    for name, fn in sources:
        try:
            rows = fn(symbol)
            if rows:
                print(f"  (nguồn {name})", flush=True)
                break
        except Exception as e:
            last_err = e
            print(f"  {name} lỗi: {e}", flush=True)
    if not rows:
        raise RuntimeError(f"Tất cả nguồn đều lỗi. Cuối: {last_err}")
    rows.sort(key=lambda x: x[0])
    dedup = {}
    for ts, c in rows:
        dedup[ts] = c
    return [[ts, dedup[ts]] for ts in sorted(dedup)]


def _gold_stooq(sym: str) -> list:
    """CSV stooq (Date,Open,High,Low,Close,Volume)."""
    r = requests.get("https://stooq.com/q/d/l/", params={"s": sym, "i": "d"},
                     headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"stooq {r.status_code}")
    lines = r.text.strip().splitlines()
    if len(lines) < 2 or not lines[0].lower().startswith("date"):
        raise RuntimeError(f"stooq trả về lạ: {r.text[:100]}")
    rows = []
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) < 5:
            continue
        try:
            dt = datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            rows.append([_day_ms(dt.timestamp()), float(parts[4])])
        except Exception:
            continue
    return rows


def _gold_yahoo(sym: str) -> list:
    """Yahoo Finance chart API (JSON). sym vd 'GC=F' (vàng tương lai) hoặc 'XAUUSD=X'."""
    from urllib.parse import quote
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym)}"
    r = requests.get(url, params={"range": "30y", "interval": "1d"},
                     headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"yahoo {r.status_code}")
    res = (r.json().get("chart") or {}).get("result") or []
    if not res:
        raise RuntimeError("yahoo: rỗng")
    res = res[0]
    ts = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    rows = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        rows.append([_day_ms(int(t)), float(c)])
    return rows


def get_gold_history() -> list:
    """Giá vàng thế giới theo ngày, thử nhiều nguồn. [[epoch_ms_ngày, close], ...]."""
    sources = [
        ("stooq XAUUSD", lambda: _gold_stooq("xauusd")),
        ("Yahoo GC=F", lambda: _gold_yahoo("GC=F")),
        ("Yahoo XAUUSD=X", lambda: _gold_yahoo("XAUUSD=X")),
        ("stooq XAU", lambda: _gold_stooq("xau")),
    ]
    rows, last_err = [], None
    for name, fn in sources:
        try:
            rows = fn()
            if rows:
                print(f"  (nguồn {name})", flush=True)
                break
        except Exception as e:
            last_err = e
            print(f"  {name} lỗi: {e}", flush=True)
    if not rows:
        raise RuntimeError(f"Tất cả nguồn vàng đều lỗi. Cuối: {last_err}")
    rows.sort(key=lambda x: x[0])
    dedup = {}
    for ts, c in rows:
        dedup[ts] = c
    return [[ts, dedup[ts]] for ts in sorted(dedup)]


# ---- ETF niêm yết trên HOSE (lấy GIÁ thị trường từ nguồn chứng khoán) ----
ETFS = [
    ("E1VFVN30", "DCVFM VN30 ETF"),
    ("FUEVFVND", "DCVFM VNDIAMOND ETF"),
    ("FUESSVFL", "SSIAM VNFIN LEAD ETF"),
    ("FUEVN100", "SSIAM VN100 ETF"),
    ("FUEMAV30", "Mirae Asset VN30 ETF"),
]


def _stock_entrade(sym: str) -> list:
    url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
    frm = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp())
    to = int(datetime.now(timezone.utc).timestamp())
    r = requests.get(url, params={"from": frm, "to": to, "symbol": sym, "resolution": "1D"},
                     headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Entrade {r.status_code}")
    data = r.json()
    if not data.get("t"):
        raise RuntimeError("Entrade rỗng")
    return [[_day_ms(ts), float(c)] for ts, c in zip(data["t"], data["c"])]


def _stock_tcbs(sym: str) -> list:
    url = "https://apipubaggr.tcbs.com.vn/stock-insight/v2/stock/bars-long-term"
    r = requests.get(url, params={"ticker": sym, "type": "stock", "resolution": "D",
                                  "to": int(datetime.now(timezone.utc).timestamp()), "countBack": 10000},
                     headers=INDEX_HEADERS, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"TCBS {r.status_code}")
    data = r.json().get("data") or []
    rows = []
    for it in data:
        d, close = it.get("tradingDate"), it.get("close")
        if d is None or close is None:
            continue
        if isinstance(d, (int, float)):
            ts = _day_ms(int(d) / 1000)
        else:
            ts = _day_ms(datetime.strptime(str(d)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        rows.append([ts, float(close)])
    return rows


def get_stock_history(sym: str) -> list:
    """Lịch sử giá 1 mã niêm yết (ETF/cổ phiếu), thử nhiều nguồn. [[ms, close], ...]."""
    sources = [("CafeF", lambda: _from_cafef(sym)), ("VNDirect", lambda: _from_vndirect(sym)),
               ("Entrade", lambda: _stock_entrade(sym)), ("TCBS", lambda: _stock_tcbs(sym))]
    rows, last = [], None
    for name, fn in sources:
        try:
            rows = fn()
            if rows:
                print(f"  (nguồn {name})", flush=True)
                break
        except Exception as e:
            last = e
            print(f"  {name} lỗi: {e}", flush=True)
    if not rows:
        raise RuntimeError(f"Hết nguồn cho {sym}. Cuối: {last}")
    rows.sort(key=lambda x: x[0])
    dedup = {}
    for ts, c in rows:
        dedup[ts] = c
    return [[ts, dedup[ts]] for ts in sorted(dedup)]


def main():
    funds = build_fund_list()
    if not funds:
        print("funds.txt trống — thêm ít nhất 1 mã quỹ hoặc dòng ALL_STOCK.")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    index = []
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    debug_dumped = False
    for fnd in funds:
        symbol = fnd["shortName"]
        try:
            print(f"Đang tải {symbol}...", flush=True)
            fid, name, owner = fnd.get("id"), fnd.get("name"), fnd.get("owner", "")
            row = fnd.get("row")
            if fid is None:                      # mã gõ tay → tra id + tên + công ty
                info = get_fund_info(symbol)
                fid, name, owner, row = info["id"], info["name"], info.get("owner", ""), info.get("row")
            rows = get_nav_history(fid)
            if not rows:
                print(f"  {symbol}: không có dữ liệu NAV, bỏ qua.")
                continue
            # chi tiết quỹ (danh mục, phí, ...) — lỗi thì vẫn lưu phần NAV
            detail = {}
            try:
                detail = get_fund_detail(fid)
            except Exception as e:
                print(f"  (chi tiết {symbol} lỗi: {e})")
            fund_info = extract_info(row or {}, detail)
            # dump nguyên JSON quỹ đầu tiên để chốt cấu trúc field thật
            if not debug_dumped and (row or detail):
                with open(os.path.join(DATA_DIR, "_debug_fmarket.json"), "w", encoding="utf-8") as f:
                    json.dump({"symbol": symbol, "row": row, "detail": detail}, f,
                              ensure_ascii=False, indent=2)
                debug_dumped = True
                print(f"  (đã dump cấu trúc mẫu → data/_debug_fmarket.json)")
            out = {
                "symbol": symbol,
                "name": name,
                "updatedAt": now_iso,
                "info": fund_info,
                "rows": rows,
            }
            with open(os.path.join(DATA_DIR, f"{symbol}.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
            index.append({
                "symbol": symbol,
                "name": name,
                "owner": owner or "",
                "assetType": fund_info.get("assetType"),
                "inceptionDate": fund_info.get("inceptionDate"),
                "navChange": fund_info.get("navChange"),
                "count": len(rows),
                "firstDate": rows[0][0],
                "lastDate": rows[-1][0],
                "lastNav": rows[-1][1],
            })
            print(f"  {symbol}: {len(rows)} phiên, NAV mới nhất {rows[-1][1]:,.2f}")
            time.sleep(1)  # lịch sự với API
        except Exception as e:
            print(f"  LỖI {symbol}: {e}")

    # ETF niêm yết — lấy giá thị trường, gom nhóm owner="ETF"
    for tk, nm in ETFS:
        try:
            print(f"Đang tải ETF {tk}...", flush=True)
            rows = get_stock_history(tk)
            if not rows:
                print(f"  {tk}: không có dữ liệu, bỏ qua.")
                continue
            out = {"symbol": tk, "name": nm, "updatedAt": now_iso,
                   "info": {"assetType": "ETF (niêm yết)", "owner": "ETF"}, "rows": rows}
            with open(os.path.join(DATA_DIR, f"{tk}.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
            index.append({
                "symbol": tk, "name": nm, "owner": "ETF", "assetType": "ETF (niêm yết)",
                "inceptionDate": None, "navChange": None, "count": len(rows),
                "firstDate": rows[0][0], "lastDate": rows[-1][0], "lastNav": rows[-1][1],
            })
            print(f"  {tk}: {len(rows)} phiên, giá mới nhất {rows[-1][1]:,.2f}")
            time.sleep(1)
        except Exception as e:
            print(f"  LỖI ETF {tk}: {e}")

    # Benchmark VNINDEX (không bắt buộc — lỗi thì web vẫn chạy, chỉ thiếu phần so sánh)
    try:
        print("Đang tải VNINDEX (benchmark)...", flush=True)
        vrows = get_index_history("VNINDEX")
        if vrows:
            with open(os.path.join(DATA_DIR, "VNINDEX.json"), "w", encoding="utf-8") as f:
                json.dump({"symbol": "VNINDEX", "name": "Chỉ số VN-Index",
                           "updatedAt": now_iso, "rows": vrows},
                          f, ensure_ascii=False, separators=(",", ":"))
            print(f"  VNINDEX: {len(vrows)} phiên, close mới nhất {vrows[-1][1]:,.2f}")
    except Exception as e:
        print(f"  LỖI VNINDEX: {e}")

    # Giá vàng thế giới (không bắt buộc — để so sánh DCA)
    try:
        print("Đang tải giá vàng (XAU/USD)...", flush=True)
        grows = get_gold_history()
        if grows:
            with open(os.path.join(DATA_DIR, "GOLD.json"), "w", encoding="utf-8") as f:
                json.dump({"symbol": "XAUUSD", "name": "Vàng thế giới (XAU/USD)",
                           "updatedAt": now_iso, "rows": grows},
                          f, ensure_ascii=False, separators=(",", ":"))
            print(f"  Vàng: {len(grows)} phiên, giá mới nhất {grows[-1][1]:,.2f}")
    except Exception as e:
        print(f"  LỖI Vàng: {e}")

    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"updatedAt": now_iso, "funds": index}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"Xong. Đã ghi {len(index)}/{len(funds)} quỹ vào {DATA_DIR}")


if __name__ == "__main__":
    main()
