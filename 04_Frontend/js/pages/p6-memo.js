/* ============================================================================
 * p6-memo.js —— 页面6 投研报告
 * ----------------------------------------------------------------------------
 * 职责：把 D 的投研简报**绑定表**（memo.json）排成一页报告。
 * 数据来源：data/memo 走 FinScope.data 的 memo* 系列取值器 → ctx.memo
 *
 * 【2026-10-13 全量重写：这一页原来等的东西根本不会来】
 *
 *   旧版读 `report.title / rating / target_price / summary / sections[]`，
 *   并在空状态下列了一份「E 向 D 建议的报告字段结构」。那份结构**没有
 *   被采纳，也不会被采纳** —— D 的交法是另一种：它不交「报告对象」，
 *   它交一张**占位符 → 已格式化字符串的绑定表**：
 *
 *     meta                     抬头（公司名 / 代码 / 报告期 / 生成时间 / 引擎）
 *     columns[7]               七节标题的**原文**（D 写的，E 不自己起标题）
 *     scalars[]                56 条 { placeholder, source_path, raw_value, formatted }
 *     collections[12]          12 张具名列表，每格同样是 { formatted }
 *     numbers[]                151 个数字 token 及其来源路径（合规扫描用）
 *     compliance / validation  D 自己的合规闸门结果
 *
 *   所以这一页的读法是：**直出 formatted**。这是全站唯一一页 E 不做数字
 *   格式化 —— D 已经把 168838102514.79 写成 "1,688.38 亿元" 了，E 再走一遍
 *   fmt.money 只会制造两处口径。**E 也不连句**：正文的句子（「综合估值结论：
 *   低估。融合每股价值…」）在 memo.md / memo.html 里，**不在 memo.json 里**，
 *   而授权是「页面 6 从 D 的 memo.json 读」—— 所以本页呈现的是数字与列表，
 *   不是成段的叙述。要成段叙述，得请 D 把那些句子也做成绑定项。见 spec。
 *
 * 【七节怎么对应】
 *   columns[0..6] 原样做标题；内容按**下标**分发。下标是硬约定 ——
 *   D 若调换章节顺序，这里会静默错位，所以 spec 里写明了「columns 顺序即契约」。
 *
 * 【版式定案】
 *   1. 用 .paper（报告纸）：这一页是文档，不是仪表盘。46em 居中。
 *   2. **不嵌套玻璃**。.paper 本身是强玻璃，页内不再放 .card / .metric-card ——
 *      玻璃叠玻璃会互相取样。行内小构件一律走**实底/底纹**那一档：
 *      .v-target（一行多格的键值条）、.mini-table（表）、.risk-*（风险卡）。
 *   3. 落点在第一节：三个大数（结论 / 融合每股价值 / 相对现价空间）走
 *      .ro-stats —— 它只有字号没有背景，是站上唯一「大而不用玻璃」的写法。
 *   4. **缺值不涂色、不解释**。D 把缺失写成 "数据缺失"，本页照原样显示，
 *      只挂一个 .dim 让它退后（改文案就是改 D 的内容）。
 *
 * 注意：E 不撰写报告内容，也不重算任何数。本页唯一的运算有两处，都是
 *       绘制行为：① 把 D 给的 " | " 分隔字符串拆回表格列（敏感性矩阵）；
 *       ② 给每股数值补一个单位后缀（D 的 scalars 不带 unit 字段）。
 *       两处都在 spec 里记了对 D 的请求。
 * ==========================================================================*/

