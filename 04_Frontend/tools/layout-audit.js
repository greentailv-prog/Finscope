/* ============================================================================
 * layout-audit.js —— 版式横向审计（**只读，不改任何文件**）
 * ----------------------------------------------------------------------------
 * 为什么需要它：
 *   页面 2/3/4/5 的正式版式是分四次单独定案的，每次都在动 css/。
 *   四次「单独看都对」的决定加起来不一定是「一致」—— 每页各自多挑了一个
 *   字号、各自定了一个卡片内距，单页看不出问题，六页摆在一起才会觉得
 *   「哪里别扭」但又指不出来。肉眼很难定位这种漂移，所以让脚本把六页
 *   横着摆成一张表。
 *
 * 它查四件事：
 *   ① 字号层级矩阵 —— 每页用了令牌阶梯里的哪几级。
 *      层级过多 = 吵（「一堆没有分辨度的数据」就是这么来的）；
 *      过少 = 分不出主次。这是「太刻板」的量化指标。
 *   ② 颜色使用矩阵 —— 每页用了 status / tone / 中性 里的哪几色、各几次。
 *      一眼看出哪页越界用了 tone，哪页该有落点的地方却是空的。
 *   ③ 圆角 / 阴影对比 —— 同一类零件（卡片）各页是不是各写了一套。
 *   ④ 裸值清单 —— 没走令牌的字号 / 圆角 / 间距。约定是零，列出来确认。
 *
 * 用法：node tools/layout-audit.js
 *      node tools/layout-audit.js <04_Frontend 目录>     # 显式指定
 * ==========================================================================*/

"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = process.argv[2] || path.join(__dirname, "..");

/* ------------------------------------------------------------------ */
/* 读文件                                                              */
/* ------------------------------------------------------------------ */
function read(rel) {
  const p = path.join(ROOT, rel);
  if (!fs.existsSync(p)) {
    console.error("找不到 " + p + " —— 请在 04_Frontend 目录下运行，或把目录当参数传进来");
    process.exit(1);
  }
  return fs.readFileSync(p, "utf8");
}

const baseCss = read("css/base.css");
const compCss = read("css/components.css");

/* 注释必须**先剥掉再分析**。本项目的注释里写满了设计理由，
   里面出现的 font-size / 色值之类会被正则当成真代码 ——
   这个坑在写 CSS 内容守卫时就踩过一次。 */
