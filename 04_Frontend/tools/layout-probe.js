/* ============================================================================
 * layout-probe.js —— 真机版式体检（headless Chrome）
 * ----------------------------------------------------------------------------
 * 为什么要有这个文件：`layout-audit.js` 读的是**源码文本**，它能告诉我
 * 「这个令牌被引用了 24 次」，但说不了「这两块在 1150px 下压在一起了」。
 * 版式缺陷只有真浏览器 + 真宽度才量得到。
 *
 * 这个工具之前不存在，代价是同一件事被一次性脚本重做了七八遍，而且
 * **同两条死路走了两遍**（见下面「三条判据的来历」）。脚本在 %TEMP% 里，
 * 下次开新会话就没了，于是又从零推一遍。现在固化在这里。
 *
 * 用法：
 *   node tools/layout-probe.js                          # 六页 × 11 档宽度
 *   node tools/layout-probe.js --page p1                # 只看页面 1
 *   node tools/layout-probe.js --page p1 --chip 1 --qa  # 点开公司 + 问一道题再量
 *   node tools/layout-probe.js --widths 1366x768,1150x800
 *   node tools/layout-probe.js --final                  # 量 05_Output/Final.html
 *   node tools/layout-probe.js --page p1 --chip 1 --minw  # 扫 .board-table 的 min-width 下限
 *   node tools/layout-probe.js --json                   # 吐原始 JSON（调试用）
 *
 * 退出码：0 = 所有页所有宽度都干净；1 = 有真发现（重叠/异常字体/探出）
 *
 * ----------------------------------------------------------------------------
 * 三条判据的来历（**每一条都踩过坑，不要凭直觉改**）
 * ----------------------------------------------------------------------------
 * ① 重叠：两个盒子相交面积 ÷ 较小盒面积 ≥ 0.12 才算，轻微压边不算。
 *    排除 <colgroup>/<col>/<thead>/<tbody>/<tr> —— 表格内部盒子和单元格
 *    永远「重叠」，那是 DOM 结构不是缺陷。
 *    排除「跨行行内元素」（display:inline 且高 > 2em）—— getBoundingClientRect
 *    对换行行内元素返回的是**各行的并集**，它天然包含紧挨的前一个行内兄弟，
 *    报过一次 96×17 / 100% 的假阳性。
 *
 * ② ★ `.vr-grid` 豁免：页面 5 有一层 position:absolute 的背景网格，
 *    它**稳定报出 19 条重叠**，而且每一条都是「它压在自己那一行下面」——
 *    这正是它该有的 z 序（背景在内容之下）。这不是缺陷，是滤镜没设对。
 *    ★ 这条假阳性坑了**两次**。第一次我以为真是页面 5 的布局坏了，
 *    逐条查证了一轮；第二次换个脚本又报一遍。所以它现在写死在这里。
 *
 * ③ ★ 溢出要用「墨迹宽度」量，不能用盒子：
 *    看板表 / 财务表的数值列是 `white-space: nowrap` + `table-layout: fixed`，
 *    装不下时**不换行**，而是溢到格子外面去压右边一列 —— 那正是用户报的
 *    「两个面板重合」。这个症状量了两次都量不到，因为两个判据都是假的：
 *      ✗ 「格高 > 1.6 倍行高」→ 每个宽度都报 wrapped（格高 40 里本含 padding）
 *      ✗ `td.scrollWidth > td.clientWidth` → **永远相等**。fixed 布局下
 *        td 的盒子是定宽的，nowrap 内容溢出到盒子**外面**，
 *        不会把 td 自己的 scrollWidth 撑大。
 *    真判据只有一个：`Range.selectNodeContents()` 量文字的墨迹宽，
 *    跟格子的**内容宽**（去掉 padding/border）比。
 *    这一条实现在 `probe-harness.html` 的 `out.boardGeom.ink` 里。
 *
 * ----------------------------------------------------------------------------
 * 为什么 harness 是单独一个文件（tools/probe-harness.html）
 * ----------------------------------------------------------------------------
 * 那段探针有 370 行，里面有大量正则（`/\s+/`、`/^[\s\d.,\-+%()/·]*$/`）。
 * 把它塞进本文件的模板字符串里，`\s` 会被 JS 当成未知转义**吃掉反斜杠**，
 * 静默变成 `/s+/` —— 这种错不会报错，只会让判据悄悄失灵。
 * 所以它待在 .html 里原样保留，本文件只负责「拷进项目根 → 跑 → 删掉」。
 *
 * ★ harness 必须拷到**项目根**再跑：它里面写的是 `css/base.css` 这类
 *   相对路径，放 tools/ 下会全部 404，量出来的是一张没样式的裸页面。
 * ==========================================================================*/

