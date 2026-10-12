---
name: financial-diagnosis
description: 把 A 抽取的年报财务数据（financial_data.json）计算成五类财务指标（成长性 / 盈利能力 / 偿债能力 / 营运能力 / 现金流质量）、三段归因与证据回链，输出统一接口的 data.ratios。当用户需要计算财务指标、做业绩归因、分析指标变动原因，或需要 ROE/ROIC/DSO/CCC/净现比等指标时使用。
version: 1.0.0
owner: B
---

# financial-diagnosis — 财务指标计算与诊断

## 这个 Skill 做什么

输入 A 模块从年报里抽出来的财务数据，输出**五类指标 + 三段归因 + 可回溯证据**。
它只做一件事：**把数字算准、把变动说清、把出处留住**。

它**不做**的事：不判断风险（那是 `risk-radar` 的活）、不做估值（那是 `valuation` 的活）、不猜测缺失数据。

## 何时使用

- 拿到了 A 的 `financial_data.json`，需要算出 ROE / ROIC / DSO / CCC / 净现比等指标
- 需要解释「ROE 为什么掉了」「利润为什么下滑」「钱去哪了」
- 需要为 Risk Radar 准备统一格式的 `ratios` 对象

## 执行流程

```
financial_data.json (A 的输出)
        │
        ├─ 1. 单位归一        ── 亿元/万元/千元 → 元
        ├─ 2. 派生量计算      ── EBIT / NOPAT / 有息负债 / 净负债 / 投入资本 / FCF
        ├─ 3. 五类指标计算    ── 65 个指标，每个都带 formula + inputs + prev + delta
        ├─ 4. 三段归因        ── 杜邦分解 / 营业利润桥 / 现金流桥
        ├─ 5. 证据回链        ── 每个字段的年报出处与页码
        └─ 6. 待核验队列      ── 算不出来的全部列出来，绝不静默吞掉
        │
        ▼
ratios 对象（统一接口 data.ratios）
```

## 怎么跑

```bash
cd financial-diagnosis
python scripts/compute_ratios.py \
    --input  demo/input_financials.json \
    --output demo/output_ratios.json --pretty
```

输出摘要示例：

```
[OK] ratios -> demo/output_ratios.json
     期间: 2025 （对比期 2024）
     指标数: 65   待核验: 0
```

## 三条不可违背的规则

1. **不猜数。** 输入缺失或分母为 0 → 输出 `null` + `status: "not_meaningful"` + 进 `review_queue`。
   绝不用行业均值、历史值或"合理假设"填充。这是投研场景，编造的数字比缺失的数字危险得多。
2. **口径必须匹配。** ROE 用归母口径，ROA 用全口径；周转率分母一律用平均余额。详见 `ratio_formulas.md` 第 0 节。
3. **出处必须留住。** 每个指标的输入项都要能回溯到年报的 source + page，否则下游的风险证据链和前端展示都断了。

> **这些规则的会计权威依据**：谨慎性（不猜数）、普通股股东视角（ROE/ROIC 归母基准）、
> 实质重于形式（永续债/优先股分类）、合并报表准则（归母vs少数股东）——见 `RULES.md` 第八节，
> 完整准则 / 监管引用见 `../references/accounting_standards_basis.md`。

## 输出结构（贴进统一接口的部分）

```jsonc
{
  "ratios": {
    "growth":           { "revenue_growth": {"value": 0.144, "prev": null, "delta": null, "unit": "ratio", "formula": "...", "inputs": {...}}, ... },
    "profitability":    { "gross_margin": {...}, "roe": {...}, "roic": {...}, ... },
    "solvency":         { "debt_to_assets": {...}, "cash_to_short_term_debt": {...}, ... },
    "efficiency":       { "dso": {...}, "dio": {...}, "dpo": {...}, "cash_conversion_cycle": {...}, ... },
    "cashflow_quality": { "ocf_to_net_income_parent": {...}, "sales_cash_ratio": {...}, "free_cash_flow": {...}, ... }
  },
  "attribution": { "dupont": {...}, "operating_profit_bridge": {...}, "cash_flow_bridge": {...} },
  "evidence":    { "revenue": {"2025": {"value": ..., "unit": "元", "source": "2025年年度报告", "page": 83}} },
  "review_queue": []
}
```

**给 D 的一句话**：`data.ratios` 直接取 `output["ratios"]`；`data.review_queue` 需要把 `output["review_queue"]` 合并进去。

## 归因怎么读

三段归因回答三个不同层面的问题，不要混用：

| 段 | 回答的问题 | 关键输出 |
|---|---|---|
| 杜邦分解 | ROE 变动由什么驱动？ | `attribution.dupont.contribution` 的三个效应 |
| 营业利润桥 | 利润变动由什么驱动？ | 规模 / 毛利率 / 费用率 / 其他 |
| 现金流桥 | 利润和现金的缺口从哪来？ | 应收、存货、应付各占用多少 |

写投研简报时的标准句式：
> "ROE 下滑 4.5pp，其中净利率拖累 4.98pp；进一步拆营业利润，毛利率下滑是最大拖累项（−3.25 亿），
> 而收入增长本应带来 +1.56 亿的正贡献。利润与现金的缺口中，应收与存货合计占用 28.3 亿。"

## 常见问题

**Q：只有两年数据够吗？**
够跑大部分指标。但 `roe`/`roa`/`roic`/周转率的「上期值」需要 t-2 的资产负债表余额才能算，
所以**强烈建议 A 提供三年数据**（当前期 + 前两期），否则上期对比值为 `null`，变化类风险规则会退化为 `not_evaluable`。

**Q：为什么 ROIC 用归母净资产而不是全部权益？**
因为 EBIT 是全口径的，但股东投入的资本只对应归母部分。若用全部权益，少数股东权益会被重复计入。

**Q：行业基准怎么加？**
在输入的 `meta` 里写 `industry_gross_margin_benchmark` 等字段，Risk Radar 的 P06 规则会自动读取。
不写就返回 `not_evaluable`，不会拍脑袋给结论。

## 文件导航

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 本文件：怎么用 |
| `INPUT_SCHEMA.md` | 输入契约（A 要给我什么） |
| `OUTPUT_SCHEMA.md` | 输出契约（我给 D 什么） |
| `RULES.md` | 会计口径、单位、阈值与异常处理 |
| `ratio_formulas.md` | 65 个指标的公式手册 + 阈值表 + 归因方法论 |
| `data/ratio_catalog.json` | 机器可读指标字典 |
| `scripts/compute_ratios.py` | 计算引擎（纯函数式，可复算） |
| `demo/` | 最小可运行案例（输入 + 输出） |
| `../references/accounting_standards_basis.md` | 口径与阈值的准则 / 监管依据（与 risk-radar 共享） |