const strip = s => s.replace(/\/\*[\s\S]*?\*\//g, "");

/* ------------------------------------------------------------------ */
/* 令牌表：从 base.css 的 :root 抽出来，用来判断「这个值是不是走了令牌」 */
/* ------------------------------------------------------------------ */
const rootBlock = strip(baseCss.match(/:root\s*\{([\s\S]*?)\}/)[1]);
const TOKENS = {};
for (const m of rootBlock.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) {
  TOKENS["--" + m[1]] = m[2].replace(/\s+/g, " ").trim();
}

/* ------------------------------------------------------------------ */
/* 把 components.css 按段落切开，再归到页面                             */
/* ------------------------------------------------------------------ */
/* 段落头有两种写法：标题下面直接就是收尾的等号线；或者标题下面还有若干行
   设计理由，再收尾。第一版正则只认前者，后者匹配不上收尾线，于是**吞掉了
   下一段的头** —— 页面 2 因此吃到了页面 3、4 的 CSS，整张表全错。
   写法上只用 [ \t] 不用 \s：\s 会把换行也吃掉，正是漏配的来源。
   收尾的等号线要求自成一行且 ≥10 个，避免半路的注释把匹配截断。 */
const SEC_RE = /\/\*[ \t]*={10,}[ \t]*\r?\n[ \t]*(\d+)\.[ \t]*([^\n]+)[\s\S]*?\n[ \t]*={10,}[ \t]*\*\//g;
const sections = [];
for (const m of compCss.matchAll(SEC_RE)) {
  sections.push({ num: Number(m[1]), title: m[2], head: m.index, body: m.index + m[0].length });
}
sections.forEach((s, i) => {
  s.end = i + 1 < sections.length ? sections[i + 1].head : compCss.length;
  s.css = compCss.slice(s.body, s.end);
});

/* 段落 → 页面。这是全脚本唯一需要人工维护的地方：
   components.css 里新增一个段落，如果它属于某一页，就要在这里登记。
   **没登记的段落按「共享」处理**，不会静默漏掉。 */
const SECTION_PAGE = {
  1: "共享", 2: "共享", 3: "共享", 4: "共享", 5: "共享", 6: "共享", 7: "共享",
  8: "p1", 9: "p2", 10: "p2",
  11: "p3",
  /* §12 图表容器：2026-10-13 随 Chart.js 一起撤空了（只剩墓碑注释，
     剥注释后这一段的 CSS 是**零字节**）。归「共享」不变 ——
     一个空段落归给谁都不影响矩阵，留着这条是为了段落编号不跳号。 */
  12: "共享",
  13: "p4", 14: "p5", 15: "p6",
  16: "共享", 17: "p3",
  /* §18 玻璃降级（2026-10-12 改版新增）。它的选择器列了六个页面的卡片，
     但它本身讲的是**全站降级行为**，所以归「共享」。 */
  18: "共享",
  /* §19 上传窗口 / A 的数据看板 / 年报问答（2026-10-13 新增）。
     ★ 归 p1，不归共享 —— 这一段里每一个选择器（.chip / .board-* /
     .ev-* / .qa-* / .preset / .file-card）都只被 js/pages/p1-upload.js 造出来。
     归「共享」会让 ② 的颜色矩阵把页面 1 的用量记到共享零件头上，
     于是 p1 那一行永远显示「主色 0、中性 0」—— 看着像这页没样式，
     实际全跑到共享列里去了。**归错页比数漏一处更坏，因为它看着是正常的。** */
  19: "p1"
};

const PAGE_ORDER = ["p1", "p2", "p3", "p4", "p5", "p6", "共享"];
const PAGE_LABEL = {
  p1: "页面1 上传年报",
  p2: "页面2 公司概览",
  p3: "页面3 财务诊断",
  p4: "页面4 风险雷达",
  p5: "页面5 估值分析",
  p6: "页面6 投研报告",
  共享: "共享零件"
};

/* 每页所有段落拼成一段 CSS（已剥注释） */
const byPage = {};
PAGE_ORDER.forEach(p => (byPage[p] = ""));
sections.forEach(s => {
  byPage[SECTION_PAGE[s.num] || "共享"] += "\n" + strip(s.css);
});

/* ------------------------------------------------------------------ */
/* 页面用到哪些类 —— ① 必须靠它才能算准                                 */
/* ------------------------------------------------------------------ */
/* 只按「类的定义在哪一段」归页会漏掉共享零件：.metric-value 定义在共享段落里，
   值 --fs-3xl，页面 5 正在用它。第一版没算这一层，于是 ① 说「页面 5 最大 16px」，
   与事实相反。**表读出来不对，先怀疑这里。** */
const allCss = strip(baseCss) + "\n" + strip(compCss) + "\n" + strip(read("css/layout.css"));

/* 所有在 CSS 里有定义的类名 */
const DEFINED = new Set();
for (const m of allCss.matchAll(/\.([a-z][a-z0-9-]*)/g)) DEFINED.add(m[1]);

/* base.css 里的类（.is-good / .num / .dim 之类）是**全局工具类**，
   谁都能用、本来就该共用，不算「跨页复用」。

   但**不能**把 base.css 里出现过的类一律当成工具类：`.metric-value` 也在
   base.css 出现（在 .num 那一串等宽字体清单里），可它是有自己规则的共用零件，
   定义在页面 2 的段落、被页面 4/5 借用 —— 那正是 ⑤ 要找的东西。
   所以判据是「**纯修饰类**」：在 components.css 里它是否从来都跟别的类一起出现。
     · .is-good        → .metric-card.is-good / .status-seg.is-good  → 从来配对 = 工具类
     · .metric-value   → .metric-value { ... }                        → 自己有规则 = 零件 */
const BASE_CLASSES = new Set();
for (const m of strip(baseCss).matchAll(/\.([a-z][a-z0-9-]*)/g)) BASE_CLASSES.add(m[1]);

/* 每个类在 components.css 里出现过的选择器，各含几个类 */
const selWidth = {};
for (const s of sections) {
  for (const m of strip(s.css).matchAll(/([^{}]+)\{/g)) {
    const cls = [...m[1].matchAll(/\.([a-z][a-z0-9-]*)/g)].map(x => x[1]);
    if (!cls.length) continue;
    cls.forEach(c => (selWidth[c] = selWidth[c] || []).push(cls.length));
  }
}

const GLOBAL = new Set();
BASE_CLASSES.forEach(c => {
  const w = selWidth[c];
  if (w && w.every(n => n >= 2)) GLOBAL.add(c);
});

/* 每页 JS 里出现的类名。
   两个坑都踩过：
     · 引号必须用 `[^"]*` 而不是 `[^"]+` —— 源码里只要有一个空串 ""，
       之后的引号配对就整体**错位**，抽出来的全是散文碎片，一个类名都抽不到。
     · 类名有单引号写的，得两种引号都认，否则页面 5 少掉一半的类。 */
const PAGE_FILE = { p1: "upload", p2: "overview", p3: "diagnosis", p4: "risk", p5: "valuation", p6: "memo" };
const usedBy = {};
PAGE_ORDER.slice(0, 6).forEach(page => {
  const src = strip(read("js/pages/" + page + "-" + PAGE_FILE[page] + ".js"));
  const set = new Set();
  for (const m of src.matchAll(/"([^"]*)"|'([^']*)'/g)) {
    const toks = (m[1] !== undefined ? m[1] : m[2]).split(/\s+/).filter(Boolean);
    /* 只认「整串都是已定义类名」的引号串。否则散文里顺嘴提到的词会被算成
       一处复用 —— 页面 5 正文里那句「待 C 补 target 的倍数」就冒充过一次 .target。 */
    if (toks.length && toks.every(t => DEFINED.has(t))) toks.forEach(t => set.add(t));
  }
  usedBy[page] = set;
});

/* 把 CSS 拆成 { 选择器, 声明块 }。components.css 里没有 @media，所以这个
   朴素正则够用；哪天加了 @media，要改成先剥掉才行。 */
function rules(css) {
  const list = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    list.push({ sel: m[1].trim(), body: m[2] });
  }
  return list;
}

