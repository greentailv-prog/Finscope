# INPUT_SCHEMA.md — financial-diagnosis 输入契约

> 本文件是 **B 对 A 的接口要求**。A 只要满足这份契约，B 就能跑通。
> 完整格式见 `demo/input_financials.json`（可直接当模板改）。

---

## 一句话版本

**B 需要：至少两期（强烈建议三期）的财务数据，每个数字带单位、出处和页码。**

---

## 顶层结构

```jsonc
{
  "schema_version": "finradar.extraction/1.0",
  "meta":   { ... },      // 期间、单位、假设
  "company": { ... },     // 公司基本信息
  "financials": { ... }   // 核心：指标 → 期间 → 值
}
```

## `meta`（必需）

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `periods` | string[] | ✅ | 期间列表，**按时间升序**，如 `["2023","2024","2025"]`。最后一个是当期。 |
| `default_unit` | string | ✅ | 当单元格没写 `unit` 时回退的单位，如 `"亿元"` |
| `currency` | string | ⭕ | 默认 `"CNY"` |
| `wacc` | number | ⭕ | 资本成本小数（0.085 = 8.5%）。**由 C 提供**，缺则 `roic_minus_wacc` 与相关风险规则不可算 |
| `days_in_year` | number | ⭕ | 默认 365。周转天数用 |
| `industry` | string | ⭕ | 行业，用于行业校准的日志与提示 |
| `industry_gross_margin_benchmark` | number\|null | ⭕ | 行业毛利率中位数。**由 C 从可比公司池统计后回填** |
| `audit_opinion` | string | ⭕ | 审计意见原文，如 `"标准无保留意见"`。Risk Radar 的 A03 规则要用 |

## `company`（必需）

```json
{ "name": "华衍智能装备股份有限公司", "ticker": "DEMO.SH",
  "industry": "专用设备制造业", "report_period": "2025" }
```

## `financials`（核心）

**结构：`指标名 → { 期间 → {值, 单位, 出处, 页码} }`**

```jsonc
"financials": {
  "revenue": {
    "2023": { "value": 98.60, "unit": "亿元", "source": "2023年年度报告", "page": 83 },
    "2024": { "value": 112.40, "unit": "亿元", "source": "2024年年度报告", "page": 82 },
    "2025": { "value": 128.60, "unit": "亿元", "source": "2025年年度报告", "page": 83 }
  },
  ...
}
```

### 单元格的两种写法（都支持）

```jsonc
"2025": { "value": 128.60, "unit": "亿元", "source": "...", "page": 83 }   // 推荐：完整
"2025": 128.60                                                            // 兼容：用 meta.default_unit
```

### 支持的单位

| unit | 系数 |
|---|---|
| `元` / `CNY` / `人民币元` | 1 |
| `千元` | 1e3 |
| `万元` | 1e4 |
| `百万元` / `百万` | 1e6 |
| `亿元` / `亿` | 1e8 |

> B 内部统一归一到**元**再计算，展示层再自行换算——这是口径 C1。

---

## 字段清单

图例：✅ 必需（缺了关键指标就不可算）｜⭐ 强烈建议（影响上期对比值与风险覆盖）｜⭕ 可选

### 利润表

| 字段 | 必需度 | 用于 |
|---|---|---|
| `revenue` | ✅ | 几乎所有比率的分母 |
| `cost_of_revenue` | ✅ | 毛利率、存货周转、应付周转 |
| `operating_profit` | ✅ | 营业利润率、EBIT、利润桥 |
| `pretax_profit` | ✅ | 有效税率 |
| `income_tax_expense` | ✅ | 有效税率、NOPAT |
| `net_income` | ✅ | 净利率、ROA、现金流桥 |
| `net_income_parent` | ✅ | ROE、净现比、扣非占比 |
| `net_income_deducted` | ✅ | 扣非净利率、盈利含金量 |
| `selling_expense` | ✅ | 销售费用率、期间费用率 |
| `admin_expense` | ✅ | 管理费用率 |
| `rd_expense` | ⭐ | 研发费用率 |
| `finance_expense` | ✅ | EBIT、财务费用率 |
| `interest_expense` | ✅ | 利息保障倍数 |
| `depreciation_amortization` | ⭐ | EBITDA、现金流桥 |
| `impairment_loss` | ⭐ | 现金流桥 |
| `rd_capitalized` | ⭕ | 研发资本化率（Risk Radar A04 规则要用） |

### 资产负债表

| 字段 | 必需度 | 用于 |
|---|---|---|
| `cash_and_equivalents` | ✅ | 现金比率、净负债、现金覆盖 |
| `restricted_cash` | ⭐ | 受限资金占比 |
| `accounts_receivable` | ✅ | DSO、应收周转 |
| `notes_receivable` | ⭐ | 应收总额（宽口径） |
| `contract_assets` | ⭐ | 应收总额（宽口径） |
| `inventory` | ✅ | DIO、存货周转、CCC |
| `total_current_assets` | ✅ | 流动比率、营运资金 |
| `fixed_assets` | ⭐ | 固定资产周转率 |
| `goodwill` | ⭐ | 商誉/净资产（Risk Radar A01） |
| `total_assets` | ✅ | ROA、总资产周转、资产负债率 |
| `accounts_payable` | ✅ | DPO、应付周转、CCC |
| `total_current_liabilities` | ✅ | 流动比率、营运资金 |
| `short_term_borrowings` | ✅ | 有息负债、现金覆盖 |
| `current_portion_lt_debt` | ✅ | 有息负债、现金覆盖 |
| `long_term_borrowings` | ✅ | 有息负债 |
| `bonds_payable` | ⭐ | 有息负债（无则填 0） |
| `total_liabilities` | ✅ | 资产负债率 |
| `equity_parent` | ✅ | ROE、净负债、商誉占比 |
| `total_equity` | ⭐ | 交叉校验 |

### 现金流量表

| 字段 | 必需度 | 用于 |
|---|---|---|
| `ocf` | ✅ | 净现比、FCF、现金流桥 |
| `cf_investing` | ⭐ | 外部融资依赖度 |
| `cf_financing` | ⭐ | 融资依赖度、资金去向 |
| `capex` | ✅ | FCF、资本开支/OCF |
| `cash_received_from_sales` | ✅ | 收现比 |
| `interest_paid` | ⭐ | 经营现金流利息覆盖 |
| `dividend_paid` | ⭐ | 分红率（Risk Radar V01 / V02） |

---

## 三条对 A 的硬性请求

1. **给三期数据。** 只要两期的话，`roe` / `roa` / `roic` / 周转率的**上期值**算不出来（需要 t-2 的余额做分母），
   所有"变化类"风险规则会退化成 `not_evaluable`。三期数据能让变化类规则全部生效。
2. **页码必须给。** 没有页码，风险证据链和 E 前端的"点击展开看原文"就断了——这是整个产品最核心的卖点。
3. **单位别混用。** 同一份 JSON 里可以有不同单位（B 会自动归一），但同一个指标的三期必须用同一单位。

## 自检清单（A 交付前跑一遍）

```bash
cd financial-diagnosis
python scripts/compute_ratios.py -i <A给你的json> -o /tmp/check.json --pretty
# 看输出：
#   指标数: 65   待核验: 0     ← 说明口径完整
#   待核验: N > 0              ← 打开 /tmp/check.json 的 review_queue，看缺哪些字段
```

`review_queue` 里的 `missing_required_field` 会直接告诉你需要补哪个字段。
