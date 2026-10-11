# FinScope 统一数据接口 Schema

本文件是 D 部分交付的统一数据接口说明。配套文件 `data_schema.json` 是填好示例值的完整对象，A/B/C 按它的格式交数据，E 只读、不重算。

## 1. 这份接口是干什么的

FinScope 的链路是「上传年报 → 财报抽取 → 指标计算与风险诊断 → 估值 → 投研报告」。五个角色各自产出 JSON，最后汇成同一个数据对象，交给 E 渲染页面。

这份 Schema 定死一件事。全组只认一个顶层对象，A/B/C 各填自己的字段，E 按字段渲染。字段名一旦定下，谁都不改。

顶层结构固定为六个键，不增不减。

```
company / financials / ratios / risks / valuation / sources
```

## 2. 谁填哪块

| 顶层字段 | 负责人 | 说明 |
|---|---|---|
| company | D 定义，A 补全 | D 定字段名，A 从年报首页与公司简介填入公司基本信息 |
| financials | A | 三表与关键科目的数值，带口径与页码 |
| ratios | B | 五类财务指标，用公式从 financials 算出 |
| risks | B | 风险卡片列表，每条带证据与页码 |
| valuation.comps、valuation.dcf | C | 相对估值与绝对估值，输入取自 financials 和 ratios |
| sources | A 归集 | 每条引用对应的文件名、页码、获取时间 |
| 全字段 | E 只读 | 不重算，不新增派生字段 |

## 3. 全局约定

### 3.1 单位与数值

- 财报数据一律折算到「百万元」再入库，币种由 company.currency 表示。示例 18650 表示 186.5 亿元，美股公司则读作 186.5 百万美元。数量级固定为百万，不随公司规模变。
- 每一条金额记录都要带 unit 字段，不允许只写数字不写单位。
- 百分数类比率（各类 margin、增长率、占比）一律用百分数数值，不带百分号，并保留一位小数。示例 28.5 表示 28.5%。这一条最容易被写错，B 和 C 必须遵守。
- 数值精度按数据本身来。原数超过两位小数时四舍五入到两位，原数只有一位小数或没有小数时保持原样，不补零。示例 1.82 保留两位，112.5 保留一位，18650 保持整数。
- 倍、次、天等写在 unit 字段里，如 `"unit": "倍"`、`"unit": "天"`。这类数值按数据本身精度，最多两位小数。
- 股本用「百万股」，与金额的百万元配对。这样 市值(百万元) ÷ 股本(百万股) = 每股价值(元)，中间不用换算。
- 每股价值、股价用「元/股」或对应币种的每股单位，与金额的数量级无关。
- 图表与前端展示由 E 自适应。金额到亿元量级显示亿元，到百万量级显示百万元，美元同理显示亿美元或百万美元。图上和表头都必须标出单位。
- 负值直接写负数，投资活动现金流、自由现金流可能为负。示例 -1850、-160。

### 3.2 口径字段取值

每个 financials 记录必须带口径，缺失即视为无效记录。三个口径字段的取值范围固定。

| 字段 | 取值 | 说明 |
|---|---|---|
| scope | 合并报表、母公司报表 | 同一指标优先取合并口径 |
| basis | 累计数、单季数、期末数 | 利润表与现金流量表用累计数或单季数，资产负债表用期末数 |

### 3.3 空值与未产出

下游要能分清「没有」和「是零」。约定如下。

| 情况 | 写法 | 例子 |
|---|---|---|
| 该模块未产出 | 空对象 `{}` 或空数组 `[]` | C 没做 DCF，则 `"dcf": {}` |
| 该字段不适用 | `null` | 亏损公司算不出 PE，则相应倍数为 `null` |
| 缺失、未抽到 | 数值字段留 `null`，并在 confidence 或说明里标注 | `"value": null` |
| 抽取到的真实零值 | 写 `0` | 某科目确实为零，写 `0` |
| 数值超范围或为负导致指标失真 | 指标 value 写 `null`，在 formula 旁注明原因 | 上年净利润为负，增速写 `null` |

记住一条。`null` 是不知道，`0` 是确定为零。不要把不知道写成 0。

### 3.4 字段命名

- 一律英文小写下划线，如 `net_income_parent`。
- 全文件前后一致，同一含义不出现两个名字。归母净利润固定写 `net_income_parent`，不再写 `net_profit` 或 `net_income`。
- 财务科目名以 `financials` 下的键为准，`ratios` 的 formula 里引用的就是这些键名，两边必须同名。

## 4. 完整 JSON 示例

下面这份示例与 `data_schema.json` 完全一致，可直接对照。示例公司为虚构的「恒锐精密制造股份有限公司」，报告期 2025 年。

数字经过自洽校验，三处勾稽成立。

- 资产总计 26800 = 负债合计 11260 + 所有者权益合计 15540
- 货币资金 4270 + 经营 1520 + 投资 -1850 + 筹资 210 = 4150，与期末货币资金一致
- 毛利率 28.5% 由营业收入 18650 与营业成本 13340 算出