/* 每个类被哪些 font-size 值赋过（含共享段落）。
   取「选择器里有一个类被该页用到」就算 —— 略宽松，但六页一视同仁，
   横向比可比性不受影响。 */
const classFs = {};
sections.forEach(s => {
  for (const r of rules(strip(s.css))) {
    const fss = [...r.body.matchAll(/font-size\s*:\s*([^;}]+)/g)].map(x => x[1].trim());
    if (!fss.length) continue;
    for (const c of r.sel.matchAll(/\.([a-z][a-z0-9-]*)/g)) {
      const set = classFs[c[1]] = classFs[c[1]] || new Set();
      fss.forEach(f => set.add(f));
    }
  }
});

/* 页面实际可能出现的 font-size 值 = 专属段落声明的 ∪ 它用到的类带来的 */
function fsValuesOf(page) {
  const vals = new Set();
  [...byPage[page].matchAll(/font-size\s*:\s*([^;}]+)/g)].forEach(m => vals.add(m[1].trim()));
  usedBy[page].forEach(c => {
    if (classFs[c]) classFs[c].forEach(v => vals.add(v));
  });
  return [...vals];
}

/* ------------------------------------------------------------------ */
/* 小工具                                                              */
/* ------------------------------------------------------------------ */
/* 中文按 2 格宽算，否则表格对不齐 —— 表格对不齐就没法横向比 */
const WIDE = /[⺀-꓏豈-﫿︰-﹯＀-｠￠-￦]/;
function textWidth(s) {
  let w = 0;
  for (const ch of String(s)) w += WIDE.test(ch) ? 2 : 1;
  return w;
}
function pad(s, n) {
  s = String(s);
  return s + " ".repeat(Math.max(0, n - textWidth(s)));
}
function padL(s, n) {
  s = String(s);
  return " ".repeat(Math.max(0, n - textWidth(s))) + s;
}

