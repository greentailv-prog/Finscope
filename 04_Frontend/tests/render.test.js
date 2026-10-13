/* FinScope 渲染冒烟测试
 * 用一个极简 DOM 桩，在 node 里真正跑一遍六个页面的 render()。
 * 目的：node --check 只能证明「语法没写错」，跑 render 才能证明「跑得起来」。
 * 换数据源之后先跑这个 —— 缺字段的页面会在这里暴露，而不是在演示现场。
 *
 * ★ 2026-10-13：数据源从 data/mock_data.js 换成 data/real_data.js（D 的统一
 *   数据对象）+ data/real_memo.js（D 的 memo 绑定表）。这不是「换一份样例」，
 *   是**换一套契约**：mock 里那批 A/B/C/D 都不产出的字段（business_mix /
 *   history / company.business / ratios.*._score / risk.calculation 的五运算
 *   算式 …）已经连同消费它们的页面代码一起撤掉了。所以本文件也对着合同
 *   重写了一遍：凡是断言在已撤字段上的条目，删；凡是条数写死的，改成从
 *   F.data.* 推导 —— 数据一换、这些断言跟着动，不会变成一堆假红。
 *
 * 用法：node tests/render.test.js
 *      node tests/render.test.js <04_Frontend 目录>   # 显式指定
 */
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const ROOT = process.argv[2] || path.join(__dirname, "..");

/* ------------------------------------------------------------------ */
/* 极简 DOM 桩：只实现页面真正用到的那点 API                            */
/* ------------------------------------------------------------------ */
/* ★ 故意**不实现** lastChild / childNodes / firstChild，也**不聚合**
   textContent。理由：桩越小，页面代码里那些「浏览器里能跑、换个环境就崩」
   的写法越容易在这里现形（p5 就在 lastChild 与 childNodes 上各栽过一次）。
   真要数子元素请用 .children；真要取整段文字请用下面的 deepText()。 */
function El(tag) {
  const self = this;
  this.tagName = String(tag).toUpperCase();
  this.children = [];
  this.style = {};
  this.dataset = {};
  this._attrs = {};
  this.textContent = "";
  this.className = "";
  this.parentNode = null;
  this.title = "";
  this.href = "";
  this.id = "";
  this.colSpan = 0;
  this.addEventListener = function () {};
  this.setAttribute = function (k, v) { self._attrs[k] = v; };
  this.getAttribute = function (k) { return self._attrs[k]; };
  this.getBoundingClientRect = function () {
    return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 };
  };
  this.querySelector = function () { return null; };
  this.insertBefore = function (n) { self.children.unshift(n); return n; };
  /* ★ 2026-10-13：classList.add / remove 现在**照真浏览器报错**，不再吞空串。
     原来这里写的是 `if (c && ...)` —— 空串被静默忽略。于是
     `el.classList.add("")` 在 387 条测试里一路绿灯，在浏览器里直接抛
     「The token provided must not be empty.」整页挂掉。
     **桩比浏览器宽松，就是给这类 bug 发通行证。** 见 EDGE_CASES #98。 */
  function checkToken(c) {
    const s = String(c);
    if (s === "") throw new Error("Failed to execute 'add' on 'DOMTokenList': The token provided must not be empty.");
    if (/\s/.test(s)) throw new Error("Failed to execute 'add' on 'DOMTokenList': The token provided ('" + s + "') contains HTML space characters, which are not valid in tokens.");
  }
  this.classList = {
    add: function () {
      for (let i = 0; i < arguments.length; i++) {
        const c = arguments[i];
        checkToken(c);
        if (!self.classList.contains(c)) self.className = (self.className + " " + c).trim();
      }
    },
    remove: function () {
      for (let i = 0; i < arguments.length; i++) {
        const c = arguments[i];
        checkToken(c);
        const parts = self.className.split(/\s+/).filter(x => x && x !== c);
        self.className = parts.join(" ");
      }
    },
    toggle: function (c, force) {
      const want = force === undefined ? !self.classList.contains(c) : !!force;
      if (want) self.classList.add(c); else self.classList.remove(c);
      return want;
    },
    contains: function (c) { return self.className.split(/\s+/).indexOf(c) >= 0; }
  };
  this.appendChild = function (n) {
    if (n === null || n === undefined) throw new Error("<" + self.tagName + "> appendChild(" + n + ")");
    self.children.push(n);
    n.parentNode = self;
    return n;
  };
}

const documentStub = {
  readyState: "loading",                 // 让 app.js 不自动 boot
  createElement: function (t) { return new El(t); },
  createTextNode: function (t) { return { textContent: String(t) }; },
  getElementById: function () { return null; },
  querySelector: function () { return null; },
  addEventListener: function () {},
  removeEventListener: function () {},
  documentElement: { clientWidth: 1200, clientHeight: 900 },
  body: new El("body")
};

const sandbox = {};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.document = documentStub;
sandbox.location = { hash: "" };
sandbox.setTimeout = function () {};
sandbox.console = { log: () => {}, warn: () => {}, error: () => {} };
sandbox.matchMedia = undefined;
/* ★ 2026-10-13 补：真浏览器的 window 一定有 addEventListener。
   页面 1 现在在模块级挂了 beforeprint（打印前展开截断的证据全文），
   桩里没有它就会在**加载阶段**抛「window.addEventListener is not a function」，
   整页测试连带失败。**修桩而不是在页面里加 `if` 兜底** ——
   浏览器里不存在这个分支，为它写兜底等于给一条永不执行的路径写测试。 */
sandbox.addEventListener = function () {};
sandbox.removeEventListener = function () {};
vm.createContext(sandbox);

const FILES = [
  "data/real_data.js",
  "data/real_memo.js",
  "js/format.js",
  "js/contract.js",
  "js/dataLoader.js",
  /* ★ 2026-10-13 新增：A 的产物。顺序**照抄 index.html** ——
     测试里的加载顺序和真页面不一致，测出来的就不是真页面。
     tokenize 必须在 search 前面（后者的 BM25 词表建在前者上）。
     注意这里只加载 A 那一组里的「引擎 + 看板 + 预设题」，
     17 MB 的 a/data/shard_*.js 不在其中 —— 它们是运行期按需注入的，
     页面 1 的看板与问答块本来就设计成**不载分片也能渲染**。 */
  "a/tokenize.js",
  "a/search.js",
  "a/data/tokens_golden.js",
  "a/data/manifest.js",
  "a/data/metrics.js",
  "a/data/queries.js",
  "app.js",
  "js/pages/p1-upload.js",
  "js/pages/p2-overview.js",
  "js/pages/p3-diagnosis.js",
  "js/pages/p4-risk.js",
  "js/pages/p5-valuation.js",
  "js/pages/p6-memo.js"
];

const out = [];
let pass = 0, total = 0;
function t(label, ok, detail) {
  total++;
  if (ok) pass++;
  out.push(`${ok ? "PASS" : "FAIL"}  ${label}${ok || !detail ? "" : "\n        " + detail}`);
}

for (const f of FILES) {
  const full = path.join(ROOT, f);
  if (!fs.existsSync(full)) { t("文件存在 " + f, false, "找不到 " + full); continue; }
  try {
    vm.runInContext(fs.readFileSync(full, "utf8"), sandbox, { filename: f });
  } catch (e) {
    t("加载 " + f, false, e.message);
  }
}

const F = sandbox.FinScope;
const D = F.data;                        // 统一数据对象（D 的交付物）
F.data.load();                           // 无参 → window.FINSCOPE_DATA + FINSCOPE_MEMO

/* 递归聚合一段文字。桩的 textContent 只管自己那一格，子元素不管 —— 这是
   故意的（见桩的注释）。所以凡是要「这一段里出现了没有」的断言，都走它。 */
function deepText(node) {
  if (!node) return "";
  if (!node.children || !node.children.length) return String(node.textContent || "");
  let s = String(node.textContent || "");
  node.children.forEach(c => { s += deepText(c) + " "; });
  return s;
}

/* 遍历整棵渲染树。**每个元素只记一条**，否则一个元素带 3 个类
   就会被后续的 filter 数成 3 个元素（这个坑我踩过一次）。
   text  = 元素自己那一格的文字（不聚合）
   all   = 含全部后代的文字（聚合） */
function walk(node, acc) {
  if (!node || !node.children) return acc;
  acc.push({
    el: node,
    classes: String(node.className || "").split(/\s+/).filter(Boolean),
    text: String(node.textContent || "").trim(),
    all: deepText(node).trim()
  });
  node.children.forEach(c => walk(c, acc));
  return acc;
}

const ORDER = ["p1", "p2", "p3", "p4", "p5", "p6"];
const trees = {};
const pageText = {};

out.push("=== 六页 render() 实跑 ===");
for (const id of ORDER) {
  const page = F.pages[id];
  if (!page) { t(id + " 模块已注册", false); continue; }
  const root = new El("section");
  try {
    page.render(root);
    trees[id] = root;
    pageText[id] = deepText(root);
    t(id + " " + page.title + " 渲染无异常", true);
  } catch (e) {
    t(id + " " + page.title + " 渲染无异常", false, e.message + "\n" + String(e.stack).split("\n")[1]);
  }
}

/* 每个页面模块都有一段「本页待办」清单。这些清单是**开发期的脚手架**，
   演示时靠 app.js 给 <body> 加 .app-demo 把它整张隐藏。
   真正让它消失的是这一步：每张「本页待实现」卡必须带 .dev-card。
   少标一个，那个开关就会漏掉一页 —— 而这在演示现场是看不出来的，
   只有翻到那一页才发现开发清单还挂在那儿。所以在这里钉死。 */
out.push("\n=== 开发卡标记（演示模式靠它隐藏） ===");
let devTotal = 0;
ORDER.forEach(id => {
  const a = walk(trees[id], []);
  const cards = a.filter(x => x.classes.includes("dev-card")).length;
  const lists = a.filter(x => x.classes.includes("todo-list")).length;
  devTotal += cards;
  t(id + "：.dev-card 数量与「待实现」清单一致", cards === lists,
    "dev-card " + cards + " / todo-list " + lists);
});
t("全站共 6 张开发卡（六页各一张）", devTotal === 6, "实际 " + devTotal);

/* ==================================================================== */
/* 页面1 上传年报 —— 契约体检（E 的消费端契约在页面上的那一半）           */
/* -------------------------------------------------------------------- */
/* 这一块和 tools/interface-check.js 是**同一个契约走出来的两份输出**：
   一个打到终端给 E 自己看，一个渲染到屏幕上给全组看。
   它回答的是「现在到底还差谁的东西」，所以两条都要在：
   ① 骨架自检卡里说出「几个页面可完整渲染」和「多少项待交付」；
   ② 「还差谁的东西」清单里每一行都要落到具体的人头上。 */
