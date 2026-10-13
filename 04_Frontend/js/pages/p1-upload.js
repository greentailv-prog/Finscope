/* ============================================================================
 * p1-upload.js —— 页面1 上传年报 · 数据看板 · 年报问答
 * ----------------------------------------------------------------------------
 * 这三块拼在一页，是因为它们在流程上本来就是同一件事的三步：
 * 交进来一份年报 → 看它抽出了什么 → 追着问它。
 *
 *   ① 上传窗口 —— 真的能选、真的能拖、真的校验。
 *      **但不解析**。解析是 A（financial-extraction）的活，编排是 D 的
 *      orchestrator 的活，两者都要起本地服务；file:// 下的单文件页面
 *      既解不了 PDF，也没有后端可调。所以这一格做到哪一步、下一步缺谁，
 *      页面上写清楚，不留一个点不动的方块。
 *
 *   ② 数据看板 —— A 从 9 份年报里抽好的 17 个指标 × 9 家公司。
 *      数据直接读 A 的 window.FINSCOPE_METRICS，E 一个数都不重算。
 *      唯一动过的是**展示缩放**：A 的原始单位是元，这里 ÷1e8 折成亿元，
 *      系数与小数位都走 F.fmt，好让同一个数在页面 1 / 2 / 6 上长得一样。
 *
 *   ③ 年报问答 —— A 的检索内核（BM25 + 向量融合）。
 *      ★ 这一块是「A 的页面搬进了 E 的壳」，不是「E 重新实现了一遍问答」：
 *        tokenize.js / search.js / metrics.js / queries.js 全部原样搬运，
 *        sha256 存证见 a/README.md。
 *
 * ---- 三条一定要记住的 ----
 *
 *   · **17 MB 不能随页加载。** a/data/shard_*.js 合计 17 MB，
 *     所以 index.html 只引「引擎 + 看板 + 预设题」那一份（约 110 KB），
 *     分片等用户真点了哪一家才注入（loadShard）。首屏不受语料体积影响。
 *
 *   · **E 不算同比。** A 自己的看板有「同比」一列，那是 A 的 app.js 用
 *     pct(v25, v24) 现算的。E 不画这一列，改成把 series 里的
 *     2023 / 2024 / 2025 **三年原值**并列 —— 三年原值是 A 抽出来的数据，
 *     照搬不算重算；同比是增长率，那是 B 的成长性维度的活
 *     （见 README 的「E 的边界」）。
 *
 *   · **答案是抽出来的，不是生成的。** 页面上明写这一句。A 的做法是从
 *     命中的证据块里挑与问句词重叠最高的句子，逐句标页码 —— 不生成、
 *     不润色。E 跟着 A，也不加任何「总结一句」。
 * ==========================================================================*/

