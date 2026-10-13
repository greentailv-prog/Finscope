/* ============================================================================
 * interface-check.js —— 接口体检（**只读，不改任何文件**）
 * ----------------------------------------------------------------------------
 * 为什么需要它：
 *   三个队友的交付速度不一样。等 D 把统一数据对象交过来才发现「字段对不上」，
 *   那时候返工的是 D 和 E 两个人；现在量出来，返工只是改个名。
 *
 *   它拿 js/contract.js 那份**消费端契约**去走查任意一份候选数据，回答三个问题：
 *     ① 这份数据，E 能用吗？—— 哪一页会不会退化成空状态
 *     ② 缺的那些，找谁要？  —— 按 A/B/C/D 切开，这就是给队友的需求文档
 *     ③ E 自己的契约有没有漏登记？—— 拿 js/ 里真实出现的取值路径反查对齐
 *
 * ⚠️ 它不校验 Schema。Schema 是 D 的活（字段该叫什么）。
 *    这里校验的是**另一半**：E 实际会去读什么、读不到会怎样。
 *    两边对不上，正是这个工具要暴露的东西。
 *
 * 用法：
 *   node tools/interface-check.js                     # 默认查 data/mock_data.js
 *   node tools/interface-check.js data/real_data.js
 *   node tools/interface-check.js ../A/data/extracted/万华化学_600309_2025.json
 *   node tools/interface-check.js <目录>              # 目录下所有 .json 各出一份
 *
 * 退出码：0 = 所有 core 路径都有值；1 = 存在 core 缺口（可当交付闸门用）
 * ==========================================================================*/

"use strict";

const fs = require("fs");
const vm = require("vm");
const path = require("path");

const ROOT = path.join(__dirname, "..");

/* ------------------------------------------------------------------ */
/* 载入契约（和浏览器用的是同一份 js/contract.js）                     */
/* ------------------------------------------------------------------ */
const sandbox = {};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.console = { log: () => {}, warn: () => {}, error: () => {} };
vm.createContext(sandbox);

const contractFile = path.join(ROOT, "js/contract.js");
if (!fs.existsSync(contractFile)) {
  console.error("找不到 " + contractFile);
  process.exit(1);
}
vm.runInContext(fs.readFileSync(contractFile, "utf8"), sandbox, { filename: "js/contract.js" });
const C = sandbox.FinScope.contract;

/* ------------------------------------------------------------------ */
/* 载入候选数据                                                        */
/* ------------------------------------------------------------------ */

/** 支持两种交付形式：
 *    .js   —— `window.FINSCOPE_DATA = {...}`（推荐形式，file:// 下能用）
 *    .json —— 纯 JSON（A 的抽取结果就是这种）
 */
function loadData(file) {
  const src = fs.readFileSync(file, "utf8");
  if (/\.json$/i.test(file)) return JSON.parse(src);

  const sb = {};
  sb.window = sb;
  sb.globalThis = sb;
  sb.console = { log: () => {}, warn: () => {}, error: () => {} };
  vm.createContext(sb);
  vm.runInContext(src, sb, { filename: file });
  return sb.window.FINSCOPE_DATA || sb.FINSCOPE_DATA;
}

/** 页面 6 的数据源是另一份产物（D 的投研简报绑定表），不在统一对象里。
 *  两个地方都找一遍，先近后远：
 *
 *    ① **打包形态**：data/real_data.js 旁边放 data/real_memo.js
 *       （构建产物 —— 页面的实际交付形态，file:// 下由 index.html 直接引）
 *    ② **D 的原始目录**：out_data/unified/000333.SZ_2025.json 同级的
 *       out_data/reports/000333.SZ_2025/memo.json
 *
 *  ★ 2026-10-13：原来只有 ② 。页面 6 改成读 memo 之后，体检跑在
 *    data/real_data.js 上就永远报「投研报告：整块未提供」—— 数据其实交齐了，
 *    只是不在 ① 之外的路径上。一条永远红的判定比没有判定更坏：它会让人
 *    习惯性地跳过这一格。所以补上 ①。
 *
 *  两处都找不到才返回 undefined —— check() 会把页面 6 整体记成「未提供」，
 *  而不是把 22 条路径逐条报成缺口。**一份文件没交是一件事，不是 22 件事。**
 */