```json
{
  "company": {
    "name": "恒锐精密制造股份有限公司",
    "ticker": "688123.SH",
    "industry": "高端装备制造",
    "report_period": "2025",
    "exchange": "上海证券交易所科创板",
    "report_type": "年度报告",
    "auditor": "华信会计师事务所（特殊普通合伙）",
    "audit_opinion": "标准无保留意见",
    "currency": "CNY",
    "amount_unit": "百万元"
  },

  "financials": {
    "revenue": {
      "value": 18650, "unit": "百万元", "period": "2025",
      "prior_value": 16800, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 82,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "operating_cost": {
      "value": 13340, "unit": "百万元", "period": "2025",
      "prior_value": 12180, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 82,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "selling_expense": {
      "value": 1120, "unit": "百万元", "period": "2025",
      "prior_value": 1040, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 84,
      "source": "2025年年度报告", "confidence": 0.97
    },
    "admin_expense": {
      "value": 840, "unit": "百万元", "period": "2025",
      "prior_value": 760, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 84,
      "source": "2025年年度报告", "confidence": 0.97
    },
    "rnd_expense": {
      "value": 980, "unit": "百万元", "period": "2025",
      "prior_value": 820, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 85,
      "source": "2025年年度报告", "confidence": 0.96
    },
    "operating_profit": {
      "value": 2210, "unit": "百万元", "period": "2025",
      "prior_value": 1940, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 86,
      "source": "2025年年度报告", "confidence": 0.97
    },
    "net_income_parent": {
      "value": 1580, "unit": "百万元", "period": "2025",
      "prior_value": 1320, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 87,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "net_income_excl_nonrecurring": {
      "value": 1360, "unit": "百万元", "period": "2025",
      "prior_value": 1100, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 88,
      "source": "2025年年度报告（主要会计数据）", "confidence": 0.95
    },
    "total_assets": {
      "value": 26800, "unit": "百万元", "period": "2025",
      "prior_value": 24600, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 60,
      "source": "2025年年度报告", "confidence": 0.99
    },
    "current_assets": {
      "value": 16800, "unit": "百万元", "period": "2025",
      "prior_value": 15200, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 60,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "total_liabilities": {
      "value": 11260, "unit": "百万元", "period": "2025",
      "prior_value": 10340, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 61,
      "source": "2025年年度报告", "confidence": 0.99
    },
    "current_liabilities": {
      "value": 9250, "unit": "百万元", "period": "2025",
      "prior_value": 8600, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 61,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "equity_parent": {
      "value": 15540, "unit": "百万元", "period": "2025",
      "prior_value": 14260, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 62,
      "source": "2025年年度报告", "confidence": 0.99
    },
    "cash_and_equivalents": {
      "value": 4150, "unit": "百万元", "period": "2025",
      "prior_value": 4270, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 60,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "accounts_receivable": {
      "value": 3860, "unit": "百万元", "period": "2025",
      "prior_value": 3050, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 60,
      "source": "2025年年度报告", "confidence": 0.97
    },
    "inventory": {
      "value": 4420, "unit": "百万元", "period": "2025",
      "prior_value": 3800, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 60,
      "source": "2025年年度报告", "confidence": 0.97
    },
    "accounts_payable": {
      "value": 3350, "unit": "百万元", "period": "2025",
      "prior_value": 2900, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 61,
      "source": "2025年年度报告", "confidence": 0.97
    },
    "goodwill": {
      "value": 1280, "unit": "百万元", "period": "2025",
      "prior_value": 1280, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 63,
      "source": "2025年年度报告（附注）", "confidence": 0.95
    },
    "interest_bearing_debt": {
      "value": 6050, "unit": "百万元", "period": "2025",
      "prior_value": 5400, "prior_period": "2024",
      "scope": "合并报表", "basis": "期末数", "page": 64,
      "source": "2025年年度报告（借款附注汇总）", "confidence": 0.92
    },
    "capex": {
      "value": 1680, "unit": "百万元", "period": "2025",
      "prior_value": 1400, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 70,
      "source": "2025年年度报告", "confidence": 0.96
    },
    "depreciation_amortization": {
      "value": 1200, "unit": "百万元", "period": "2025",
      "prior_value": 1100, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 71,
      "source": "2025年年度报告（附注）", "confidence": 0.93
    },
    "cfo": {
      "value": 1520, "unit": "百万元", "period": "2025",
      "prior_value": 1650, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 68,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "cfi": {
      "value": -1850, "unit": "百万元", "period": "2025",
      "prior_value": -1580, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 69,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "cff": {
      "value": 210, "unit": "百万元", "period": "2025",
      "prior_value": 150, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 70,
      "source": "2025年年度报告", "confidence": 0.98
    },
    "cash_received_from_sales": {
      "value": 20500, "unit": "百万元", "period": "2025",
      "prior_value": 18200, "prior_period": "2024",
      "scope": "合并报表", "basis": "累计数", "page": 68,
      "source": "2025年年度报告", "confidence": 0.97
    }
  },

  "ratios": {
    "growth": {
      "revenue_growth_yoy": {
        "value": 11.0, "unit": "%", "period": "2025",
        "formula": "revenue / prior_revenue - 1", "page": 82
      },
      "net_income_growth_yoy": {
        "value": 19.7, "unit": "%", "period": "2025",
        "formula": "net_income_parent / prior_net_income_parent - 1", "page": 87
      },
      "net_income_excl_nonrecurring_growth_yoy": {
        "value": 23.6, "unit": "%", "period": "2025",
        "formula": "net_income_excl_nonrecurring / prior_net_income_excl_nonrecurring - 1", "page": 88
      },
      "revenue_cagr_3y": {
        "value": 7.7, "unit": "%", "period": "2025",
        "formula": "(revenue / revenue_2023) ^ (1/3) - 1", "page": 32
      }
    },
    "profitability": {
      "gross_margin": {
        "value": 28.5, "unit": "%", "period": "2025",
        "formula": "(revenue - operating_cost) / revenue", "page": 82
      },
      "operating_margin": {
        "value": 11.8, "unit": "%", "period": "2025",
        "formula": "operating_profit / revenue", "page": 86
      },
      "net_margin": {
        "value": 8.5, "unit": "%", "period": "2025",
        "formula": "net_income_parent / revenue", "page": 87
      },
      "roe_weighted": {
        "value": 10.6, "unit": "%", "period": "2025",
        "formula": "net_income_parent / ((equity_parent_begin + equity_parent_end) / 2)", "page": 62
      },
      "roa": {
        "value": 6.1, "unit": "%", "period": "2025",
        "formula": "net_income_parent / ((total_assets_begin + total_assets_end) / 2)", "page": 60
      },
      "roic": {
        "value": 8.3, "unit": "%", "period": "2025",
        "formula": "operating_profit * (1 - tax_rate) / (interest_bearing_debt + equity_parent)", "page": 32
      },
      "ebitda_margin": {
        "value": 18.3, "unit": "%", "period": "2025",
        "formula": "(operating_profit + depreciation_amortization) / revenue", "page": 32
      }
    },
    "solvency": {
      "debt_to_asset_ratio": {
        "value": 42.0, "unit": "%", "period": "2025",
        "formula": "total_liabilities / total_assets", "page": 61
      },
      "interest_bearing_debt_ratio": {
        "value": 22.6, "unit": "%", "period": "2025",
        "formula": "interest_bearing_debt / total_assets", "page": 64
      },
      "net_debt_to_ebitda": {
        "value": 0.56, "unit": "倍", "period": "2025",
        "formula": "(interest_bearing_debt - cash_and_equivalents) / (operating_profit + depreciation_amortization)", "page": 64
      },
      "current_ratio": {
        "value": 1.82, "unit": "倍", "period": "2025",
        "formula": "current_assets / current_liabilities", "page": 60
      },
      "quick_ratio": {
        "value": 1.34, "unit": "倍", "period": "2025",
        "formula": "(current_assets - inventory) / current_liabilities", "page": 60
      }
    },
    "efficiency": {
      "ar_turnover_days": {
        "value": 67.6, "unit": "天", "period": "2025",
        "formula": "((accounts_receivable_begin + accounts_receivable_end) / 2) / revenue * 365", "page": 60
      },
      "inventory_turnover_days": {
        "value": 112.5, "unit": "天", "period": "2025",
        "formula": "((inventory_begin + inventory_end) / 2) / operating_cost * 365", "page": 60
      },
      "payable_turnover_days": {
        "value": 85.5, "unit": "天", "period": "2025",
        "formula": "((accounts_payable_begin + accounts_payable_end) / 2) / operating_cost * 365", "page": 61
      },
      "cash_conversion_cycle": {
        "value": 94.6, "unit": "天", "period": "2025",
        "formula": "ar_turnover_days + inventory_turnover_days - payable_turnover_days", "page": 60
      },
      "total_asset_turnover": {
        "value": 0.73, "unit": "次", "period": "2025",
        "formula": "revenue / ((total_assets_begin + total_assets_end) / 2)", "page": 60
      }
    },
    "cashflow_quality": {
      "cfo_to_net_income": {
        "value": 0.96, "unit": "倍", "period": "2025",
        "formula": "cfo / net_income_parent", "page": 68
      },
      "cash_collection_ratio": {
        "value": 1.10, "unit": "倍", "period": "2025",
        "formula": "cash_received_from_sales / revenue", "page": 68
      },
      "free_cash_flow": {
        "value": -160, "unit": "百万元", "period": "2025",
        "formula": "cfo - capex", "page": 68
      },
      "capex_to_da_ratio": {
        "value": 1.40, "unit": "倍", "period": "2025",
        "formula": "capex / depreciation_amortization", "page": 70
      }
    }
  },

  "risks": [
    {
      "risk_id": "R01",
      "risk_name": "应收账款增速快于营业收入增速",
      "category": "收入与资产",
      "severity": "medium",
      "trigger": "应收账款增速 - 营业收入增速 > 10 个百分点",
      "involved_values": [
        { "metric": "accounts_receivable", "value": 3860, "unit": "百万元", "period": "2025", "page": 60 },
        { "metric": "accounts_receivable", "value": 3050, "unit": "百万元", "period": "2024", "page": 60 },
        { "metric": "revenue_growth_yoy", "value": 11.0, "unit": "%", "period": "2025", "page": 82 }
      ],
      "numeric_evidence": "应收账款由 3050 百万元增至 3860 百万元，增速 26.6%；营业收入增速 11.0%，相差 15.6 个百分点，超过 10 个百分点阈值。",
      "text_evidence": { "quote": "报告期内公司适度放宽了部分战略客户的信用账期。", "page": 45 },
      "explanation": "应收增速显著高于收入增速，可能通过放宽信用政策换取收入增长，也可能是收入确认节奏前移，需结合账龄与坏账计提判断回款质量。",
      "suggested_action": "核对应收账款账龄结构附注与前五大欠款方，比较信用政策是否变化。"
    },
    {
      "risk_id": "R02",
      "risk_name": "存货周转天数上行且高于同业",
      "category": "收入与资产",
      "severity": "low",
      "trigger": "存货周转天数连续两期上行，且高于同业中位数",
      "involved_values": [
        { "metric": "inventory_turnover_days", "value": 112.5, "unit": "天", "period": "2025", "page": 60 },
        { "metric": "inventory_turnover_days", "value": 109.4, "unit": "天", "period": "2024", "page": 60 }
      ],
      "numeric_evidence": "存货周转天数由 109.4 天升至 112.5 天，同业中位数约 95 天，偏高约 17 天。",
      "text_evidence": { "quote": "受下游需求波动影响，部分在产品备货周期有所拉长。", "page": 47 },
      "explanation": "库存周转放缓叠加高于同业，可能指向需求走弱或产品滞销。当前幅度有限，列为观察项。",
      "suggested_action": "核对存货构成与跌价准备计提，结合在手订单判断是否存在积压。"
    },
    {
      "risk_id": "R03",
      "risk_name": "控股股东股权质押比例偏高",
      "category": "治理与合规",
      "severity": "medium",
      "trigger": "控股股东质押股份占其持股比例超过 50%",
      "involved_values": [
        { "metric": "pledge_ratio", "value": 58.0, "unit": "%", "period": "2025", "page": 51 }
      ],
      "numeric_evidence": "控股股东累计质押 1.05 亿股，占其所持 1.81 亿股的 58.0%，超过 50% 观察线。",
      "text_evidence": { "quote": "截至报告期末，控股股东已质押股份 1.05 亿股，占其所持股份的 58.0%。", "page": 51 },
      "explanation": "高比例质押在股价波动时可能引发控制权稳定风险，属治理类信号，与当期财务数字无关但影响风险评级。",
      "suggested_action": "跟踪质押平仓线与控股股东资金用途披露。"
    }
  ],

  "valuation": {
    "comps": {
      "inputs": {
        "revenue": 18650,
        "net_income": 1580,
        "ebitda": 3410,
        "net_debt": 1900,
        "share_price": 16.50,
        "shares_outstanding": 2200.0,
        "shares_unit": "百万股",
        "market_cap": 36300,
        "currency": "CNY"
      },
      "peer_companies": [
        { "name": "锐科装备", "ticker": "002xxx.SZ", "pe": 20.5, "pb": 2.1, "ev_ebitda": 11.0, "ps": 1.9 },
        { "name": "精工制造", "ticker": "300xxx.SZ", "pe": 24.0, "pb": 2.6, "ev_ebitda": 13.2, "ps": 2.3 },
        { "name": "恒达智造", "ticker": "600xxx.SH", "pe": 18.0, "pb": 1.9, "ev_ebitda": 9.8, "ps": 1.6 }
      ],
      "peer_multiples": {
        "pe": { "min": 18.0, "median": 20.5, "max": 24.0 },
        "pb": { "min": 1.9, "median": 2.1, "max": 2.6 },
        "ev_ebitda": { "min": 9.8, "median": 11.0, "max": 13.2 },
        "ps": { "min": 1.6, "median": 1.9, "max": 2.3 }
      },
      "implied_value_per_share": {
        "pe": { "low": 12.9, "mid": 14.7, "high": 17.2 },
        "pb": { "low": 13.4, "mid": 14.8, "high": 18.4 },
        "ev_ebitda": { "low": 14.3, "mid": 16.2, "high": 19.6 },
        "ps": { "low": 13.6, "mid": 16.1, "high": 19.5 }
      },
      "valuation_range": { "low": 12.9, "mid": 15.5, "high": 19.6, "currency": "元/股" }
    },
    "dcf": {
      "inputs": {
        "revenue_base": 18650,
        "ebit_margin": 11.9,
        "tax_rate": 19.0,
        "da": 1200,
        "capex": 1680,
        "nwc": 4930,
        "wacc": 8.0,
        "terminal_growth": 3.0,
        "forecast_years": 5
      },
      "forecast": [
        { "year": 2026, "revenue": 20140, "ebit": 2400, "fcff": 1400 },
        { "year": 2027, "revenue": 21550, "ebit": 2560, "fcff": 1520 },
        { "year": 2028, "revenue": 22850, "ebit": 2720, "fcff": 1640 },
        { "year": 2029, "revenue": 23990, "ebit": 2850, "fcff": 1760 },
        { "year": 2030, "revenue": 24950, "ebit": 2970, "fcff": 1860 }
      ],
      "terminal_assumptions": {
        "terminal_growth": 3.0,
        "terminal_fcff": 1860,
        "terminal_value": 38320,
        "pv_terminal_value": 26080,
        "tv_pct_of_ev": 80.2,
        "wacc": 8.0
      },
      "valuation_range": { "low": 11.7, "mid": 13.9, "high": 17.4, "currency": "元/股" },
      "sensitivity": {
        "metric": "value_per_share",
        "unit": "元/股",
        "wacc_values": [7.5, 8.0, 8.5],
        "terminal_growth_values": [2.5, 3.0, 3.5],
        "matrix": [
          [14.2, 15.6, 17.4],
          [12.8, 13.9, 15.3],
          [11.7, 12.6, 13.7]
        ]
      }
    }
  },

  "sources": [
    {
      "company_name": "恒锐精密制造股份有限公司",
      "report_period": "2025",
      "file_name": "恒锐精密_2025年年度报告.pdf",
      "page": 60,
      "retrieved_at": "2026-10-05T14:20:00+08:00",
      "source_url": "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=688123"
    },
    {
      "company_name": "恒锐精密制造股份有限公司",
      "report_period": "2025",
      "file_name": "恒锐精密_2025年年度报告.pdf",
      "page": 82,
      "retrieved_at": "2026-10-05T14:20:00+08:00",
      "source_url": "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=688123"
    },
    {
      "company_name": "恒锐精密制造股份有限公司",
      "report_period": "2025",
      "file_name": "恒锐精密_2025年年度报告.pdf",
      "page": 68,
      "retrieved_at": "2026-10-05T14:20:00+08:00",
      "source_url": "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=688123"
    },
    {
      "company_name": "恒锐精密制造股份有限公司",
      "report_period": "2025",
      "file_name": "恒锐精密_2025年年度报告.pdf",
      "page": 45,
      "retrieved_at": "2026-10-05T14:20:00+08:00",
      "source_url": "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=688123"
    },
    {
      "company_name": "恒锐精密制造股份有限公司",
      "report_period": "2025",
      "file_name": "恒锐精密_2025年年度报告.pdf",
      "page": 51,
      "retrieved_at": "2026-10-05T14:20:00+08:00",
      "source_url": "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=688123"
    }
  ]
}

```

