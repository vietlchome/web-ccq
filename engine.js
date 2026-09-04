/* =========================================================================
   DCA EMA200 — ĐỘNG CƠ BACKTEST  (engine.js)
   Dùng được ở hai nơi:
     • Trình duyệt:  <script src="engine.js"></script>  ->  window.DCAEngine
     • Node (test):  const E = require("./engine.js");
   Không phụ thuộc thư viện nào, không đụng DOM.

   BA QUY ƯỚC QUAN TRỌNG
   1. LỊCH, KHÔNG PHẢI ĐIỂM DỮ LIỆU.
      Quỹ mở công bố NAV với tần suất rất khác nhau (48 -> 365 điểm/năm).
      Nếu tính EMA200 trên mảng NAV thô thì "EMA200" của TBLF là 4.2 năm
      còn của BTC là 0.55 năm — cùng một dòng code, ý nghĩa lệch 8 lần.
      Nên mọi thứ chạy trên LƯỚI NGÀY LÀM VIỆC (forward-fill NAV).
   2. KHÔNG NHÌN TRƯỚC.
      Quyết định dựa trên phiên i-1, khớp lệnh ở phiên i. EMA tuần chỉ dùng
      tuần ĐÃ ĐÓNG.
   3. CHỈ KHỚP KHI CÓ NAV THẬT.
      Ngày forward-fill không giao dịch được. Lệnh dời sang phiên NAV kế tiếp.
   ========================================================================= */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DCAEngine = factory();
})(typeof self !== "undefined" ? self : this, function () {
"use strict";

var DAY = 86400000, WEEK = 7 * DAY, YEAR = 31557600000;

/* ---------- 1. LƯỚI LỊCH ---------------------------------------------- */
function toCalendarGrid(rows) {
  if (!rows || !rows.length) return { times: [], closes: [], isReal: [] };
  var byDay = Object.create(null);
  for (var i = 0; i < rows.length; i++) {
    var d = new Date(rows[i][0]);
    byDay[Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())] = rows[i][1];
  }
  var keys = Object.keys(byDay).map(Number).sort(function (a, b) { return a - b; });
  // Nhịp lịch phải theo CHÍNH tài sản: crypto chạy 7 ngày/tuần, cổ phiếu và quỹ
  // chỉ chạy T2-T6. Suy ra từ dữ liệu thay vì áp đặt, nếu không "mỗi 7 phiên"
  // sẽ mang hai nghĩa khác nhau (52 lệnh/năm vs 37 lệnh/năm).
  var wkEnd = 0;
  for (var q = 0; q < keys.length; q++) { var dw = new Date(keys[q]).getUTCDay(); if (dw === 0 || dw === 6) wkEnd++; }
  var allDays = keys.length > 0 && (wkEnd / keys.length) > 0.10;
  var t = keys[0], end = keys[keys.length - 1];
  var times = [], closes = [], isReal = [], last = null;
  while (t <= end) {
    var wd = new Date(t).getUTCDay();
    if (allDays || (wd !== 0 && wd !== 6)) {
      var real = byDay[t] !== undefined;
      if (real) last = byDay[t];
      if (last !== null) { times.push(t); closes.push(last); isReal.push(real); }
    }
    t += DAY;
  }
  return { times: times, closes: closes, isReal: isReal, allDays: allDays };
}

/* ---------- 2. EMA ------------------------------------------------------ */
function emaSeries(values, period) {
  var a = 2 / (period + 1), out = new Array(values.length), prev = values[0];
  out[0] = prev;
  for (var i = 1; i < values.length; i++) { prev = a * values[i] + (1 - a) * prev; out[i] = prev; }
  return out;
}

// EMA200 khung TUẦN, ánh xạ về từng ngày của lưới.
// Ngày trong tuần k nhận EMA của tuần k-1 (tuần đã đóng) -> không nhìn trước.
function weeklyEmaOnGrid(times, closes, period) {
  period = period || 200;
  var wkOf = function (ms) { return Math.floor((ms - 4 * DAY) / WEEK); };
  var wKeys = [], wClose = [], dayWeekIdx = new Array(times.length);
  for (var i = 0; i < times.length; i++) {
    var k = wkOf(times[i]);
    if (wKeys.length && wKeys[wKeys.length - 1] === k) wClose[wClose.length - 1] = closes[i];
    else { wKeys.push(k); wClose.push(closes[i]); }
    dayWeekIdx[i] = wKeys.length - 1;
  }
  var wEma = wClose.length ? emaSeries(wClose, period) : [];
  var out = new Array(times.length);
  for (var j = 0; j < times.length; j++) {
    var wi = dayWeekIdx[j] - 1;                  // tuần đã đóng gần nhất
    out[j] = wi >= 0 ? wEma[wi] : null;
  }
  return { perDay: out, weekCount: wClose.length };
}

/* ---------- 3. MỎ NEO ĐÔI ---------------------------------------------- */
// hệ số = max(1, %dưới EMA200D / stepD) + (%dưới EMA200W / stepW)
// Sàn 1.0, làm tròn 1 chữ số, chặn bởi trần. Trên EMA200D -> không mua khi bật lọc.
function buyMultiplier(close, emaD, emaW, p) {
  if (close == null || emaD == null || !(emaD > 0)) return p.onlyBuyBelowEMA ? 0 : 1;
  var belowD = close < emaD;
  if (!belowD && p.onlyBuyBelowEMA) return 0;
  if (!p.enableMult) return 1;
  var anchorD = belowD ? Math.max(1, ((emaD - close) / emaD * 100) / p.stepPctD) : 1;
  var anchorW = 0;
  if (emaW != null && emaW > 0 && close < emaW) anchorW = ((emaW - close) / emaW * 100) / p.stepPctW;
  var m = Math.round((anchorD + anchorW) * 10) / 10;
  return Math.min(p.multCap, Math.max(1, m));
}

/* ---------- 4. IRR ------------------------------------------------------ */
function irrAnnual(years, amounts, finalValue, finalYear) {
  if (!amounts.length) return null;
  var npv = function (r) {
    var s = finalValue / Math.pow(1 + r, finalYear);
    for (var i = 0; i < amounts.length; i++) s += amounts[i] / Math.pow(1 + r, years[i]);
    return s;
  };
  var lo = -0.95, hi = 10;
  if (npv(lo) < 0 || npv(hi) > 0) return null;
  for (var k = 0; k < 300; k++) { var m = (lo + hi) / 2; if (npv(m) > 0) lo = m; else hi = m; }
  return (lo + hi) / 2;
}

/* ---------- 5. BACKTEST ------------------------------------------------- */
var DEFAULTS = {
  dcaDays: 5,           // phiên LỊCH giữa hai lần mua
  buyAmount: 1,         // tiền mua cơ sở (đơn vị tuỳ người dùng)
  lumpsum: 0,
  onlyBuyBelowEMA: false,
  enableMult: false,
  stepPctD: 5, stepPctW: 5, multCap: 10,
  escRate: 0,           // Tiền điều chỉnh mỗi năm (%), neo ở phiên CUỐI
  feeBuyPct: 0,         // phí mua CCQ (%). Phí quản lý KHÔNG cộng: NAV đã trừ rồi.
  startDate: null, endDate: null
};

function runBacktest(rows, params) {
  var p = {}; for (var k in DEFAULTS) p[k] = DEFAULTS[k];
  for (var k2 in (params || {})) if (params[k2] !== undefined) p[k2] = params[k2];

  var g = toCalendarGrid(rows);
  var n = g.times.length;
  if (!n) return null;
  var emaD = emaSeries(g.closes, 200);
  var w = weeklyEmaOnGrid(g.times, g.closes, 200);
  var emaW = w.perDay;

  var s = p.startDate ? Date.parse(p.startDate + "T00:00:00Z") : -Infinity;
  var e = p.endDate ? Date.parse(p.endDate + "T23:59:59Z") : Infinity;
  var anchorT = g.times[n - 1];

  var totalInvested = 0, totalUnits = 0, nOrders = 0, sumMult = 0, nFloor = 0;
  var maxMult = 0, firstT = null, lastBuyIdx = null, lump = false;
  var minPnl = null, nSessions = 0;
  var cfY = [], cfA = [], buys = [];
  var wkSpend = [], curWk = 0, curWkKey = null;   // chi tiêu quy về TIỀN HÔM NAY

  for (var i = 0; i < n; i++) {
    var t = g.times[i];
    if (t < s || t > e) continue;
    nSessions++;
    var wkKey = Math.floor((t - 4 * DAY) / WEEK);
    if (curWkKey === null) curWkKey = wkKey;
    while (curWkKey < wkKey) { wkSpend.push(curWk); curWk = 0; curWkKey++; }

    var esc = p.escRate > 0 ? Math.pow(1 + p.escRate / 100, (t - anchorT) / YEAR) : 1;

    if (!lump && p.lumpsum > 0) {
      lump = true; firstT = t;
      var la = p.lumpsum * esc;
      totalInvested += la;
      totalUnits += (la * (1 - p.feeBuyPct / 100)) / g.closes[i];
      cfY.push(0); cfA.push(-la);
    }

    // tín hiệu đọc phiên TRƯỚC; chỉ khớp vào ngày có NAV thật
    var due = lastBuyIdx === null || (i - lastBuyIdx) >= p.dcaDays;
    if (due && g.isReal[i] && i > 0) {
      var mult = buyMultiplier(g.closes[i - 1], emaD[i - 1], emaW[i - 1], p);
      if (mult > 0) {
        var today = p.buyAmount * mult;          // tiền HÔM NAY -> nuôi chẩn đoán
        var nominal = today * esc;               // tiền DANH NGHĨA -> vào danh mục
        if (firstT === null) firstT = t;
        totalInvested += nominal;
        totalUnits += (nominal * (1 - p.feeBuyPct / 100)) / g.closes[i];
        nOrders++; sumMult += mult; curWk += today;
        if (mult > maxMult) maxMult = mult;
        if (mult <= 1.0) nFloor++;
        lastBuyIdx = i;
        cfY.push((t - firstT) / YEAR); cfA.push(-nominal);
        buys.push({ time: t, price: g.closes[i], mult: mult, amount: nominal });
      }
    }

    if (totalInvested > 0) {
      var pnl = (totalUnits * g.closes[i] - totalInvested) / totalInvested * 100;
      if (minPnl === null || pnl < minPnl) minPnl = pnl;
    }
  }
  wkSpend.push(curWk);

  var lastIdx = n - 1;
  for (var z = n - 1; z >= 0; z--) if (g.times[z] <= e) { lastIdx = z; break; }
  var finalPrice = g.closes[lastIdx];
  var finalValue = totalUnits * finalPrice;
  var years = firstT === null ? 0 : (g.times[lastIdx] - firstT) / YEAR;

  return {
    symbol: null,
    years: years,
    nSessions: nSessions,
    nWeeks: wkSpend.length,
    nOrders: nOrders,
    pctWeeksWithOrder: wkSpend.length ? 100 * wkSpend.filter(function (x) { return x > 0; }).length / wkSpend.length : 0,
    multAvg: nOrders ? sumMult / nOrders : 0,
    multMax: maxMult,
    pctAtFloor: nOrders ? 100 * nFloor / nOrders : 0,
    totalInvested: totalInvested,
    totalUnits: totalUnits,
    avgCost: totalUnits > 0 ? totalInvested / totalUnits : null,
    finalPrice: finalPrice,
    finalValue: finalValue,
    pnlPct: totalInvested > 0 ? (finalValue / totalInvested - 1) * 100 : null,
    minPnlPct: minPnl,
    irrPct: firstT === null ? null : (function () {
      var r = irrAnnual(cfY, cfA, finalValue, (g.times[lastIdx] - firstT) / YEAR);
      return r === null ? null : r * 100;
    })(),
    cashflow: cashflowStats(wkSpend),
    buys: buys,
    weekCount: w.weekCount,
    _grid: g, _emaD: emaD, _emaW: emaW
  };
}

/* ---------- 6. CHẨN ĐOÁN DÒNG TIỀN (đơn vị TIỀN HÔM NAY) ---------------- */
function cashflowStats(wkSpend) {
  var nW = wkSpend.length;
  if (!nW) return null;
  var sum = 0, mx = 0, i;
  for (i = 0; i < nW; i++) { sum += wkSpend[i]; if (wkSpend[i] > mx) mx = wkSpend[i]; }
  var avgAll = sum / nW;
  var buyW = wkSpend.filter(function (x) { return x > 0; });
  var avgBuy = buyW.length ? buyW.reduce(function (a, b) { return a + b; }, 0) / buyW.length : 0;

  // 13 tuần liên tiếp nặng nhất
  var win = Math.min(13, nW), run = 0, best = 0;
  for (i = 0; i < nW; i++) {
    run += wkSpend[i];
    if (i >= win) run -= wkSpend[i - win];
    if (i >= win - 1 && run > best) best = run;
  }
  // ĐỆM CẦN CÓ: tiết kiệm đều bằng avgAll, điểm hụt sâu nhất
  var cash = 0, worst = 0;
  for (i = 0; i < nW; i++) { cash += avgAll - wkSpend[i]; if (cash < worst) worst = cash; }

  return {
    avgWeekAll: avgAll, avgWeekBuy: avgBuy,
    peakWeek: mx, peakQuarter: best, quarterWin: win,
    bufferWeeks: avgAll > 0 ? -worst / avgAll : null,
    bufferMoney: -worst
  };
}

/* ---------- 7. BỐN CÁCH DÙNG ------------------------------------------- */
var WAYS = [
  { id: 1, name: "Mua đều, không nhìn giá",        onlyBuyBelowEMA: false, enableMult: false },
  { id: 2, name: "Chỉ mua khi giá rẻ",             onlyBuyBelowEMA: true,  enableMult: false },
  { id: 3, name: "Chỉ mua khi rẻ, càng rẻ càng đậm", onlyBuyBelowEMA: true,  enableMult: true },
  { id: 4, name: "Mua đều, rẻ thì mua đậm",        onlyBuyBelowEMA: false, enableMult: true }
];

// savingPerWeek: khả năng tiết kiệm mỗi tuần (cùng đơn vị buyAmount)
// cashOnHand:    tiền mặt sẵn có
function compareFour(rows, params, profile) {
  profile = profile || {};
  var res = WAYS.map(function (wy) {
    var p = Object.assign({}, params, { onlyBuyBelowEMA: wy.onlyBuyBelowEMA, enableMult: wy.enableMult });
    var r = runBacktest(rows, p);
    if (r) { r.wayId = wy.id; r.wayName = wy.name; }
    return r;
  });
  var ok = res.filter(Boolean);
  if (!ok.length) return { ways: res, compare: null };

  // Khả năng huy động lấy theo CỬA SỔ DÀI NHẤT: bạn tiết kiệm từ ngày đầu,
  // kể cả những năm chiến thuật lọc chưa mua gì.
  var maxWeeks = Math.max.apply(null, ok.map(function (r) { return r.nWeeks; }));
  var save = profile.savingPerWeek || null;
  var capacity = save ? save * maxWeeks : null;
  var base = ok.find(function (r) { return r.wayId === 1; });

  ok.forEach(function (r) {
    r.capacityPct = capacity ? r.totalInvested / capacity * 100 : null;
    r.scaleFactor = capacity ? capacity / r.totalInvested : null;
    r.valueAtFullScale = r.scaleFactor ? r.finalValue * r.scaleFactor : null;
    r.unusedCash = capacity ? capacity - r.totalInvested : null;
    r.endWealth = r.unusedCash === null ? null : r.finalValue + r.unusedCash;
    r.cheaperThanWay1 = (base && base.avgCost) ? (1 - r.avgCost / base.avgCost) * 100 : null;
    r.bufferMoneyAtScale = (r.scaleFactor && save && r.cashflow)
      ? r.cashflow.bufferWeeks * save * r.scaleFactor : null;
    r.gateCash = (r.bufferMoneyAtScale && profile.cashOnHand) ? r.bufferMoneyAtScale / profile.cashOnHand : null;
    r.gateLoss = (r.minPnlPct != null && profile.maxDrawdownPct) ? Math.abs(r.minPnlPct) / profile.maxDrawdownPct : null;
    r.gateWait = (r.cashflow && profile.maxWaitWeeks) ? r.cashflow.bufferWeeks / profile.maxWaitWeeks : null;
    var gates = [r.gateCash, r.gateLoss, r.gateWait].filter(function (x) { return x != null; });
    r.worstGate = gates.length ? Math.max.apply(null, gates) : null;
    r.verdict = r.worstGate == null ? null
      : (r.worstGate > 1 ? "KHÔNG KHẢ THI" : (r.worstGate > 0.8 ? "CÂN NHẮC" : "KHẢ THI"));
    r.overCapacity = r.capacityPct != null && r.capacityPct > 105;
  });

  var pick = ok.filter(function (r) { return r.verdict === "KHẢ THI" && !r.overCapacity; })
               .sort(function (a, b) { return (b.endWealth || 0) - (a.endWealth || 0) })[0];
  return { ways: res, best: pick ? pick.wayId : null, capacity: capacity, maxWeeks: maxWeeks };
}

/* ---------- 8. GẮN LẠI VÀO MẢNG rows GỐC -------------------------------
   Cho phép UI cũ giữ nguyên vòng lặp theo rows, nhưng EMA và nhịp DCA
   được tính trên LỊCH. Trả về ba mảng cùng độ dài với rows.            */
function alignToRows(rows, period) {
  period = period || 200;
  var g = toCalendarGrid(rows);
  var eD = emaSeries(g.closes, period);
  var eW = weeklyEmaOnGrid(g.times, g.closes, period).perDay;
  var pos = Object.create(null);
  for (var i = 0; i < g.times.length; i++) pos[g.times[i]] = i;
  var dayKey = function (ms) { var d = new Date(ms); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); };
  var emaD = new Array(rows.length), emaW = new Array(rows.length), gridIdx = new Array(rows.length);
  var lastK = 0;
  for (var r = 0; r < rows.length; r++) {
    var k = pos[dayKey(rows[r][0])];
    if (k === undefined) k = lastK; else lastK = k;
    gridIdx[r] = k; emaD[r] = eD[k]; emaW[r] = eW[k];
  }
  return { emaD: emaD, emaW: emaW, gridIdx: gridIdx, gridLen: g.times.length, allDays: g.allDays };
}

return {
  toCalendarGrid: toCalendarGrid,
  alignToRows: alignToRows,
  emaSeries: emaSeries,
  weeklyEmaOnGrid: weeklyEmaOnGrid,
  buyMultiplier: buyMultiplier,
  irrAnnual: irrAnnual,
  cashflowStats: cashflowStats,
  runBacktest: runBacktest,
  compareFour: compareFour,
  WAYS: WAYS,
  DEFAULTS: DEFAULTS
};
});
