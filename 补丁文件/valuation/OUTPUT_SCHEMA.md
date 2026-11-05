# 输出定义（v2）

估值结果是一个 JSON 对象，可直接放进 D 统一对象的 `valuation` 字段。

## 与 ABC 接口规范的兼容性

| C 原生字段 | D 的 canonical | 说明 |
|---|---|---|
| `relative` | `comps` | C 保留 `relative`，同时输出 `comps` 别名 |
| `relative.peers_detail[]` | `comps.peer_companies[]` | C 两边都输出 |
| `sensitivity.wacc_axis / growth_axis / grid` | `sensitivity.wacc_g` | 旧字段保留；新字段 `wacc_g` 带 `matrix` |
| `dcf.rows` | `dcf.forecast` | 两边都输出 |
| `status` / `industry_support` / `gate_reason` / `assumptions[]` / `excel_path` | 同名透传 | 新增 |

> `blocked` 由 D 的数据质量闸门写入，C 不写；C 只返回
> `ok / partial / unsupported / failed`。

## 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | `2.0` |
| `status` | string | `ok / partial / unsupported / failed` |
| `industry_support` | string | `supported / limited / unsupported` |
| `gate_reason` | string / null | 行业结构性限制的机器原因，如 `standard_fcff_unsupported; ddm_used`；无限制时为 null |
| `industry_gate` | object | 行业门槛说明、`standard_fcff_supported` 与替代方法 |
| `company` | object | 标的公司 |
| `as_of` | int | 最新会计年度（异常年份剔除后） |
| `currency` | string | `CNY / USD` |
| `market_data` | object | `price / shares_outstanding / market_cap / price_date / price_time / price_source` |
| `method_selection` | string | `auto/dcf/comps/sotp/blended/ddm` |
| `method_plan` | object | `methods[] / reason / status{}` |
| `history` | object | 历史财务与比率：`years / revenue / ebit / net_income / cogs / gross_profit / da / capex / cfo / delta_nwc / revenue_growth / ebit_margin / net_margin / gross_margin / capex_pct / da_pct / nwc_pct / tax_rate` |
| `assumptions` | object[] | 假设台账 |
| `reliabilities` | object | 各方法可靠性评分与扣分项 |
| `dcf` | object | DCF 结果 |
| `relative` | object | = `comps`（兼容 D 的 `from_c`） |
| `comps` | object | 相对估值结果 |
| `sotp` | object | 分部估值结果 |
| `ddm` | object | 金融行业 DDM/剩余收益 |
| `blended` | object | 融合结论 |
| `scenarios` | object | Bull / Base / Bear |
| `sensitivity` | object | `wacc_g` / `growth_margin`；同时保留旧 `wacc_axis/growth_axis/grid` |
| `valuation_range` | object | Comps 的 low/mid/high |
| `peer_selection` | object | 可比公司选择理由与层级 |
| `segment_meta` / `segment_source` | object/string | 分部来源与覆盖度 |
| `data_source` | object | `requested / used / fallback`，如 `web` / `akshare` / `canonical` |
| `gates` | object[] | 交叉验证门槛（severity: info/warn/block） |
| `warnings` | string[] | 模型提示，交付前逐条复核 |
| `sources` | object[] | 数据来源 |
| `excel_path` | string | **每次估值同步生成**的 Excel 路径，相对交付包根目录；D 按包根解析后生成下载 URL |
| `excel_format` | string | `professional_18_sheets` / `legacy_12_sheets` / `three_statement_formula_5_sheets` |
| `excel_generated_at` | string | 本次底稿生成时间 `YYYY-MM-DD HH:MM:SS` |
| `presentation` | object | `narrative` + `charts` |
| `disclaimer` | string | 免责声明 |

## status

| 值 | 含义 |
|---|---|
| `ok` | 至少两种方法正常产出，且无重大方法分歧 |
| `partial` | 只有一种方法、方法分歧 >50%、缺行情，或**行业结构性不支持标准 FCFF 但替代方法已产出**（银行/保险/证券） |
| `unsupported` | 行业没有任何可用估值方法，未出估值（地产/REITs 且无 NAV/FFO 口径） |
| `failed` | 模型运行失败，看 `error` |

银行/保险/证券的输出约定：

```json
{
  "status": "partial",
  "industry_support": "limited",
  "gate_reason": "standard_fcff_unsupported; ddm_used",
  "dcf": {"ok": false},
  "ddm": {"ok": true, "per_share": 59.91},
  "comps": {"ok": true, "implied_per_share": 29.23},
  "blended": {"blended_per_share": 53.77}
}
```

`unsupported` 只留给“真的没有任何可用方法”的行业；不得再用 `unsupported`
表示“标准 FCFF 不适用但 DDM/Comps 可用”。

## dcf

