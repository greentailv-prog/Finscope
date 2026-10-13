/* ============================================================================
 * dataLoader.js —— 唯一的数据入口
 * ----------------------------------------------------------------------------
 * 全项目只有这一个文件碰原始数据。页面一律通过 FinScope.data.get() 取值，
 * 不许自己写 data.financials.revenue.value 这种长链，原因有二：
 *   1. 字段名变了只改这里，不用翻六个页面；
 *   2. 任何字段缺失都在这里被兜住，页面永远不会因为 undefined 崩掉。
 *
 * 职责：
 *   ① 接收 D 的统一数据对象（+ D 的投研简报绑定表 memo.json，页面 6 专用）；
 *   ② 校验结构，缺什么记进 warnings（页面可显示"数据未就绪"提示）；
 *   ③ 提供安全的取值接口 get(path, fallback)。
 *
 * ── 【2026-10-13 D 对齐】这一版按 D 的真实 Schema 改过，四类改动 ─────────
 *   A 改名   financials / ratios 的键名换成 D 的（见 FINANCIAL_LABELS、
 *            RATIO_META）。E 原来那套名字是照着 B 的旧口径猜的。
 *   B 领新   D 多给了 E 原来没读的东西：比值的 prev / delta / inputs /
 *            higher_is_better、valuation.blended / scenarios / sensitivity /
 *            warnings。
 *            ★ 财务项的 prior_value / prior_period 本来也在这个清单里，
 *            2026-10-13 起**已经用上了** —— 页面 2 财务数据表的「上期」列，
 *            打包成 finRow 的 r.prior（见 priorOf）。所以它从「领新」挪走了。
 *   C 撤块   **删掉了 businessMix() / history() / hasHistoryField()** ——
 *            A 的抽取结果顶层只有 company / financials / extraction_meta，
 *            这三样四个队友谁也不产出。不做无源之物。
 *            同理删掉整个公式代入层（CALC_INPUT_LABELS / buildEquation …）：
 *            D 的风险证据链给的是 evidence_chain[]（已分好「数据/计算/出处/
 *            判断/归因/建议」六种步骤），E 原来那套「拆 formula 字符串再配上
 *            inputs」的拼装把一个已经结构化的东西又拆回字符串，纯属绕路。
 *   D 真缺口 只剩偿债三项 + sources[].source_url，都登记在 js/contract.js 里。
 *
 *   ⚠️ 一句话记住新口径：**E 不做任何数值运算，只做单位换算与格式化。**
 *      单位换算（元 → 亿元）是显示刻度，与画柱状图要算坐标同类。
 * ==========================================================================*/