## 5. 逐字段说明

### 5.1 company（D 定义，A 补全）

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| name | string | A | 恒锐精密制造股份有限公司 | 公司全称 |
| ticker | string | A | 688123.SH | 证券代码加交易所后缀 |
| industry | string | A | 高端装备制造 | 行业归属，同业对比用 |
| report_period | string | A | 2025 | 报告期年份，也用于 E 的页面标题 |
| exchange | string | A | 上海证券交易所科创板 | 上市地 |
| report_type | string | A | 年度报告 | 文件类型 |
| auditor | string | A | 华信会计师事务所（特殊普通合伙） | 审计机构 |
| audit_opinion | string | A | 标准无保留意见 | 审计意见类型，非标准意见要触发风险 |
| currency | string | D | CNY | 币种，按年报实际使用的货币填，取值 CNY / USD / HKD。美股公司填 USD，报表可能是英文的 |
| amount_unit | string | D | 百万元 | 金额数量级，固定「百万元」。USD 币种时读作 百万美元，HKD 时读作 百万港元 |

### 5.2 financials 记录的字段（A 填）

`financials` 是一个对象。键是科目名，值是记录对象。A 抽到的每个科目按下面这十个字段交。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| value | number \| null | A | 18650 | 本期数值，单位见 unit。抽不到填 null |
| unit | string | A | 百万元 | 金额科目固定「百万元」，全组一致 |
| period | string | A | 2025 | 数值所属期间 |
| prior_value | number \| null | A | 16800 | 上期数值，供 B 算同比。不需要则 null |
| prior_period | string \| null | A | 2024 | 上期期间，配合 prior_value |
| scope | string | A | 合并报表 | 合并报表或母公司报表，必填 |
| basis | string | A | 累计数 | 累计数、单季数、期末数，必填 |
| page | integer | A | 82 | 年报原始页码，可追溯的锚点 |
| source | string | A | 2025年年度报告 | 文件名或章节，写明出处 |
| confidence | number | A | 0.98 | 0 到 1 的抽取置信度，低于阈值进核验队列 |