| 字段 | 说明 |
|---|---|
| `ok` / `error` | 是否成功 |
| `per_share` / `equity_value` / `enterprise_value` | 结论；**`market_data.price=null` 时 `per_share=null`，`equity_value`/`enterprise_value` 仍保留** |
| `wacc` / `wacc_capm` / `implied_wacc` | 采用 WACC / CAPM WACC / 市场隐含 WACC |
| `wacc_reconciliation` | 校准幅度、规则说明 |
| `wacc_block` | `risk_free / erp / beta / cost_of_equity / cost_of_debt / tax_rate / debt_ratio / equity_ratio` 及来源 |
| `terminal_growth` / `terminal_growth_cap` / `terminal_method` / `terminal_roic` | 终值假设 |
| `revenue_growth_y1` / `revenue_growth_path` / `ebit_margin` / `da_pct` / `capex_pct` / `nwc_pct` / `tax_rate` | 关键假设 |
| `rows[]` / `forecast[]` | 逐年明细：`year / growth / revenue / ebit / cash_tax / nopat / da / capex / delta_nwc / fcff / discount_factor / pv_fcff` |
| `pv_explicit` / `pv_terminal` | 预测期现值 / 终值现值 |
| `tv_gordon` / `tv_exit` / `tv_roic` / `tv_base` / `tv_divergence` | 三种终值与采用值、偏离度 |
| `tv_ratio` | 终值占企业价值 |
| `diagnostics` | `wacc_gap_bp / wacc_minus_g / tv_ratio / tv_divergence` |
| `reliability`（在外层 `reliabilities.dcf`） | 评分与扣分项 |

## comps / relative

| 字段 | 说明 |
|---|---|
| `ok` / `error` | 是否成功 |
| `peers_used` / `peer_count` | 可比公司家数 |
| `peers_detail[]` | 可比公司原始对象（D 的 `comps.peer_companies`） |
| `peer_companies[]` | 展示用明细：`name / ticker / pe / pb / ps / pcf / peg / ev_* / growth / margin / selection_reason / tier / source / as_of / comparability{score,level,reasons}` |
| `comparability_note` | 可比性评分口径说明 |
| `peer_selection` | `tier / theme / selection_note / peers[] / missing[]` |
| `decisions` | 倍数选择：`multiple / label / used / reason` |
| `results[]` | 各倍数：`peer_median / peer_mean / p25 / p75 / sample_count / dispersion / adjustment / applied_multiple / metric_basis / metric_value / implied_equity_value / implied_per_share` |
| `implied_per_share` / `implied_equity_value` | 结论（各倍数中位） |
| `range_low` / `range_high` / `valuation_range` | 区间 |
| `target_multiples` / `positioning` | 目标自身倍数与在同业分布中的位置 |
| `judgment` | 中文相对估值判断 |

## sotp

| 字段 | 说明 |
|---|---|
| `ok` / `skipped` / `reason` | 是否启用 |
| `rows[]` | `name / metric_type / value / multiple / peer_names / segment_ev / revenue / gross_margin / allocated_ebit / allocated_ebitda / source` |
| `segment_ev_total` | 分部 EV 合计 |
| `corporate_cost` / `corporate_cost_estimated` | 总部费用 |
| `net_debt` / `minority_interest` / `preferred_stock` | 桥接项 |
| `equity_value` / `per_share` | 结论 |
| `conglomerate_discount` | 集团折价 |
| `revenue_coverage` / `implied_ev_revenue` / `implied_ev_ebitda` | 覆盖度与隐含倍数 |

## ddm

| 字段 | 说明 |
|---|---|
| `ok` / `error` | 是否成功 |
| `per_share` / `equity_value` | 结论 |
| `cost_of_equity` / `cost_of_equity_capm` / `implied_cost_of_equity` | Ke 与校准 |
| `ke_reconciliation` | 校准说明 |
| `growth` / `payout_ratio` / `payout_source` / `roe` | 假设 |
| `ddm_value` / `ri_value` / `components[]` | 两种口径 |
| `note` | 金融行业口径说明 |

## blended

| 字段 | 说明 |
|---|---|
| `ok` | 是否形成融合 |
| `blended_per_share` / `blended_equity_value` | 融合结论 |
| `current_price` / `upside` / `verdict` | 现价、空间、判断 |
| `weights` / `components[]` | 各方法权重与每股价值 |
| `weight_source` / `trace[]` | 权重口径与规则轨迹 |
| `confidence` | 高 / 中 / 低 |
| `primary` / `divergence` | 主方法 / 方法分歧 |
| `range_low` / `range_high` / `range_note` | 分歧 >50% 时的区间参考 |

## sensitivity

```json
{
  "wacc_axis": [0.05, 0.055, 0.06, 0.065, 0.07],
  "growth_axis": [0.015, 0.02, 0.025, 0.03, 0.035],
  "grid": [[...], ...],
  "wacc_g": {"title": "...", "matrix": [[...]], "wacc_axis": [...], "growth_axis": [...],
             "base_wacc": 0.06, "base_growth": 0.025, "base_index": {"x": 2, "y": 2}},
  "growth_margin": {"growth_axis": [...], "margin_axis": [...], "matrix": [[...]],
                    "base_growth": 0.08, "base_margin": 0.68, "base_index": {...}}
}
```

`null` 表示该组合 `WACC ≤ g`，无解；`market_data.price=null` 时整个矩阵为 `null`。

