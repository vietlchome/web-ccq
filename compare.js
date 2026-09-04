#!/usr/bin/env node
/* So 4 cách mua trên dữ liệu quỹ trong data/.
   Ví dụ:
     node compare.js FUESSVFL
     node compare.js VESAF --tien=2 --tiet-kiem=2 --tien-mat=100 --chu-ky=5
     node compare.js --tat-ca                 (quét toàn bộ quỹ)
   Tham số (đơn vị tiền tuỳ bạn, chỉ cần nhất quán):
     --tien       tiền mua cơ sở mỗi lệnh      (mặc định = --tiet-kiem)
     --tiet-kiem  khả năng tiết kiệm mỗi tuần  (mặc định 2)
     --tien-mat   tiền mặt sẵn có              (mặc định 50 tuần tiết kiệm)
     --chu-ky     số phiên lịch giữa 2 lệnh    (mặc định 5)
     --buoc-d --buoc-w  bước nhảy % mỗi mỏ neo (mặc định 5)
     --tran       trần hệ số                   (mặc định 10)
     --dc         tiền điều chỉnh mỗi năm %    (mặc định 0)
     --lo         chịu lỗ tối đa %             (mặc định 40)
     --tu --den   ngày bắt đầu / kết thúc      (YYYY-MM-DD)
*/
const E = require("./engine.js"), fs = require("fs"), path = require("path");
const DIR = path.join(__dirname, "data");
const arg = (k, d) => { const a = process.argv.find(x => x.startsWith("--" + k + "=")); return a ? a.split("=")[1] : d; };
const has = k => process.argv.includes("--" + k);
const num = (k, d) => parseFloat(arg(k, d));

const save = num("tiet-kiem", 2);
const P = {
  dcaDays: num("chu-ky", 5), buyAmount: num("tien", save),
  stepPctD: num("buoc-d", 5), stepPctW: num("buoc-w", 5),
  multCap: num("tran", 10), escRate: num("dc", 0),
  startDate: arg("tu", null), endDate: arg("den", null)
};
const PROF = { savingPerWeek: save, cashOnHand: num("tien-mat", save * 50),
               maxDrawdownPct: num("lo", 40), maxWaitWeeks: 9999 };

const fmt = (v, d = 1) => v == null ? "—" : v.toFixed(d);
const load = s => JSON.parse(fs.readFileSync(path.join(DIR, s + ".json"), "utf8"));

function one(sym, quiet) {
  const d = load(sym); if (!d.rows || d.rows.length < 220) return null;
  const out = E.compareFour(d.rows, P, PROF);
  const ok = out.ways.filter(Boolean); if (!ok.length) return null;
  const w1 = ok.find(r => r.wayId === 1);
  if (!quiet) {
    console.log(`\n${d.symbol} — ${d.name || ""}`);
    console.log(`${(d.info && d.info.assetType) || ""} · ${fmt(w1.years, 1)} năm · khả năng huy động ${fmt(out.capacity, 0)}`);
    console.log("\n  cách  công suất  giá vốn TB  rẻ hơn C1  đệm(tuần)  của cải  quy đổi   cửa căng  kết luận");
    for (const r of ok) {
      console.log(`   ${r.wayId}  ${fmt(r.capacityPct, 0).padStart(7)}%`
        + `  ${fmt(r.avgCost, 0).padStart(10)}`
        + `  ${fmt(r.cheaperThanWay1, 1).padStart(8)}%`
        + `  ${fmt(r.cashflow.bufferWeeks, 0).padStart(9)}`
        + `  ${fmt(r.endWealth, 0).padStart(7)}`
        + `  ${fmt(r.valueAtFullScale, 0).padStart(7)}`
        + `  ${fmt(r.worstGate, 2).padStart(8)}`
        + `  ${r.overCapacity ? "vượt KN" : (r.verdict || "—")}`);
    }
    console.log(`  -> NÊN CHỌN: Cách ${out.best || "—"}`);
  }
  const w3 = ok.find(r => r.wayId === 3);
  return { sym: d.symbol, type: (d.info && d.info.assetType) || "", years: w1.years,
           irr: w1.irrPct, cheaper3: w3 ? w3.cheaperThanWay1 : null,
           scale3: (w3 && w1.valueAtFullScale) ? (w3.valueAtFullScale / w1.valueAtFullScale - 1) * 100 : null,
           best: out.best, buf3: w3 ? w3.cashflow.bufferWeeks : null };
}

if (has("tat-ca")) {
  const syms = fs.readdirSync(DIR).filter(f => f.endsWith(".json") && f !== "changelog.json")
                 .map(f => f.replace(/\.json$/, ""));
  const rs = syms.map(s => { try { return one(s, true); } catch (e) { return null; } }).filter(Boolean);
  rs.sort((a, b) => (a.irr ?? 0) - (b.irr ?? 0));
  console.log("QUÉT TOÀN BỘ — xếp theo IRR của Cách 1 (mua đều)\n");
  console.log("  mã          loại              năm   IRR C1   rẻ hơn C1(C3)  quy đổi(C3)  đệm C3  nên chọn");
  for (const r of rs)
    console.log(`  ${r.sym.padEnd(11)} ${r.type.padEnd(16).slice(0,16)} ${fmt(r.years,1).padStart(5)}`
      + ` ${fmt(r.irr,1).padStart(7)}% ${fmt(r.cheaper3,1).padStart(13)}%`
      + ` ${fmt(r.scale3,1).padStart(11)}% ${fmt(r.buf3,0).padStart(7)}  Cách ${r.best ?? "—"}`);
  const pos = rs.filter(r => r.cheaper3 > 0).length;
  console.log(`\n  Lọc EMA mua được RẺ HƠN ở ${pos}/${rs.length} quỹ`);
} else {
  const sym = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : "FUESSVFL";
  one(sym, false);
}