### 5.3 financials 科目清单（A 的抽取范围，25 个）

| 键名 | 含义 | 示例值（百万元） | 设计文档口径来源 |
|---|---|---|---|
| revenue | 营业收入 | 18650 | 附录 A 毛利率、各增速 |
| operating_cost | 营业成本 | 13340 | 附录 A 毛利率、存货周转 |
| selling_expense | 销售费用 | 1120 | 费用率分析 |
| admin_expense | 管理费用 | 840 | 费用率分析 |
| rnd_expense | 研发费用 | 980 | 附录 A 研发费用率 |
| operating_profit | 营业利润 | 2210 | 附录 A 营业利润率、EBIT |
| net_income_parent | 归母净利润 | 1580 | 附录 A 净利率、ROE、ROA |
| net_income_excl_nonrecurring | 扣非净利润 | 1360 | 附录 A 扣非净利润增速 |
| total_assets | 总资产 | 26800 | 附录 A ROA、资产负债率 |
| current_assets | 流动资产 | 16800 | 附录 A 流动比率 |
| total_liabilities | 负债合计 | 11260 | 附录 A 资产负债率 |
| current_liabilities | 流动负债 | 9250 | 附录 A 流动比率 |
| equity_parent | 归母净资产 | 15540 | 附录 A ROE、商誉占净资产 |
| cash_and_equivalents | 货币资金 | 4150 | 附录 A 净负债与 EBITDA |
| accounts_receivable | 应收账款 | 3860 | 附录 A 应收账款周转天数 |
| inventory | 存货 | 4420 | 附录 A 存货周转天数 |
| accounts_payable | 应付账款 | 3350 | 附录 A 现金转换周期 |
| goodwill | 商誉 | 1280 | 附录 A 商誉占净资产比重 |
| interest_bearing_debt | 有息负债 | 6050 | 附录 A ROIC、净负债与 EBITDA |
| capex | 资本开支 | 1680 | 附录 A 自由现金流、资本开支与折旧摊销之比 |
| depreciation_amortization | 折旧与摊销 | 1200 | 附录 A EBITDA、资本开支比 |
| cfo | 经营活动现金流量净额 | 1520 | 附录 A 经营现金流与净利润之比 |
| cfi | 投资活动现金流量净额 | -1850 | 现金流量表三分类 |
| cff | 筹资活动现金流量净额 | 210 | 现金流量表三分类 |
| cash_received_from_sales | 销售商品、提供劳务收到的现金 | 20500 | 附录 A 收现比 |

