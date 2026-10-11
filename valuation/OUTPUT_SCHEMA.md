# 输出定义 · 统一 valuation JSON

这是 **C 填进 D 的统一数据对象的那一段**：

```json
{
  "company":   { ... },
  "financials":{ ... },   // A 填
  "ratios":    { ... },   // B 填
  "risks":     [ ... ],   // B 填
  "valuation": {          // ← C 填的就是这个
    "comps": { ... },
    "dcf":   { ... }
  },
  "sources":   [ ... ]
}
```

本模块跑完输出的顶层结构，**可以直接整体放进 `valuation` 字段**；
也额外带了 `blended` / `sensitivity` / `scenarios`，是超出作业基本要求的部分。

金额单位一律为**元**，比率为**小数**。

---

## 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `company` | object | 回显标的公司信息 |
| `as_of` | int | 估值所用最新会计年度 |
| `currency` | string | `CNY` / `USD` |
| `dcf` | object | DCF 结果 |
| `relative` | object | 相对估值结果 |
| `sotp` | object | 分部估值结果（`ok:false, skipped:true` 表示未启用） |
| `blended` | object | 三法融合结论 |
| `sensitivity` | object | WACC × 永续增长率 5×5 矩阵 |
| `scenarios` | object | Bull / Base / Bear |
| `warnings` | string[] | 模型提示，**交付前须逐条复核** |
| `sources` | object[] | 数据来源 |
| `disclaimer` | string | 免责声明 |

---

## dcf

| 字段 | 说明 |
|---|---|
| `ok` | 是否算成功；`false` 时看 `error` |
| `per_share` / `equity_value` | **结论：每股价值 / 股权价值** |
| `enterprise_value` | 企业价值 |
| `wacc` | 折现率 |
| `implied_wacc` | **市场隐含折现率**（反解出让 DCF 等于市值的 WACC）——核心交叉验证 |
| `terminal_growth` / `terminal_growth_cap` | 永续增长率及其市场上限 |
| `revenue_growth_y1` + `_source` | 首年增速及其来源 |
| `ebit_margin` / `da_pct` / `capex_pct` / `nwc_pct` + `_source` | 各项假设及来源 |
| `wacc_block` | WACC 拆解：`risk_free / erp / beta / cost_of_equity / cost_of_debt / tax_rate / equity_ratio / debt_ratio` 及各自来源 |
| `rows` | 逐年明细（`revenue / ebit / nopat / da / capex / delta_nwc / fcff / discount_factor / pv_fcff`） |
| `pv_explicit` / `pv_terminal` | 预测期现值 / 终值现值 |
| `tv_gordon` / `tv_exit` / `tv_base` / `tv_divergence` | 终值的两种算法、中点、及其偏离度 |
| `exit_multiple` + `_source` | 退出倍数取值 |
| `tv_ratio` | 终值占企业价值比例 |
| `cash` / `debt` / `minority_interest` / `preferred_stock` | 桥接到股权价值的各项 |

```json
"dcf": {
  "ok": true, "method": "dcf",
  "per_share": 2646.99, "equity_value": 3.31e12, "enterprise_value": 3.27e12,
  "wacc": 0.0464, "implied_wacc": 0.0831,
  "terminal_growth": 0.025, "terminal_growth_cap": 0.04,
  "revenue_growth_y1": 0.1213, "revenue_growth_y1_source": "历史 CAGR",
  "ebit_margin": 0.6873, "ebit_margin_source": "近三年中位数",
  "tv_gordon": 5.87e12, "tv_exit": 1.12e12, "tv_base": 3.49e12,
  "tv_divergence": 1.361, "tv_ratio": 0.851,
  "rows": [ { "year_index": 1, "revenue": 1.93e11, "ebit": 1.33e11,
              "nopat": 9.95e10, "fcff": 5.86e10, "pv_fcff": 5.73e10 }, ... ]
}
```

## relative（对应作业要求里的 `comps`）