out.push("\n=== 页面1 契约体检 ===");
{
  const p1 = trees.p1;
  if (p1) {
    const a1 = walk(p1, []);
    const has1 = c => a1.some(x => x.classes.includes(c));
    const cnt1 = c => a1.filter(x => x.classes.includes(c)).length;
    const cs = D.contractStatus();

    t("有上传区 .upload-zone", has1("upload-zone"));

    /* ---- 2026-10-13 改：原来这里验的是「有一个禁用的『开始分析』按钮」。
       ★ 为什么删掉而不是保留：那个按钮**没有下一步** ——
         它等的是 D 的 orchestrator，而 orchestrator 要起本地服务，
         file:// 下永远不会有。一个永远禁用的按钮不是「待对接」，是死路；
         而且它挡住了一件更该验的事：这个格子在屏幕上到底能不能用。
       ★ 换成下面四条：**上传窗口必须真的可交互**。
         判据取的是浏览器真正的入口 —— 一枚 .upload-input 的
         <input type="file">。没有它，点击、拖放、键盘三条路一条都不通，
         「上传区」就只是个画出来的方块（这正是用户报的那个问题）。 */
    const fileInput = a1.find(x => x.el.tagName === "INPUT" && x.classes.includes("upload-input"));
    t("上传窗口有真的 <input type=\"file\">（点击 / 拖放 / 键盘三条路的入口）", !!fileInput);
    /* ★ 读 el.accept 而不是 el._attrs.accept：页面用的是 `input.accept = "..."`
       这种**属性赋值**（DOM 里本来就是这么写的），走的不是 setAttribute，
       桩的 _attrs 收不到。上面这行断言曾经因此误报过一次 —— 记在这里。 */
    const acceptAttr = fileInput ? String(fileInput.el.accept || "") : "";
    t("它只管 .pdf", !!fileInput && /pdf/i.test(acceptAttr), acceptAttr || "没有 input");
    t("它的 type 是 file", !!fileInput && fileInput.el.type === "file",
      fileInput ? String(fileInput.el.type) : "没有 input");

    /* 透明铺满、而不是 display:none —— 后者不可点也不可聚焦，
       等于把入口又堵回去了。这一条钉的是**实现方式**：两种写法在
       渲染出来的 DOM 树上一模一样，只有 CSS 里有区别。
       所以这里直接读 components.css 的源文本，取 .upload-input 的**第一条**规则。 */
    const compSrc = fs.readFileSync(path.join(ROOT, "css/components.css"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "");
    const inputRule = (compSrc.match(/(^|\})([^{}]*\.upload-input[^{}]*)\{([^{}]*)\}/) || [])[3] || "";
    t("它是透明铺满，而不是 display:none / visibility:hidden",
      /position:\s*absolute/.test(inputRule) && /opacity:\s*0/.test(inputRule) &&
      !/display:\s*none/.test(inputRule) && !/visibility:\s*hidden/.test(inputRule),
      inputRule.replace(/\s+/g, " ").trim().slice(0, 120) || "没找到 .upload-input 规则");

    /* ---- 看板与问答 ----
       数据来自 A（a/README.md 有 sha256 存证）。这里验的是**接上了**，
       不是「渲染出某个数字」—— 数字由 A 负责，缺了就是 A 换了版本。 */
    t("有数据看板表 .board-table", has1("board-table"));
    t("看板列头是 2023 / 2024 / 2025 三年并列",
      ["2023", "2024", "2025"].every(y =>
        a1.some(x => x.el.tagName === "TH" && x.text === y)),
      a1.filter(x => x.el.tagName === "TH").map(x => x.text).join(" | "));
    /* ★ 这一条是给「E 不算同比」立的闸门。
       A 自己的看板有「同比」一列（它用 pct(v25,v24) 现算），
       迁到 E 这边时最容易被顺手抄过来 —— 而同比是增长率，
       属于 B 的成长性维度，E 一个数都不该算。 */
    t("看板**不列同比**（同比是 B 的成长性维度，E 不算）",
      !a1.some(x => x.el.tagName === "TH" && /同比|增长|增速/.test(x.text)),
      a1.filter(x => x.el.tagName === "TH").map(x => x.text).join(" | "));
    t("看板 9 行指标（A 的 17 个科目里有 8 个不落在这一列口径上则少于此数）",
      cnt1("fin-row") > 0, "渲染 " + cnt1("fin-row") + " 行");
    t("有公司 chips .chip（点一下读那一家的年报正文）", cnt1("chip") > 0,
      "渲染 " + cnt1("chip") + " 枚");
    t("有 A 的预设问题 .preset", cnt1("preset") > 0, "渲染 " + cnt1("preset") + " 道");
    t("有自由提问输入框 .qa-input", has1("qa-input"));
    t("有证据块容器 .ev-list", has1("ev-list"));

    t("有「还差谁的东西」清单 .owner-list", has1("owner-list"));
    t("清单每人一行",
      cnt1("owner-row") === Object.keys(cs.byOwner).length,
      "渲染 " + cnt1("owner-row") + " / 数据 " + Object.keys(cs.byOwner).length);
    t("每行都有队友代号", cnt1("owner-who") === cnt1("owner-row"));
    t("每行都有内容描述（空行会让这块看着像坏了）",
      a1.filter(x => x.classes.includes("owner-what")).every(x => x.text.length > 0));
    t("四行分别落到 A / B / C / D",
      a1.filter(x => x.classes.includes("owner-who")).map(x => x.text).sort().join(",") === "A,B,C,D",
      a1.filter(x => x.classes.includes("owner-who")).map(x => x.text).join(","));

    /* 骨架自检两个数字必须出现在页面上 —— 它们是这块的入口，
       少一个，看的人就不知道点进「还差谁的东西」之前先看什么。 */
    t("骨架自检说了「几个页面可完整渲染」",
      new RegExp(cs.totals.renderable + " / " + cs.totals.pages + " 个页面可完整渲染").test(pageText.p1),
      "期望 " + cs.totals.renderable + " / " + cs.totals.pages);
    t("骨架自检说了「待交付多少项」",
      new RegExp("待交付\\s*" + cs.totals.open + " 项").test(pageText.p1), "期望 " + cs.totals.open);
    t("骨架自检说了「校验提醒几项」",
      new RegExp("校验提醒\\s*" + D.status().warnings.length + " 项").test(pageText.p1));

    /* ★ 2026-10-13：原来这里验的是「图表库状态与实际一致」
       （pageText.p1 里那句 Chart.js 已加载/未加载）。Chart.js 撤了，
       跟着删。**不改成断言「未加载」** —— 那等于逼着页面留一行永远红的自检格。
       取而代之的是下面「全站零 canvas」那条：它验的是**真的不变式**
       （六个页面一张 canvas 都不依赖），不是某个库在不在。 */
    t("骨架自检里不再提图表库",
      !/图表库|Chart\.js/.test(pageText.p1), pageText.p1.slice(0, 160));
  }
}

/* ==================================================================== */
/* 页面4 风险雷达                                                        */
/* -------------------------------------------------------------------- */
out.push("\n=== 页面4 风险雷达 ===");
{
  const p4 = trees.p4;
  if (p4) {
    const a4 = walk(p4, []);
    const has4 = c => a4.some(x => x.classes.includes(c));
    const cnt4 = c => a4.filter(x => x.classes.includes(c)).length;

    const risks = D.sortedRisks();
    const summary = D.riskSummary();
    const scan = D.rulesSummary();

    t("有概览条 .risk-overview", has4("risk-overview"));
    t("概览条三个数字格", cnt4("ro-item") === 3, "实际 " + cnt4("ro-item"));
    t("风险卡片数与数据一致", cnt4("risk-card") === risks.length,
      "渲染 " + cnt4("risk-card") + " / 数据 " + risks.length);
    t("高风险卡片数与数据一致",
      cnt4("sev-high") === risks.filter(r => r.severity === "high").length,
      "渲染 " + cnt4("sev-high") + " / 数据 " + risks.filter(r => r.severity === "high").length);
    t("每张卡都带一个严重度类",
      cnt4("sev-high") + cnt4("sev-attention") + cnt4("sev-normal") === cnt4("risk-card"),
      cnt4("sev-high") + "+" + cnt4("sev-attention") + "+" + cnt4("sev-normal"));

    /* 概览条三个数来自 riskSummary()，不写死 —— 数据变了跟着变 */
    const roText = a4.filter(x => x.classes.includes("risk-overview")).map(x => x.all).join(" ");
    t("概览条报出高/中/低三个数",
      [summary.high, summary.medium, summary.low].every(n =>
        new RegExp("(^|\\s)" + n + "\\s").test(roText)),
      roText.slice(0, 160));

    /* ★ 这一句是这一页最容易缺、也最要紧的一句：只有 4 张卡时，读者的默认
       理解是「4 个问题」；加上「共扫描 36 条」之后才是「扫了 36 条、命中 4 条」。
       后者同时说明了扫描的覆盖面和结论的克制。 */
    t("概览条说明了「扫了多少条、命中多少条」",
      new RegExp("已扫描 " + scan.total + " 条规则，触发 " + scan.triggered + " 条").test(roText),
      roText.slice(0, 200));
    t("概览条报出「无法判断」的条数（D 的规则里有大量缺变量项）",
      scan.other === 0 || new RegExp(scan.other + " 条因缺变量无法判断").test(roText));

    /* 卡片默认展开策略：只有重大风险默认摊开。全折叠则看不到落点，
       全展开则一屏全是字。 */
    const cards = a4.filter(x => x.classes.includes("risk-card"));
    const expectedOpen = risks.filter(r => r.severity === "high").length;
    t("只有重大风险默认展开",
      cards.filter(x => x.classes.includes("is-open")).length === expectedOpen,
      "展开 " + cards.filter(x => x.classes.includes("is-open")).length + " / 期望 " + expectedOpen);
    const highCard = cards.find(x => x.classes.includes("sev-high"));
    t("展开的那张确实是重大风险",
      expectedOpen === 0 || (!!highCard && highCard.classes.includes("is-open")),
      "className = " + (highCard && highCard.el.className));

    /* ---- 证据链四层 ---- */
    /* D 的 evidence_chain[] 每步带 step（数据/计算/出处/判断/归因/建议），
       页面按 step 归到四层。层数不写死 —— 「归因」那一层是 D 给了才有。 */
    const withAttr = risks.filter(r => (r.evidence_chain || []).some(s => s.step === "归因")).length;
    const expectedLayers = risks.length * 3 + withAttr;
    t("证据链层数与数据一致（4 卡 × 3 层 + 有归因的再加一层）",
      cnt4("layer") === expectedLayers,
      "渲染 " + cnt4("layer") + " / 期望 " + expectedLayers);
    t("每层都有编号标记", cnt4("layer-mark") === cnt4("layer"),
      cnt4("layer-mark") + " / " + cnt4("layer"));
    t("事实层（①②③）数量 = 层数 − 结论层", cnt4("is-fact") === expectedLayers - risks.length,
      "实际 " + cnt4("is-fact"));
    t("结论层每张卡恰好一层", cnt4("is-conclusion") === risks.length, "实际 " + cnt4("is-conclusion"));

    t("计算卡每张卡一张", cnt4("calc-box") === risks.length, "实际 " + cnt4("calc-box"));
    t("代入值行与计算卡同数", cnt4("calc-eq") === cnt4("calc-box"));
    t("代入值是「科目 值」的串，不再是 A − B = C 的算式",
      a4.filter(x => x.classes.includes("calc-eq"))
        .every(x => walk(x.el, []).some(y => y.classes.includes("ce-term"))));
    /* 代入值必须已格式化：不该出现 0.412 / -0.0121 这种裸小数 */
    const eqTexts = a4.filter(x => x.classes.includes("calc-eq")).map(x => x.all);
    out.push("   代入值正文：");
    eqTexts.forEach(s => out.push("     " + s));
    t("代入值无裸小数（不是 0.747 / -0.0121）",
      !eqTexts.some(s => /(^|[^\d.])-?0\.\d/.test(s)), eqTexts.join(" | "));
    t("触发标记每张卡一个", cnt4("calc-flag") === risks.length, "实际 " + cnt4("calc-flag"));
    t("无回落版式（四条都能拼出算式层）", !has4("is-fallback"));

    t("解释正文每张卡一段", cnt4("risk-explain") === risks.length, "实际 " + cnt4("risk-explain"));
    t("应对建议每张卡一条", cnt4("risk-suggest") === risks.length, "实际 " + cnt4("risk-suggest"));
    t("建议标签与建议条数相同", cnt4("sug-tag") === cnt4("risk-suggest"));

    /* ---- 出处：并进证据链，不再是独立模块 ---- */
    t("不再有独立的出处层（.src-chips 已删）", !has4("src-chips") && !has4("src-chip"));
    const evAll = risks.flatMap(r => r.evidence_chain || []);
    const evWithPage = evAll.filter(e => e.page !== null && e.page !== undefined);
    t("出处列数与证据链中带页码的步骤数一致",
      cnt4("col-source") === evWithPage.length,
      "渲染 " + cnt4("col-source") + " / 数据 " + evWithPage.length);
    t("带页码的证据都能点开溯源",
      cnt4("page-link") === evWithPage.length,
      "渲染 " + cnt4("page-link") + " / 数据 " + evWithPage.length);

    /* ---- 规则明细表 ---- */
    const rules = D.get("rules_evaluated", []) || [];
    t("规则明细每行一个状态胶囊",
      cnt4("status-chip") === rules.length,
      "渲染 " + cnt4("status-chip") + " / 数据 " + rules.length);
    /* D 的规则只给「通过 / 无法判断」两档 —— 没有「未触发」这一说，
       也没有「警告」。这一页照它给的状态原样显示，不自造第三档。 */
    const statuses = {}; rules.forEach(r => { statuses[r.status] = (statuses[r.status] || 0) + 1; });
    out.push("   规则状态分布：" + JSON.stringify(statuses));
    t("规则明细里没有自造的状态词",
      a4.filter(x => x.classes.includes("status-chip"))
        .every(x => x.text === "通过" || x.text === "无法判断" || x.text === "触发"),
      a4.filter(x => x.classes.includes("status-chip")).map(x => x.text).filter((v, i, s) => s.indexOf(v) === i).join(","));

    t("页面4 无涨跌配色（tone-*）",
      !a4.some(x => x.classes.some(c => c.indexOf("tone-") === 0)));
    t("已移除骨架自检卡片", !has4("kv-grid"));
    t("不含 undefined / NaN", !/undefined|NaN/.test(pageText.p4), pageText.p4.slice(0, 200));
  }
}