(function () {
  "use strict";
  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  /* ------------------------------------------------------------------ */
  /* 常量                                                                */
  /* ------------------------------------------------------------------ */

  /* D 的缺失标记。memo.json 里所有取不到的值都被 D 写成这一串 ——
     照原样显示，只加 .dim 让它退后。 */
  var MISS_TEXT = "数据缺失";

  /* scalars 的**显示用**中文名。D 的 scalars 只给 placeholder（英文键名），
     不给 label，所以这张表是唯一来源，不是兜底表 ——
     D 加了新标量，这里必须跟着加，否则直接显示成英文键名。
     unit 后缀同样是 E 补的：D 的 scalars 不带 unit 字段，
     而 "1,431.30" 不写「元/股」就不知道是什么。
     ---------- 单位后缀的取值依据（逐条核过，不是猜的）----------
       · 每股类（blended_ps / current_price / *_ps / *_low|mid|high）→ "元/股"
         依据 valuation.*.valuation_range.currency = "元/股"，
         且 memo.md 正文写的也是「1,431.30 元/股」。
       · *delta / 贡献类 → "个百分点"（D 的 formatted 是裸数 -3.97）
       · 其余：D 的 formatted 自带「亿元」或「%」，不加后缀。 */
  var SCALARS = {
    /* ① 结论摘要 */
    verdict:            { label: "估值结论" },
    blended_ps:         { label: "融合每股价值", unit: "元/股" },
    current_price:      { label: "当前股价", unit: "元/股" },
    upside:             { label: "相对现价空间" },
    dcf_ps:             { label: "DCF（收益法）每股", unit: "元/股" },
    dcf_weight:         { label: "权重" },
    comps_ps:           { label: "相对估值（市场法）每股", unit: "元/股" },
    comps_weight:       { label: "权重" },
    risk_count:         { label: "触发风险" , unit: "项" },

    /* ③ 经营情况与变化归因 */
    revenue:            { label: "营业收入" },
    revenue_growth:     { label: "营业收入同比" },
    ni_parent:          { label: "归母净利润" },
    ni_growth:          { label: "归母净利润同比" },
    operating_cost:     { label: "营业成本" },
    cost_growth:        { label: "营业成本同比" },
    gross_margin:       { label: "毛利率" },
    gross_margin_delta: { label: "毛利率变动", unit: "个百分点" },
    ocf:                { label: "经营活动现金流净额" },
    ocf_growth:         { label: "经营现金流同比" },
    cfo_to_ni:          { label: "净现比（经营现金流÷归母净利润）" },
    fcf:                { label: "自由现金流" },
    roe:                { label: "加权 ROE" },
    roe_delta:          { label: "ROE 变动", unit: "个百分点" },
    dupont_roe_delta:        { label: "ROE 变动合计", unit: "个百分点" },
    dupont_net_margin:       { label: "净利率贡献", unit: "个百分点" },
    dupont_asset_turnover:   { label: "总资产周转贡献", unit: "个百分点" },
    dupont_leverage:         { label: "权益乘数贡献", unit: "个百分点" },

    /* ⑤ 预测与估值 */
    forecast_years:     { label: "预测期", unit: "年" },
    wacc:               { label: "WACC" },
    terminal_growth:    { label: "永续增长率" },
    tax_rate:           { label: "所得税率" },
    revenue_base:       { label: "收入基数" },
    ebit_margin:        { label: "EBIT 利润率" },
    dcf_low:            { label: "DCF 下限", unit: "元/股" },
    dcf_mid:            { label: "DCF 中值", unit: "元/股" },
    dcf_high:           { label: "DCF 上限", unit: "元/股" },
    comps_low:          { label: "相对估值下限", unit: "元/股" },
    comps_mid:          { label: "相对估值中值", unit: "元/股" },
    comps_high:         { label: "相对估值上限", unit: "元/股" },
    tv_pct:             { label: "终值占企业价值" },

    /* ⑥ 待核验事项 */
    n_rules:            { label: "规则不可评估", unit: "项" },
    n_fin:              { label: "财务科目录取异常", unit: "项" },
    n_valwarn:          { label: "估值警告", unit: "项" },
    n_runwarn:          { label: "运行日志警告", unit: "项" },

    /* ⑦ 数据来源与免责声明 */
    disclaimer:         { label: "本报告免责声明" },
    group_disclaimer:   { label: "小组免责声明" }
  };

  /* memo 的 risks / top_risks 集合只给 severity_tag（中文），
     没给 severity 代码。卡片染色要靠代码，所以这里做一张中文→代码的
     反查表。它只影响配色，不影响任何文案 —— 反查不到就不染色，
     卡片走 --c-text-3 的灰档，仍然能读。 */
  var SEV_BY_TAG = {
    "重大": "high", "高": "high",
    "关注": "medium", "中": "medium",
    "提示": "low", "一般": "low", "低": "low"
  };

  var RISK_COLS = ["risk_id", "severity_tag", "risk_name", "category", "score",
                   "trigger", "involved_str", "numeric_evidence",
                   "explanation", "suggested_action"];

  F.pages.p6 = {
    id: "p6",
    index: 6,
    title: "投研报告",
    subtitle: "Research Memo",

    spec: [
      "「正文句子不在 memo.json 里」。D 的 memo.md 有「综合估值结论：低估。"
        + "融合每股价值 1,431.30 元/股……」这样的成段叙述，但那是 D 的模板"
        + "渲染产物，memo.json 只给「占位符 → 字符串」的绑定关系，句子本身没进来。"
        + "所以本页现在是数字与列表，不是叙述。若要在页面上读成段的结论，"
        + "需要 D 把那些句子也做成集合项（如 sections[]），E 侧不需要改结构",
      "scalars[] 不带 unit 字段 → 每股类数值的单位（元/股）由 E 在 SCALARS 表里"
        + "逐条硬写。D 若给 scalars 补一个 unit 字段，这张表就能收掉一半",

      "「columns[7] 的顺序是硬约定」：本页按下标 0–6 分发七节内容。"
        + "D 若调整章节顺序，页面会静默错位（不报错、只是内容跑错节）。"
        + "若 D 打算动顺序，需要先同步 E",

      "risks / top_risks 集合没有 severity 代码（只有中文 severity_tag），"
        + "卡片染色靠 E 的反查表。D 若在集合里带上 severity，这张表就能删",

      "估值构成（DCF / 相对估值 两行）的「方法名」是 E 按 memo.md 的措辞写死的。"
        + "D 若愿意把 blended.components[] 也做成集合（blend_components），"
        + "这一处硬编码可以撤掉",

      "敏感性矩阵：D 把每行压成 \"a | b | c | d | e\" 一个字符串，本页按 \" | \" "
        + "拆回列。表头 sens_header_cells 用的是同一个分隔符，所以两边对得上 ——"
        + "但这是 E 在解析 D 的展示串，属于绘制行为。更好的做法是 D 直接给数组",

      "打印 / 导出 PDF（window.print）已可用；本页的风险卡默认全展开，"
        + "不需要依赖 app.js 的 beforeprint 展开逻辑"
    ],

    render: function (root) {
      var ui = F.ui, fmt = F.fmt, data = F.data;

      root.appendChild(ui.section(
        this.title,
        "由 D 的报告生成模块自动汇总前述分析结果，输出完整投研简报。"
             + "本节文字与数字全部来自该简报的绑定表，前端只做排版与导出。"
      ));

      if (!data.hasMemo()) {
        root.appendChild(emptyPaper(ui));
        root.appendChild(actions(ui));
        root.appendChild(specCard(this.spec, ui,
          "memo 绑定表未到场。本页读的是 D 的 out_data/reports/<key>/memo.json，"
               + "统一数据对象到不到位都不影响它 —— 两份是独立产物。"));
        return;
      }

      var meta = data.memoMeta() || {};
      var cols = data.memoColumns();

      var paper = ui.el("div", "paper");
      paperHead(ui, fmt, data, paper, meta);
      gateRow(ui, fmt, data, paper);

      secConclusion(ui, fmt, data, paper, cols[0]);
      secDashboard(ui, fmt, data, paper, cols[1]);
      secOperation(ui, fmt, data, paper, cols[2]);
      secRisks(ui, fmt, data, paper, cols[3]);
      secValuation(ui, fmt, data, paper, cols[4]);
      secReview(ui, fmt, data, paper, cols[5]);
      secSources(ui, fmt, data, paper, cols[6]);

      root.appendChild(paper);
      root.appendChild(actions(ui));
      root.appendChild(specCard(this.spec, ui, null));
    }
  };

  /* ==================================================================== */
  /* 通用小件                                                             */
  /* ==================================================================== */

  function isMiss(v) { return v === null || v === undefined || v === MISS_TEXT; }

  /* 读一个标量，补上 E 声明的单位后缀。取不到就返回 null，
     调用方据此**整格不放**（一排「—」比少一格更难看）。 */
  function val(data, key) {
    var s = data.memoValue(key);
    if (s === null || s === undefined || s === "") return null;
    var spec = SCALARS[key];
    if (!spec || !spec.unit) return s;
    return s + " " + spec.unit;
  }

  function labelOf(key) { return (SCALARS[key] && SCALARS[key].label) || key; }

  /* 一行多格的键值条。值为 null 的格整格不出现。 */
  function strip(ui, headLabel, pairs) {
    var keep = pairs.filter(function (p) { return !isMiss(p[1]); });
    if (!keep.length && !headLabel) return null;
    var box = ui.el("div", "v-target");
    if (headLabel) box.appendChild(ui.el("span", "v-target-label", headLabel));
    keep.forEach(function (p) {
      var item = ui.el("span", "v-target-item");
      item.appendChild(ui.el("span", "v-target-k", p[0]));
      item.appendChild(ui.el("span", "v-target-v" + (isMiss(p[1]) ? " dim" : ""), p[1]));
      box.appendChild(item);
    });
    return box;
  }

  /* 表。一格可以是三种东西：
       · 字符串                      → 直出
       · 一个 DOM 节点               → 直接放进去（状态胶囊那类）
       · { text, cls }               → 带类名的文字
     缺值的格（"数据缺失"）挂 .dim —— 只改视觉权重，不改文案。 */
  function table(ui, headers, rows) {
    var tb = ui.el("table", "mini-table");
    var thead = ui.el("thead");
    var hr = ui.el("tr");
    headers.forEach(function (h) { hr.appendChild(ui.el("th", null, h)); });
    thead.appendChild(hr);
    tb.appendChild(thead);

    var tbody = ui.el("tbody");
    rows.forEach(function (cells) {
      var tr = ui.el("tr");
      cells.forEach(function (c) {
        var td = ui.el("td");
        if (c && c.nodeType === 1) {
          td.appendChild(c);
        } else {
          var text = (c && typeof c === "object") ? c.text : c;
          var cls = (c && typeof c === "object") ? c.cls : null;
          if (isMiss(text)) { text = MISS_TEXT; cls = "dim"; }
          if (cls) td.className = cls;
          td.textContent = (text === null || text === undefined) ? "" : String(text);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    tb.appendChild(tbody);
    return tb;
  }

  /* 一行 memo 集合项 → 已格式化的字符串数组 */
  function rowOf(data, item, cols) {
    var r = data.memoRow(item, cols);
    return cols.map(function (c) { return r[c]; });
  }

  /* 节标题。**用 D 的 columns[i] 原文** —— E 不自己起标题。
     兜底（D 没给这一列时）才用 E 的通用词。 */
  function secHead(ui, title, fallback) {
    var t = (title === undefined || title === null || title === "") ? fallback : title;
    return ui.el("h2", "paper-h2", t);
  }

  /* 一小段灰字说明。**不用 .note**（它带左边框 + 底纹，在一页纸里太响），
     也不用 .block-sub（上边距是负数，本页的段落间距不都是小标题配的，
     套上去会撞到上面的表格边线）。朴素的灰段落在纸面上最不打扰。 */
  function muted(ui, text) { return ui.el("p", "dim", text); }

  /* ==================================================================== */
  /* 报告纸：抬头 + 合规闸门                                              */
  /* ==================================================================== */

  function paperHead(ui, fmt, data, paper, meta) {
    var name = meta.company_name || "（公司名称未提供）";
    var ticker = meta.ticker;
    paper.appendChild(ui.el("h1", "paper-title",
      ticker ? name + "（" + ticker + "）" : name));

    var row = ui.el("div", "paper-meta");
    [
      ["报告期", meta.report_period],
      ["行业", data.memoValue("industry")],
      ["上市地", data.memoValue("exchange")],
      ["币种", data.memoValue("currency_label")],
      ["生成时间", meta.generated_at],
      /* 引擎也走这一行：它是**可信度信息**不是身份信息 ——
         「数字全部代码注入、不经过语言模型」这句话决定了读者该怎么读
         这份简报，所以它必须在抬头就被看到，而不是埋在页脚。
         单起一行会撑高三行，塞进这条会自动换行的横排里最省。 */
      ["渲染引擎", meta.engine]
    ].forEach(function (kv) {
      if (kv[1] === null || kv[1] === undefined || kv[1] === "") return;
      row.appendChild(ui.el("span", null, kv[0] + "：" + kv[1]));
    });
    paper.appendChild(row);
  }

  /* D 自己的合规闸门。顶在正文最上面：「这份简报能信吗」得先回答。
     全绿时也只给一个胶囊 —— 一页报告不该在开头堆三个绿标。 */
  function gateRow(ui, fmt, data, paper) {
    var g = data.memoValidation();
    if (!g) return;

    var box = ui.el("div", "v-target");
    box.appendChild(ui.el("span", "v-target-label", "数字校验"));

    if (g.passed === true) {
      var n = (g.allowedCount !== null && g.allowedCount !== undefined)
        ? g.allowedCount + " 项全部可溯源" : "通过";
      box.appendChild(ui.el("span", "status-chip is-good", n));
    } else if (g.passed === false) {
      box.appendChild(ui.el("span", "status-chip is-bad", "未通过"));
    }

    if (g.violations.length) {
      box.appendChild(ui.el("span", "status-chip is-bad",
        g.violations.length + " 处越界数字"));
    }
    if (g.hits.length) {
      box.appendChild(ui.el("span", "status-chip is-watch",
        "合规命中 " + g.hits.length + " 处"));
    }
    /* 三个都没有时不摆一条空条 —— 那会让「没有闸门结果」和「闸门通过」
       长得一样。 */
    if (box.children.length > 1) paper.appendChild(box);
  }

  /* ==================================================================== */
  /* ① 结论摘要                                                           */
  /* ==================================================================== */
  function secConclusion(ui, fmt, data, paper, col) {
    paper.appendChild(secHead(ui, col, "结论摘要"));

    /* 落点：三个大数。走 .ro-stats —— 站上唯一「大而不用玻璃」的写法，
       放进 .paper 里不会造成玻璃叠玻璃。 */
    var stats = ui.el("div", "ro-stats");
    [
      ["verdict", "估值结论"],
      ["blended_ps", "融合每股价值"],
      ["upside", "相对现价空间"]
    ].forEach(function (s) {
      var v = val(data, s[0]);
      if (v === null) return;
      var it = ui.el("div", "ro-item");
      it.appendChild(ui.el("span", "ro-num", v));
      it.appendChild(ui.el("span", "ro-label", s[1]));
      stats.appendChild(it);
    });
    if (stats.children.length) paper.appendChild(stats);

    var s2 = strip(ui, "口径", [
      ["当前股价", val(data, "current_price")],
      ["终值占企业价值", val(data, "tv_pct")],
      ["触发风险", val(data, "risk_count")]
    ]);
    if (s2) paper.appendChild(s2);

    /* 估值构成。方法名是 E 按 memo.md 的措辞写的，见 spec。 */
    var comp = [];
    if (!isMiss(val(data, "dcf_ps")) || !isMiss(val(data, "comps_ps"))) {
      comp.push(["DCF（收益法）", val(data, "dcf_ps"), val(data, "dcf_weight")]);
      comp.push(["相对估值（市场法）", val(data, "comps_ps"), val(data, "comps_weight")]);
    }
    if (comp.length) {
      paper.appendChild(ui.subhead("估值构成"));
      paper.appendChild(table(ui, ["方法", "每股价值", "权重"], comp));
    }

    /* 主要风险（top_risks 是 D 从 risks 里挑出来的前几条，不是 E 挑的） */
    var top = data.memoCollection("top_risks");
    if (top.length) {
      paper.appendChild(ui.subhead("主要风险"));
      paper.appendChild(table(ui, ["编号", "等级", "风险", "评分"],
        top.map(function (it) {
          var r = data.memoRow(it, ["risk_id", "severity_tag", "risk_name", "score"]);
          return [r.risk_id, { text: r.severity_tag, cls: sevCell(r.severity_tag) },
                  r.risk_name, r.score];
        })));
    }
  }

  function sevCell(tag) {
    var code = SEV_BY_TAG[tag];
    if (code === "high") return "strong";
    return null;
  }

  /* ==================================================================== */
  /* ② 关键指标仪表盘                                                     */
  /* ==================================================================== */
  function secDashboard(ui, fmt, data, paper, col) {
    var items = data.memoCollection("dashboard");
    paper.appendChild(secHead(ui, col, "关键指标仪表盘"));
    if (!items.length) {
      paper.appendChild(muted(ui, "仪表盘数据未提供。"));
      return;
    }
    var COLS = ["label", "category", "value_str", "prev_str", "delta_str", "status_str"];
    paper.appendChild(table(ui, ["指标", "类别", "本期", "上期", "变动", "状态"],
      items.map(function (it) {
        var r = data.memoRow(it, COLS);
        return [r.label, r.category, r.value_str, r.prev_str, r.delta_str,
                statusCell(ui, r.status_str)];
      })));
  }

  /* D 已经把状态写成中文（"正常" / "数据缺失·待核验"）。E 不翻译、不改写，
     只在它含「待核验」时换成一个橙胶囊 —— 那是这一节唯一需要动作的格。
     十一个指标里正常的那十个不挂胶囊：挂满等于没挂。 */
  function statusCell(ui, s) {
    if (isMiss(s)) return { text: MISS_TEXT, cls: "dim" };
    if (s.indexOf("待核验") >= 0) return ui.el("span", "status-chip is-watch", s);
    return { text: s, cls: "dim" };
  }

  /* ==================================================================== */
  /* ③ 经营情况与变化归因                                                 */
  /* ==================================================================== */
  function secOperation(ui, fmt, data, paper, col) {
    paper.appendChild(secHead(ui, col, "经营情况与变化归因"));

    var lines = [
      ["收入线", [["营业收入", val(data, "revenue")],
                  ["同比", val(data, "revenue_growth")],
                  ["归母净利润", val(data, "ni_parent")],
                  ["同比", val(data, "ni_growth")]]],
      ["成本费用线", [["营业成本", val(data, "operating_cost")],
                      ["同比", val(data, "cost_growth")],
                      ["毛利率", val(data, "gross_margin")],
                      ["较上期", val(data, "gross_margin_delta")]]],
      ["现金流线", [["经营现金流净额", val(data, "ocf")],
                    ["同比", val(data, "ocf_growth")],
                    ["净现比", val(data, "cfo_to_ni")],
                    ["自由现金流", val(data, "fcf")]]]
    ];
    lines.forEach(function (L) {
      var s = strip(ui, L[0], L[1]);
      if (s) paper.appendChild(s);
    });

    /* 变化归因：杜邦分解 + 现金流桥。两块的原始出处都是 B 的证据链「归因」层，
       D 从那里搬过来的（memo.md 里写着「D 不新增叙述、不改写措辞」）。 */
    var dupont = [
      ["ROE 变动合计", val(data, "dupont_roe_delta")],
      ["净利率贡献", val(data, "dupont_net_margin")],
      ["总资产周转贡献", val(data, "dupont_asset_turnover")],
      ["权益乘数贡献", val(data, "dupont_leverage")]
    ].filter(function (p) { return !isMiss(p[1]); });

    if (dupont.length) {
      paper.appendChild(ui.subhead("变化归因 · 杜邦分解"));
      paper.appendChild(table(ui, ["项目", "贡献（个百分点）"], dupont));
    }

    var bridge = data.memoCollection("cashflow_bridge");
    if (bridge.length) {
      paper.appendChild(ui.subhead("现金流桥"));
      paper.appendChild(table(ui, ["项目", "金额（亿元）"],
        bridge.map(function (it) {
          var r = data.memoRow(it, ["item", "amount_yi"]);
          return [r.item, r.amount_yi];
        })));
    }
  }

  /* ==================================================================== */
  /* ④ 风险雷达                                                           */
  /* ==================================================================== */
  /* 复用页面 4 的 .risk-card 结构。**同一件东西在全站长一个样**：
     页面 4 是风险的工作台，这里是它的报告版，读者不该在两页之间重新学一遍。
     差别有两处：
       ① 这里不给折叠按钮 —— 报告是从上往下读的，
          而且打印时展开逻辑（app.js 的 beforeprint）也就不必参与；
       ② **卡片要摊平**（.is-flat）：这些卡压在报告纸上，而报告纸自己
          就是一张强玻璃。玻璃里再叠一层玻璃，四张卡会连成一片没有边界。
          摊平这件事以前是 CSS 用 `.paper .risk-card` 偷偷补的，
          挪出 .paper 就会静默失效；现在写在调用点上。 */
  function secRisks(ui, fmt, data, paper, col) {
    var items = data.memoCollection("risks");
    paper.appendChild(secHead(ui, col, "风险雷达"));
    if (!items.length) {
      paper.appendChild(muted(ui, "本报告未列出已触发的风险。"));
      return;
    }
    items.forEach(function (it) { paper.appendChild(riskCard(ui, fmt, data, it)); });
  }

  function riskCard(ui, fmt, data, item) {
    var r = data.memoRow(item, RISK_COLS);

    /* is-flat：压在报告纸上，见 secRisks 上面的注释 ② */
    var card = ui.el("div", "risk-card is-open is-flat");
    /* ⚠️ 走 ui.addClass，不写 classList.add：
       severityClass 对**没映射上的等级**返回空串，而空串喂进 classList 是抛异常
       不是无操作。原来是 `var code = SEV_BY_TAG[...]; if (code) add(...)` ——
       那个 if 挡的是「标签认不出来」，挡不住「标签认得、等级没映射上」，
       两件事不是同一个判断。现在两个失败点都归 addClass 兜。 */
    ui.addClass(card, fmt.severityClass(SEV_BY_TAG[r.severity_tag]));

    /* --- 头 --- */
    var head = ui.el("div", "risk-head");
    head.appendChild(ui.el("span", "sev-chip", r.severity_tag || fmt.MISSING));

    var text = ui.el("div", "risk-head-text");
    var tagline = [r.risk_id, r.category].filter(function (x) { return !isMiss(x); });
    if (!isMiss(r.score)) tagline.push("评分 " + r.score);
    if (tagline.length) text.appendChild(ui.el("div", "dim", tagline.join(" · ")));
    text.appendChild(ui.el("div", "risk-name", isMiss(r.risk_name) ? fmt.MISSING : r.risk_name));
    if (!isMiss(r.trigger)) text.appendChild(ui.el("div", "risk-trigger", "触发规则：" + r.trigger));
    head.appendChild(text);
    card.appendChild(head);

    /* --- 体：三层，左侧节点挂在同一条竖线上（同页面 4） --- */
    var body = ui.el("div", "risk-body");
    var rail = ui.el("div", "risk-layers");

    /* 第一层：触发判据与涉及数值。①②是事实、③是判断 —— 与页面 4 同一套语义。 */
    var L1 = layer(ui, 1, "触发判据", "is-fact");
    if (!isMiss(r.involved_str)) {
      L1.content.appendChild(ui.el("div", "detail-line", "涉及数值：" + r.involved_str));
    }
    if (!isMiss(r.numeric_evidence)) {
      L1.content.appendChild(ui.el("div", "detail-line", "数字证据：" + r.numeric_evidence));
    }
    if (L1.content.children.length > 1) rail.appendChild(L1.root);

    var L2 = layer(ui, 2, "解释", "is-fact");
    if (!isMiss(r.explanation)) {
      L2.content.appendChild(ui.el("div", "risk-explain", r.explanation));
    }
    if (L2.content.children.length > 1) rail.appendChild(L2.root);

    var L3 = layer(ui, 3, "建议动作", "is-conclusion");
    if (!isMiss(r.suggested_action)) {
      var sug = ui.el("div", "risk-suggest");
      sug.appendChild(ui.el("span", "sug-tag", "应对"));
      sug.appendChild(ui.el("p", "sug-text", r.suggested_action));
      L3.content.appendChild(sug);
    }
    if (L3.content.children.length > 1) rail.appendChild(L3.root);

    /* 三层全空（D 只给了名字）时不留一条光秃秃的竖线 */
    if (rail.children.length) {
      body.appendChild(rail);
      card.appendChild(body);
    }
    return card;
  }

  /* 层骨架：左侧节点 + 右侧内容。与页面 4 同一实现。 */
  function layer(ui, num, title, kind) {
    var root = ui.el("div", "layer " + kind);
    root.appendChild(ui.el("div", "layer-mark", num));
    var content = ui.el("div", "layer-content");
    content.appendChild(ui.el("div", "layer-title", title));
    root.appendChild(content);
    return { root: root, content: content };
  }

  /* ==================================================================== */
  /* ⑤ 预测与估值                                                         */
  /* ==================================================================== */
  function secValuation(ui, fmt, data, paper, col) {
    paper.appendChild(secHead(ui, col, "预测与估值"));

    var assum = strip(ui, "DCF 假设", [
      ["预测期", val(data, "forecast_years")],
      ["WACC", val(data, "wacc")],
      ["永续增长率", val(data, "terminal_growth")],
      ["所得税率", val(data, "tax_rate")],
      ["收入基数", val(data, "revenue_base")],
      ["EBIT 利润率", val(data, "ebit_margin")]
    ]);
    if (assum) paper.appendChild(assum);

    var fc = data.memoCollection("forecast");
    if (fc.length) {
      paper.appendChild(ui.subhead("DCF 预测"));
      paper.appendChild(table(ui, ["年度", "营业收入", "EBIT", "FCFF"],
        fc.map(function (it) {
          return rowOf(data, it, ["year", "revenue_yi", "ebit_yi", "fcff_yi"]);
        })));
    }

    var range = strip(ui, "估值区间", [
      ["DCF", rangeText(data, "dcf_low", "dcf_high", "dcf_mid")],
      ["相对估值", rangeText(data, "comps_low", "comps_high", "comps_mid")],
      ["融合每股", val(data, "blended_ps")]
    ]);
    if (range) paper.appendChild(range);

    var sc = data.memoCollection("scenarios");
    if (sc.length) {
      paper.appendChild(ui.subhead("三情景"));
      paper.appendChild(table(ui,
        ["情景", "每股价值（元/股）", "第一年收入增速", "EBIT 利润率", "WACC"],
        sc.map(function (it) {
          return rowOf(data, it, ["label", "per_share", "growth_y1", "ebit_margin", "wacc"]);
        })));
    }

    var sens = data.memoCollection("sensitivity_rows");
    if (sens.length) {
      var headCells = data.memoValue("sens_header_cells");
      /* 表头也是 D 用 " | " 压成的一串（sens_header_cells），
         与每行的 cells 同一个分隔符 —— 两边一起拆，列数才对得上。 */
      var gCols = headCells ? splitCells(headCells) : [];
      var headers = ["WACC \\ 永续增长"].concat(gCols);
      paper.appendChild(ui.subhead("敏感性（每股价值，元/股）"));
      paper.appendChild(table(ui, headers,
        sens.map(function (it) {
          var r = data.memoRow(it, ["wacc", "cells"]);
          return [r.wacc].concat(splitCells(r.cells));
        })));
    }
  }

  /* "413.91 至 660.13，中值 537.02 元/股" —— 这是**拼串**，不是算数：
     三个数都是 D 给好的，E 只决定中间用什么字连、单位放在哪。
     理由是 .v-target 一格放不下三段标签，拆成三格会让这一行膨胀成九个格。
     ★ 单位只在末尾补一次，所以这里读的是**原始 memoValue**，
     不走 val()（那会给每个数都加一遍「元/股」）。 */
  function rangeText(data, loKey, hiKey, midKey) {
    var raw = data.memoValue, lo = raw(loKey), hi = raw(hiKey), mid = raw(midKey);
    if (isMiss(lo) && isMiss(hi) && isMiss(mid)) return null;
    var u = SCALARS[loKey].unit;
    if (isMiss(lo) || isMiss(hi)) return isMiss(mid) ? null : mid + " " + u;
    return lo + " 至 " + hi + (isMiss(mid) ? "" : "，中值 " + mid) + " " + u;
  }

  /* 把 D 压成 "a | b | c" 的展示串拆回单元格。空段保留（拆出来是空串），
     这样列数才与表头一致 —— 少一列会让整行右移。 */
  function splitCells(s) {
    if (s === null || s === undefined || s === "") return [];
    return String(s).split("|").map(function (x) {
      return x.trim() === "" ? MISS_TEXT : x.trim();
    });
  }

  /* ==================================================================== */
  /* ⑥ 待核验事项                                                         */
  /* ==================================================================== */
  function secReview(ui, fmt, data, paper, col) {
    paper.appendChild(secHead(ui, col, "待核验事项"));

    var counts = strip(ui, "统计", [
      ["规则不可评估", val(data, "n_rules")],
      ["财务科目录取异常", val(data, "n_fin")],
      ["估值警告", val(data, "n_valwarn")],
      ["运行日志警告", val(data, "n_runwarn")]
    ]);
    if (counts) paper.appendChild(counts);

    var rules = data.memoCollection("review_rules");
    if (rules.length) {
      paper.appendChild(ui.subhead("规则不可评估"));
      paper.appendChild(table(ui, ["编号", "规则", "无法判定的原因"],
        rules.map(function (it) {
          return rowOf(data, it, ["rule_id", "rule_name", "explanation"]);
        })));
    }

    var fin = data.memoCollection("review_fin");
    if (fin.length) {
      paper.appendChild(ui.subhead("财务科目录取异常"));
      paper.appendChild(table(ui, ["科目", "状态"],
        fin.map(function (it) {
          var r = data.memoRow(it, ["name", "status"]);
          /* ★ 两个字段都要过一遍前端词汇表：
             name 是 D 的**字段键名**（"goodwill"），中文名在全站统一台账
             FINANCIAL_LABELS 里（→「商誉」）；
             status 是 D 的状态码（not_applicable），中文由 statusLabel 翻。
             两处都是查表不是翻译 —— 查不到就原样显示英文，不猜。 */
          return [data.metricLabel(r.name), fmt.statusLabel(r.status)];
        })));
    }

    var vw = data.memoCollection("review_valwarn");
    if (vw.length) {
      paper.appendChild(ui.subhead("估值警告"));
      var ul = ui.el("ul", "warn-list");
      vw.forEach(function (it) {
        var r = data.memoRow(it, ["text"]);
        ul.appendChild(ui.el("li", null, r.text === null ? MISS_TEXT : r.text));
      });
      paper.appendChild(ul);
    }

    /* review_runwarn 为空是常态（D 的 run_log 没有警告），不摆一条空标题。
       它有没有值，上面那行统计里的「运行日志警告 N 项」已经回答了。 */
    var rw = data.memoCollection("review_runwarn");
    if (rw.length) {
      paper.appendChild(ui.subhead("运行日志警告"));
      var ul2 = ui.el("ul", "warn-list");
      rw.forEach(function (it) {
        var r = data.memoRow(it, ["text"]);
        ul2.appendChild(ui.el("li", null, r.text === null ? MISS_TEXT : r.text));
      });
      paper.appendChild(ul2);
    }
  }

  /* ==================================================================== */
  /* ⑦ 数据来源与免责声明                                                 */
  /* ==================================================================== */
  function secSources(ui, fmt, data, paper, col) {
    paper.appendChild(secHead(ui, col, "数据来源与免责声明"));

    var srcs = data.memoCollection("sources");
    if (srcs.length) {
      paper.appendChild(ui.subhead("数据来源"));
      /* ★ 2026-10-13 第七轮：删掉「获取时间」这一列。
         反馈原话：「数据来源部分去掉『获取时间』一列」。
         查过 D 交付的 memo.sources：**每一行的 retrieved_at 都是「未标注」**
         （12 行、12 个「未标注」）—— 这一列占着宽度、不进任何信息，
         而且「未标注」三个字会被读成「E 没填」，实际是 D 的抽取器没有这个字段。
         ★ 判据仍然落在数据上：这里不写 `if (retrieved_at)` 之类的条件渲染，
           而是**整列去掉** —— 一列全是同一个占位符，不是「有的有有的没有」，
           条件渲染只会让表头对齐随数据变。D 哪天真的补上取值时间，
           要恢复这一列是把它加回 headers，不是恢复一个空列。 */
      paper.appendChild(table(ui, ["文件名", "页码"],
        srcs.map(function (it) {
          var r = data.memoRow(it, ["file_name", "page"]);
          return [r.file_name, r.page === null ? null : "P." + r.page];
        })));
      paper.appendChild(muted(ui, "页码为年报原始印刷页码，可逐条核对。"));
    }

    var body = ui.el("div", "paper-body");
    var d1 = val(data, "disclaimer");
    var d2 = val(data, "group_disclaimer");
    if (d1 || d2) {
      body.appendChild(ui.el("h3", "blk-title", "免责声明"));
      if (d1) body.appendChild(ui.el("p", null, d1));
      if (d2) body.appendChild(ui.el("p", null, d2));
    }
    if (body.children.length) paper.appendChild(body);
  }

  /* ==================================================================== */
  /* 空状态 / 操作区 / 开发卡                                             */
  /* ==================================================================== */

  function emptyPaper(ui) {
    var paper = ui.el("div", "paper");
    var ph = ui.el("div", "paper-empty");
    ph.appendChild(ui.el("div", "paper-empty-title", "投研简报尚未生成"));
    ph.appendChild(ui.el("p", "paper-empty-text",
      "memo 绑定表未提供。本页等待 D 的简报渲染产物 "
      + "out_data/reports/<key>/memo.json。"));
    paper.appendChild(ph);
    return paper;
  }

  function actions(ui) {
    var row = ui.el("div", "action-row");
    /* ★ 2026-10-13 第七轮：按钮从 .btn-ghost 改成 .btn-primary（橙底深墨字）。
       反馈原话：「打印 / 导出 PDF 按钮调整为橙色」。
       直接复用 .btn-primary 而不是新加一个 .btn-print —— 橙色令牌**只有一个**
       （--c-watch），新开类只会再造一处「同一个橙写两遍」的地方。
       语义上它也站得住：橙 = 「强调 = 可行动 + 需关注」，
       全页只有这一个按钮，它就是这个页面上唯一要人动手的东西。 */
    var btn = ui.el("button", "btn btn-primary", "打印 / 导出 PDF");
    btn.addEventListener("click", function () { window.print(); });
    row.appendChild(btn);
    return row;
  }

  function specCard(spec, ui, note) {
    var block = ui.card("dev-card");
    block.appendChild(ui.subhead("本页待确认"));
    block.appendChild(ui.todoList(spec));
    if (note) block.appendChild(ui.note(note, "warn"));
    return block;
  }
})();
