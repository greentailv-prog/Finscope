/* ============================================================================
 * p5-valuation.js —— 页面5 估值分析
 * ----------------------------------------------------------------------------
 * 职责：让「两条估值区间差在哪」一眼可见。
 *
 * Comps（可比公司法）与 DCF（现金流折现法）是用两套完全不同的逻辑回答
 * 同一个问题。所以这页的核心不是某一家算出来的数字，而是
 * **两条区间落在同一把尺子上的相对位置** —— 演示脚本原话就是
 * 「指出 Comps 和 DCF 两条区间，讲两者差异」（docs/DEMO_SCRIPT.md:68）。
 *
 * 数据来源：valuation.* —— D 的统一数据对象（data/real_data.js）
 *
 * 【2026-10-13 全量重写：字段名全线对不上，且原来等的东西 D 已经给了】
 *
 *   旧版读的都是 C 那一版的字段名，D 交付的是另一套：
 *     comps.range            → comps.valuation_range（★ 自带 currency:"元/股"）
 *     comps.range.unit       → valuation_range.currency
 *     comps.target           → comps.inputs
 *     comps.peers            → comps.peer_companies
 *     dcf.range              → dcf.valuation_range
 *     dcf.assumptions        → dcf.inputs
 *   旧版的 spec 列了三条「待 C 补」，**D 已经全部补上了**：
 *     ① 没有 current_price → 现在 valuation.market_data.price 与
 *        blended.current_price 都有，标尺上画得出「现价」竖线（本版新增）；
 *     ② comps.target 没有倍数 → 现在 comps.implied_value_per_share 直接给出
 *        每种倍数推出来的每股价值，不必 E 自己乘；
 *     ③ 没有 WACC × g 的敏感性矩阵 → 现在 dcf.sensitivity.matrix 是 5×5 现成的。
 *   另外 D 还多给了三块旧契约里根本没有的东西：blended（融合估值）、
 *   scenarios（三情景）、dcf.forecast[]（逐年预测）。本页按「D 有就渲染」处理。
 *
 *   所以「A/B/C/D 没有的部分从 E 撤掉」在这页的具体含义是：
 *   删掉三个画不出来的降级分支、删掉所有对 C 的字段名引用，
 *   同时把 spec 换成**现在真的还缺的那几条**（见 spec）。
 *
 * 【版式定案 2026-10-10，2026-10-13 修订】
 *   1. 顺序是「结论 → 证据 → 细节」：
 *      ① 融合估值头条（D 的 blended，三个大数）
 *      ② 估值标尺（两条区间 + 现价竖线）
 *      ③ 两法细节（可比公司表 / DCF 假设）
 *      ④ 逐年预测与敏感性
 *      旧版把标尺放第一，因为当时没有 blended。现在有了 ——
 *      「贵还是便宜」这个问题有直接答案，让人先看到答案再去看推导。
 *   2. 标尺用 DOM + CSS 画，不用 Chart.js。三条理由：
 *      ① 浮动条 + 贯穿网格 + 跨行阴影，在 canvas 里要靠自定义插件，DOM 里
 *         就是几个绝对定位的 div；② 导出 PDF / 打印时 DOM 清晰、canvas 发虚；
 *      ③ 条形上的文字是真实文本，可选中、可被测试断言。
 *      代价是没有 tooltip —— 所以所有数值都直接写在行头上，不需要悬停。
 *   3. 本页零 tone。估值高低不是涨跌，用不到红涨绿跌。详见 css/base.css 顶部。
 *   4. 颜色只用 status/primary 系统，**不新造第二种"方法色"**。
 *      两条区间条长得一样，靠位置区分；视觉重点是重叠段，不是"哪条是哪条"。
 *      给 DCF 单独配一个颜色会暗示它有独立语义，而它没有。
 *
 * 【E 不重算估值 —— 本页的四种运算全是绘制行为】
 *   ① 刻度选择与取整（niceScale / logScale）—— 与画柱状图要算坐标同类
 *   ② 两条已给区间的重叠段（overlapOf）
 *   ③ 标尺上「现价」竖线的左右位置
 *   ④ 把 D 已给的数值按显示口径格式化（元 → 亿元、小数 → 百分数）
 *   以上都不产出新的估值结论。结论性的句子一律引用 D 的原文（warnings / verdict）。
 * ==========================================================================*/