/* ==================================================================== */
/* 页面5 估值分析                                                        */
/* ==================================================================== */
out.push("\n=== 页面5 估值分析 ===");
{
  const p5 = trees.p5;
  if (p5) {
    const a5 = walk(p5, []);
    const has5 = c => a5.some(x => x.classes.includes(c));
    const cnt5 = c => a5.filter(x => x.classes.includes(c)).length;
    const v = D.get("valuation", {});

    t("有估值标尺 .vr", has5("vr"));
    t("标尺两行区间条（D 两法都给了 valuation_range）",
      cnt5("vr-row") === 2, "实际 " + cnt5("vr-row"));
    t("刻度标签 ≥ 3 个", cnt5("vr-tick") >= 3, "实际 " + cnt5("vr-tick"));
    t("网格线数量与刻度一致",
      cnt5("vr-gridline") === cnt5("vr-tick"),
      cnt5("vr-gridline") + " vs " + cnt5("vr-tick"));
    t("中枢点 2 个", cnt5("vr-dot") === 2, "实际 " + cnt5("vr-dot"));

    /* 条形定位：left / width 必须是百分比，且落在 0–100 之间 */
    const bars = a5.filter(x => x.classes.includes("vr-bar")).map(x => x.el.style);
    t("区间条用百分比定位",
      bars.length === 2 && bars.every(s => /%$/.test(s.left) && /%$/.test(s.width)),
      bars.map(s => s.left + "+" + s.width).join(" | "));
    const pct = s => parseFloat(s);
    t("区间条不出画布",
      bars.every(s => pct(s.left) >= 0 && pct(s.left) + pct(s.width) <= 100.001),
      bars.map(s => pct(s.left) + "+" + pct(s.width)).join(" | "));

    /* ---- 现价竖线（旧版 spec 的第一条缺口，D 已补 market_data.price） ---- */
    const priceLines = a5.filter(x => x.classes.includes("vr-priceline"));
    t("标尺上画出现价竖线", priceLines.length === 2,
      "两行各一条，实际 " + priceLines.length);
    const price = v.blended && v.blended.current_price;
    t("现价竖线写在页面文字里（读者要知道竖线是多少钱）",
      new RegExp("竖线.*现价").test(pageText.p5) || pageText.p5.includes("现价 " + price));
    t("现价日期一并给出（没有日期的现价没有意义）",
      !v.market_data || !v.market_data.price_date
        || pageText.p5.includes(v.market_data.price_date));

    /* ---- 重叠段：**不重叠时不该画** ----
       D 的两条区间现在离得很远（相对估值 413–660 vs DCF 1,267–24,654），
       画一个 band 等于凭空造出一段共识。所以这条断言是「与数据一致」，
       而不是写死 0 或 1。 */
    const rComps = v.comps && v.comps.valuation_range;
    const rDcf = v.dcf && v.dcf.valuation_range;
    const overlap = (rComps && rDcf && Number.isFinite(rComps.low) && Number.isFinite(rDcf.low)
      && Math.min(rComps.high, rDcf.high) > Math.max(rComps.low, rDcf.low));
    t("重叠段是否存在与数据一致",
      cnt5("vr-band") === (overlap ? 1 : 0),
      "渲染 " + cnt5("vr-band") + " / 数据" + (overlap ? "有交集" : "无交集"));
    if (!overlap) {
      t("两法区间不重叠时明说「不重叠」并把它当作发现",
        pageText.p5.includes("不重叠"));
    }

    /* ---- 对数刻度 ----
       两法区间跨 60 倍，线性刻度下窄的那条只剩 0.95% 宽 —— 视觉上等于不存在。
       这是坐标轴的选择（与 niceScale 取整同类），不是重新估值；
       但**必须在页面上写出来**，否则读者会按线性比例去读。 */
    const spread = (rComps && rDcf)
      ? Math.max(rComps.high / rComps.low, rDcf.high / rDcf.low) : 0;
    t("跨度大时改用对数刻度并在标尺上标注",
      spread >= 10 ? /对数/.test(pageText.p5) : !/对数/.test(pageText.p5),
      "最大跨度 " + spread.toFixed(1) + " 倍");
    t("单位已标注", has5("vr-unit"));

    /* ---- 结论大数 ---- */
    t("三个结论大数", cnt5("ro-item") === 3, "实际 " + cnt5("ro-item"));
    t("估值对象行已渲染（target 不再是被忽略的死数据）", has5("v-target"));
    t("DCF 假设全部渲染（kv-cell 与 dcf.inputs 条数一致）",
      cnt5("kv-cell") >= 4, "实际 " + cnt5("kv-cell"));
    t("可比公司表已渲染", cnt5("mini-table") >= 3, "实际 " + cnt5("mini-table"));
    /* ★ 2026-10-13：原来这条验的是「页面 5 里没有『图表库未加载』的降级文字」。
       Chart.js 撤了之后那句话根本无从产生，断言变成恒真 ——
       换成本页那条**真的不变式**：标尺是 DOM + CSS 画的，不是 canvas。 */
    t("估值标尺是 DOM，不是 canvas",
      a5.filter(x => x.tagName === "CANVAS").length === 0
        && !a5.some(x => /图表库未加载/.test(x.text)));

    /* ★ 金额单位 —— 这一条钉的是本会话修掉的真实显示 bug。
       D 的 valuation 下**没有任何 unit 字段**（Schema 只对 company.amount_unit
       与 financials.*.unit 声明了「元」），所以 moneyOf() 必须自己补上「元」。
       不补的话 fmt.money 会走默认单位「亿元」、scale = 1，于是
       revenue_base = 168838102514.79 被渲染成 "168,838,102,514.8 亿元" ——
       差了整整一亿倍，而且看起来还挺像个数。 */
    const revBase = v.dcf && v.dcf.inputs && v.dcf.inputs.revenue_base;
    if (Number.isFinite(revBase)) {
      const good = F.fmt.money({ value: revBase, unit: "元" });
      t("DCF 收入基数的金额刻度与 D 的 memo 一致（亿元，不是裸元）",
        pageText.p5.includes(good),
        "期望出现 " + good);
      t("没有把裸元当亿元输出（差一亿倍的那个 bug）",
        !pageText.p5.includes(String(revBase)),
        "页面里出现了原始元值 " + revBase);
    }

    /* 定位值取 2 位小数：不该出现 left:16.666666666666664% 这种浮点噪声 */
    const noisy = a5.filter(x => x.el.style && typeof x.el.style.left === "string")
      .filter(x => !/^-?\d+(\.\d{1,2})?%$/.test(x.el.style.left))
      .map(x => x.el.className + " left=" + x.el.style.left);
    t("inline 定位值已取整到 2 位小数", noisy.length === 0, noisy.join(" | "));

    /* 告警条数必须与 D 的 warnings 一致 —— 少报一条等于把 D 的告警藏起来 */
    const warns = v.warnings || [];
    t("估值告警条数与 D 的 warnings 一致",
      a5.filter(x => x.classes.includes("warn-list")).length > 0
        && new RegExp("估值告警（" + warns.length + " 项）").test(pageText.p5),
      "数据 " + warns.length + " 条");

    t("不含 undefined / NaN", !/undefined|NaN/.test(pageText.p5), pageText.p5.slice(0, 200));
  }
}

/* ---- 刻度算法：这页唯一的数学，纯函数，单独覆盖 ---- */
out.push("\n=== 页面5 刻度算法 ===");
{
  const nice = F.pages.p5.scale;
  const log = F.pages.p5.logScale;
  const choose = F.pages.p5.chooseScale;
  t("scale / logScale / chooseScale 都已导出",
    typeof nice === "function" && typeof log === "function" && typeof choose === "function");

  const sc1 = nice(14.2, 24.6);
  t("普通区间 → 读得下去的整齐步长",
    !!sc1 && [0.1, 0.25, 0.5, 1, 2, 2.5, 5, 10].some(v => Math.abs(sc1.step - v) < 1e-9),
    sc1 && "step=" + sc1.step);
  t("区间被包含在刻度范围内", !!sc1 && sc1.min <= 14.2 && sc1.max >= 24.6,
    sc1 && sc1.min + " – " + sc1.max);
  t("刻度覆盖整个区间",
    !!sc1 && sc1.ticks[0] === sc1.min && sc1.ticks[sc1.ticks.length - 1] === sc1.max);
  t("刻度等距",
    !!sc1 && sc1.ticks.every((v, i) => i === 0 || Math.abs((v - sc1.ticks[i - 1]) - sc1.step) < 1e-9),
    sc1 && sc1.ticks.join(","));
  t("线性刻度的 pos 单调递增",
    !!sc1 && sc1.pos(sc1.min) === 0 && Math.abs(sc1.pos(sc1.max) - 100) < 1e-9);
  t("退化区间 low===high 不除零", !!nice(20, 20) && nice(20, 20).max > nice(20, 20).min,
    JSON.stringify(nice(20, 20)));
  t("low > high 也能处理", !!nice(24.6, 14.2));
  t("非数字 → null", nice("abc", 20) === null && nice(null, 20) === null);

  /* 对数刻度：等比的量要在同一把尺上比，只能取对数 */
  const lg = log(413.91, 24654.14);
  t("对数刻度能画", !!lg && lg.log === true);
  t("对数刻度的 pos 单调递增",
    !!lg && lg.pos(413.91) < lg.pos(1267.32) && lg.pos(1267.32) < lg.pos(24654.14));
  t("对数刻度里窄的那条不再是看不见的一条线",
    !!lg && (lg.pos(660.13) - lg.pos(413.91)) > 2,
    lg && "相对估值带宽 " + (lg.pos(660.13) - lg.pos(413.91)).toFixed(2) + "%");
  t("对数刻度不含 0 与负数（会返回 null 而不是画错）",
    log(0, 100) === null && log(-5, 100) === null);
  t("对数刻度的刻度值是 1/2/5 × 10^k",
    !!lg && lg.ticks.every(v => {
      const m = v / Math.pow(10, Math.floor(Math.log10(v) + 1e-9));
      return [1, 2, 5].some(x => Math.abs(m - x) < 1e-6);
    }),
    lg && lg.ticks.join(","));

  /* chooseScale 是这页的裁判：量级相当走线性，跨 10 倍才换对数 */
  t("量级相当 → 线性", choose(14.2, 24.6).log === false,
    "log=" + (choose(14.2, 24.6) || {}).log);
  t("跨度 ≥ 10 倍 → 对数", choose(413.91, 24654.14).log === true);
  t("恰好 10 倍走对数（阈值含等号）", choose(10, 100).log === true);
  t("低于 10 倍仍走线性", choose(9.9, 98).log === false,
    "9.9 × 9.9 = 9.9 倍，log=" + (choose(9.9, 98) || {}).log);
  t("非数字 → null", choose(null, 5) === null);
}

