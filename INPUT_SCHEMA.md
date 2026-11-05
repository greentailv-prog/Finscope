# 输入定义（v2）

估值引擎的输入是**一个 JSON 对象**。它兼容三种来源：

1. **D 的 canonical 统一对象**（`company / financials / market_data / comparison`）；
2. 本模块 v1 的输入（`company / financials / peers / sotp_segments / assumptions`）；
3. 最小输入（只给代码，自动联网取数）。

## 单位约定

| 类型 | 单位 |
|---|---|
| 金额 | 报表原始货币的**元** |
| 比率 | **小数**（15% 写作 `0.15`） |
| 股价 | 元 / 美元 |
| 股本 | 股 |

## 最小输入

```json
{"company": {"ticker": "600519", "market": "A"}}
```

引擎会自动：

- 取历史财务、行情、股本、行业、分部收入；
- 按行业池选 4–6 家可比公司；
- 按规则补 DCF 假设；
- 计算 DCF / Comps / SOTP（或 DDM）；
- 输出融合结论与 Excel 底稿。

## 顶层结构

```json
{
  "company":        { ... },          // 必填（ticker 即可）
  "financials":     { ... },          // 可选；给了就不联网取财务
  "market_data":    { ... },          // 可选；D 传入的行情，优先级最高
  "peers":          [ ... ],          // 可选；带倍数的可比公司
  "peer_set":       ["000858"],       // 可选；只给代码，C 补财务
  "peer_financials":[ ... ],          // 可选；D 传入的同业财务
  "peer_market_data":[{ ... }],       // 可选；D 传入的同业行情
  "segments":       [ ... ],          // 可选；SOTP 分部
  "segment_evidence":{ ... },         // 可选；证据包
  "assumptions":    { ... },          // 可选；用户/规则假设
  "method_selection": "auto",         // auto/dcf/comps/sotp/blended/ddm
  "relative_multiples": ["pe","pb"], // 可选；用户指定倍数
  "sources":        [ ... ],
  "fetch_data": true,                 // 是否允许联网
  "data_source": "auto",              // auto/ifind/choice/web/akshare/canonical
  "web_evidence":   { ... },          // 已复核的网页/年报证据包
  "as_of": "2026-11-03"
}
```

## company

| 字段 | 说明 |
|---|---|
| `ticker` / `code` | 代码。A 股 6 位数字，美股大写字母 |
| `name` | 名称（可空，自动取） |
| `market` | `A` / `US` |
| `currency` | `CNY` / `USD` |
| `industry` / `sector` | 行业，用于选同业与行业门槛 |
| `report_period` | 估值基准期，如 `2025-12-31` |
| `price_date` / `price_time` / `price_source` | 行情日期与来源 |

## financials

年份索引的数组与 `years` 等长；缺失用 `null`。

| 字段 | 说明 |
|---|---|
| `years` | 会计年度，升序 |
| `revenue` / `cogs` / `gross_profit` | 营业收入 / 营业成本 / 毛利 |
| `ebit` | 息税前利润（D 若只给 `operating_profit`，C 会加回财务费用） |
| `pretax_income` / `tax_provision` / `net_income` | 利润总额 / 所得税 / 净利润 |
| `net_income_parent` | 归母净利润 |
| `interest_expense` / `finance_expense` | 利息费用 / 财务费用 |
| `eps` / `sbc` | 每股收益 / 股份支付 |
| `da` / `capex` / `delta_nwc` | 折旧摊销 / 资本开支（正数=流出）/ 营运资本增加（正数=占用） |
| `cfo` / `dividends_paid` | 经营现金流 / 股利支付 |
| `total_debt` / `cash` | 有息负债 / 货币资金 |
| `minority_interest` / `preferred_stock` | 少数股东权益 / 优先股 |
| `total_assets` / `total_equity` | 总资产 / 所有者权益 |
| `current_assets` / `current_liabilities` | 流动资产 / 流动负债 |
| `price` / `shares_outstanding` / `market_cap` / `beta` | 市场数据 |

### D canonical 字段映射

| C 字段 | D canonical 可能键名 |
|---|---|
| `revenue` | `revenue` / `operating_revenue` / `total_revenue` |
| `cogs` | `cogs` / `operating_cost` / `cost_of_revenue` |
| `ebit` | `ebit` / `operating_income`；若只有 `operating_profit` 则加回 `finance_expense` |
| `pretax_income` | `pretax_income` / `pretax_profit` / `profit_before_tax` |
| `tax_provision` | `tax_provision` / `income_tax_expense` |
| `net_income` | `net_income` / `net_profit` |
| `net_income_parent` | `net_income_parent` / `attributable_net_income` |
| `da` | `da` / `depreciation_amortization` |
| `capex` | `capex` / `capital_expenditure` |
| `delta_nwc` | `delta_nwc` / `change_in_working_capital` |
| `cfo` | `cfo` / `operating_cash_flow` |
| `total_debt` | `total_debt` / `interest_bearing_debt` |

## market_data