/* 取某个属性出现的全部值（去重） */
function valuesOf(css, prop) {
  const set = new Set();
  const re = new RegExp("(?:^|[;{\\s])" + prop + "\\s*:\\s*([^;}]+)", "g");
  for (const m of css.matchAll(re)) set.add(m[1].trim());
  return [...set];
}

/* 数某个令牌被引用了几次。
   ★ 结尾用 (?![-\w]) 而不是 \b：`--c-primary\b` 会**吃掉** `--c-primary-soft`
   和 `--c-primary-soft-2`（- 是非单词字符，所以那里正好有个 \b），
   于是「主色」那一列一直把两个派生令牌算进自己头上，数字虚高。
   2026-10-12 改版新开了 --c-primary-soft-2 / --c-watch-ink / --c-watch-bg，
   这个虚高一下子变得显眼了，顺手修掉。 */
function countToken(css, tok) {
  return (css.match(new RegExp(tok.replace(/-/g, "\\-") + "(?![-\\w])", "g")) || []).length;
}

const out = [];
const say = s => out.push(s);

/* ================================================================== */
say("FinScope 版式横向审计 · 只读");
say("数据源：css/base.css（令牌） + css/components.css（按段落归页）");
say("");

/* ------------------------------------------------------------------ */
/* ① 字号层级矩阵                                                      */
/* ------------------------------------------------------------------ */
/* --fs-sm(13px) 已于 2026-10-12 从 base.css 删除（拆用法，理由见 base.css）。
   这里同步去掉，否则 ① 矩阵会留一列永远是空的 sm，让人以为漏了什么。 */
const FS_TOKENS = ["--fs-xs", "--fs-md", "--fs-lg", "--fs-xl", "--fs-2xl", "--fs-3xl"];
const FS_SHORT = FS_TOKENS.map(t => t.replace("--fs-", ""));

say("──────────────────────────────────────────────────────────────────");
say("① 字号层级矩阵    ● = 该页 CSS 用到这一级");
say("──────────────────────────────────────────────────────────────────");
say("  " + pad("页面", 18) + FS_SHORT.map(s => padL(s, 5)).join("") + padL("级数", 7) + "  裸值");
say("  " + "-".repeat(62));

PAGE_ORDER.forEach(page => {
  /* 页面 1–6 走 fsValuesOf（含共享零件带来的字号）；
     「共享零件」那一行没有用类可查，退回去数段落声明。 */
  const vals = page === "共享"
    ? valuesOf(byPage[page], "font-size")
    : fsValuesOf(page);
  /* 值长这样：var(--fs-2xl) —— 判的是「含这个令牌」，不是整值相等 */
  const used = FS_TOKENS.map(tok => vals.some(v => v.includes(tok)));
  const bare = vals.filter(v => !v.includes("var(") && v !== "inherit");
  say("  " + pad(PAGE_LABEL[page], 18)
    + used.map(u => padL(u ? "●" : "·", 5)).join("")
    + padL(used.filter(Boolean).length + "/7", 7)
    + "  " + (bare.length ? bare.join("  ") : "—"));
});
say("");
say("  读法：这一行数的是「这页可能出现的字号级数」= 专属段落声明的，");
say("        ∪ 它用到的共享零件带来的（.metric-value 那类）。");
say("        4–6 级属正常（大数 / 标题 / 正文 / 脚注 / 表格小字）；");
say("        7 级全用满通常意味着有地方该合并；3 级以下则分不出主次。");
say("        注意这是**上限**：声明了不等于同屏真的出现。");
say("");

