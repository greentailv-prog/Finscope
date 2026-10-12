# INPUT_SCHEMA.md — risk-radar 输入契约

> 本文件是 **Risk Radar 对 financial-diagnosis / 统一数据对象的接口要求**。

---

## 一句话版本

**Risk Radar 只需要 `financial-diagnosis` 的输出，再加上 `meta` 里的两个外部假设。**

它**不直接读年报**，也**不重新计算指标**——所有数字都来自 `ratios`，保证不会因为口径不一致打架。

---

## 调用方式

```bash
cd risk-radar
python scripts/detect_risks.py \
    --ratios <financial-diagnosis 的输出.json> \
    --rules  risk_rules.json \
    [--meta  补充假设.json] \
    --output 输出.json --pretty
```

`--meta` 可选，用于补 `financial-diagnosis` 输出里没有的外部假设（如行业基准、审计意见）。

---

## 输入的必需字段

### 1. `ratios`（✅ 必需）

五类指标，结构见 `../financial-diagnosis/OUTPUT_SCHEMA.md`。
每个指标条目需要：`value` / `prev` / `delta` / `unit` / `formula` / `status`。

> **为什么需要 `unit`**：引擎靠 `unit` 判断这个指标是比率（`ratio`）还是天数（`days`）还是金额（`CNY`），
> 从而决定生成 `_pp`（百分点）还是 `_yi`（亿元）别名。缺 `unit` 会导致模板变量解析失败。

### 2. `derived`（✅ 必需）

按期间的派生量：EBIT / NOPAT / EBITDA / 有息负债 / 短期有息债务 / 净负债 / 投入资本 / 营运资金 / FCF。
引擎用它生成 `ebit_yi`、`interest_bearing_debt_yi` 等金额别名。

### 3. `evidence`（✅ 必需）

原始抽取值 + 出处。引擎用它生成：

- `raw_<字段>` 变量（单位：元）—— 供"存贷双高""分红占现金流"这类需要绝对值口径的规则
- 证据链的「数据」层和「出处」层（年报 source + page）

```jsonc
"evidence": {
  "revenue": { "2025": { "value": 12860000000.0, "unit": "元",
                         "display_value": 128.60, "display_unit": "亿元",
                         "source": "2025年年度报告", "page": 83 } }
}
```

### 4. `attribution`（✅ 必需）

三段归因（杜邦 / 营业利润桥 / 现金流桥）。引擎把 `dupont.contribution` 摊平进变量上下文，
让解释模板能直接引用 `{net_margin_effect_pp}` 这样的归因结论。

### 5. `assumptions`（✅ 必需）

至少要有 `wacc`。缺了的话，`roic_minus_wacc` 相关的规则返回 `not_evaluable`。

### 6. `meta`（⭐ 强烈建议）

| 字段 | 缺失后果 |
|---|---|
| `audit_opinion` | A03（非标审计意见）规则返回 `not_evaluable` |
| `industry_gross_margin_benchmark` | P06（毛利率低于行业中位数）规则返回 `not_evaluable` |

**由 C 从可比公司池统计后回填。**

### 7. `company` / `period`（⭕ 可选）

只用于输出里透传，不参与判断。

---

## 变量命名规则（写规则时必须遵守）

引擎会把输入摊平成一套扁平变量，规则表达式直接引用变量名：

| 变量形式 | 来源 | 生成条件 |
|---|---|---|
| `<key>` | `ratios.<cat>.<key>.value` | 总是 |
| `<key>_prev` | `.prev` | 总是（可能为 null） |
| `<key>_delta` | `.delta` | 总是（可能为 null） |
| `<key>_pp` | `.value × 100` | 仅当 `unit == "ratio"` 或名字含 `growth/margin/ratio/roe/roa/roic/gap/scissors/_effect/…` |
| `<key>_prev_pp` / `<key>_delta_pp` | 同上 | 同上 |
| `<key>_yi` | `.value ÷ 1e8` | 仅当 `unit == "CNY"` 或名字在金额白名单里 |
| `raw_<字段>` | `evidence.<字段>.<当期>.value` | 总是 |
| `<字段>_yi` | `raw_<字段> ÷ 1e8` | 总是 |
| `wacc` | `assumptions.wacc` | |
| `audit_opinion` / `audit_opinion_flag` | `meta.audit_opinion` | flag：标准无保留=0，其他=1 |
| `industry_gross_margin_benchmark` | `meta` | |
| `derived_vars` 里定义的 | 引擎安全求值 | 见 `risk_rules.json` |

> **写规则时不确定变量名？** 加个 `--debug-ctx` 参数就能打印完整变量上下文（v1.1 支持）。
> 当前版本可直接 `python -c "import detect_risks; ..."` 打印，或看 `demo/output_risks.json` 里
> 每条风险的 `trigger_values` 字段——那是引擎实际用到的变量值。

---

## 缺失输入的处理承诺

| 缺失 | 引擎行为 |
|---|---|
| 某个指标为 `null` | 引用它的规则 → `status: "not_evaluable"` → 进 `review_queue`，**不判安全** |
| `ratios` 整个缺失 | 所有规则 `not_evaluable` |
| `evidence` 缺失 | 金额类规则 `not_evaluable`；证据链的「数据」「出处」层为空 |
| `attribution` 缺失 | 证据链的「归因」层为空，风险判断不受影响 |
| 表达式引用了不存在的变量 | 该规则 `not_evaluable`，并在 `review_queue` 里写明缺哪个变量 |

**核心原则**：缺失输入 → 不可评估 → 转人工。**永远不会因为"算不出来"就当成"没问题"。**

---

## 给 D 的提示

如果你把 `financial-diagnosis` 的输出和 Risk Radar 串起来，只需要：

```python
diag = run_extraction_and_diagnosis()          # A → B
risks = run_risk_radar(diag)                   # B 的第二段

unified["ratios"] = diag["ratios"]
unified["risks"]  = risks["risks"]
unified["review_queue"] = diag["review_queue"] + risks["review_queue"]
```

Risk Radar **不需要**再单独喂 `financials`——它已经从 `ratios` + `evidence` 拿到了全部需要的数字。