(function () {
  "use strict";
  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  var ui = null;                  // 延迟取，保证 app.js 已执行

  /* ==================================================================== */
  /* 常量与状态                                                            */
  /* ==================================================================== */

  var MAX_BYTES = 50 * 1024 * 1024;      // 与页面上写的「≤ 50 MB」一致

  /* A 的产物相对于**本页所在目录**的位置。
     index.html 与 _probe.html 都在 04_Frontend/ 根下，所以默认 "a/"。
     打包成 05_Output/Final.html 时目录层级变了，那里会用
     window.FINSCOPE_A_BASE 覆盖它 —— 而不是在这里写死一个绝对路径。 */
  function aBase() { return window.FINSCOPE_A_BASE || "a/"; }

  var prepared = Object.create(null);    // code -> FinSearch.prepare 过的分片
  var pending  = Object.create(null);    // code -> 正在加载的 Promise
  var shardErr = Object.create(null);    // code -> 失败原因（给 chip 显示用）
  var onScopeChange = null;              // 载入状态变了就喊一声，重画 chip 与范围行

  var current = null;                    // 看板当前公司 code
  var picked  = null;                    // 已通过校验的 File 对象
  var refs    = {};                      // 本页要反复改的节点

  /* ==================================================================== */
  /* 小工具                                                                */
  /* ==================================================================== */

  /* A 的指标值是**元**（metrics.js 里每条都有 unit: "元"，这就是原始计量单位）。
     这一列要显示亿元。元 → 亿元 是一次**展示缩放**，不是重算 ——
     值本身一个字节没动，只换了个读法。
     系数与小数位跟着 F.fmt.money 走（1e8、2 位），这样同一个数
     「168838102514.79」在页面 1 是 1,688.38、在页面 2 和页面 6 上也是 1,688.38。
     千分位也借 F.fmt.grouped —— 页面 6 早就是 1,688.38 带逗号的，
     这里不借就会变成 1688.38，同一个数在两页长两个样。 */
  function yi(v) {
    var n = F.fmt.toNum(v);
    if (n === null) return F.fmt.MISSING;
    var out = F.fmt.grouped(n / 1e8, 2);
    /* ★ -9.89 元 ÷ 1e8 再留两位 = "-0.00"。
       一个负数被四舍五入到零，那个负号是纯粹的假信息：它说「这里是负的」，
       而真实含义是「这里小得看不见」。格力 2023 那一格就是这么来的
       （A 的 series 里存的是 -9.89，那是个百分数不是金额，见 dataNotes 一节）。
       抹掉负号只是不再撒谎，值本身一个字没改。 */
    if (/^-0(\.0+)?$/.test(out)) out = out.slice(1);
    return out;
  }

  /* ==================================================================== */
  /* 数据存疑自查                                                          */
  /* -------------------------------------------------------------------- */
  /* 为什么页面 1 需要这个、别的页不需要：
     页面 2/6 的数走 D 的接口，D 的值 E 与它交叉核对过（见 dataNotes 的 16/16）。
     页面 1 这一整块走 A 的 metrics.js，而 A 的 series 里混进了**明显不是金额**的格子。
     举三个当场能复现的（raw_text 里就写着答案）：
       · 格力   revenue.series["2023"] = -9.89      ← 这是同比百分数 −9.89%
       · 海康   revenue.series["2023"] =  0.01      ← 同上，0.01 是占比
       · 茅台   cash.series = {2024: 19.84, 2025: 17.01}
                raw_text 是「货币资金 51,690,610,946.50 17.01 59,295,822,956.89 19.84」
                A 取走了 17.01 / 19.84（那两个是**占比**），把 516.9 亿漏在左边。
     E 的规矩是绝不重算、也绝不替 A 改数。所以这里的做法只有一条：
     **一个数都不动，只在它旁边说一句「这个我看着不对」** ——
     就像 A 给的 status 不适用/未找到一样，是「把数据里的话说出来」，不是替数据下结论。
     ★ 三个判据都只用 A **自己给的数**互相比，不引任何外部数据、不引常识估算：
       ① 同一行三年里，某年与其余年份的中位数差 100 倍以上；
       ② 某年的值换算成亿元会显示成 0.00，而这家公司总资产在 10 亿元以上
          （资产负债表科目不可能是「17 元」这种量级）；
       ③ 跨行恒等式：营业成本 > 营业收入，或总负债 > 总资产（同一年）。
     判据 ①③ 是纯比较，阈值只有 100 倍这一个；判据 ② 是最保守的一条，
     只在「资产负债表科目 + 公司规模 ≥10 亿 + 值 < 100 万元」三条同时成立时触发。
     **三个判据都只产出一个标记，不产出任何数值** —— 这是 E 能做的极限。 */

  var SUSPECT_MIN_YUAN = 1e6;      // 100 万元：小于它、又不是 0，就是量级不对
  var SUSPECT_SCALE_YUAN = 1e9;    // 10 亿元：公司规模下限，用来否掉「这家本来就很小」
  var SUSPECT_TIMES = 100;         // 同一年列内相差 100 倍

  /* 一行自己的三年：给一行找可疑的年份，返回 { "2023": "理由", ... } */
  function suspectYearsByMagnitude(series, totalAssets) {
    var out = {};
    var yrs = ["2023", "2024", "2025"];
    var vals = yrs.map(function (y) {
      var v = series ? F.fmt.toNum(series[y]) : null;
      return v;
    });
    var nz = vals.filter(function (v) { return v !== null && v !== 0; })
                 .map(function (v) { return Math.abs(v); })
                 .sort(function (a, b) { return a - b; });
    var med = nz.length ? nz[Math.floor(nz.length / 2)] : null;

    yrs.forEach(function (y, i) {
      var v = vals[i];
      if (v === null || v === 0) return;
      var a = Math.abs(v);
      if (med !== null && nz.length >= 2 && (a > med * SUSPECT_TIMES || a < med / SUSPECT_TIMES)) {
        out[y] = "与同一行其余年份相差 " + SUSPECT_TIMES + " 倍以上，量级不对";
        return;
      }
      /* 判据 ②：换算成亿元是 0.00，而这家公司是十亿量级 —— 多半是 A 把
         「占比」那一列当成了金额（茅台货币资金 17.01 就是这么来的）。 */
      if (a < SUSPECT_MIN_YUAN && totalAssets !== null && Math.abs(totalAssets) >= SUSPECT_SCALE_YUAN) {
        out[y] = "只有 " + a + " 元，对这家公司的体量来说量级不对";
      }
    });
    return out;
  }

  /* 跨行恒等式：一年一年地查。返回 { 年份: { 键: 理由 } } */
  function suspectByIdentity(fin) {
    var out = {}, rev = fin.revenue, cost = fin.operating_cost,
        ta = fin.total_assets, tl = fin.total_liabilities;
    if (!rev || !cost || !ta || !tl) return out;
    ["2023", "2024", "2025"].forEach(function (y) {
      function g(f) {
        var v = f.series ? F.fmt.toNum(f.series[y]) : null;
        if (v === null && y === "2025" && f.status === "found") v = F.fmt.toNum(f.value);
        return v;
      }
      var r = g(rev), c = g(cost), A = g(ta), L = g(tl);
      if (r !== null && c !== null && r > 0 && c > r) {
        out[y] = out[y] || {};
        out[y].operating_cost = "营业成本 " + yi(c) + " 高于营业收入 " + yi(r) + "（亿元）";
        out[y].revenue = out[y].revenue || "营业收入低于营业成本（亿元）";
      }
      if (A !== null && L !== null && A > 0 && L > A) {
        out[y] = out[y] || {};
        out[y].total_liabilities = "总负债 " + yi(L) + " 高于总资产 " + yi(A) + "（亿元）";
        out[y].total_assets = out[y].total_assets || "总资产低于总负债（亿元）";
      }
    });
    return out;
  }

  function manifest() { return window.FINSCOPE_MANIFEST || null; }
  function metricsAll() { return window.FINSCOPE_METRICS || null; }

  /* A 的产物在不在。不在就整块退化成一条说明，而不是抛异常白屏 ——
     index.html 少引一行 a/data/metrics.js，这一页该说「A 的数据没接上」，
     而不是留一片空白让人以为是 E 没做。 */
  function aReady() {
    return !!(window.FinSearch && window.FinTok &&
              window.FINSCOPE_MANIFEST && window.FINSCOPE_METRICS);
  }

  function findMeta(code) {
    var man = manifest();
    if (!man || !man.shards) return null;
    for (var i = 0; i < man.shards.length; i++) {
      if (man.shards[i].code === code) return man.shards[i];
    }
    return null;
  }

  function clear(n) { while (n && n.firstChild) n.removeChild(n.firstChild); }

  /* D 交付的那一家，取裸代码。
     ------------------------------------------------------------------------
     ★ 为什么是**读** D 的 ticker 而不是写死 "600519"：
       写死会把「D 哪天多交付一家、或换了一家」变成一处**沉默的失配** ——
       页面照常跑、链接照常在，只是指向了错的公司。读的话自动跟上。

     ★ 为什么要去掉后缀：D 的 company.ticker 形如 "600519.SH"，
       而 A 的 FINSCOPE_METRICS 用裸代码 "600519" 作键。两边不是同一个串，
       必须先归一才能比。 */
  function dCompanyCode() {
    var t = (F.data && F.data.get) ? F.data.get("company.ticker") : null;
    if (!t) return null;
    return String(t).split(".")[0];
  }

  function mib(bytes) { return (bytes / 1048576).toFixed(2) + " MB"; }

  /* ==================================================================== */
  /* 分片按需加载                                                          */
  /* ==================================================================== */

  /**
   * 注入一家公司的分片（1.2–2.2 MB），返回已 prepare 好的 shard。
   *
   * ★ 为什么是 document.createElement('script') 而不是 fetch：
   *   file:// 下 fetch 本地 .js 会被 CORS 拦掉，<script> 注入不受限。
   *   这正是 A 的原页面能在 file:// 下跑起来的原因（a/README.md ①）。
   *
   * ★ 为什么不让 app.js 直接 promise-cache 进 window.FINSCOPE_SHARDS 就完事：
   *   FinSearch.prepare() 会建词表与向量索引，那是 17 MB 里最贵的一步。
   *   每家只 prepare 一次，重问不重算 —— 所以这里另开一个 prepared 表，
   *   而不是每问一次就 prepare 一遍。
   */
  function loadShard(code) {
    if (prepared[code]) return Promise.resolve(prepared[code]);
    if (pending[code]) return pending[code];

    var meta = findMeta(code);
    if (!meta) return Promise.reject(new Error("a/data/manifest.js 里没有 " + code));

    var p = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = aBase() + "data/" + meta.file;
      s.onload = function () {
        var store = window.FINSCOPE_SHARDS || {};
        if (!store[code]) {
          /* 文件下下来了，但没有挂上 FINSCOPE_SHARDS —— 那是 a/search.js
             的 `global.FINSCOPE_SHARDS = global.FINSCOPE_SHARDS || {}` 没跑到，
             或者拿到的分片文件名对不上。这是**真故障**，不能吞掉。 */
          reject(new Error("分片已读入但没有挂上 window.FINSCOPE_SHARDS"));
          return;
        }
        prepared[code] = FinSearch.prepare(store[code]);
        resolve(prepared[code]);
      };
      s.onerror = function () { reject(new Error("分片文件读不到：" + meta.file)); };
      document.head.appendChild(s);
    });

    pending[code] = p.then(
      function (r) { delete pending[code]; delete shardErr[code]; if (onScopeChange) onScopeChange(); return r; },
      function (e) { delete pending[code]; shardErr[code] = e.message; if (onScopeChange) onScopeChange(); throw e; }
    );
    if (onScopeChange) onScopeChange();
    return pending[code];
  }

  function loadAll() {
    var man = manifest();
    if (!man || !man.shards) return Promise.resolve();
    return Promise.all(man.shards.map(function (s) {
      return loadShard(s.code).catch(function () { return null; });   // 单家失败不拖垮其余
    }));
  }

  function loadedCodes() {
    return Object.keys(prepared).sort();
  }

  /* ==================================================================== */
  /* 页面                                                                  */
  /* ==================================================================== */

  F.pages.p1 = {
    id: "p1",
    index: 1,
    title: "上传年报",
    subtitle: "Upload · 看板 · 问答",

    /* 本页待实现清单 —— 只留**真缺的**。
       2026-10-13 改版前这份清单是一张愿望表（拖拽、进度、重试、演示模式…），
       里面大半已经落地了。留着一张说「待实现」的表，读的人分不清
       「还没做」和「做完了忘了划掉」。现在只写这三条：它们缺的不是 E 的工时，
       是别的角色的东西或一个后端。 */
    spec: [
      "PDF 解析入库：要 A 的 financial-extraction 起来解析、D 的 orchestrator 接住 —— file:// 下没有后端可调，本页只做类型与体积校验",
      "自由提问现算向量：要 A 的 serve.py 那个 /embed；不起服务时检索自动退回 BM25 单路（页面会如实标出来）",
      "上传后重新抽取看板：本页的看板读的是 A 已抽好的 9 家，上传的文件不会进这张表"
    ],

    render: function (root) {
      ui = F.ui;
      refs = {};
      current = null;
      picked = null;

      root.appendChild(ui.section(
        this.title,
        "上传上市公司年度报告 PDF，或直接使用已入库的 9 家 —— 下面是 A 抽好的指标看板，" +
        "以及对着年报正文的问答，答案逐条带页码出处。"
      ));

      root.appendChild(this.uploadBlock());
      root.appendChild(this.boardBlock());
      root.appendChild(this.qaBlock());
      root.appendChild(this.devBlock());
      root.appendChild(this.checkBlock());
    },

    /* ================================================================== */
    /* ① 上传窗口                                                          */
    /* ================================================================== */

    uploadBlock: function () {
      var box = ui.card();
      box.appendChild(ui.subhead("上传年报"));

      var zone = ui.el("div", "upload-zone");

      /* ★ 真的 <input type="file">，铺满整格、透明地压在上面。
         改版前这一格只有图标和一行字 —— 点了没反应、拖不进来、
         Tab 也聚焦不到，「上传窗口」在页面上纯粹是个装饰方块。

         为什么用「透明 input 铺满」而不是 `zone.onclick = input.click()`：
           · 点击、拖放、键盘（Tab + 回车）三条路一次全通 ——
             <input type="file"> 三种都原生支持，自己写只能覆盖前两条；
           · 拖放也不用自己接管 dataTransfer：浏览器会直接把文件塞进 input
             并触发 change。下面的 dragover 只负责给一点视觉反馈。
         代价是这格的文字选不中了。这一格本来就是「一整块可点的区域」，
         选不中比点不动好。 */
      var input = ui.el("input", "upload-input");
      input.type = "file";
      input.accept = ".pdf,application/pdf";
      input.setAttribute("aria-label", "选择年报 PDF 文件");
      zone.appendChild(input);

      zone.appendChild(ui.el("div", "upload-icon", "＋"));
      zone.appendChild(ui.el("div", "upload-main", "拖拽年报 PDF 到此处，或点击选择文件"));
      zone.appendChild(ui.el("div", "upload-hint",
        "仅 .pdf · 单文件 ≤ 50 MB · 只在本机校验，不上传、不解析"));

      var result = ui.el("div", "upload-result");
      refs.uploadResult = result;

      /* 拖放反馈。真正把文件接住的是上面那个 input，
         这里只做两件事：dragover 时 preventDefault（不这么做浏览器
         会当场打开这个 PDF，把页面顶掉），以及加一个高亮类。 */
      function over(on) { zone.classList.toggle("is-over", on); }
      zone.addEventListener("dragover", function (e) { e.preventDefault(); over(true); });
      zone.addEventListener("dragenter", function (e) { e.preventDefault(); over(true); });
      zone.addEventListener("dragleave", function (e) {
        /* relatedTarget 为 null = 真的拖出这一格了。
           不判一下的话，指针从格内一个子元素移到另一个子元素就会闪一下。 */
        if (!e.relatedTarget || !zone.contains(e.relatedTarget)) over(false);
      });
      zone.addEventListener("drop", function (e) { e.preventDefault(); over(false); });

      input.addEventListener("change", function () {
        handleFile(input.files && input.files[0]);
        /* 清空 value：不清的话连选两次同一个文件不会再触发 change，
           而「改完文件又拖回来」是这个格子很常见的用法。 */
        input.value = "";
      });

      box.appendChild(zone);
      box.appendChild(result);

      var actions = ui.el("div", "action-row");
      var btnSee = ui.el("button", "btn btn-primary", "看已入库的 9 家年报 ↓");
      btnSee.addEventListener("click", function () { scrollTo(refs.boardCard); });
      actions.appendChild(btnSee);
      var btnPick = ui.el("button", "btn btn-ghost", "选择一个 PDF");
      btnPick.addEventListener("click", function () { input.click(); });
      actions.appendChild(btnPick);
      box.appendChild(actions);

      /* 这一段是这个格子的重点。上传窗口在演示里最容易变成「假装能用」——
         点一下、转个圈、然后什么都没有。所以把边界写在页面上：
         文件停在哪、下一步缺谁。 */
      box.appendChild(ui.note(
        "这一格只做到「校验」为止。PDF 解析是 A 的 financial-extraction 的活，" +
        "整条链路的编排是 D 的 orchestrator 的活，两者都要起本地服务；" +
        "file:// 下单页既解不了 PDF、也没有后端可调。" +
        "要看这套界面跑在真数据上什么样，下面的 9 家是 A 已经抽好的。",
        "info"
      ));

      return box;
    },

    /* ================================================================== */
    /* ② 数据看板                                                          */
    /* ================================================================== */

    boardBlock: function () {
      /* card-dense：载数据的壳，走更实的一档玻璃，别让背景透上来干扰读数。
         与页面 2 那张 16 行的「主要财务数据」同一档。 */
      var box = ui.card("card-dense");
      refs.boardCard = box;
      box.appendChild(ui.subhead("数据看板 · A 抽好的 9 家年报"));

      if (!aReady()) {
        /* 不抛异常、不留白：说清楚缺哪个文件、去哪补。 */
        box.appendChild(ui.note(
          "A 的产物没接上 —— window.FinSearch / FINSCOPE_MANIFEST / FINSCOPE_METRICS " +
          "至少缺一个。检查 index.html 里 a/ 那一组 <script> 是否齐全（见 a/README.md）。",
          "warn"
        ));
        return box;
      }

      var man = manifest();
      box.appendChild(ui.el("p", "block-sub",
        "指标由 A 的 financial-extraction 从年报原文抽出，本页直接读 A 的 window.FINSCOPE_METRICS，" +
        "一个数都不重算。单位：亿元 —— A 给的原始单位是元，这里只做 ÷1e8 的展示缩放，" +
        "小数位与千分位跟页面 2 / 6 对齐。本表不列同比：同比是增长率，归 B 的成长性维度。"
      ));

      /* ---- 公司 chips ---- */
      var chips = ui.el("div", "chip-row");
      refs.chips = chips;
      box.appendChild(chips);

      /* ---- 检索范围提示（载入状态就写在这） ---- */
      var scope = ui.el("div", "scope-line");
      refs.scopeLine = scope;
      box.appendChild(scope);

      /* ---- 公司抬头 ---- */
      var head = ui.el("div", "board-head");
      refs.boardHead = head;
      box.appendChild(head);

      /* ---- 指标表 ---- */
      var scroller = ui.el("div", "table-scroll");
      var table = ui.el("table", "fin-table board-table");
      var cg = document.createElement("colgroup");
      [["c-name"], ["c-y1"], ["c-y2"], ["c-y3"], ["c-source"]].forEach(function (c) {
        var col = document.createElement("col");
        col.className = c[0];
        cg.appendChild(col);
      });
      table.appendChild(cg);

      var thead = document.createElement("thead");
      var hr = ui.el("tr", "fin-head-row");
      ["指标", "2023", "2024", "2025", "来源页码"].forEach(function (t) {
        hr.appendChild(ui.el("th", null, t));
      });
      thead.appendChild(hr);
      table.appendChild(thead);

      var tbody = document.createElement("tbody");
      refs.boardBody = tbody;
      table.appendChild(tbody);

      scroller.appendChild(table);
      box.appendChild(scroller);

      /* ---- 存疑汇总（一处橙，行内徽标只负责定位） ---- */
      var warnSlot = ui.el("div", "board-warn");
      refs.boardWarn = warnSlot;
      box.appendChild(warnSlot);

      box.appendChild(ui.el("p", "block-sub",
        "数值是 A 从年报里抽出来的三年原样数字，不是任何形式的推算；" +
        "同一行三年并列，变化多少由读者自己判断。"
      ));

      /* ---- 该页原文抽屉（点表格里的页码） ---- */
      var drawer = ui.el("div", "board-drawer");
      refs.boardDrawer = drawer;
      box.appendChild(drawer);

      /* ---- 检索范围变了就重画 ---- */
      onScopeChange = function () { renderChips(); renderScope(); };

      /* 首屏：看板立刻可用（metrics.js 只有 95 KB，随 index.html 一起进来），
         一家分片都不载。默认选中的公司取 A 清单里的第一家，与 A 原页面一致。 */
      if (man && man.shards && man.shards.length) current = man.shards[0].code;
      renderChips();
      renderScope();
      renderDashboard(current);

      return box;
    },

    /* ================================================================== */
    /* ③ 年报问答                                                          */
    /* ================================================================== */

    qaBlock: function () {
      var box = ui.card("card-dense");
      refs.qaCard = box;
      box.appendChild(ui.subhead("年报问答 · A 的检索内核"));

      if (!aReady()) {
        box.appendChild(ui.note("A 的检索内核没接上（缺 window.FinSearch 或 window.FinTok），本块不可用。", "warn"));
        return box;
      }

      var presets = window.FINSCOPE_QUERIES || [];
      var man = manifest();
      box.appendChild(ui.el("p", "block-sub",
        "下面是 A 出的 " + presets.length + " 道核验题（每题带预计算向量，所以点一下就能跑）。" +
        "答案是从年报正文里抽出来的原句，不是生成的、也没有润色；每条后面的角标对应下方证据块，" +
        "证据块带公司、章节与年报页码。"
      ));

      /* ---- 预设题 ---- */
      var row = ui.el("div", "preset-row");
      presets.forEach(function (p) {
        var b = ui.el("button", "preset", p.q);
        b.type = "button";
        b.addEventListener("click", function () {
          refs.qaInput.value = p.q;

          /* 点到一家还没载入的公司时先把它的正文读进来 —— 否则第一次
             点任何一道题都只会得到「还没有载入任何一家年报」。
             读哪几家由问句自己决定：点名了就只读那几家
             （「三一重工2025年…」只读 1.9 MB），没点名就是跨公司题，
             要全量（「各家公司2025年的研发费用分别是多少」→ 17 MB）。 */
          var need = scopeFor(p.q);
          var todo = need.filter(function (c) { return !prepared[c]; });
          clear(refs.qaStatus);
          if (todo.length) {
            refs.qaStatus.appendChild(ui.el("span", "qa-hint",
              todo.length === need.length
                ? ("这道题要读入 " + todo.length + " 家年报正文" +
                   (todo.length > 3 ? "（约 17 MB，首次会慢几秒）" : "") + "…")
                : ("这道题要读入 " + todo.length + " 家年报正文…")));
          }
          ensureScopeFor(p.q).then(function () { runQuery(p.q); });
        });
        row.appendChild(b);
      });
      refs.presetRow = row;
      box.appendChild(row);

      /* ---- 提问框 ---- */
      var form = ui.el("form", "qa-form");
      var input = ui.el("input", "qa-input");
      input.type = "text";
      input.placeholder = "也可以自己问一句，例如「存货跌价准备怎么计提的」";
      input.setAttribute("aria-label", "对年报正文提问");
      refs.qaInput = input;
      form.appendChild(input);

      var go = ui.el("button", "btn btn-primary", "提问");
      go.type = "submit";
      form.appendChild(go);
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        runQuery(input.value);
      });
      box.appendChild(form);

      /* ---- 检索状态 ---- */
      var status = ui.el("div", "qa-status");
      refs.qaStatus = status;
      box.appendChild(status);

      /* ---- 答案 ---- */
      var answer = ui.el("div", "qa-answer");
      refs.qaAnswer = answer;
      box.appendChild(answer);

      /* ---- 证据块 ---- */
      var evidence = ui.el("div", "ev-list");
      refs.qaEvidence = evidence;
      box.appendChild(evidence);

      /* 分词器一致性自检。A 的 tokenize.js 必须与 Python 侧逐字一致，
         不一致则 BM25 词表整体错位、检索结果不可信 —— 这比「答得不准」
         严重得多，所以挂一条看得见的判定，而不是只在控制台打个日志。 */
      if (window.TOKENIZER_GOLDEN && FinTok.checkGolden) {
        var g = FinTok.checkGolden(window.TOKENIZER_GOLDEN);
        if (!g.ok) {
          box.appendChild(ui.note(
            "分词器与 A 的 Python 侧不一致（黄金样本未通过），检索结果不可信。" +
            "请核对 a/tokenize.js 的版本：manifest 声明 " +
            ((man && man.tokenizer_version) || "?") + "。",
            "warn"
          ));
        }
      }

      if (man && man.index_version) {
        box.appendChild(ui.el("p", "qa-meta",
          "索引 " + man.index_version + " · 分词 " + man.tokenizer_version +
          " · 向量 " + (man.embedder_version || "?") +
          " · 语料共 " + (man.shards || []).reduce(function (a, s) { return a + s.n_chunks; }, 0) +
          " 个块（" + (man.shards || []).length + " 家年报）"
        ));
      }

      box.appendChild(ui.note(
        "检索范围 = 已载入的公司（见上方看板的载入状态）。分片按需读取，" +
        "没载入的公司不参与检索 —— 页面上会写明这次是在几家、多少个块里找的。",
        "info"
      ));

      return box;
    },

    /* ================================================================== */
    /* ④ 待实现 + 骨架自检                                                 */
    /* ================================================================== */

    devBlock: function () {
      var box = ui.card("dev-card");
      box.appendChild(ui.subhead("本页还差什么"));
      box.appendChild(ui.todoList(this.spec));
      return box;
    },

    checkBlock: function () {
      var box = ui.card();
      box.appendChild(ui.subhead("骨架自检 · 数据管道验证"));

      var st = F.data.status();
      var cs = F.data.contractStatus();
      var rows = [
        ["数据源", st.sourceName, "", "由 index.html 引用决定"],
        ["加载状态", st.loaded ? "已就绪" : "未就绪", st.loaded ? "is-good" : "is-bad"],
        ["校验提醒", st.warnings.length + " 项",
         st.warnings.length ? "is-watch" : "is-good",
         "只报「缺口」；页面仍可运行，明细见控制台"]
      ];

      /* A 的语料单独一行 —— 它是本页唯一一个**体积和就绪状态不在一块报**的东西：
         manifest / metrics / queries 三份约 110 KB 随页加载，17 MB 分片按需。
         不写清楚的话，「问答要 17 MB」看起来像首屏成本。 */
      if (aReady()) {
        var man = manifest();
        var n = loadedCodes().length;
        rows.push([
          "A 的语料",
          n + " / " + ((man && man.shards) ? man.shards.length : 0) + " 家已载入",
          n ? "is-good" : "",
          "随页加载 110 KB（引擎+看板+预设题）；17 MB 分片按需读取，不点不载"
        ]);
      } else {
        rows.push(["A 的语料", "未接上", "is-bad", "见 a/README.md 的接入说明"]);
      }

      /* ---- 2026-10-13 撤：「图表库」那一行 ----
         它原来报的是 `F.charts.hasLib() ? "Chart.js 已加载" : "未加载"`，
         来源是 vendor/chart.umd.min.js。那张库连同 js/charts.js 一起删了。
         ★ 为什么是**整行删掉**而不是改成「未加载」：
           这一格的作用是「声明一个能力」，而 Chart.js 从来不是这个产品的能力 ——
           六个页面一张 canvas 都没有（标尺、比例条全是 DOM + CSS）。
           留一行「图表库：未加载」等于在自检面板上挂一个永远红的格，
           而它对能不能交付毫无影响 —— 见 README 里那条
           「一条永远红的判定比没有判定更坏」。 */
      if (cs) {
        var tt = cs.totals;
        rows.push(["契约体检", tt.renderable + " / " + tt.pages + " 个页面可完整渲染",
                   tt.core ? "is-bad" : (tt.problems ? "is-watch" : "is-good"),
                   "依据 js/contract.js 的 " + F.contract.allPaths().length + " 条路径走查"]);
        rows.push(["待交付", tt.open + " 项", tt.open ? "is-watch" : "is-good",
                   "合同里已挂着、页面已留位；不算缺口，所以不进上面的提醒条"]);
      }
      box.appendChild(ui.kv(rows));

      /* 按队友切开的缺口清单 —— 把「还差什么」直接落到人头上。
         这一个块就是 tools/interface-check.js 在页面上的那一半。 */
      if (cs && Object.keys(cs.byOwner).length) {
        box.appendChild(ui.subhead("还差谁的东西"));
        var ol = ui.el("div", "owner-list");
        Object.keys(cs.byOwner).sort().forEach(function (w) {
          var o = cs.byOwner[w];
          var bits = [];
          if (o.core.length) bits.push("必需 " + o.core.length + " 项");
          if (o.open.length) bits.push("待交付 " + o.open.length + " 项");
          if (o.opt.length)  bits.push("可选 " + o.opt.length + " 项");
          if (o.problems.length) bits.push("⚠️ 异常 " + o.problems.length + " 项");
          var line = ui.el("div", "owner-row");
          line.appendChild(ui.el("span", "owner-who", w));
          line.appendChild(ui.el("span", "owner-what", bits.join(" / ")));
          line.appendChild(ui.el("span", "owner-note",
            o.core.length ? "缺了对应页面会退化成空状态" :
            (o.open.length ? "页面已留位，交付后零改动生效" : "")));
          ol.appendChild(line);
        });
        box.appendChild(ol);
      } else if (cs) {
        /* 用 info 不用 good：全站零新增色。这一条是「无事发生」，
           不该为一句话在页面上多开一个绿色的落点。 */
        box.appendChild(ui.note("契约体检未发现任何缺口与欠账 —— 这份数据是完整的。", "info"));
      }

      return box;
    }
  };

  /* ==================================================================== */
  /* 上传：校验与登记                                                      */
  /* ==================================================================== */

  function handleFile(file) {
    var out = refs.uploadResult;
    if (!out) return;
    clear(out);

    if (!file) {
      picked = null;
      return;
    }

    var name = file.name || "(没有文件名)";

    /* 两道校验。accept=".pdf" 只过滤**选择框**里的条目，
       拖进来的文件它管不着，所以类型必须在这里再判一次。 */
    if (!/\.pdf$/i.test(name) && file.type !== "application/pdf") {
      picked = null;
      out.appendChild(ui.note("这不是 PDF：「" + name + "」。这一格只收 .pdf。", "warn"));
      return;
    }
    if (file.size > MAX_BYTES) {
      picked = null;
      out.appendChild(ui.note(
        "「" + name + "」有 " + mib(file.size) + "，超过 50 MB 上限。" +
        "年报 PDF 一般 3–15 MB，先确认一下是不是扫错了文件。", "warn"));
      return;
    }

    picked = file;

    /* 通过校验 → 出文件卡。显示的四项都是 File 对象上**真的有**的属性，
       没有一个是我们自己编出来的。 */
    var cardBox = ui.el("div", "file-card");
    var top = ui.el("div", "file-top");
    top.appendChild(ui.el("span", "file-badge", "PDF"));
    top.appendChild(ui.el("span", "file-name", name));
    cardBox.appendChild(top);

    var meta = ui.el("div", "file-meta");
    meta.appendChild(ui.el("span", null, "体积 " + mib(file.size)));
    meta.appendChild(ui.el("span", null, "最后修改 " +
      new Date(file.lastModified).toLocaleString("zh-CN")));
    meta.appendChild(ui.el("span", null, "类型 " + (file.type || "未标明")));
    cardBox.appendChild(meta);

    var foot = ui.el("div", "file-foot");
    foot.appendChild(ui.el("span", "file-verdict",
      "✓ 类型与体积都通过 —— 校验到此为止，文件没有离开这台机器"));
    var rm = ui.el("button", "btn-link", "移除");
    rm.type = "button";
    rm.addEventListener("click", function () {
      picked = null;
      clear(out);
      var inp = refs.uploadResult && refs.uploadResult.parentNode
        ? refs.uploadResult.parentNode.querySelector(".upload-input") : null;
      if (inp) inp.value = "";
    });
    foot.appendChild(rm);
    cardBox.appendChild(foot);

    out.appendChild(cardBox);
  }

  /* ==================================================================== */
  /* 看板                                                                  */
  /* ==================================================================== */

  function renderChips() {
    var box = refs.chips;
    if (!box) return;
    clear(box);

    var man = manifest();
    if (!man || !man.shards) return;
    var M = metricsAll() || {};

    man.shards.forEach(function (s) {
      var m = M[s.code];
      var b = ui.el("button", "chip");
      b.type = "button";
      if (s.code === current) b.className += " is-on";
      if (prepared[s.code]) b.className += " is-loaded";
      if (pending[s.code]) b.className += " is-loading";
      if (shardErr[s.code]) b.className += " is-failed";

      b.appendChild(ui.el("span", "chip-name", (m && m.company && m.company.name) || s.name));
      b.appendChild(ui.el("span", "chip-meta", s.code + " · " + s.n_chunks + " 块"));
      /* 载入状态**写在 chip 上**，而不是只写在上方那行小字里 ——
         点一下公司名会读 1–2 MB 的文件，这件事必须当场看得见。 */
      b.appendChild(ui.el("span", "chip-load", chipLoadText(s.code)));

      b.addEventListener("click", function () { selectCode(s.code); });
      box.appendChild(b);
    });
  }

  function chipLoadText(code) {
    if (prepared[code]) return "已载入 · 可检索";
    if (pending[code]) return "载入中…";
    if (shardErr[code]) return "载入失败";
    return "点击载入语料";
  }

  function renderScope() {
    var box = refs.scopeLine;
    if (!box) return;
    clear(box);

    var man = manifest();
    var total = (man && man.shards) ? man.shards.length : 0;
    var n = loadedCodes().length;
    var chunks = loadedCodes().reduce(function (a, c) {
      return a + ((prepared[c].meta && prepared[c].meta.n_chunks) || 0);
    }, 0);

    box.appendChild(ui.el("span", "scope-text",
      n ? ("检索范围：已载入 " + n + " / " + total + " 家，共 " + chunks +
           " 个块（约 " + (chunks * 3.2 / 1000).toFixed(1) + " MB 正文）")
        : ("检索范围：0 / " + total + " 家 —— 点公司名读入那一家的年报正文后才能提问")
    ));

    var errs = Object.keys(shardErr);
    if (errs.length) {
      box.appendChild(ui.el("span", "scope-err",
        "有 " + errs.length + " 家读不进来：" + errs.map(function (c) {
          return c + "（" + shardErr[c] + "）";
        }).join("；")));
    }

    if (n < total) {
      var all = ui.el("button", "btn-link", "全部载入（" + total + " 家，约 17 MB）");
      all.type = "button";
      all.addEventListener("click", function () {
        all.disabled = true;
        all.textContent = "载入中…";
        loadAll();
      });
      box.appendChild(all);
    }
  }

  function selectCode(code) {
    current = code;
    renderChips();
    renderDashboard(code);
    if (!prepared[code] && !pending[code]) loadShard(code);
  }

  function statusBadge(st) {
    if (st === "found" || !st) return null;
    if (st === "not_applicable") {
      var a = ui.el("span", "badge na", "不适用");
      a.title = "命中了科目名，但值确实是空（这一项对这家公司不存在）";
      return a;
    }
    if (st === "not_found") {
      var b = ui.el("span", "badge nf", "未找到");
      b.title = "别名未命中 —— 可能是抽取失败，不是「这家没有」";
      return b;
    }
    return ui.el("span", "badge nf", st);
  }

  function renderDashboard(code) {
    var head = refs.boardHead, body = refs.boardBody;
    if (!head || !body) return;
    clear(head);
    clear(body);
    closeDrawer();

    var M = metricsAll();
    var m = M && code ? M[code] : null;
    if (!m) {
      head.appendChild(ui.el("div", "board-empty", "这一家没有指标数据（FINSCOPE_METRICS 里无 " + code + "）"));
      return;
    }

    /* ---- 抬头 ---- */
    var c = m.company, em = m.extraction_meta || {};
    var pm = em.pagemap || {};

    var nameRow = ui.el("div", "board-name-row");
    nameRow.appendChild(ui.el("span", "board-name", c.name || code));
    nameRow.appendChild(ui.el("span", "ticker", c.ticker || code));
    head.appendChild(nameRow);

    var meta = ui.el("div", "board-meta");
    [
      c.industry,
      c.report_period,
      em.pdf_pages ? ("年报 " + em.pdf_pages + " 页") : null,
      /* 页码映射覆盖率：A 用来声明「每个块都能对上印刷页码」的程度。
         它不是 E 算的，是 A 的 extraction_meta 直接读的。 */
      (pm.coverage != null) ? ("页码映射覆盖 " + Math.round(pm.coverage * 100) + "%") : null,
      (pm.n_missing ? (pm.n_missing + " 页未对上") : null),
      "指标 " + Object.keys(m.financials).length + " / " + Object.keys(m.financials).length
    ].forEach(function (t) {
      if (t) meta.appendChild(ui.el("span", "meta-chip", String(t)));
    });
    head.appendChild(meta);

    /* ---- 通向页面 2 的联动（① 方案 A） ----
       ------------------------------------------------------------------
       ★ **只在「这一家正好是 D 交付的那一家」时才给这个链接。**
         D 只交付 1 家（600519 茅台）。其余 8 家在页面 2 上**根本没有对应
         数据** —— 无条件给链接，点过去看到的还是茅台，那是**指错**，
         比不给链接更坏（同 EDGE_CASES #99「一条指错的欠账比没有欠账更坏」）。
       ★ 用 <a href="#p2"> 而不是调 app 的内部函数：全站切页就是靠
         hashchange（app.js 的 show(fromHash())），所以普通的锚点就是
         唯一正确的接法，也不给页面开一个「要认识 app 内部」的口子。
       ★ 箭头是**文字字形**不是图标字体（硬约束：零图标字体）。 */
    if (code === dCompanyCode()) {
      var jump = ui.el("a", "board-jump",
        "看这家公司的完整概览 →");
      jump.href = "#p2";
      jump.title = "页面 2 · " + (c.name || code) +
        "：核心指标 / 主要财务数据 / 估值。其余 8 家 D 未交付完整财务数据，不在页面 2 上。";
      head.appendChild(jump);
    } else {
      /* ★ 2026-10-13 第六轮：**把「为什么这一家没有那个入口」写在它缺席的地方。**
         反馈原话：「按理来说已经载入的 9 家公司都可以看到完整概览吧，
         但是只有茅台下面有『看这家公司的完整概览』的引导，我认为其它公司也可以加上」。

         边界是真实的：页面 2 读的是 D 的 window.FINSCOPE_DATA，
         而 D 只交付了 600519 一家（公司抬头 + 17 个科目 + ratios / risks /
         valuation）。A 的 window.FINSCOPE_METRICS 虽然 9 家都有，但它只有
         company / financials / extraction_meta 三段 —— 缺 ratios、缺 valuation，
         连科目键名都不一样（A 是 net_profit_attr，D 是 net_income_parent）。
         所以「给另外 8 家也加上那个链接」在这里做不到，
         硬做的话点过去看到的还是茅台 —— 那是指错，
         比不给入口更坏（EDGE_CASES #99）。

         既然做不到「都加上」，就不要让它**沉默**：把缺席的原因和覆盖范围
         写在这一行该在的位置上。读者看到的是「这家没有，因为 D 没交付，
         完整概览目前覆盖贵州茅台」，而不是「为什么这家没有链接」。
         这一行只在**非 600519** 的看板上出现 —— 有入口的那一家不需要解释。 */
      var dCode = dCompanyCode();
      var dM = (M && dCode) ? M[dCode] : null;
      var dName = dM && dM.company ? dM.company.name : null;
      var off = ui.el("div", "board-jump-off",
        "页面 2 的完整概览（核心指标 / 主要财务数据 / 估值）由 D 交付，"
          + "目前只覆盖 " + (dName && dCode ? dName + "（" + dCode + "）" : "贵州茅台（600519）")
          + " 一家；这一家的核心指标与三年原值在本表，但 ratios / risks / valuation "
          + "D 未交付，所以页面 2 上没有它。");
      head.appendChild(off);
    }

    /* ---- 表体 ---- */
    var ident = suspectByIdentity(m.financials);            // 跨行恒等式，一年一年算一次
    var tA = m.financials.total_assets;
    var totalAssetsYuan = tA ? F.fmt.toNum(tA.value) : null;  // 只用来判「这家是什么量级」
    var susRows = 0, susCells = 0;

    Object.keys(m.financials).forEach(function (key) {
      var f = m.financials[key];
      var s = f.series || {};

      var tr = ui.el("tr", "fin-row");

      var td0 = ui.el("td", "fin-label fin-name");
      td0.appendChild(document.createTextNode(f.label || key));
      var badge = statusBadge(f.status);
      if (badge) td0.appendChild(badge);

      /* 存疑标记。**不改任何数** —— 值照 A 给的画，只是在旁边说一句。
         徽标落在**科目名那一格**而不是数值格：数值格在 680 px 宽度下只剩 34 px 余量，
         塞一枚徽标就会把数字挤出去，那等于用一个显示缺陷去修一个数据缺陷。 */
      var sus = suspectYearsByMagnitude(s, totalAssetsYuan);
      Object.keys(ident).forEach(function (y) {
        if (ident[y][key]) sus[y] = ident[y][key];
      });
      var susYrs = Object.keys(sus).sort();
      if (susYrs.length) {
        susRows++; susCells += susYrs.length;
        var sb = ui.el("span", "badge suspect", "存疑");
        sb.title = susYrs.map(function (y) { return y + "：" + sus[y]; }).join("；")
                 + "。★ 这是 A 的抽取结果，E 只做展示、没有改数，也没有重算。";
        td0.appendChild(sb);
      }
      tr.appendChild(td0);

      /* 三年原值，全部来自 A 的 series。
         v2025 兜一层 f.value：series 缺 2025 但 status=found 时，
         value 就是 A 抽出来的本期值，不能显示成破折号。
         （全语料 153 格里有 2 格 series 为空，都是 not_applicable / not_found，
          这一层兜底是为将来 A 换了抽取结果准备的，不是为现在这两格。） */
      [["2023", "fin-prior"], ["2024", "fin-prior"], ["2025", "fin-value"]].forEach(function (p) {
        var v = s[p[0]];
        if (v == null && p[0] === "2025" && f.status === "found") v = f.value;
        tr.appendChild(ui.el("td", p[1], yi(v)));
      });

      var tdP = ui.el("td", "col-source");
      if (f.page != null) {
        var lk = ui.el("span", "page-link", F.fmt.page(f.page));
        lk.title = "点击查看这一页的原文";
        lk.addEventListener("click", function () { showPageEvidence(code, f.page); });
        tdP.appendChild(lk);
      } else {
        tdP.appendChild(ui.el("span", "board-dim", F.fmt.MISSING));
      }
      tr.appendChild(tdP);

      body.appendChild(tr);
    });

    /* ---- 存疑汇总 ----
       一处橙就够了，行内那几枚灰徽标只负责「让你在 17 行里找到它们」。
       全站的橙预算是一屏 1–2 处；这一条正好是「需要警觉」那一半。 */
    if (refs.boardWarn) {
      clear(refs.boardWarn);
      if (susRows) {
        refs.boardWarn.appendChild(ui.note(
          "这张表里有 " + susRows + " 行（共 " + susCells + " 个年份）的数据「自相矛盾」 —— " +
          "标了「存疑」的那些。判据只用 A 自己给的数互相比（同一行相差 100 倍以上、" +
          "营业成本高于营业收入、总负债高于总资产、资产负债表科目只有几十元），" +
          "没有引任何外部数据。「E 没有改任何数字，也没有重算」 —— " +
          "值照 A 的原文画，标记只是提醒你别直接引用。这属于 A 的抽取结果，要修得从那边修。",
          "warn"));
      }
    }
  }

  /* 点页码 → 把**该页所有命中的指标**的原样信息铺开：
     原始单位、原文字段、科目名匹配、口径、置信度。
     这一块的意义是让「1,688.38」能一路追回到年报第 6 页的那一行字。 */
  function showPageEvidence(code, page) {
    var box = refs.boardDrawer;
    if (!box) return;
    clear(box);

    var M = metricsAll();
    var m = M && M[code];
    if (!m) return;

    var hits = Object.keys(m.financials).filter(function (k) { return m.financials[k].page === page; })
      .map(function (k) { return m.financials[k]; });

    var head = ui.el("div", "drawer-head");
    head.appendChild(ui.el("span", "drawer-title",
      "该页原文 · " + (m.company.name || code) + " 年报 P." + page));
    var close = ui.el("button", "btn-link", "收起");
    close.type = "button";
    close.addEventListener("click", closeDrawer);
    head.appendChild(close);
    box.appendChild(head);

    if (!hits.length) {
      box.appendChild(ui.el("p", "block-sub", "这一页没有指标命中 —— 说明该页是正文叙述，不是财务指标表。"));
      box.classList.add("is-open");
      return;
    }

    hits.forEach(function (f) {
      var ev = ui.el("div", "ev");
      var h = ui.el("div", "ev-head");
      h.appendChild(ui.el("b", null, f.label));
      h.appendChild(ui.el("span", "ev-dim", "原始单位 " + (f.unit_raw || f.unit || "—")));
      if (f.section) h.appendChild(ui.el("span", "ev-dim", f.section));
      ev.appendChild(h);

      ev.appendChild(ui.el("div", "ev-raw", String(f.raw_text || "—")));

      var foot = ui.el("div", "ev-foot");
      [
        ["科目名匹配", f.alias_matched],
        ["口径", f.basis],
        ["置信度", f.confidence],
        ["所在表", f.table]
      ].forEach(function (p) {
        if (p[1] === null || p[1] === undefined || p[1] === "") return;
        foot.appendChild(ui.el("span", "ev-kv", p[0] + "：" + p[1]));
      });
      ev.appendChild(foot);
      box.appendChild(ev);
    });

    box.classList.add("is-open");
    scrollTo(box);
  }

  function closeDrawer() {
    var box = refs.boardDrawer;
    if (!box) return;
    box.classList.remove("is-open");
    clear(box);
  }

  /* ==================================================================== */
  /* 问答                                                                  */
  /* ==================================================================== */

  /* A 的预置题自带预计算向量（queries.js 每条都有 vec 字段）。
     静态页装不下 95 MB 的 ONNX 模型，所以只有这几句能走向量；
     自由提问拿不到向量，检索退回 BM25 单路 —— 页面会如实标出来，
     而不是假装「语义检索」了。 */
  function queryVector(text) {
    var presets = window.FINSCOPE_QUERIES || [];
    for (var i = 0; i < presets.length; i++) {
      if (presets[i].q === text) return toFloatVec(presets[i].vec);
    }
    return null;
  }

  function toFloatVec(b64) {
    var i8 = FinSearch.decodeTyped(b64, Int8Array);
    var f = new Float32Array(i8.length);
    for (var i = 0; i < i8.length; i++) f[i] = i8[i];
    return f;
  }

  /* 断句。★ 没有用 A 原来的 `split(/(?<=[。！？；\n])/)` ——
     那个后行断言（lookbehind）在 Safari 16.4 之前是语法错误，
     整段脚本会直接不执行。这一页要能在 Mac 上双击打开，所以换成手写扫描：
     逐字累积、碰到终止符就切一刀。语义与原来的正则一致。 */
  function splitSentences(text) {
    var out = [], buf = "";
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      buf += ch;
      if (ch === "。" || ch === "！" || ch === "？" || ch === "；" || ch === "\n") {
        if (buf.trim()) out.push(buf.trim());
        buf = "";
      }
    }
    if (buf.trim()) out.push(buf.trim());
    return out;
  }

  /* 抽取式回答：从命中的证据块里挑与问句词重叠最高的句子。
     分数 = 命中词数 / √(句子词数) —— 除以根号是为了不让长句天然占优，
     再加一个很小的名次奖励（越靠前的证据块越可能对题）。 */
  function composeAnswer(question, results) {
    var qset = Object.create(null);
    FinTok.tokenize(question).forEach(function (t) { qset[t] = true; });

    var scored = [];
    results.forEach(function (r, ri) {
      splitSentences(r.text).forEach(function (s) {
        if (s.length < 8) return;
        var toks = FinTok.tokenize(s), hit = 0;
        toks.forEach(function (t) { if (qset[t]) hit++; });
        scored.push({
          sent: s,
          score: hit / Math.sqrt(toks.length || 1) + 0.35 / (ri + 1),
          ref: ri + 1
        });
      });
    });
    scored.sort(function (a, b) { return b.score - a.score; });

    var picked = [], seen = Object.create(null);
    for (var i = 0; i < scored.length && picked.length < 4; i++) {
      var key = scored[i].sent.slice(0, 30);
      if (seen[key]) continue;
      seen[key] = true;
      picked.push(scored[i]);
    }
    return picked;
  }

  /* 一道题需要在哪几家的语料里找。
     点名了公司就只带那几家（问句里的公司名直接对着 A 清单的 name 匹配，
     和 a/search.js 里 searchAll 给同名词加权的口径是同一个字符串）；
     一家都没点名，说明是跨公司题，那就全量。 */
  function scopeFor(q) {
    var man = manifest();
    if (!man || !man.shards) return [];
    var M = metricsAll() || {};
    var named = man.shards.filter(function (s) {
      var n = (M[s.code] && M[s.code].company && M[s.code].company.name) || s.name;
      return n && q.indexOf(n) >= 0;
    });
    var pick = named.length ? named : man.shards;
    return pick.map(function (s) { return s.code; });
  }

  function ensureScopeFor(q) {
    return Promise.all(scopeFor(q).map(function (c) {
      return loadShard(c).catch(function () { return null; });   // 单家失败不阻塞其余
    }));
  }

  function runQuery(text) {
    text = (text || "").trim();
    if (!text) return;

    var status = refs.qaStatus;
    if (!status) return;
    clear(status);
    clear(refs.qaAnswer);
    clear(refs.qaEvidence);

    if (!loadedCodes().length) {
      /* 一句话都没载入时，别让用户对着「还没有载入任何一家」发呆 ——
         默认把看板上选中的那家读进来再答。这是 page 1 唯一一处
         「不点也会读文件」的地方，只读一家（≤ 2.2 MB）。 */
      if (!current) {
        status.appendChild(ui.el("span", "qa-hint",
          "还没有可检索的年报 —— 先在上面的看板里点一家公司，或直接用上面的预设题。"));
        return;
      }
      var meta = findMeta(current);
      status.appendChild(ui.el("span", "qa-hint",
        "先读入 " + ((meta && meta.name) || current) + " 的年报正文…"));
      loadShard(current).then(go, function (e) {
        clear(status);
        status.appendChild(ui.el("span", "qa-hint", "读入失败：" + e.message));
      });
      return;
    }
    go();

    function go() {
      var codes = loadedCodes();
      if (!codes.length) {
        status.appendChild(ui.el("span", "qa-hint", "没有可检索的语料。"));
        return;
      }

      /* 同步算完再渲染。一次 searchAll 在 600 个块上约几十毫秒，
         不值得为它做异步状态机；「检索中…」这一行是给重问九家时兜的。 */
      var now = function () { return (window.performance && performance.now) ? performance.now() : Date.now(); };
      var t0 = now();
      var vec = queryVector(text);
      var list = codes.map(function (c) { return prepared[c]; });
      var results = FinSearch.searchAll(list, text, vec, { topN: 8, pool: 200 });
      var ms = Math.round(now() - t0);
      var chunks = list.reduce(function (a, s) { return a + (s.meta.n_chunks || 0); }, 0);

      clear(status);
      status.appendChild(ui.el("span", "qa-mode " + (vec ? "is-vec" : "is-bm25"),
        vec ? "BM25 + 向量 双路融合" : "BM25 单路"));
      status.appendChild(ui.el("span", "qa-hint",
        (vec
          ? "这道题在 A 的预置题里，带着预计算向量 —— 语义与关键词两路都跑。"
          : "自由提问在 file:// 下算不了向量（要 A 的 serve.py 的 /embed），所以只有关键词一路；" +
            "换用上面的预置题可以走到双路。") +
        " 本次在 " + codes.length + " 家、" + chunks + " 个块里找，用时 " + ms + " ms。"
      ));

      renderAnswer(text, results);
    }
  }

  function renderAnswer(question, results) {
    var picked = composeAnswer(question, results);
    var ans = refs.qaAnswer;
    if (!ans) return;
    clear(ans);

    ans.appendChild(ui.el("div", "ans-note",
      "以下答案由检索到的证据块抽取拼接，未做生成式改写；每条末的角标对应下方证据块，证据块带页码。"));

    if (!picked.length) {
      ans.appendChild(ui.el("p", "ans-empty", "没有找到足够相关的证据。换一种说法，或先把相关公司载入。"));
    } else {
      picked.forEach(function (p) {
        var line = ui.el("p", "ans-line");
        line.appendChild(document.createTextNode(p.sent));
        line.appendChild(ui.el("sup", "cite", "[" + p.ref + "]"));
        ans.appendChild(line);
      });
    }

    /* ---- 证据块 ---- */
    var ev = refs.qaEvidence;
    clear(ev);
    if (!results.length) return;

    ev.appendChild(ui.subhead("证据块（" + results.length + "）"));

    results.forEach(function (r) {
      var box = ui.el("div", "ev");

      var h = ui.el("div", "ev-head");
      h.appendChild(ui.el("b", null, "[" + r.fused_rank + "]"));
      h.appendChild(ui.el("span", "ev-name", r.company_name || r.company_code));
      if (r.section) h.appendChild(ui.el("span", "ev-dim", r.section));
      h.appendChild(ui.el("b", "ev-page", "第 " + (r.printed_page == null ? "?" : r.printed_page) + " 页"));
      if (r.is_table) h.appendChild(ui.el("span", "badge tb", "表格"));
      box.appendChild(h);

      var meta = ui.el("div", "ev-meta");
      meta.appendChild(ui.el("span", null, "BM25 名次 " + (r.bm25_rank || "—")));
      meta.appendChild(ui.el("span", null, "向量名次 " + (r.vec_rank || "—")));
      meta.appendChild(ui.el("span", null, "融合分 " + r.fused_score.toFixed(4)));
      box.appendChild(meta);

      /* 长块先截 420 字，给一个「展开全文」把它换出来 ——
         直接铺全文会让一整页都是正文，反而看不到有几条证据。
         截断这件事要说出来（写「共 N 字」），不能悄悄切。 */
      var full = String(r.text || "");
      var textEl = ui.el("div", "ev-text", full.slice(0, 420));
      box.appendChild(textEl);

      if (full.length > 420) {
        var more = ui.el("button", "btn-link", "展开全文（共 " + full.length + " 字）");
        more.type = "button";
        more.addEventListener("click", function () {
          if (textEl.textContent.length > 420) {
            textEl.textContent = full.slice(0, 420);
            more.textContent = "展开全文（共 " + full.length + " 字）";
          } else {
            textEl.textContent = full;
            more.textContent = "收起";
          }
        });
        box.appendChild(more);
      }

      ev.appendChild(box);
    });
  }

  /* ==================================================================== */
  /* 小动作                                                                */
  /* ==================================================================== */

  function scrollTo(el) {
    if (!el) return;
    var r = el.getBoundingClientRect();
    window.scrollTo(0, Math.max(0, r.top + window.scrollY - 24));
  }

  /* ---- 打印前把截断的证据全文展开 ----
     与 app.js 里那个 expandAll（展开折叠的风险卡）同一个道理：
     「先给 420 字、想看全文再点」是**屏幕上的省地方设计**，
     印到纸上就变成「内容真的只有这些」—— 那是一种很坏的错法，
     全文和截断在纸上长得一模一样。所以印前先替读者点开。

     ★ 用 click() 而不是直接改 DOM：按钮自己的文案（展开全文 ↔ 收起）
       要跟着同步，绕过去会印出一个写着「展开全文」的按钮配一整段全文。
     只点 .ev-list 里的（问答证据块）；看板抽屉里的原文本来就不截断。 */
  function expandEv() {
    var btns = document.querySelectorAll(".ev-list .btn-link");
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].textContent.indexOf("展开全文") === 0) btns[i].click();
    }
  }

  window.addEventListener("beforeprint", expandEv);
  /* ★ Chrome 在部分场景不触发 beforeprint，用媒体查询兜一道 ——
     app.js 里对风险卡也是这么兜的，两处保持同一种写法。 */
  if (window.matchMedia) {
    var mq = window.matchMedia("print");
    var onMq = function (e) { if (e.matches) expandEv(); };
    if (mq.addEventListener) mq.addEventListener("change", onMq);
    else if (mq.addListener) mq.addListener(onMq);
  }
})();