/* --- 阶梯本身：相邻两级差多少 --- */
/* 这一小段比上面的矩阵更值钱。级数够多不代表分得出主次 ——
   相邻两级只差 1px 的话，眼睛读起来是**同一级**，页面就变成
   「一堆一样大的字」。这正是「太刻板、没有分辨度」的来源。 */
say("  ── 阶梯本身：相邻两级差多少 ──");
const FS_SCALE = FS_TOKENS
  .map(tok => ({ tok, px: parseFloat(TOKENS[tok]) }))
  .filter(x => !isNaN(x.px))
  .sort((a, b) => a.px - b.px);
/* 「肉眼能分辨」的线。**1.14，不是 1.15**（2026-10-12 调）：
   原来的 1.15 会把 14→16（1.143，差 2px，中文读得出，且这两级常配不同字重）
   也判成「分不出」，等于给一条无需处理的事项常年挂着警告 ——
   那会训练人忽略这个工具，比不报还糟。
   经验上真正读不出的是 13→12 的 1.083（只差 1px）；1.14 这条线正好把它拦住。 */
const STEP_MIN = 1.14;
say("  " + pad("令牌", 10) + padL("px", 5) + padL("比上一级", 10) + "  判读");
let prev = null;
FS_SCALE.forEach(x => {
  if (prev === null) {
    say("  " + pad(x.tok, 10) + padL(x.px, 5) + padL("—", 10) + "  最小一级");
  } else {
    const ratio = x.px / prev;
    const flat = ratio < STEP_MIN;
    say("  " + pad(x.tok, 10) + padL(x.px, 5) + padL("×" + ratio.toFixed(3), 10)
      + "  " + (flat ? "← 与上一级几乎同高，肉眼分不出" : ""));
  }
  prev = x.px;
});
const flatSteps = FS_SCALE.filter((x, i) =>
  i > 0 && x.px / FS_SCALE[i - 1].px < STEP_MIN
).map(x => x.tok.replace("--fs-", ""));
say("");
if (flatSteps.length) {
  say("  ⚠ " + flatSteps.join(" / ") + " 与各自上一级的比 < " + STEP_MIN + "。"
    + "列在一起时读者读不出差别，");
  say("    等于这几级**实际只是一级**。要么把它们拉开（改数值），");
  say("    要么承认重复、合并掉（改用法）。二者都比维持现状好。");
} else {
  say("  各级间距都在 " + STEP_MIN + " 以上，肉眼能分辨。");
}
say("");

/* ------------------------------------------------------------------ */
/* ② 颜色使用矩阵                                                      */
/* ------------------------------------------------------------------ */
/* 原有一列「强调」(--c-accent)，2026-10-12 随令牌一起删除 ——
   那一列从来都是空的；留着会让人以为「本站应该有个强调色只是还没用上」。
   2026-10-12 改版又把「橙」单独立了一列，但这次不是重蹈覆辙：
   橙是有用户的，而且它的用量**需要被盯着**（见下面的读法）。

   三列对应改版定案的三色分工：主色=灰蓝管结构 / 橙=需关注 / 中性里含 --c-ink 管焦点。
   --c-watch* 从 status 挪到橙列 —— status 列现在只剩绿和红两个「评价」色。 */
const C_GROUPS = [
  { key: "主色", toks: ["--c-primary", "--c-primary-dark", "--c-primary-soft", "--c-primary-soft-2"] },
  { key: "橙", toks: ["--c-watch", "--c-watch-ink", "--c-watch-bg"] },
  { key: "status", toks: ["--c-good", "--c-good-bg", "--c-bad", "--c-bad-bg"] },
  { key: "tone", toks: ["--c-up", "--c-down"] },
  { key: "条形", toks: ["--c-bar", "--c-bar-neg"] },
  { key: "中性", toks: ["--c-ink", "--c-text-2", "--c-text-3", "--c-line", "--c-line-soft", "--c-surface", "--c-surface-2", "--c-bg"] }
];

