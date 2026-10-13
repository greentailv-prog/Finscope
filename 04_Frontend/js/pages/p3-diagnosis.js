/* ============================================================================
 * p3-diagnosis.js —— 页面3 财务诊断
 * ----------------------------------------------------------------------------
 * 职责：五维能力（成长性 / 盈利能力 / 偿债能力 / 营运能力 / 现金流质量）
 *       的指标明细。
 * 数据来源：ratios（B 算、D 统一）。每项
 *   { value, unit, period, formula, page, prev, delta, inputs, status, higher_is_better }
 *
 * 【2026-10-13 对齐 D：这一页改了三个根本假设】
 *
 *   ① **没有得分了。** 上一版整页建立在 `ratios.<维度>._score` 上 —— 一张
 *      五维雷达图 + 每个维度块右上角的大号得分。D 的 ratios **不产出 _score**，
 *      而且这不是「忘了给」，是它压根不做打分这件事：D 给的是
 *      `status: ok / not_evaluable / not_meaningful`，含义是
 *      「**这一项算不算得出来**」，不是「好不好」。
 *      所以雷达图整块删除、得分显示整块删除。**不自己凑一个分数出来** ——
 *      那既不是 B 的判断也不是 D 的判断，是 E 的判断，越权了。
 *
 *   ② **一个维度不是 3–4 项，是 10–18 项。** D 的 ratios 一共 68 项
 *      （growth 10 / profitability 18 / solvency 14 / efficiency 12 /
 *      cashflow_quality 14）。全平铺的话五个块各十几行，一屏读不完，
 *      而且「哪几个是重点」这件事被摊平掉了。
 *      改法：**核心指标常显，其余折进「其余 N 项」**。
 *      核心名单来自 js/contract.js 的 INDICATORS —— 不在这里另抄一份。
 *      ★ 2026-10-13 第六轮更正：这一段原来写着「复用已有的 .ratio-detail +
 *      .is-open 机制，没有新增 CSS」——**是错的**，而且错得刚好藏住了 bug。
 *      .ratio-detail 是**另一件事**（点开看公式的那一行），
 *      被折叠的主行是 .ratio-row，而 .ratio-row.is-open 只改背景色，
 *      收不起来。CSS 里没有 .is-folded 这条规则，等于折叠一直是死的：
 *      五个块全部平铺 10–18 行，「其余 N 项（点这里展开）」插在中间被读成分节线。
 *      现在补上了 .ratio-row.is-folded { display: none } 与它的 .is-open 分支。
 *
 *   ③ **status 的语义换了，颜色映射跟着换。** 见 format.js 的 statusClass：
 *      ok 不上色（算出来了不等于好）、not_evaluable 上橙（需要有人去做点什么）、
 *      not_meaningful 不上色（不是问题，是事实）。
 *      所以本页的橙只出现在「待核验」上 —— 橙出现即「这里有活要干」。
 *
 * 【沿用上一版的版式定案】
 *   1. **本页零 tone**。得分和比率都是水平值，没有涨跌方向。
 *   2. **出处贴在被支撑的数据旁边**：有 page 的指标在指标名下挂一行灰色
 *      可点页码。★ 2026-10-13 更正：这一段原来写着「D 的比值项一律 page = null，
 *      所以本页一个页码链接都没有」——**与实测不符**。真数据里 68 项有 2 项带了
 *      page（现金流质量的 ocf @6、capex @13），页面也确实把它们渲染出来了。
 *      绝大多数比值项仍然是 page = null，那是对的（比率由几个科目算出，
 *      本来就不对应某一页），但这个「有则渲染、无则整格不放」的行为
 *      不该被写成「一律没有」。也不为此写提示条 —— 缺的是可选字段，不是缺口。
 *   3. **五个维度块两栏并排**，一屏看全五维。窄屏自动退回单栏。
 *   4. **每块给一句话结论**，只报例外（「14 项指标中 4 项待核验」），
 *      全算得出时才报总数。
 *   5. **待核验行左边加一道 2px 状态色**。其余行不涂 —— 对比才是指示。
 *
 * 注意：E 不判断指标好坏。颜色与结论全部来自数据里的 status 字段。
 * ==========================================================================*/

