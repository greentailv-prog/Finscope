# OUTPUT_SCHEMA.md — risk-radar 输出契约

> 本文件是 **Risk Radar 对 D / E 的接口承诺**。
> 完整样例见 `demo/output_risks.json`（40 条规则的实算结果）。

---

## 一句话版本

**`output["risks"]` 就是统一接口里的 `data.risks`，直接搬过去。**

---

## D 需要的三行代码

```python
risks = json.load(open("output_risks.json"))

unified["risks"]        = risks["risks"]                                    # 直接填 data.risks
unified["review_queue"] = diag["review_queue"] + risks["review_queue"]      # 合并待核验队列
unified["summary"].update(risks["summary"])                                 # 可选：风险概览
```

---

## 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | `finradar.risk/1.0` |
| `generated_at` | string | 生成时间 |
| `generator` | string | `risk-radar/scripts/detect_risks.py` |
| `rules_version` | string | 使用的规则库版本 |
| `company` / `period` | object | 透传 |
| `summary` | object | 风险概览（E 的风险雷达页顶部用） |
| **`risks`** | array | **→ `data.risks`** |
| `review_queue` | array | → 合并进 `data.review_queue` |

---

## `summary` 结构

```jsonc
{
  "total_rules": 53,
  "in_scope_rules": 23,               // 适用规则数（启用行业剖面后才有）
  "triggered": 3, "passed": 18, "not_evaluable": 2, "not_applicable": 30,
  "by_severity": { "high": 0, "medium": 2, "low": 1 },
  "by_category": { "growth": {"triggered": 4, "high": 2, "medium": 2, "low": 0}, ... },
  "overall_risk_score": 78.9,
  "overall_risk_level": "高",
  "suggested_action": "投研简报须以'风险提示'开篇，并逐条给出证据链",
  "top_risks": [
    { "risk_id": "C01", "risk_name": "净现比偏低，利润缺乏现金支撑",
      "severity": "high", "severity_tag": "重大", "score": 85 }
  ]
}
```

### 综合评分口径

```
raw = 重大数 × 10 + 关注数 × 4 + 提示数 × 1.5
overall_risk_score = round(100 × raw / (raw + 40), 1)
```

> `not_applicable`（行业口径不适用）**不计入** raw 分。
> 它既不代表有风险，也不代表已检查，把它算进任何一边都会污染评分。

| 分数 | 等级 | 建议动作 |
|---|---|---|
| ≥75 | 高 | 投研简报以"风险提示"开篇 |
| 55–74 | 较高 | 在归因章节解释成因，列入持续跟踪 |
| 35–54 | 中等 | 常规提示，纳入风险清单 |
| 20–34 | 较低 | 观察即可 |
| <20 | 低 | 无需特别提示 |

> 总分只用于排序与快速浏览。**投资决策必须回到单条风险的证据链，不要只看一个数字。**

---

## `risks[]` 每条的结构

### 公共字段（三种状态都有）

```jsonc
{
  "risk_id": "E01",
  "risk_name": "应收账款增速显著高于收入增速",
  "risk_name_en": "Receivables Growth",
  "category": "efficiency",
  "category_label": "营运风险：应收、存货、应付周转与现金转换周期",
  "status": "triggered",            // triggered | passed | not_evaluable | not_applicable
  "severity": "high",               // high | medium | low（未触发时为 null）
  "severity_tag": "重大",           // 重大 | 关注 | 提示
  "score": 85,
  "trigger": "(accounts_receivable_growth - revenue_growth) > 0.05",
  "trigger_display": "应收账款增速 - 收入增速 > 5pp；超过 15pp 升级为重大",
  "threshold": 0.05,
  "evidence_required": ["revenue", "accounts_receivable"],
  "confidence": 0.9
}
```

### `status: "triggered"` 额外字段

```jsonc
{
  "explanation": "应收账款同比增长 41.5%，收入增长 14.4%，差额 27.1 个百分点。应收账款周转天数由 125.0 天升至 141.2 天，延长 16.2 天。",
  "suggestions": ["读取'应收账款'附注，按账龄结构看 1 年以上占比是否上升", "..."],
  "trigger_values": { "accounts_receivable_growth": 0.415049, "revenue_growth": 0.144128 },
  "evidence_chain": [ ... ]          // 见下
}
```

### `status: "passed"` 额外字段

```jsonc
{
  "explanation": "规则已执行，条件不成立，本项无异常。",
  "trigger_values": { "current_ratio": 1.458678 },
  "evidence_chain": []
}
```

> **为什么未触发也要输出**：`passed` 在审计意义上告诉读者"这条我查过了，确实没问题"。
> 只输出触发项的清单，读者无法区分"没触发"和"没检查"。

### `status: "not_evaluable"` 额外字段

```jsonc
{
  "explanation": "无法判定：表达式引用的变量缺失（industry_gross_margin_benchmark），已转人工核验，不做'无风险'假设。",
  "trigger_values": {},
  "evidence_chain": []
}
```

同时在 `review_queue` 里生成一条：

```jsonc
{
  "type": "risk_not_evaluable",
  "item": "P06 毛利率低于行业中位数",
  "reason": "缺失变量：industry_gross_margin_benchmark",
  "missing_inputs": ["industry_gross_margin_benchmark"],
  "severity_if_triggered": "medium",
  "suggested_action": "由 C 从可比公司池计算行业中位数并回写到 meta.industry_gross_margin_benchmark",
  "needs_human_judgement": true
}
```