say("──────────────────────────────────────────────────────────────────");
say("② 颜色使用矩阵    数字 = 引用次数（不是颜色种类）");
say("──────────────────────────────────────────────────────────────────");
say("  " + pad("页面", 18) + C_GROUPS.map(g => padL(g.key, 8)).join(""));
say("  " + "-".repeat(18 + C_GROUPS.length * 8));

PAGE_ORDER.forEach(page => {
  const css = byPage[page];
  const cells = C_GROUPS.map(g => g.toks.reduce((a, t) => a + countToken(css, t), 0));
  say("  " + pad(PAGE_LABEL[page], 18) + cells.map(n => padL(n || "·", 8)).join(""));
});
say("");
say("  读法：主色（灰蓝）管结构 / 可点 / 参考，导航链接浮层都该是它；");
say("        橙 = 强调（**可行动 + 需关注**，2026-10-12 第二轮由「纯需关注」扩宽），");
say("        **全站唯一暖色**。这一列要连着「哪些规则」一起读：");
say("        数的是**接了几处**，不是屏幕上会出现几个 —— .ratio-row.st-watch");
say("        一条规则就能画出 N 行橙条，N 由数据决定。所以列小不代表屏幕上就少。");
say("        真正的预算得人眼看：「每屏 1–2 处橙」是目标，橙成片就退回");
say("        「一堆没有分辨度的数据」——那正是这次改版要修的毛病。");
say("        一眼能看出的越界信号（**主按钮的橙不算越界**，那是「可行动」那一半）：");
say("          · 橙拿去做**多系列区分** —— 三条线里一条是橙，橙就不再是重点；");
say("          · 橙落在**既不能点也不需关注**的装饰上");
say("            （建议块 / 结论块 / 比例条），那些都该是主色或墨色。");
say("        tone 全站应为 0（约定见 css/base.css 顶部），非 0 就是越界；");
say("        条形是页面 2 专用的中性刻度色，别页出现要问一句为什么；");
say("        中性列含 --c-ink（墨色焦点：品牌字 / 得分大数 / 页面 6 的评级与目标价）。");
say("");

/* ------------------------------------------------------------------ */
/* ③ 圆角 / 阴影                                                       */
/* ------------------------------------------------------------------ */
say("──────────────────────────────────────────────────────────────────");
say("③ 圆角 · 阴影    同一类零件各页是不是各写了一套");
say("──────────────────────────────────────────────────────────────────");
PAGE_ORDER.forEach(page => {
  const css = byPage[page];
  /* 999px（胶囊）与 50%（圆点）是形状不是尺寸，不算进比对 */
  const radius = valuesOf(css, "border-radius").filter(v => !/999px|50%/.test(v));
  const shadow = valuesOf(css, "box-shadow");
  if (!radius.length && !shadow.length) return;
  say("  " + PAGE_LABEL[page]);
  if (radius.length) say("      border-radius : " + radius.join("   "));
  if (shadow.length) say("      box-shadow    : " + shadow.join("   "));
});
say("");
say("  读法：.card 全站是 var(--radius-lg)。哪页的卡片用了别的值，");
say("        并排看就会觉得「这页的卡片有点不太一样」但说不清哪里不一样。");
say("");

/* ------------------------------------------------------------------ */
/* ④ 裸值清单                                                          */
/* ------------------------------------------------------------------ */
say("──────────────────────────────────────────────────────────────────");
say("④ 裸值清单    没走令牌的字号 / 圆角 / 间距（约定是零）");
say("──────────────────────────────────────────────────────────────────");

const BARE_PROPS = ["font-size", "border-radius", "padding", "margin", "gap", "color", "background", "box-shadow"];
/* 光学对齐微调：给文字下移 1px 对基线、把点居中到线上之类，不是为了好看而挑的尺寸。
   **多值也认** —— `padding: 3px 0` / `margin: -5px 0 0 -5px` 同样是光学微调。
   原来的正则只认单值，这两处假阳性一直挂在清单里，看着像没收拾干净。 */