### 5.4 ratios（B 填）

按五类组织，与设计文档 4.8 节的指标分组一致。每类是一个对象，键是指标名，值是记录对象。

指标记录的字段。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| value | number \| null | B | 28.5 | 百分数指标写数值不带百分号。分母为零或失真填 null |
| unit | string | B | % | %、倍、天、次、百万元 |
| period | string | B | 2025 | 计算所属期间 |
| formula | string | B | (revenue - operating_cost) / revenue | 计算式，引用的名字必须与 financials 的键同名 |
| page | integer | B | 82 | 主要输入所在的年报页码 |

五类指标与示例值。

| 类别 | 指标键 | 示例值 | 单位 |
|---|---|---|---|
| growth | revenue_growth_yoy | 11.0 | % |
| growth | net_income_growth_yoy | 19.7 | % |
| growth | net_income_excl_nonrecurring_growth_yoy | 23.6 | % |
| growth | revenue_cagr_3y | 7.7 | % |
| profitability | gross_margin | 28.5 | % |
| profitability | operating_margin | 11.8 | % |
| profitability | net_margin | 8.5 | % |
| profitability | roe_weighted | 10.6 | % |
| profitability | roa | 6.1 | % |
| profitability | roic | 8.3 | % |
| profitability | ebitda_margin | 18.3 | % |
| solvency | debt_to_asset_ratio | 42.0 | % |
| solvency | interest_bearing_debt_ratio | 22.6 | % |
| solvency | net_debt_to_ebitda | 0.56 | 倍 |
| solvency | current_ratio | 1.82 | 倍 |
| solvency | quick_ratio | 1.34 | 倍 |
| efficiency | ar_turnover_days | 67.6 | 天 |
| efficiency | inventory_turnover_days | 112.5 | 天 |
| efficiency | payable_turnover_days | 85.5 | 天 |
| efficiency | cash_conversion_cycle | 94.6 | 天 |
| efficiency | total_asset_turnover | 0.73 | 次 |
| cashflow_quality | cfo_to_net_income | 0.96 | 倍 |
| cashflow_quality | cash_collection_ratio | 1.10 | 倍 |
| cashflow_quality | free_cash_flow | -160 | 百万元 |
| cashflow_quality | capex_to_da_ratio | 1.40 | 倍 |