/* ==================================================================== */
/* 页面3 财务诊断                                                        */
/* -------------------------------------------------------------------- */
out.push("\n=== 页面3 财务诊断 ===");
{
  const p3 = trees.p3;
  if (p3) {
    const a3 = walk(p3, []);
    const has3 = c => a3.some(x => x.classes.includes(c));
    const cnt3 = c => a3.filter(x => x.classes.includes(c)).length;

    const groups = D.ratioGroups();
    const all = groups.flatMap(g => D.ratioItems(g.key));
    const core = all.filter(x => x.isCore);
    const withPage = all.filter(x => x.page !== null && x.page !== undefined);

    t("五个维度块", cnt3("dim-block") === groups.length && groups.length === 5,
      "渲染 " + cnt3("dim-block") + " / 数据 " + groups.length);
    t("指标行数 = 指标数 + 每块一个折叠头",
      cnt3("ratio-row") === all.length + groups.filter(g =>
        D.ratioItems(g.key).some(x => !x.isCore)).length,
      "渲染 " + cnt3("ratio-row") + " / 数据 " + all.length);
    t("折叠头不是指标行（不进 .ratio-value）",
      cnt3("ratio-value") === all.length,
      "渲染 " + cnt3("ratio-value") + " / 数据 " + all.length);
    /* 不许漏出原始键名。指标中文名的唯一来源是 dataLoader.js 的 RATIO_META
       （68 项逐条登记）—— D 的比值项**不带 name 字段**，查不到就退化成英文键。
       所以这里查的是「有没有 snake_case 键名漏出来」，不是「是不是全中文」：
       真数据里有一条叫「ROIC − WACC」，全大写缩写，是正经指标名。 */
    const rawKeys = a3.filter(x => x.classes.includes("ratio-label"))
      .map(x => x.text).filter(s => /^[a-z][a-z0-9_]*$/.test(s));
    t("指标名没有漏出原始键名", rawKeys.length === 0, rawKeys.join(","));

    /* 三层压成两层：分组卡并进维度块表头，独立的 .group-grid 不该再出现 */
    t("不再有独立分组卡（.group-grid / .group-card）",
      !has3("group-grid") && !has3("group-card"));
    t("每个维度块一个健康分布色条", cnt3("status-bar") === groups.length);
    t("每个维度块一句结论", cnt3("dim-meta") === groups.length);

    /* ---- 五块并排 ---- */
    /* 五块必须都挂在同一个栅格容器下，否则 CSS 的 .dim-grid 无从生效。
       这条在渲染树里就能验，不用等肉眼看版面。 */
    const grid3 = a3.filter(x => x.classes.includes("dim-grid"))[0];
    t("五块装进同一个并排栅格",
      !!grid3 && walk(grid3.el, []).filter(x => x.classes.includes("dim-block")).length === 5);

    /* 五块必须**等高**。维度之间指标条数不同（10/18/14/12/14），块高本来会差
       好几行，两块并排时看着参差不齐。靠 grid-auto-rows: 1fr + 默认 stretch
       解决，**不给表补空行**（补空行会被读成「数据缺失」）。
       渲染树里看不出 CSS，所以直接查样式表 —— 去掉注释再查，
       否则规则里的说明文字自己就把断言骗过去了。 */
    const dimGridRule = ((fs.readFileSync(path.join(ROOT, "css/layout.css"), "utf8"))
      .match(/\.dim-grid\s*\{([^}]*)\}/) || ["", ""])[1].replace(/\/\*[\s\S]*?\*\//g, "");
    t("五块等高（栅格行等高 + 撑满格子）",
      /grid-auto-rows:\s*1fr/.test(dimGridRule) && !/align-items:\s*start/.test(dimGridRule),
      dimGridRule.replace(/\s+/g, " ").trim());

    /* ---- 一行状态类：CSS 上色的挂钩，也是「哪几行要看」的落点 ---- */
    const byStatus = s => all.filter(x => x.item.status === s).length;
    t("每行都带状态类",
      cnt3("st-ok") + cnt3("st-not_evaluable") + cnt3("st-not_meaningful") === all.length,
      "实际 " + (cnt3("st-ok") + cnt3("st-not_evaluable") + cnt3("st-not_meaningful"))
        + " / 数据 " + all.length);
    t("待核验行的条数与数据一致",
      cnt3("st-not_evaluable") === byStatus("not_evaluable"),
      "渲染 " + cnt3("st-not_evaluable") + " / 数据 " + byStatus("not_evaluable"));
    t("不适用行的条数与数据一致",
      cnt3("st-not_meaningful") === byStatus("not_meaningful"),
      "渲染 " + cnt3("st-not_meaningful") + " / 数据 " + byStatus("not_meaningful"));

    /* 健康行**不涂**色 —— 对比才是指示，全都涂等于都没涂。
       这是 CSS 的约定，渲染树里看不出来，所以直接查样式表。 */
    /* ★ 这条曾经是红的：CSS 里写的是 .ratio-row.st-watch / .st-bad，
       而页面挂的类名是 st-not_evaluable —— 两边对不上，那道 2px 状态色
       一直是死的。断言的类名必须与 addRow() 里拼出来的**逐字相同**。 */
    const cssP3 = fs.readFileSync(path.join(ROOT, "css/components.css"), "utf8");
    t("样式表只给待核验行涂左边缘",
      /\.ratio-row\.st-not_evaluable\s/.test(cssP3)
        && !/\.ratio-row\.st-ok\s/.test(cssP3)
        && !/\.ratio-row\.st-good\s/.test(cssP3)
        && !/\.ratio-row\.st-not_meaningful\s/.test(cssP3));

    /* ---- 状态胶囊只在待核验时出现 ---- */
    /* D 没有「好/差」这一档。给 ok 挂一个「正常」胶囊等于给 68 行里的 35 行
       挂同一个标签 —— 挂满等于没挂。 */
    t("状态胶囊只挂在待核验行上",
      cnt3("status-chip") >= byStatus("not_evaluable")
        && a3.filter(x => x.classes.includes("status-chip") && x.text === "待核验")
             .length === byStatus("not_evaluable"),
      "待核验胶囊 " + a3.filter(x => x.classes.includes("status-chip") && x.text === "待核验").length
        + " / 数据 " + byStatus("not_evaluable"));

    /* ---- 展开行只给核心指标 ---- */
    /* 折叠组里的行不给展开行 —— 折叠本来就是「这些先不看」，
       再套一层展开，点起来的层级就乱了。 */
    t("展开行只给核心指标", cnt3("ratio-detail") === core.length,
      "渲染 " + cnt3("ratio-detail") + " / 核心 " + core.length);
    /* D 的比值项**没有 threshold 字段**，所以展开行里不再有「判断标准：」 */
    t("展开行不再写「判断标准」（D 不做阈值判断）",
      !a3.some(x => x.text.indexOf("判断标准：") === 0));
    t("展开行写了公式或明确说没有公式",
      a3.filter(x => x.classes.includes("ratio-detail"))
        .every(x => /计算公式：|该指标未提供公式|方向：/.test(x.all)));

    /* ---- 出处：D 现在真的给了两个 page ---- */
    t("带 page 的指标条数与数据一致",
      cnt3("ratio-src") === withPage.length,
      "渲染 " + cnt3("ratio-src") + " / 数据 " + withPage.length);
    t("页码链接与带 page 的指标一一对应",
      cnt3("page-link") === withPage.length);
    t("出处链接挂在指标名那一格（不是单开一列）",
      a3.filter(x => x.classes.includes("ratio-src"))
        .every(x => String(x.el.parentNode.className).indexOf("ratio-name") >= 0));

    /* 没 page 的项**整格不放**（不是写个破折号占位）—— 缺的是可选字段，
       不是缺口，不该在 66 行上各留一个空位把表撑难看。
       但也不许谎称齐全：D 只给了 2 项，页面不能让人以为这是全覆盖。 */
    const lacking = all.length - withPage.length;
    /* 每一处 .ratio-src（指标名下面那一行灰字）里都必须真的有个链接 ——
       也就是说，没 page 的项**根本没有这个元素**，而不是留一个空壳/破折号。
       （不能查 text 是否为空：DOM 桩的 textContent 不聚合子节点，
       有链接的那几处自己那格的文字也是空的。） */
    t("没 page 的项整格不放（不写空壳或破折号）",
      a3.filter(x => x.classes.includes("ratio-src"))
        .every(x => walk(x.el, []).some(y => y.classes.includes("page-link"))));
    t("没有谎称页码齐全",
      lacking === 0 || !pageText.p3.includes("全部可溯源"));

    /* ---- 已撤：雷达与 _score ---- */
    /* ratios.*._score 与雷达图（chart-box）是 C 那版契约的产物。
       D 的 ratios 里没有 _score，所以这一页不再有雷达，也不再打了分的
       维度表头 —— 缺的东西不留在页面上当空壳。 */
    t("已撤雷达图（chart-box 不再出现）", !has3("chart-box"));
    t("已撤维度得分（.dim-score / .dim-score-den）",
      !has3("dim-score") && !has3("dim-score-den"));
    t("不再声称得分由财务诊断模块给出（得分已不存在）",
      !pageText.p3.includes("由财务诊断模块给出"));

    /* 一句话结论：只报例外；全算得出来时报总数 */
    const metas = a3.filter(x => x.classes.includes("dim-meta")).map(x => x.text);
    t("结论只报待核验项数或说明全部算得出",
      metas.length === 5 && metas.every(m => /项指标(全部算得出|中 \d+ 项待核验)|暂无指标/.test(m)),
      metas.join(" | "));

    t("不含 undefined / NaN", !/undefined|NaN/.test(pageText.p3), pageText.p3.slice(0, 200));
  }
}

/* ==================================================================== */
/* 页面2 公司概览                                                        */
/* -------------------------------------------------------------------- */
/* ★ 本页已从「五块」缩到「三块」。代价写在 p2-overview.js 的头部注释里：
   business_mix（主营构成）、history（多期趋势）、company.business（一句话
   业务定位）这三样 A 都不产出，E 撤掉了消费它们的代码与样式。
   下面最后几条断言就是防止它们偷偷回来。 */
