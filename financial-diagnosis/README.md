# financial-diagnosis — 怎么用

> FinRadar（财报雷达）B 模块第 1 段：财务指标计算与诊断
> 负责人：B ｜ 上游：A（`financial-extraction`）｜ 下游：`risk-radar`、C（`valuation`）、D（编排）

---

## 30 秒跑起来

```bash
cd financial-diagnosis
python scripts/compute_ratios.py -i demo/input_financials.json -o demo/output_ratios.json --pretty
```

看到这个就成了：

```
[OK] ratios -> demo/output_ratios.json
     期间: 2025 （对比期 2024）
     指标数: 65   待核验: 0
```

**依赖**：Python 3.9+，零第三方库（只用标准库 `json` / `argparse` / `datetime` / `math`）。

---

## 目录

```
financial-diagnosis/
├── SKILL.md              ← Agent 读这个，知道"怎么做"
├── INPUT_SCHEMA.md       ← A 要给我什么
├── OUTPUT_SCHEMA.md      ← 我给 D 什么
├── RULES.md              ← 会计口径与判断标准
├── ratio_formulas.md     ← 65 个指标的公式手册 + 阈值表 + 归因方法论   【分工文档点名要的】
├── README.md             ← 你正在看这个
├── data/
│   └── ratio_catalog.json    ← 机器可读指标字典（65 个指标）
├── scripts/
│   └── compute_ratios.py     ← 计算引擎（纯函数式，可复算）
└── demo/
    ├── input_financials.json  ← 合成演示数据（三期：2023-2025）
    └── output_ratios.json     ← 实算结果
```

---

## 它算什么

五类共 **65 个指标**，每个都带 `formula` / `inputs` / `prev` / `delta` / `unit` / `status`：

| 类别 | 数量 | 代表指标 |
|---|---|---|
| 成长性 `growth` | 9 | 收入增速、归母净利增速、扣非增速、收入利润剪刀差 |
| 盈利能力 `profitability` | 17 | 毛利率、ROE、ROA、ROIC、四项费用率、扣非占归母比 |
| 偿债能力 `solvency` | 14 | 资产负债率、有息负债率、现金对短期债务覆盖、利息保障倍数、净负债/EBITDA |
| 营运能力 `efficiency` | 12 | DSO、DIO、DPO、CCC、三项周转率 |
| 现金流质量 `cashflow_quality` | 13 | 净现比、收现比、FCF、资本开支/OCF、外部融资依赖度 |

外加 **三段归因**：

- **杜邦分解** → ROE 变动由什么驱动（净利率 / 周转率 / 杠杆，三项严格闭合）
- **营业利润桥** → 利润变动由什么驱动（规模 / 毛利率 / 费用率 / 其他）
- **现金流桥** → 利润与现金的缺口从哪来（应收 / 存货 / 应付 / 折旧摊销 / 减值 / 倒轧）

---

## 给 D 的接入方式（三行）

```python
diag = json.load(open("output_ratios.json"))
unified["ratios"]       = diag["ratios"]            # 直接填 data.ratios
unified["sources"]     += diag["sources"]           # 出处（年报 + 页码）
unified["review_queue"] += diag["review_queue"]     # 待核验队列
```

**注意**：`data.ratios` 里的五类 key（`growth` / `profitability` / `solvency` / `efficiency` / `cashflow_quality`）
与 D 的统一 Schema 完全一致，**不需要做字段映射**。

---

## 给 C 的接入方式

估值需要的输入，B 都已经算好了，**请不要重复计算**：

| C 需要 | 从 B 的哪里取 |
|---|---|
| EBIT / EBITDA | `derived["<当期>"]["ebit"]` / `["ebitda"]`，或 `ratios.profitability.ebit_margin × revenue` |
| NOPAT | `derived["<当期>"]["nopat"]` |
| 净负债（EV 计算） | `ratios.solvency.net_debt.value` |
| 有息负债 | `ratios.solvency.interest_bearing_debt.value` |
| 自由现金流 | `ratios.cashflow_quality.free_cash_flow.value` |
| 资本开支 | `ratios.cashflow_quality.capex.value` |
| 折旧摊销 | `evidence.depreciation_amortization["<当期>"].value` |
| 营运资金 | `ratios.solvency.working_capital.value` |
| 可持续利润率口径 | 用 `ratios.profitability.net_margin_deducted`（扣非口径） |

**C 需要回填给 B 的**：`meta.wacc`、`meta.industry_gross_margin_benchmark`。
填了之后，`roic_minus_wacc` 和 P06 规则才会生效（否则返回 `not_evaluable`）。

---

## 给 E 的接入方式

| E 的页面 | 读 B 的哪里 |
|---|---|
| 2 Company Overview | `ratios.growth.revenue_growth`、`ratios.growth.net_income_parent_growth`、`ratios.profitability.roe` |
| 3 Financial Diagnosis | `ratios` 五个子对象，按 `unit` 决定格式化（`ratio`→百分比，`days`→天，`x`→倍，`CNY`→亿元） |
| 4 Risk Radar | 由 `risk-radar` 提供，但证据链的「数据 / 出处」两层来自 B 的 `evidence` |
| 6 Research Memo | `attribution` 三段，是投研简报"业绩归因"章节的直接素材 |
| 数据可信度提示 | `checks` —— 三表勾稽自检结果，不平项已进 `review_queue` |

---

## 设计上的三个坚持

1. **计算逻辑在代码里，不在模型的脑子里。**
   大模型口算财务比率会错，且无法复现。所有指标由 `compute_ratios.py` 实算，
   同样的输入必然得到同样的输出，可回归测试、可解释、可审计。

2. **不猜数。**
   输入缺失、分母为 0、上期为负 → 一律 `null` + `not_meaningful` + 进 `review_queue`。
   在投研场景里，**编造的数字比缺失的数字危险得多**。

3. **出处留住。**
   每个指标的输入项都能回溯到年报的 `source` + `page`。
   没有出处，风险证据链和"点击展开看原文"就断了——那是这个产品最核心的卖点。

---

## 换一家公司怎么跑

把 `demo/input_financials.json` 复制一份，按 `INPUT_SCHEMA.md` 的字段清单填好三期数据，然后：

```bash
python scripts/compute_ratios.py -i 你的数据.json -o 输出.json --pretty
```

**至少两期**，但**强烈建议三期**——只有三期，`roe` / `roa` / `roic` / 周转率的**上期值**才算得出来，
所有"变化类"风险规则才能生效。

---

## 常见问题

**Q：为什么是 Python 脚本而不是纯 SKILL.md 让大模型照着算？**
分工文档要求 A/B/C 交"可插拔的能力模块"。纯文本 Skill 让大模型自己算比率，结果不可复现、无法回归测试。
脚本 + Skill 的组合才能做到：Agent 知道什么时候调用（`SKILL.md`），调用后拿到确定的结果（`scripts/`）。

**Q：`待核验: 0` 说明什么？**
说明演示数据的口径完整，65 个指标全部算得出来。真实年报跑出来大概率会 > 0，
打开输出 JSON 的 `review_queue` 看缺哪些字段即可。

**Q：我可以改规则吗？**
指标公式改 `scripts/compute_ratios.py` 的 `compute()` 函数，然后重新生成 `data/ratio_catalog.json`。
阈值和触发条件不在这里改，在 `../risk-radar/risk_rules.json`——改那个文件不需要动代码。