`free_cash_flow` 是金额，写百万元，其余四类都是比率。B 若按设计文档扩展更多指标，直接在该类别下加键，字段格式不变。

### 5.5 risks（B 填）

`risks` 是数组，每条是一张风险卡片，字段对应设计文档 4.9 节的风险卡结构。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| risk_id | string | B | R01 | 卡片编号，同一次分析内唯一 |
| risk_name | string | B | 应收账款增速快于营业收入增速 | 风险简称 |
| category | string | B | 收入与资产 | 取值见附录 B 分类，如盈利质量、收入与资产、偿债与流动性、治理与合规、会计政策、审计与披露 |
| severity | string | B | medium | 等级，取 high、medium、low 三值 |
| trigger | string | B | 应收账款增速 - 营业收入增速 > 10 个百分点 | 触发条件原文 |
| involved_values | array | B | 见示例 | 涉及数值列表，每项含 metric、value、unit、period、page |
| numeric_evidence | string | B | 应收账款由 3050 百万元增至 3860 百万元…… | 数字证据，一句话说清算式与结果 |
| text_evidence | object | B | {"quote": "...", "page": 45} | 文本证据，含原文片段与页码。未找到管理层解释时 quote 写 null |
| explanation | string | B | 应收增速显著高于收入增速…… | 解释说明。区分事实与推断 |
| suggested_action | string | B | 核对应收账款账龄结构附注…… | 建议核查动作 |

