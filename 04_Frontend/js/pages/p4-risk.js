/* ============================================================================
 * p4-risk.js —— 页面4 风险雷达
 * ----------------------------------------------------------------------------
 * 职责：风险点列表。每条风险摊开证据链，从原始数据到结论可逐层复核。
 * 数据来源：risks[] + rules_evaluated[]（B 定规则、D 统一）
 *
 * 【2026-10-13 对齐 D：这一页的取证方式整个换了】
 *
 *   上一版 E 自己写了一个「公式代入层」：B 给一个 formula 字符串 + 一个 inputs
 *   对象，E 去拆字符串、按中文名反查每一侧对应哪个键、拼成
 *   「A 41.2% − B 18.4% = 22.8%」。难点全在「公式字符串与 inputs 对象的顺序
 *   不保证一致」，所以 E 写了一堆校验、拼不可靠就返回 null 让页面回落三行式。
 *   很谨慎，但很绕 —— 而且**整个是多余的**。
 *
 *   D 的 risks[].evidence_chain[] 直接给的就是**已经分好步骤的结构**：
 *     step: "数据" | "计算" | "出处" | "判断" | "归因" | "建议"
 *   每一步自带字段，没有任何东西需要 E 再拆字符串。所以那一整层删掉了，
 *   本页改成**顺着 evidence_chain 走**。
 *
 * 【D 的 risks 与 B 的 rules 是两份东西，都要用】
 *   · risks[]           —— **只装已触发的**（D 已按 status == "triggered" 过滤）。
 *                          一条风险 = 一张卡。
 *   · rules_evaluated[] —— **全部已评估的规则**（含通过的和算不出的）。
 *                          它回答的是「一共扫了几条」。600519 是 36 条里 4 条触发。
 *   ★ 少了后者，页面上只有 4 张卡会被读成「这家公司只有 4 个问题」；
 *     有了它才是「扫了 36 条，命中 4 条」。这是完全不同的两句话，
 *     所以概览条上必须写出来。
 *
 * 【版式定案 2026-10-10，沿用】
 *   1. 高风险卡片**默认展开**。这一页最值钱的就是证据链，不能藏在一次点击后面。
 *   2. 颜色只用 status 系统。本页零 tone —— 这里的数字是水平值。
 *      ★ 严重度三档：high → 红，medium → 橙，low → 灰。
 *        D 的 severity 就是 high / medium / low（并另给中文 severity_tag）。
 *   3. 三层用「链条」版式：左侧一条竖线，节点挂在线上。
 *      前面几层是事实（中性色），最后一层是结论（状态色）。
 *   4. **出处不单独占一层**。它是数据的附属属性，不是与数据平级的结论，
 *      所以并进「数据」那一层、以低调的可点击页码紧贴其支撑的那个数字。
 *   5. ③ 内部再分主次：解释是背景（灰底小字），建议是行动项（蓝底大字）。
 *
 * 注意：风险的触发与解释都是 B 的判断，E 只负责把证据链摊开给人看。
 * ==========================================================================*/