### `status: "not_applicable"`（v1.1 新增）

由行业剖面判定：该规则在当前行业**口径不成立**，主动跳过。

```jsonc
{
  "status": "not_applicable",
  "skipped_reason": "银行无应收账款，本规则不适用；应收风险改由 B 系列资产质量规则刻画",
  "explanation": "本规则在当前行业剖面（banking）下不适用，已跳过。",
  "evidence_chain": []
}
```

> **不算触发，也不算通过**。语义是"这条规则在银行业没有意义"，
> 与"查过且无异常"（`passed`）区分开——
> 合并统计会让"已检查规则数"虚高。
> 工商银行案例中有 **30 条**规则处于此状态。

---

## `evidence_chain` 六层结构（E 前端按此展开）

分工文档对 E 页面 4「Risk Radar」的要求是：点击展开 **数据 → 计算 → 年报页码 → AI 解释**。
本模块的证据链是它的超集，六层：

```jsonc
[
  { "step": "数据",  "item": "revenue",
    "value": 128.6, "unit": "亿元", "value_cny": 12860000000.0,
    "prev_value": 112.4, "prev_value_cny": 11240000000.0,
    "source": "2025年年度报告", "page": 83 },
  { "step": "数据",  "item": "accounts_receivable", ... },

  { "step": "计算",  "item": "触发表达式",
    "formula": "(accounts_receivable_growth - revenue_growth) > 0.05",
    "values": { "accounts_receivable_growth": 0.415049, "revenue_growth": 0.144128 } },

  { "step": "出处",  "item": "年报来源与页码",
    "sources": ["2024年年度报告", "2025年年度报告"], "pages": [82, 83, 97, 99] },

  { "step": "判断",  "item": "应收账款增速 - 收入增速 > 5pp；超过 15pp 升级为重大",
    "result": "触发", "severity": "medium" },

  { "step": "归因",  "item": "指标变动归因",
    "unit_note": "金额类字段单位为亿元（由元换算），比率类字段为小数",
    "dupont": { "net_margin_effect": -0.049756, "asset_turnover_effect": 0.000272,
                "leverage_effect": 0.004411, "roe_delta": -0.045073 },
    "operating_profit_bridge_yi": { "delta_operating_profit": -2.43, "scale_effect": 1.56,
                                    "gross_margin_effect": -3.25, "expense_ratio_effect": -1.13,
                                    "other_effect": 0.39 },
    "cash_flow_bridge_items_yi": [ { "item": "净利润", "amount_yi": 6.68 }, ... ],
    "cash_gap_yi": -3.83 },

  { "step": "建议",  "item": "下一步动作",
    "actions": ["读取'应收账款'附注，按账龄结构看 1 年以上占比是否上升", "..."] }
]
```

> **给 E 的提示**：`数据` 层用 `value` + `unit`（年报原文口径，人类可读），
> 需要参与计算时用 `value_cny`（归一到元）。

---

## `review_queue` 结构

```jsonc
[
  { "type": "risk_not_evaluable", "item": "A04 研发投入资本化率异常",
    "reason": "缺失变量：rd_capitalization_ratio",
    "missing_inputs": ["rd_capitalization_ratio"],
    "severity_if_triggered": "medium",
    "suggested_action": "本条需要 A 补充抽取 rd_capitalized（开发支出本期增加额）字段，缺失时不可评估",
    "needs_human_judgement": true },
  { "type": "missing_required_field", "item": "...", "inherited_from": "financial-diagnosis" }
]
```

`inherited_from: "financial-diagnosis"` 标记这条是从指标计算阶段继承过来的。

---

## E 前端的字段映射速查

| E 的页面元素 | 读 B 的哪里 |
|---|---|
| 风险雷达顶部：综合评分 + 等级 | `summary.overall_risk_score` / `overall_risk_level` |
| 风险点数量：重大 / 关注 / 提示 | `summary.by_severity` |
| 风险点列表 | `risks[]` 中 `status == "triggered"` 的项，按 `score` 降序 |
| 雷达图各维度 | `summary.by_category`（七个类别各自的触发数） |
| 点击展开 → 数据 | `evidence_chain` 里 `step == "数据"` 的项 |
| 点击展开 → 计算 | `step == "计算"` 的 `formula` + `values` |
| 点击展开 → 年报页码 | `step == "出处"` 的 `sources` + `pages` |
| 点击展开 → AI 解释 | `explanation`（模板渲染好的）+ `suggestions` |
| 待核验队列 | `review_queue` |

---

## 幂等性承诺

同样的 `ratios` 输入 + 同样的 `risk_rules.json` → 同样的输出（除 `generated_at`）。
规则库改了，`rules_version` 会跟着变，D 可以做版本校验。

## 兼容性承诺

| 变更类型 | 影响 |
|---|---|
| 新增规则 | `risks[]` 多一项，`summary.total_rules` 变化，向后兼容 |
| 修改某条规则的 `risk_id` | **破坏兼容**，E 若有硬编码映射会失效 |
| 修改严重度分档 | 向后兼容（`severity` 取值集合不变） |
| 新增 `status` 取值 | **破坏兼容**，需升 `schema_version` |