(function () {
  "use strict";

  window.FinScope = window.FinScope || {};

  var ctx = {
    raw: null,          // 原始数据对象（D 的 unified.json）
    memo: null,         // D 的投研简报绑定表（reports/<key>/memo.json），页面 6 用
    warnings: [],       // 结构校验发现的问题
    loaded: false,      // 是否已成功加载
    sourceName: "(未加载)"
  };

  /* --------------------------------------------------------------------------
     指标词汇表：D 的比值键名 → 中文名 + **显示口径**
     --------------------------------------------------------------------------
     ⚠️ 这张表现在**不是兜底，是唯一来源**。D 的比值项里没有 name 字段
        （字段只有 value / unit / period / formula / page / prev / delta /
        inputs / inputs_prev / status / higher_is_better），
        所以中文名只能由 E 给 —— 这是排版的一部分，不是数据。

     ⚠️ kind（显示口径）也是 E 的决定，但**有据可依**，不是猜的：
        D 的 unit 有四类（"小数" / "倍" / "次" / "天"），其中 "小数"
        是个**混装桶** —— gross_margin 0.9118 是「该显示成 91.18%」，
        equity_multiplier 1.242 是「本来就该显示成 1.242」。
        光看 unit 分不出来，所以逐条声明。
        依据是 D 自己 memo.json 里的写法（dashboard 表把毛利率写成
        "26.39%"、把总资产周转率写成 "0.75 次"、周转天数写成 "30.49 天"），
        E 跟着 D 的口径，不另立一套。

        kind 取值：
          "pct"      → 0.9118 显示成 "91.18%"（×100）
          "num"      → 1.242 原样显示（倍数类比率，不 ×100）
          "money"    → 单位归一到亿元
          "multiple" → 1.62 → "1.62 倍"
          "times"    → 3.32 → "3.32 次"
          "days"     → 30.49 → "30.49 天"

     ⚠️ D 新增指标时这里要补一行，否则页面会显示成英文键名 ——
        这是**唯一**一处「D 加了东西 E 必须跟着改」的地方，请留意。
     ------------------------------------------------------------------------*/
  var RATIO_META = {
    /* ---- 成长性（10）---- */
    revenue_growth_yoy:                       { label: "营业收入同比",            kind: "pct" },
    net_income_total_growth:                  { label: "净利润同比",              kind: "pct" },
    net_income_growth_yoy:                    { label: "归母净利润同比",          kind: "pct" },
    net_income_excl_nonrecurring_growth_yoy:  { label: "扣非归母净利润同比",      kind: "pct" },
    cost_of_revenue_growth:                   { label: "营业成本同比",            kind: "pct" },
    total_assets_growth:                      { label: "总资产同比",              kind: "pct" },
    equity_parent_growth:                     { label: "归母净资产同比",          kind: "pct" },
    ocf_growth:                               { label: "经营活动现金流同比",      kind: "pct" },
    profit_revenue_scissors:                  { label: "利润—收入剪刀差",         kind: "pct" },
    revenue_cagr_3y:                          { label: "营业收入 3 年复合增速",   kind: "pct" },

    /* ---- 盈利能力（18）---- */
    gross_margin:                             { label: "毛利率",                  kind: "pct" },
    net_margin_total:                         { label: "净利率",                  kind: "pct" },
    net_margin:                               { label: "归母净利率",              kind: "pct" },
    net_margin_deducted:                      { label: "扣非归母净利率",          kind: "pct" },
    operating_margin:                         { label: "营业利润率",              kind: "pct" },
    ebit_margin:                              { label: "EBIT 利润率",             kind: "pct" },
    ebitda_margin:                            { label: "EBITDA 利润率",           kind: "pct" },
    selling_expense_ratio:                    { label: "销售费用率",              kind: "pct" },
    admin_expense_ratio:                      { label: "管理费用率",              kind: "pct" },
    rd_expense_ratio:                         { label: "研发费用率",              kind: "pct" },
    finance_expense_ratio:                    { label: "财务费用率",              kind: "pct" },
    period_expense_ratio:                     { label: "期间费用率",              kind: "pct" },
    roe_weighted:                             { label: "加权 ROE",                kind: "pct" },
    roa:                                      { label: "总资产收益率 ROA",        kind: "pct" },
    roic:                                     { label: "投入资本回报率 ROIC",     kind: "pct" },
    effective_tax_rate:                       { label: "实际税率",                kind: "pct" },
    deducted_to_parent:                       { label: "扣非 / 归母净利润",       kind: "pct" },
    roic_minus_wacc:                          { label: "ROIC − WACC",             kind: "pct" },

    /* ---- 偿债能力（14）---- */
    /* ⚠️ 前四项是 D 说「该有的」，但目前 A 抽不到 → 状态是 not_evaluable。
           E 不补数、不算替代值，就显示「待核验」并标出缺的是哪个科目。 */
    current_ratio:                            { label: "流动比率",                kind: "num" },
    quick_ratio:                              { label: "速动比率",                kind: "num" },
    cash_ratio:                               { label: "现金比率",                kind: "num" },
    cash_to_short_term_debt:                  { label: "货币资金 / 短期债务",     kind: "num" },
    equity_multiplier:                        { label: "权益乘数",                kind: "num" },
    debt_to_asset_ratio:                      { label: "资产负债率",              kind: "pct" },
    interest_bearing_debt:                    { label: "有息负债",                kind: "money" },
    interest_bearing_debt_ratio:              { label: "有息负债率",              kind: "pct" },
    interest_bearing_debt_growth:             { label: "有息负债同比",            kind: "pct" },
    net_debt:                                 { label: "净负债",                  kind: "money" },
    working_capital:                          { label: "营运资本",                kind: "money" },
    interest_coverage:                        { label: "利息保障倍数",            kind: "multiple" },
    net_debt_to_ebitda:                       { label: "净负债 / EBITDA",         kind: "multiple" },
    restricted_cash_ratio:                    { label: "受限资金占比",            kind: "pct" },

    /* ---- 营运能力（12）---- */
    ar_turnover:                              { label: "应收账款周转率",          kind: "times" },
    inventory_turnover:                       { label: "存货周转率",              kind: "times" },
    ap_turnover:                              { label: "应付账款周转率",          kind: "times" },
    total_asset_turnover:                     { label: "总资产周转率",            kind: "times" },
    fixed_asset_turnover:                     { label: "固定资产周转率",          kind: "times" },
    ar_turnover_days:                         { label: "应收账款周转天数",        kind: "days" },
    inventory_turnover_days:                  { label: "存货周转天数",            kind: "days" },
    payable_turnover_days:                    { label: "应付账款周转天数",        kind: "days" },
    cash_conversion_cycle:                    { label: "现金转换周期",            kind: "days" },
    accounts_receivable_growth:               { label: "应收账款同比",            kind: "pct" },
    inventory_growth:                         { label: "存货同比",                kind: "pct" },
    ar_and_inventory_to_assets:               { label: "应收+存货 / 总资产",      kind: "pct" },

    /* ---- 现金流质量（14）---- */
    ocf:                                      { label: "经营活动现金流净额",      kind: "money" },
    cfo_to_net_income:                        { label: "净现比",                  kind: "pct" },
    cfo_to_net_income_total:                  { label: "净现比（含少数股东）",    kind: "pct" },
    ocf_to_revenue:                           { label: "经营现金流 / 营业收入",   kind: "pct" },
    cash_collection_ratio:                    { label: "销售收现比",              kind: "pct" },
    capex:                                    { label: "资本开支",                kind: "money" },
    capex_to_ocf:                             { label: "资本开支 / 经营现金流",   kind: "pct" },
    capex_to_da_ratio:                        { label: "资本开支 / 折旧摊销",     kind: "multiple" },
    free_cash_flow:                           { label: "自由现金流",              kind: "money" },
    fcf_to_revenue:                           { label: "自由现金流 / 营业收入",   kind: "pct" },
    ocf_to_interest_paid:                     { label: "经营现金流 / 利息支出",   kind: "multiple" },
    payout_ratio:                             { label: "分红率",                  kind: "pct" },
    cf_financing_dependency:                  { label: "筹资依赖度",              kind: "pct" },
    goodwill_to_equity:                       { label: "商誉 / 归母净资产",       kind: "pct" }
  };

  /* --------------------------------------------------------------------------
     ★★ 风险规则用的指标词汇表 —— **和 ratios 字典不是同一套键名** ★★
     --------------------------------------------------------------------------
     这是对齐 D 时踩出来的一个坑，写清楚免得下次再踩：

       ratios.growth.revenue_growth_yoy                ← ratios 字典的键
       risks[].involved_values[].metric = "revenue_growth"   ← 规则语言的键

     同一件事（营业收入同比）在两处叫两个名字。原因不难理解：ratios 是 B 算出来的
     指标台账，键名带口径后缀（_yoy / _weighted）；而风险规则写的是**触发条件**，
     用的是规则作者顺手起的短名。两边都不是错的，但 E 不能拿一张表去查两个地方。

     实测出现过的 5 个（600519 / 000333 两份数据的 risks 全集）：
       revenue_growth / net_income_parent_growth / roe_delta /
       ocf_to_net_income_parent / debt_to_assets
     ★ 这张表**只覆盖规则的取值**，不覆盖 ratios。页面 4 展示风险时查这里，
       页面 3 展示指标时查 RATIO_META —— 两条线不交叉。
     ★ 没登记的键一律原样显示英文（见 labelOfAny），不猜。
     ------------------------------------------------------------------------*/
  var RULE_META = {
    revenue_growth:           { label: "营业收入同比",                  kind: "pct" },
    net_income_parent_growth: { label: "归母净利润同比",                kind: "pct" },
    roe_delta:                { label: "ROE 变动",                      kind: "pct" },
    ocf_to_net_income_parent: { label: "净现比（经营现金流/归母净利润）", kind: "pct" },
    debt_to_assets:           { label: "资产负债率",                    kind: "pct" }
  };

  /* 解析指标中文名。词汇表里没有就原样返回英文键 ——
     **不猜**。显示成 net_margin_total 至少能让人一眼看出是 E 没登记，
     比默默编一个像模像样的中文名、事后没人发现要安全得多。 */
  function labelOf(key) {
    var m = RATIO_META[key];
    return m ? m.label : key;
  }

  /* 风险里出现的任意指标键 → 中文名。三张表依次查：
       RULE_META（规则语言）→ FINANCIAL_LABELS（财报科目）→ RATIO_META（指标台账）。
     顺序反过来的话，"ocf" 会先命中 RATIO_META 的「经营活动现金流净额」——
     其实两边名字一样，无所谓；但 "capex" 之类在两张表里都在，
     所以顺序只影响同义不同名的情况，这里按「风险场景优先」排。 */
  function labelOfAny(key) {
    if (RULE_META[key]) return RULE_META[key].label;
    if (FINANCIAL_LABELS[key]) return FINANCIAL_LABELS[key];
    if (RATIO_META[key]) return RATIO_META[key].label;
    return key;
  }

  /* 风险里的数值按它的口径渲染成文字。
     · unit 是 "元" / "万元" / "亿元" → money（归一后再显示）
     · unit 是 "%" / "倍" / "次" / "天" → 交给 fmt.metric 分派
     · unit 是 "小数"（混装桶）或没给 → 查 RULE_META / RATIO_META 的 kind；
       两张表都没有就**当裸数字显示**，不擅自 ×100（猜错会把 0.75 写成 75%） */
  function formatRiskValue(key, value, unit) {
    var f = FinScope.fmt;
    if (value === null || value === undefined) return f.MISSING;

    if (unit === "元" || unit === "万元" || unit === "亿元") {
      return f.money({ value: value, unit: unit });
    }
    if (unit && unit !== "小数") return f.metric({ value: value, unit: unit });

    var m = RULE_META[key] || RATIO_META[key];
    if (m && m.kind === "pct")      return f.percent({ value: value });
    if (m && m.kind === "money")    return f.money({ value: value, unit: "元" });
    if (m && m.kind === "multiple") return f.multiple({ value: value });
    if (m && m.kind === "times")    return f.times({ value: value });
    if (m && m.kind === "days")     return f.days({ value: value });
    return f.num({ value: value }, 4);
  }

  /* 按声明口径格式化一个比值项。
     - kind 缺失（词汇表没登记）→ 退回 fmt.metric() 按 unit 分派
     - 值是 null → 交给 fmt 返回破折号，页面据此不画条、不写数 */
  function formatRatio(key, item) {
    var f = FinScope.fmt;
    if (!item || typeof item !== "object") return f.MISSING;

    var m = RATIO_META[key];
    if (!m) return f.metric(item);

    switch (m.kind) {
      case "pct":      return f.percent({ value: item.value });
      case "money":    return f.money(item);
      case "multiple": return f.multiple({ value: item.value });
      case "times":    return f.times({ value: item.value });
      case "days":     return f.days({ value: item.value });
      default:         return f.num({ value: item.value }, 3);
    }
  }

  /* 对外的名字。format.js 的注释里把它写作 ratioValue()，
     含义是「按指标口径把一个比值项渲染成文字」—— 名字更贴近它做的事。 */
  function ratioValue(key, item) {
    return formatRatio(key, item);
  }

  /* 这个指标是不是「核心指标」（页面 3 的主行）。
     ★ 名单来自 js/contract.js 的 INDICATORS —— E 的消费端契约里那一份，
       不在这里另抄。D 的 ratios 一个维度有 10–18 项，全平铺等于没排；
       契约登记的 3–4 项是「读的人先要看的那几个」。
       contract.js 没加载（或该维度没登记）时一律返回 false ——
       于是页面 3 退化成「全部平铺」，是能用的，只是不如有主次。 */
  function isCoreRatio(groupKey, key) {
    var C = FinScope.contract;
    if (!C || !C.INDICATORS) return false;
    var list = C.INDICATORS[groupKey];
    return Array.isArray(list) && list.indexOf(key) >= 0;
  }

  /* 该维度的核心指标清单（按契约声明顺序）。契约里没登记这个维度 → null，
     调用方据此不排序，保持数据原序。 */
  function coreOrder(groupKey) {
    var C = FinScope.contract;
    if (!C || !C.INDICATORS) return null;
    var list = C.INDICATORS[groupKey];
    return Array.isArray(list) ? list : null;
  }

  /* --------------------------------------------------------------------------
     财报科目词汇表：字段名 → 中文名 + 归属报表 + 在报表里的层级
     --------------------------------------------------------------------------
     为什么要在前端排这个表：16 个科目平铺成一长串等于没排。
     三张报表各有自己的形状，压成同一个模板就会显得刻板 ——
       · 利润表是「收入 → 减成本费用 → 利润」的层级；
       · 资产负债表是「总资产（其中四个细项）／总负债／净资产」；
       · 现金流量表是三项净额的正负分流，资本开支是投资活动下的细项。
     所以这里除了分组，还要声明每行的 indent（缩进层级）与 op（前缀）。

     ⚠️ 严格区分两类字段：
       · key / label        —— 数据口径，随 D 的 Schema 变；
       · 分组 / indent / op / gap / headline —— **E 的呈现决定**，与数据口径无关。
     ⚠️ 这里只放「怎么显示」，不放任何数值。数值一律走 get("financials.xxx")。
     ------------------------------------------------------------------------*/
  var FINANCIAL_BOOK = [
    {
      label: "利润表", shape: "plain", headline: "net_income_parent",
      rows: [
        { key: "revenue" },
        { key: "operating_cost", indent: 1, op: "减：" },
        { key: "rnd_expense",    indent: 1, op: "减：" },
        /* gap：在这一行上面画一道分隔线。它不是算术等号 ——
           中间还隔着其他费用和税，本表列不全，所以**不能让人以为
           上面几行加起来就等于净利润**。分隔线只表示「以下是结论行」。

           D 多给了一个 net_income（净利润，含少数股东）。它和归母净利润
           是两个口径，本产品（以及 D 的简报、C 的估值）全程用归母，
           所以头条挂在归母上；净利润总额留着，因为下面两个「其中：」
           得有个被「其中」的父项，否而缩进是悬空的。 */
        { key: "net_income", gap: true },
        { key: "net_income_parent", indent: 1, op: "其中：" },
        { key: "net_income_excl_nonrecurring", indent: 1, op: "其中：" }
      ]
    },
    {
      label: "资产负债表", shape: "plain", headline: "total_assets",
      rows: [
        { key: "total_assets" },
        /* 「其中：」是报表里的标准写法，且这四个科目确实构成总资产 ——
           缩进表达的是构成关系，是真的，不是排版手感。 */
        { key: "cash_and_equivalents", indent: 1, op: "其中：" },
        { key: "accounts_receivable",  indent: 1 },
        { key: "inventory",            indent: 1 },
        { key: "goodwill",             indent: 1 },
        /* 总负债 / 归母净资产移到细项之后：放在中间会被读成「其中」的一部分。
           注意**不画「资产 = 负债 + 权益」的等号** —— 本表的归母净资产
           不含少数股东权益，真数据下这个等式不成立，画出来就是错的。 */
        { key: "total_liabilities", gap: true },
        { key: "equity_parent" }
      ]
    },
    {
      /* 三项现金流是**净额**，正负号表示流向，所以这一块用零点线分左右。
         资本开支是投资活动下的一个细项、且是流出额，与净额不是同一类数，
         所以放在分隔线之后、用普通幅度条，不参与左右分流。
         —— 因此它单独把 shape 覆写回 "plain"。**不翻符号**：
         真数据里 600519 的资本开支是 +31.3 亿，E 不许把它改成 -31.3
         来迁就图形，那是替 A 重算口径。形状服从数据，不是数据迁就形状。
         （2026-10-13 核实：D 交付的 9 家里资本开支全部为正，符号已一致。） */
      label: "现金流量表", shape: "diverging", headline: "cfo",
      rows: [
        { key: "cfo" },
        { key: "cfi" },
        { key: "cff" },
        { key: "capex", gap: true, shape: "plain" }
      ]
    }
  ];

  /* 科目键名 → 中文名。**键名以 D 的 Schema 为准**（对齐方案决定 #2：
     字段统一用 D 的，A/B/C 的名字映射过来）。
     与旧名的对应：cost_of_revenue→operating_cost、rd_expense→rnd_expense、
     net_income_attr→net_income_parent、net_income_deducted→
     net_income_excl_nonrecurring、equity_attr→equity_parent。 */
  var FINANCIAL_LABELS = {
    revenue:                      "营业收入",
    operating_cost:               "营业成本",
    rnd_expense:                  "研发费用",
    net_income:                   "净利润",
    net_income_parent:            "归母净利润",
    net_income_excl_nonrecurring: "扣非归母净利润",
    total_assets:                 "总资产",
    total_liabilities:            "总负债",
    equity_parent:                "归母净资产",
    cash_and_equivalents:         "货币资金",
    accounts_receivable:          "应收账款",
    inventory:                    "存货",
    goodwill:                     "商誉",
    cfo:                          "经营活动现金流净额",
    cfi:                          "投资活动现金流净额",
    cff:                          "筹资活动现金流净额",
    capex:                        "资本开支"
  };

  function finRow(spec, item) {
    return {
      key: spec.key,
      name: FINANCIAL_LABELS[spec.key] || spec.key,
      indent: spec.indent || 0,      // 0 / 1，页面 2 的缩进层级
      op: spec.op || null,           // 行前缀，如「减：」「其中：」
      gap: !!spec.gap,               // 本行之前画一道分隔线
      /* 逐行覆写所在块的形状。为空表示跟块走。
         用途只有一个：现金流量表里的资本开支（见上）。 */
      shape: spec.shape || null,
      /* 上期值。D 在每个财务科目上带了 prior_value / prior_period
         （如 revenue.prior_value = 170899152276.34, prior_period = "2024"）。
         ★ 这不是 E 算出来的同比，是 D 抽出来的上年同科目原值 ——
           页面 2 用它做「本期 / 上期」两列对照，**不显示增长率**：
           增长率的家在第 3 页的成长性维度，两处各算一次迟早对不上。
         单位为 null 表示 D 没给上期（新上市、科目首次出现等）。 */
      prior: priorOf(item),
      item: item
    };
  }

  /* 取上期值。D 给的是 prior_value + prior_period 两个平铺字段，
     这里打包成一个对象 —— 页面拿到的永远是「有或没有」，不用自己判两次。  */
  function priorOf(item) {
    if (!item || typeof item !== "object") return null;
    var v = item.prior_value;
    if (v === undefined || v === null) return null;
    return { value: v, period: item.prior_period || null, unit: item.unit };
  }

  /* 「这一格对这家公司不成立」—— D 在财务科目上用 status 表达这个意思：
     茅台的 goodwill 是 { value: null, status: "not_applicable", page: 57 }，
     也就是「年报的资产负债表上本来就没有『商誉』这一行」。
     这一类**不画进表**，而不是画一行破折号。

     ★ 判据必须是 status，**绝不能是 value === null**。两者差得很远：
       · status === "not_applicable"  → 这家公司没有这一项，不画；
       · value === null 且 status 不是 → **抽取失败**，照画一个灰破折号。
     按 value 判会把「上游没抽到」静默抹掉，那正是本页「数字必须可验证」
     这句话要防的事 —— 缺数据必须明说，不能不留白。
     这也是为什么这条判断写在这里（数据层、按 D 给的语义），
     而不是在页面里按科目名硬写一个「不画商誉」：换成一家真有商誉的公司
     （万华之类），硬写就会凭空少一行。 */
  function isNotApplicable(item) {
    return !!item && item.status === "not_applicable";
  }

  /* 按词汇表分组返回财报科目；**词汇表里没登记但数据里出现的科目兜进「其他」组**。
     宁可多显示一行，也不能因为前端没登记就把它静默藏起来 ——
     D 换了数据源、多抽了一个科目，前端不该假装它不存在。 */
  function financialGroups() {
    var fin = get("financials", {}) || {};
    var seen = {};
    var out = [];

    FINANCIAL_BOOK.forEach(function (g) {
      var items = [];
      g.rows.forEach(function (spec) {
        if (!Object.prototype.hasOwnProperty.call(fin, spec.key)) return;
        /* ★ 先登记 seen、再决定画不画。顺序不能反 ——
           反了的话，被跳过的科目会掉进下面的「其他」兜底组，
           以「词汇表没登记」的名义重新出现一次，等于没删。 */
        seen[spec.key] = true;
        if (isNotApplicable(fin[spec.key])) return;
        items.push(finRow(spec, fin[spec.key]));
      });
      if (!items.length) return;
      out.push({
        label: g.label,
        shape: g.shape || "plain",
        /* headline 指向该表的头条科目（页面上字号大一档的那一行）。
           头条科目缺数据时退回第一行，页面不该因此留一个空的大字位。 */
        headline: items.some(function (r) { return r.key === g.headline; })
                    ? g.headline : items[0].key,
        items: items
      });
    });

    /* 兜底组不参与报表结构：没有层级、没有头条，一律平铺。
       同样要滤掉 not_applicable —— 词汇表没登记不代表它就该出现。 */
    var extra = Object.keys(fin).filter(function (k) {
      return !seen[k] && !isNotApplicable(fin[k]);
    });
    if (extra.length) {
      out.push({
        label: "其他", shape: "plain", headline: extra[0],
        items: extra.map(function (k) { return finRow({ key: k }, fin[k]); })
      });
    }
    return out;
  }

  /* --------------------------------------------------------------------------
     【2026-10-13 已撤】主营构成 businessMix() 与多期趋势 history()
     --------------------------------------------------------------------------
     撤掉的理由：**没有源**。A 的抽取结果顶层只有
     company / financials / extraction_meta 三段，四个队友谁也不产出
     business_mix 或 history。E 原来按「A 以后会给」把这两块做完了、跑着 mock，
     但那是把不存在的接口当成既有接口在用 —— 演示时只能拿 mock 撑场面。
     按「A/B/C/D 没有的部分从 E 撤掉」处理，页面 2 相应改成用 D 真正给的东西
     （每个财务科目都带 prior_value / prior_period，见 financialGroups）。

     唯一值得回头追的一条：A 在每个抽取指标上确实带了一个 series 字段
     （含 3 年）。也就是说 history **是能低成本恢复的**，只差 D 把它透传出来。
     已记在 js/contract.js 文件末尾与 docs/INTERFACE_CONTRACT.md。
     ------------------------------------------------------------------------ */

  /* --------------------------------------------------------------------------
     【2026-10-13 已撤】公式代入层（CALC_INPUT_LABELS / buildEquation 一整套）
     --------------------------------------------------------------------------
     撤掉的理由：**D 已经把这活干完了，而且干得更好。**

     E 原来那套的做法是：B 给一个 formula 字符串 + 一个 inputs 对象，
     E 去拆字符串、按中文名反查每一侧对应哪个键、拼成「A 41.2% − B 18.4% = 22.8%」。
     难点全在「公式字符串和 inputs 对象的顺序不保证一致」，所以 E 写了
     一堆验证逻辑，拼不可靠就返回 null 让页面回落三行式 —— 很谨慎，但很绕。

     D 的 risks[].evidence_chain[] 直接给的就是**已经分好步骤的结构**：
       step: "数据" | "计算" | "出处" | "判断" | "归因" | "建议"
     每一步都自带字段（item / value / unit / formula / values / pages /
     result / severity / actions …），没有任何东西需要 E 再拆字符串。
     把一个结构化对象拆回字符串再拼回来，是纯粹的自找麻烦。

     页面 4 的「计算」层改为直接渲染 evidence_chain 里 step === "计算" 的那一步。
     ------------------------------------------------------------------------ */

  /* ------------------------------------------------------------------ */
  /* 安全取值                                                            */
  /* ------------------------------------------------------------------ */

  /**
   * 按路径取值，任何一层断掉都返回 fallback，不抛异常。
   *   FinScope.data.get("financials.revenue")
   *   FinScope.data.get("ratios.roe.value", null)
   */
  function get(path, fallback) {
    if (FinScope.fmt.isNil(path)) return fallback === undefined ? null : fallback;
    var node = ctx.raw;
    var keys = String(path).split(".");
    for (var i = 0; i < keys.length; i++) {
      if (node === null || node === undefined) return fallback === undefined ? null : fallback;
      node = node[keys[i]];
    }
    return node === undefined ? (fallback === undefined ? null : fallback) : node;
  }

  /* 取某个财务/指标数据项，顺带保证它是 {value,...} 结构 */
  function item(path) {
    var v = get(path, null);
    if (!v || typeof v !== "object") return null;
    return v;
  }

  /* 取某个单项数值（数据项里的 value） */
  function value(path, fallback) {
    var it = item(path);
    if (!it) return fallback === undefined ? null : fallback;
    var n = FinScope.fmt.toNum(it);
    return n === null ? (fallback === undefined ? null : fallback) : n;
  }

  /* ------------------------------------------------------------------ */
  /* 结构校验                                                            */
  /* ------------------------------------------------------------------ */

  /* 只有这六个是必须的。它们同时也是 D 的 Schema.json 里的顶层键
     （另有 D 自己加的 rules_evaluated，那是它的运行记录，E 只读不做校验门槛）。
     页面 6 的数据源不在这里 —— 它是另一份产物 memo.json，走 ctx.memo。 */
  var REQUIRED_TOP = ["company", "financials", "ratios", "risks", "valuation", "sources"];

  function warn(msg) {
    ctx.warnings.push(msg);
  }

  /* --------------------------------------------------------------------------
     契约驱动的走查（js/contract.js）
     --------------------------------------------------------------------------
     比下面那个浅检查准得多：浅检查只看得见「顶层少了哪个键」，
     看不见「17 个指标全缺 page」「risks 缺证据层」这类真缺口 ——
     而那恰恰是队友交付时最容易漏、E 最难自己发现的。

     ★ 一条关键取舍：**只报「缺口」，不报「欠账」。**
       lv = "open"（合同里挂着、现在肯定还没有）和 "opt"（纯加法字段）
       一律不进提醒条。理由是它们会长年不变 —— 进去就变成没人看的墙纸，
       反而把真正意外的缺口淹掉。这两类由页面内联提示和
       tools/interface-check.js 负责，那里才是看它们的地方。
     ------------------------------------------------------------------------*/
  function validateByContract(raw, memo) {
    var results = FinScope.contract.check(raw, memo);
    var groups = [];
    var byKey = {};

    function bucket(key, init) {
      if (!byKey[key]) { byKey[key] = init; groups.push(byKey[key]); }
      return byKey[key];
    }

    results.forEach(function (r) {
      var isBad = (r.status === "type" || r.status === "range");

      if (isBad) {
        /* 类型 / 范围不对是**脏数据**，不管它挂在哪一档都要报 */
        var g = bucket("!" + r.pageId, {
          pageTitle: r.pageTitle, who: r.spec.who, bad: [], labels: [], order: 0
        });
        g.bad.push(r);
        return;
      }

      if (r.spec.lv !== "core") return;          // 欠账与可选项不进条
      /* 这里只放行 miss / null 两档。**gated 也被这一行挡掉了**，是有意的：
         gated = 它依赖的那一段整块没交（比如 memo.json 没到场，页面 6 的
         22 条会一起变成 gated）。一份文件没交是**一件事**，不是 22 件事 ——
         页面 6 自己会显示整块空状态，提醒条不必数 22 遍。 */
      if (r.status !== "miss" && r.status !== "null") return;

      var g2 = bucket(r.pageId + "|" + r.spec.who, {
        pageTitle: r.pageTitle, who: r.spec.who, bad: [], labels: [], order: 1
      });
      /* 「营业成本」和「营业成本 的页码」是同一件事的两半，
         摘要里只留一条，否则「缺 4 项」会看着像「缺 8 项」。 */
      var lab = String(r.spec.label || r.spec.p).replace(/\s*的页码$/, "");
      if (g2.labels.indexOf(lab) < 0) g2.labels.push(lab);
    });

    /* 脏数据排最前 —— 它是唯一一类「页面会显示错东西」的问题，
       缺数据只是显示成空状态，脏数据是显示成假的。 */
    groups.sort(function (a, b) { return a.order - b.order; });

    groups.forEach(function (g) {
      if (g.bad.length) {
        g.bad.slice(0, 3).forEach(function (r) {
          warn("【" + g.pageTitle + "】" + r.spec.p + " 的值"
            + (r.status === "type" ? "类型不对" : "超出约定范围")
            + "（" + briefValue(r.sample) + "）· 找 " + r.spec.who);
        });
        if (g.bad.length > 3) {
          warn("【" + g.pageTitle + "】另有 " + (g.bad.length - 3) + " 处类型 / 范围问题，不逐条列出。");
        }
        return;
      }

      /* 三条以内全列出来；超过三条只列前三条并以省略号收尾 ——
         不要写「缺 5 项：a、b、c 等 5 项」，那个「等 5 项」和前面的
         「缺 5 项」是同一个数，读的人会以为一共有 10 项。 */
      var n = g.labels.length;
      var names = (n <= 3 ? g.labels : g.labels.slice(0, 3)).join("、") + (n > 3 ? " …" : "");
      warn("【" + g.pageTitle + "】缺 " + n + " 项：" + names + " · 找 " + g.who);
    });
  }

  /* 脏值摘要：截成一行，别让一个长对象把提醒条刷屏 */
  function briefValue(v) {
    var s;
    try { s = JSON.stringify(v); } catch (e) { s = String(v); }
    if (s === undefined) s = String(v);
    return s.length > 40 ? s.slice(0, 40) + "…" : s;
  }

  /* 兜底：js/contract.js 没加载时退回浅检查。
     保留它是为了让 dataLoader 单测能独立跑，**不是**说这层够用。 */
  function validateShallow(raw) {
    REQUIRED_TOP.forEach(function (k) {
      if (raw[k] === undefined || raw[k] === null) {
        warn("缺少顶层字段：" + k + "（对应模块将显示为空状态）");
      }
    });

    if (raw.risks !== undefined && !Array.isArray(raw.risks)) {
      warn("risks 应为数组，实际为 " + typeof raw.risks + "，已按空数组处理。");
    }

    if (raw.sources !== undefined && !Array.isArray(raw.sources)) {
      warn("sources 应为数组，实际为 " + typeof raw.sources + "，已按空数组处理。");
    }

    // 财务数据项逐个检查 value 是否存在
    var fin = raw.financials;
    if (fin && typeof fin === "object") {
      Object.keys(fin).forEach(function (k) {
        var it = fin[k];
        if (it === null || it === undefined) {
          warn("财务字段缺失：" + k);
        } else if (typeof it === "object" && FinScope.fmt.isNil(it.value)) {
          warn("财务字段无值：" + k);
        }
      });
    }
  }

  function validate(raw, memo) {
    ctx.warnings = [];

    if (!raw || typeof raw !== "object") {
      warn("数据结构无效：根对象不存在或不是对象。");
      return false;
    }

    if (FinScope.contract && typeof FinScope.contract.check === "function") {
      validateByContract(raw, memo);
    } else {
      validateShallow(raw);
    }

    return true;
  }

  /* ------------------------------------------------------------------ */
  /* 归一化：把不规范的输入削成前端能安全消费的形状                        */
  /* ------------------------------------------------------------------ */

  function normalize(raw) {
    var out = raw || {};
    out.company = out.company || {};
    out.financials = out.financials || {};
    out.ratios = out.ratios || {};
    out.valuation = out.valuation || {};
    if (!Array.isArray(out.risks)) out.risks = [];
    if (!Array.isArray(out.sources)) out.sources = [];

    // 指标分组保证存在，避免页面里到处写 if
    ["growth", "profitability", "solvency", "efficiency", "cashflow_quality"]
      .forEach(function (g) {
        if (!out.ratios[g] || typeof out.ratios[g] !== "object") out.ratios[g] = {};
      });

    return out;
  }

  /* ------------------------------------------------------------------ */
  /* 加载                                                                */
  /* ------------------------------------------------------------------ */

  /**
   * 加载数据。不传参则读取 window.FINSCOPE_DATA（由 data/*.js 赋值）。
   *   load()                          统一对象 + window.FINSCOPE_MEMO
   *   load(raw)                       只给统一对象，页面 6 记「未提供」
   *   load(raw, memo)                 两份都给（tools 与测试用）
   * 返回值：是否加载成功（**只看统一对象**；memo 缺不算加载失败，
   *        只是页面 6 退化成空状态 —— 它本来就是另一份产物）。
   */
  function load(source, memoSource) {
    var raw = source;

    if (!raw) {
      raw = window.FINSCOPE_DATA;
      ctx.sourceName = (window.FINSCOPE_DATA_SOURCE || "window.FINSCOPE_DATA");
    } else {
      ctx.sourceName = "(传入对象)";
    }

    /* memo 与统一对象**独立**：谁先到都能用。
       不传就退回 window.FINSCOPE_MEMO（由 data/memo_*.js 赋值）。 */
    ctx.memo = (memoSource !== undefined) ? memoSource : (window.FINSCOPE_MEMO || null);

    if (!raw) {
      ctx.raw = null;
      ctx.loaded = false;
      ctx.warnings = ["未找到数据源。请确认 index.html 里引入了 data/real_data.js"
                    + "（该文件由 tools/build-data.js 从 D 的交付物生成）。"];
      return false;
    }

    var ok = validate(raw, ctx.memo);
    ctx.raw = normalize(raw);
    ctx.loaded = ok;

    if (ok && ctx.warnings.length) {
      console.warn("[FinScope] 数据校验提醒：\n- " + ctx.warnings.join("\n- "));
    }
    return ctx.loaded;
  }

  /* ------------------------------------------------------------------ */
  /* 便捷访问器：六个页面共用                                            */
  /* ------------------------------------------------------------------ */

  var api = {

    load: load,
    get: get,
    item: item,
    value: value,

    /* 当前数据状态（调试用） */
    status: function () {
      return {
        loaded: ctx.loaded,
        sourceName: ctx.sourceName,
        warnings: ctx.warnings.slice()
      };
    },

    /**
     * 契约体检结果 —— 与 tools/interface-check.js 是同一份契约走出来的。
     * 提醒条只报「缺口」（意外），这里连「欠账」一起给：
     * 页面 1 的骨架自检卡用它显示「还有多少项在等队友」。
     * 返回 null 表示 contract.js 没加载。
     */
    contractStatus: function () {
      if (!FinScope.contract || !ctx.raw) return null;
      var results = FinScope.contract.check(ctx.raw, ctx.memo);
      var pages = FinScope.contract.summarize(results);
      var totals = { core: 0, open: 0, opt: 0, problems: 0, renderable: 0, gated: 0 };
      pages.forEach(function (p) {
        totals.core += p.core;
        totals.open += p.open;
        totals.opt += p.opt;
        totals.gated += p.gated || 0;
        totals.problems += p.problems.length;
        /* 「可完整渲染」的判据只看 core 与脏数据。
           gated（整块没交）不算 —— 页面会显示成空状态，本身是诚实的。 */
        if (p.core === 0 && !p.problems.length) totals.renderable++;
      });
      totals.pages = pages.length;
      return { totals: totals, pages: pages, byOwner: FinScope.contract.byOwner(results) };
    },

    /* 风险按严重度排序：high → medium → low。
       D 用 high / medium / low，早期契约用 high / attention / normal，两套都认。 */
    sortedRisks: function () {
      var order = { high: 0, medium: 1, attention: 1, low: 2, normal: 2 };

      /* 注意：这里不能用 order[s] || 9 —— high 的优先级是 0，是 falsy，
         会被兜底成 9 排到最后。必须显式判断键是否存在。 */
      function rank(s) {
        return Object.prototype.hasOwnProperty.call(order, s) ? order[s] : 9;
      }

      return (get("risks", []) || []).slice().sort(function (a, b) {
        return rank(a.severity) - rank(b.severity);
      });
    },

    /* 指标分组清单，供给页面3遍历渲染。
       ------------------------------------------------------------------
       五个固定维度 + **数据里出现的其他分组**（D 有个 ratios.banking，
       银行专用指标，目前是空的）。兜底那一条的道理和 financialGroups 的
       「其他」组一样：D 加了新维度，前端不该假装它不存在。
       空分组不返回 —— 空块是噪声，不是内容。 */
    ratioGroups: function () {
      var fixed = [
        { key: "growth",           label: "成长性" },
        { key: "profitability",    label: "盈利能力" },
        { key: "solvency",         label: "偿债能力" },
        { key: "efficiency",       label: "营运能力" },
        { key: "cashflow_quality", label: "现金流质量" }
      ];
      var out = [];
      var seen = {};

      fixed.forEach(function (g) {
        seen[g.key] = true;
        /* ★ 必须写 api.ratioItems —— ratioItems 是 api 的属性，
           不是函数声明，没有提升。写成裸名就是在 api 还没赋完值的时候
           去找一个全局的 ratioItems，一定 ReferenceError。 */
        if (api.ratioItems(g.key).length) out.push(g);
      });

      var all = get("ratios", {}) || {};
      Object.keys(all).forEach(function (k) {
        if (seen[k]) return;
        if (!all[k] || typeof all[k] !== "object") return;
        if (!api.ratioItems(k).length) return;
        out.push({ key: k, label: k });              // 未登记的分组，显示英文键名
      });

      return out;
    },

    /* 取某分组下所有指标项，自动跳过 _score 等元字段（D 已经不产出了，
       这个 guard 留给 mock 数据）。
       每项带 label（中文名）、text（按声明口径格式化好的值）、以及
       status / quiet / page / formula 等页面直接要用的字段。
       **页面不要自己去 fmt 这个值** —— 单位口径（该不该 ×100）只有这里知道。

       ★ 顺序：**核心指标排在前面**，其余保持数据里的原序跟在后面。
         D 一个维度有 10–18 项（ratioItems 全给），页面 3 靠 isCore 决定
         谁常显、谁折进「其余 N 项」。排序放在这里而不是页面里 ——
         排序规则是契约的一部分（INDICATORS 的顺序就是「先看哪个」的顺序），
         页面只负责画。 */
    ratioItems: function (groupKey) {
      var g = get("ratios." + groupKey, {}) || {};
      var out = [];
      Object.keys(g).forEach(function (k) {
        if (k.charAt(0) === "_") return;             // 跳过 _score 等元字段
        var it = g[k];
        if (!it || typeof it !== "object") return;

        var f = FinScope.fmt;
        var st = it.status === undefined ? null : it.status;
        out.push({
          key: k,
          item: it,
          label: labelOf(k),
          text: formatRatio(k, it),
          registered: !!RATIO_META[k],               // false = 词汇表没登记，中文名是英文键
          status: st,
          quiet: f.statusQuiet(st),                  // true = 不值得挂状态胶囊
          page: (it.page === undefined ? null : it.page),
          formula: (typeof it.formula === "string" && it.formula) ? it.formula : null,
          isCore: isCoreRatio(groupKey, k)
        });
      });

      var seq = coreOrder(groupKey);
      if (seq) {
        out.sort(function (a, b) {
          var ia = seq.indexOf(a.key), ib = seq.indexOf(b.key);
          if (ia < 0) ia = seq.length;               // 没登记的排在登记项之后
          if (ib < 0) ib = seq.length;
          return ia - ib;
        });
      }
      return out;
    },

    /* 只取 E 的契约登记为「核心」的那几项，供给页面 3 的主行。
       ★ 名单不在这里另写一份 —— 直接读 js/contract.js 的 INDICATORS，
         一份契约两个消费者（运行时校验 + 页面排序），改了不会两边不一致。 */
    ratioCore: function (groupKey) {
      return api.ratioItems(groupKey).filter(function (x) { return x.isCore; });
    },

    /* 指标字段名 → 中文显示名 */
    ratioLabel: function (key) {
      return labelOf(key);
    },

    /* 按指标声明口径把比值项渲染成文字。("roe_weighted", {value:0.3446,…})
       → "34.5%"。★ 页面拿到比率项后**必须走这个函数**，不要用 fmt.metric ——
       D 的 unit "小数" 是个混装桶，fmt.metric 分不出该不该 ×100，
       会把 34.5% 显示成 "0.345"。 */
    ratioValue: function (key, item) {
      return ratioValue(key, item);
    },

    /* 风险里出现的指标键 → 中文名。查三张表（规则语言 / 财报科目 / 指标台账），
       都没有就原样返回英文键。页面 4 用。 */
    metricLabel: function (key) {
      return labelOfAny(key);
    },

    /* 风险里的数值 → 显示文字。页面 4 用。
       与 ratioValue 的区别：这里的"指标"可能是财报科目、可能是规则短名、
       也可能两者都不是，所以它先认 unit，unit 不可判时才查表。 */
    riskValue: function (key, value, unit) {
      return formatRiskValue(key, value, unit);
    },

    /* 财报科目按报表分组，供给页面2 的「主要财务数据」表。
       返回 [{ label:"利润表", items:[{key,name,item,prior,...}] }]，空分组不返回。
       每项带 prior：{ value, period } —— D 在每个财务项上给了上期值与上期期间，
       页面 2 因此能做「本期 / 上期」对照，不需要 history 字段。 */
    financialGroups: function () {
      return financialGroups();
    },

    /* 风险概览计数，供给页面 4 顶部概览条。
       认不出的 severity 归入 low —— 不猜、也不丢，条数永远对得上。
       ⚠️ 这里数的是 D 的 risks[]，它**已经被 D 按 status == "triggered"
          过滤过**，所以「未触发」那些不在此列。
          「一共检查了几条、触发了几条」由 rules_evaluated 回答，
          页面 4 从 rulesSummary() 取。 */
    riskSummary: function () {
      var list = get("risks", []) || [];
      var out = { total: list.length, high: 0, medium: 0, low: 0 };
      list.forEach(function (r) {
        if (r.severity === "high") out.high++;
        else if (r.severity === "medium" || r.severity === "attention") out.medium++;
        else out.low++;
      });
      return out;
    },

    /* 规则扫描的账：D 一共评估了几条规则、其中几条通过、几条无法判定。
       供给页面 4 顶部那句「已检查 N 条规则，触发 M 条」——
       没有这句话，「只有 2 条风险」会被读成「这家公司只有 2 个问题」，
       而实际上是「扫了 20 条，命中 2 条」。这是完全不同的两句话。
       返回 null 表示 D 没给 rules_evaluated。 */
    rulesSummary: function () {
      var list = get("rules_evaluated", null);
      if (!Array.isArray(list)) return null;
      var out = { total: list.length, triggered: 0, passed: 0, other: 0 };
      list.forEach(function (r) {
        var s = r && r.status;
        if (s === "triggered") out.triggered++;
        else if (s === "passed") out.passed++;
        else out.other++;
      });
      return out;
    },

    /* ------------------------------------------------------------------ */
    /* 页面 6 专用：D 的投研简报绑定表（memo.json）                        */
    /* ------------------------------------------------------------------ */
    /* memo 不是「报告正文」，是占位符 → 值的绑定表，结构见 js/contract.js
       的「关于页面 6」一节。三件事：
         · 每个值都已经由 D 格式化好了（"4,564.52 亿元"）——
           页面 6 是**唯一一页 E 不做数字格式化**的页面，直接用 formatted。
         · memo 与统一对象是**两份独立产物**，任一不到场另一份照常用。
         · E 不撰写报告内容 —— 页面 6 只搬 D 的字符串，不自己连句。 */

    /* memo 是否到场 */
    hasMemo: function () { return !!ctx.memo; },

    memoMeta: function () {
      return (ctx.memo && ctx.memo.meta) || null;
    },

    /* 七个章节标题，D 的 columns[] 原样返回 */
    memoColumns: function () {
      var c = ctx.memo && ctx.memo.columns;
      return Array.isArray(c) ? c.slice() : [];
    },

    /* 标量绑定表 → { placeholder: { formatted, source_path, raw_value } }。
       D 的 scalars[] 里同名 placeholder 会出现多次（如 blended_ps 在
       「⑤ 预测与估值」和抬头各绑一次），**取第一条**——
       它们的 formatted 是同一次渲染的产物，值必然相同。 */
    memoScalars: function () {
      var out = {};
      var list = (ctx.memo && ctx.memo.scalars) || [];
      if (!Array.isArray(list)) return out;
      list.forEach(function (s) {
        if (!s || typeof s !== "object" || !s.placeholder) return;
        if (out[s.placeholder]) return;
        out[s.placeholder] = s;
      });
      return out;
    },

    /* 单个标量的显示值，直出 D 的 formatted。没绑到就返回 null，
       页面据此决定这一格是「不显示」还是「显示占位」。 */
    memoValue: function (placeholder) {
      var s = api.memoScalars()[placeholder];
      return s ? s.formatted : null;
    },

    /* 具名列表 → { name: items[] } */
    memoCollections: function () {
      var out = {};
      var list = (ctx.memo && ctx.memo.collections) || [];
      if (!Array.isArray(list)) return out;
      list.forEach(function (c) {
        if (!c || typeof c.name !== "string") return;
        out[c.name] = Array.isArray(c.items) ? c.items : [];
      });
      return out;
    },

    memoCollection: function (name) {
      var items = api.memoCollections()[name];
      return items || [];
    },

    /* 一行 memo 表格的单元格取值：{ col: {formatted} } → { col: "文字" }。
       空单元格统一成 null（而不是空串），页面才好判断要不要留空格。 */
    memoRow: function (row, cols) {
      var out = {};
      cols.forEach(function (c) {
        var cell = row && row[c];
        var v = cell && typeof cell === "object" ? cell.formatted : cell;
        out[c] = (v === undefined || v === null || v === "") ? null : String(v);
      });
      return out;
    },

    /* D 自己的合规闸门结果。页面 6 把它顶在报告最上面 ——
       「这份简报可信吗」得先回答，再让人读内容。 */
    memoValidation: function () {
      if (!ctx.memo) return null;
      var v = ctx.memo.validation || null;
      var hits = (ctx.memo.compliance && ctx.memo.compliance.hits) || [];
      if (!v && !hits.length) return null;
      var violations = (v && Array.isArray(v.violations)) ? v.violations : [];
      return {
        passed: v ? v.passed !== false : null,
        allowedCount: v ? v.allowed_count : null,
        scannedTokens: v ? v.scanned_tokens : null,
        violations: violations,
        hits: Array.isArray(hits) ? hits : []
      };
    },

    /**
     * 按页码反查 sources[] 里的来源条目，拿到文件名 / 期间 / 取数时间。
     *
     * ★ 2026-10-13 改：**不再按指标名匹配**。
     *   D 的 sources[] 结构是
     *     { company_name, report_period, file_name, page, retrieved_at, source_url }
     *   —— 里面**没有 metric 字段**。E 原来按「指标名 + 页码」双键匹配，
     *   指标名那一半永远匹配不上，等于白写。现在只按页码，多命中取第一条。
     *   都中不了返回 null，页面据此显示灰色破折号（**不编一个链接出来**）。
     */
    findSource: function (metric, page) {
      var list = get("sources", []) || [];
      var hasPage = page !== null && page !== undefined;
      if (!hasPage) return null;

      for (var i = 0; i < list.length; i++) {
        if (list[i] && list[i].page === page) return list[i];
      }
      return null;

      /* metric 参数留着不删：调用点还照着老签名传，删了参数等于把
         一个静默的接口变更埋进页面里。哪天页面全改完可以再收。 */
    }
  };

  FinScope.data = api;
})();
