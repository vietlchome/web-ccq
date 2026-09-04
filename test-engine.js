/* Đối chiếu engine.js với chỉ báo TradingView.  Chạy: node test-engine.js
   Vàng là mốc chuẩn (giá vàng gần như giống nhau mọi nguồn).
   BTC chỉ để tham khảo: mỗi sàn một giá nên không kỳ vọng khớp tuyệt đối. */
const E = require("./engine.js"), fs = require("fs"), path = require("path");
const load = s => JSON.parse(fs.readFileSync(path.join(__dirname, "data", s + ".json"), "utf8")).rows;
let fail = 0;

function suite(name, sym, params, tv, tol) {
  const rows = load(sym);
  let base = null, tvBase = tv[1].cost;
  console.log(`\n${name}`);
  console.log("  cách   giá vốn TB          rẻ hơn Cách 1        lệch");
  for (const w of E.WAYS) {
    const r = E.runBacktest(rows, { ...params, onlyBuyBelowEMA: w.onlyBuyBelowEMA, enableMult: w.enableMult });
    if (w.id === 1) base = r.avgCost;
    const mine = (1 - r.avgCost / base) * 100, ref = (1 - tv[w.id].cost / tvBase) * 100;
    const gap = Math.abs(mine - ref), ok = gap <= tol;
    if (!ok) fail++;
    console.log(`   ${w.id}   ${r.avgCost.toFixed(0).padStart(6)} vs ${tv[w.id].cost.toFixed(0).padStart(6)}`
      + `   ${mine.toFixed(1).padStart(6)}% vs ${ref.toFixed(1).padStart(6)}%`
      + `   ${gap.toFixed(1).padStart(5)}đ ${ok ? "✓" : "✗"}`);
  }
}

suite("VÀNG — mốc chuẩn (ngưỡng lệch 1.5 điểm)", "GOLD",
  { dcaDays: 7, buyAmount: 20, stepPctD: 5, stepPctW: 5, multCap: 10, startDate: "2006-10-01", endDate: "2026-08-05" },
  { 1: { cost: 1357.04 }, 2: { cost: 1311.16 }, 3: { cost: 1236.53 }, 4: { cost: 1292.02 } }, 1.5);

suite("BTC — tham khảo, khác nguồn giá (ngưỡng 15 điểm)", "BTC",
  { dcaDays: 7, buyAmount: 20, stepPctD: 5, stepPctW: 5, multCap: 10, startDate: "2016-09-01", endDate: "2026-08-05" },
  { 1: { cost: 6907.87 }, 2: { cost: 12648.36 }, 3: { cost: 10633.39 }, 4: { cost: 8634.67 } }, 15);

/* Lưới lịch: quỹ NAV thưa phải cho kết quả khác hẳn cách đếm điểm dữ liệu */
console.log("\nLƯỚI LỊCH — quỹ NAV thưa");
for (const sym of ["VCBF-BCF", "FUESSVFL"]) {
  const rows = load(sym), g = E.toCalendarGrid(rows);
  const yrs = (rows[rows.length - 1][0] - rows[0][0]) / 31557600000;
  const emaRaw = E.emaSeries(rows.map(r => r[1]), 200);
  const pctRaw = 100 * rows.filter((r, i) => r[1] < emaRaw[i]).length / rows.length;
  const emaCal = E.emaSeries(g.closes, 200);
  const pctCal = 100 * g.closes.filter((c, i) => c < emaCal[i]).length / g.closes.length;
  console.log(`  ${sym.padEnd(10)} ${(rows.length / yrs).toFixed(0).padStart(4)} điểm/năm`
    + `  |  đếm điểm ${pctRaw.toFixed(1)}%  ->  lịch ${pctCal.toFixed(1)}%`
    + `  (lệch ${(pctCal - pctRaw >= 0 ? "+" : "") + (pctCal - pctRaw).toFixed(1)} điểm)`);
}

console.log(fail ? `\n✗ ${fail} mục lệch quá ngưỡng` : "\n✓ Tất cả trong ngưỡng");
process.exit(fail ? 1 : 0);