(function () {
  "use strict";
  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  F.pages.p4 = {
    id: "p4",
    index: 4,
    title: "风险雷达",
    subtitle: "Risk Radar",

    spec: [
      "evidence_chain 的六个 step（数据／计算／出处／判断／归因／建议）已按序渲染；"
        + "D 若新增 step，本页会「静默跳过」它 —— 这是刻意的，"
        + "画一个不认识的步骤不如不画（见本文件 stepRenderer 的 return null 分支）",
      "「算不出来的规则」目前只能数出条数，说不出「缺哪个变量」 ——"
        + "B 的 review_queue 里有 missing_inputs，但 D 的统一对象没透传。"
        + "若要显示「P03 待核验：缺 wacc」，需要 D 补这一节",
      "text_evidence.quote 在 600519 上全部是 null。字段在，但没有可用引文 ——"
        + "有值的样本会自动显示成引文块，前端零改动"
    ],

    render: function (root) {
      var ui = F.ui, data = F.data;

      root.appendChild(ui.section(
        this.title,
        "逐条规则扫描后的命中项。每条风险都摊开证据链，"
             + "从原始数据到结论可逐层复核。重大条目默认展开。"
      ));

      var risks = data.sortedRisks();
      var scan = data.rulesSummary();

      if (!risks.length) {
        var empty = ui.card();
        empty.appendChild(ui.empty(scan
          ? "已扫描 " + scan.total + " 条规则，无一触发。"
          : "未触发风险规则，或 risks 字段尚未提供。"));
        root.appendChild(empty);
      } else {
        root.appendChild(overviewBar(ui, data, scan));
        var list = ui.el("div", "risk-list");
        risks.forEach(function (r) { list.appendChild(riskCard(r, ui, data)); });
        root.appendChild(list);
      }

      var detail = scanDetail(ui, data, scan);
      if (detail) root.appendChild(detail);

      /* ---- 待实现清单（.dev-card：演示模式会整张隐藏） ---- */
      var block = ui.card("dev-card");
      block.appendChild(ui.subhead("本页待办"));
      block.appendChild(ui.todoList(this.spec));
      block.appendChild(ui.note(
        "证据链的每一层都直接来自 D 的 evidence_chain[]，E 只做排版与单位换算，"
             + "不重算、不补写、不排序。某个 step 缺字段时那一小段会降级为提示文字"
             + "（不静默留白），整条链的其余部分照常显示。",
        "info"
      ));
      root.appendChild(block);
    }
  };

  /* ==================================================================== */
  /* 概览条                                                                */
  /* -------------------------------------------------------------------- */
  /* 只说「各有几条」。刻意不写「优先处理：XX」这种提示 ——                 */
  /* 三色已经说清了严重性，再点一遍风险名是重复强调，反而稀释了颜色的信息量。 */
  /* ==================================================================== */
  function overviewBar(ui, data, scan) {
    var s = data.riskSummary();
    var bar = ui.el("div", "risk-overview");

    var stats = ui.el("div", "ro-stats");
    [
      { n: s.high,   sev: "high",   cls: "is-bad"   },
      { n: s.medium, sev: "medium", cls: "is-watch" },
      { n: s.low,    sev: "low",    cls: "is-good"  }
    ].forEach(function (x) {
      var it = ui.el("div", "ro-item");
      it.appendChild(ui.el("span", "ro-num " + x.cls, String(x.n)));
      it.appendChild(ui.el("span", "ro-label", F.fmt.severityLabel(x.sev)));
      stats.appendChild(it);
    });
    bar.appendChild(stats);

    /* ★ 这一句是这一页最容易缺、也最要紧的一句。
       只有 4 张卡时，读者的默认理解是「4 个问题」；
       加上「共扫描 36 条」之后，才是「扫了 36 条、命中 4 条」——
       后者同时说明了扫描的覆盖面和结论的克制。
       没有 rules_evaluated 时退化成只报触发数，但那种情况下要说明。 */
    var note = ui.el("div", "ro-note");
    if (scan) {
      var bits = ["已扫描 " + scan.total + " 条规则，触发 " + scan.triggered + " 条"];
      if (scan.passed) bits.push("通过 " + scan.passed + " 条");
      if (scan.other)  bits.push(scan.other + " 条因缺变量无法判断");
      note.appendChild(ui.el("span", "ro-hint-text", bits.join(" · ")));
    } else {
      note.appendChild(ui.el("span", "ro-hint-text",
        "共 " + s.total + " 条风险（D 未提供 rules_evaluated，无法给出扫描总数）"));
    }
    bar.appendChild(note);

    return bar;
  }

  /* 规则扫描明细。放在风险列表**下面** ——
     它讲的是「没触发的那些」，属于补充材料，不该压在结论前面。
     36 行确实长，但这一节回答的是「你们到底查了多少」，
     是这一页可信度的底账，不能只给一个数字。 */
  function scanDetail(ui, data, scan) {
    if (!scan) return null;

    var card = ui.card("card-dense");
    card.appendChild(ui.subhead("规则扫描明细"));

    var tb = ui.el("table", "mini-table");
    var thead = ui.el("thead");
    var hr = ui.el("tr");
    ["规则", "名称", "结果", "触发条件"].forEach(function (h) {
      hr.appendChild(ui.el("th", null, h));
    });
    thead.appendChild(hr);
    tb.appendChild(thead);

    var tbody = ui.el("tbody");
    (data.get("rules_evaluated", []) || []).forEach(function (r) {
      var tr = ui.el("tr");
      tr.appendChild(ui.el("td", "strong", F.fmt.text(r.rule_id)));
      tr.appendChild(ui.el("td", null, F.fmt.text(r.rule_name)));
      var tdSt = ui.el("td");
      tdSt.appendChild(ui.el("span", "status-chip " + ruleStatusClass(r.status),
        ruleStatusLabel(r.status)));
      tr.appendChild(tdSt);
      tr.appendChild(ui.el("td", "dim", F.fmt.text(r.trigger)));
      tbody.appendChild(tr);
    });
    tb.appendChild(tbody);
    card.appendChild(tb);

    card.appendChild(ui.note(
      "以上是全部被评估过的规则，含「没有触发」的那些 ——"
        + "「通过」和「无法判断」同样是结论：通过 = 查过了没问题，"
        + "无法判断 = 上游缺变量、这一条还欠着。不列出来的话，"
        + "读者没法区分「没查」和「查了没事」这两件事。",
      "info"));
    return card;
  }

  /* 只认三档：通过 = 绿，无法判断 = 橙（有活要干），不适用 = 素净。
     ★ 这里**没有** is-bad 这一档 —— D 不会把一条规则标成「失败」，
       只标「触发」（那是 risks[] 里的事）或「算不出」。 */
  function ruleStatusClass(s) {
    if (s === "passed") return "is-good";
    if (s === "not_evaluable") return "is-watch";
    return "";
  }

  /* D 的 rules_evaluated[].status 是 passed / not_evaluable / not_applicable
     （risks[] 里的那条则一定是 triggered）。 */
  function ruleStatusLabel(s) {
    return {
      passed: "通过",
      not_evaluable: "无法判断",
      not_applicable: "不适用",
      triggered: "已触发"
    }[s] || F.fmt.text(s, "—");
  }

  /* ==================================================================== */
  /* 单条风险卡片                                                          */
  /* ==================================================================== */
  function riskCard(r, ui, data) {
    var fmt = F.fmt;
    var sev = fmt.severityClass(r.severity) || "sev-normal";
    var isHigh = r.severity === "high";

    var box = ui.el("div", "risk-card " + sev);

    /* --- 头部 --- */
    var head = ui.el("div", "risk-head");
    /* 严重度标签优先用 D 给的 severity_tag（中文，如「重大」「关注」），
       severity 只是英文枚举。两个都给不出时才显示破折号。 */
    head.appendChild(ui.el("span", "sev-chip",
      !fmt.isNil(r.severity_tag) ? r.severity_tag : fmt.severityLabel(r.severity)));

    var ht = ui.el("div", "risk-head-text");
    /* 规则编号 + 类别缀在风险名下面。编号是这条风险与 B 的规则库之间的凭据 ——
       页面上要能对着下面那张「规则扫描明细」查回去。 */
    var tagline = [r.risk_id, r.category].filter(function (x) { return !fmt.isNil(x); });
    if (tagline.length) {
      ht.appendChild(ui.el("div", "dim", tagline.join(" · ")));
    }
    ht.appendChild(ui.el("div", "risk-name", fmt.text(r.risk_name)));
    if (r.trigger) ht.appendChild(ui.el("div", "risk-trigger", "触发规则：" + r.trigger));
    head.appendChild(ht);

    var toggle = ui.el("button", "risk-toggle");
    toggle.type = "button";
    head.appendChild(toggle);
    box.appendChild(head);

    /* --- 证据链 --- */
    var body = ui.el("div", "risk-body");
    var chain = ui.el("div", "risk-layers");
    /* 归因层可能整层不存在（D 的归因步是空的）—— 那时它返回 null，
       直接跳过。**不留一个空节点**：空节点会照常吃掉 .layer 的
       margin-top 和左边那条竖线，视觉上像少画了一段。 */
    [layerData(r, ui, fmt, data),
     layerCalc(r, ui, fmt, data),
     layerAttribution(r, ui, fmt, data),
     layerExplain(r, ui, fmt)].forEach(function (L) {
      if (L) chain.appendChild(L);
    });
    body.appendChild(chain);
    box.appendChild(body);

    /* --- 展开 / 收起 --- */
    function setOpen(open) {
      box.classList.toggle("is-open", open);
      toggle.textContent = open ? "收起证据链" : "展开证据链";
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
    setOpen(isHigh);                       /* 重大条目默认展开 */

    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(!box.classList.contains("is-open"));
    });
    /* 整个头部可点，命中区域大一些；按钮自身已在上面拦掉 */
    head.addEventListener("click", function () {
      setOpen(!box.classList.contains("is-open"));
    });

    return box;
  }

  /* ==================================================================== */
  /* 证据链分层                                                            */
  /* ==================================================================== */
  /* D 的 evidence_chain 是**按序排列的步骤数组**，同一个 step 可能出现多次
     （比如 C01 有两个「数据」步骤）。所以这里按 step 名归并，
     而不是按下标取 —— 下标会随规则不同而变。 */
  function stepsOf(r, name) {
    var chain = r.evidence_chain;
    if (!Array.isArray(chain)) return [];
    return chain.filter(function (s) { return s && s.step === name; });
  }

  /* 层骨架：左侧节点 + 右侧内容 */
  function layer(ui, num, title, kind) {
    var root = ui.el("div", "layer " + kind);
    root.appendChild(ui.el("div", "layer-mark", num));
    var content = ui.el("div", "layer-content");
    content.appendChild(ui.el("div", "layer-title", title));
    root.appendChild(content);
    return { root: root, content: content };
  }

  /* ---- ① 数据与出处 ----
     数据步：每一条是一个年报科目（revenue / ocf / net_income_parent…），
     带本期值、上期值、出处页码。
     ★ 上期值是 D 直接给的 prev_value，**不是 E 算的同比**；
       本页连增长率都不显示，因为那是页面 3 成长性维度的事。 */
  function layerData(r, ui, fmt, data) {
    var L = layer(ui, "1", "数据与出处", "is-fact");
    var rows = stepsOf(r, "数据");

    if (!rows.length) {
      L.content.appendChild(ui.note(
        "证据链里没有「数据」步骤 —— 这一层无法渲染。", "warn"));
    } else {
      var tb = ui.el("table", "mini-table");
      var thead = ui.el("thead");
      var hr = ui.el("tr");
      ["科目", "本期", "上期", "出处"].forEach(function (h) {
        hr.appendChild(ui.el("th", null, h));
      });
      thead.appendChild(hr);
      tb.appendChild(thead);

      var tbody = ui.el("tbody");
      rows.forEach(function (s) {
        var tr = ui.el("tr");
        tr.appendChild(ui.el("td", "strong", data.metricLabel(s.item)));
        tr.appendChild(ui.el("td", "metric-value",
          data.riskValue(s.item, s.value, s.unit)));
        tr.appendChild(ui.el("td", "dim",
          (s.prev_value === null || s.prev_value === undefined)
            ? fmt.MISSING
            : data.riskValue(s.item, s.prev_value, s.unit)));

        var tdSrc = ui.el("td", "col-source");
        if (s.page === null || s.page === undefined) {
          /* 没有页码就只能是灰破折号 —— 不编一个链接出来 */
          tdSrc.appendChild(ui.el("span", "dim", fmt.MISSING));
        } else {
          tdSrc.appendChild(ui.sourceLink(fmt.page(s.page), {
            metric: data.metricLabel(s.item),
            page: s.page,
            item: { value: s.value, unit: s.unit, page: s.page,
                    source: s.source, period: s.period }
          }));
        }
        tr.appendChild(tdSrc);
        tbody.appendChild(tr);
      });
      tb.appendChild(tbody);
      L.content.appendChild(tb);
    }

    /* 原文证据。600519 上 quote 全是 null，所以整块不出现 ——
       留一个「暂无引文」的占位反而让人以为本该有。 */
    var te = r.text_evidence;
    if (te && !fmt.isNil(te.quote)) {
      var srcs = (te.sources || []).join("、");
      var pages = (te.pages || []).join("、");
      var byline = [srcs, pages ? "P." + pages : ""].filter(Boolean).join("　");
      L.content.appendChild(ui.note(
        "年报原文：「" + String(te.quote) + "」" + (byline ? "　—— " + byline : ""),
        "info"));
    }

    return L.root;
  }

  /* ---- ② 计算与判断 ---- */
  /* 「计算」步给的是 rule 的触发表达式 + 代进去的变量值；
     「判断」步给的是这条规则的完整条件、结果、以及它自己的严重度。
     ★ 两处都直接是结构化字段，E 不需要拆字符串 ——
       上一版那个 buildEquation 就是在这里被删掉的。 */
  function layerCalc(r, ui, fmt, data) {
    var L = layer(ui, "2", "计算与判断", "is-fact");
    var calcSteps = stepsOf(r, "计算");
    var judgeSteps = stepsOf(r, "判断");

    if (!calcSteps.length && !judgeSteps.length) {
      L.content.appendChild(ui.note(
        "证据链里没有「计算」与「判断」步骤 —— 只能看到结论，看不到复核路径。",
        "warn"));
      return L.root;
    }

    var box = ui.el("div", "calc-box");

    calcSteps.forEach(function (c) {
      if (c.formula) box.appendChild(ui.el("div", "calc-formula", c.formula));

      var vals = c.values && typeof c.values === "object" ? Object.keys(c.values) : [];
      if (vals.length) {
        var line = ui.el("div", "calc-eq");
        line.appendChild(ui.el("span", "ce-term", vals.map(function (k) {
          return data.metricLabel(k) + " " + data.riskValue(k, c.values[k], "小数");
        }).join("　")));
        box.appendChild(line);
      }
    });

    judgeSteps.forEach(function (j) {
      var meta = ui.el("div", "calc-meta");
      meta.appendChild(ui.el("span", "calc-threshold", fmt.text(j.item)));
      if (!fmt.isNil(j.result)) {
        meta.appendChild(ui.el("span",
          "calc-flag " + (j.result === "触发" ? "is-triggered" : "is-quiet"),
          j.result));
      }
      box.appendChild(meta);
    });

    L.content.appendChild(box);
    return L.root;
  }

  /* ---- ③ 归因：这一层是 D 白送的 ----
     杜邦三因子拆解 + 现金流桥。D 在每条风险的证据链里都带了一个「归因」步，
     说明「这个数字变动是由什么驱动的」。上一版没有这一层（B 没给），
     所以本层整块是新增的 —— 它也是这一页现在最有分量的一段：
     它把「收入下滑」从一句话变成三个可核对的因子。 */
  function layerAttribution(r, ui, fmt, data) {
    var steps = stepsOf(r, "归因");
    if (!steps.length) return null;

    var L = layer(ui, "3", "变动归因", "is-fact");
    var any = false;

    steps.forEach(function (s) {
      var dup = s.dupont;
      if (dup && typeof dup === "object") {
        var dk = Object.keys(dup).filter(function (k) { return dup[k] !== null; });
        if (dk.length) {
          any = true;
          var DUP_LABEL = {
            net_margin_effect:      "净利率变动影响",
            asset_turnover_effect:  "资产周转变动影响",
            leverage_effect:        "权益乘数变动影响",
            roe_delta:              "ROE 合计变动"
          };
          var tb = ui.el("table", "mini-table");
          var h = ui.el("thead"), hrow = ui.el("tr");
          ["杜邦拆解", "影响（百分点）"].forEach(function (x) {
            hrow.appendChild(ui.el("th", null, x));
          });
          h.appendChild(hrow); tb.appendChild(h);
          var tbody = ui.el("tbody");
          dk.forEach(function (k) {
            var tr = ui.el("tr");
            tr.appendChild(ui.el("td", "strong", DUP_LABEL[k] || k));
            tr.appendChild(ui.el("td", "metric-value", fmt.signedPercent(dup[k])));
            tbody.appendChild(tr);
          });
          tb.appendChild(tbody);
          L.content.appendChild(tb);
        }
      }

      var items = s.cash_flow_bridge_items_yi;
      if (Array.isArray(items) && items.length) {
        var live = items.filter(function (x) { return x && x.amount_yi !== null; });
        if (live.length) {
          any = true;
          L.content.appendChild(ui.el("div", "block-sub", "经营现金流桥（亿元）"));
          var tb2 = ui.el("table", "mini-table");
          var t2 = ui.el("tbody");
          live.forEach(function (x) {
            var tr = ui.el("tr");
            tr.appendChild(ui.el("td", "strong", fmt.text(x.item)));
            tr.appendChild(ui.el("td", "metric-value", fmt.signed(x.amount_yi, 2)));
            if (/倒轧|其他/.test(String(x.item))) tr.classList.add("is-gap");
            t2.appendChild(tr);
          });
          if (s.cash_gap_yi !== null && s.cash_gap_yi !== undefined) {
            var trg = ui.el("tr");
            trg.appendChild(ui.el("td", "strong", "现金缺口"));
            trg.appendChild(ui.el("td", "metric-value", fmt.signed(s.cash_gap_yi, 2)));
            t2.appendChild(trg);
          }
          tb2.appendChild(t2);
          L.content.appendChild(tb2);
        }
      }
    });

    if (!any) return null;
    if (steps[0].unit_note) {
      L.content.appendChild(ui.el("div", "detail-line dim", steps[0].unit_note));
    }
    return L.root;
  }

  /* ---- ④ 解释与建议 ----
     版式上有主次：解释是背景说明（中性底、小字），建议是行动项（强调底、大字）。
     演示时被记住的应该是「要做什么」，不是「这是什么意思」。 */
  function layerExplain(r, ui, fmt) {
    var L = layer(ui, "4", "解释与建议", "is-conclusion");

    if (r.explanation) {
      L.content.appendChild(ui.el("p", "risk-explain", r.explanation));
    } else {
      L.content.appendChild(ui.note(
        "未提供 explanation 字段 —— 此层无法渲染。", "warn"));
    }

    /* 建议直接取 D 的 suggested_action 整段。
       ★ 证据链的「建议」步里另有一个 actions 数组（拆成三条），
         但那一份是**同一段话的切分版**（D 用它自己把三条用「；」连起来
         写成 suggested_action）。E 拿哪一份都行，取整段是因为
         **不必由 E 决定这几条之间是什么关系**（并列？递进？先后？）——
         D 连好的那一份已经把关系写在标点里了。
       两处都没有时才降级为提示。 */
    var text = !fmt.isNil(r.suggested_action) ? String(r.suggested_action) : null;
    if (!text) {
      var acts = [];
      stepsOf(r, "建议").forEach(function (s) {
        if (Array.isArray(s.actions)) {
          s.actions.forEach(function (a) { if (!fmt.isNil(a)) acts.push(String(a)); });
        }
      });
      if (acts.length) text = acts.join("；");
    }

    if (text) {
      var sug = ui.el("div", "risk-suggest");
      sug.appendChild(ui.el("div", "sug-tag", "应对建议"));
      sug.appendChild(ui.el("p", "sug-text", text));
      L.content.appendChild(sug);
    }
    return L.root;
  }
})();
