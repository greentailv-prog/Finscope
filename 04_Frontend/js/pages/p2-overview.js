/* ============================================================================
 * p2-overview.js —— 页面2 公司概览
 * ----------------------------------------------------------------------------
 * 职责：公司抬头 + 三个核心大数（营收 / 归母净利润 / ROE）+ 主要财务数据表。
 * 数据来源：company / financials（D 定义、A 抽全）、
 *          ratios.profitability.roe_weighted（B）
 *
 * 【2026-10-13 对齐 D 之后，本页撤掉了两块】
 *   主营构成（business_mix）与多期趋势（history）**没有源** ——
 *   A 的抽取结果顶层只有 company / financials / extraction_meta 三段，
 *   四个队友谁也不产出这两个字段。E 原来按「A 以后会给」把界面做完了、
 *   跑着 mock，那是把不存在的接口当既有接口在用。按授权从 E 撤掉。
 *
 *   代价要说清楚：本页因此从「五块」变成「三块」，比原来薄。
 *   ★ 2026-10-13：用 D 给的 prior_value / prior_period 把密度补回来了 ——
 *   财务数据表加一列「上期」+ 一行表头，五列：科目 / 本期 / 上期 / 相对大小 / 出处。
 *   上期值走 dataLoader 已打包的 r.prior，**E 不自己找上期、更不算同比**
 *   （同比是 B 的成长性维度）。整块一个 prior 都没有时自动退回四列。
 *
 * 【版式定案 2026-10-10】
 *   1. 本页讲一句话：**数字必须可验证**（DEMO_SCRIPT.md:42 的演示台词）。
 *      所以版面重心不是「几个好看的数」，是「每个数旁边都有一条能点开的页码」。
 *   2. **本页零 tone**。曾经想过给三个大数配同比的涨跌色，否掉了：
 *      卡片顶边和右上角健康度标签已经在用 status 色，再加一套红涨绿跌，
 *      同一张卡上红色会同时表示「上涨」和「差」。同比归页面 3 的成长性维度讲，
 *      那里已经是它的主场。（base.css 的 tone 因此全站无使用，保留待用）
 *   3. **主要财务数据分三块，每块保留报表自身的形状**，不套同一个模板：
 *      利润表有缩进与「减：」，资产负债表有「其中：」的从属关系，
 *      现金流量表的三项净额沿零点线分左右（正负号是流向，不是大小）。
 *      分组顺序与形状定义见 dataLoader 的 FINANCIAL_BOOK。
 *   4. **每行配一条比例条**，条长按本块内最大科目归一。这是显示缩放，
 *      不是金融比率 —— 脚注里写明了，免得被读成「占营收比」。
 *      「快慢两条车道」也在这里：头条科目大一号，其余退到次级，
 *      16 行一样的粗细等于没有重点。
 *   5. **出处一律低调**：小一号、灰色、虚线，紧贴在它支撑的那个数字右侧。
 *      全站原则见 css/components.css 的 .page-link 注释。
 *   6. 大数缺失时显示「未提取」而不是破折号 —— 破折号分不清「没有」和「是零」。
 *
 * 注意：ROE 来自 B，**没有单一页码**（它是几个科目算出来的），
 *       所以它的来源行写「由财务数据计算得出」，不显示成缺数据。
 *       ★ 且它不能走 fmt.metric() —— 见 HEADLINE 下面的注释。
 * ==========================================================================*/