(function () {
  "use strict";
  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  /* 两种方法的固定身份。key 必须与 valuation 下的字段名一致。 */
  var METHODS = [
    { key: "comps", label: "Comps 相对估值", tag: "可比公司法" },
    { key: "dcf",   label: "DCF 绝对估值",   tag: "现金流折现法" }
  ];

  /* 两法区间跨度到这个倍数，线性刻度就没法用了 —— 见 chooseScale。 */
  var LOG_THRESHOLD = 10;

  F.pages.p5 = {
    id: "p5",
    index: 5,
    title: "估值分析",
    subtitle: "Valuation",

    spec: [
      "两法区间跨度 60 倍（相对估值 413.91–660.13，DCF 1,267.32–24,654.14）——"
        + "线性刻度下窄的那条会被压成一根看不见的线，本页改用对数刻度并在标尺上标注。"
        + "根因写在 D 的 warnings 里：WACC − 永续增长只有 1.63%，分母太小把 Gordon 终值放大了，"
        + "请 D 复核这个折现率假设",
      "valuation.comps.peer_multiples 与 implied_value_per_share 只填了 PE / PS 两个中点，"
        + "PB、EV/EBITDA 全空 —— 可比公司表里那两列有值，推出来的每股价值却没有。"
        + "本页按「有则渲染、无则整格不放」处理，不留空位",
      "blended.weight_source 写的是「默认权重：DCF 50% / 相对估值 50%」——"
        + "权重是 D 给的，本页照搬不调。若将来要按可信度加权，需要 D 给出权重的依据"
        + "（现在两法差 333%，等权平均把两头的分歧摊平了）",
      "valuation.sotp 是 {ok:false, skipped:true}，本页「不单列一块」："
        + "D 的 valuation.warnings[] 里已经有同一句话，同一句在一屏出现两次是噪声",
      "★ valuation 下的「金额」字段一个 unit 都没有：comps.inputs.*、"
        + "dcf.inputs.revenue_base、dcf.forecast[].*、dcf.terminal_assumptions.*、"
        + "blended.*、scenarios.*.equity_value 全都没有单位声明。"
        + "对照之下，Schema 对 company.amount_unit 与 financials.*.unit 都写了「元」，"
        + "而 valuation 里唯一带单位的是 comps/dcf.valuation_range.currency（值「元/股」）——"
        + "那是「每股价格」的单位，管不到上面这些总额。"
        + "本页现在按 D 自己在 memo 里的写法推定是「元」，再换算成亿元显示（刻度换算，不是重算）。"
        + "请 D 要么补 unit 字段，要么在 Schema 里写明 valuation 的金额一律为元 ——"
        + "「推定」在演示现场解释不清。",
      "同上的另一面：valuation.*.valuation_range 的键叫 「currency」，"
        + "financials.* 的叫 「unit」 —— 同一份 Schema 里两套词。"
        + "E 侧两条都接了（currency 优先、退化到 unit），但接口应该只有一种写法"
    ],

    /* 导出给测试：刻度算法是这页唯一的数学，值得单独覆盖 */
    scale: niceScale,
    logScale: logScale,
    chooseScale: chooseScale,

    render: function (root) {
      var ui = F.ui, fmt = F.fmt, data = F.data;

      root.appendChild(ui.section(
        this.title,
        "相对估值（可比公司法）与绝对估值（现金流折现法）的区间对比。"
             + "两条区间画在同一把价格尺上，重叠段即两种方法都认可的价位；"
             + "竖线是现价 —— 区间落在竖线哪一侧，就是高估还是低估。"
      ));

      var v = data.get("valuation", null);

      /* ★ 判的是「里面有没有料」，不是「对象在不在」。
         dataLoader 的 normalize() 会把 valuation 补成 {}（它给 company /
         financials / ratios 也这么补，好让各页不用到处写 if）。于是
         `if (!v)` 永远为假 —— 下面这段空态**一次也走不到**，
         而 D 整块没交时页面会摊开四张各说各话的空卡（结论、标尺、Comps、DCF），
         正好是「又出图又出空卡」。改成看三个子块在不在。 */
      var hasValuation = !!v && !!(v.blended || v.comps || v.dcf);
      if (!hasValuation) {
        root.appendChild(ui.empty(
          "估值块未提供（valuation 缺失）。本页读的是 D 的统一数据对象，"
               + "该对象未加载或 D 未产出估值块。"));
        root.appendChild(this.specCard(ui));
        return;
      }

      /* ① 结论：D 的 blended */
      root.appendChild(conclusionCard(ui, fmt, v));

      /* ② 标尺 */
      root.appendChild(rulerCard(ui, fmt, v));

      /* ③ 两法细节 */
      var cols = ui.el("div", "two-col");
      cols.appendChild(compsCard(ui, fmt, v.comps));
      cols.appendChild(dcfCard(ui, fmt, v.dcf));
      root.appendChild(cols);

      /* ④ DCF 逐年预测 */
      var fc = forecastCard(ui, fmt, v.dcf);
      if (fc) root.appendChild(fc);

      /* ⑤ 敏感性与三情景 */
      var sens = sensitivityCard(ui, fmt, v);
      if (sens) root.appendChild(sens);

      /* ⑥ 告警与来源 */
      var tail = warningsCard(ui, fmt, v);
      if (tail) root.appendChild(tail);

      /* ⑦ 待办 */
      root.appendChild(this.specCard(ui));
    },

    /* 本页待办卡。和其它五页一样带 .dev-card ——
       打包时由 index.html 的 window.FINSCOPE_DEMO 统一隐藏，不各页各摘一遍。 */
    specCard: function (ui) {
      var block = ui.card("dev-card");
      block.appendChild(ui.subhead("本页待办 / 待确认"));
      block.appendChild(ui.todoList(this.spec));
      block.appendChild(ui.note(
        "本页渲染的是 D 的统一数据对象（data/real_data.js，由 tools/build-data.js "
             + "从 D 的交付物原样搬运）。E 不重算任何估值：标尺的刻度、重叠段、"
             + "现价竖线的位置都是绘制行为，数字本身全部来自 D。", "info"));
      return block;
    }
  };

  /* ==================================================================== */
  /* 数值规整                                                              */
  /* ==================================================================== */

  function num(v) {
    if (v === null || v === undefined || v === "") return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  /* 每股价值的显示值，统一走 fmt.price（2 位小数 + 千分位 + 元/股）。
     矩阵和表格里用 fmt.grouped（只补千分位，单位在表头写一次）。 */
  function ps(fmt, v) { return fmt.price(v); }
  function cell(fmt, v) { return fmt.grouped(v, 2); }

  /* 金额：D 的 valuation 里所有钱都是**原始元**，而且底下**没有逐字段的
     unit**（Schema 只对 company.amount_unit 和 financials.*.unit 声明了「元」，
     valuation 下的钱一个单位字段都没有）。
     ------------------------------------------------------------------
     ★ 这里踩过一个坑，写下来免得再犯：
       直接把裸数丢给 fmt.money()，它会走默认单位「亿元」，于是
       dcf.inputs.revenue_base = 168838102514.79 显示成
       "168,838,102,514.8 亿元" —— 差了整整一亿倍，而且看起来还挺像个数。
       fmt.money 认单位，所以**必须把单位补上再交给它**。
     单位取「元」的依据：同一批数字（revenue_base 与 comps.inputs.revenue
     是同一个 168838102514.79）在 D 自己的投研简报里写成「1,688.38 亿元」，
     E 跟着 D 的口径走。这不是 E 重算数据，是显示刻度 —— 与股 → 亿股同类。 */
  function moneyOf(fmt, v) {
    var n = num(v);
    return n === null ? null : fmt.money({ value: n, unit: "元" });
  }

  /**
   * 把 D 的 valuation_range 规整成可画的形式。
   * 返回 null 表示「画不了」—— 这时候宁可整条落选，也不猜一个值出来。
   *
   * ★ 2026-10-13：单位从 r.unit 改成 r.currency。
   *   D 的字段名就是 currency（"元/股"），旧代码读 unit 读的是 C 的口径。
   *   两个都认是有意的：只要将来谁改回 unit，这页不会静默丢掉单位。
   */
  function normaliseRange(r) {
    if (!r || typeof r !== "object") return null;
    var low = num(r.low), high = num(r.high), mid = num(r.mid);
    if (low === null || high === null) return null;

    var reversed = false;
    if (low > high) {                       /* 数据写反了：照样画，但要报出来 */
      var t = low; low = high; high = t;
      reversed = true;
    }
    var unit = (typeof r.currency === "string" && r.currency)
            || (typeof r.unit === "string" && r.unit) || null;
    return { low: low, high: high, mid: mid, unit: unit, reversed: reversed };
  }

  /* ==================================================================== */
  /* 刻度                                                                  */
  /* ==================================================================== */
  /* 纯函数，好测。选 1 / 2 / 2.5 / 5 / 10 × 10^k 作步长 —— 这样刻度上
     出现的都是 12.5、15、17.5 这种读得下去的数，不会冒出 13.37。 */
  function niceScale(lo, hi, wantTicks) {
    wantTicks = wantTicks || 5;
    lo = num(lo);
    hi = num(hi);
    if (lo === null || hi === null) return null;
    if (lo > hi) { var t = lo; lo = hi; hi = t; }

    var span = hi - lo;
    if (!(span > 0)) {
      /* 区间退化成一个点（low === high）：人为撑开，否则除零 */
      var pad0 = Math.abs(lo) * 0.1 || 1;
      lo -= pad0; hi += pad0; span = hi - lo;
    }

    /* 两端各留 5% 余量，条形不会顶到尺子边缘 */
    var pad = span * 0.05;
    lo -= pad; hi += pad;
    span = hi - lo;

    var raw = span / wantTicks;
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / mag;
    var stepUnit = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
    var step = stepUnit * mag;

    var min = Math.floor(lo / step) * step;
    var max = Math.ceil(hi / step) * step;

    var ticks = [];
    for (var x = min; x <= max + step * 1e-9; x += step) {
      ticks.push(Math.round(x * 1e6) / 1e6);     /* 抹掉浮点累加的尾数 */
    }
    return {
      min: min, max: max, step: step, ticks: ticks, log: false,
      pos: linearPos(min, max)
    };
  }

  /* 对数刻度：等比的量要在同一把尺上比，只能取对数。
     刻度取 1 / 2 / 5 × 10^k —— 与 niceScale 同一套「读得下去的数」原则。 */
  function logScale(lo, hi) {
    lo = num(lo); hi = num(hi);
    if (lo === null || hi === null) return null;
    if (lo > hi) { var t = lo; lo = hi; hi = t; }
    if (!(lo > 0)) return null;              /* 对数刻不容 0 与负数 → 放弃 */
    if (lo === hi) { lo /= 2; hi *= 2; }

    var lmin = Math.log10(lo), lmax = Math.log10(hi);
    var pad = (lmax - lmin) * 0.05;
    lmin -= pad; lmax += pad;

    var ticks = [];
    var dmin = Math.pow(10, lmin), dmax = Math.pow(10, lmax);
    for (var e = Math.floor(lmin); e <= Math.ceil(lmax); e++) {
      [1, 2, 5].forEach(function (m) {
        var val = m * Math.pow(10, e);
        if (val >= dmin && val <= dmax) ticks.push(val);
      });
    }
    var lg = function (x) { return x > 0 ? Math.log10(x) : lmin; };
    return {
      min: dmin, max: dmax, ticks: ticks, log: true,
      pos: function (x) { return (lg(x) - lmin) / (lmax - lmin) * 100; }
    };
  }

  function linearPos(min, max) {
    var span = max - min;
    return function (x) { return (x - min) / span * 100; };
  }

  /**
   * 选刻度类型。
   *
   * ★ 为什么需要这一步（不是炫技，是这页能不能读的问题）：
   *   600519 的相对估值是 413.91–660.13，DCF 是 1,267.32–24,654.14，
   *   跨度 60 倍。线性刻度下那条相对估值的条只有整幅宽度的 **0.95%** ——
   *   视觉上等于不存在，而它恰恰是这页要展示的两条之一。
   *   对数刻度下两条都看得见（相对估值约 11% 宽，DCF 约 71%）。
   *
   *   这是**坐标轴的选择**（与 niceScale 取整同类），不是重新估值；
   *   标尺上会明确标出「对数刻度」，不会让读者误读成线性比例。
   *   两个区间量级相当（跨度 < 10 倍）时仍走线性 —— 那才是默认读法。
   */
  function chooseScale(lo, hi) {
    var a = num(lo), b = num(hi);
    if (a === null || b === null) return null;
    if (a > b) { var t = a; a = b; b = t; }
    if (a > 0 && b / a >= LOG_THRESHOLD) return logScale(a, b);
    return niceScale(a, b, 5);
  }

  /* 数值显示：留够精度再抹掉末尾的 0。
     直接用步长的小数位去格式化会出事 —— 步长 2.5 时 15.8 会被舍成 15.8→没问题，
     但 20.15 会被舍成 20.2，精度就丢了。所以统一按 4 位格式化再 trim：
     15.8 → "15.8"，20 → "20"，20.15 → "20.15"。 */
  function trimNum(fmt, v) {
    var s = fmt.num(v, 4);
    if (s === fmt.MISSING) return s;
    if (s.indexOf(".") >= 0) s = s.replace(/0+$/, "").replace(/\.$/, "");
    return s;
  }

  /* 刻度标签：先 trim 再补千分位 —— 对数的 10000 该读作 "10,000" */
  function tickLabel(fmt, v) {
    return fmt.group(trimNum(fmt, v));
  }

  /* 两个区间的重叠段；不重叠返回 null（那是个结论，不是错误） */
  function overlapOf(a, b) {
    var lo = Math.max(a.low, b.low);
    var hi = Math.min(a.high, b.high);
    return hi > lo ? { low: lo, high: hi } : null;
  }

  /* ==================================================================== */
  /* ① 结论：D 的 blended                                                  */
  /* ==================================================================== */
  /* D 原话（写进 contract.js 的注释里）：「融合每股价值、相对现价的上行空间、
     低估或高估的结论，**E 页面的头条数字**，最有用的一块」。
     所以这一块排在最前 —— 先回答「贵还是便宜」，再给推导。 */
  function conclusionCard(ui, fmt, v) {
    var box = ui.card();
    box.appendChild(ui.subhead("估值结论"));

    var b = v.blended;
    var md = v.market_data || null;

    if (!b || (b.blended_per_share === null && b.current_price === null && b.upside === null)) {
      box.appendChild(ui.empty("融合估值未提供（valuation.blended 全空）。"));
      box.appendChild(ui.note(
        "blended 是导出量：行情或可比公司缺任一样，它就为空。"
             + "D 在 valuation.warnings 里写了原因，见本页末尾「估值告警」。", "info"));
      return box;
    }

    /* --- 三个大数 --- */
    /* 落点走 .ro-stats：只有字号没有背景，是全站「大而不用玻璃」的唯一写法。
       顺序就是读的顺序：D 的结论每股价值多少 → 现在卖多少 → 差多少。 */
    var stats = ui.el("div", "ro-stats");
    [
      ["融合每股价值", b.blended_per_share],
      ["当前股价", b.current_price],
      ["相对现价空间", b.upside]
    ].forEach(function (pair) {
      if (pair[1] === null || pair[1] === undefined) return;
      var it = ui.el("div", "ro-item");
      var isPct = pair[0] === "相对现价空间";
      it.appendChild(ui.el("span", "ro-num",
        isPct ? fmt.signedPercent(pair[1]) : cell(fmt, pair[1])));
      it.appendChild(ui.el("span", "ro-label",
        isPct ? pair[0] : pair[0] + "（元/股）"));
      stats.appendChild(it);
    });
    box.appendChild(stats);

    /* --- 口径一行：结论、现价日期、权重来源 --- */
    var line = ui.el("div", "v-target");
    line.appendChild(ui.el("span", "v-target-label", "口径"));
    [
      ["结论", b.verdict],
      ["现价日期", md && md.price_date],
      ["每股价值单位", v.dcf && v.dcf.valuation_range && v.dcf.valuation_range.currency],
      ["权重来源", b.weight_source]
    ].forEach(function (pair) {
      if (pair[1] === null || pair[1] === undefined || pair[1] === "") return;
      var it = ui.el("span", "v-target-item");
      it.appendChild(ui.el("span", "v-target-k", pair[0]));
      it.appendChild(ui.el("span", "v-target-v", String(pair[1])));
      line.appendChild(it);
    });
    box.appendChild(line);

    /* --- 估值构成：融合数是怎么拼出来的 --- */
    /* 这一段是这页最该有的东西 —— 它让「1,431.30」不再是凭空一个数：
       一半来自 DCF（2,325.59），一半来自相对估值（537.02），
       两法差 4.3 倍，等权一摊就成了 1,431.30。
       权重与每股价值都是 D 给的，E 不做除法、不校验它们是否自洽。 */
    if (b.components && b.components.length) {
      var tb = ui.el("table", "mini-table");
      var thead = ui.el("thead");
      var hr = ui.el("tr");
      ["估值方法", "每股价值（元/股）", "权重", "隐含股权价值（亿元）"].forEach(function (h) {
        hr.appendChild(ui.el("th", null, h));
      });
      thead.appendChild(hr);
      tb.appendChild(thead);

      var tbody = ui.el("tbody");
      b.components.forEach(function (c) {
        var tr = ui.el("tr");
        tr.appendChild(ui.el("td", "strong", fmt.text(c.label)));
        tr.appendChild(ui.el("td", "num metric-value", ps(fmt, c.per_share)));
        tr.appendChild(ui.el("td", "num",
          c.weight === null || c.weight === undefined ? fmt.MISSING : fmt.percent(c.weight)));
        tr.appendChild(ui.el("td", "num", moneyOf(fmt, c.equity_value) || fmt.MISSING));
        tbody.appendChild(tr);
      });

      /* 融合合计行。blended_equity_value 是 D 给的，不是 E 把上面两行加起来。 */
      var sum = ui.el("tr");
      sum.appendChild(ui.el("td", "strong", "融合"));
      sum.appendChild(ui.el("td", "num metric-value", ps(fmt, b.blended_per_share)));
      sum.appendChild(ui.el("td", "num", "100.0%"));
      sum.appendChild(ui.el("td", "num", moneyOf(fmt, b.blended_equity_value) || fmt.MISSING));
      tbody.appendChild(sum);

      tb.appendChild(tbody);
      box.appendChild(tb);

      if (b.most_bullish || b.most_bearish) {
        box.appendChild(ui.note(
          "D 的标注：" + (b.most_bullish ? "最乐观的是「" + b.most_bullish + "」" : "")
               + (b.most_bearish ? "，最保守的是「" + b.most_bearish + "」" : "") + "。", "info"));
      }
    }
    return box;
  }

  /* ==================================================================== */
  /* ② 估值标尺                                                            */
  /* ==================================================================== */
  function rulerCard(ui, fmt, v) {
    var box = ui.card();
    box.appendChild(ui.subhead("估值区间对比"));

    var rows = [];
    var problems = [];
    METHODS.forEach(function (m) {
      var mod = v[m.key];
      var raw = mod && mod.valuation_range;
      var r = normaliseRange(raw);
      if (r) {
        r.label = m.label;
        r.tag = m.tag;
        rows.push(r);
      } else if (raw && (raw.low !== null || raw.high !== null)) {
        problems.push(m.label + " 的 valuation_range 缺 low / high，画不了标尺。");
      }
    });

    if (!rows.length) {
      box.appendChild(ui.empty(
        "两条估值区间都未提供（valuation.comps.valuation_range 与 "
             + "valuation.dcf.valuation_range 都没有 low / high）。"
             + "D 会在 valuation.warnings 里说明原因，见本页末尾。"));
      if (problems.length) box.appendChild(ui.note(problems.join(" "), "warn"));
      return box;
    }

    /* --- 单位口径：必须一致，且必须给出来 --- */
    var units = rows.map(function (r) { return r.unit; });
    var sameUnit = units.every(function (u) { return u === units[0]; });
    var unit = sameUnit ? units[0] : null;

    if (!sameUnit) {
      /* 单位不一致绝不能硬画 —— 那等于把两把不同刻度的尺子叠在一起 */
      box.appendChild(ui.note(
        "两条区间的单位不一致（" + units.map(function (u, i) {
          return rows[i].label + "：" + (u || "未标注");
        }).join("；") + "），无法画在同一把尺上。", "warn"));
      box.appendChild(rangeFallbackTable(ui, fmt, rows));
      return box;
    }
    if (!unit) {
      box.appendChild(ui.note(
        "valuation.*.valuation_range.currency 缺失 —— 本页不知道这些数字是"
             + "「元/股」还是「亿元总市值」，两种口径下图与结论都不是一回事。"
             + "已按无单位渲染。", "warn"));
    }

    /* 现价：D 给了才画。blended.current_price 与 market_data.price 是同一个数，
       前者在、后者缺时说得出「现价是多少但不知道是哪天的」，所以优先前者。 */
    var price = num(v.blended && v.blended.current_price);
    if (price === null) price = num(v.market_data && v.market_data.price);
    var priceDate = (v.market_data && v.market_data.price_date) || null;

    box.appendChild(ruler(ui, fmt, rows, unit, price, priceDate));
    box.appendChild(legend(ui, fmt, rows, unit, price));

    if (problems.length) box.appendChild(ui.note(problems.join(" "), "warn"));
    return box;
  }

  /* ---------------------------------------------------------------------
     标尺本体
     ---------------------------------------------------------------------
     分层顺序是这页的关键，写下来免得后面改坏：
       .vr-band       z-index 0 —— 最底层的重叠阴影
       .vr-track      **必须透明** —— 一旦给它填色，压在它下面的阴影就全被挡住了，
                                   整页的落点会无声消失（这个坑踩过一次）
       .vr-bar        半透明填充，压在两者之上 —— 重叠处 band+bar 自然更深
       .vr-dot        在条内，位置按 (mid-low)/(high-low) 换算
       .vr-priceline  在条内、**只在轨道高度内** —— 见下面注释
     行头文字（方法名 + 区间值）直接写出来，不靠 tooltip —— 这是不用 canvas
     换来的代价，也是它的好处：所有数字都是可选中的真文本，打印清晰。 */
  function ruler(ui, fmt, rows, unit, price, priceDate) {
    /* 刻度域 = 两条区间 ∪ 现价。
       现价必须进定义域，否则它可能落在尺子外面 —— 「比区间高还是低」
       正是这条线要回答的问题，画到框外就白画了。 */
    var lo = Math.min.apply(null, rows.map(function (r) { return r.low; }));
    var hi = Math.max.apply(null, rows.map(function (r) { return r.high; }));
    if (price !== null) { lo = Math.min(lo, price); hi = Math.max(hi, price); }

    var sc = chooseScale(lo, hi);
    /* sc 为 null 只可能发生在数值不是有效数字时，而那种行已经被
       normaliseRange 滤掉了。留个兜底，免得万一崩掉整页。 */
    if (!sc) return ui.note("刻度计算失败：区间数值不是有效数字。", "warn");

    /* 位置一律取 2 位小数再拼进 inline style。
       不这样做的话会写出 left:16.666666666666664% 这种噪声，虽然浏览器能认，
       但审查代码和读数时都是干扰。 */
    var pos = function (x) { return Math.round(sc.pos(x) * 100) / 100; };

    var box = ui.el("div", "vr");

    /* --- 单位与刻度说明 + 现价图例 --- */
    var cap = ui.el("div", "vr-unit");
    var parts = ["单位：" + (unit || "未标注")];
    if (sc.log) parts.push("刻度：对数（两法区间跨度过大，线性刻度会让窄的那条消失）");
    if (price !== null) {
      parts.push("竖线＝现价 " + ps(fmt, price) + (priceDate ? "（" + priceDate + "）" : ""));
    }
    cap.textContent = parts.join("　·　");
    box.appendChild(cap);

    /* --- 刻度条 --- */
    var tickStrip = ui.el("div", "vr-ticks");
    sc.ticks.forEach(function (t, i) {
      var cls = "vr-tick";
      if (i === 0) cls += " is-first";
      if (i === sc.ticks.length - 1) cls += " is-last";
      var lab = ui.el("span", cls, tickLabel(fmt, t));
      lab.style.left = pos(t) + "%";
      tickStrip.appendChild(lab);
    });
    box.appendChild(tickStrip);

    /* --- 绘图区：网格线 + 重叠带 + 两行区间条 --- */
    var plot = ui.el("div", "vr-plot");

    var grid = ui.el("div", "vr-grid");
    sc.ticks.forEach(function (t) {
      var g = ui.el("span", "vr-gridline");
      g.style.left = pos(t) + "%";
      grid.appendChild(g);
    });
    plot.appendChild(grid);

    /* 重叠段：画在最底层，两条半透明的区间条压上去，
       重叠处的颜色自然更深 —— 这就把「两个方法都认这个价」画出来了。 */
    var ov = null;
    if (rows.length === 2) ov = overlapOf(rows[0], rows[1]);
    if (ov) {
      var band = ui.el("div", "vr-band");
      band.style.left = pos(ov.low) + "%";
      band.style.width = (pos(ov.high) - pos(ov.low)) + "%";
      plot.appendChild(band);
    }

    var list = ui.el("div", "vr-rows");
    rows.forEach(function (r) {
      var row = ui.el("div", "vr-row");

      var head = ui.el("div", "vr-row-head");
      head.appendChild(ui.el("span", "vr-name", r.label));
      var vals = ui.el("span", "vr-vals");
      vals.appendChild(ui.el("span", "vr-range",
        cell(fmt, r.low) + " – " + cell(fmt, r.high) + (unit ? " " + unit : "")));
      if (r.mid !== null) {
        vals.appendChild(ui.el("span", "vr-mid", "中枢 " + cell(fmt, r.mid)));
      }
      head.appendChild(vals);
      row.appendChild(head);

      var track = ui.el("div", "vr-track");

      /* 现价竖线画在**轨道里**，不贯穿整幅高度：
         贯穿全高会从行头的方法名和区间值上切过去，读的时候正是干扰。
         位置与网格线同一套 pos()，所以线和刻度是对齐的。 */
      if (price !== null) {
        var pl = ui.el("span", "vr-priceline");
        pl.style.left = pos(price) + "%";
        track.appendChild(pl);
      }

      var bar = ui.el("div", "vr-bar");
      bar.style.left = pos(r.low) + "%";
      bar.style.width = (pos(r.high) - pos(r.low)) + "%";
      /* 中枢点：画在条内，位置按 (mid-low)/(high-low) 换算 */
      if (r.mid !== null && r.high > r.low) {
        var dot = ui.el("span", "vr-dot");
        dot.style.left = (Math.round((r.mid - r.low) / (r.high - r.low) * 10000) / 100) + "%";
        bar.appendChild(dot);
      }
      track.appendChild(bar);
      row.appendChild(track);
      list.appendChild(row);
    });
    plot.appendChild(list);
    box.appendChild(plot);

    if (rows.some(function (r) { return r.reversed; })) {
      box.appendChild(ui.note(
        "有区间的 low 大于 high（数据疑似写反），标尺已按大小顺序画，"
             + "但请核对原始数据。", "warn"));
    }
    return box;
  }

  /* 标尺下面的图例：把「阴影是什么」写成一句话，不让读者猜 */
  function legend(ui, fmt, rows, unit, price) {
    var lg = ui.el("div", "vr-legend");
    var suf = unit ? " " + unit : "";

    if (rows.length === 2) {
      var ov = overlapOf(rows[0], rows[1]);
      if (ov) {
        lg.appendChild(ui.el("span", "vr-legend-key is-band"));
        var txt = ui.el("span", "vr-legend-text");
        txt.appendChild(ui.el("strong", null,
          "两法重叠 " + cell(fmt, ov.low) + " – " + cell(fmt, ov.high) + suf));
        txt.appendChild(ui.el("span", "dim",
          "　两种估值方法都覆盖的价位，可信度相对更高"));
        lg.appendChild(txt);
      } else {
        /* ★ 用局部变量而不是 lg.lastChild —— 上一步刚 append 进去就回头取
           lastChild 是能跑，但那让这一段的正确性取决于「前面一行没被改」。
           直接拿着引用，改起来不会断。 */
        var ntxt = ui.el("span", "vr-legend-text");
        ntxt.appendChild(ui.el("strong", null, "两条区间不重叠："));
        ntxt.appendChild(ui.el("span", null,
          rows[0].label + " " + cell(fmt, rows[0].low) + " – " + cell(fmt, rows[0].high) + suf
            + "，"
            + rows[1].label + " " + cell(fmt, rows[1].low) + " – " + cell(fmt, rows[1].high) + suf
            + "，中间没有交集。市场法与绝对法给出的结论分歧到这个程度，"
            + "本身就是个值得讲的发现 —— D 已把它记进 warnings。"));
        lg.appendChild(ntxt);
      }
    } else {
      lg.appendChild(ui.el("span", "vr-legend-text dim",
        "当前只有一种方法的区间（另一种的 valuation_range 没有 low / high）。"
             + "单法区间照样能对着现价读高低。"));
    }

    /* 现价落在哪：这是标尺唯一的「结论性」读法，且完全是几何事实，
       不含 E 的判断 —— 竖线在条左侧就是区间高于现价，反之亦然。 */
    if (price !== null && rows.length) {
      var below = rows.filter(function (r) { return r.low > price; });
      var above = rows.filter(function (r) { return r.high < price; });
      var cover = rows.filter(function (r) { return r.low <= price && price <= r.high; });
      var seg = [];
      if (below.length) seg.push(below.map(function (r) { return r.label; }).join("、") + " 整段高于现价");
      if (cover.length) seg.push(cover.map(function (r) { return r.label; }).join("、") + " 覆盖现价");
      if (above.length) seg.push(above.map(function (r) { return r.label; }).join("、") + " 整段低于现价");
      if (seg.length) {
        lg.appendChild(ui.el("span", "vr-legend-text dim", "　现价 " + ps(fmt, price) + "：" + seg.join("；") + "。"));
      }
    }
    return lg;
  }

  /* 单位不一致时的降级：画不了尺子，就把两条区间并排列出来 */
  function rangeFallbackTable(ui, fmt, rows) {
    var tb = ui.el("table", "mini-table");
    var thead = ui.el("thead");
    var hr = ui.el("tr");
    ["方法", "区间", "中枢", "单位"].forEach(function (h) {
      hr.appendChild(ui.el("th", null, h));
    });
    thead.appendChild(hr);
    tb.appendChild(thead);

    var tbody = ui.el("tbody");
    rows.forEach(function (r) {
      var tr = ui.el("tr");
      tr.appendChild(ui.el("td", "strong", r.label));
      tr.appendChild(ui.el("td", "num metric-value",
        cell(fmt, r.low) + " – " + cell(fmt, r.high)));
      tr.appendChild(ui.el("td", "num", r.mid === null ? fmt.MISSING : cell(fmt, r.mid)));
      tr.appendChild(ui.el("td", "dim", r.unit || fmt.MISSING));
      tbody.appendChild(tr);
    });
    tb.appendChild(tbody);
    return tb;
  }

  /* ==================================================================== */
  /* ③ 两栏细节                                                            */
  /* ==================================================================== */

  /* 一行多格的键值条。值为空的格整格不出现 —— 一排「—」比少一格更难看，
     而且会让人以为「这里该有数但没取到」，其实那项对这家公司没意义
     （如茅台没有 EBITDA / 净债务）。 */
  function strip(ui, headLabel, pairs) {
    var keep = pairs.filter(function (p) {
      return p[1] !== null && p[1] !== undefined && p[1] !== "";
    });
    if (!keep.length) return null;
    var line = ui.el("div", "v-target");
    line.appendChild(ui.el("span", "v-target-label", headLabel));
    keep.forEach(function (p) {
      var it = ui.el("span", "v-target-item");
      it.appendChild(ui.el("span", "v-target-k", p[0]));
      it.appendChild(ui.el("span", "v-target-v", String(p[1])));
      line.appendChild(it);
    });
    return line;
  }

  /* 可比公司法。D 给了三样旧契约没有的东西：inputs（估值对象）、
     implied_value_per_share（每种倍数推出的每股价值）、peer_multiples（同行中位数）。
     旧版最缺的「本公司比同行贵还是便宜」这一行，现在直接用 implied 表回答。 */
  function compsCard(ui, fmt, comps) {
    var box = ui.card();
    box.appendChild(ui.subhead("相对估值 Comps"));

    if (!comps) {
      box.appendChild(ui.empty("Comps 数据未提供。"));
      return box;
    }

    /* --- 估值对象 --- */
    var inp = comps.inputs || {};
    var obj = strip(ui, "估值对象", [
      ["营业收入", moneyOf(fmt, inp.revenue)],
      ["归母净利润", moneyOf(fmt, inp.net_income)],
      /* 股 → 亿股：D 给的是原始股数（1,252,270,215 股），除以 1e8 再显示。
         与 moneyOf 把「元」归一到「亿元」同性质 —— 单位换算是显示刻度，
         不是重新算数据。（D 的 shares_unit 已注明单位是「股」。） */
      ["总股本", num(inp.shares_outstanding) === null
                   ? null : fmt.grouped(inp.shares_outstanding / 1e8, 2) + " 亿股"],
      ["市值", moneyOf(fmt, inp.market_cap)],
      ["股价", num(inp.share_price) === null ? null : ps(fmt, inp.share_price)]
    ]);
    if (obj) box.appendChild(obj);

    /* --- 倍数法推出来的每股价值 --- */
    /* 这张表是「本公司相对同行贵还是便宜」的答案本身：
       用同行的 PE 中位数乘本公司的盈利，得到 660.13 元/股。
       数值全部来自 D 的 implied_value_per_share，E 不做乘法。 */
    var imp = comps.implied_value_per_share || null;
    var impRows = [];
    if (imp) {
      [["pe", "PE"], ["pb", "PB"], ["ps", "PS"], ["ev_ebitda", "EV/EBITDA"]].forEach(function (m) {
        var o = imp[m[0]];
        if (!o) return;
        var mid = num(o.mid), lo = num(o.low), hi = num(o.high);
        if (mid === null && lo === null && hi === null) return;
        var med = comps.peer_multiples && comps.peer_multiples[m[0]]
                ? num(comps.peer_multiples[m[0]].median) : null;
        impRows.push([
          { text: m[1], cls: "strong" },
          { text: med === null ? fmt.MISSING : fmt.multiple(med), cls: med === null ? "dim" : "num" },
          { text: mid === null ? fmt.MISSING : ps(fmt, mid), cls: mid === null ? "dim" : "num metric-value" },
          { text: (lo === null && hi === null) ? fmt.MISSING
                  : (lo === null ? "≤ " : cell(fmt, lo) + " – ") + (hi === null ? "" : cell(fmt, hi)), cls: "num dim" }
        ]);
      });
    }
    if (impRows.length) {
      box.appendChild(ui.el("div", "block-sub", "同行倍数推出的每股价值"));
      /* ★ 2026-10-13：这张表和下面的「可比公司」原来是本卡里**唯一两张
         没套 .table-scroll 的表**。窄屏（vw ≈1050–1130）卡内容区只剩 276px，
         6 列挤不下时它们不会滚，而是从卡片右边漏出去压住隔壁的 DCF 卡 ——
         用户报的「两个面板重合」。补上外层容器，与本卡其余表一致。 */
      box.appendChild(scrollWrap(ui, miniTable(ui, ["倍数", "同行中位数", "隐含每股价值（元/股）", "区间"], impRows)));
      box.appendChild(ui.note(
        "「隐含每股价值」是 D 用同行倍数算出来的，E 不做乘法。"
             + "只有填了中位数的倍数才有隐含值 —— 空的那几行不是算错，是同行样本不足。", "info"));
    }

    /* --- 可比公司明细 --- */
    var peers = comps.peer_companies;
    if (peers && peers.length) {
      box.appendChild(ui.el("div", "block-sub", "可比公司"));
      var rows = peers.map(function (p) {
        return [
          { text: fmt.text(p.name), cls: "strong" },
          { text: fmt.text(p.ticker), cls: "dim" },
          { text: fmt.multiple(p.pe), cls: "num" },
          { text: fmt.multiple(p.pb), cls: "num" },
          { text: fmt.multiple(p.ev_ebitda), cls: "num" },
          { text: fmt.multiple(p.ps), cls: "num" }
        ];
      });
      box.appendChild(scrollWrap(ui, miniTable(ui, ["可比公司", "代码", "PE", "PB", "EV/EBITDA", "PS"], rows)));
      box.appendChild(ui.note(
        "倍数口径（静态 / TTM / 前瞻）D 未标注。本表 5 家的倍数齐全，"
             + "但推出来的每股价值只有 PE 与 PS 两个 —— 差额在同行样本的聚合口径上。", "info"));
    } else {
      box.appendChild(ui.empty("可比公司清单未提供。"));
    }
    /* 这里**刻意不再重复一遍估值区间** —— 标尺的行头已经写了。
       两张卡回答的是「这个数怎么来的」，标尺回答「这个数在哪」，
       同一个数字在一屏里出现两次会稀释标尺的分量。 */
    return box;
  }

  /* 绝对估值法：买什么假设、这些假设把终值推到多重 */
  function dcfCard(ui, fmt, dcf) {
    var box = ui.card();
    box.appendChild(ui.subhead("绝对估值 DCF"));

    if (!dcf) {
      box.appendChild(ui.empty("DCF 数据未提供。"));
      return box;
    }

    var a = dcf.inputs || dcf.assumptions || null;
    if (a) {
      box.appendChild(ui.kv([
        ["WACC",        a.wacc === null || a.wacc === undefined ? fmt.MISSING : fmt.percent(a.wacc)],
        ["永续增长率",   a.terminal_growth === null || a.terminal_growth === undefined ? fmt.MISSING : fmt.percent(a.terminal_growth)],
        ["预测期",       a.forecast_years === null || a.forecast_years === undefined ? fmt.MISSING : a.forecast_years + " 年"],
        ["所得税率",     a.tax_rate === null || a.tax_rate === undefined ? fmt.MISSING : fmt.percent(a.tax_rate)],
        ["收入基数",     moneyOf(fmt, a.revenue_base) || fmt.MISSING],
        ["EBIT 利润率",  a.ebit_margin === null || a.ebit_margin === undefined ? fmt.MISSING : fmt.percent(a.ebit_margin)]
      ]));
    }

    /* 终值假设：DCF 的成败八成在这一格。
       tv_pct_of_ev（终值占企业价值 87%）是读者最该看到的一个数 ——
       它说明这个模型实质上是在押几年以后的事。 */
    var t = dcf.terminal_assumptions || null;
    if (t) {
      var pairs = [
        ["终值占企业价值", t.tv_pct_of_ev === null || t.tv_pct_of_ev === undefined ? fmt.MISSING : fmt.percent(t.tv_pct_of_ev)],
        ["永续期自由现金流", moneyOf(fmt, t.terminal_fcff)],
        ["终值（现值）", moneyOf(fmt, t.pv_terminal_value)],
        ["退出倍数", t.exit_multiple === null || t.exit_multiple === undefined ? fmt.MISSING : fmt.multiple(t.exit_multiple)]
      ];
      var line = strip(ui, "永续期假设", pairs);
      if (line) box.appendChild(line);

      /* 两种终值算法的偏离度 —— 这是 D 自己算的，也是它 warnings 的第一条。 */
      if (t.tv_gordon !== null && t.tv_gordon !== undefined
          && t.tv_exit !== null && t.tv_exit !== undefined) {
        var d = ui.el("div", "v-target");
        d.appendChild(ui.el("span", "v-target-label", "终值两种算法"));
        [["Gordon 增长模型", moneyOf(fmt, t.tv_gordon) || fmt.MISSING],
         ["退出倍数法", moneyOf(fmt, t.tv_exit) || fmt.MISSING],
         ["两者偏离", t.tv_divergence === null || t.tv_divergence === undefined
                        ? fmt.MISSING : fmt.percent(t.tv_divergence)]
        ].forEach(function (p) {
          var it = ui.el("span", "v-target-item");
          it.appendChild(ui.el("span", "v-target-k", p[0]));
          it.appendChild(ui.el("span", "v-target-v", p[1]));
          d.appendChild(it);
        });
        box.appendChild(d);
      }
    }

    box.appendChild(ui.note(
      "假设值由 D 给定，E 不调整。终值偏离与占比的具体判断见本页末尾「估值告警」"
           + "—— D 已经把这些写成告警了，这里不重述。", "info"));
    /* 同 compsCard：区间交给标尺，这里不重复 */
    return box;
  }

  /* ==================================================================== */
  /* ④ DCF 逐年预测                                                        */
  /* ==================================================================== */
  /* 放在整幅宽度上：六列数字在 half-width 里会挤成一团。
     这张表回答的是「DCF 的钱从哪几年折出来的」。 */
  function forecastCard(ui, fmt, dcf) {
    var list = dcf && dcf.forecast;
    if (!Array.isArray(list) || !list.length) return null;

    var box = ui.card();
    box.appendChild(ui.subhead("DCF 逐年预测"));

    var rows = list.map(function (f) {
      return [
        { text: f.year === null || f.year === undefined ? "第 " + f.year_index + " 年" : String(f.year), cls: "strong" },
        { text: f.growth === null || f.growth === undefined ? fmt.MISSING : fmt.signedPercent(f.growth), cls: "num" },
        { text: moneyOf(fmt, f.revenue) || fmt.MISSING, cls: "num" },
        { text: moneyOf(fmt, f.ebit) || fmt.MISSING, cls: "num" },
        { text: moneyOf(fmt, f.fcff) || fmt.MISSING, cls: "num" },
        { text: f.discount_factor === null || f.discount_factor === undefined ? fmt.MISSING : fmt.num(f.discount_factor, 3), cls: "num dim" },
        { text: moneyOf(fmt, f.pv_fcff) || fmt.MISSING, cls: "num metric-value" }
      ];
    });
    box.appendChild(miniTable(ui,
      ["年度", "收入增速", "营业收入（亿元）", "EBIT（亿元）",
       "自由现金流（亿元）", "折现因子", "现值（亿元）"], rows));
    box.appendChild(ui.note(
      "预测期内的现值合计只占 DCF 结论的一小部分 —— 剩下的大头在永续终值，"
           + "也就是上面「终值占企业价值」那一格。", "info"));
    return box;
  }

  /* ==================================================================== */
  /* ⑤ 敏感性与三情景                                                      */
  /* ==================================================================== */
  /* 两件事放一张卡：都在回答「结论对假设有多敏感」，只是问法不同 ——
     前者问「WACC 与永续增长各动 1%，每股价值怎么变」，
     后者问「三套打包好的假设各给出什么价」。 */
  function sensitivityCard(ui, fmt, v) {
    var s = v.dcf && v.dcf.sensitivity;
    var scen = v.scenarios;
    var hasSens = s && Array.isArray(s.matrix) && s.matrix.some(function (r) {
      return Array.isArray(r) && r.some(function (x) { return num(x) !== null; });
    });
    var hasScen = scen && ["bull", "base", "bear"].some(function (k) {
      var o = scen[k];
      return o && (num(o.per_share) !== null || num(o.equity_value) !== null);
    });
    if (!hasSens && !hasScen) return null;

    var box = ui.card();
    box.appendChild(ui.subhead("假设的敏感性"));

    /* --- 5×5 矩阵 --- */
    if (hasSens) {
      var waccs = s.wacc_values || [];
      var tgs = s.terminal_growth_values || [];
      var baseW = num(s.base_wacc), baseG = num(s.base_growth);
      /* 基准格的下标：在 D 给的坐标轴数组里找出等于 base 的那一格。
         找不到就不标 —— 猜一个下标去高亮是最容易埋错的地方。 */
      var bRow = -1, bCol = -1;
      waccs.forEach(function (w, i) { if (num(w) === baseW) bRow = i; });
      tgs.forEach(function (g, i) { if (num(g) === baseG) bCol = i; });

      /* 表头：第一列是行轴名（WACC），其余是永续增长的各档。
         纵轴与横轴的角色从 D 的矩阵形状定死：matrix 的一行对应一个 WACC，
         一行里的各格对应 terminal_growth_values 的各档。
         靠这个约定才敢把 base_wacc 的下标拿去标记 —— 见下面的 bRow/bCol。

         ★ 2026-10-13 第六轮起，这张表的基准标记改过四稿，过程记在
         components.css 的 .cell-tag 上面。**这一轮（第八轮）的结论是：
         标记从数据格整体挪到两条轴的表头上。**
         基准列的表头挂一个「基准」，基准行的行轴格挂一个「基准」——
         交叉那一格被两把尺子同时指到，格子里不需要再有任何记号。
         这样拆的理由：数据格只有一列宽（≈150px），塞进任何东西都会
         把等宽矩阵挤变形（实测基准列会从 159 撑到 225px），
         而两条轴的表头本来就有富余（第一列 238px@1600 … 165px@1200，
         数字表头 150px 上下）。挪的代价是零。 */
      var headers = ["WACC ＼ 永续增长"];
      tgs.forEach(function (g, ci) {
        headers.push({ text: fmt.percent(g), tag: ci === bCol ? "基准" : null });
      });

      var rows = waccs.map(function (w, ri) {
        var cells = [{
          text: fmt.percent(w), cls: "strong",
          tag: ri === bRow ? "基准" : null
        }];
        tgs.forEach(function (g, ci) {
          var val = (s.matrix[ri] || [])[ci];
          cells.push({
            text: num(val) === null ? fmt.MISSING : cell(fmt, val),
            cls: "num" + (num(val) === null ? " dim" : "")
          });
        });
        return cells;
      });
      box.appendChild(ui.el("div", "block-sub",
        "每股价值对 WACC × 永续增长率（" + (s.unit || "元/股") + "）"));
      if (bRow >= 0 && bCol >= 0) {
        /* ★ 2026-10-13 第八轮：说明里不再出现「框住的那一格」——
           两条轴上各挂了一个写着「基准」的标签，说明不必再当图例使唤。
           它现在只干图例干不了的那件事：**说清其余各格是什么**。
           （前七轮这段越写越长，正是因为它在替一个没有字的标记做解释。） */
        box.appendChild(ui.note(
          "带「基准」标签的那一行和那一列（WACC " + fmt.percent(baseW)
               + " × 永续增长 " + fmt.percent(baseG) + "）是 D 的基准假设，"
               + "也就是 DCF 主口径用的那一组，两轴交点就是主口径算出的价。"
               + "其余各格是 D 按同一套模型换一组假设得到的价 ——"
               + "表格读的是「结论对假设有多敏感」，不是「哪一格更好」。", "info"));
      }
      box.appendChild(scrollWrap(ui, miniTable(ui, headers, rows)));
    }

    /* --- 三情景 --- */
    if (hasScen) {
      box.appendChild(ui.el("div", "block-sub", "三情景"));
      var rows2 = ["bull", "base", "bear"].map(function (k) {
        var o = scen[k];
        if (!o) return null;
        return [
          { text: (o.label || { bull: "乐观", base: "基准", bear: "悲观" }[k]), cls: "strong" },
          { text: num(o.per_share) === null ? fmt.MISSING : ps(fmt, o.per_share),
            cls: "num metric-value" + (num(o.per_share) === null ? " dim" : "") },
          { text: moneyOf(fmt, o.equity_value) || fmt.MISSING, cls: "num" },
          { text: num(o.growth_y1) === null ? fmt.MISSING : fmt.signedPercent(o.growth_y1), cls: "num" },
          { text: num(o.ebit_margin) === null ? fmt.MISSING : fmt.percent(o.ebit_margin), cls: "num" },
          { text: num(o.wacc) === null ? fmt.MISSING : fmt.percent(o.wacc), cls: "num" },
          { text: num(o.terminal_growth) === null ? fmt.MISSING : fmt.percent(o.terminal_growth), cls: "num" }
        ];
      }).filter(Boolean);

      box.appendChild(scrollWrap(ui, miniTable(ui,
        ["情景", "每股价值", "隐含股权价值（亿元）", "首年增速", "EBIT 利润率", "WACC", "永续增长"], rows2)));

      /* 情景的杠杆单独列 —— 塞进表格会撑爆列宽，而它恰恰是「这三套假设
         差在哪」的答案，不能省。 */
      var lev = ui.el("ul", "warn-list");
      ["bull", "base", "bear"].forEach(function (k) {
        var o = scen[k];
        if (!o || !o.levers) return;
        var li = ui.el("li", null, (o.label || k) + "：" + o.levers);
        lev.appendChild(li);
      });
      /* 用 children 而不是 childNodes —— 这里数的是**元素**，不是文本节点，
         而且 children 在渲染桩里也有。 */
      if (lev.children.length) box.appendChild(lev);
    }
    return box;
  }

  /* ==================================================================== */
  /* ⑥ 告警与来源                                                          */
  /* ==================================================================== */
  /* 契约注释写得很清楚：「warnings 是结论的一部分，不是报错」。
     缺行情、缺可比公司、跳过 SOTP 这些**都写在这里**。必须显示它们 ——
     否则用户看到一片空白，不知道是「这家公司不值钱」还是「数据没取到」。
     这两者天差地别。
     所以 valuation.sotp 不另起一块：它的 skip 理由就在这张清单里，
     同一句话在一屏出现两次是噪声。 */
  function warningsCard(ui, fmt, v) {
    var warns = Array.isArray(v.warnings) ? v.warnings : [];
    var sources = Array.isArray(v.sources) ? v.sources : [];
    var disc = v.disclaimer;
    if (!warns.length && !sources.length && !disc) return null;

    var box = ui.card();
    box.appendChild(ui.subhead("估值告警与数据来源"));

    if (warns.length) {
      /* 用 .warn-title + .warn-list 而不是逐条 .note-warn：
         7 条带左边框和底纹的段落连排会变成一堵墙，
         而要的只是「这里有 7 件事你该知道」的语气。 */
      box.appendChild(ui.el("div", "warn-title",
        "D 记录的估值告警（" + warns.length + " 项）"));
      var ul = ui.el("ul", "warn-list");
      warns.forEach(function (w) { ul.appendChild(ui.el("li", null, String(w))); });
      box.appendChild(ul);
    }

    if (sources.length) {
      box.appendChild(ui.el("div", "block-sub", "数据来源"));
      var rows = sources.map(function (s) {
        return [
          { text: fmt.text(s.name), cls: "strong" },
          { text: fmt.text(s.purpose), cls: "dim" },
          { text: fmt.text(s.as_of), cls: "num dim" },
          { text: s.official === true ? "官方" : "第三方", cls: "dim" }
        ];
      });
      box.appendChild(scrollWrap(ui, miniTable(ui, ["来源", "用途", "取数日期", "性质"], rows)));
    }

    if (disc) box.appendChild(ui.note(String(disc), "info"));
    return box;
  }

  /* ==================================================================== */
  /* 表格小工具                                                            */
  /* ==================================================================== */

  /* 表。一格可以是三种东西：
       · 字符串         → 直出
       · { text, cls }  → 带类名的文字
     空值统一显示成破折号并挂 .dim —— 不是留白，是明确地说「这里没有」。 */
  /* 表头和表体的每一格都可以是字符串，也可以是 {text, cls, tag}。
     tag = 格内小标签（现在只有敏感性矩阵的基准行 / 基准列在用）。
     ★ 不带 tag 的格子仍走纯 textContent，DOM 结构和以前一模一样 ——
       「顺手把所有格子都包一层 <span>」会改动另外三张表的输出，
       那些表有测试钉着，没有必要为一条新特性去动它们。 */
  function miniTable(ui, headers, rows) {
    var tb = ui.el("table", "mini-table");
    var thead = ui.el("thead");
    var hr = ui.el("tr");
    headers.forEach(function (h) {
      var th = ui.el("th");
      var text = (h && typeof h === "object") ? h.text : h;
      th.textContent = String(text);
      if (h && typeof h === "object" && h.tag) {
        th.appendChild(ui.el("span", "cell-tag", h.tag));
      }
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    tb.appendChild(thead);

    var tbody = ui.el("tbody");
    rows.forEach(function (cells) {
      var tr = ui.el("tr");
      cells.forEach(function (c) {
        var td = ui.el("td");
        var text = (c && typeof c === "object") ? c.text : c;
        var cls = (c && typeof c === "object") ? c.cls : null;
        if (text === null || text === undefined || text === "") {
          text = "—";
          cls = "dim";
        }
        if (cls) td.className = cls;
        td.textContent = String(text);
        /* 标签排在值**后面**：它只挂在行轴那一格上，那格是左对齐的，
           「4.63% 基准」顺着读下来才对。数值列里没有标签，无关对齐。 */
        if (c && typeof c === "object" && c.tag) {
          td.appendChild(ui.el("span", "cell-tag", c.tag));
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    tb.appendChild(tbody);
    return tb;
  }

  /* 列多的表在窄屏/打印时会溢出，套一层横向滚动。
     .mini-table 自己是 overflow:hidden，直接溢出会被裁掉。 */
  function scrollWrap(ui, node) {
    var w = ui.el("div", "table-scroll");
    w.appendChild(node);
    return w;
  }
})();