const OPTICAL = /^(0|1px|2px|3px|-5px)$/;
const isOptical = v => v.trim().split(/\s+/).every(x => OPTICAL.test(x));
let bareTotal = 0;

for (const s of sections) {
  const css = strip(s.css);
  const hits = new Set();
  for (const prop of BARE_PROPS) {
    for (const v of valuesOf(css, prop)) {
      if (v.includes("var(")) continue;                       // 走了令牌
      if (/^(0|auto|inherit|none|transparent|currentColor)$/.test(v)) continue;
      if (isOptical(v)) continue;
      hits.add(prop + ": " + v);
    }
  }
  const label = [...hits];
  if (!label.length) continue;
  bareTotal += label.length;
  say("  §" + pad(s.num, 3) + pad(s.title, 26) + "→ " + PAGE_LABEL[SECTION_PAGE[s.num] || "共享"]);
  label.forEach(h => say("        " + h));
}
if (!bareTotal) say("  （无）");
say("");
say("  白名单：0 / 1px / 2px / 3px / -5px（单值或多值组合，如 padding: 3px 0）");
say("          与 inherit —— 前者是光学对齐微调，后者是「跟着父级」而不是挑了尺寸。");
say("          其余裸值全部列在上面。");
say("");
say("  历史：2026-10-12 改版前这里挂着 §14 估值标尺 / §16 溯源浮层的主色裸值");
say("  （rgba(47,111,184,0.16 / 0.18)），当时的结论是「统一到 --c-primary-soft(0.10)");
say("  会让底色变浅、先不动」。改版时新增了第二档 --c-primary-soft-2(0.18)，");
say("  按原透明度就近归位 —— 观感没变浅，裸值收干净。所以现在清单是空的：");
say("  不是「不管了」，是「两档令牌正好接得住」。");
say("");

/* ------------------------------------------------------------------ */
/* ⑤ 跨页复用的类                                                      */
/* ------------------------------------------------------------------ */
/* `.metric-value` 定义在共享段落、值 --fs-3xl，页面 3/5 都在用。
   这一段把这种「长相由别处决定」的关系摊开 —— ① 已经把它们的字号算进去了，
   列在这里是为了让人知道：改这些类会连带影响哪几页。 */
say("──────────────────────────────────────────────────────────────────");
say("⑤ 跨页复用的类    定义在某页，却被别页用");
say("──────────────────────────────────────────────────────────────────");

/* 每个类被哪些段落定义过（全局工具类不算，它们本来就该共用） */
const owners = {};
sections.forEach(s => {
  const page = SECTION_PAGE[s.num] || "共享";
  for (const m of strip(s.css).matchAll(/\.([a-z][a-z0-9-]*)/g)) {
    if (GLOBAL.has(m[1])) continue;
    (owners[m[1]] = owners[m[1]] || new Set()).add(page);
  }
});

const reuses = [];
for (const cls of Object.keys(owners).sort()) {
  const own = owners[cls];
  const users = Object.keys(usedBy).filter(p => usedBy[p].has(cls));
  /* 只看「定义在某一页、且有别的页在用」的 */
  const pageOwners = [...own].filter(p => p !== "共享");
  if (!pageOwners.length) continue;
  const foreign = users.filter(p => !pageOwners.includes(p));
  if (!foreign.length) continue;
  reuses.push({
    cls,
    owner: pageOwners.join("/"),
    users: users.join(" "),
    foreign: foreign.map(p => PAGE_LABEL[p].slice(0, 3)).join(" ")
  });
}

if (!reuses.length) {
  say("  （无：每个类都只被定义它的那一页用）");
} else {
  say("  " + pad("类名", 20) + pad("定义于", 10) + pad("使用页", 16) + "跨页");
  say("  " + "-".repeat(58));
  reuses.forEach(r =>
    say("  " + pad("." + r.cls, 20) + pad(PAGE_LABEL[r.owner] ? r.owner : r.owner, 10)
      + pad(r.users, 16) + r.foreign)
  );
}
say("");
say("  「跨页」那一列非空 = 这个类的长相由**别的页**决定。");
say("  想改它，得先想清楚会连带影响哪几页 —— 这也是全站一致性的来源：");
say("  共用越少，越容易各页长得不一样。");
say("");