(function () {
  "use strict";
  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  F.pages.p3 = {
    id: "p3",
    index: 3,
    title: "财务诊断",
    subtitle: "Diagnosis",

    spec: [
      "比值项的 page 字段：D 只给得出 2 项（ocf / capex），其余 66 项都是 null，"
        + "这是对的 —— 比率由几个科目算出，本来就不对应某一页。"
        + "本页按「有则渲染、无则整格不放」处理，不写提示条（可选字段缺 ≠ 缺口）。"
        + "★ 但 D 若哪天想支持「点开看是哪几个科目」，要的是 inputs（已有），不是 page；"
        + "两个标准混用的结果是读者以为只有那两项能溯源",
      "三张偿债能力指标（current_ratio / quick_ratio / interest_coverage）"
        + "在 D 的交付里是 not_evaluable —— 缺的是流动负债、利息支出等科目，"
        + "那要 A 多抽几行。E 侧已经按「待核验」如实显示，不去替它算",
      "维度间联动（点一个维度高亮）—— 页面本身不长，收益小于复杂度，暂缓"
    ],

    render: function (root) {
      var ui = F.ui, fmt = F.fmt, data = F.data;

      root.appendChild(ui.section(
        this.title,
        "从成长性、盈利能力、偿债能力、营运能力、现金流质量五个维度看公司财务。"
             + "指标值、公式与状态均来自财务诊断模块，前端只做呈现。"
      ));

      var groups = data.ratioGroups();

      if (!groups.length) {
        root.appendChild(emptyCard(ui));
        return;
      }

      /* 顶部说清这一页读什么。★ 原来这条注释讲的是「得分不是我们算的」，
         现在没有得分了，注释改成讲**状态词的含义** ——
         这是读这一页最容易读错的地方：看到一片灰以为「都好」。 */
      var intro = ui.card();
      intro.appendChild(ui.note(
        "每项指标后面若跟着「待核验」，意思是「这一项算不出来」（缺上游科目），"
          + "不是「这一项很差」；「不适用」意思是这项对该公司没有意义"
          + "（如无商誉的公司算不出商誉占比）。算得出来的项不标注 ——"
          + "一片素净才是正常，有橙色才说明有活要干。",
        "info"
      ));
      root.appendChild(intro);

      /* 两栏并排：一屏看全五维。
         原先五个维度块竖着排，要滚两屏才看完，而且每块都是同一个形状，
         读到第三块就没有分辨度了。 */
      var grid = ui.el("div", "dim-grid");
      groups.forEach(function (g) {
        grid.appendChild(dimBlock(ui, fmt, data, g));
      });
      root.appendChild(grid);

      /* ---- 待实现清单（.dev-card：演示模式会整张隐藏） ---- */
      var block = ui.card("dev-card");
      block.appendChild(ui.subhead("本页待实现"));
      block.appendChild(ui.todoList(this.spec));
      block.appendChild(ui.note(
        "指标中文名的唯一来源是 dataLoader.js 的 RATIO_META（68 项逐条登记）。"
             + "D 的比值项「不带 name 字段」，所以这不是兜底表，是唯一来源 ——"
             + "D 加了新指标，这里必须跟着加一行，否则显示成英文键名。",
        "info"
      ));
      root.appendChild(block);
    }
  };

  function emptyCard(ui) {
    var c = ui.card();
    c.appendChild(ui.empty("ratios 字段尚未提供，财务诊断暂无法生成。"));
    return c;
  }

  /* ------------------------------------------------------------------ */
  /* 一个维度 = 一块                                                     */
  /* ------------------------------------------------------------------ */
  function dimBlock(ui, fmt, data, g) {
    var items = data.ratioItems(g.key);

    var block = ui.el("div", "card dim-block");

    /* ---- 表头 ---- */
    /* 右上角原来是一个大号的「/ 100」得分。得分没了之后这里改放
       **这一维度有活要干的项数** —— 它是这一块里唯一一个跨行才数得出来的数，
       放在表头才不用逐行扫。全算得出时这个位置不占。 */
    var head = ui.el("div", "dim-head");
    head.appendChild(ui.el("h3", "dim-name", g.label));

    var counts = countByStatus(items);
    if (counts.not_evaluable) {
      var flag = ui.el("span", "status-chip is-watch",
        counts.not_evaluable + " 项待核验");
      flag.title = "这几项因为缺上游科目算不出来，需要补数据";
      head.appendChild(flag);
    }
    block.appendChild(head);

    /* ---- 健康分布色条 ---- */
    /* 色条上只画「待核验」。理由：ok 与 not_meaningful 都**不需要动作**，
       把它们也涂成颜色，色条就永远满着，橙色就不再是信号了。
       全维度没有待核验项时给一条空槽 —— 空槽本身就是「这块没事」。 */
    var barRow = ui.el("div", "dim-bar-row");
    var bar = ui.el("div", "status-bar");
    if (counts.not_evaluable) {
      var seg = ui.el("span", "status-seg is-watch");
      seg.style.flex = counts.not_evaluable;
      seg.title = "待核验：" + counts.not_evaluable + " 项";
      bar.appendChild(seg);
      var rest = ui.el("span", "status-seg is-empty");
      rest.style.flex = Math.max(items.length - counts.not_evaluable, 0.001);
      rest.title = "已算出或本项不适用：" + (items.length - counts.not_evaluable) + " 项";
      bar.appendChild(rest);
    } else {
      bar.appendChild(ui.el("span", "status-seg is-empty"));
    }
    barRow.appendChild(bar);

    /* 一句话结论。颜色取**本维度最差**的那一档 —— 这只是把同一组里
       最严重的那个标签抬到句子上，没有新增任何判断。 */
    var meta = ui.el("div", "dim-meta" + (counts.not_evaluable ? " is-watch" : ""),
      dimConclusion(counts, items.length));
    barRow.appendChild(meta);
    block.appendChild(barRow);

    /* ---- 指标表 ---- */
    if (!items.length) {
      block.appendChild(ui.empty("该维度暂无指标数据。"));
      return block;
    }

    var core = items.filter(function (x) { return x.isCore; });
    var rest = items.filter(function (x) { return !x.isCore; });

    var tb = ui.el("table", "ratio-table");
    var tbody = ui.el("tbody");

    core.forEach(function (x) { addRow(ui, fmt, tbody, x, true); });

    /* 其余项：折起来。一个「点一下展开」的行，展开的是一组行。
       ★ 折叠组挂 .is-folded（见 addRow），CSS 里对应 .ratio-row.is-folded。
       没有核心名单时（契约没加载）core 为空，这里就不会出现折叠头，
       全部指标常显 —— 退化成「平铺」，能读，只是没有主次。 */
    if (rest.length) {
      var folded = [];
      rest.forEach(function (x) {
        addRow(ui, fmt, tbody, x, false, folded);
      });

      var toggle = ui.el("tr", "ratio-row");
      var td = ui.el("td", "ratio-name");
      td.colSpan = 3;
      var toggleLabel = ui.el("span", "ratio-label dim",
        "其余 " + rest.length + " 项指标（点这里展开）");
      td.appendChild(toggleLabel);
      toggle.appendChild(td);

      toggle.addEventListener("click", function () {
        var open = !folded[0].classList.contains("is-open");
        folded.forEach(function (r) { r.classList.toggle("is-open", open); });
        toggle.classList.toggle("is-open", open);
        toggleLabel.textContent = open
          ? "收起 " + rest.length + " 项指标"
          : "其余 " + rest.length + " 项指标（点这里展开）";
      });

      tbody.insertBefore(toggle, folded[0]);
    }

    tb.appendChild(tbody);
    block.appendChild(tb);

    return block;
  }

  /* 一行指标。openable=true 时行下方挂一条可展开的公式行。
     collect 不为空时，这一行会被收进折叠组（加了 is-open 才显示）。 */
  function addRow(ui, fmt, tbody, x, openable, collect) {
    var it = x.item;

    var tdName = ui.el("td", "ratio-name");
    tdName.appendChild(ui.el("span", "ratio-label", x.label));
    if (x.page !== null && x.page !== undefined) {
      var sl = ui.el("span", "ratio-src");
      sl.appendChild(ui.sourceLink(fmt.page(x.page), {
        metric: x.label, page: x.page, item: it
      }));
      tdName.appendChild(sl);
    }

    var tr = ui.el("tr", "ratio-row");
    /* 状态类名用 st-* 前缀，不复用全局的 is-good/is-watch/is-bad ——
       那三个是**文字颜色**类，挂到 tr 上会把整行文字染色。
       这里要的是左边那一道 2px 色条，只作用于第一个单元格。
       ★ D 只会给出 not_evaluable 一种需要着色的值，所以实际只有 st-watch。 */
    if (it.status) tr.classList.add("st-" + it.status);
    tr.appendChild(tdName);

    /* 值。取不到值时紧跟着一个淡色说明（「不适用」/「待核验」）——
       光一个破折号分不清是「E 没填」还是「这项本来就没有」。
       ★ 用 x.text，不要用 fmt.metric(it)：比率的口径按 RATIO_META 逐条声明。 */
    var tdVal = ui.el("td", "ratio-value");
    tdVal.appendChild(ui.el("span", null, x.text));
    if (!x.quiet) {
      tdVal.appendChild(ui.el("span", "dim", "（" + fmt.statusLabel(it.status) + "）"));
    }
    tr.appendChild(tdVal);

    /* 状态胶囊**只在待核验时出现**。D 没有「好/差」这一档，
       给 ok 挂一个「正常」胶囊等于给 68 行里的 35 行挂同一个标签 ——
       挂满等于没挂（format.js 的 statusQuiet 就是在管这件事）。 */
    var tdStatus = ui.el("td");
    if (it.status === "not_evaluable") {
      tdStatus.appendChild(ui.el("span", "status-chip is-watch", "待核验"));
    }
    tr.appendChild(tdStatus);

    tbody.appendChild(tr);

    /* 展开行：怎么算的。默认隐藏，点主行切换。
       出处已经上移到主行，这里不再重复。
       ⚠️ 折叠组里的行**不给展开行** —— 折叠本来就是「这些先不看」，
       再套一层展开，点起来的层级就乱了。 */
    if (!openable) {
      if (collect) {
        /* ★ 2026-10-13 第六轮补的 is-folded。原来这里只 push 不挂类，
           而 CSS 里**根本没有一条规则收得起来** —— .ratio-row.is-open 只改背景色，
           被折叠的 7–14 行于是全部常显，「其余 N 项指标（点这里展开）」那行
           插在中间，被读成一条分节线。点它只会变一下底色，什么也不收。
           于是这一页的五个块全部平铺 10–18 行，再加上 grid-auto-rows: 1fr
           拉齐高度，短的块底下空出一大片 —— 就是「可读性不高」的真因。 */
        tr.classList.add("is-folded");
        collect.push(tr);
      }
      return;
    }

    var dr = ui.el("tr", "ratio-detail");
    var dc = ui.el("td");
    dc.colSpan = 3;

    if (x.formula) {
      dc.appendChild(ui.el("div", "detail-line", "计算公式：" + x.formula));
    }
    /* D 的比值项**没有 threshold 字段** —— 它不做「好/差」的阈值判断，
       只做「算不算得出来」。所以这里不再写「判断标准」那一行。 */
    if (it.higher_is_better === true) {
      dc.appendChild(ui.el("div", "detail-line dim", "方向：该指标越高越好"));
    } else if (it.higher_is_better === false) {
      dc.appendChild(ui.el("div", "detail-line dim", "方向：该指标越低越好"));
    }
    if (dc.children.length === 0) {
      dc.appendChild(ui.el("div", "detail-line dim", "该指标未提供公式。"));
    }

    dr.appendChild(dc);
    tr.addEventListener("click", function () {
      var open = dr.classList.toggle("is-open");
      tr.classList.toggle("is-open", open);
    });
    tbody.appendChild(dr);
  }

  /* ------------------------------------------------------------------ */
  /* 统计                                                                */
  /* ------------------------------------------------------------------ */
  /* D 的三档 + 认不出的兜底。认不出的键单列出来而不是塞进某一档 ——
     塞错档会让「待核验 N 项」这个数撒谎。 */
  function countByStatus(items) {
    var c = { ok: 0, not_evaluable: 0, not_meaningful: 0, other: 0 };
    items.forEach(function (x) {
      var s = x.status;
      if (Object.prototype.hasOwnProperty.call(c, s)) c[s]++;
      else c.other++;
    });
    return c;
  }

  /* 一句话结论。只报**例外**，没事时才报总数 ——
     「14 项指标全部算得出」是一句结论，「ok 10 / 不适用 4」是两个数。 */
  function dimConclusion(counts, n) {
    if (!n) return "暂无指标";
    var bits = [];
    if (counts.not_evaluable) bits.push(counts.not_evaluable + " 项待核验");
    if (counts.other)         bits.push(counts.other + " 项状态未知");
    if (!bits.length) return n + " 项指标全部算得出";
    return n + " 项指标中 " + bits.join(" · ");
  }
})();
