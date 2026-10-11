# 输入定义

估值引擎的输入是**一个 JSON 对象**。A/B/C/D 之间通过它交换数据——D 的总集成
把上游（A 的财报、B 的指标）整理成本结构后调用即可。

## 单位约定（全项目统一）

| 类型 | 单位 |
|---|---|
| 金额 | 报表原始货币的**元**（不是万元、不是亿元） |
| 比率 | **小数**（15% 写作 `0.15`） |
| 股价 | 元 / 美元 |
| 股本 | 股 |

## 顶层结构

```json
{
  "company":            { ... },   // 必填
  "financials":         { ... },   // 必填
  "peers":              [ ... ],   // 相对估值需要；缺失则跳过该方法
  "assumptions":        { ... },   // 可选，缺省走默认值
  "sotp_segments":      [ ... ],   // 可选，有分部数据才填
  "relative_multiples": ["pe", "ps", "pb"],
  "sources":            [ ... ],
  "meta":               { }
}
```

---

## company（必填）

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 公司名称 |
| `ticker` | string | 代码。A 股 6 位数字，美股大写字母 |
| `market` | string | `"A"` 或 `"US"`——决定用哪套市场默认参数 |
| `currency` | string | `CNY` / `USD` |
| `industry` / `sector` | string | 行业，用于挑可比公司 |
| `report_period` | string | 估值基准期，如 `2025-12-31` |
| `price_date` | string | 价格日期 |

## financials（必填）

**年份索引的数组一律与 `years` 等长**；缺失值用 `null`，**不要用 0 冒充**。

| 字段 | 类型 | 对应利润表/现金流量表科目 |
|---|---|---|
| `years` | int[] | 会计年度，升序，如 `[2021,2022,2023,2024,2025]` |
| `revenue` | number[] | 营业总收入 |
| `cogs` | number[] | 营业成本 |
| `ebit` | number[] | 息税前利润（营业利润） |
| `pretax_income` | number[] | 利润总额 |
| `tax_provision` | number[] | 所得税费用 |
| `net_income` | number[] | 净利润 |
| `interest_expense` | number[] | 利息费用 |
| `sbc` | number[] | 股份支付（可选） |
| `da` | number[] | 折旧与摊销 |
| `capex` | number[] | 资本开支（**正数 = 流出**） |
| `delta_nwc` | number[] | 营运资本变动（**正数 = 占用增加**） |

**资产负债表（最新一期，标量）**

| 字段 | 说明 |
|---|---|
| `total_debt` | 有息负债合计（短借＋长借＋应付债券） |
| `cash` | 货币资金 |
| `minority_interest` | 少数股东权益 |
| `preferred_stock` | 优先股 |
| `total_assets` / `total_equity` | 总资产 / 所有者权益合计 |

**市场数据（标量）**

| 字段 | 说明 |
|---|---|
| `price` | 最新股价 |
| `shares_outstanding` | 稀释后股本 |
| `market_cap` | 总市值 |
| `beta` | 市场观测的 Beta（含杠杆）。留空则用 CAPM 默认值 |

## peers（可选，数组）

相对估值的可比公司。**至少 3 家**，建议 4–6 家。缺失的倍数写 `null`，不要填 0。

```json
{
  "name": "五粮液", "ticker": "000858",
  "pe": 8.25, "pe_forward": 7.9, "pb": 2.01, "ps": 3.07,
  "ev_revenue": 4.2, "ev_ebitda": 5.6, "ev_ebit": 5.1, "peg": 1.2,
  "revenue_growth": 0.05, "gross_margin": 0.75,
  "ebitda_margin": 0.42, "ebit_margin": 0.38,
  "market_cap": 1.1e12, "net_debt": -5e10, "ebitda": 3e10, "revenue": 8e10,
  "note": "选取依据"
}
```

## assumptions（可选）

不给就用 `RULES.md` 里的默认值。

| 字段 | 默认 | 说明 |
|---|---|---|
| `forecast_years` | 5 | 预测期，允许 3–10 |
| `revenue_growth_y1` | null | 首年增速；null = 用历史 CAGR |
| `terminal_growth` | 0.025 | 永续增长率，受市场上限约束 |
| `ebit_margin` | null | null = 近三年中位数 |
| `da_pct_revenue` | null | 同上 |
| `capex_pct_revenue` | null | 同上 |
| `nwc_pct_revenue` | null | 同上 |
| `tax_rate` | null | null = 近三年有效税率中位数，夹在 15%–30% |
| `sbc_is_cash` | false | SaaS 一般设 true |
| `risk_free` | null | null = 用市场默认（A 股 1.8% / 美股 4.28%） |
| `erp` | 0.0514 | A 股用 Damodaran 中国值；美股用 4.28% |
| `beta` | null | null = 用 financials.beta |
| `cost_of_debt` | null | null = 利息费用 ÷ 有息负债 |
| `size_premium` | 0.0 | 小市值补充回报 |
| `target_debt_ratio` | null | null = 用当前市值口径 |
| `multiple_adjustment` | {} | `{"pe": 0.1}` 表示 PE 上调 10% |
| `weights` | {} | `{"dcf":0.5,"relative":0.5}`，不给按有无 SOTP 取默认 |
| `wacc_steps` / `growth_steps` | ±1.0%/±0.5% | 敏感性矩阵轴的偏移 |

## sotp_segments（可选，数组）

```json
{"name": "云业务", "metric": "ebitda", "value": 7.5e9,
 "multiple": 20.0, "peer_names": ["MSFT","AMZN"], "note": ""}
```

`metric` 取 `ebitda` / `revenue` / `ebit`。

## sources（可选，数组）

**交付时必须填**，用于底稿的「数据来源」页。

```json
{"name": "新浪财经·利润表", "as_of": "2026-10-11", "official": false,
 "purpose": "财务报表"}
```

---

## 最小可用输入

只填这三个也能跑（相对估值会跳过）：

```json
{
  "company": {"name":"某某公司","ticker":"600519","market":"A","currency":"CNY"},
  "financials": {
    "years": [2023,2024,2025],
    "revenue": [1.5e11, 1.74e11, 1.72e11],
    "ebit":    [1.03e11, 1.2e11, 1.15e11],
    "net_income": [7.75e10, 8.93e10, 8.53e10],
    "price": 1263.0, "shares_outstanding": 1.252e9, "market_cap": 1.58e12,
    "total_debt": 5e8, "cash": 5.17e10
  }
}
```
