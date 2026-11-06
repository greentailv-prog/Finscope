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

unified["ratios"] = diag["ratios"]              # 六类指标（含行业专属 banking），直接填
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

六类。前五类与统一 Schema 的 `ratios` 段落**一一对应**；`banking` 只在银行业公司出现，
非银行公司不生成该键：

```jsonc
"ratios": {
  "growth":           { ... },   // A 填 financials，B 填这里
  "profitability":    { ... },
  "solvency":         { ... },
  "efficiency":       { ... },
  "cashflow_quality": { ... },
  "banking":          { ... }    // 仅银行业：净息差 / 不良率 / 拨备覆盖率 / 资本充足率等
}
```

### 每个指标条目的固定结构

```jsonc
"gross_margin": {
  "value":  0.267202,                                     // 当期值；不可算时为 null
  "prev":   0.267669,                                     // 上期值；不可算或缺 t-2 余额时为 null
  "delta":  -0.000467,                                    // value - prev
  "unit":   "ratio",                                      // ratio | days | x | CNY
  "formula": "(营业收入 - 营业成本) / 营业收入",
  "inputs": { "revenue": 458502407000.0, "cost_of_revenue": 335989528000.0 },
  "inputs_prev": { "revenue": 409084266000.0, "cost_of_revenue": 299584935000.0 },
  "higher_is_better": true,                               // null = 无方向性
  "status": "ok",                                         // ok | not_evaluable | not_meaningful
  "name": "毛利率",                                        // 中文指标名，取自 metric_labels.json
  "role": "core",                                         // core | diagnostic
  "source_fields": ["revenue", "cost_of_revenue"],         // 该指标用到的原始科目
  "source_pages": [134]                                   // 上述科目在年报里的印刷页码
}
```

### `role` 怎么分

- `core`：营收增速、归母净利增速、毛利率、归母净利率、加权 ROE、资产负债率、经营现金流收入比、净现比。
- `diagnostic`：其余。

D 的公司概览页不读 `ratios`，只读 `meta.display.overview_financials`；`role` 只影响财务诊断页的分组与排序。

### `unit` 取值含义

| unit | 含义 | 例子 |
|---|---|---|
| `ratio` | 小数比率，`1.0 = 100%` | `gross_margin = 0.2672` → 26.72% |
| `days` | 天 | `dso = 141.2` |
| `x` | 倍数 | `current_ratio = 1.46` |
| `CNY` | 元 | `net_debt = 4680000000.0` |

> **给 E 的提示**：前端展示时按 `unit` 决定格式化方式，不要硬编码。

### `status` 的三种状态

| status | 含义 | 触发条件 | 页面怎么显示 |
|---|---|---|---|
| `ok` | 计算成功 | 输入齐全 | 正常显示数值 |
| `not_evaluable` | 数据不够，**补数据就能算** | 缺科目、分母为 0、缺上期余额 | 显示“不可算”，关联 `review_queue` |
| `not_meaningful` | 口径本身不适用，**补数据也没意义** | 行业口径不成立（如银行算流动比率、非银算净息差） | 显示“不适用”，不关联 `review_queue` |

两者的区别是判定语义：`not_evaluable` 是待补的缺口，`not_meaningful` 是正确的跳过。
`review_queue` 只收前者，`reason` 与状态一一对应。

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