function loadMemo(unifiedFile) {
  const key = path.basename(unifiedFile).replace(/\.(json|js)$/i, "");

  /* ① 打包形态：同目录的 _memo 兄弟文件。
        两个命名都认：real_data.js → real_data_memo.js（同名加后缀）
        与 real_data.js → real_memo.js（去掉 _data 再换 _memo）。
        build-data.js 出的是后者，但前者更像人会顺手起的名字。 */
  const dir = path.dirname(unifiedFile);
  const bases = [path.join(dir, key + "_memo")];
  if (/_data$/.test(key)) bases.push(path.join(dir, key.replace(/_data$/, "") + "_memo"));

  for (const base of bases) for (const ext of [".js", ".json"]) {
    const sib = base + ext;
    try {
      if (!fs.existsSync(sib)) continue;
      const raw = fs.readFileSync(sib, "utf8");
      const parsed = ext === ".json"
        ? JSON.parse(raw)
        : (() => {
            const sb = {};
            sb.window = sb; sb.globalThis = sb;
            sb.console = { log: () => {}, warn: () => {}, error: () => {} };
            vm.createContext(sb);
            vm.runInContext(raw, sb, { filename: sib });
            return sb.window.FINSCOPE_MEMO || sb.FINSCOPE_MEMO;
          })();
      if (parsed) return parsed;
    } catch (e) { /* 读不动就试下一个 */ }
  }

  /* ② D 的原始目录约定 */
  const guess = path.join(path.dirname(unifiedFile), "..", "reports", key, "memo.json");
  try {
    if (fs.existsSync(guess)) return JSON.parse(fs.readFileSync(guess, "utf8"));
  } catch (e) { /* 读不动就当没交 */ }
  return undefined;
}

/* ------------------------------------------------------------------ */
/* 输出小工具                                                          */
/* ------------------------------------------------------------------ */
const out = [];
const say = (s) => out.push(s);
const pad = (s, n) => {
  s = String(s);
  /* 中文按 2 个字符宽算，否则表格对不齐 */
  let w = 0;
  for (const ch of s) w += /[　-鿿＀-￯]/.test(ch) ? 2 : 1;
  return s + " ".repeat(Math.max(0, n - w));
};

/* ------------------------------------------------------------------ */
/* 契约自查：js/ 里真实出现的取值路径，契约是否都登记了               */
/* ------------------------------------------------------------------ */
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function scanLiterals() {
  const files = ["js/dataLoader.js", "app.js"].concat(
    fs.existsSync(path.join(ROOT, "js/pages"))
      ? fs.readdirSync(path.join(ROOT, "js/pages")).filter((f) => f.endsWith(".js")).map((f) => "js/pages/" + f)
      : []
  );

  const found = new Map();          // 字面量 → 出现的文件
  const RE = /\.(?:get|value|item)\(\s*["']([^"']+)["']/g;

  files.forEach((rel) => {
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p)) return;
    const src = stripComments(fs.readFileSync(p, "utf8"));
    let m;
    while ((m = RE.exec(src))) {
      const lit = m[1];
      if (!found.has(lit)) found.set(lit, new Set());
      found.get(lit).add(rel);
    }
  });
  return found;
}

/** 契约里有没有一条路径「覆盖」这个字面量。
 *  `ratios.` 这种以点结尾的是前缀拼接（get("ratios." + g)），按前缀算。 */
function covered(lit, paths) {
  return paths.some((p) => p === lit || p.startsWith(lit) || p.startsWith(lit + "."));
}

