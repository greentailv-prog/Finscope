/* ============================================================================
 * mock_data.js —— 假数据（阶段一）
 * ----------------------------------------------------------------------------
 * 作用：在 D 交付统一数据接口之前，用这份手造数据把整个前端先跑起来。
 *       等 D 交付真数据后，只需在 index.html 里把这一行换成 real_data.js，
 *       页面全部变真，其他文件一行都不用改。
 *
 * 重要：
 *   1. 本文件字段名 = E 与 D 的接口约定。改字段名等于改接口，必须双方确认。
 *   2. 用 .js 而不是 .json，是因为最终交付要能双击打开（file:// 协议），
 *      浏览器会因 CORS 拦掉 fetch 本地 .json。写成 JS 变量赋值则不受限制。
 *   3. 数据为演示用虚构数据，非真实上市公司数据。
 *
 * 数据来源分工（团队分工说明第四节）：
 *   company      → D 定义，A 补全公司基本信息（含 business 一句话业务定位）
 *   financials   → A（单期）
 *   business_mix → A（主营构成；E 新增需求，见 INTERFACE_CONTRACT 四·4）
 *   history      → A（多期趋势；E 新增需求，见 INTERFACE_CONTRACT 四·5）
 *   ratios       → B
 *   risks        → B
 *   valuation    → C
 *   sources      → A（页码追踪）
 *
 * ⚠️ business_mix / history 是**可选**字段：A 不交付时页面 2 照常成立，
 *    那两块整块不出现（见 docs/E_PAGE_SPEC.md 页面2 降级行为表）。
 * ==========================================================================*/

