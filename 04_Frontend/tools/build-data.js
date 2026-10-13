/* ============================================================================
 * build-data.js —— 把 D 的交付物转成浏览器能直接读的 .js（**只写 data/，不碰 D 的文件**）
 * ----------------------------------------------------------------------------
 * 为什么需要这一步：
 *   最终交付要能双击 index.html 打开（file:// 协议）。这个协议下浏览器会因
 *   CORS 拦掉 fetch 本地 .json —— 所以 D 的 .json 必须包成
 *   `window.FINSCOPE_DATA = {...};` 这种形式才能被页面读到。
 *
 *   这不是「E 加工 D 的数据」，是**换一种容器**：里面的对象原样搬过去，
 *   一个字段不改、一个数不算。D 重新交付时重跑一次即可。
 *
 * 产物（两份，对应 D 的两份独立产物）：
 *   data/real_data.js   ← out_data/unified/<key>.json     统一数据对象
 *   data/real_memo.js   ← out_data/reports/<key>/memo.json 投研简报绑定表
 *
 * 用法：
 *   node tools/build-data.js                          # 默认 600519.SH_2025
 *   node tools/build-data.js 000333.SZ_2025           # 指定公司
 *   node tools/build-data.js 600519.SH_2025 --out-dir data
 *
 * 退出码：0 = 两份都写成；1 = 缺文件或读不动
 * ==========================================================================*/

"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");

/* D 的交付根目录。相对 04_Frontend 定位 —— 两个目录是并列的兄弟目录。
   哪天 D 挪了地方，只改这一行。 */
const D_ROOT = path.join(ROOT, "..", "D", "D分支文件", "out_data");

/* 默认演示公司。选它是因为它的数据最全（有价、有区间、有敏感性矩阵、
   有跨期对照）；000333.SZ_2025 的估值段几乎全空，适合专门用来验降级，
   不适合当演示主数据。 */
const DEFAULT_KEY = "600519.SH_2025";

function parseArgs(argv) {
  const out = { key: DEFAULT_KEY, outDir: path.join(ROOT, "data") };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--out-dir") { out.outDir = path.resolve(argv[++i]); }
    else rest.push(argv[i]);
  }
  if (rest.length) out.key = rest[0];
  return out;
}

function readJson(file, label) {
  if (!fs.existsSync(file)) {
    console.error("✗ 找不到" + label + "：" + file);
    process.exit(1);
  }
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    console.error("✗ " + label + " 不是合法 JSON：" + file + "\n  " + e.message);
    process.exit(1);
  }
}

/* 生成一个数据文件。header 是给人看的说明，data 原样 JSON 化。
   不缩进：这两个对象是机器产物，缩进只会让文件大两三倍，
   而没人会去逐行读它 —— 要读就读 D 的原始 .json。 */
function wrap(header, varName, data) {
  return "/* " + "=".repeat(72) + "\n"
       + " * （本文件由 tools/build-data.js 自动生成，请勿手改）\n"
       + " * " + header.split("\n").join("\n * ") + "\n"
       + " * " + "=".repeat(72) + " */\n\n"
       + "window." + varName + " = " + JSON.stringify(data) + ";\n";
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const key = args.key;

  const unifiedFile = path.join(D_ROOT, "unified", key + ".json");
  const memoFile = path.join(D_ROOT, "reports", key, "memo.json");

  const unified = readJson(unifiedFile, "统一数据对象");
  const memo = readJson(memoFile, "投研简报绑定表");

  if (!fs.existsSync(args.outDir)) fs.mkdirSync(args.outDir, { recursive: true });

  const unifiedOut = path.join(args.outDir, "real_data.js");
  const memoOut = path.join(args.outDir, "real_memo.js");

  fs.writeFileSync(
    unifiedOut,
    wrap(
      "来源：D/D分支文件/out_data/unified/" + key + ".json\n"
      + "内容：D 的统一数据对象（company / financials / ratios / risks /\n"
      + "      rules_evaluated / valuation / sources）。字段与数值原样搬运，\n"
      + "      E 未做任何计算或改名。\n"
      + "被谁用：js/dataLoader.js 的 load() → 页面 1/2/3/4/5\n"
      + "体检：node tools/interface-check.js data/real_data.js",
      "FINSCOPE_DATA",
      unified
    ),
    "utf8"
  );

  fs.writeFileSync(
    memoOut,
    wrap(
      "来源：D/D分支文件/out_data/reports/" + key + "/memo.json\n"
      + "内容：D 的投研简报**绑定表**（meta / columns / scalars / collections /\n"
      + "      numbers / compliance / validation）。注意它不是报告正文 ——\n"
      + "      正文在 memo.md / memo.html 里，这里只有「占位符 → 已格式化好的\n"
      + "      字符串」的绑定关系，页面 6 直接取 formatted 显示。\n"
      + "被谁用：js/pages/p6-memo.js（走 FinScope.data 的 memo* 系列取值器）\n"
      + "独立性：这份与 real_data.js 是两份独立产物，任一缺席另一份照常能用。",
      "FINSCOPE_MEMO",
      memo
    ),
    "utf8"
  );

  const kb = n => Math.round(fs.statSync(n).size / 1024) + " KB";
  console.log("✓ " + key);
  console.log("  " + path.relative(ROOT, unifiedOut).replace(/\\/g, "/") + "  " + kb(unifiedOut)
            + "  （统一数据对象）");
  console.log("  " + path.relative(ROOT, memoOut).replace(/\\/g, "/") + "  " + kb(memoOut)
            + "  （投研简报绑定表）");
  console.log("");
  console.log("  下一步：把 index.html 的数据源两行指到这两个文件，然后");
  console.log("    node tools/interface-check.js data/real_data.js");
  console.log("    node tests/run.js");
}

main();