(function () {
  "use strict";
  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  /* --------------------------------------------------------------------------
     三个核心大数
     --------------------------------------------------------------------------
     kind 决定取值与格式化走哪条路，**这两条路不能混**：
       · "fin"   财报科目 → data.item(path) → fmt.metric()，
                 单位由 D 的 unit 字段决定（元 → money() 归一到亿元）；
       · "ratio" 比率项   → data.ratioValue(key, item)，
                 单位的口径由 dataLoader 的 RATIO_META 逐条声明。
     ★ 这里踩过一次：roe_weighted 的 unit 是 "小数"、value 是 0.3446，
       而 "小数" 是个混装桶（既装百分数也装真倍数），fmt.metric() 分不出来，
       会显示成 "0.345" —— 一个毛利 91% 的公司，ROE 看着像 0.3%。
       所以比率项一律走 ratioValue，**永远不要**对它调 fmt.metric。 */
  var HEADLINE = [
    { label: "营业收入",   kind: "fin",   path: "financials.revenue",         metric: "营业收入" },
    { label: "归母净利润", kind: "fin",   path: "financials.net_income_parent", metric: "归母净利润" },
    { label: "ROE",        kind: "ratio", group: "profitability", key: "roe_weighted", metric: null }
  ];

  F.pages.p2 = {
    id: "p2",
    index: 2,
    title: "公司概览",
    subtitle: "Overview",

    spec: [
      "ROE 的 page 字段：D 的比值项目前一律 page = null（它是几个科目算出来的，"
        + "原本就不对应某一页）。页面因此写「由财务数据计算得出」，不显示成缺数据",
      "上期对照：D 已给 financials.*.prior_value / prior_period，"
        + "dataLoader 也已打包成 r.prior。★ 2026-10-13 已上版：五列为"
        + "科目 / 本期 / 上期 / 相对大小 / 出处，列宽改走 <colgroup>。"
        + "整块一个 prior 都没有时自动退回四列（不留 16 行破折号的空壳）"
    ],

    render: function (root) {
      var ui = F.ui, fmt = F.fmt, data = F.data;

      root.appendChild(ui.section(
        this.title,
        "公司基本面与核心财务数据一览。每一个数字都可以点开，回到它在年报里的位置。"
      ));

      root.appendChild(companyHead(ui, fmt, data));
      root.appendChild(headlineRow(ui, fmt, data));
      root.appendChild(financialTable(ui, fmt, data));

      /* ---- 待实现清单（.dev-card：演示模式会整张隐藏） ---- */
      var block = ui.card("dev-card");
      block.appendChild(ui.subhead("本页待实现"));
      block.appendChild(ui.todoList(this.spec));
      root.appendChild(block);
    }
  };

  /* ------------------------------------------------------------------ */
  /* 公司抬头                                                            */
  /* ------------------------------------------------------------------ */
  function companyHead(ui, fmt, data) {
    var head = ui.card();
    head.classList.add("company-head");

    var nameRow = ui.el("div", "company-name-row");
    nameRow.appendChild(ui.el("h2", "company-name",
      fmt.text(data.get("company.name"), "（公司名称未提供）")));
    nameRow.appendChild(ui.el("span", "ticker", fmt.text(data.get("company.ticker"), "—")));
    head.appendChild(nameRow);

    /* 四个属性芯片。字段名一律用 D 的（对齐方案决定 #2）：
         · 报告期用 report_period（"2025"），不是拼接出来的标题；
         · 报告类型用 report_type（"年度报告"）；
         · 交易所用 exchange。
       ★ 撤掉的 company.report_title / company.business / company.business_page
         三个字段 D 和 A 都不产出 —— 上一版那句「一句话业务定位」整块删除。
         它是本页唯一一段不是数字的内容，删除后抬头只剩名字和属性，
         这是「没有源就不画」的直接代价，不拿别的话去填。 */
    var meta = ui.el("div", "company-meta");
    addChip(ui, fmt, meta, "行业", data.get("company.industry"));
    addChip(ui, fmt, meta, "报告期", data.get("company.report_period"));
    addChip(ui, fmt, meta, "报告类型", data.get("company.report_type"));
    addChip(ui, fmt, meta, "交易所", data.get("company.exchange"));
    head.appendChild(meta);

    return head;
  }

  /* 一个属性芯片。值为空时**整格不出现** ——
     一排「行业：— 报告期：— 」比少一格更难看，也没多告诉人任何事。 */
  function addChip(ui, fmt, row, label, value) {
    if (fmt.isNil(value)) return;
    row.appendChild(ui.el("span", "meta-chip", label + "：" + value));
  }

  /* ------------------------------------------------------------------ */
  /* 三个核心大数                                                        */
  /* ------------------------------------------------------------------ */
  function headlineRow(ui, fmt, data) {
    var row = ui.el("div", "metric-row");

    HEADLINE.forEach(function (m) {
      /* 取值：两条路各走各的。ratio 那条要同时拿到 item（判有无、取页码）
         和格式化好的文字（口径在 RATIO_META 里）。 */
      var path = m.kind === "fin" ? m.path : ("ratios." + m.group + "." + m.key);
      var item = data.item(path);
      var text = null;
      if (item) {
        text = m.kind === "fin" ? fmt.metric(item) : data.ratioValue(m.key, item);
      }

      var c = ui.el("div", "metric-card");
      c.appendChild(ui.el("div", "metric-label", m.label));

      /* 大数缺失时写「未提取」，不写破折号 ——
         「—」分不清是没有这个数、还是这个数就是零。 */
      if (!item) {
        c.appendChild(ui.el("div", "metric-value is-missing", "未提取"));
      } else {
        c.appendChild(ui.el("div", "metric-value", text));
      }

      /* 来源行分两种情况：
         A 抽出来的财务数据项带页码 → 做成可点击的溯源链接；
         B 算出来的比率没有单一页码（是几个科目算出来的）→ 说明来源方式即可，
         不能显示成「—」，那会让人以为数据缺失。 */
      var srcBox = ui.el("div", "metric-source");
      if (!item) {
        srcBox.textContent = "无数据可溯源";
      } else if (item.page !== null && item.page !== undefined) {
        srcBox.appendChild(ui.sourceLink(fmt.source(item), {
          metric: m.metric,
          page: item.page,
          item: item
        }));
      } else {
        srcBox.textContent = m.kind === "ratio"
          ? "由财务数据计算得出"
          : "未标注页码";
      }
      c.appendChild(srcBox);

      /* 健康度色只用 status 系统，本页不出现 tone。
         ★ D 的比值 status 是 ok / not_evaluable / not_meaningful，
           含义是「算不算得出来」不是「好不好」，statusClass 因此不给
           ok / found 上色（见 format.js 的长注释）。这里照传即可。
         ⚠️ 必须走 ui.addClass 而不是 classList.add —— 上面那几档
           statusClass 返回的是**空串**，直接喂给 classList 会抛异常。
           这一条踩过：页面 2 曾经整页白屏，就出在这一行。 */
      if (item && item.status) {
        ui.addClass(c, fmt.statusClass(item.status));
        if (!fmt.statusQuiet(item.status)) {
          c.appendChild(ui.el("span", "metric-status", fmt.statusLabel(item.status)));
        }
      }

      row.appendChild(c);
    });

    return row;
  }

  /* ------------------------------------------------------------------ */
  /* 主要财务数据：三张报表，各有各的形状                                */
  /* ------------------------------------------------------------------ */
  /* 这是本页撑起「可验证」那句话的地方：16 个科目每个都带年报页码。
     但**把 16 行排成一张同样的表，等于没排** —— 一样的字号、一样的颜色、
     一样的列宽，眼睛没有落点。所以这里做三件事：
       ① 按报表自身形状排（缩进层级 / 其中： / 净额分流），不套同一个模板；
       ② 每行配一条比例条，大小关系不用读数字就看得出来；
       ③ 每张表一行头条科目（字号大一档），其余退到次一级 —— 快慢两条车道。
     条长按**本表内**最大科目归一（纯显示缩放，与画柱状图算刻度同类）
     不是金融比率，脚注里写清楚了，免得被读成「占营收比」。 */
  function financialTable(ui, fmt, data) {
    var groups = data.financialGroups();

    /* 挂 card-dense：这张卡有 16 行科目 + 比例条，是站上最密的一张。
       毛玻璃默认那档（0.60）让背景透上来，行底色会随渐变轻微漂移。
       加这个类走强玻璃（0.82）。**.card 用不了 :has()** ——
       file:// 下不知道对面是什么浏览器，不敢赌，所以在 JS 里显式标。 */
    var card = ui.card("card-dense");
    card.appendChild(ui.subhead("主要财务数据"));

    var total = groups.reduce(function (n, g) { return n + g.items.length; }, 0);
    if (!total) {
      card.appendChild(ui.empty("financials 字段尚未提供，主要财务数据表暂无法生成。"));
      return card;
    }

    groups.forEach(function (g) { card.appendChild(statementBlock(ui, fmt, g)); });

    card.appendChild(ui.note(
      "条形长度按本表内最大科目等比缩放，只用于比较同一张报表内的相对大小，"
        + "不是任何比率。点任意一行的页码，可以看这个数字来自年报的哪一节、哪一页。"
        + "页面 3 的比率、页面 4 的证据链、页面 5 的估值对象都建立在这些数之上。",
      "info"
    ));

    return card;
  }

  /* 一张报表 = 一个块 */
  function statementBlock(ui, fmt, g) {
    var block = ui.el("div", "fin-block");

    /* 表头：报表名 + 该表的头条科目。看一眼就知道这块是什么、多大。 */
    var head = ui.el("div", "fin-block-head");
    head.appendChild(ui.el("span", "fin-block-name", g.label));
    var top = g.items.filter(function (r) { return r.key === g.headline; })[0] || g.items[0];
    head.appendChild(ui.el("span", "fin-block-flag",
      top.name + " " + fmt.metric(top.item)));
    block.appendChild(head);

    /* 归一基准：本表内绝对值最大的科目（不跨表比 —— 利润表和资产负债表
       根本不是一个量纲，跨表比条形毫无意义） */
    var max = 0;
    g.items.forEach(function (r) {
      var v = fmt.toNum(r.item);
      if (v !== null && Math.abs(v) > max) max = Math.abs(v);
    });

    /* ★ 2026-10-13 新增「上期」列。取值走 dataLoader 已经打包好的 r.prior
       （= { value, period, unit }，来自 D 的 prior_value / prior_period），
       **E 不自己去找上期、也不自己算同比** —— 同比是 B 的活。
       prior 是整列存在与否的判断依据，不是逐行判断：
       D 要么每个科目都给 prior_value，要么都不给。
       一个都没有时**整列不画**（也不画表头那一格），免得出现 16 行破折号的空壳。 */
    var hasPrior = g.items.some(function (r) { return !!r.prior; });

    var tb = ui.el("table", "fin-table" + (hasPrior ? "" : " is-4col"));

    /* 列宽走 colgroup 而不是 td 类名 —— 见 css/components.css 的注释：
       table-layout: fixed 按第一行取列宽，有了表头行之后第一行就是表头。 */
    var cols = ["c-name", "c-value"];
    if (hasPrior) cols.push("c-prior");
    cols.push("c-bar", "c-source");
    var cg = ui.el("colgroup");
    cols.forEach(function (c) { cg.appendChild(ui.el("col", c)); });
    tb.appendChild(cg);

    /* 表头行。期间（本期 2025 / 上期 2024）是从数据里读的，**不写死年份** ——
       D 换一份年报，这里得跟着变。整列都没有 Period 就只写「本期 / 上期」。 */
    tb.appendChild(finHeadRow(ui, fmt, g, hasPrior));

    var tbody = ui.el("tbody");

    g.items.forEach(function (r) {
      var it = r.item || {};
      var v = fmt.toNum(it);

      var tr = ui.el("tr", "fin-row");
      if (r.key === g.headline) tr.classList.add("is-headline");
      if (r.gap) tr.classList.add("is-gap");

      /* 科目：缩进层级 + 行前缀（减： / 其中：） */
      var tdName = ui.el("td", "fin-name");
      if (r.op) tdName.appendChild(ui.el("span", "fin-op", r.op));
      if (r.indent) tdName.classList.add("indent-" + r.indent);
      tdName.appendChild(ui.el("span", "fin-label", r.name));
      tr.appendChild(tdName);

      /* 本期值。status 不是 found 时给个淡色小字 ——
         不标出来的话，读者会以为这一格是 E 没填。
         ⚠️ 这个分支**只接得住「进来了的行」**。not_applicable（这一项对这家
           公司不成立，如茅台没有商誉）已经在 dataLoader 的 financialGroups
           里整行滤掉了，走不到这里 —— 所以下面的例子举的是别的档。
         见 dataLoader.js 的 isNotApplicable。 */
      var tdVal = ui.el("td", "fin-value");
      tdVal.appendChild(ui.el("span", null, fmt.metric(it)));
      if (it.status && it.status !== "found") {
        tdVal.appendChild(ui.el("span", "dim",
          "（" + fmt.statusLabel(it.status) + "）"));
      }
      tr.appendChild(tdVal);

      /* 上期值：跟本期**同一条格式化路径**（fmt.metric + 同一个 unit），
         两列的数字必须是一个模子刻出来的，否则对照就无从谈起。
         D 没给这一格的值时给破折号 —— 不写 0，也不留空。 */
      if (hasPrior) tr.appendChild(priorCell(ui, fmt, r));

      /* 比例条。diverging 表（现金流量表）用零点线分左右；
         其余从左端起算。**行可以覆写所在块的形状** ——
         现金流量表里的资本开支是流出额、不是净额，不参与左右分流。
         数值取不到就不画条，不留一根空轨道。 */
      var tdBar = ui.el("td", "fin-bar-cell");
      tdBar.appendChild(barFor(ui, r.shape || g.shape, v, max));
      tr.appendChild(tdBar);

      /* 出处：有页码才给链接，没有就给灰破折号 —— **不编一个链接出来** */
      var tdSrc = ui.el("td", "col-source");
      if (it.page !== null && it.page !== undefined) {
        tdSrc.appendChild(ui.sourceLink(fmt.page(it.page), {
          metric: r.name, page: it.page, item: it
        }));
      } else {
        tdSrc.appendChild(ui.el("span", "dim", fmt.MISSING));
      }
      tr.appendChild(tdSrc);

      tbody.appendChild(tr);
    });

    tb.appendChild(tbody);

    /* ★ 2026-10-13：整张表包一层横向滚动壳（.table-scroll）。
       窄窗口下这张五列表放不下 —— 数字是 nowrap 的，放不下就直接溢出、
       压到隔壁的上期列和比例条上（实测窗口 1000px 有 4 处、950px 有 20 处）。
       为什么是滚动而不是换行/裁切，见 css/components.css 的 .fin-table
       { min-width } 那条注释。宽屏下这层壳不产生任何滚动条。 */
    var scroller = ui.el("div", "table-scroll");
    scroller.appendChild(tb);
    block.appendChild(scroller);
    return block;
  }

  /* 表头行：科目 / 本期（2025）/ 上期（2024）/ 相对大小 / 出处。
     为什么值得占一行，见 css/components.css 的 .fin-head-row 注释。 */
  function finHeadRow(ui, fmt, g, hasPrior) {
    var thead = ui.el("thead");
    var tr = ui.el("tr", "fin-head-row");

    tr.appendChild(ui.el("th", "h-name", "科目"));

    /* 期间只在**整块第一行**取一次。D 的 prior_period 是全表同一个年份
       （实测 17 个科目里 16 个带值、period 一律 "2025"、prior_period 一律 "2024"），
       逐行重复写等于 17 遍噪声。 */
    var period = null, priorPeriod = null;
    g.items.forEach(function (r) {
      var it = r.item || {};
      if (period === null && !fmt.isNil(it.period)) period = it.period;
      if (priorPeriod === null && r.prior && !fmt.isNil(r.prior.period)) {
        priorPeriod = r.prior.period;
      }
    });

    tr.appendChild(ui.el("th", "h-value", "本期" + (period ? "（" + period + "）" : "")));
    if (hasPrior) {
      tr.appendChild(ui.el("th", "h-prior", "上期" + (priorPeriod ? "（" + priorPeriod + "）" : "")));
    }
    tr.appendChild(ui.el("th", "h-bar", "相对大小"));
    tr.appendChild(ui.el("th", "h-source", "出处"));

    thead.appendChild(tr);
    return thead;
  }

  /* 一格里放上期值。走 fmt.metric 而不是 fmt.num：
     单位、千分位、元→亿元全都得跟本期同一套，手工拼字符串迟早会岔开。 */
  function priorCell(ui, fmt, r) {
    var td = ui.el("td", "fin-prior");
    if (!r.prior || fmt.isNil(r.prior.value)) {
      td.appendChild(ui.el("span", "dim", fmt.MISSING));
      return td;
    }
    td.appendChild(ui.el("span", null, fmt.metric(r.prior)));
    return td;
  }

  /* 一根比例条。pct 是占本表最大值的百分比，四舍五入到 2 位 ——
     不取整的话内联样式里会出现 16.666666666666664% 这种噪声。 */
  function barFor(ui, shape, v, max) {
    var track = ui.el("div", "fin-track" + (shape === "diverging" ? " is-diverging" : ""));
    track.title = "条长按本表内最大科目等比缩放";

    if (v === null || max <= 0) return track;

    var pct = Math.round((Math.abs(v) / max) * 10000) / 100;
    var bar = ui.el("div", "fin-bar");
    if (v < 0) bar.classList.add("is-neg");

    /* 定位一律写在行内：绝对定位下 left / right / width 三者同时存在会过约束，
       CSS 里留一个默认值就会让负向条跑到右边去。所以两条分支都把 left 或 right
       显式定死，CSS 里不设默认。 */
    if (shape === "diverging") {
      /* 零点线在轨道正中，正数往右、负数往左 */
      bar.style.width = (pct / 2) + "%";
      if (v < 0) bar.style.right = "50%";
      else bar.style.left = "50%";
    } else {
      /* 普通幅度条：从左边起算，取绝对值 —— 资本开支是流出额，
         与净额不是同一类数，只用来看「多大」，不用来看「流向」。 */
      bar.style.left = "0";
      bar.style.width = pct + "%";
    }
    track.appendChild(bar);
    return track;
  }
})();