`severity` 三值对应中文含义。high 高，medium 中，low 低或观察项。E 按等级排序渲染。

### 5.6 valuation.comps（C 填）

相对估值。输入取自 financials，输出估值区间与可比公司区间。

输入字段。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| revenue | number | C | 18650 | 营业收入，来自 financials.revenue |
| net_income | number | C | 1580 | 归母净利润，来自 financials.net_income_parent |
| ebitda | number | C | 3410 | 息税折旧摊销前利润，由营业利润加折旧摊销得来 |
| net_debt | number | C | 1900 | 净负债，有息负债减货币资金 |
| share_price | number | C | 16.50 | 评估日收盘价，元 |
| shares_outstanding | number | C | 2200.0 | 总股本，单位见 shares_unit |
| shares_unit | string | C | 百万股 | 股本数量级，固定「百万股」，与金额的百万元配对 |
| market_cap | number | C | 36300 | 总市值，百万元，等于股价乘股本 |
| currency | string | C | CNY | 币种 |

输出字段。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| peer_companies | array | C | 见示例 | 可比公司，每家含 name、ticker、pe、pb、ev_ebitda、ps |
| peer_multiples | object | C | 见示例 | 可比公司倍数的区间，键为 pe、pb、ev_ebitda、ps，每个含 min、median、max |
| implied_value_per_share | object | C | 见示例 | 各方法推出的每股价值，每个含 low、mid、high |
| valuation_range | object | C | {low, mid, high} | 综合每股估值区间，含 currency，单位元每股 |

`peer_multiples` 是「可比公司区间」，`valuation_range` 是本公司的估值区间，两者都要给。

### 5.7 valuation.dcf（C 填）

绝对估值。输入按分工说明的 DCF 清单，输出估值区间、终值假设与敏感性矩阵。

输入字段。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| revenue_base | number | C | 18650 | 预测起点营业收入 |
| ebit_margin | number | C | 11.9 | 息税前利润率，百分数数值 |
| tax_rate | number | C | 19.0 | 所得税率，百分数数值 |
| da | number | C | 1200 | 折旧与摊销 |
| capex | number | C | 1680 | 资本开支 |
| nwc | number | C | 4930 | 净营运资本，应收加存货减应付 |
| wacc | number | C | 8.0 | 加权平均资本成本，百分数数值 |
| terminal_growth | number | C | 3.0 | 永续增长率，百分数数值 |
| forecast_years | integer | C | 5 | 明确预测期年数 |

输出字段。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| forecast | array | C | 见示例 | 预测期逐年，每项含 year、revenue、ebit、fcff |
| terminal_assumptions | object | C | 见示例 | 终值假设，含 terminal_growth、terminal_fcff、terminal_value、pv_terminal_value、tv_pct_of_ev、wacc |
| valuation_range | object | C | {low, mid, high} | 每股估值区间，含 currency |
| sensitivity | object | C | 见示例 | 敏感性，含 metric、unit、wacc_values、terminal_growth_values、matrix |

`sensitivity.matrix` 的行对应 wacc_values，列对应 terminal_growth_values。示例里 wacc 8.0% 与终值增长 3.0% 交叉得到 13.9 元每股，与 valuation_range.mid 对齐。

### 5.8 sources（A 归集）

`sources` 是数组，每条对应一个被引用的文件页。

| 字段名 | 类型 | 谁填 | 示例 | 说明 |
|---|---|---|---|---|
| company_name | string | A | 恒锐精密制造股份有限公司 | 公司全称 |
| report_period | string | A | 2025 | 报告期 |
| file_name | string | A | 恒锐精密_2025年年度报告.pdf | 原始文件名 |
| page | integer | A | 60 | 被引用的页码 |
| retrieved_at | string | A | 2026-10-05T14:20:00+08:00 | 获取时间，ISO 8601 带时区 |
| source_url | string | A | http://www.cninfo.com.cn/... | 来源链接，本地文件留 null |

不同页码要写不同条目。同一次分析里被引用多少次页，就写多少条。

## 6. 各模块输入输出约定

链路按分工说明第五节的顺序走，每一步的输出是下一步的输入。统一对象在链路上只增字段，不换字段名。

| 步骤 | 谁做 | 读什么 | 写什么 |
|---|---|---|---|
| 财报抽取 | A | 年报 PDF | company（补全基本信息）、financials、sources |
| 指标计算 | B | financials | ratios |
| 风险诊断 | B | financials、ratios | risks |
| 相对估值 | C | financials、ratios、company | valuation.comps |
| 绝对估值 | C | financials、ratios（EBIT、折旧摊销等） | valuation.dcf |
| 前端渲染 | E | 整个对象，全字段只读 | 不写任何字段 |

三条硬约束。

1. B 算指标只从 financials 取数，不自己重新抽数值。
2. C 估值的输入只从 financials 与 ratios 取，行情与股本除外。行情值要写进 valuation.comps.inputs 并在 sources 标注。
3. E 只读。页面要显示的任何数字，都必须在对象里已经存在，E 不派生。

## 7. 数据边界与待定项

### 7.1 本 Schema 覆盖了什么

覆盖单公司一次分析的完整链路，含三表关键科目、五类指标、风险卡片、相对与绝对估值、来源。示例公司为制造业，科目标签以通用口径给出。