out.push("\n=== 页面2 公司概览 ===");
{
  const p2 = trees.p2;
  if (p2) {
    const a2 = walk(p2, []);
    const has2 = c => a2.some(x => x.classes.includes(c));
    const cnt2 = c => a2.filter(x => x.classes.includes(c)).length;

    const groups = D.financialGroups();
    const rows = groups.flatMap(g => g.items);
    const valued = rows.filter(r => F.fmt.toNum(r.item) !== null);
    const withPage = rows.filter(r => r.item && r.item.page !== null && r.item.page !== undefined);

    t("有公司抬头", has2("company-head") && has2("company-name-row"));
    t("三个核心大数", cnt2("metric-card") === 3, "实际 " + cnt2("metric-card"));
    t("抬头的 meta chip 来自 company 的实际字段",
      cnt2("meta-chip") > 0, "实际 " + cnt2("meta-chip"));

    /* ---- 主要财务数据：三块，不是一张平表 ---- */
    t("主要财务数据表已渲染", has2("fin-table"));
    t("科目行数与数据一致", cnt2("fin-row") === rows.length,
      "渲染 " + cnt2("fin-row") + " / 数据 " + rows.length);
    t("分成三块", cnt2("fin-block") === groups.length,
      "渲染 " + cnt2("fin-block") + " / 数据 " + groups.length);
    t("分组名就是报表名",
      groups.every(g => a2.some(x => x.text === g.label)),
      groups.map(g => g.label).join(","));
    t("每块都有块头（表名 + 头条科目）",
      cnt2("fin-block-head") === 3 && cnt2("fin-block-name") === 3 && cnt2("fin-block-flag") === 3);
    t("表内出处列每行一个", cnt2("col-source") === rows.length,
      "渲染 " + cnt2("col-source") + " / 数据 " + rows.length);

    /* ---- 本期 / 上期两列对照（2026-10-13 新增）----
       上期值来自 D 的 prior_value（经 dataLoader 打包成 r.prior）。
       ★ 这里刻意断言「两列的格子数一样」而不是断言某个具体数字：
       具体数字一换年报就假红，而「本期有 17 格、上期就得有 17 格」
       是版式不变式 —— 少一格就是列错位，跟数据内容无关。 */
    const priorRows = rows.filter(r => r.prior && r.prior.value !== null
      && r.prior.value !== undefined);
    t("上期列每行一个（本期有几行就有几格）",
      cnt2("fin-prior") === rows.length,
      "渲染 " + cnt2("fin-prior") + " / 数据 " + rows.length);
    t("上期列用的是 D 给的 prior_value，不是 E 自己找的",
      priorRows.length === rows.filter(r => r.item && r.item.prior_value !== undefined
        && r.item.prior_value !== null).length,
      "prior 打包 " + priorRows.length);
    /* 表头必须存在且是 5 格 —— 没有表头，两列数字一模一样，读者只能猜。 */
    t("财报表有表头行", cnt2("fin-head-row") === groups.length,
      "渲染 " + cnt2("fin-head-row") + " / 数据 " + groups.length);
    t("表头 5 格（科目/本期/上期/相对大小/出处）",
      a2.filter(x => x.classes.includes("fin-head-row"))
        .every(x => x.el.children.length === 5),
      a2.filter(x => x.classes.includes("fin-head-row"))
        .map(x => x.el.children.length).join(","));
    /* 期间从数据里读，**不在 JS 里写死 "2025" / "2024"** ——
       D 换一份年报，写死的年份会让整页说谎，而且不会报错。
       所以断言「表头里的年份 === 数据里的 period」，不是断言 "2025"。 */
    const someItem = rows.map(r => r.item).filter(x => x && x.period)[0];
    const headText = a2.filter(x => x.classes.includes("fin-head-row"))
      .map(x => x.all).join(" ");
    t("表头期间来自数据（本期 " + (someItem ? someItem.period : "?") + "）",
      !!someItem && headText.indexOf(someItem.period) >= 0, headText);

    /* ---- 报表自身的形状，三块各不一样 ---- */
    t("每块一行头条科目", cnt2("is-headline") === groups.length, "实际 " + cnt2("is-headline"));
    t("结论行分隔线", cnt2("is-gap") > 0, "实际 " + cnt2("is-gap"));
    t("有缩进的科目行", cnt2("indent-1") > 0, "实际 " + cnt2("indent-1"));
    t("科目行前缀（减：/ 其中：）", cnt2("fin-op") > 0, "实际 " + cnt2("fin-op"));

    /* ---- 比例条 ----
       .fin-track / .fin-bar 是共用组件。条长是**显示缩放**（按本表内最大科目
       等比），不是任何比率 —— 这句话必须留在页面上。 */
    const tracks = a2.filter(x => x.classes.includes("fin-track"));
    const barIn = x => String((x.el.children[0] || {}).className || "").split(/\s+/).includes("fin-bar");
    /* 数值取不到就不画条，不留一根空轨道（茅台没有商誉，那一行就是这样） */
    t("每行一条轨道", tracks.length === rows.length, "实际 " + tracks.length);
    t("取不到值的行不画条",
      tracks.filter(barIn).length === valued.length,
      "画了 " + tracks.filter(barIn).length + " 条 / 有值 " + valued.length + " 行");
    /* 现金流量表用零点线分流（三项净额），资本开支逐行覆写成普通幅度条 ——
       它是流出额、不是净额。这条断言防的就是「资本开支被画到零线右边」。 */
    const divN = groups.reduce((n, g) =>
      n + g.items.filter(r => (r.shape || g.shape) === "diverging" && F.fmt.toNum(r.item) !== null).length, 0);
    t("只有净额项分左右", cnt2("is-diverging") === divN,
      "渲染 " + cnt2("is-diverging") + " / 数据 " + divN);
    /* 负向条必须真的被标出来，否则「流向」就丢了 */
    t("负向的条被标记", cnt2("is-neg") === valued.filter(r => F.fmt.toNum(r.item) < 0).length,
      "渲染 " + cnt2("is-neg") + " / 数据 " + valued.filter(r => F.fmt.toNum(r.item) < 0).length);

    /* ★ 只查**真有条的**轨道。空轨道（取不到值的那几行）里没有 .fin-bar，
       children[0] 指的是同级的其它格，style.width 本来就是 undefined ——
       把它算进来，等于拿「没画条」去要求「条宽合法」。 */
    const widths = tracks.filter(barIn).map(x => (x.el.children[0] || {}).style || {});
    t("条宽都是合法百分比",
      widths.length > 0 && widths.every(w => /^\d+(\.\d+)?%$/.test(w.width || "")),
      widths.map(w => w.width).join(","));
    const divTracks = tracks.filter(x => x.classes.includes("is-diverging"));
    t("分流块的条不超过半边",
      divTracks.every(x => parseFloat((x.el.children[0] || {}).style.width) <= 50));
    t("普通块的条不超过整条",
      Math.max.apply(null, tracks.filter(x => !x.classes.includes("is-diverging"))
        .map(x => parseFloat(((x.el.children[0] || {}).style || {}).width) || 0)) <= 100);
    t("写明了条长不是比率",
      pageText.p2.includes("等比缩放") && pageText.p2.includes("不是任何比率"));

    /* 表里每一行都应能点开溯源 —— 这正是本页要讲的那句话。
       缺 page 的行渲染成灰破折号，**不编一个链接出来**。 */
    const finLinks = a2.filter(x => x.classes.includes("fin-row"))
      .filter(r => walk(r.el, []).some(y => y.classes.includes("page-link"))).length;
    t("每个有 page 的科目都能点开溯源",
      finLinks === withPage.length,
      "渲染 " + finLinks + " / 数据 " + withPage.length);

    /* ---- 金额刻度：亿元量级要带千分位，与页面 6 对齐 ---- */
    const rev = D.get("financials.revenue", null);
    if (rev && Number.isFinite(rev.value)) {
      const good = F.fmt.money({ value: rev.value, unit: rev.unit || "元" });
      t("页面上出现的营业收入与页面 6 同刻度（亿元 + 千分位）",
        pageText.p2.includes(good), "期望出现 " + good);
    }

    t("页面2 无涨跌配色（tone-*）",
      !a2.some(x => x.classes.some(c => c.indexOf("tone-") === 0)));
    t("已移除骨架自检卡片",
      !has2("kv-grid") && !pageText.p2.includes("骨架自检"));

    /* ---- 已撤：A 不产出的三块 ---- */
    t("已撤主营构成（business_mix）", !has2("ctx-row") && !has2("mix-row") && !has2("mix-source"));
    t("已撤多期趋势（history）", !has2("trend-series") && !has2("trend-row"));
    t("已撤一句话业务定位（company.business）", !has2("company-brief"));
    t("不含 undefined / NaN", !/undefined|NaN/.test(pageText.p2), pageText.p2.slice(0, 200));
  }
}

/* ==================================================================== */
/* 页面6 投研简报（读 D 的 memo.json 绑定表）                            */
/* -------------------------------------------------------------------- */
/* 这一页是**独立产物**：它读 data/real_memo.js（由 D 的 memo.json 包成 JS），
   统一数据对象到不到位都不影响它。E 在这里**不做任何数字格式化** ——
   D 已经把 168838102514.79 写成 "1,688.38 亿元" 了，E 再走一遍 fmt.money
   只会制造两处口径。E 也不连句，只排表格与键值条。 */
out.push("\n=== 页面6 投研简报 ===");
{
  const p6 = trees.p6;
  if (p6) {
    const a6 = walk(p6, []);
    const has6 = c => a6.some(x => x.classes.includes(c));
    const cnt6 = c => a6.filter(x => x.classes.includes(c)).length;

    const meta = D.memoMeta() || {};
    const cols = D.memoColumns() || [];

    t("本页读到了 memo 绑定表", D.hasMemo());
    t("有报告纸 .paper", has6("paper"));
    t("抬头是公司名 + 代码",
      a6.some(x => x.text.indexOf(meta.company_name) === 0
        && x.text.indexOf(meta.ticker) >= 0));
    t("抬头一行里有报告期 / 行业 / 币种 / 生成时间 / 渲染引擎",
      pageText.p6.includes(meta.generated_at)
        && pageText.p6.includes(meta.engine)
        && pageText.p6.includes("食品饮料"));

    /* ---- 七节：标题用 D 的 columns[] 原文，E 不自己起标题 ---- */
    const h2 = a6.filter(x => x.classes.includes("paper-h2")).map(x => x.text);
    t("七节标题与 D 的 columns[] 逐字相同",
      h2.length === 7 && h2.every((s, i) => s === cols[i]),
      "渲染 " + JSON.stringify(h2));

    /* D 自己的合规闸门结果必须顶在正文最上面 */
    const gate = D.memoValidation();
    if (gate) {
      t("数字校验结果渲染出来了",
        pageText.p6.includes(gate.allowedCount + " 项全部可溯源"));
    }

    /* ---- 落点：第一节三个大数 ---- */
    t("结论摘要三个大数", cnt6("ro-item") === 3, "实际 " + cnt6("ro-item"));
    t("大数值直接来自 D 的 formatted（E 不重排版数字）",
      a6.filter(x => x.classes.includes("ro-num")).every(y => y.text.length > 0),
      a6.filter(x => x.classes.includes("ro-num")).map(y => y.text).join(" | "));

    t("键值条 .v-target 已渲染", has6("v-target"));
    t("表 .mini-table 已渲染", cnt6("mini-table") >= 8, "实际 " + cnt6("mini-table"));
    t("风险卡与 D 的 risks 集合条数一致",
      cnt6("risk-card") === (D.memoCollection("risks") || []).length,
      "渲染 " + cnt6("risk-card") + " / 数据 " + (D.memoCollection("risks") || []).length);
    /* 风险卡的 severity 代码 D 没给（只有中文 severity_tag），卡片染色靠
       E 的反查表。这一条钉的是「反查表没失效」——重大那张必须是 sev-high。 */
    t("重大风险卡带 sev-high（反查表生效）",
      a6.filter(x => x.classes.includes("risk-card"))
        .some(x => x.classes.includes("sev-high")));
    /* 报告纸里的风险卡默认全展开 —— 打印时不该还要人去点 */
    t("报告纸里的风险卡默认全展开",
      a6.filter(x => x.classes.includes("risk-card"))
        .every(x => x.classes.includes("is-open")));
    /* 摊平是**调用点声明**的，不是 CSS 靠 .paper 后代选择器偷偷补的。
       这条同时钉住 JS（每张卡都带 is-flat）和 CSS（规则写在 .risk-card.is-flat 上）。 */
    t("报告纸里的风险卡都是摊平的",
      a6.filter(x => x.classes.includes("risk-card"))
        .every(x => x.classes.includes("is-flat")));

    /* ---- 版式定案：不嵌套玻璃 ----
       .paper 本身是强玻璃，**纸内**不再放 .card / .metric-card ——
       玻璃叠玻璃会互相取样。行内小构件一律走实底/底纹那一档。

       ★ 断言必须限定在 .paper **子树**内。p6 的「本页待实现」开发卡
       (specCard) 确实是 ui.card("dev-card")，但它按定案放在报告纸**外面** ——
       查整页会把这张合法的卡也算成违规。 */
    const paper = a6.filter(x => x.classes.includes("paper"))[0];
    const inPaper = paper ? walk(paper.el, []) : [];
    const glassInside = inPaper.filter(x =>
      x.classes.includes("card") || x.classes.includes("metric-card"));
    t("报告纸内不叠玻璃（纸外那张开发卡不算）",
      glassInside.length === 0,
      glassInside.map(x => x.el.className).join(" | "));
    t("开发卡确实在报告纸外",
      a6.some(x => x.classes.includes("dev-card") && inPaper.indexOf(x) < 0));

    /* 缺值不涂色、不改文案 —— D 把缺失写成「数据缺失」，本页照原样显示，
       只挂 .dim 让它退后。 */
    const missCells = a6.filter(x => x.text === "数据缺失");
    t("D 的缺失标记照原样保留，只降视觉权重",
      missCells.every(x => x.classes.includes("dim")),
      missCells.map(x => x.el.className).join(" | "));

    t("不含 undefined / NaN", !/undefined|NaN/.test(pageText.p6), pageText.p6.slice(0, 200));
  }
}