/* ------------------------------------------------------------------ */
/* 体检一份数据                                                        */
/* ------------------------------------------------------------------ */
function report(label, data, memo) {
  const results = C.check(data, memo);
  const pages = C.summarize(results);

  const coreGaps = results.filter((r) => C.isGap(r) && r.spec.lv === "core");
  const opens    = results.filter((r) => C.isGap(r) && r.spec.lv === "open");
  const optMiss  = results.filter((r) => C.isGap(r) && r.spec.lv === "opt");
  const bad      = results.filter((r) => r.status === "type" || r.status === "range");

  say("");
  say("══════════════════════════════════════════════════════════════════");
  say("  接口体检 · " + label);
  say("══════════════════════════════════════════════════════════════════");
  say("");

  /* ---- 一句话结论 ---- */
  if (!data || typeof data !== "object") {
    say("  ✕ 这不是一个对象，E 完全用不了。");
    return { exit: 1, coreGaps };
  }
  const renderable = pages.filter((p) => p.core === 0).length;
  say("  " + pages.length + " 个页面/块里，" + renderable + " 个可以完整渲染。");
  if (coreGaps.length) say("  ⚠️ 有 " + coreGaps.length + " 条必需路径读不到（下面按页列出）。");
  else say("  ✅ 必需路径全部有值。");
  if (opens.length) say("  ◻ 另有 " + opens.length + " 条是**已知待交付**，不算这份数据的错。");
  if (bad.length) say("  ✕ 有 " + bad.length + " 条类型/范围不对 —— 这类必须是 0，会渲染出脏数据。");
  say("");

  /* ---- 逐页 ---- */
  say("  ┌──────────┬────────┬────────┬────────┬──────────────────────┐");
  say("  │ 页面     │ 必需缺 │ 待交付 │ 可选缺 │ 判定                 │");
  say("  ├──────────┼────────┼────────┼────────┼──────────────────────┤");

  pages.forEach((p) => {
    let verdict;
    if (p.problems.length)   verdict = "✕ 类型/范围异常";
    else if (p.core)         verdict = "⚠️ 退化成空状态";
    else if (p.open)         verdict = "◻ 待交付（页面留位）";
    else if (p.gated && !p.ok) verdict = "◻ 整块未提供";
    else                     verdict = "✅ 完整";

    say("  │ " + pad(p.title, 8) + " │ " + pad(p.core, 6) + " │ " + pad(p.open, 6) +
        " │ " + pad(p.opt, 6) + " │ " + pad(verdict, 20) + " │");
  });
  say("  └──────────┴────────┴────────┴────────┴──────────────────────┘");
  say("");

  /* ---- 必需缺口明细 ---- */
  if (coreGaps.length) {
    say("  ── 必需缺口（这些不解决，对应页面就是空的）──");
    groupByPage(coreGaps).forEach(([pg, list]) => {
      say("    · " + pg + "（" + list.length + " 项，找 " + ownerList(list) + "）");
      list.slice(0, 6).forEach((r) => say("        " + r.spec.p + "   " + why(r)));
      if (list.length > 6) say("        …… 其余 " + (list.length - 6) + " 项");
    });
    say("");
  }

  /* ---- 类型 / 范围异常（这类最贵，会渲染出脏数据）---- */
  if (bad.length) {
    say("  ── 类型 / 范围异常（脏数据来源，必须清零）──");
    bad.forEach((r) => say("    ✕ " + pad(r.spec.p, 42) + " " + short(r.sample) +
                           "   期望 " + expect(r)));
    say("");
  }

  /* ---- 按谁欠着切一刀 = 给队友的需求文档 ---- */
  const owners = C.byOwner(results);
  const ownerKeys = Object.keys(owners).sort();
  if (ownerKeys.length) {
    say("  ── 按人汇总（这一节可以直接发给对应队友）──");
    ownerKeys.forEach((w) => {
      const o = owners[w];
      const bits = [];
      if (o.core.length) bits.push("必需 " + o.core.length + " 项");
      if (o.open.length) bits.push("待交付 " + o.open.length + " 项");
      if (o.opt.length)  bits.push("可选 " + o.opt.length + " 项");
      if (o.problems.length) bits.push("⚠️ 异常 " + o.problems.length + " 项");
      say("    " + pad(w, 4) + "  " + bits.join(" / "));
      o.core.slice(0, 4).forEach((r) => say("          [必需] " + r.spec.p + "  ← " + r.spec.label));
      if (o.core.length > 4) say("          …… 必需项其余 " + (o.core.length - 4) + " 项");
      o.open.slice(0, 3).forEach((r) => say("          [待交付] " + r.spec.p + "  ← " + r.spec.label));
      if (o.open.length > 3) say("          …… 待交付其余 " + (o.open.length - 3) + " 项");
    });
    say("");
  }

  return { exit: coreGaps.length || bad.length ? 1 : 0, coreGaps, opens, optMiss, bad, pages };
}

function groupByPage(list) {
  const m = new Map();
  list.forEach((r) => {
    if (!m.has(r.pageTitle)) m.set(r.pageTitle, []);
    m.get(r.pageTitle).push(r);
  });
  return [...m.entries()];
}

function ownerList(list) {
  return [...new Set(list.map((r) => r.spec.who))].join("、");
}

/** 把值截成一行 —— 不截的话一条类型异常能把整个终端刷满 */
function short(v, n = 56) {
  let s;
  try { s = JSON.stringify(v); } catch (e) { s = String(v); }
  if (s === undefined) s = String(v);
  return s.length > n ? s.slice(0, n) + "…（共 " + s.length + " 字符）" : s;
}

function expect(r) {
  return r.spec.t || r.want || (r.spec.range ? "范围 " + JSON.stringify(r.spec.range) : "");
}

function why(r) {
  if (r.status === "miss") return "路径不存在";
  if (r.status === "null") return "值是 null（= 未提取）";
  if (r.status === "type") return "类型不对：" + short(r.sample) + "，期望 " + expect(r);
  if (r.status === "range") return "超出范围：" + short(r.sample) + "，期望 " + expect(r);
  /* na 是**答复**不是缺口，所以正常不会走到这里（isGap 已经把它排除了）。
     留着是为了万一它出现在别的清单里，别显示成一个光秃秃的 "na"。 */
  if (r.status === "na") return "不适用（" + (r.naAt || "?") + " 标了 not_applicable）";
  return r.status;
}

/* ================================================================== */
/* 主流程                                                              */
/* ================================================================== */