/* ------------------------------------------------------------------ */
/* ⑥ 色值零裸值                                                        */
/* ------------------------------------------------------------------ */
/* 「颜色只在 :root 里定义，任何页面不许写死颜色」是本站最老的一条约定
   （见 css/base.css 顶部），但**一直没有自动闸门** —— ④ 的裸值清单只扫
   font-size / padding / border-radius 这类尺寸，颜色一直是肉眼查的。
   2026-10-12 改版顺手补上：三个 CSS 文件剥掉注释、去掉 :root 那一块之后，
   剩下的任何 #hex / rgb() / rgba() 都是漏网的裸值。

   ★ 目标 = 0。非 0 就说明有个颜色绕过了令牌，改配色时那个地方不会跟着变。 */
say("──────────────────────────────────────────────────────────────────");
say("⑥ 色值零裸值     :root 之外还写死着的颜色（目标 = 0）");
say("──────────────────────────────────────────────────────────────────");

/* 按花括号配对删掉一整块（@media 的块里还嵌着块，朴素正则会在第一个 }
   就收手，所以要数括号）。from 是块开头的正则，删掉从它到配对 } 为止。 */
function stripBlock(css, from) {
  const m = from.exec(css);
  if (!m) return css;
  let i = css.indexOf("{", m.index), depth = 0;
  for (let j = i; j < css.length; j++) {
    if (css[j] === "{") depth++;
    else if (css[j] === "}" && --depth === 0) {
      return css.slice(0, m.index) + css.slice(j + 1);
    }
  }
  return css;
}

const CSS_FILES = ["css/base.css", "css/layout.css", "css/components.css"];
const bareHits = [];

CSS_FILES.forEach(f => {
  let css = strip(read(f));   /* read() 自己会拼 ROOT，别再 join 一次 */
  /* 两处**允许**写死色值的地方，都排除掉：
     · :root { … }  —— 令牌就定义在这里，是唯一允许写色值的正经地方；
     · @media print { … } —— 纸上是白底，background: #fff 是打印专用落地色，
       跟着主题走反而会导出成灰糊糊一片。 */
  css = stripBlock(css, /:root\s*\{/);
  css = stripBlock(css, /@media\s+print\s*\{/);
  const re = /#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)/g;
  const hits = css.match(re) || [];
  if (hits.length) bareHits.push({ file: f, hits });
});

if (!bareHits.length) {
  say("  ✓ 0 —— 三个 CSS 文件里，:root 之外没有任何裸色值。");
} else {
  bareHits.forEach(h => {
    const uniq = [...new Set(h.hits)];
    say("  " + h.file + "：" + h.hits.length + " 处（" + uniq.length + " 种）");
    uniq.forEach(v => say("      " + v));
  });
}
say("");
say("  色值写在 css/base.css 的 :root 里、页面用 var(--xxx) 取 —— 这是「改一处全站变」的前提。");
say("  ★ 特例：css/base.css 的 @media print 里有 background: #fff !important，");
say("    那是**打印专用**的落地色（纸上没有主题），写死是对的，已从上面的扫描里排除。");
say("");

/* ------------------------------------------------------------------ */
/* 附：段落归属索引                                                    */
/* ------------------------------------------------------------------ */
say("──────────────────────────────────────────────────────────────────");
say("附：components.css 段落 → 页面 归属（脚本按这张表归组）");
say("    上面某一行看着不对，先核对这张表，再改 SECTION_PAGE");
say("──────────────────────────────────────────────────────────────────");
sections.forEach(s =>
  say("  §" + pad(s.num, 3) + pad(s.title, 34) + "→  " + PAGE_LABEL[SECTION_PAGE[s.num] || "共享"])
);

console.log(out.join("\n"));