| 字段 | 说明 |
|---|---|
| `ok` | 是否算成功 |
| `peers_used` | 实际使用的可比公司家数 |
| `results[]` | 每个选用倍数的明细 |
| `implied_per_share` | **结论：各倍数隐含每股价值的中位数** |
| `implied_equity_value` | 对应的股权价值 |
| `range_low` / `range_high` | 各倍数结论的区间 |

`results[]` 每项：

| 字段 | 说明 |
|---|---|
| `multiple` / `label` | 倍数代号与中文名 |
| `peer_median` | 同业中位倍数 |
| `adjustment` / `applied_multiple` | 调整幅度与调整后倍数 |
| `metric_basis` / `metric_value` | 对应的财务指标及其取值 |
| `net_debt_deducted` | EV 类倍数扣减的净负债 |
| `implied_equity_value` / `implied_per_share` | 该倍数的隐含结论 |
| `sample_count` | 参与统计的同业家数 |

```json
"relative": {
  "ok": true, "peers_used": 5,
  "implied_per_share": 421.80, "implied_equity_value": 5.28e11,
  "range_low": 5.10e11, "range_high": 8.27e11,
  "results": [
    { "multiple": "pe", "label": "市盈率 PE", "peer_median": 9.69,
      "adjustment": 0.0, "applied_multiple": 9.69,
      "metric_basis": "净利润", "metric_value": 8.53e10,
      "net_debt_deducted": 0.0, "implied_equity_value": 8.27e11,
      "implied_per_share": 660.13, "sample_count": 5 }
  ]
}
```

## sotp

| 字段 | 说明 |
|---|---|
| `ok` / `skipped` | 未启用时为 `false` / `true`，原因见 `reason` |
| `rows[]` | 各分部：`name / metric / value / multiple / segment_ev / peers` |
| `segment_ev_total` | 分部价值合计 |
| `corporate_cost` | 扣减的总部费用 |
| `equity_value` / `per_share` | 结论 |
| `conglomerate_discount` | 集团折价 =（SOTP 价 − 市价）÷ SOTP 价 |

## blended（三法融合）

| 字段 | 说明 |
|---|---|
| `components[]` | 各方法：`key / label / per_share / weight / equity_value` |
| `weight_source` | 权重口径说明 |
| `blended_per_share` / `blended_equity_value` | **最终结论** |
| `current_price` / `upside` | 现价与上行空间（小数） |
| `verdict` | 显著低估 / 低估 / 大致合理 / 高估 / 显著高估 |
| `most_bullish` / `most_bearish` | 最乐观与最保守的方法 |

## sensitivity

```json
"sensitivity": {
  "wacc_axis": [0.0364, 0.0414, 0.0464, 0.0514, 0.0564],
  "growth_axis": [0.015, 0.020, 0.025, 0.030, 0.035],
  "grid": [[null, 3201.2, 3620.5, 4140.1, 4830.9], ...],
  "base_wacc": 0.0464, "base_growth": 0.025, "unit": "每股价值"
}
```

`grid` 中 `null` 表示该格 `WACC ≤ g`，无解。

## scenarios

```json
"scenarios": {
  "bull": {"label":"乐观","per_share":...,"growth_y1":...,"ebit_margin":...,"wacc":...,"levers":"收入增速 +3%、..."},
  "base": {...},
  "bear": {...}
}
```

---

## warnings（交付前必看）

模型自动跑的交叉验证结果，典型条目：

| 提示内容 | 含义 |
|---|---|
| 算出的 WACC 低于/高于市场隐含折现率 N bp | **折现率假设与市场共识的分歧**，必须写进交付说明 |
| 终值两种算法偏离 N%，根因是 WACC − g 只有 N% | 分母太小把 Gordon 终值放大了 |
| 终值占企业价值 N%，超过 85% | 模型实质上是在押倍数扩张 |
| DCF 与相对估值相差 N% | 方法间分歧过大，加权平均参考价值有限 |
| 永续增长率超过市场上限 | 已按上限处理 |

**这些提示不是噪音，是模型在告诉你哪里可能出错。交付时应当逐条回应。**