/* ==================================================================== */
/* 降级路径                                                              */
/* -------------------------------------------------------------------- */
/* 下面几段都靠临时 load() 一份改动过的数据来走分支，每条跑完立刻还原。   */
/* 放在文件最后，是因为后面的断言都依赖原始数据。                          */
const ORIG_DATA = JSON.parse(JSON.stringify(sandbox.FINSCOPE_DATA));
const ORIG_MEMO = JSON.parse(JSON.stringify(sandbox.FINSCOPE_MEMO));

function withData(id, mutate, memo) {
  const d = JSON.parse(JSON.stringify(ORIG_DATA));
  mutate(d);
  F.data.load(d, memo === undefined ? ORIG_MEMO : memo);
  const root = new El("div");
  let err = null;
  try { F.pages[id].render(root); } catch (e) { err = e.message; }
  F.data.load(ORIG_DATA, ORIG_MEMO);       /* 立刻还原 */
  const a = err ? [] : walk(root, []);
  return {
    err: err,
    text: err ? "" : deepText(root),
    has: c => a.some(x => x.classes.includes(c)),
    count: c => a.filter(x => x.classes.includes(c)).length,
    all: c => a.filter(x => x.classes.includes(c)).map(x => x.all),
    rows: pred => a.filter(x => x.classes.includes("fin-row") && (!pred || pred(x))),
    /* 裸的渲染树节点表。上面几个助手都是按类名过滤好的视图，
       碰上「要看某个元素**子元素有几个**」这类结构性问题时不够用 ——
       比如表头行是 4 格还是 5 格。 */
    nodes: a
  };
}

/* ---- 页面5：两法缺一 / 都缺 / 单位不一致 / 缺单位 ---- */
out.push("\n=== 页面5 降级路径（临时换数据，跑完还原）===");

/* ① 只有 Comps —— 中期汇报最可能的形态 */
let g = withData("p5", d => { delete d.valuation.dcf; });
t("只有 Comps 时不崩", !g.err, g.err);
t("只有 Comps 时标尺只画一行", g.count("vr-row") === 1, "实际 " + g.count("vr-row"));
t("只有 Comps 时不画重叠段", !g.has("vr-band"));
t("只有 Comps 时说明这是预期内的常态", /只有一种方法/.test(g.text));

/* ② 只有 DCF */
g = withData("p5", d => { delete d.valuation.comps; });
t("只有 DCF 时不崩", !g.err, g.err);
t("只有 DCF 时标尺只画一行", g.count("vr-row") === 1, "实际 " + g.count("vr-row"));

/* ③ 两法都缺 —— 只能有一个空状态，不能又出图又出空卡 */
g = withData("p5", d => { delete d.valuation; });
t("两法都缺时不崩", !g.err, g.err);
/* 整块 valuation 都没了（normalize 会把它补成 {}，所以走的是「空壳」这一支），
   页面该只留**一个**空状态。 */
t("两法都缺时只留一个空状态", /估值块未提供/.test(g.text), g.text.slice(0, 120));
t("两法都缺时不铺标尺骨架", !g.has("vr") && !g.count("vr-row"));
t("两法都缺时不铺两栏骨架", !g.has("two-col"));

/* ④ 两法单位不一致 —— 硬画等于把两把不同刻度的尺子叠在一起 */
g = withData("p5", d => { d.valuation.dcf.valuation_range.currency = "亿元"; });
t("单位不一致时不画标尺", !g.has("vr"), "标尺不该出现");
t("单位不一致时明说是单位问题", /单位不一致/.test(g.text));
t("单位不一致时两条区间仍并列给出",
  new RegExp("1,?267").test(g.text) || /1267/.test(g.text));

/* ⑤ 单位缺失 —— 绝不能静默按「元/股」处理 */
g = withData("p5", d => {
  delete d.valuation.comps.valuation_range.currency;
  delete d.valuation.dcf.valuation_range.currency;
});
t("缺 unit 时显式警告，不静默兜底", /currency\s*缺失|缺失/.test(g.text));
t("缺 unit 时标尺仍能画", g.has("vr"));
/* ★ .vr-unit 是**常驻**的：有单位就写单位，没单位写「未标注」——
   所以不能查「元素在不在」，要查它**写的是什么**。
   若哪天真按「元/股」兜底，刻度尺就成了一把说谎的尺子。 */
/* 只查**单位那半句**。同一行末尾还有「竖线＝现价 1,263.00 元/股」——
   那个「元/股」是从 market_data.price 来的、是**对的**，不该被这条牵连。 */
t("缺 unit 时刻度不谎称「元/股」",
  g.all("vr-unit").length > 0
    && g.all("vr-unit").every(s => /单位：未标注/.test(s) && !/单位：元/.test(s)),
  g.all("vr-unit").join(" | "));

/* ⑥ 两法区间不重叠 —— 那是个结论，不是错误 */
g = withData("p5", d => {
  d.valuation.dcf.valuation_range = { low: 8, mid: 9, high: 11, currency: "元/股" };
});
t("不重叠时不画 band", !g.has("vr-band"));
t("不重叠时明说分歧本身是个发现", /不重叠/.test(g.text));
t("不重叠时标尺照画", g.count("vr-row") === 2);

/* ⑦ low > high（数据写反） —— 照样画，但要报出来 */
g = withData("p5", d => {
  d.valuation.comps.valuation_range = { low: 24654.14, mid: 2000, high: 413.91, currency: "元/股" };
});
t("low > high 时不崩", !g.err, g.err);
t("low > high 时照样画标尺", g.count("vr-row") === 2);
t("low > high 时提示核对原始数据", /low 大于 high/.test(g.text));

/* ⑧ 区间缺 high —— 那一条落选，其余照画 */
g = withData("p5", d => { delete d.valuation.comps.valuation_range.high; });
t("缺 high 的那条落选，另一条照画", g.count("vr-row") === 1, "实际 " + g.count("vr-row"));
t("缺 high 时说明是哪一条画不了", /缺 low \/ high/.test(g.text));

/* ⑨ D 连 current_price 都没给 —— 竖线不画，但标尺照画 */
g = withData("p5", d => {
  delete d.valuation.blended.current_price;
  delete d.valuation.market_data;
});
t("没有现价时不崩，也不硬编一条竖线",
  !g.err && g.count("vr-priceline") === 0, g.err || ("竖线 " + g.count("vr-priceline")));
t("没有现价时标尺照画", g.count("vr-row") === 2);

/* ---- 页面6：memo 绑定表缺席 ---- */
out.push("\n=== 页面6 memo 缺席（临时换数据，跑完还原）===");
g = withData("p6", d => d, null);
t("memo 缺席时不崩", !g.err, g.err);
t("memo 缺席时留一张空报告纸", g.has("paper") && g.has("paper-empty"));
t("memo 缺席时说清楚等的是什么文件", /memo\.json/.test(g.text));
t("memo 缺席时不摆七节骨架", g.count("paper-h2") === 0, "实际 " + g.count("paper-h2"));
t("memo 缺席时开发卡照在", g.has("dev-card"));

/* ---- 页面3：B 补 page 之后自动生效 ---- */
out.push("\n=== 页面3 补 page 之后自动生效（临时换数据，跑完还原）===");

/* 真数据里已经有 2 项带 page（现金流质量的 ocf 与 capex），
   所以这里的期望值一律从数据推导，不写死。 */
const p3All = D.ratioGroups().flatMap(gr => D.ratioItems(gr.key));
const p3HasPage = p3All.filter(x => x.page !== null && x.page !== undefined).length;

g = withData("p3", d => {
  Object.keys(d.ratios).forEach(k => {
    if (k.charAt(0) === "_") return;
    Object.keys(d.ratios[k]).forEach(m => {
      if (m.charAt(0) === "_") return;
      d.ratios[k][m].page = 85;
    });
  });
});
t("补 page 后不崩", !g.err, g.err);
t("补 page 后每一行都能点开",
  g.count("ratio-src") === p3All.length && g.count("page-link") === p3All.length,
  "渲染 " + g.count("ratio-src") + " / 数据 " + p3All.length);
t("补 page 后不留多余的提示条",
  !/还有 \d+ 项/.test(g.text) && !/还没有 page/.test(g.text));

/* 只补一部分：最容易真实发生的情况（D 补到一半）。
   ★ 这里**不报「还差 N 项」**，是定案不是漏做：page 是**可选字段**，
   缺的是「这一项不对应某一页」（比率由几个科目算出），不是缺口。
   在 66 行上各挂一句提醒，等于把「正常」说成「缺陷」。
   要钉的是另外两件事：补上的真出链接、没补的整格不放（不写破折号占位）。 */
g = withData("p3", d => { d.ratios.growth.revenue_growth_yoy.page = 85; });
t("部分补 page：已补的行出链接",
  g.count("ratio-src") === p3HasPage + 1,
  "渲染 " + g.count("ratio-src") + " / 期望 " + (p3HasPage + 1));
t("部分补 page：不把缺 page 说成缺口",
  !/还有 \d+ 项|还差 \d+ 项/.test(g.text));

/* 分组整个缺掉 —— 五块变四块，不崩，不留空壳 */
g = withData("p3", d => { delete d.ratios.solvency; });
t("缺一个分组时不崩", !g.err, g.err);
t("缺一个分组时那块整块不出现", g.count("dim-block") === 4, "实际 " + g.count("dim-block"));

/* ratios 整个缺掉 —— 一个空状态，不是五张空卡 */
g = withData("p3", d => { delete d.ratios; });
t("ratios 全缺时不崩", !g.err, g.err);
t("ratios 全缺时不留五个空维度块", g.count("dim-block") === 0, "实际 " + g.count("dim-block"));

/* ---- 页面2：财报块缺掉 ---- */
out.push("\n=== 页面2 降级路径（临时换数据，跑完还原）===");

/* ① 财务表整个缺 —— 公司抬头与三个大数照常，不崩、不留空壳 */
g = withData("p2", d => { delete d.financials; });
t("financials 全缺时不崩", !g.err, g.err);
t("financials 全缺时不留三张空表", g.count("fin-block") === 0, "实际 " + g.count("fin-block"));
t("financials 全缺时公司抬头照常", g.has("company-head") && g.has("company-name-row"));
t("financials 全缺时不含 undefined / NaN", !/undefined|NaN/.test(g.text));