分业务驱动（`operating_forecast`）模式下：`wacc_g` 仍完整输出；
`growth_margin` 置 `null` 并在 `warnings` 说明，因为分部预测的收入与利润率固定；
`scenarios.scenario_basis="driver_rows_scaled"`，三情景按分部预测行缩放收入/利润率后重算 FCFF。

## scenarios

```json
{
  "bull": {"per_share": 3168.12, "growth_y1": 0.083, "ebit_margin": 0.71, "wacc": 0.057},
  "base": {"per_share": 2104.86, "...": "..."},
  "bear": {"per_share": 1511.40, "...": "..."},
  "scenario_basis": "assumption_deltas | driver_rows_scaled",
  "warnings": []
}
```

## assumptions[]

```json
{"name": "WACC（CAPM 口径）", "value": 0.0600, "unit": "小数",
 "source_type": "model", "source": "rf 1.63% + β 0.85 × ERP 5.14%",
 "confidence": "中", "overridable": true, "note": ""}
```

`source_type` 四选一：`history / management / industry / model`。
使用者提交的分部预测情景归入 `model`，不再使用第五类 `user_scenario`。

## 行情缺失时的输出

- `market_data.price=null` → `dcf.per_share=null`、`blended.blended_per_share=null`、
  `scenarios.*.per_share=null`、`sensitivity.wacc_g.matrix` 全部为 `null`；
- `dcf.equity_value`、`dcf.enterprise_value`、`blended.blended_equity_value` 仍保留；
- `warnings` 写“未获取到实时行情，每股价值未计算”；
- 不拿上一家公司或上一次的股价顶替。

## gates[]

```json
{"code": "WACC_IMPLIED_GAP", "severity": "warn",
 "message": "CAPM 与市场隐含 WACC 相差 247bp……",
 "affected_paths": ["dcf.wacc", "valuation.blended"]}
```

`severity`：`info / warn / block`。`block` 只表示「该结论需要显著降级/复核」，
最终 `blocked` 状态仍由 D 的数据质量闸门写入。

## presentation

### narrative

```json
{
  "headline": "……",
  "verdict": "估值分歧较大（区间参考）",
  "confidence": "低",
  "sections": [
    {"title": "结论摘要", "kind": "text", "paragraphs": ["……"], "metrics": [...]},
    {"title": "相对估值（Comps）", "paragraphs": ["……"]},
    {"title": "绝对估值（DCF / FCFF）", "paragraphs": ["……"]},
    {"title": "分部估值（SOTP）", "paragraphs": ["……"]},
    {"title": "关键风险与待核验", "paragraphs": ["……"]}
  ],
  "disclaimer": "……"
}
```

### charts

| 键 | 内容 |
|---|---|
| `dcf_forecast` | `years / series{revenue, ebit, fcff, capex, da, delta_nwc} / ratios{growth, ebit_margin, capex_pct, da_pct, nwc_pct}` |
| `tv_composition` | `items[{label, value}] / tv_ratio` |
| `valuation_range` | `low / mid / high / price / blended / dcf / sotp` |
| `sensitivity_wacc_g` | 同 `sensitivity.wacc_g` |
| `sensitivity_growth_margin` | 同 `sensitivity.growth_margin` |
| `scenarios` | `labels / values / levers` |
| `comps_position` | `items[{multiple, target, peer_median, peer_min, peer_max, percentile, premium_discount}]` |
| `weights` | `items[{method, weight, reliability}]` |

单位：除比率外，金额均为**亿元**（前端直接画图）；每股价值为**元**。

## 最小输出示例

```json
{
  "schema_version": "2.0",
  "status": "partial",
  "industry_support": "supported",
  "company": {"name": "贵州茅台", "ticker": "600519", "market": "A", "currency": "CNY"},
  "market_data": {"price": 1480.0, "shares_outstanding": 1250081601, "market_cap": 1.85e12},
  "data_source": {"requested": "web", "used": "web", "fallback": false},
  "dcf": {"ok": true, "per_share": 1815.59, "wacc": 0.0600, "wacc_capm": 0.0600,
          "implied_wacc": 0.0732, "tv_ratio": 0.808, "rows": [...]},
  "comps": {"ok": true, "implied_per_share": 1360.48, "peers_detail": [...], "results": [...]},
  "sotp": {"ok": true, "per_share": 1075.50, "rows": [...]},
  "blended": {"blended_per_share": 1383.81, "upside": -0.0650,
              "verdict": "估值分歧较大（区间参考）", "confidence": "低",
              "weights": {"dcf": 0.1591, "comps": 0.70, "sotp": 0.1409}},
  "sensitivity": {"wacc_g": {"matrix": [[...]]}, "growth_margin": {"matrix": [[...]]}},
  "gates": [...], "warnings": [...], "sources": [...],
  "excel_path": "valuation/output/600519_2025_估值底稿.xlsx",
  "excel_format": "professional_18_sheets",
  "excel_generated_at": "2026-11-05 22:00:00",
  "presentation": {"narrative": {...}, "charts": {...}}
}
```