const target = process.argv[2];
let files = [];

if (!target) {
  files = ["data/mock_data.js"];
} else {
  const t = path.isAbsolute(target) ? target : path.join(process.cwd(), target);
  if (!fs.existsSync(t)) {
    console.error("找不到 " + t);
    process.exit(1);
  }
  if (fs.statSync(t).isDirectory()) {
    files = fs.readdirSync(t)
      /* run_log / chain_log / render_log 是运行日志，不是数据样本。
         扫进来会把「日志里没有 company 段」报成缺口 —— 纯噪音。 */
      .filter((f) => /\.(json|js)$/i.test(f) && !/_log\.(json|js)$/i.test(f))
      .map((f) => path.join(t, f));
    if (!files.length) { console.error(t + " 里没有 .json / .js"); process.exit(1); }
  } else {
    files = [t];
  }
}

say("");
say("FinScope 接口体检 —— E 的消费端契约走查");
say("契约定义：js/contract.js（" + C.allPaths().length + " 条路径）");

/* ---- 契约自查：先确认 E 自己的清单没漏 ---- */
(function selfAudit() {
  const literals = scanLiterals();
  const paths = C.allPaths();
  const uncovered = [...literals.keys()].filter((lit) => !covered(lit, paths));

  say("");
  say("── 契约自查 ──");
  say("  js/ 里实际出现的取值路径：" + literals.size + " 个");
  if (!uncovered.length) {
    say("  ✅ 全部被 js/contract.js 登记 —— 「E 会读什么」这份清单是准的");
  } else {
    say("  ⚠️ 以下路径代码在读、契约没登记（先补契约，否则体检会漏报）：");
    uncovered.forEach((lit) => say("      " + lit + "   ← " + [...literals.get(lit)].join(", ")));
  }
})();

/* ---- 逐个文件体检 ---- */
let worst = 0;
const all = [];
files.sort().forEach((f) => {
  const rel = path.relative(process.cwd(), f) || f;
  let data;
  try {
    data = loadData(f);
  } catch (e) {
    say("");
    say("  ✕ " + rel + " 载入失败：" + e.message);
    worst = 1;
    return;
  }
  const memo = loadMemo(f);
  const r = report(rel, data, memo);
  worst = Math.max(worst, r.exit);
  all.push({ label: rel, r });
});

/* ---- 多份数据时出一张横向对比表 ------------------------------------ */
/* 一家公司的缺口可能是「这家就是这样」（比如茅台没有商誉）；
   九家一起缺口完全相同，才是「接口没对上」。
   这一节就是用来分开这两件事的。 */
if (all.length > 1) {
  say("");
  say("══════════════════════════════════════════════════════════════════");
  say("  跨样本对比 · " + all.length + " 份数据");
  say("══════════════════════════════════════════════════════════════════");
  say("");
  say("  " + pad("样本", 22) + pad("必需缺", 8) + pad("待交付", 8) + pad("异常", 6) + "判定");
  say("  " + "─".repeat(64));
  all.forEach(({ label, r }) => {
    const v = r.bad.length ? "✕ 脏数据" : (r.coreGaps.length ? "⚠️ 缺口 " + r.coreGaps.length : "✅ 干净");
    say("  " + pad(label.replace(/^.*[\\/]/, "").replace(/\.(json|js)$/i, ""), 22) +
        pad(r.coreGaps.length, 8) + pad(r.opens.length, 8) + pad(r.bad.length, 6) + v);
  });
  say("");

  /* 每条路径在几份数据里缺失 —— 出现次数高 = 接口问题，不是数据问题 */
  const missCount = new Map();
  all.forEach(({ r }) => {
    r.coreGaps.forEach((g) => {
      const k = (g.spec.root || "") + "|" + g.spec.p;
      missCount.set(k, (missCount.get(k) || 0) + 1);
    });
  });
  const rows = [...missCount.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (rows.length) {
    say("  ── 必需缺口出现在几份数据里（" + all.length + " 份中）──");
    say("     9/9 = **接口没对上**，改一处全解决；1/9 = 这家公司确实没有，属正常。");
    say("     标 [memo] 的来自投研简报绑定表，其余来自统一对象。");
    say("");
    const spec = {};
    C.check({}, {}).forEach((r) => { spec[(r.spec.root || "") + "|" + r.spec.p] = r.spec; });
    rows.forEach(([k, n]) => {
      const s = spec[k] || {};
      const flag = n === all.length ? "★ 普遍" : "· 个别";
      const shown = k.replace(/^memo\|/, "[memo] ");
      say("     " + flag + "  " + pad(n + "/" + all.length, 8) + pad(shown, 52) + " " + (s.label || ""));
    });
    say("");
  }
}

say("");
console.log(out.join("\n"));
process.exit(worst);
