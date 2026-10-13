/* ============================================================================
 * contract.js —— E 的消费契约：E 会去读哪些路径、读不到时页面怎样、该找谁要
 * ----------------------------------------------------------------------------
 * ⚠️ **这不是 Schema，不要把它当 Schema 用。**
 *
 *   · D 的 `Schema.json` 是**生产端契约** —— 规定字段该叫什么、什么类型、
 *     缺值怎么表示。那是 D 的活。
 *   · 本文件是**消费端契约** —— 规定 E 实际会去读哪些路径、
 *     每条路径读不到时对应页面会退化成什么、以及这条路径该找谁要。
 *
 *   两份东西的关系是**互相校验**：对不上就是接口有缺口。
 *   本文件的全部价值就在于把这个缺口**量出来**。
 *
 * 两个消费者，一份定义（改一处，两边同时跟上）：
 *   ① `js/dataLoader.js` 的 validate()  —— 运行时，把缺口写进「数据校验提醒」条；
 *   ② `tools/interface-check.js`        —— 离线，给任意候选数据出体检报告。
 *
 * ============================================================================
 * ★★★ 2026-10-13 大改：从「E 自己猜的名字」改成「D 的 Schema 的镜像」★★★
 * ----------------------------------------------------------------------------
 * 本文件第一版写于 D 的 Schema 还不存在的时候 —— 那些字段名是**照着 E 的页面
 * 代码反推**出来的猜想。现在 D 交了 `output/Schema.json`（生产端契约）并把
 * 管线跑通、出了真数据，D 的对齐方案第 2 条定案是：
 *
 *     「字段统一用我的」—— 字段名以 D 的 Schema 为准，A/B/C 的名字映射过来。
 *
 * 所以本文件跟着改名，**方向是 E 服从 D**。理由：D 的 Schema 是内部自洽的，
 * 适配层已按它建成并验证过；E 的名字只是猜想，没有对抗的价值。
 * （另一条路是让 D 再加一层「E 视图」适配器 —— 那是第二个映射层，迟早腐烂。）
 *
 * 这次的改动有四类，性质完全不同，**看体检报告时要分开读**：
 *   A 改名      —— 纯换名，改一处全解决
 *   B 领新字段  —— D 给了更好的东西而 E 原来没读（净损失，不是缺口）
 *   C 撤块      —— D/A/B/C 四家都不产出的，E 撤掉，不做无源之物
 *   D 真缺口    —— 确实没人给，退回队友（见文件末尾「已撤与待补」一节）
 *
 * ---------------------------------------------------------------------------
 * 路径语法：  a.b[].c
 *   `[]` 表示「对数组里的每个元素」。嵌套可以有多层。
 *
 * 每个条目的字段：
 *   p      路径
 *   root   数据根，缺省 = 统一对象（D 的 unified.json）。
 *          "memo" = D 的投研简报绑定表（out_data/reports/<key>/memo.json）。
 *          页面 6 是唯一读 memo 的一页 —— 见文件末尾「关于页面 6」。
 *   lv     缺失后果，三档：
 *            "core" —— 缺了对应页面功能不成立（该页退化到空状态）
 *            "opt"  —— 缺了就少一块，页面照常成立（纯加法字段）
 *            "open" —— 已在合同里挂账、现在肯定还没有。**不算扣分**，
 *                      单独列出只是为了「别忘了他」
 *
 *          ⚠️ 用 "open" 有**一个附带义务**：这一条必须在**页面内**显式说明，
 *             因为提醒条对它保持沉默（见 dataLoader 的 validateByContract）。
 *             目前 open 项各自的着落：
 *               · ratios.solvency.{current_ratio,quick_ratio,interest_coverage}
 *                 —— 页面 3 偿付能力块逐行写「待 A 扩抽」
 *               · ratios.<g>.<k>.page —— 页面 3 指标名下写「还差 N 项」
 *               · report 结构说明 —— 页面 6 见下
 *             将来新增 open 项，先确认页面会说一句话，再加进来。
 *
 *          ★ 判据：「**长年不变**的缺，用 open；**意外**的缺，用 core。」
 *            core 进提醒条，open 不进。提醒条里出现的东西必须是「咦，这个怎么没了」，
 *            不能是天天都在的墙纸 —— 墙纸会把真缺口一起淹掉。
 *   who    谁欠着：A / B / C / D
 *   label  人话名字，出现在提醒条和体检报告里
 *   gate   上游闸门：闸门没提供时，本条目记为「整块未提供」，
 *          不计入缺口（否则一个块一缺就连报 N 条子路径）
 *   t      期望类型（可选）：num / str / arr / obj
 *   range  数值范围（可选）：[min, max]，用小数口径
 *
 * 每条路径走查后落一个 status，共七种：
 *   ok / miss / null / empty / type / range / gated ——
 *   再加一种由**祖先对象**的 status 派生的：
 *   "na"  「不适用」—— 祖先对象上写着 status: "not_applicable"，
 *         意思是「这一项对这家公司不成立」（茅台的商誉就是这样）。
 *
 *   ⚠️ **na 不是缺口**，这是它唯一要紧的地方：它不进提醒条、不进欠账清单、
 *      不影响「可否完整渲染」。理由是名单上挂着「缺商誉 · 找 A」，
 *      而 A 那边根本没有这个数可抽 —— **一条指错的欠账比没有欠账更坏**。
 *      派生规则见 check() 的第三遍，与 dataLoader 的 isNotApplicable 成对。
 * ==========================================================================*/