D 统一取的行情，优先级最高；C 不自己另取一个价。

```json
{"price": 1263.0, "shares_outstanding": 1256197800, "market_cap": 1586161714000,
 "price_date": "2026-11-03", "price_time": "15:00:00", "price_source": "腾讯行情"}
```

## peers

带倍数的可比公司；不给倍数则用 `peer_set` 代码由 C 补财务。

```json
{
  "name": "五粮液", "ticker": "000858",
  "pe": 8.25, "pb": 2.01, "ps": 3.07, "pcf": 18.0, "peg": 1.2,
  "ev_revenue": 4.2, "ev_ebitda": 5.6, "ev_ebit": 5.1,
  "revenue_growth": 0.05, "ebit_margin": 0.38, "ebitda_margin": 0.42,
  "market_cap": 1.1e12, "net_debt": -5e10, "ebitda": 3e10, "revenue": 8e10,
  "selection_reason": "高端白酒双寡头之一", "tier": "user"
}
```

## peer_financials + peer_market_data（D canonical）

```json
"peer_financials": [
  {"ticker": "000858", "name": "五粮液", "financials": {"years": [2023,2024,2025], "revenue": [...]}}
],
"peer_market_data": [
  {"ticker": "000858", "price": 128.0, "shares_outstanding": 3.88e9, "market_cap": 4.97e11}
]
```

C 会用两段数据自己算倍数，不再联网。

## segments

```json
{"name": "智能家居业务", "metric": "revenue", "value": 299927239000,
 "multiple_type": "ev_revenue", "multiple": null,
 "peer_names": ["格力电器", "海尔智家"], "note": "年报分部"}
```

`metric` 可取 `revenue` / `ebit` / `ebitda`；`multiple` 为空时由 C 按分部名称匹配纯业务同业。

## data_source

| 值 | 行为 |
|---|---|
| `auto` | D 有 `financials` 就用 D；否则 akshare；`FINSCOPE_OFFICIAL=1` 时先探测 iFinD/Choice |
| `canonical` | 只用 D/A 传入的数据，不联网 |
| `ifind` / `choice` | 先走官方源，失败回退 akshare |
| `web` | 巨潮资讯年报检索 → PDF 解析 → 估值 |
| `akshare` | 新浪财报 + 东财主营构成 |

## web_evidence

Agent / D 复核后的证据包，C 直接使用，不再联网：

```json
{
  "financials": {"years": [2023,2024,2025], "revenue": [...], "net_income": [...],
                 "da": [...], "capex": [...], "total_equity": 0, "shares": 0},
  "segments": [{"name": "智能家居业务", "revenue": 299927239000, "gross_margin": 0.299}],
  "sources": [{"name": "年报 PDF·2025", "purpose": "财务报表/分部",
               "as_of": "2025-12-31", "official": true,
               "note": "https://static.cninfo.com.cn/..."}]
}
```

也支持 `{"pdf_path": "...", "report_year": 2025}`，由 C 调 `web.parse_annual_report` 解析。

## assumptions

| 字段 | 默认 | 说明 |
|---|---|---|
| `method_selection` | `auto` | `auto/dcf/comps/sotp/blended/ddm` |
| `selected_methods` | `[]` | 显式方法组合 |
| `forecast_years` | 5 | 3–10 |
| `revenue_growth_y1` | null | null = 规则合成 |
| `revenue_growth_path` | [] | 逐年增速；给了就覆盖 |
| `terminal_growth` | 2.5% | 受市场上限约束 |
| `terminal_method` | `blend` | `blend/gordon/exit/roic` |
| `terminal_roic` | null | 终值再投资率 |
| `ebit_margin` / `da_pct_revenue` / `capex_pct_revenue` / `nwc_pct_revenue` | null | null = 近三年中位数 |
| `tax_rate` | null | null = 近三年中位数，夹 15%–30% |
| `risk_free` / `erp` / `beta` / `cost_of_debt` | null | null = 运行时/行业锚点 |
| `beta_mode` | `blume` | `raw/blume/sector/manual` |
| `wacc_mode` | `reconciled` | `capm/reconciled/manual` |
| `wacc_override` | null | 手工 WACC |
| `size_premium` / `target_debt_ratio` | null | 规模溢价 / 目标资本结构 |
| `multiples` | [] | 用户指定倍数 |
| `multiple_adjustment` | {} | `{"pe":0.1}` |
| `peer_growth_adjustment` | true | 是否按增速/利润率自动调整 |
| `segment_allocation` | `gross_profit` | EBIT 分摊口径 |
| `sotp_corporate_cost_pct` | 2% | 总部费用估算 |
| `weights` / `weight_mode` | {} / `rules` | 手工权重 |
| `dividend_payout` / `ddm_growth` | null | DDM 用 |
| `wacc_steps` / `growth_steps` | ±1%/±0.5% | 敏感性轴 |
| `bull_*` / `bear_*` | ±3%/±2%/∓1% | 三情景 |

## 输出

见 `OUTPUT_SCHEMA.md`。
