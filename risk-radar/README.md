# risk-radar — 怎么用

> FinRadar（财报雷达）B 模块第 2 段：财务风险识别与证据链
> 负责人：B ｜ 上游：`financial-diagnosis` ｜ 下游：D（编排）、E（前端渲染）

---

## 30 秒跑起来

```bash
# 先跑第 1 段（如果还没跑过）
cd ../financial-diagnosis
python scripts/compute_ratios.py -i demo/input_financials.json -o demo/output_ratios.json --pretty

# 再跑第 2 段
cd ../risk-radar
python scripts/detect_risks.py \
    --ratios ../financial-diagnosis/demo/output_ratios.json \
    --rules  risk_rules.json \
    --output demo/output_risks.json --pretty
```

看到这个就成了：

```
[OK] risks -> demo/output_risks.json
     规则 40 条 | 触发 27 (重大 7 / 关注 20 / 提示 0) | 通过 11 | 不可评估 2
     综合风险：高（78.9）  待核验 2 项
       - [重大] C01 净现比偏低，利润缺乏现金支撑
       - [重大] C03 自由现金流连续为负
```

**依赖**：Python 3.9+，零第三方库。

---

## 目录

```
risk-radar/
├── SKILL.md              ← Agent 读这个，知道"怎么做"
├── INPUT_SCHEMA.md       ← 我要什么（就是 diagnosis 的输出）
├── OUTPUT_SCHEMA.md      ← 我给 D / E 什么
├── RULES.md              ← 风险分级标准、证据链规范、误报控制
├── risk_rules.json       ← 40 条规则库本体     【分工文档点名要的】
├── README.md             ← 你正在看这个
├── data/
│   └── industry_calibration.json   ← 行业阈值校准表
├── scripts/
│   └── detect_risks.py             ← 风险识别引擎
└── demo/
    ├── input_analysis.json   ← 演示输入（= diagnosis 的输出）
    └── output_risks.json     ← 【分工文档点名要的：风险输出 JSON】
```

---

## 它做什么

把 40 条财务风险规则跑一遍，每条给出：

- **有没有触发**（`triggered` / `passed` / `not_evaluable`）
- **严不严重**（重大 / 关注 / 提示）
- **凭什么这么说**（六层证据链：数据 → 计算 → 出处 → 判断 → 归因 → 建议）

### 规则覆盖

| 类别 | 数 | ID | 覆盖 |
|---|---|---|---|
| 成长性 | 5 | G01–G05 | 收入下滑、利润下滑、增收不增利、扣非占比、现金流背离 |
| 盈利能力 | 7 | P01–P07 | 毛利率、ROE、ROE vs WACC、ROIC vs WACC、费用率、行业对比 |
| 偿债能力 | 8 | S01–S08 | 杠杆水平与速度、期限错配、利息覆盖、净负债/EBITDA、受限资金 |
| 营运能力 | 7 | E01–E07 | 应收跑赢收入、DSO、存货积压、CCC、周转率 |
| 现金流质量 | 7 | C01–C07 | 净现比、OCF 为负、FCF、资本开支缺口、收现比、融资依赖 |
| 资产质量（扩展） | 4 | A01–A04 | 商誉、存贷双高、非标审计意见、研发资本化 |
| 治理分红（扩展） | 2 | V01–V02 | 分红率、分红超经营现金流 |

> 分工文档示例里那条 `Receivables Growth: AR growth - Revenue growth > 15%` 对应 **E01**，
> 已扩展为「>5pp 关注 / >15pp 重大」两档，并配了完整的证据链与归因。

---

## 演示样本说明（重要）

`demo/` 里的公司是**合成数据**（华衍智能装备股份有限公司，DEMO.SH，专用设备制造业），
**刻意构造成高风险样本**以最大化规则覆盖——收入增长但利润下滑、应收暴增、现金流恶化、加杠杆扩产。

- **触发 27 条不代表真实公司的常态。** 真实公司通常触发 3–8 条。
- 之所以用高风险样本，是为了让中期展示时能看到"规则确实在工作"，而不是一片空白。
- 演示中有 11 条 `passed` 和 2 条 `not_evaluable`，这是**故意保留**的：
  前者证明"查过且无异常"，后者证明"缺数据时不硬判"。这三态一起才是可信的风险系统。

---

## 给 D 的接入方式

```python
diag  = run_diagnosis()               # A → B 第一段
risks = run_risk_radar(diag)          # B 第二段

unified["ratios"] = diag["ratios"]
unified["risks"]  = risks["risks"]    # 直接填 data.risks
unified["review_queue"] = diag["review_queue"] + risks["review_queue"]
```

`data.risks` 不需要字段映射，直接搬。

---

## 给 E 的接入方式