(function () {
  "use strict";

  window.FinScope = window.FinScope || {};

  /* --------------------------------------------------------------------------
     页面 3 的五个维度 × 指标清单
     --------------------------------------------------------------------------
     ⚠️ 这张表与 dataLoader.js 的 RATIO_LABELS 是**同一批指标的两种切法**：
        RATIO_LABELS 切的是「键 → 中文名」，这里切的是「组 → 有哪些键」。
        两者必须一一对应，**谁多一个键就是漏登记**。
        tests/data.test.js 有一条断言专门钉这件事，别手工保持同步。

     指标名已全部改成 **D 的 ratio 键名**（对齐方案 3.1 的映射表）。
     英文键在体检报告里会露出，所以落点处一律走 RATIO_LABELS 翻中文。
     ------------------------------------------------------------------------*/
  var INDICATORS = {
    growth:           ["revenue_growth_yoy", "net_income_growth_yoy",
                       "net_income_excl_nonrecurring_growth_yoy"],
    profitability:    ["gross_margin", "net_margin", "roe_weighted", "roa"],
    /* ⚠️ 偿付能力这一组，真数据里**只有 debt_to_asset_ratio 有值** ——
       current_ratio / quick_ratio 要 current_assets 与 current_liabilities，
       interest_coverage 要 interest_expense 与 operating_profit，
       四项输入全在 A 待扩抽的那 25 个科目里（对齐方案 5.1 / 5.2）。
       所以前三条在下面登记为 open（欠账），不进提醒条；
       页面 3 的偿付能力块逐行写「待 A 扩抽」，见 p3-diagnosis.js。
       A 补完之后把这三条从 open 改成 core 即可。 */
    solvency:         ["current_ratio", "quick_ratio", "debt_to_asset_ratio", "interest_coverage"],
    efficiency:       ["ar_turnover", "inventory_turnover", "total_asset_turnover"],
    cashflow_quality: ["cfo_to_net_income", "ocf_to_revenue", "free_cash_flow"]
  };

  /* 这三条是「等 A 扩抽」的欠账，不进提醒条（见上面 ⚠️） */
  var SOLVENCY_ARREARS = { current_ratio: 1, quick_ratio: 1, interest_coverage: 1 };

  var GROUP_LABELS = {
    growth:           "成长性",
    profitability:    "盈利能力",
    solvency:         "偿债能力",
    efficiency:       "营运能力",
    cashflow_quality: "现金流质量"
  };

  /* 页面 2 主要财务数据表的 16 个科目（顺序 = 呈现顺序）
     ★ 键名已全部改成 D 的 financials 键名。对照表（对齐方案 2.1）：
         E 旧名                  → D 现名
         cost_of_revenue         → operating_cost
         rd_expense              → rnd_expense
         net_income_attr         → net_income_parent
         net_income_deducted     → net_income_excl_nonrecurring
         equity_attr             → equity_parent
       其余 11 个（revenue / total_assets / total_liabilities / cash_and_equivalents
       / accounts_receivable / inventory / goodwill / cfo / cfi / cff / capex）
       本来就同名 —— D 的适配层已经把 A 的 `cash` 对到 cash_and_equivalents 了。 */
  var FIN_KEYS = [
    "revenue", "operating_cost", "rnd_expense",
    "net_income_parent", "net_income_excl_nonrecurring",
    "total_assets", "cash_and_equivalents", "accounts_receivable", "inventory", "goodwill",
    "total_liabilities", "equity_parent",
    "cfo", "cfi", "cff", "capex"
  ];
  var FIN_LABELS = {
    revenue: "营业收入",
    operating_cost: "营业成本",
    rnd_expense: "研发费用",
    net_income_parent: "归母净利润",
    net_income_excl_nonrecurring: "扣非归母净利润",
    total_assets: "总资产",
    cash_and_equivalents: "货币资金",
    accounts_receivable: "应收账款",
    inventory: "存货",
    goodwill: "商誉",
    total_liabilities: "总负债",
    equity_parent: "归母净资产",
    cfo: "经营活动现金流净额",
    cfi: "投资活动现金流净额",
    cff: "筹资活动现金流净额",
    capex: "资本开支"
  };

  /* ========================================================================
     契约本体：按页分组
     ======================================================================*/
  var PAGES = [];

  function page(id, title, items) {
    PAGES.push({ id: id, title: title, items: items });
  }

  /* ---- 页 1 · 上传年报 -------------------------------------------------- */
  page("p1", "上传年报", [
    { p: "company.name",           lv: "core", who: "A", label: "公司名称", t: "str" },
    { p: "company.ticker",         lv: "opt",  who: "A", label: "股票代码" },
    { p: "company.industry",       lv: "opt",  who: "A", label: "所属行业" },
    { p: "company.report_period",  lv: "opt",  who: "A", label: "报告期间" },
    /* --- 以下四项是 D 新给的，E 原来压根没读（B 类「领新字段」）--- */
    { p: "company.exchange",       lv: "opt",  who: "A", label: "上市地" },
    { p: "company.report_type",    lv: "opt",  who: "A", label: "报告类型（年报／半年报）" },
    { p: "company.auditor",        lv: "opt",  who: "A", label: "审计机构" },
    /* 🔴 D 自己标了「要紧」：非标审计意见要触发风险规则。
       E 把它显示在页 1 的公司抬头，标成「需关注」当出现非标意见时。 */
    { p: "company.audit_opinion",  lv: "opt",  who: "A", label: "审计意见" },
    /* currency 与 amount_unit 是**显示用**的：unit 只管数量级（一律「元」），
       币种单独存。E 显示时拼成「人民币元」/「美元」。见对齐方案 1.2。 */
    { p: "company.currency",       lv: "opt",  who: "A", label: "币种（CNY／USD／HKD）" },
    { p: "company.amount_unit",    lv: "opt",  who: "A", label: "金额单位" }
  ]);

  /* ---- 页 2 · 财务概览 -------------------------------------------------- */
  (function () {
    var items = [
      { p: "financials", lv: "core", who: "A", label: "财务数据块", t: "obj" }
    ];
    FIN_KEYS.forEach(function (k) {
      items.push({ p: "financials." + k + ".value", lv: "core", who: "A",
                   label: FIN_LABELS[k], gate: "financials", t: "num" });
      /* 页码是页面 2 最值钱的东西：整页 16 行都能点开溯源。
         没有它，这页就只是一堆数字。 */
      items.push({ p: "financials." + k + ".page", lv: "core", who: "A",
                   label: FIN_LABELS[k] + " 的页码", gate: "financials" });
      /* 上期值：D 的适配层从 A 的 series 里取了上一年填进来。
         ★ 2026-10-13 页面 2 用上它了：财务数据表有一列「上期」（见
         p2-overview.js 的 statementBlock）。这里仍然标 **opt 不是 core**，
         因为它缺席时页面有一条正经退路 —— 整列不画、表退回四列，
         而不是摊一列 17 行破折号的空壳。

         ⚠️ 这条注释原来写的是「有了它，页面 2 才有『同比』这一列」——
         不对，页面 2 从头到尾没有同比列，只有上期值本身。
         **同比是算出来的，那是 B 的成长性维度**（ratios.growth.*），
         E 把它摆在页面 2 就是越权重算。改这一列时别顺手把差也算出来。 */
      items.push({ p: "financials." + k + ".prior_value", lv: "opt", who: "A",
                   label: FIN_LABELS[k] + " 的上期值", gate: "financials", t: "num" });
      items.push({ p: "financials." + k + ".prior_period", lv: "opt", who: "A",
                   label: FIN_LABELS[k] + " 的上期期间", gate: "financials" });
    });
    /* ★ 已撤：business_mix（主营构成）与 history（多期趋势）两块。
       A 的抽取结果里根本没有这两个键（顶层只有 company / financials /
       extraction_meta），D 的 Schema 里也没有，431 行的对齐方案全文没提。
       **四家都不产出的东西，E 不做。** 详见文件末尾「已撤与待补」。 */
    page("p2", "财务概览", items);
  })();

  /* ---- 页 3 · 财务诊断 -------------------------------------------------- */
  (function () {
    var items = [
      { p: "ratios", lv: "core", who: "B", label: "指标块", t: "obj" }
    ];
    Object.keys(INDICATORS).forEach(function (g) {
      var L = GROUP_LABELS[g];
      items.push({ p: "ratios." + g, lv: "core", who: "B",
                   label: L + " 维度", gate: "ratios", t: "obj" });

      INDICATORS[g].forEach(function (k) {
        /* ★ 已撤：ratios.<g>._score（维度得分，驱动雷达图）。
           D 的 ratios 里没有 _score，Schema.json / 对齐方案 / 统一输出
           **三处都是 0** —— B 算的 65 个指标里也没有「维度分」这个概念。
           E 不能自己算分（E 绝不重算数据），所以雷达图撤掉。
           页面 3 的视觉主体改为五块指标表，见 p3-diagnosis.js。 */
        var isArrears = (g === "solvency" && SOLVENCY_ARREARS[k]);
        items.push({ p: "ratios." + g + "." + k + ".value",
                     lv: isArrears ? "open" : "core", who: "B",
                     label: L + "·" + k, gate: "ratios." + g, t: "num" });
        /* D 的 ratio 记录里**有** page 字段（Schema 定义了），
           但真数据里两家公司都是 null —— B 拿不到页码。
           所以是 opt 不是 open：字段在，只是这家取不到，缺了页面少个链接。 */
        items.push({ p: "ratios." + g + "." + k + ".page", lv: "opt", who: "B",
                     label: L + "·" + k + " 的页码", gate: "ratios." + g });
        /* D 不给 ratio 的中文名 —— E 的 RATIO_LABELS 兜底翻译。
           只有出现 E 没登记过的新指标时才会露出英文键名。 */
        items.push({ p: "ratios." + g + "." + k + ".name", lv: "opt", who: "B",
                     label: L + "·" + k + " 的中文名", gate: "ratios." + g });
        /* --- 以下三项是 D 新给的（B 类「领新字段」）--- */
        /* status 是 D 的「这个数能不能用」：ok / not_evaluable / not_meaningful。
           有了它，页面 3 才能像 D 的简报那样写「数据缺失·待核验」而不是留白 ——
           **留白和「这家公司不适用」是两回事**，这个字段是区分它们的东西。 */
        items.push({ p: "ratios." + g + "." + k + ".status", lv: "opt", who: "B",
                     label: L + "·" + k + " 的状态", gate: "ratios." + g });
        items.push({ p: "ratios." + g + "." + k + ".prev", lv: "opt", who: "B",
                     label: L + "·" + k + " 的上期值", gate: "ratios." + g, t: "num" });
        items.push({ p: "ratios." + g + "." + k + ".delta", lv: "opt", who: "B",
                     label: L + "·" + k + " 的变动", gate: "ratios." + g, t: "num" });
      });
    });
    page("p3", "财务诊断", items);
  })();

  /* ---- 页 4 · 风险雷达 -------------------------------------------------- */
  page("p4", "风险雷达", [
    { p: "risks[]",                       lv: "core", who: "B", label: "风险数据（risks 数组）" },
    /* ⚠️ risks 为空数组是**合法状态**（EDGE_CASES 3：页面显示「未触发风险规则」），
       不是缺口。走查器把「空数组」单列一档，就是为了不把这种情况报成错。
       ★ 另：D 的适配层已按 status == "triggered" 过滤过（对齐方案 3.4）——
       B 原本把 40 条规则全塞进 risks，其中二十多条 severity 为 null 是空壳。
       到这里剩下的都是真触发的，E 不必再过滤。 */
    { p: "risks[].risk_name",             lv: "core", who: "B", label: "风险名",     gate: "risks[]" },
    { p: "risks[].severity",              lv: "core", who: "B", label: "严重度",     gate: "risks[]" },
    { p: "risks[].trigger",               lv: "core", who: "B", label: "触发规则原文", gate: "risks[]" },
    { p: "risks[].explanation",           lv: "core", who: "B", label: "解释正文",   gate: "risks[]" },
    { p: "risks[].suggested_action",      lv: "opt",  who: "B", label: "应对建议",   gate: "risks[]" },
    /* --- 以下八项是 D 新给的（B 类「领新字段」）---
       E 原来向 B 要的是 calculation + evidence 两套自定义结构，B 没做；
       D 的适配层把 B 的 evidence_chain 拆成了 involved_values / numeric_evidence
       / text_evidence / evidence_chain 四样 —— **比 E 原来要的更全**。 */
    { p: "risks[].risk_id",               lv: "opt",  who: "B", label: "规则编号",   gate: "risks[]" },
    { p: "risks[].category",              lv: "opt",  who: "B", label: "风险类别",   gate: "risks[]" },
    { p: "risks[].severity_tag",          lv: "opt",  who: "B", label: "严重度标签（重大／关注）", gate: "risks[]" },
    { p: "risks[].score",                 lv: "opt",  who: "B", label: "风险评分",   gate: "risks[]", t: "num" },
    { p: "risks[].status",                lv: "opt",  who: "B", label: "规则状态",   gate: "risks[]" },
    /* 带值的证据：触发这个风险的原始数字，每项带 metric/value/unit/period/page */
    { p: "risks[].involved_values[]",     lv: "opt",  who: "B", label: "涉及数值",   gate: "risks[]" },
    { p: "risks[].involved_values[].metric", lv: "core", who: "B", label: "涉及数值·指标名", gate: "risks[].involved_values[]" },
    { p: "risks[].involved_values[].value",  lv: "opt",  who: "B", label: "涉及数值·数值",   gate: "risks[].involved_values[]" },
    { p: "risks[].involved_values[].unit",   lv: "opt",  who: "B", label: "涉及数值·单位",   gate: "risks[].involved_values[]" },
    { p: "risks[].involved_values[].period", lv: "opt",  who: "B", label: "涉及数值·期间",   gate: "risks[].involved_values[]" },
    { p: "risks[].involved_values[].page",   lv: "opt",  who: "B", label: "涉及数值·年报页码", gate: "risks[].involved_values[]" },
    /* 一句话把触发讲成人话；E 原来要的「计算层结果」由它承担 */
    { p: "risks[].numeric_evidence",      lv: "opt",  who: "B", label: "数值证据（一句话）", gate: "risks[]" },
    /* 年报原文引文 —— 这是「可溯源」最硬的一块 */
    { p: "risks[].text_evidence",         lv: "opt",  who: "B", label: "原文证据",   gate: "risks[]" },
    { p: "risks[].text_evidence.quote",   lv: "opt",  who: "B", label: "原文证据·引文", gate: "risks[].text_evidence" },
    { p: "risks[].text_evidence.page",    lv: "opt",  who: "B", label: "原文证据·页码", gate: "risks[].text_evidence" },
    /* 🔴 六层证据链（数据→计算→出处→判断→建议→…）。D 原话：
       「信息量大，E 的『点击展开』正好用得上」。
       E 原来根本没有可展开的东西 —— 这是页面 4 交互升级的原料。 */
    { p: "risks[].evidence_chain[]",      lv: "opt",  who: "B", label: "证据链",     gate: "risks[]" },

    /* --- 没触发的规则：页面 4 的「已检查 N 条，触发 M 条」靠它 --- */
    { p: "rules_evaluated[]",             lv: "opt",  who: "B", label: "已评估规则清单" },
    { p: "rules_evaluated[].rule_id",     lv: "opt",  who: "B", label: "已评估规则·编号", gate: "rules_evaluated[]" },
    { p: "rules_evaluated[].rule_name",   lv: "opt",  who: "B", label: "已评估规则·名称", gate: "rules_evaluated[]" },
    { p: "rules_evaluated[].status",      lv: "opt",  who: "B", label: "已评估规则·状态", gate: "rules_evaluated[]" }
  ]);

  /* ---- 页 5 · 估值分析 -------------------------------------------------- */
  page("p5", "估值分析", [
    { p: "valuation",                                     lv: "core", who: "C", label: "估值块", t: "obj" },

    /* --- comps：相对估值（C 的 relative）--- */
    /* ★ 定 core：C 的降级要求（INTERFACE_CONTRACT 三·3）写明
       「comps 单独存在时也必须是一个完整的可用对象」—— 即 DCF 可以没有，
       comps 不能没有。它是页面 5 的主体，缺了整页就是空的。 */
    { p: "valuation.comps",                              lv: "core", who: "C", label: "可比公司估值", t: "obj" },
    { p: "valuation.comps.peer_companies[]",             lv: "core", who: "C", label: "可比公司清单", gate: "valuation.comps" },
    { p: "valuation.comps.peer_companies[].name",        lv: "core", who: "C", label: "可比公司名",   gate: "valuation.comps.peer_companies[]" },
    { p: "valuation.comps.peer_companies[].ticker",      lv: "opt",  who: "C", label: "可比公司代码", gate: "valuation.comps.peer_companies[]" },
    { p: "valuation.comps.peer_companies[].pe",          lv: "opt",  who: "C", label: "可比公司 PE",       gate: "valuation.comps.peer_companies[]" },
    { p: "valuation.comps.peer_companies[].pb",          lv: "opt",  who: "C", label: "可比公司 PB",       gate: "valuation.comps.peer_companies[]" },
    { p: "valuation.comps.peer_companies[].ev_ebitda",   lv: "opt",  who: "C", label: "可比公司 EV/EBITDA", gate: "valuation.comps.peer_companies[]" },
    { p: "valuation.comps.peer_companies[].ps",          lv: "opt",  who: "C", label: "可比公司 PS",       gate: "valuation.comps.peer_companies[]" },
    /* ★ 2026-10-13 补登记：估值对象（页面 5 的「这个区间是给谁估的」）。
       旧契约里这一块叫 comps.target 且只有 eps / net_income / shares_outstanding；
       D 交的是 comps.inputs，多了 ebitda / net_debt / share_price / market_cap。
       ebitda 与 net_debt 对茅台是 null —— 它没有 EBITDA（无息税折旧口径）
       也没有净债务可算，D 在 warnings 里写明「标的对应指标为负或缺失，已跳过」。
       所以这两条只登记不报警：它们为 null 是**事实**，不是欠账。 */
    { p: "valuation.comps.inputs",                       lv: "opt",  who: "C", label: "估值对象",     t: "obj", gate: "valuation.comps" },
    { p: "valuation.comps.inputs.revenue",               lv: "opt",  who: "C", label: "估值对象·营业收入", gate: "valuation.comps.inputs" },
    { p: "valuation.comps.inputs.net_income",            lv: "opt",  who: "C", label: "估值对象·归母净利润", gate: "valuation.comps.inputs" },
    { p: "valuation.comps.inputs.share_price",           lv: "opt",  who: "C", label: "估值对象·股价",   gate: "valuation.comps.inputs" },
    { p: "valuation.comps.inputs.shares_outstanding",    lv: "opt",  who: "C", label: "估值对象·总股本", gate: "valuation.comps.inputs" },
    { p: "valuation.comps.inputs.market_cap",            lv: "opt",  who: "C", label: "估值对象·市值",   gate: "valuation.comps.inputs" },
    { p: "valuation.comps.inputs.currency",              lv: "opt",  who: "C", label: "估值对象·币种",   gate: "valuation.comps.inputs" },
    /* 每种倍数一个区间：min / median / max */
    { p: "valuation.comps.peer_multiples",               lv: "opt",  who: "C", label: "可比公司倍数区间", gate: "valuation.comps" },
    { p: "valuation.comps.peer_multiples.pe.median",     lv: "opt",  who: "C", label: "PE 中位数",   gate: "valuation.comps.peer_multiples" },
    { p: "valuation.comps.peer_multiples.pb.median",     lv: "opt",  who: "C", label: "PB 中位数",   gate: "valuation.comps.peer_multiples" },
    { p: "valuation.comps.peer_multiples.ev_ebitda.median", lv: "opt", who: "C", label: "EV/EBITDA 中位数", gate: "valuation.comps.peer_multiples" },
    { p: "valuation.comps.peer_multiples.ps.median",     lv: "opt",  who: "C", label: "PS 中位数",   gate: "valuation.comps.peer_multiples" },
    /* 每种倍数推出来的每股价值：low / mid / high。
       ★ 页面 5 现在真的渲染这一块 —— 它是「本公司比同行贵还是便宜」的答案。
       E 不做乘法，直接读 D 算好的值。
       实数据下四种倍数**只有 PE / PS 有 mid**，PB 与 EV/EBITDA 全空，
       D 在 warnings 里逐条写了原因（「市净率：标的净资产为负或缺失，已跳过」/
       「EV/EBITDA：标的对应指标为负或缺失，已跳过」）。
       所以这里只登记真有的两项 —— 登记必然为 null 的项只会制造噪音。 */
    { p: "valuation.comps.implied_value_per_share",      lv: "opt",  who: "C", label: "推导每股价值", gate: "valuation.comps" },
    { p: "valuation.comps.implied_value_per_share.pe.mid", lv: "opt", who: "C", label: "PE 法每股价值", gate: "valuation.comps.implied_value_per_share" },
    { p: "valuation.comps.implied_value_per_share.ps.mid", lv: "opt", who: "C", label: "PS 法每股价值", gate: "valuation.comps.implied_value_per_share" },
    /* 🔴 D 专门替 E 挡下来的一个错（对齐方案 4.3）：
       C 原始的 range_low / range_high 是**股权价值总额（元）**，不是每股。
       C 的交接说明教 E 拿它当 Comps 区间画图 —— **E 会把 5104 亿当股价显示**。
       D 的适配层已经换成 valuation_range 并**自带 currency: "元/股"**。
       E 一律读这里，绝不读 C 的原始 range_low / range_high。
       若哪天 currency 不是「元/股」，页面 5 就不画标尺（见 p5-valuation.js）。 */
    { p: "valuation.comps.valuation_range",              lv: "opt",  who: "C", label: "估值区间",     gate: "valuation.comps" },
    { p: "valuation.comps.valuation_range.low",          lv: "opt",  who: "C", label: "估值区间·下限", gate: "valuation.comps.valuation_range" },
    { p: "valuation.comps.valuation_range.mid",          lv: "opt",  who: "C", label: "估值区间·中值", gate: "valuation.comps.valuation_range" },
    { p: "valuation.comps.valuation_range.high",         lv: "opt",  who: "C", label: "估值区间·上限", gate: "valuation.comps.valuation_range" },
    { p: "valuation.comps.valuation_range.currency",     lv: "opt",  who: "C", label: "估值区间的单位口径", gate: "valuation.comps.valuation_range" },

    /* --- dcf：绝对估值 --- */
    { p: "valuation.dcf",                                lv: "opt",  who: "C", label: "DCF 估值", t: "obj" },
    { p: "valuation.dcf.inputs",                         lv: "opt",  who: "C", label: "DCF 假设", t: "obj", gate: "valuation.dcf" },
    { p: "valuation.dcf.inputs.wacc",                    lv: "core", who: "C", label: "WACC",       gate: "valuation.dcf", t: "num" },
    { p: "valuation.dcf.inputs.terminal_growth",         lv: "core", who: "C", label: "永续增长率", gate: "valuation.dcf", t: "num" },
    { p: "valuation.dcf.inputs.tax_rate",                lv: "core", who: "C", label: "税率",       gate: "valuation.dcf", t: "num" },
    { p: "valuation.dcf.inputs.forecast_years",          lv: "core", who: "C", label: "预测年数",   gate: "valuation.dcf", t: "num" },
    { p: "valuation.dcf.inputs.revenue_base",            lv: "opt",  who: "C", label: "收入基数",   gate: "valuation.dcf.inputs" },
    { p: "valuation.dcf.inputs.ebit_margin",             lv: "opt",  who: "C", label: "EBIT 利润率", gate: "valuation.dcf.inputs" },
    { p: "valuation.dcf.forecast[]",                     lv: "opt",  who: "C", label: "逐年预测",   gate: "valuation.dcf" },
    { p: "valuation.dcf.forecast[].year",                lv: "opt",  who: "C", label: "预测年",     gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.forecast[].growth",              lv: "opt",  who: "C", label: "预测收入增速", gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.forecast[].revenue",             lv: "opt",  who: "C", label: "预测营收",   gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.forecast[].ebit",                lv: "opt",  who: "C", label: "预测 EBIT",  gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.forecast[].fcff",                lv: "opt",  who: "C", label: "预测自由现金流", gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.forecast[].discount_factor",     lv: "opt",  who: "C", label: "折现因子",   gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.forecast[].pv_fcff",             lv: "opt",  who: "C", label: "自由现金流现值", gate: "valuation.dcf.forecast[]" },
    { p: "valuation.dcf.terminal_assumptions",           lv: "opt",  who: "C", label: "永续期假设", gate: "valuation.dcf" },
    { p: "valuation.dcf.terminal_assumptions.tv_pct_of_ev", lv: "opt", who: "C", label: "永续价值占比", gate: "valuation.dcf.terminal_assumptions", t: "num" },
    { p: "valuation.dcf.terminal_assumptions.terminal_fcff", lv: "opt", who: "C", label: "永续期自由现金流", gate: "valuation.dcf.terminal_assumptions" },
    { p: "valuation.dcf.terminal_assumptions.pv_terminal_value", lv: "opt", who: "C", label: "终值现值", gate: "valuation.dcf.terminal_assumptions" },
    { p: "valuation.dcf.terminal_assumptions.exit_multiple", lv: "opt", who: "C", label: "退出倍数", gate: "valuation.dcf.terminal_assumptions" },
    /* 终值两种算法的对照。页面 5 把它单独画一行 ——
       「Gordon 55,284 亿 vs 退出倍数 7,401 亿」是 D warnings 的第一条，
       也是这个模型最该被质疑的地方。 */
    { p: "valuation.dcf.terminal_assumptions.tv_gordon", lv: "opt", who: "C", label: "Gordon 终值", gate: "valuation.dcf.terminal_assumptions" },
    { p: "valuation.dcf.terminal_assumptions.tv_exit",   lv: "opt",  who: "C", label: "退出倍数终值", gate: "valuation.dcf.terminal_assumptions" },
    { p: "valuation.dcf.terminal_assumptions.tv_divergence", lv: "opt", who: "C", label: "终值偏离度", gate: "valuation.dcf.terminal_assumptions" },
    { p: "valuation.dcf.valuation_range",                lv: "opt",  who: "C", label: "DCF 估值区间", gate: "valuation.dcf" },
    { p: "valuation.dcf.valuation_range.low",            lv: "opt",  who: "C", label: "DCF 区间·下限", gate: "valuation.dcf.valuation_range" },
    { p: "valuation.dcf.valuation_range.mid",            lv: "opt",  who: "C", label: "DCF 区间·中值", gate: "valuation.dcf.valuation_range" },
    { p: "valuation.dcf.valuation_range.high",           lv: "opt",  who: "C", label: "DCF 区间·上限", gate: "valuation.dcf.valuation_range" },
    { p: "valuation.dcf.valuation_range.currency",       lv: "opt",  who: "C", label: "DCF 区间的单位口径", gate: "valuation.dcf.valuation_range" },
    { p: "valuation.dcf.sensitivity",                    lv: "opt",  who: "C", label: "敏感性分析", gate: "valuation.dcf" },
    { p: "valuation.dcf.sensitivity.matrix",             lv: "opt",  who: "C", label: "敏感性矩阵", gate: "valuation.dcf.sensitivity" },
    /* 矩阵的两个坐标轴与基准点。页面 5 靠 base_wacc / base_growth
       在矩阵里找回基准格并高亮 —— 没有它，「哪个格子是结论所依据的假设」
       就得靠 E 猜一个下标，那是最容易埋错的地方。 */
    { p: "valuation.dcf.sensitivity.wacc_values[]",      lv: "opt",  who: "C", label: "敏感性·WACC 各档", gate: "valuation.dcf.sensitivity" },
    { p: "valuation.dcf.sensitivity.terminal_growth_values[]", lv: "opt", who: "C", label: "敏感性·永续增长各档", gate: "valuation.dcf.sensitivity" },
    { p: "valuation.dcf.sensitivity.base_wacc",          lv: "opt",  who: "C", label: "敏感性·基准 WACC", gate: "valuation.dcf.sensitivity" },
    { p: "valuation.dcf.sensitivity.base_growth",        lv: "opt",  who: "C", label: "敏感性·基准永续增长", gate: "valuation.dcf.sensitivity" },
    { p: "valuation.dcf.sensitivity.unit",               lv: "opt",  who: "C", label: "敏感性·单位", gate: "valuation.dcf.sensitivity" },

    /* --- blended：★ 页面 5 的头条数字 --- */
    /* D 原话：「融合每股价值、相对现价的上行空间、低估或高估的结论，
       **E 页面的头条数字**，最有用的一块」。
       ⭐ 这是 B 类「领新字段」里最值钱的一项 —— E 第一版契约里根本没有它。
       定 opt 不定 core：它是**导出量**，输入不全时（缺行情、缺可比公司）
       必然为 null，D 会在 valuation.warnings 里说明原因。
       把它报成「缺口」是噪音 —— 缺的是行情，不是这个字段。 */
    { p: "valuation.blended",                            lv: "opt",  who: "C", label: "融合估值", t: "obj" },
    { p: "valuation.blended.blended_per_share",          lv: "opt",  who: "C", label: "融合每股价值", gate: "valuation.blended", t: "num" },
    { p: "valuation.blended.current_price",              lv: "opt",  who: "C", label: "当前股价",   gate: "valuation.blended", t: "num" },
    { p: "valuation.blended.upside",                     lv: "opt",  who: "C", label: "相对现价空间", gate: "valuation.blended" },
    { p: "valuation.blended.verdict",                    lv: "opt",  who: "C", label: "高估／低估结论", gate: "valuation.blended" },
    { p: "valuation.blended.components[]",               lv: "opt",  who: "C", label: "融合构成",   gate: "valuation.blended" },
    { p: "valuation.blended.components[].label",         lv: "core", who: "C", label: "融合构成·方法名", gate: "valuation.blended.components[]" },
    { p: "valuation.blended.components[].per_share",     lv: "opt",  who: "C", label: "融合构成·每股价值", gate: "valuation.blended.components[]" },
    { p: "valuation.blended.components[].weight",        lv: "opt",  who: "C", label: "融合构成·权重", gate: "valuation.blended.components[]" },
    { p: "valuation.blended.components[].equity_value",  lv: "opt",  who: "C", label: "融合构成·隐含股权价值", gate: "valuation.blended.components[]" },
    /* 页面 5 的「口径」一行读这四个：结论本身 + 两法谁高谁低 + 权重是怎么定的。
       weight_source 是**E 不越权**的保证 —— 它写明了 50/50 是默认值，
       读者才知道那个融合数不是按可信度加权出来的。 */
    { p: "valuation.blended.blended_equity_value",       lv: "opt",  who: "C", label: "融合股权价值", gate: "valuation.blended" },
    { p: "valuation.blended.most_bullish",               lv: "opt",  who: "C", label: "最乐观的方法", gate: "valuation.blended" },
    { p: "valuation.blended.most_bearish",               lv: "opt",  who: "C", label: "最保守的方法", gate: "valuation.blended" },
    { p: "valuation.blended.weight_source",              lv: "opt",  who: "C", label: "权重的来源",   gate: "valuation.blended" },

    /* --- 三情景与分部 --- */
    { p: "valuation.scenarios",                          lv: "opt",  who: "C", label: "三情景",     t: "obj" },
    { p: "valuation.scenarios.bull.per_share",           lv: "opt",  who: "C", label: "乐观情景每股", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.base.per_share",           lv: "opt",  who: "C", label: "中性情景每股", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.bear.per_share",           lv: "opt",  who: "C", label: "悲观情景每股", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.bull.equity_value",        lv: "opt",  who: "C", label: "乐观情景股权价值", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.base.equity_value",        lv: "opt",  who: "C", label: "中性情景股权价值", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.bear.equity_value",        lv: "opt",  who: "C", label: "悲观情景股权价值", gate: "valuation.scenarios" },
    /* levers 是「这三套假设差在哪」的答案，页面 5 单独列成一行 ——
       塞进表格会撑爆列宽，省掉又让人看不出 100% 的价差从哪来。 */
    { p: "valuation.scenarios.bull.levers",              lv: "opt",  who: "C", label: "乐观情景的杠杆", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.base.levers",              lv: "opt",  who: "C", label: "中性情景的杠杆", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.bear.levers",              lv: "opt",  who: "C", label: "悲观情景的杠杆", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.bull.wacc",                lv: "opt",  who: "C", label: "乐观情景 WACC", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.base.wacc",                lv: "opt",  who: "C", label: "中性情景 WACC", gate: "valuation.scenarios" },
    { p: "valuation.scenarios.bear.wacc",                lv: "opt",  who: "C", label: "悲观情景 WACC", gate: "valuation.scenarios" },
    /* sotp 只登记对象本身，**不登记 ok / skipped / reason** ——
       页面 5 不单列分部估值块（它的 skip 理由与 warnings 里那句重复），
       消费端契约只登记真被消费的路径。 */
    { p: "valuation.sotp",                               lv: "opt",  who: "C", label: "分部估值" },

    /* --- 行情与告警 --- */
    { p: "valuation.market_data",                        lv: "opt",  who: "C", label: "行情数据",   t: "obj" },
    { p: "valuation.market_data.price",                  lv: "opt",  who: "C", label: "股价",       gate: "valuation.market_data" },
    { p: "valuation.market_data.price_date",             lv: "opt",  who: "C", label: "股价日期",   gate: "valuation.market_data" },
    /* ★ price_date 是标尺上「现价竖线」的时点标签。没有它，
       读者不知道那条线是今天的价还是上个季度的价 —— 差一年结论就不一样。 */
    { p: "valuation.market_data.market_cap",             lv: "opt",  who: "C", label: "市值",       gate: "valuation.market_data" },
    { p: "valuation.market_data.shares_outstanding",     lv: "opt",  who: "C", label: "总股本",     gate: "valuation.market_data" },
    /* ★ 2026-10-13 新增：估值自己的来源清单。与顶层 sources[] 是**两套** ——
       顶层那条是按年报页码走的（8 条，都是同一份年报），
       这里这 3 条是按估值输入走的（财务报表 / 行情 / 无风险利率），
       只有最后一条 official:true。页面 5 用它回答「这些假设是从哪拿的」，
       与页面 2/3 的页码溯源回答的是两个不同的问题。 */
    { p: "valuation.sources[]",                          lv: "opt",  who: "C", label: "估值来源" },
    { p: "valuation.sources[].name",                     lv: "opt",  who: "C", label: "估值来源·名称", gate: "valuation.sources[]" },
    { p: "valuation.sources[].purpose",                  lv: "opt",  who: "C", label: "估值来源·用途", gate: "valuation.sources[]" },
    { p: "valuation.sources[].as_of",                    lv: "opt",  who: "C", label: "估值来源·取数日期", gate: "valuation.sources[]" },
    { p: "valuation.sources[].official",                 lv: "opt",  who: "C", label: "估值来源·是否官方", gate: "valuation.sources[]" },
    /* 🔴 C 与 D 都强调过：「warnings 是结论的一部分，不是报错」。
       缺行情、缺可比公司、跳过 SOTP 这些**都写在这里**。
       E 页面 5 必须显示它们 —— 否则用户看到一片空白，
       不知道是「这家公司不值钱」还是「数据没取到」。这两者天差地别。 */
    { p: "valuation.warnings[]",                         lv: "opt",  who: "C", label: "估值告警" },
    { p: "valuation.disclaimer",                         lv: "opt",  who: "C", label: "免责声明" }
  ]);

  /* ---- 页 6 · 投研报告 --------------------------------------------------
     ★★ 关于页面 6：数据源不是统一对象，是 D 的 memo.json ★★
     --------------------------------------------------------------------
     D 的 Schema.json 里**根本没有 report 这个概念**（对齐方案里那 4 处
     "report" 全是 report_period / report_type 的子串）。D 的投研简报是
     report-skill/ 单独产出的另一套产物：

       out_data/reports/<key>/memo.json   ← E 读这个
       out_data/reports/<key>/memo.html / .md / .csv

     memo.json 不是「报告正文」，是一张**占位符 → 值 的绑定表**：
       meta         这份简报的元信息
       columns[]    七个章节标题（① 结论摘要 … ⑦ 数据来源与免责声明）
       scalars[]    56 个标量，每条 { placeholder, source_path, raw_value, formatted }
       collections[] 12 个具名列表（top_risks / dashboard / cashflow_bridge / …）
       numbers[]    96 个数字及其来源路径（核验用）
       compliance / validation  D 自己的合规闸门结果

     ★ 关键好处：**每个值都已经格式化好了**（formatted 字段，
       如 "4,564.52 亿元"），E 不需要自己格式化 —— 页面 6 是唯一
       E 不做数字格式化的页面。这也正是「E 绝不重算数据」的自然延伸。

     ★ 代价：这是产物不是我方契约。D 改模板，这里要跟着改。
       所以下面全部按 memo 的真实结构登记，并且 gate 挂在 meta / columns /
       scalars / collections 上 —— 少一节不报错，整份没有才报「未提供」。
     -------------------------------------------------------------------- */
  page("p6", "投研报告", [
    { p: "meta",                          lv: "open",  who: "D", root: "memo", label: "简报元信息", t: "obj" },
    { p: "meta.company_name",             lv: "core",  who: "D", root: "memo", label: "公司名称", gate: "meta", t: "str" },
    { p: "meta.ticker",                   lv: "opt",   who: "D", root: "memo", label: "股票代码", gate: "meta" },
    { p: "meta.report_period",            lv: "opt",   who: "D", root: "memo", label: "报告期间", gate: "meta" },
    { p: "meta.generated_at",             lv: "opt",   who: "D", root: "memo", label: "生成时间", gate: "meta" },
    /* engine 那句话（「不使用大模型，数字全部代码注入」）是**可信度声明**，
       值得原样显示在页面上 —— 这是 FinScope 与「让大模型编一份研报」的分界线。 */
    { p: "meta.engine",                   lv: "opt",   who: "D", root: "memo", label: "渲染引擎说明", gate: "meta" },

    { p: "columns[]",                     lv: "core",  who: "D", root: "memo", label: "章节标题" },
    { p: "scalars[]",                     lv: "core",  who: "D", root: "memo", label: "标量绑定表" },
    { p: "scalars[].placeholder",         lv: "core",  who: "D", root: "memo", label: "标量·占位符名", gate: "scalars[]", t: "str" },
    { p: "scalars[].formatted",           lv: "opt",   who: "D", root: "memo", label: "标量·已格式化值", gate: "scalars[]" },
    { p: "scalars[].source_path",         lv: "opt",   who: "D", root: "memo", label: "标量·来源点路径", gate: "scalars[]" },
    { p: "collections[]",                 lv: "core",  who: "D", root: "memo", label: "具名列表" },
    { p: "collections[].name",            lv: "core",  who: "D", root: "memo", label: "列表·名称", gate: "collections[]", t: "str" },
    { p: "collections[].items",           lv: "opt",   who: "D", root: "memo", label: "列表·内容", gate: "collections[]" },

    /* D 自己的合规闸门：validation.passed 为 false 或 violations 非空时，
       页面 6 必须把这件事顶到最上面 —— 这是「这份简报可信吗」的直接答案。 */
    { p: "validation.passed",             lv: "opt",   who: "D", root: "memo", label: "合规闸门是否通过", gate: "validation" },
    { p: "validation.violations[]",       lv: "opt",   who: "D", root: "memo", label: "合规违规项", gate: "validation" },
    { p: "compliance.hits[]",             lv: "opt",   who: "D", root: "memo", label: "合规命中项", gate: "compliance" }
  ]);

  /* ---- 共享 · 溯源浮层（每一页都在用）----------------------------------- */
  page("shared", "全站溯源", [
    /* ★ 定 core：整个产品的立命之本是可溯源。sources 一缺，全站每一处
       「点击看出处」都变成死链 —— 页面还在，但那正是 E 卖的东西没了。
       这条也与 dataLoader 原来的浅检查口径一致（sources 在 REQUIRED_TOP 里）。 */
    { p: "sources[]",              lv: "core", who: "D", label: "数据来源索引" },
    /* ★ 改名：E 原来读 sources[].source（文件名），D 的 Schema 键是 file_name。
       真数据里两个键都在，但以 D 的 Schema 为准。 */
    { p: "sources[].file_name",    lv: "core", who: "D", label: "来源·文件名", gate: "sources[]" },
    { p: "sources[].page",         lv: "core", who: "D", label: "来源·页码",   gate: "sources[]" },
    { p: "sources[].company_name", lv: "opt",  who: "D", label: "来源·公司名", gate: "sources[]" },
    { p: "sources[].report_period", lv: "opt", who: "D", label: "来源·报告期", gate: "sources[]" },
    /* 🔴 现在浮层只到「告诉你在哪」，没到「带你过去」—— 用户看完还得自己
       翻年报找第 80 页。D 的 Schema 里有 source_url，真数据里目前是 null。
       补上它，E 会在浮层底部加「打开原文 ↗」，零改动接入。 */
    { p: "sources[].source_url",   lv: "open", who: "D", label: "来源·可跳转地址（打开原文）", gate: "sources[]" },
    { p: "sources[].retrieved_at", lv: "opt",  who: "D", label: "来源·取数时间", gate: "sources[]" }
  ]);

  /* ========================================================================
     走查器
     ======================================================================*/

  /* 路径求值。返回 { status, n, filled }
       status: "ok"    路径存在且有值
               "null"  路径在，值是 null（= 未提取 / 不适用）
               "miss"  路径不存在
               "empty" 是数组但一个元素都没有（**中性，不是错**）
               "type"  类型与契约声明不符
               "range" 数值越界
               "gated" 上游闸门没提供（由 check 的第二遍填） */
  function evalPath(data, spec) {
    var segs = String(spec.p).split(".");
    var cur = [data];

    for (var i = 0; i < segs.length; i++) {
      var seg = segs[i];
      var each = seg.slice(-2) === "[]";
      var key = each ? seg.slice(0, -2) : seg;
      var next = [];
      var sawEmpty = false;

      for (var j = 0; j < cur.length; j++) {
        var node = cur[j];
        if (node === null || node === undefined || typeof node !== "object") continue;
        var v = node[key];
        if (v === undefined) continue;

        if (each) {
          /* `[]` 自己就断言了「这里必须是数组」——
             risks 传成对象、sources 传成字符串都在这一行被抓住。
             所以契约里不用再写 t:"arr"，写了反而是错的：
             走查器已经把数组扇开了，叶子拿到的是**元素**不是数组。 */
          if (v === null) { next.push(v); continue; }          // null 交给叶子判定
          if (!Array.isArray(v)) {
            return { status: "type", n: 1, filled: 1, sample: v, want: "数组（" + spec.p + " 的 [] 段）" };
          }
          if (!v.length) { sawEmpty = true; continue; }
          for (var k = 0; k < v.length; k++) next.push(v[k]);
        } else {
          next.push(v);
        }
      }

      if (!next.length) return { status: sawEmpty ? "empty" : "miss", n: 0, filled: 0 };
      cur = next;
    }

    var filled = cur.filter(function (v) { return v !== null && v !== undefined; });

    if (!filled.length) return { status: "null", n: cur.length, filled: 0 };

    /* 类型与范围只对**叶子**检查：中间层是容器，类型由路径形状保证 */
    if (spec.t) {
      var bad = filled.filter(function (v) {
        if (spec.t === "num")    return !isFinite(Number(v)) || typeof v === "boolean";
        if (spec.t === "str")    return typeof v !== "string" || !v;
        if (spec.t === "arr")    return !Array.isArray(v);
        if (spec.t === "obj")    return typeof v !== "object" || Array.isArray(v);
        return false;
      });
      if (bad.length) return { status: "type", n: cur.length, filled: filled.length, sample: bad[0] };
    }

    if (spec.range) {
      var out = filled.filter(function (v) {
        var n = Number(v);
        return !isFinite(n) || n < spec.range[0] || n > spec.range[1];
      });
      if (out.length) return { status: "range", n: cur.length, filled: filled.length, sample: out[0] };
    }

    return { status: "ok", n: cur.length, filled: filled.length };
  }

  /**
   * 走查一份候选数据。
   *   raw   统一对象（D 的 unified.json）
   *   memo  投研简报绑定表（D 的 memo.json），页面 6 专用。不传则页面 6 全部记 gated
   * 返回逐路径结果的扁平数组。**不抛异常** —— 传 null / 非对象也照常出报告。
   */
  function check(raw, memo) {
    var roots = { "": raw, "memo": memo };
    var all = [];

    PAGES.forEach(function (pg) {
      pg.items.forEach(function (spec) {
        var rootKey = spec.root || "";
        var rootData = roots[rootKey];
        var r;
        if (rootData === null || rootData === undefined) {
          /* 整份数据源没给（比如根本没传 memo.json）——
             记 gated 而不是 miss，否则页面 6 的 22 条会一起报成缺口。
             一份文件没交，是**一件事**，不是 22 件事。 */
          r = { status: "gated", n: 0, filled: 0, gateStatus: "miss" };
        } else {
          r = evalPath(rootData, spec);
        }
        r.spec = spec;
        r.pageId = pg.id;
        r.pageTitle = pg.title;
        all.push(r);
      });
    });

    /* 第二遍：闸门。上游整块没提供时，子路径记 "gated" ——
       否则一个块一缺就立刻连报 N 条子路径，一条真缺口被 N 条噪音盖住。 */
    var byPath = {};
    all.forEach(function (r) { byPath[(r.spec.root || "") + "|" + r.spec.p] = r; });

    all.forEach(function (r) {
      var g = r.spec.gate;
      var pre = (r.spec.root || "") + "|";
      while (g) {
        var gr = byPath[pre + g];
        if (!gr) break;
        if (gr.status === "miss" || gr.status === "null" || gr.status === "empty" || gr.status === "gated") {
          r.status = "gated";
          r.gateStatus = gr.status;
          break;
        }
        g = gr.spec.gate;                     // 闸门本身也被闸住 → 继续往上找
      }
    });

    /* ==================================================================
       第三遍：not_applicable —— 「这一项对这家公司不成立」是一种**答复**，
       不是缺口。
       ------------------------------------------------------------------
       真例：茅台的 goodwill 是
         { value: null, status: "not_applicable", page: 57 }
       D 用 status 说了「年报的资产负债表上本来就没有这一行」。
       于是 `financials.goodwill` 这一族的四条路径（value / page /
       prior_value / prior_period）**都算已被答复**。

       不这么做的后果很具体：提醒条上会写着「【财务概览】缺 1 项：商誉 · 找 A」——
       让 E 去找 A 补一个**根本不存在**的数。一条指错的欠账，比没有欠账更坏。

       ★ 判据必须落在祖先对象的 `status` 上，**不能落在 `value === null`**。
         按 value 判会把「上游没抽到」一并放行 —— 而那正是这一页
         「数字必须可验证」要防的事：缺数据必须明说，不能不留白。
         这与 dataLoader.js 的 isNotApplicable 是同一条规矩的两端，改一处要看另一处。

       ⚠️ 只处理**不含 `[]` 的路径**。数组元素（risks[].xxx）没有「祖先对象」
         这个概念 —— 同一条路径上不同元素的状态各不相同，一个 status
         代表不了一族。现在没有需要它的数组路径，遇到再想。 */
    all.forEach(function (r) {
      if (String(r.spec.p).indexOf("[]") >= 0) return;
      var rootData = roots[r.spec.root || ""];
      if (rootData === null || rootData === undefined) return;

      var segs = String(r.spec.p).split(".");
      /* 从最贴近叶子的祖先往上找 —— 就近的那个才算数 */
      for (var i = segs.length - 1; i > 0; i--) {
        var node = nodeAt(rootData, segs.slice(0, i).join("."));
        if (node && typeof node === "object" && node.status === "not_applicable") {
          r.status = "na";
          r.naAt = segs.slice(0, i).join(".");
          break;
        }
      }
    });

    return all;
  }

  /* 按不含 `[]` 的点分路径取一个节点。取不到返回 undefined。 */
  function nodeAt(data, p) {
    var segs = String(p).split(".");
    var cur = data;
    for (var i = 0; i < segs.length; i++) {
      if (cur === null || cur === undefined || typeof cur !== "object") return undefined;
      cur = cur[segs[i]];
    }
    return cur;
  }

  /* 「缺口」= 该有而没拿到。
     ★ na（不适用）**不是**缺口 —— 上游明确答复了「这项不成立」。
       它是唯一一类「存在感为负」的状态：不该让人去找人补，也不该出现在欠账清单里。 */
  function isGap(r) {
    var s = r.status;
    return s === "miss" || s === "null" || s === "type" || s === "range";
  }

  /* ========================================================================
     汇总：把逐路径结果压成「页面 × 谁 × 什么」
     ======================================================================*/

  function summarize(results) {
    var byPage = {};
    results.forEach(function (r) {
      var id = r.pageId;
      byPage[id] = byPage[id] || {
        id: id, title: r.pageTitle,
        core: 0, opt: 0, open: 0, gated: 0, empty: 0, ok: 0, na: 0,
        coreMiss: [], openMiss: [], problems: []
      };
      var b = byPage[id];

      if (r.status === "gated") { b.gated++; return; }
      if (r.status === "empty") { b.empty++; return; }
      if (r.status === "ok")    { b.ok++;    return; }
      /* 不适用也算「这一条有交代了」，所以走 ok 那条路：不进 coreMiss、
         不进 problems、不影响「可否完整渲染」。单独计一个 na 只是为了让
         体检报告能说清楚「这几条不是漏，是不成立」。 */
      if (r.status === "na")    { b.na++; b.ok++; return; }

      if (r.status === "type" || r.status === "range") {
        b.problems.push(r);
        return;
      }

      /* 剩下的就是 miss / null，按 lv 归位 */
      if (r.spec.lv === "core")      { b.core++; b.coreMiss.push(r); }
      else if (r.spec.lv === "open") { b.open++; b.openMiss.push(r); }
      else                           { b.opt++;  b.openMiss.push(r); }
    });

    return PAGES.map(function (pg) { return byPage[pg.id]; }).filter(Boolean);
  }

  /* 按「谁欠着」重新切一刀 —— 这就是给队友的需求文档 */
  function byOwner(results) {
    var out = {};
    results.forEach(function (r) {
      /* na（不适用）也在这里被跳过 —— 它是答复，不是欠账。
         这份 byOwner 就是「发给队友的需求文档」，不该向谁要一个不存在的数。 */
      if (r.status === "gated" || r.status === "empty"
          || r.status === "ok" || r.status === "na") return;
      var w = r.spec.who;
      out[w] = out[w] || { who: w, core: [], open: [], opt: [], problems: [] };
      if (r.status === "type" || r.status === "range") out[w].problems.push(r);
      else if (r.spec.lv === "core") out[w].core.push(r);
      else if (r.spec.lv === "open") out[w].open.push(r);
      else                           out[w].opt.push(r);
    });
    return out;
  }

  window.FinScope.contract = {
    PAGES: PAGES,
    INDICATORS: INDICATORS,
    GROUP_LABELS: GROUP_LABELS,
    FIN_KEYS: FIN_KEYS,
    FIN_LABELS: FIN_LABELS,
    evalPath: evalPath,
    check: check,
    isGap: isGap,
    summarize: summarize,
    byOwner: byOwner,

    /* 全部路径（工具和测试用来做覆盖自查）。
       带 root 前缀 —— 两个数据源里的同名路径要能分开数。 */
    allPaths: function () {
      var out = [];
      PAGES.forEach(function (pg) {
        pg.items.forEach(function (s) {
          out.push(s.root === "memo" ? "memo|" + s.p : s.p);
        });
      });
      return out;
    },

    /* 页面 6 用的那批路径（interface-check 靠它决定要不要去读 memo.json） */
    needsMemo: function () {
      var out = [];
      PAGES.forEach(function (pg) {
        pg.items.forEach(function (s) { if (s.root === "memo") out.push(s.p); });
      });
      return out;
    }
  };
})();

/* ============================================================================
 * 已撤与待补（2026-10-13）—— 记下来，免得下一个人再问一遍
 * ----------------------------------------------------------------------------
 * 【已撤 · 四家都不产出，E 不做】
 *   1. business_mix（主营构成）
 *      A 抽取结果顶层只有 company / financials / extraction_meta，没有这个键；
 *      D 的 Schema.json 与 431 行的对齐方案全文没提。→ 撤掉，页面 2 少一块。
 *
 *   2. history（多期趋势）
 *      ⚠️ **这条和上面不一样**：A 其实有数据 —— 每条指标里都带 `series`
 *      （万华的 revenue 是 {"2025":…, "2024":…, "2023":…} 三年）。
 *      只是 D 的适配层只把它取成 prior_value / prior_period 两格，
 *      没把整条序列路由出来，D 的 Schema 里也没有位置放它。
 *      → 按「统一对象里没有就不做」撤掉。
 *      **但这是四条里唯一一条能低成本恢复的**：让 D 把 A 已有的 series
 *      原样透出一层（对齐方案 2.2 已经标了「要转」），E 这边零成本接回来。
 *      想让页面 2 保留趋势图，找 D 加这一行，不要让 E 去猜。
 *
 *   3. ratios.<g>._score（维度得分）
 *      D 的 ratios 是 65 个具体指标，没有「维度分」这个概念。
 *      E 不能自己算（绝不重算数据）→ 雷达图撤掉，页面 3 改为五块指标表。
 *
 *   4. sources[].metric（来源对应到哪个指标）
 *      D 的 sources 是按「文件 + 页码」组织的，不是按指标。
 *      指标 → 页码的链接改由 financials.<k>.page / risks[].involved_values[].page
 *      承担，浮层改为「按页码反查来源」。
 *
 * 【待补 · 退回队友】
 *   5. ratios.solvency.{current_ratio, quick_ratio, interest_coverage}
 *      要 current_assets / current_liabilities / interest_expense / operating_profit，
 *      全在 A 待扩抽的 25 个科目里（对齐方案 5.1 / 5.2）。
 *      → 登记为 open，页面 3 逐行写「待 A 扩抽」。
 *      A 补完后把 contract 里这三条从 open 改回 core。
 *
 *   6. ratios.<g>.<k>.page —— D 的字段在，真数据里是 null，等 B 补页码。
 *      ⚠️ 真数据里 68 项**有 2 项带值**（现金流质量的 ocf @6、capex @13）。
 *      页面 3 按「有则渲染、无则整格不放」处理，**不写提示条** ——
 *      比率由几个科目算出，本来就不对应某一页，缺的是可选字段不是缺口。
 *      这一条留在这里是提醒「还有 66 项可能补得上」，不是「页面缺东西」。
 *
 *   7. sources[].source_url —— D 的字段在，真数据里是 null，等 D 补链接。
 *
 *   8. valuation 下的**金额**字段没有 unit（找 C/D）
 *      comps.inputs.*、dcf.inputs.revenue_base、dcf.forecast[].*、
 *      dcf.terminal_assumptions.*、blended.*、scenarios.*.equity_value
 *      —— 一个单位声明都没有。Schema 对 company.amount_unit 与
 *      financials.*.unit 都写明了「元」，valuation 里唯一带单位的是
 *      comps/dcf.valuation_range.currency（"元/股"，管的是**每股价格**，
 *      管不到这些总额）。
 *      E 现在按 D 在 memo 里的写法推定「元」再换亿元显示 —— 那是**刻度换算**，
 *      不是重算。但「推定」在演示现场解释不清，请补 unit 或由 Schema 统一声明。
 *      ★ 顺带：valuation_range 用 `currency` 而 financials 用 `unit`，
 *      同一份 Schema 里两套词。E 侧两条都接（currency 优先、退化到 unit）。
 *
 *   9. company.report_title —— A 抽了（"…2025年年度报告"），D 的 company 里没有。
 *      与 history 同类：数据在、没路由。E 现用 company.name + report_period 拼。
 *
 * 【已确认 · 不用再查】
 *   · capex 符号：A 交付的 9 家全为正数、cfi 全为负。EDGE_CASES #48 担心的
 *     「capex 传负数导致比例条和数字打架」在实际数据里没有发生。
 *   · C 的 range_low / range_high 是股权价值总额（元）不是每股 —— D 的适配层
 *     已换成 valuation_range 并自带 currency: "元/股"。E 一律读这里。
 *   · risks 里混着没触发的规则 —— D 的适配层已按 status == "triggered" 过滤。
 * ==========================================================================*/