/* ② 只缺一张表 —— 另外两张照画。
   ★ financials 是**扁平表**（键=科目名：revenue / cfo / capex …），三张报表由
   dataLoader 的 FINANCIAL_BOOK 现组，某块一行都取不到就整块不出现。
   所以「删掉一张表」= 删掉那块名下的**全部科目**，不是删一个叫
   income_statement 的对象（那个键根本不存在，删了等于没删 —— 这个坑我踩过）。 */
g = withData("p2", d => {
  ["cfo", "cfi", "cff", "capex", "net_change_in_cash", "ending_cash"].forEach(k => {
    delete d.financials[k];
  });
});
t("缺一张表时不崩", !g.err, g.err);
t("缺一张表时剩下的照画", g.count("fin-block") === 2, "实际 " + g.count("fin-block"));

/* ③ 某一行**抽取失败**（不是「不适用」）—— 那一行不画条，但行还在，值是破折号。
   ★ 这一条与下面 ③b 是**成对的**，别把两件事并成一件：
       value === null 且 status 不是 not_applicable → 照画，破折号（上游没抽到，要修）；
       status === "not_applicable"                  → 整行不画（这家公司没这一项）。
   两件事长得像，判据完全不同，而且**只能按 status 判**。
   哪天有人「顺手」把它改成按 value 判，这两条会同时红。

   ⚠️ 这条断言原来写的是 `g.has("dim")`，看着过了、其实**测错了东西**：
   `.dim` 在值那一格只在 `status !== "found"` 时才挂，而真数据里**只有商誉**
   （not_applicable）满足 —— 所以它一直在验商誉，根本没验 revenue。
   商誉一删，它立刻红，露的就是这个。现在改成按科目名把那一行找出来。 */
g = withData("p2", d => { d.financials.revenue.value = null; });
t("缺值的行仍在表里", g.count("fin-row") === 16, "实际 " + g.count("fin-row"));
const revRow = g.rows(r => /营业收入/.test(r.all));
t("缺值的行按科目名还找得到", revRow.length, 1);
t("缺值的行值是破折号", revRow.length > 0 && /—/.test(revRow[0].all),
  revRow.length ? revRow[0].all : "(没找到行)");
t("缺值的行不画条",
  g.count("fin-track") === 16 && g.count("fin-track") - g.count("fin-bar") === 1,
  "轨道 " + g.count("fin-track") + " 条 " + g.count("fin-bar"));

/* ③b 不适用（not_applicable）—— 整行不画。
   真例：茅台没有商誉，D 给的是 { value: null, status: "not_applicable", page: 57 }。
   ★ 注意这条**不是**「缺数据留白」的反例：不适用不是缺数据，
     是「年报的资产负债表上本来就没有这一行」，删掉才是忠于年报。 */
g = withData("p2", d => {});
t("真数据：不适用的一整行不画（茅台没有商誉）",
  !g.rows().some(r => /商誉/.test(r.all)), "商誉行还在");
t("真数据：财报表 16 行（17 个科目 − 1 个不适用）",
  g.count("fin-row") === 16, "实际 " + g.count("fin-row"));
t("不适用时不留「（不适用）」这种半截行", !/不适用/.test(g.text));
/* 兜底组不能按「词汇表没登记」把它重新收编 —— 判的是它有没有真的消失 */
g = withData("p2", d => { d.financials.revenue.status = "not_applicable"; });
t("换成别的科目同样成立（不是给商誉开的特例）",
  !g.rows().some(r => /营业收入/.test(r.all)), "营业收入行还在");
t("不适用时总行数跟着少", g.count("fin-row") === 15, "实际 " + g.count("fin-row"));

/* ④ 财报行缺 page —— 那一格给灰破折号，不编链接 */
g = withData("p2", d => {
  Object.keys(d.financials).forEach(k => {
    if (d.financials[k] && typeof d.financials[k] === "object" && "page" in d.financials[k]) {
      d.financials[k].page = null;
    }
  });
});
/* ★ 只数**财报表行内**的链接。页面 2 顶上的三个大数卡（metric-card）自己也带
   page-link（那三处指向的是别的东西），数整页会把它们一起算进来。 */
const finRowLinks = g.rows(r => walk(r.el, []).some(y => y.classes.includes("page-link"))).length;
t("缺 page 时财报表里不编链接", finRowLinks === 0, "实际 " + finRowLinks);
t("缺 page 时那一格仍是灰破折号", g.count("col-source") === 16);

/* ⑤ 上期值整块缺席 —— 退成四列，**不画一列 17 行破折号的空壳**。
   这是新增列时最容易忘的那条：列本身是 E 加的，但值不是 E 给的，
   所以「上游没给」必须是页面上的一个正经分支，不是一条被忽略的路径。 */
g = withData("p2", d => {
  Object.keys(d.financials).forEach(k => {
    const it = d.financials[k];
    if (it && typeof it === "object") { delete it.prior_value; delete it.prior_period; }
  });
});
t("上期整块缺席时不崩", !g.err, g.err);
t("上期整块缺席时整列不画", g.count("fin-prior") === 0, "实际 " + g.count("fin-prior"));
/* 表头也得跟着退 —— 只退数据格不退表头的话，会剩一个写着「上期（2024）」
   的表头横在全是对不上的四列上。表头格数必须**等于**该表实际的列数。 */
const head4 = g.nodes.filter(x => x.classes.includes("fin-head-row"));
t("上期整块缺席时表头跟着退回四格",
  head4.length > 0 && head4.every(x => x.el.children.length === 4),
  "表头格数 " + head4.map(x => x.el.children.length).join(","));
t("上期整块缺席时科目行一格不少", g.count("fin-row") === 16, "实际 " + g.count("fin-row"));

/* ⑥ company 缺 —— 抬头退化成空状态，不崩 */
g = withData("p2", d => { delete d.company; });
t("company 缺时不崩", !g.err, g.err);
t("company 缺时不含 undefined / NaN", !/undefined|NaN/.test(g.text));

/* ==================================================================== */
/* 回归：空类名不能进 classList（2026-10-13 页面 2 白屏）                */
/* -------------------------------------------------------------------- */
/* 报错原话：Failed to execute 'add' on 'DOMTokenList':
   The token provided must not be empty.

   起因是 p2 的指标卡写 `classList.add(fmt.statusClass(item.status))`，
   而 statusClass 对「不需要上色」的那几档（ok / found / not_applicable /
   not_meaningful）返回的正是**空串** —— 真数据里 ok 有 35 项、found 有 16 项，
   所以这一页是必挂的，不是偶发。

   **它逃过 387 条断言的唯一原因，是测试桩当时把空串静默吞掉了。**
   所以这一节有两半：一半钉住映射函数会返回空串（这是**有意的**，
   空串 = 「不上色」这个信号不能丢），一半钉住渲染路径即使拿到空串也不炸。
   真正堵住这个洞的是桩里新加的 checkToken()（见文件开头 El 的注释）。 */
out.push("\n=== 回归：空类名不能进 classList ===");
{
  /* ① 映射函数在「不上色」那几档上返回空串 —— 这是约定，不是 bug */
  ["ok", "found", "not_applicable", "not_meaningful"].forEach(s => {
    t("statusClass(" + s + ") 返回空串（= 不上色）", F.fmt.statusClass(s) === "", F.fmt.statusClass(s));
  });
  t("statusClass(not_evaluable) 仍要上色", F.fmt.statusClass("not_evaluable") === "is-watch");
  t("severityClass 对未映射等级返回空串", F.fmt.severityClass("nonsense") === "");

  /* ② 真浏览器里 classList.add("") 是**抛异常**，不是无操作 —— 桩必须照做。
     这条拿桩自己试，就是在验「桩的保真度」：把桩改回宽松，它会立刻红。 */
  let threw = false;
  try { documentStub.createElement("div").classList.add(""); }
  catch (e) { threw = true; }
  t("桩的 classList.add('') 会抛异常（与浏览器一致）", threw);

  /* ③ 端到端：把指标卡的 status 逐个换成会返回空串的那几档，页面都不能崩。
     这条才是当初该拦住白屏的那条。 */
  ["ok", "found", "not_applicable", "not_meaningful", "not_evaluable"].forEach(s => {
    const gg = withData("p2", d => {
      Object.keys(d.ratios || {}).forEach(grp => {
        Object.keys(d.ratios[grp] || {}).forEach(k => {
          if (d.ratios[grp][k] && d.ratios[grp][k].status !== undefined) d.ratios[grp][k].status = s;
        });
      });
    });
    t("p2 全部指标 status=" + s + " 时不崩", !gg.err, gg.err);
  });
}

/* ==================================================================== */
/* 全站零 canvas（2026-10-13 撤 Chart.js）                               */
/* -------------------------------------------------------------------- */
/* 撤掉 vendor/chart.umd.min.js + js/charts.js 之后，「六个页面一张 canvas
   都不依赖」从一句观察变成了**结构性事实**。这几条把它钉住：
   谁哪天偷偷加回一个 <canvas>，在这里就会响，而不是等到演示现场
   发现图表画不出来（演示脚本的翻车预案里专门写了这一条）。 */
out.push("\n=== 全站零 canvas ===");
{
  const allNodes = ORDER.flatMap(id => trees[id] ? walk(trees[id], []) : []);
  const canvases = allNodes.filter(x => x.tagName === "CANVAS");
  t("六个页面共 0 个 <canvas>", canvases.length === 0,
    canvases.map(x => x.el.className || "(无类名)").join(" | "));
  t("六个页面不含任何图表降级文字",
    !allNodes.some(x => /图表库未加载|Chart\.js/.test(x.text)));
}

/* index.html 不能再引那两个已经删掉的文件。
   文件删了但 <script> 还留着，浏览器只会静默 404 —— 页面照跑，
   控制台一条红。这种「删了一半」最容易蒙混过关，所以直接读源文本。

   ★ 读之前**必须剥掉 HTML 注释** —— 和下面读 CSS 时那条「读之前必须剥注释」
   是同一个坑：这两处撤除都在原地留了墓碑注释，里面正写着
   `vendor/chart.umd.min.js` 和 `js/charts.js` 这两个路径。不剥的话，
   一条记录「这里撤掉了什么」的注释会把断言自己判红。 */
const htmlSrc = fs.readFileSync(path.join(ROOT, "index.html"), "utf8")
  .replace(/<!--[\s\S]*?-->/g, "");
t("index.html 不再引 Chart.js", !/vendor\/chart/.test(htmlSrc),
  (htmlSrc.match(/[^\n]*vendor\/chart[^\n]*/) || [""])[0]);
t("index.html 不再引 js/charts.js", !/js\/charts\.js/.test(htmlSrc),
  (htmlSrc.match(/[^\n]*charts\.js[^\n]*/) || [""])[0]);