### 7.2 明确没覆盖，需要时再加

- 时间序列。financials 每条记录只带一期内含 prior_value，够算一期同比。三年复合增速所需的 2023 年数据靠 B 的指标时间序列，未在本对象展开。要做多期趋势，另开时间序列字段，等确定后再加。
- 分产品分地区收入、分部毛利、账龄结构、借款明细等附注级明细。当前不展开，A 抽到后按需并入 financials 或单独挂。
- 假设台账与预测三表。设计文档 M6 的假设台账字段较多，本 Schema 只保留 dcf.inputs 的关键假设。完整台账建议另设文件，接口待定。
- 同业对比（M8）的多公司数组结构。本对象是单公司对象，多公司对比由 D 在编排层把多个对象拼成数组。拼接键待定。

### 7.3 待与成员商榷

下面每条都附了建议方案，等 D 和对应成员确认后再改接口。审查发现的 H1、H2 两处暂时搁置，也记在这里。

**1. 有息负债与折旧摊销的口径（找 A、B）**

问题：这两个科目要从附注汇总，哪些借款算有息负债、折旧摊销取哪张表，A 和 B 理解不一致会让 B 的偿债指标跟着错。

建议方案：A 按「短期借款 + 一年内到期的非流动负债 + 长期借款 + 应付债券」汇总，并在 source 里注明含哪几项。折旧摊销取现金流量表补充资料里固定资产折旧与无形资产摊销的合计。B 直接用 A 给的值，不自己重拼口径。两人确认后写进 5.2 节。

**2. 税率与基期数据由谁给（找 A、B，对应审查 H2，暂搁置）**

问题：B 算 ROIC 要用税率，算三年复合增速要用 2023 年的数，financials 里现在都没有。B 只看这两个文件跑不完全部指标。

建议方案：税率由 A 抽「所得税费用 ÷ 利润总额」，键名 tax_rate，放进 financials。基期数据不要求 A 抽三代，改由 B 在指标层自己维护一个三年序列，并在第 6 节写明 B 可以自建时间序列。这样 B 不用回头问 A。若 A 时间紧，退一步的做法是把 tax_rate 标成可选，B 算不出 ROIC 时写 null 并注明原因。

**3. 估值输入的出处（找 C、E，对应审查 H1，暂搁置）**

问题：valuation 的 comps 和 dcf 输入没有页码和来源字段，E 点不出出处，估值区间这块成了黑箱。

建议方案：comps.inputs 和 dcf.inputs 各加 page 与 source 两栏。sources 数组增加一类 kind 为 market 的条目，登记股价、可比公司倍数、WACC 参数的来源与获取时间。行情来自公开行情页，同样要标页码或链接。

**4. 三个抽了没有下游用的科目（找 B）**

问题：selling_expense、admin_expense、goodwill 都抽了，但 ratios 里没有费用率指标，也没有商誉占净资产比重，字段悬空。

建议方案：保留字段，B 补三条指标。设计文档附录 A 明确列了商誉占净资产比重，风险红旗也要用商誉，砍掉会伤到风险模块。两条费用率指标属于常规计算，加上成本很低。

**5. 风险等级档位（找 B）**

问题：severity 现在只有 high / medium / low 三档。

建议方案：维持三档，不加 info。设计文档的风险卡也只有等级这一个维度，多一档会让 B 的规则和 E 的渲染都复杂一层，收益不明显。

**6. DCF 终值与 WACC 的拆解深度（找 C）**

问题：设计文档 4.12 要求终值并列永续增长与退出倍数两种方式，WACC 要拆出无风险利率、Beta、股权风险溢价、债务成本。现在只有一个 wacc 数字和一种终值算法。

建议方案：中期汇报不要求 DCF，先保留现状。WACC 加四个可选字段 rf、beta、erp、cost_of_debt，C 有余力就填。退出倍数法放到第二阶段。中期若要展示估值模块，优先补 WACC 拆解，因为它同时满足设计文档「参数全部公开」这条原则。

**7. 非财务事实的命名规则（找 B、E）**

问题：风险卡里出现 pledge_ratio，financials 和 ratios 都没定义这个键，E 不知道该按什么渲染。

建议方案：规定非财务事实的 metric 名一律带前缀，写成 governance.pledge_ratio、governance.auditor_change 这类，并在 source 里注明取自公司治理章节的页码。E 按前缀判断渲染方式。

**8. 母公司口径（找 A、B）**

问题：现在只存合并报表口径。

建议方案：暂不单独存一套。需要时另开对象或用 scope 字段区分。当前分析以合并为主，母公司数据用得少，先不付这个复杂度。

**9. ROE 加权口径（找 B）**

问题：示例 roe_weighted 用期初期末平均净资产简化计算，设计文档要求加权口径。

建议方案：B 在附注数据可得时改用加权口径，并在 formula 里注明用的是加权还是平均。示例值保持简化写法，但要在 5.4 节说明里标注清楚。

注记：第 4 节示例里的数字全部是虚构的，只用于对齐格式。正式交付时由 A 用真实年报数据替换，替换后仍须满足第 4 节的勾稽关系。