"use strict";

const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const OUT_DIR = path.join(ROOT, "..", "05_Output");
const HARNESS = path.join(__dirname, "probe-harness.html");

/* harness 拷到项目根时的临时名 —— 用完必删（见 finally）。
   点开头是故意的：它一眼就能看出是临时产物，不会被人当交付物拷走。
   ★ 带 pid：两个探针同时跑（比如一边扫全量一边量 min-width）会共用同一个
     文件名，后起的那个把前一个的临时页覆盖/删掉，前一个就报「探针没出 JSON」——
     看着像脚本抛错，其实是两个人抢一个文件。带 pid 就没有这回事。 */
const TMP_NAME = "_probe.tmp." + process.pid + ".html";

const PAGES = ["p1", "p2", "p3", "p4", "p5", "p6"];
const DEFAULT_WIDTHS = [
  "1920x900", "1600x900", "1366x768", "1280x800", "1200x800",
  "1150x800", "1100x800", "1050x800", "1000x800", "950x800", "900x800"
];

/* ---------------------------------------------------------------- 参数 */

const argv = process.argv.slice(2);
function flag(name) { return argv.indexOf("--" + name) >= 0; }
function opt(name, dflt) {
  const i = argv.indexOf("--" + name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
}

const wantJson = flag("json");
const useFinal = flag("final");
const doQa = flag("qa");
const showMinw = flag("minw");
const chip = opt("chip", null);
const onlyPage = opt("page", null);
const widths = opt("widths", DEFAULT_WIDTHS.join(",")).split(",").filter(Boolean);
const pages = onlyPage && onlyPage !== "all" ? [onlyPage] : PAGES;

/* ★ 必须比 harness 里 run() 的延时大。harness 是「要问答等 9000ms、
   不要问答 400ms」，所以这里是 20000 / 8000。
   这个坑踩过两次：探针报「没有 JSON」不是脚本坏了，是 runner 的虚拟时钟
   先到点把页面掐了，run() 根本没轮到跑。改 harness 的延时请一起改这里。 */
const VTB = doQa ? "20000" : "8000";

/* ---------------------------------------------------------------- Chrome */

function findChrome() {
  const cands = [
    process.env.CHROME,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  ].filter(Boolean);
  for (const c of cands) { try { if (fs.existsSync(c)) return c; } catch (e) {} }
  console.error("找不到 Chrome。用 CHROME=<路径> node tools/layout-probe.js 指定。");
  process.exit(2);
}
const CHROME = findChrome();

/* ------------------------------------------------- 造临时页（含 --final） */

let tmpPath = null;

function makeTmpPage() {
  const harness = fs.readFileSync(HARNESS, "utf8");

  if (!useFinal) {
    tmpPath = path.join(ROOT, TMP_NAME);
    fs.writeFileSync(tmpPath, harness, "utf8");
    return;
  }

  /* --final：把 harness 的 <script> 插进真正的交付物 Final.html 的副本，
     这样量的是**打包后的文件**，不是源码版。
     两版之间有真实的差异（内联顺序、DEMO 开关），交付前值得单独量一次。 */
  const finalPath = path.join(OUT_DIR, "Final.html");
  if (!fs.existsSync(finalPath)) {
    console.error("没有 " + finalPath + "，先跑 node tools/build-final.js");
    process.exit(2);
  }
  const blocks = [...harness.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  const code = blocks.length ? blocks[blocks.length - 1][1] : "";
  if (code.indexOf("PROBE_JSON_START") < 0) {
    console.error("harness 最后一段 <script> 不是探针脚本 —— 结构变了？");
    process.exit(2);
  }
  let html = fs.readFileSync(finalPath, "utf8");
  html = html.replace("</body>",
    "<pre id=\"PROBE\" style=\"display:none\"></pre>\n<script>" +
    code.replace(/<\/script/gi, "<\\/script") + "</script>\n</body>");
  tmpPath = path.join(OUT_DIR, TMP_NAME);
  fs.writeFileSync(tmpPath, html, "utf8");
}

/* ------------------------------------------------------------------ 跑一次 */

function runOne(w, h, page) {
  const url = "file:///" + tmpPath.split(path.sep).join("/") +
    "?target=" + page + (chip != null ? "&chip=" + chip : "") + (doQa ? "&qa=1" : "");
  let dom;
  try {
    dom = execFileSync(CHROME, [
      "--headless=new", "--disable-gpu", "--no-sandbox",
      "--user-data-dir=" + path.join(os.tmpdir(), "fglp-" + page + "-" + w),
      "--window-size=" + w + "," + h, "--force-device-scale-factor=1",
      "--virtual-time-budget=" + VTB, "--run-all-compositor-stages-before-draw",
      "--dump-dom", url
    ], { encoding: "utf8", maxBuffer: 1 << 28, stdio: ["ignore", "pipe", "ignore"] });
  } catch (e) {
    return { err: "Chrome 跑不动：" + String(e.message).slice(0, 120) };
  }
  /* ★ 正则必须带 `\{`。`PROBE_JSON_START` 那串字面量**就在 harness 自己的
     源码里**，不带 `{` 会匹到脚本源码本身，然后 JSON.parse 一段 JS ——
     报出来的是「读不到 .viewport」，看着像探针没跑，其实是匹错了地方。
     （`js/finboxes.js` 踩的是同一个坑。） */
  const m = dom.match(/PROBE_JSON_START(\{[\s\S]*?\})PROBE_JSON_END/);
  if (!m) return { err: "探针没出 JSON（脚本抛错了？或者虚拟时钟跑完时它还没到点）" };
  try { return JSON.parse(m[1]); } catch (e) { return { err: "JSON 解析失败 " + e.message }; }
}

/* ------------------------------------------------------------------ 判读 */

/* ★ `.vr-grid` 在**两端**都可能出现（它压自己的行，也可能是别人压它），
   所以两边都要查。 */
function realOverlaps(o) {
  return (o.overlaps || []).filter(function (x) {
    return !/vr-grid/.test(x.a) && !/vr-grid/.test(x.b);
  });
}

function report(page, size, o) {
  if (o.err) { console.log("  " + size.padEnd(11) + " ✗ " + o.err); return 1; }
  const ov = realOverlaps(o);
  const odd = o.oddFontsCount || 0;
  const hov = o.hOverflowCount || 0;
  const jump = (o.docScrollWidth || 0) > (o.viewport.w || 0) + 1;
  const bad = ov.length || odd || hov || jump;

  const g = o.boardGeom;
  const inkOver = g && g.ink ? g.ink.overflow : 0;
  const headOver = g && g.headOverflow ? g.headOverflow.overflow : 0;
  const boardBad = inkOver || headOver;

  console.log("  " + size.padEnd(11) +
    (bad || boardBad ? "✗" : "✓") +
    "  重叠 " + ov.length + "（已豁免 .vr-grid " + (o.overlapsCount - ov.length) + "）" +
    "  异常字体 " + odd +
    "  探出 " + hov +
    (jump ? "  ★横向滚动 docSW=" + o.docScrollWidth : "") +
    (g ? "  看板 墨迹溢出 " + inkOver + " / 列头 " + headOver : "") +
    "  字族 " + Object.keys(o.fontFamilies || {}).length);

  /* --minw：把 min-width 下限扫描结果打出来（定 .board-table 那个 680 用的）。
     ★ 只有**表宽被 min-width 顶住**时这次扫描才有意义 —— 视口宽的时候
       表由滚动容器撑开，改 min-width 根本不生效，扫出来是一条平线。
       所以扫出来的数只有在窄视口（≤950）下才作数，报告里明说。 */
  if (showMinw && o.boardMinwScan) {
    o.boardMinwScan.scan.forEach(function (x) {
      /* over = need − have。正数才是挤；0.5px 以内算噪声（子像素舍入）。
         之前这里写成 `x.over > 1 ? "溢出" : "余 " + (-x.over)` —— 0.7px 的
         **正**溢出被印成「余 -0.7px」，于是 440px 那档被误判成合格下限。 */
      var tight = x.over > 0.5;
      console.log("          min-width " + String(x.minw).padStart(4) + "px  " +
        ("表宽 " + String(x.tableW).padStart(4) + "  ").slice(0, 12) +
        (tight ? "★溢出 " + x.over.toFixed(1) + "px" : "余 " + (-x.over).toFixed(1) + "px") +
        "  列" + x.col + " \"" + x.txt + "\" 需 " + x.need + " 有 " + x.have);
    });
    if (!o.boardMinwScan.binding) {
      console.log("        → 这一档视口太宽，min-width 根本没生效（表宽始终 " +
        o.boardMinwScan.tableWAtMin + "px）——扫出来的数不作数，换窄视口重跑");
    } else {
      console.log("        → 下限 " + (o.boardMinwScan.floor != null
        ? o.boardMinwScan.floor + "px（最挤的一列刚好不溢出）" : "没扫到，需要把扫描范围往上加"));
    }
  }

  ov.slice(0, 3).forEach(function (x) {
    console.log("       ★ " + x.shareOfSmaller + " " + x.overlapPx +
      "\n          A: " + x.a + "\n          B: " + x.b);
  });
  (o.oddFonts || []).slice(0, 3).forEach(function (x) {
    console.log("       ★字体 " + (x.why || "") + " " + x.cls);
  });
  (o.hOverflow || []).slice(0, 3).forEach(function (x) {
    console.log("       ★探出 " + x.cls + " right=" + x.right + " vw=" + x.vw);
  });
  if (boardBad && g) {
    if (g.ink && g.ink.worst) {
      const r = g.ink.worst;
      console.log("       ★墨迹 列" + r.col + " \"" + r.txt + "\" 需要 " + r.need +
        " > 可用 " + r.have + "（差 " + r.over + "px）");
    }
    (g.headOverflow && g.headOverflow.worst ? [g.headOverflow.worst] : []).forEach(function (r) {
      if (r.need > r.have + 1) {
        console.log("       ★列头 \"" + r.txt + "\" 需要 " + r.need + " > 可用 " + r.have);
      }
    });
  }
  return (bad || boardBad) ? 1 : 0;
}

/* ------------------------------------------------------------------ main */

makeTmpPage();
let findings = 0;
const raws = {};

try {
  console.log("版式体检：" + (useFinal ? "05_Output/Final.html（交付物）" : "04_Frontend（源码版）"));
  console.log("  harness " + path.relative(ROOT, HARNESS) +
    " → " + path.relative(ROOT, tmpPath) + "（用完即删）");
  if (doQa) console.log("  已开问答：先点第一道预设题，等分片注入后再量");
  if (chip != null) console.log("  已选公司 chip #" + chip);
  console.log("");

  for (const p of pages) {
    console.log("── " + p);
    for (const s of widths) {
      const [w, h] = s.split("x");
      const o = runOne(w, h, p);
      if (wantJson) raws[p + "@" + s] = o;
      findings += report(p, s, o);
    }
  }
} finally {
  /* ★ 无论成功、报错、还是 Ctrl-C，临时页必须走。
     它是拷贝进项目根的，留下来就是又一个「差点被当交付物」的文件。 */
  try { if (tmpPath && fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath); } catch (e) {}
}

if (wantJson) {
  console.log("\n" + JSON.stringify(raws));
} else {
  console.log("\n" + (findings
    ? "★ " + findings + " 处需要人工判断（上面带 ✗ / ★ 的行）"
    : "全部干净：0 重叠、0 异常字体、0 探出、0 看板墨迹溢出"));
}

process.exit(findings ? 1 : 0);