const chartCss = cssOf("css/components.css");
const baseCssSrc = cssOf("css/base.css");
t("组件样式里没有孤立的 .chart-box / .chart-fallback",
  !/\.chart-(box|fallback)\s*\{/.test(chartCss));
t("base.css 不再给 canvas 写重置", !/(^|\})\s*canvas\s*\{/.test(baseCssSrc));

/* ==================================================================== */
/* 配色与毛玻璃的样式表守卫                                              */
/* -------------------------------------------------------------------- */
/* 颜色全在 CSS 里，渲染树（DOM 桩）看不见 —— 所以这几条直接读 CSS 文本。
   读之前**必须剥注释**：本项目注释里写满了设计理由，里面就有一堆
   色值和令牌名，不剥的话断言会被注释自己骗过去（这个坑前面踩过）。 */
out.push("\n=== 配色与毛玻璃的样式表守卫 ===");

function cssOf(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
}
const baseCss = cssOf("css/base.css");
const compCss = cssOf("css/components.css");

/* ★ 2026-10-13 第十轮修：**抽令牌之前先把注释剥掉。**
   踩到的坑：base.css 的注释里有一句
       「接替原来的 --c-watch: #c9922f（黄）。」
   它长得和一条真声明一模一样，于是下面那条正则把**注释里的退役值**
   当成了 `--c-watch` 的第一条匹配，find() 取第一条 ⇒ 拿到 #c9922f。
   后果很具体：第九轮那条「同色相 + 对比 ≥ 4.5」的守卫，
   两个数（4.41:1 / hover 3.92:1）全是按 #c9922f 算的 ——
   连它自己的门槛都够不着。**一个读错值的守卫比没有守卫更糟**，
   它给的是假的安全感。剥注释只影响抽令牌这条路（rootBody / colorDecls），
   上面 baseCss / compCss 的原文引用一律不动，别的断言不受影响。 */
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "");

/* ① 没有任何两个**含义不同**的颜色令牌同值。
   这条守的是 2026-10-12 删掉 --c-accent 的那个坑：它当时与 --c-watch 同值，
   于是「名字写着强调、实际是需关注」，页面 6 的目标价被涂成了需关注色。
   同值的两个令牌 ≈ 同一个颜色戴两顶帽子，读代码的人一定会搞混。

   ★ 例外（有意的同值，不是漏网）：
     · --c-up / --c-down —— tone 系统**故意**镜像 status 的红与绿。
       A 股惯例红涨绿跌，红绿就是红绿，另挑两个色号反而会让
       「上涨」和「好」看起来是两种不同性质的东西。约定见 base.css 顶部。
     · --c-on-primary —— 它和 --c-surface 都是纯白。白就是白，
       没有第二种白；而且这两个是「面」和「面上的字」，角色差得远。
   除了这几个，任何两个令牌同值都该被拦下来问一句。 */
const SAME_OK = new Set(["--c-up", "--c-down", "--c-on-primary"]);
const rootBody = (stripComments(baseCss).match(/:root\s*\{([\s\S]*?)\}/) || ["", ""])[1];
const colorDecls = [...rootBody.matchAll(/(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))/g)]
  .map(m => [m[1], m[2].replace(/\s+/g, "").toLowerCase()])
  .filter(([name]) => !SAME_OK.has(name));
const dupGroups = {};
colorDecls.forEach(([name, val]) => (dupGroups[val] = dupGroups[val] || []).push(name));
const dups = Object.entries(dupGroups).filter(([, names]) => names.length > 1);
t("没有任何两个含义不同的颜色令牌同值",
  colorDecls.length > 0 && dups.length === 0,
  "重复：" + dups.map(([v, n]) => v + " = " + n.join(" / ")).join("；"));

/* ② 橙只有一个入口：--c-watch* 家族，且 --c-accent 不许复活。
   ★ 2026-10-12 第四轮：家族从 3 个扩到 5 个。
     起因 —— 风险卡改成按 severity 铺红/橙/绿透明渐变，橙需要两个渐变端点
     （--c-watch-bg-2 / -3），和红早就有的 --c-bad-bg-2 / -3 对齐。
     这个断言本来就是**绊线**：令牌数一变就该红一次，逼人确认一次
     「是不是又冒出第二个橙了」。确认结论：新增的两个和 --c-watch
     **同一个色相、只差透明度**，没有引入第二种橙，--c-accent 仍然不存在。
     所以放行，并把数从 3 改成 5。

     顺手把它改**严**了：原来只数个数，拦不住「把其中一个换成另一种橙」。
     现在额外把三个**角色名**钉死（填充 / 写字 / 底纹），改名要过这一条。
     渐变端点没进角色名清单 —— 它们是 -bg 的变体，属于实现细节。

   ★ 2026-10-13 第九轮（已被第十轮撤回）：家族一度从 5 个扩到 6 个 ——
     新增 --c-watch-on（橙面上的字，同色相深档）。第十轮她把橙面上的字
     改成**白**，白不需要新令牌（--c-on-primary 本来就是干这个的），
     那个专用令牌随即没有用户，于是删掉、家族**回到 5 个**、角色名回到三个。
     记这一笔是为了：下次再有人想给橙加第四个颜色档时，先看到这里。 */
const watchNames = colorDecls.filter(([n]) => /^--c-watch/.test(n)).map(([n]) => n);
const WATCH_ROLES = ["--c-watch", "--c-watch-ink", "--c-watch-bg"];
t("橙的令牌是 --c-watch 家族 5 个，且三个角色名都在",
  watchNames.length === 5
    && WATCH_ROLES.every((n) => watchNames.indexOf(n) >= 0)
    && !/--c-accent/.test(rootBody),
  "watch 系 " + watchNames.join(","));

/* ②a 橙面上的字：第十轮定案「用白」，这条钉的不是对比度，是**取舍本身**。
     ★ 为什么不钉「对比 ≥ 4.5」：白 on #fa9205 实测只有 **2.29:1**，
       本来就够不着（§2c 有实测）。硬钉 4.5 只会让它永远红，
       而它红的原因不是代码坏了，是**取舍** —— 一个永远红的守卫比没有守卫更糟，
       人很快就开始无视它。
     ★ 所以改钉两件事，各有各的对手：
       ① 三处橙面的字必须都写 `color: var(--c-on-primary)`。
          对手是**半截改法**：只把其中一处改回深色，同一张脸就出现两种字
          （第九轮的原话就是「三处橙面必须同时改，否则同一张脸两种字」）。
       ② `--c-watch` 必须仍是 **#fa9205**（她第七轮指定的值）。
          对手是**为了凑对比去压深橙面**：想让白字达 AA 只有这一条路 ——
          橙的相对亮度得 ≤ 0.183，那得到的是 #b35f00 这一带的**褐色**
          （+白 = 4.61:1，确实达标），代价是「按钮橙」和「色条橙」裂成两种，
          而那正是她第六轮亲口否过的。实机对照见 E_PAGE_SPEC.md §2c。
     实测的那个数写进消息里 —— 它一变，说明有人动过色号，断言跟着红。 */
function toRGB(h) {
  h = h.replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
function relLum(h) {
  const [r, g, b] = toRGB(h).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a, b) {
  const la = relLum(a), lb = relLum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}
/* --c-on-primary 在 SAME_OK 里，被 colorDecls 过滤掉了，所以这里单独取。 */
const tokAll = (n) => {
  const m = rootBody.match(new RegExp(n + "\\s*:\\s*(#[0-9a-fA-F]{3,8}|rgba?\\([^)]*\\))"));
  return m ? m[1].replace(/\s+/g, "").toLowerCase() : null;
};
(() => {
  const FACES = [".btn-primary", ".risk-card.sev-attention .sev-chip", ".status-chip.is-watch"];
  const badFace = FACES.filter((sel) => {
    const i = compCss.indexOf(sel + " {");
    if (i < 0) return true;                       /* 选择器被改名/删掉 */
    const body = compCss.slice(i, compCss.indexOf("}", i));
    return !/color:\s*var\(--c-on-primary\)/.test(body);
  });
  const face = tokAll("--c-watch"), onFace = tokAll("--c-on-primary");
  const ratio = (face && onFace) ? contrast(face, onFace) : 0;
  t("三处橙面的字都是白（--c-on-primary），橙面仍是 #fa9205（白字 2.29:1 是知情取舍）",
    badFace.length === 0 && face === "#fa9205" && onFace === "#ffffff" && ratio > 2.2,
    "橙面 " + face + " × 字 " + onFace + " = " + ratio.toFixed(2) + ":1"
      + (badFace.length ? "；没走白的：" + badFace.join(" / ") : ""));
})();

/* ②b 三个等级的渐变**浓度必须逐档一致**（2026-10-12 第四轮新增）。
     风险卡改成按 severity 上色之后，三级之间的唯一区别应该是**色相**。
     如果有人把橙的起点调到 0.28、红的留在 0.20，读者就会以为
     「需关注」比「高风险」更严重 —— 颜色的浓淡天然被读成轻重。
     色相可以不同，浓度必须对齐。这条断言只有三行，但拦的是
     「改一个色号顺手也调了浓度」这种最难靠肉眼发现的漂移。 */
const alphaOf = (v) => parseFloat((String(v).match(/rgba\([^)]*,\s*([\d.]+)\)/) || [, "1"])[1]);
const at = (name) => alphaOf((colorDecls.find(([n]) => n === name) || [, ""])[1]);
const ramp = (base) => [at(base + "-2"), at(base + "-3")];
const rBad = ramp("--c-bad-bg"), rWatch = ramp("--c-watch-bg"), rGood = ramp("--c-good-bg");
t("红/橙/绿三级渐变的浓度逐档一致",
  rBad[0] > 0 && rBad[0] === rWatch[0] && rWatch[0] === rGood[0]
    && rBad[1] === rWatch[1] && rWatch[1] === rGood[1],
  "起点 " + rBad[0] + "/" + rWatch[0] + "/" + rGood[0]
    + "；终点 " + rBad[1] + "/" + rWatch[1] + "/" + rGood[1] + "（红/橙/绿）");

/* ③ 比例条只用中性色。
   这是全站最容易「顺手改橙」的地方 —— 比例条是**中性的量**，不是预警。
   一页 17 根橙条会直接把「橙是稀缺信号」这条规矩废掉。 */
const barRule = (compCss.match(/\.fin-bar\s*\{([^}]*)\}/) || ["", ""])[1];
t("比例条只用中性色，不用 status / tone 任何一色",
  /--c-bar/.test(barRule) && !/--c-(good|watch|bad|up|down|accent)\b/.test(barRule),
  barRule.replace(/\s+/g, " ").trim());

/* ④ 卡片走玻璃：.card 必须同时有半透明白底和 backdrop-filter。
   只改 background 不加 blur（或反过来）都会让「毛玻璃」名不副实。 */
const cardRule = (compCss.match(/\.card\s*\{([^}]*)\}/) || ["", ""])[1];
t("卡片是玻璃（半透明白底 + backdrop-filter）",
  /background:\s*var\(--c-glass\)/.test(cardRule)
    && /backdrop-filter:\s*var\(--glass-blur\)/.test(cardRule),
  cardRule.replace(/\s+/g, " ").trim());

/* ⑤ 打印时玻璃必须落地成实底。
   少了这条，导出 PDF 会得到一片灰糊糊的卡片（纸上没有 backdrop 可透）。 */
const printBlock = (baseCss.match(/@media\s+print\s*\{([\s\S]*)\}/) || ["", ""])[1];
/* ⑤-1 摊平卡走**显式修饰类**，不许再用 `.paper .risk-card` 这种后代选择器。
   后代选择器把「卡片在哪」和「卡片长什么样」捆死了 —— 哪天把卡片挪出 .paper，
   样式静默失效，代码里没有任何一处会提示他，而页面上四张卡会连成一片没边界。
   ★ 这两条必须读**剥注释后**的 CSS：本项目注释里写满了「原来写的是 X」，
   不剥的话第二条会被注释里的那句旧写法自己判红。 */
t("摊平卡走显式类 .risk-card.is-flat",
  /\.risk-card\.is-flat\s*\{/.test(compCss));
t("不再用 .paper 后代选择器覆写风险卡",
  !/\.paper\s+\.risk-card\s*\{/.test(compCss));

t("打印时关掉 backdrop-filter",
  /backdrop-filter:\s*none\s*!important/.test(printBlock));
t("打印时保住了背景色（状态色条 / 橙的落点才打得出来）",
  /print-color-adjust:\s*exact/.test(printBlock));

console.log(out.join("\n"));
console.log(`\n通过 ${pass}/${total}`);
process.exit(pass === total ? 0 : 1);
