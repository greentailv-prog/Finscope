# OUTPUT_SCHEMA.md — financial-diagnosis 输出契约

> 本文件是 **B 对 D 的接口承诺**。D 只要按这份契约取值，就能填进统一数据对象。
> 完整样例见 `demo/output_ratios.json`。

---

## 一句话版本

**`output["ratios"]` 就是统一接口里的 `data.ratios`，直接搬过去，不用二次加工。**

---

## D 需要的三行代码

```python
diag = json.load(open("output_ratios.json"))

unified["ratios"] = diag["ratios"]              # 五类指标，直接填
unified["sources"] += diag["sources"]           # 出处汇总（年报 + 页码）
unified["review_queue"] += diag["review_queue"] # 待核验队列，合并进去
```

---

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | `finradar.diagnosis/1.0` |
| `generated_at` | string | 生成时间（ISO8601，东八区） |
| `generator` | string | `financial-diagnosis/scripts/compute_ratios.py` |
| `company` | object | 原样透传 |
| `period` | object | `{current, previous, all}` |
| `meta` | object | 输入 meta 原样透传（含 audit_opinion、行业基准） |
| `assumptions` | object | WACC、天数、平均余额口径、单位口径 |
| `derived` | object | 按期间的派生量（EBIT / NOPAT / 有息负债 / 净负债 / 投入资本 / FCF） |
| **`ratios`** | object | **→ `data.ratios`** |
| `attribution` | object | 三段归因 |
| `evidence` | object | 原始值回链（含 source / page），Risk Radar 要用 |
| **`review_queue`** | array | **→ 合并进 `data.review_queue`** |
| `sources` | array | `[{source, pages}]`，供 E 展示 |

---

## `ratios` 结构

五类，与统一 Schema 的 `ratios` 段落**一一对应**：

```jsonc
"ratios": {
  "growth":           { ... },   // A 填 financials，B 填这里
  "profitability":    { ... },
  "solvency":         { ... },
  "efficiency":       { ... },
  "cashflow_quality": { ... }
}
```

### 每个指标条目的固定结构

```jsonc
"gross_margin": {
  "value":  0.230949,                                     // 当期值；不可算时为 null
  "prev":   0.256228,                                     // 上期值；不可算或无 t-2 余额时为 null
  "delta":  -0.025279,                                    // value - prev
  "unit":   "ratio",                                      // ratio | days | x | CNY
  "formula": "(营业收入 - 营业成本) / 营业收入",
  "inputs": { "revenue": 12860000000.0, "cost_of_revenue": 9890000000.0 },
  "higher_is_better": true,                               // null = 无方向性
  "status": "ok"                                          // ok | not_meaningful
}
```

### `unit` 取值含义

| unit | 含义 | 例子 |
|---|---|---|
| `ratio` | 小数比率，`1.0 = 100%` | `gross_margin = 0.2309` → 23.09% |
| `days` | 天 | `dso = 141.2` |
| `x` | 倍数 | `current_ratio = 1.46` |
| `CNY` | 元 | `net_debt = 4680000000.0` |

> **给 E 的提示**：前端展示时按 `unit` 决定格式化方式，不要硬编码。

### `status` 的两种状态

| status | 含义 | E 怎么显示 |
|---|---|---|
| `ok` | 计算成功 | 正常显示数值 |
| `not_meaningful` | 输入缺失 / 分母为 0 / 上期为负 | 显示"不可算"，并关联 `review_queue` 的条目 |

---

## `attribution` 结构（三段归因）

```jsonc
"attribution": {
  "dupont": {
    "current":     { "net_margin": 0.0494, "asset_turnover": 0.6357, "equity_multiplier": 3.0149, "roe": 0.0946 },
    "previous":    { "net_margin": 0.0767, "asset_turnover": 0.6338, "equity_multiplier": 2.8744, "roe": 0.1397 },
    "contribution": {
      "net_margin_effect":     -0.049756,   // 净利率拖累 4.98pp
      "asset_turnover_effect":  0.000272,
      "leverage_effect":        0.004411,
      "roe_delta":             -0.045073    // 三项之和
    }
  },
  "operating_profit_bridge": {
    "delta_operating_profit": -243000000.0,   // 营业利润减少 2.43 亿（单位：元）
    "scale_effect":            156379003.56,
    "gross_margin_effect":    -325088967.97,
    "expense_ratio_effect":   -112809608.54,
    "other_effect":             38519572.95
  },
  "cash_flow_bridge": {
    "net_income": 668000000.0,
    "ocf":        285000000.0,
    "gap":       -383000000.0,
    "items": [ { "item": "净利润", "amount": 668000000.0 }, ... ]
  }
}
```

**金额字段单位一律为「元」**，前端展示时除以 1e8 得亿元。

---

## `evidence` 结构（Risk Radar 的输入）

```jsonc
"evidence": {
  "revenue": {
    "2025": {
      "value": 12860000000.0,          // 归一到「元」
      "unit": "元",
      "display_value": 128.60,         // 年报原文口径
      "display_unit": "亿元",
      "source": "2025年年度报告",
      "page": 83
    },
    "2024": { ... }
  }
}
```

> **给 E 的提示**：展示用 `display_value` + `display_unit`（人类可读），计算用 `value`（元）。

---

## `review_queue` 结构

```jsonc
{
  "type": "uncomputable_ratio",            // uncomputable_ratio | missing_required_field
  "item": "profitability.roic",
  "reason": "missing_or_invalid_input",
  "missing_inputs": ["nopat"],
  "suggested_action": "请回到 A 的抽取结果核对字段口径与页码…"
}
```

D 只需把整个数组合并进 `data.review_queue`；Risk Radar 会把自己的 `not_evaluable` 条目追加在后面，
并用 `inherited_from: "financial-diagnosis"` 标记来源。

---

## `sources` 结构

```jsonc
[ { "source": "2025年年度报告", "pages": [81, 83, 85, 87, 94, 96, ...] } ]
```

E 前端的"出处"面板可以直接渲染这个数组。

---

## 幂等性承诺

**同样的输入必然产生同样的输出**（除 `generated_at` 时间戳外）。
D 可以随时重算、做回归测试、排查口径问题——这是把计算逻辑放在代码里而不是让大模型口算的核心原因。

## 兼容性承诺

| 变更类型 | 影响 |
|---|---|
| 新增指标 | `ratios.<cat>.<新key>`，向后兼容 |
| 修改指标公式 | **会破坏兼容**，必须升 `schema_version` 并同步通知 D |
| 新增 `review_queue` 的 `type` | 向后兼容（D 按 type 分发即可） |