| 页面元素 | 字段 |
|---|---|
| 综合评分 + 等级 | `summary.overall_risk_score` / `overall_risk_level` |
| 重大/关注/提示计数 | `summary.by_severity` |
| 雷达图七个维度 | `summary.by_category` |
| 风险列表（按分排序） | `risks[]` 中 `status=="triggered"`，按 `score` 降序 |
| 展开 → 数据 | `evidence_chain[step=="数据"]` |
| 展开 → 计算 | `evidence_chain[step=="计算"]` 的 `formula` + `values` |
| 展开 → 年报页码 | `evidence_chain[step=="出处"]` 的 `sources` + `pages` |
| 展开 → AI 解释 | `explanation` + `suggestions` |
| 待核验队列 | `review_queue` |

---

## 怎么加一条自己的规则

**改 `risk_rules.json`，不用动代码。** 复制一条现有规则，改这六个字段：

```jsonc
{
  "risk_id": "E08",                                        // 不要和已有的重号
  "risk_name": "我的新规则",
  "category": "efficiency",
  "severity": "medium",
  "escalate_to": "high",                                   // 可选
  "escalate_when": "dso > 200",                            // 可选
  "trigger": "ar_and_inventory_to_assets > 0.50",          // 触发条件
  "trigger_display": "应收与存货合计占总资产 > 50%",        // 中文说明
  "evidence_required": ["accounts_receivable", "inventory", "total_assets"],
  "explanation_template": "应收与存货合计占总资产 {ar_and_inventory_to_assets:.1%}…",
  "suggestions": ["查附注…", "查结构…"],
  "confidence": 0.8
}
```

**表达式支持的语法**：`+ - * / **`、`< > <= >= == !=`、`and` / `or`、`abs` / `min` / `max` / `round`。
其他一律拒绝（引擎用受限 AST 求值，遇到不认识的语法直接报错，不会静默执行）。

**变量怎么取**：`<指标key>` / `_prev` / `_delta` / `_pp`（百分点）/ `_yi`（亿元）/ `raw_<字段>` / `wacc`。
详见 `INPUT_SCHEMA.md` 的「变量命名规则」。

需要新的中间变量，加到 `risk_rules.json` 的 `derived_vars`：

```jsonc
"my_new_var": "raw_inventory / raw_total_assets"
```

---

## 行业校准（正式作业前必做）

`risk_rules.json` 里的 60% / 120 天 / 1.0 倍是**制造业通用档**，直接用到银行地产、工程设备上会大量误报。

两种方式：

1. **推荐**：让 C 统计可比公司分位数，写入 `meta.industry_gross_margin_benchmark` 等字段，
   规则自动读取（缺了就返回 `not_evaluable`，不会瞎猜）。
2. 复制 `risk_rules.json` → `risk_rules_银行.json`，按 `data/industry_calibration.json` 改阈值，
   调用时用 `--rules` 指定。

行业差异要点见 `data/industry_calibration.json`，里面有九个行业的校准建议。

---

## 设计上的三个坚持

1. **算不出来 ≠ 没问题。**
   输入缺失 → `not_evaluable` → 进 `review_queue` 转人工。
   在投研场景里，把"我不知道"说成"没问题"是最危险的。

2. **未触发也要输出。**
   `passed` 是在审计意义上告诉读者"这条我查过了，确实没事"。
   只输出触发项的清单，读者无法区分"没触发"和"没检查"。

3. **规则是线索，不是结论。**
   尤其是 A02「存贷双高」，触发后**必须回到年报附注与资金流水核实**。
   `confidence < 0.8` 的规则触发后一律标记 `needs_human_judgement`，不得直接写进研报的风险提示章节。

---

## 验收对照（分工文档第七节）

| 分工文档对 B 的验收 | 本模块怎么满足 |
|---|---|
| **Skill：怎么判断风险** | `SKILL.md` + `RULES.md` + `risk_rules.json`（40 条，机器可读） |
| **Demo：给一组数据，能触发风险** | `demo/input_analysis.json` → `demo/output_risks.json`，脚本实算，27 条触发 |
| **Interface：输出统一的 risk JSON** | `OUTPUT_SCHEMA.md` + `output_risks.json`，`data.risks` 直接可填 |

## 分工文档第三节要求的目录对照

| 要求 | 实际交付 |
|---|---|
| 两个 SKILL.md | `financial-diagnosis/SKILL.md`、`risk-radar/SKILL.md` |
| `risk_rules.json` | `risk-radar/risk_rules.json` |
| `ratio_formulas.md` | `financial-diagnosis/ratio_formulas.md` |
| `demo/`（风险输出 JSON） | `risk-radar/demo/output_risks.json` |
| `README.md` | 两个包各一份，另加根目录 `B_README.md` |
| （额外）`INPUT_SCHEMA.md` / `OUTPUT_SCHEMA.md` / `RULES.md` / `data/` | 两个包均已齐备 |