window.FINSCOPE_DATA = {

  /* --------------------------------------------------------------------------
   * 1. 公司信息
   * 前端用途：页面2 公司概览 的抬头区
   * ------------------------------------------------------------------------*/
  company: {
    name: "示例科技股份有限公司",          // 公司全称
    ticker: "DEMO.SH",                     // 股票代码
    industry: "电力设备与新能源",          // 所属行业
    report_period: "2025年度",             // 报告期
    report_title: "2025年年度报告",        // 报告名称（用于展示"数据来源"）

    /* ↓ E 向 A 索取的新字段（见 docs/INTERFACE_CONTRACT.md 四·2）。
       一句话说清公司靠什么赚钱，放在抬头下面。页面 2 原来只有财务数字，
       读的人不知道这 128.6 亿是从哪个业务里长出来的。
       A 不给就整行不显示，不留空位。 */
    business: "以输配电设备为主业，同时经营新能源设备与智能电网系统，"
            + "客户以电网公司及大型工业用户为主。",
    business_page: 12                      // 上面那句话出自年报第几页
  },

  /* --------------------------------------------------------------------------
   * 2. 财务数据（A 填写）
   * 统一结构：{ value, unit, period, source, page }
   *   value  数值（一律用"元"为基准换算后的数值，单位见 unit）
   *   unit   展示单位："亿元"
   *   period 归属期间："2025"
   *   source 来源文件
   *   page   年报页码（点开可溯源，A 的页码追踪能力就体现在这）
   * 注意：增长率不在这里，属于 B 的 ratios.growth
   * ------------------------------------------------------------------------*/
  financials: {
    revenue:                { value: 128.6,  unit: "亿元", period: "2025", source: "2025年年度报告", page: 82 },
    cost_of_revenue:        { value: 94.2,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 83 },
    net_income_attr:        { value: 11.4,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 84 },
    net_income_deducted:    { value: 10.1,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 84 },
    total_assets:           { value: 210.5,  unit: "亿元", period: "2025", source: "2025年年度报告", page: 78 },
    total_liabilities:      { value: 118.3,  unit: "亿元", period: "2025", source: "2025年年度报告", page: 78 },
    equity_attr:            { value: 92.2,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 79 },
    cash_and_equivalents:   { value: 33.7,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 79 },
    accounts_receivable:    { value: 38.7,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 80 },
    inventory:              { value: 24.1,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 80 },
    goodwill:               { value: 15.2,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 81 },
    cfo:                    { value: 9.8,    unit: "亿元", period: "2025", source: "2025年年度报告", page: 86 },
    cfi:                    { value: -14.3,  unit: "亿元", period: "2025", source: "2025年年度报告", page: 86 },
    cff:                    { value: 5.2,    unit: "亿元", period: "2025", source: "2025年年度报告", page: 87 },
    rd_expense:             { value: 7.6,    unit: "亿元", period: "2025", source: "2025年年度报告", page: 85 },
    capex:                  { value: 16.9,   unit: "亿元", period: "2025", source: "2025年年度报告", page: 86 }
  },

  /* --------------------------------------------------------------------------
   * 2b. 主营构成（A 填写）—— 页面2「钱是从哪儿来的」
   * 结构：{ period, source, section, page, items: [{ name, revenue, unit, share, page }] }
   *   share  = **占营业收入的比例**，小数，0.62 = 62%（与全站百分数约定一致）
   *            ⚠️ E **不自己算 share**。占比会被当成结论读，不由前端推导。
   *            哪一项没给 share，那一项就只显示金额、不画条、不写百分数。
   *   items  按 A 给的顺序显示（通常是按收入降序），E 不重排 —— 排序规则
   *           属于口径，不是排版。用户想看别的顺序，让 A 换。
   * ------------------------------------------------------------------------*/
  business_mix: {
    period: "2025",
    source: "2025年年度报告",
    section: "第三节 管理层讨论与分析 · 主营业务分产品情况",
    page: 83,
    items: [
      { name: "输配电设备",   revenue: 79.7, unit: "亿元", share: 0.62, page: 83 },
      { name: "新能源设备",   revenue: 33.4, unit: "亿元", share: 0.26, page: 84 },
      { name: "智能电网系统", revenue: 15.5, unit: "亿元", share: 0.12, page: 84 }
    ]
  },

  /* --------------------------------------------------------------------------
   * 2c. 多期趋势（A 填写）—— 页面2「这几年是怎么长过来的」
   * 结构：{ unit, source, series: [{ key, name, values: [{ period, value, page }] }] }
   *   values 必须**按时间升序**给。E 不排序：期间是 "2023H1" 这种字符串时，
   *          按字符串排会把中期排到年末后面。顺序由 A 负责，合同里写死了。
   *   少于 2 个点的系列不是趋势，E 直接不画那一系列。
   *   ⚠️ E 只画**绝对值**，不画同比增速 —— 增速是 B 的 ratios.growth 的活。
   *      在图里标增速等于前端替 B 出了一版数据，越界。
   *
   * 数字必须与 B 的 ratios.growth 自洽：revenue_yoy = 0.184 要求
   * 2024 营收 = 128.6 / 1.184 = 108.6；net_income_yoy = 0.062 要求
   * 2024 归母净利润 = 11.4 / 1.062 = 10.73。下面这两个值就是这么定的 ——
   * 演示时若有人拿增长率反推，数字对得上。
   * （换真数据时这条自洽性由 A 保证，前端不做校验，只在这里留个记号。）
   * ------------------------------------------------------------------------*/
  history: {
    unit: "亿元",
    source: "2025年年度报告",
    series: [
      {
        key: "revenue", name: "营业收入",
        values: [
          { period: "2023", value: 95.0,  page: 40 },
          { period: "2024", value: 108.6, page: 60 },
          { period: "2025", value: 128.6, page: 82 }
        ]
      },
      {
        key: "net_income_attr", name: "归母净利润",
        values: [
          { period: "2023", value: 8.9,  page: 40 },
          { period: "2024", value: 10.73, page: 60 },
          { period: "2025", value: 11.4, page: 84 }
        ]
      }
    ]
  },

  /* --------------------------------------------------------------------------
   * 3. 财务指标（B 填写）
   * 统一结构：{ value, unit, formula, threshold, status }
   *   value      指标值
   *   unit       "%" | "倍" | "次"
   *   formula    公式（前端要展示"怎么算出来的"）
   *   threshold  判断阈值（原文，如 "> 15%"）
   *   status     B 的判断结论：good | watch | bad  → 前端只负责上色，不自己判断
   * ------------------------------------------------------------------------*/
  /* 注意：下面每个指标项**都没有 page 字段**（B 尚未提供）。
     后果：页面 3 指标名下那一行出处只能留空。这是刻意的 ——
     假数据要如实反映真实的数据缺口，否则「补齐后自动生效」这条路径
     在换真数据之前根本不会被验证到。见 docs/INTERFACE_CONTRACT.md 二·4。 */
  ratios: {
    growth: {
      revenue_yoy:      { name: "营业收入同比",   value: 0.184,  unit: "%", formula: "本期营收 / 上期营收 - 1", threshold: "> 0", status: "good" },
      net_income_yoy:   { name: "归母净利润同比", value: 0.062,  unit: "%", formula: "本期归母净利润 / 上期 - 1", threshold: "> 0", status: "watch" },
      ar_yoy:           { name: "应收账款同比",   value: 0.412,  unit: "%", formula: "本期应收账款 / 上期 - 1", threshold: "与收入增速比较", status: "bad" },
      _score: 62
    },
    profitability: {
      gross_margin:     { name: "毛利率",         value: 0.2675, unit: "%", formula: "(营收 - 营业成本) / 营收", threshold: "行业均值 24%", status: "good" },
      net_margin:       { name: "净利率",         value: 0.0886, unit: "%", formula: "归母净利润 / 营收", threshold: "行业均值 9%", status: "good" },
      roe:              { name: "净资产收益率 ROE", value: 0.1236, unit: "%", formula: "归母净利润 / 归母净资产", threshold: "> 10%", status: "good" },
      roa:              { name: "总资产收益率 ROA", value: 0.0542, unit: "%", formula: "归母净利润 / 总资产", threshold: "> 5%", status: "good" },
      _score: 78
    },
    solvency: {
      current_ratio:    { name: "流动比率",       value: 1.62,   unit: "倍", formula: "流动资产 / 流动负债", threshold: "> 1.5", status: "good" },
      quick_ratio:      { name: "速动比率",       value: 1.14,   unit: "倍", formula: "(流动资产 - 存货) / 流动负债", threshold: "> 1.0", status: "good" },
      debt_to_asset:    { name: "资产负债率",     value: 0.562,  unit: "%", formula: "总负债 / 总资产", threshold: "< 60%", status: "good" },
      interest_cover:   { name: "利息保障倍数",   value: 5.8,    unit: "倍", formula: "EBIT / 利息费用", threshold: "> 3", status: "good" },
      _score: 82
    },
    efficiency: {
      ar_turnover:      { name: "应收账款周转率", value: 3.32,   unit: "次", formula: "营收 / 平均应收账款", threshold: "> 4", status: "bad" },
      inventory_turnover: { name: "存货周转率",   value: 3.91,   unit: "次", formula: "营业成本 / 平均存货", threshold: "> 4", status: "watch" },
      asset_turnover:   { name: "总资产周转率",   value: 0.61,   unit: "次", formula: "营收 / 平均总资产", threshold: "> 0.5", status: "good" },
      _score: 55
    },
    cashflow_quality: {
      ocf_to_net_income: { name: "经营现金流 / 归母净利润", value: 0.86, unit: "倍", formula: "经营现金流 / 归母净利润", threshold: "> 1.0", status: "bad" },
      ocf_to_revenue:    { name: "经营现金流 / 营业收入",   value: 0.076, unit: "%", formula: "经营现金流 / 营收", threshold: "> 10%", status: "watch" },
      free_cash_flow:    { name: "自由现金流",              value: -7.1, unit: "亿元", formula: "经营现金流 - 资本开支", threshold: "> 0", status: "bad" },
      _score: 48
    }
  },

  /* --------------------------------------------------------------------------
   * 4. 风险（B 填写）—— 前端页面4 风险雷达 的核心数据
   * E 需要的四类内容：数据 → 计算 → 年报页码 → AI 解释
   * 对应字段：evidence → calculation → evidence[].page → explanation
   * 版面上合成三层节点（出处并进「数据与出处」层，见 docs/E_PAGE_SPEC.md）
   *
   * 【需要向 B 索要的字段】下面 calculation / explanation / suggestion
   * 是 E 单方面提出的需求，团队文档原示例只有 risk_name / trigger /
   * severity / evidence_required。必须在 INTERFACE_CONTRACT.md 里与 B 谈定。
   * ------------------------------------------------------------------------*/
  risks: [
    {
      risk_id: "R1",
      risk_name: "应收账款增速显著高于收入增速",
      severity: "high",                                   // high | attention | normal
      trigger: "AR growth - Revenue growth > 15%",        // B 的触发规则原文
      calculation: {
        formula: "应收账款增速 - 营业收入增速",
        inputs: { ar_yoy: 0.412, revenue_yoy: 0.184 },
        result: "22.8%",                                  // 展示用字符串
        threshold: "15%",
        triggered: true
      },
      evidence: [
        { metric: "应收账款", value: 38.7, unit: "亿元", period: "2025", source: "2025年年度报告", page: 80 },
        { metric: "营业收入", value: 128.6, unit: "亿元", period: "2025", source: "2025年年度报告", page: 82 }
      ],
      explanation: "公司应收账款增速达 41.2%，远超营业收入 18.4% 的增速，两者差值 22.8% 已越过 15% 警戒线。结合应收账款周转率 3.32 次（低于 4 次基准）判断，公司可能通过放宽信用政策刺激销售，收入质量存在下降风险，需关注后续回款情况及坏账计提是否充分。",
      suggestion: "建议核查前五大欠款方账龄结构与信用期变化，并对比同行业信用政策；若账龄结构恶化，需下调盈利质量评价。"
    },
    {
      risk_id: "R2",
      risk_name: "经营现金流与净利润背离",
      severity: "attention",
      trigger: "OCF / Net Income < 1.0",
      calculation: {
        formula: "经营活动现金流净额 / 归母净利润",
        inputs: { cfo: 9.8, net_income_attr: 11.4 },
        result: "0.86",
        threshold: "1.0",
        triggered: true
      },
      evidence: [
        { metric: "经营活动现金流净额", value: 9.8, unit: "亿元", period: "2025", source: "2025年年度报告", page: 86 },
        { metric: "归母净利润", value: 11.4, unit: "亿元", period: "2025", source: "2025年年度报告", page: 84 }
      ],
      explanation: "经营现金流净额 9.8 亿元低于归母净利润 11.4 亿元，比值 0.86 倍，说明账面利润未能完全转化为现金。叠加应收账款大幅增长，利润含金量偏低，存在通过赊销确认收入的可能。",
      suggestion: "建议结合 R1 一并评估；关注下一年度一季度回款情况，作为利润质量的验证窗口。"
    },
    {
      risk_id: "R3",
      risk_name: "商誉占净资产比例偏高",
      severity: "attention",
      trigger: "Goodwill / Equity > 15%",
      calculation: {
        formula: "商誉 / 归母净资产",
        inputs: { goodwill: 15.2, equity_attr: 92.2 },
        result: "16.5%",
        threshold: "15%",
        triggered: true
      },
      evidence: [
        { metric: "商誉", value: 15.2, unit: "亿元", period: "2025", source: "2025年年度报告", page: 81 },
        { metric: "归母净资产", value: 92.2, unit: "亿元", period: "2025", source: "2025年年度报告", page: 79 }
      ],
      explanation: "商誉 15.2 亿元占归母净资产 16.5%，超过 15% 关注线。若并购标的业绩不及预期，存在商誉减值风险，将直接侵蚀当期利润。",
      suggestion: "建议查阅年报商誉减值测试章节，核对标的公司业绩承诺完成率。"
    }
  ],

  /* --------------------------------------------------------------------------
   * 5. 估值（C 填写）
   * ------------------------------------------------------------------------*/
  valuation: {
    comps: {
      peers: [
        { name: "可比公司A", ticker: "PEER1.SH", pe: 19.8, pb: 2.6, ev_ebitda: 12.4 },
        { name: "可比公司B", ticker: "PEER2.SH", pe: 24.1, pb: 3.1, ev_ebitda: 14.8 },
        { name: "可比公司C", ticker: "PEER3.SH", pe: 16.9, pb: 2.2, ev_ebitda: 10.7 }
      ],
      target: { eps: 0.86, net_income: 11.4, shares_outstanding: 13.25 },
      range: { low: 15.8, mid: 20.1, high: 24.6, unit: "元/股" },
      conclusion: "基于可比公司 PE 中枢 20.2 倍，给予目标公司合理估值区间 15.8–24.6 元/股。"
    },
    dcf: {
      assumptions: {
        wacc: 0.095,
        terminal_growth: 0.025,
        forecast_years: 5,
        tax_rate: 0.15
      },
      range: { low: 14.2, mid: 18.9, high: 23.5, unit: "元/股" },
      conclusion: "以 WACC 9.5%、永续增长率 2.5% 测算，DCF 合理价值中枢 18.9 元/股。"
    }
  },

  /* --------------------------------------------------------------------------
   * 6. 数据来源（A 填写）
   * 前端用途：全站"查看出处"的兜底索引；风险卡片点击页码时跳转/弹窗
   * ------------------------------------------------------------------------*/
  sources: [
    { source_id: "S1", metric: "营业收入",   source: "2025年年度报告", section: "第三节 管理层讨论与分析", page: 82 },
    { source_id: "S2", metric: "归母净利润", source: "2025年年度报告", section: "第二节 公司简介和主要财务指标", page: 84 },
    { source_id: "S3", metric: "应收账款",   source: "2025年年度报告", section: "第十节 财务报告", page: 80 },
    { source_id: "S4", metric: "经营活动现金流净额", source: "2025年年度报告", section: "第十节 财务报告", page: 86 },
    { source_id: "S5", metric: "商誉",       source: "2025年年度报告", section: "第十节 财务报告", page: 81 },
    { source_id: "S6", metric: "归母净资产", source: "2025年年度报告", section: "第十节 财务报告", page: 79 }
  ]
};
