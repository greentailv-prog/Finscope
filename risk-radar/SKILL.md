---
name: risk-radar
description: 基于统一接口的 ratios 指标，按 risk_rules.json 的规则库识别财务风险，输出带证据链（数据→计算→年报页码→判断→归因→建议）的风险清单与待核验队列，填统一接口的 data.risks。当需要判断财务风险、触发风险规则、生成风险证据链或风险评分时使用。
version: 1.0.0
owner: B
---

# risk-radar — 财务风险识别与证据链

## 这个 Skill 做什么

输入 `financial-diagnosis` 算好的指标，输出**风险清单 + 每条风险的完整证据链 + 待核验队列**。

它回答三个问题：**有没有风险？证据在哪？下一步该查什么？**

它**不做**的事：不算指标（那是 `financial-diagnosis` 的活）、不做估值、不猜测缺失数据。

## 何时使用

- 拿到了 `ratios` 输出，需要判断这家公司有没有财务风险
- 需要为每条风险给出可追溯到年报页码的证据
- 需要为 E 的前端「风险雷达」页面准备 `data.risks`

## 执行流程

```
ratios 输出 (financial-diagnosis)
        │
        ├─ 1. 建立变量上下文   ── 摊平 ratios / derived / evidence / 归因 / 假设
        ├─ 2. 计算派生变量     ── 应收收入剪刀差、存贷双高分量、分红占现金流…
        ├─ 3. 逐条求值规则     ── 40 条规则，受限 AST 安全求值（不用 eval）
        ├─ 4. 严重度分级       ── 基础档 + escalate 升级档
        ├─ 5. 生成证据链       ── 数据 → 计算 → 出处 → 判断 → 归因 → 建议
        ├─ 6. 待核验队列       ── 算不出来的绝不默认安全
        └─ 7. 综合评分
        │
        ▼
risks 对象（统一接口 data.risks）
```

## 怎么跑

```bash
cd risk-radar
python scripts/detect_risks.py \
    --ratios ../financial-diagnosis/demo/output_ratios.json \
    --rules  risk_rules.json \
    --output demo/output_risks.json --pretty
```

### 指定行业剖面（重要）

不同行业的"正常值"天差地别，**用错口径会大面积误报**。用 `--industry` 指定：

```bash
python scripts/detect_risks.py \
    --ratios cases/icbc-601398/output_ratios.json \
    --rules  risk_rules.json \
    --industry banking \
    -o cases/icbc-601398/output_risks.json --pretty
```

不传 `--industry` 时，引擎会按 `meta.industry_profile` → 公司简称关键词
自动匹配（`_index.json` 的 `match_keywords`）；匹配不上就退回 `general` 通用档，
并往待核验队列里推一条提示，让你知道"行业没认出来，阈值可能是错的"。

输出摘要示例（银行业）：

```
[OK] risks -> cases/icbc-601398/output_risks.json
     行业剖面：banking（银行（货币金融服务 / 商业银行））；--industry 显式指定
     规则 53 条 | 适用 23 | 不适用 30 | 触发 3 (重大 0 / 关注 2 / 提示 1) | 通过 18 | 不可评估 2
     综合风险：低（19.2）  待核验 2 项
       - [关注] B04 资本充足率下滑
       - [关注] B06 净息差收窄
       - [提示] B13 分红率与资本充足率同时承压
```

对照组（同一份数据，误用制造业通用口径）：

```
     规则 40 条 | 适用 40 | 不适用 0 | 触发 2 (重大 1 / 关注 1) | 通过 15 | 不可评估 23
     综合风险：较低（25.9）  待核验 66 项
       - [重大] S01 资产负债率偏高      ← 银行常态 90%+，纯误报
       - [关注] P03 ROE 低于资本成本    ← 银行资本约束是资本充足率，口径错误
```

**同样的公司、同样的数据，换个行业口径，结论从"息差承压的稳健大行"
变成"资产负债率 91.5% 的重大风险企业"。** 这就是为什么行业剖面不是可选项。

## 三条不可违背的规则

1. **算不出来 ≠ 没问题。** 输入缺失 → `status: "not_evaluable"` → 进 `review_queue`，
   绝不当成"通过"。这是投研场景最危险的认知错误。
2. **未触发也要输出。** 每条规则无论触发与否都出现在 `risks` 数组里，
   `status: "passed"` 是在审计意义上告诉读者"这条我查过了，没问题"。
3. **每条触发的风险必须自带完整证据链。** 数据、计算、年报页码、判断、归因、建议，
   六层齐全。前端可以直接按层展开，不需要再回头查任何东西。

> **风险判定的会计权威依据**：谨慎性底线（缺失不判安全）、监管导向（阈值分"越红线"与"低于同业"）、
> 确定性分级（重大/关注/提示对应应当/建议/可能）——见 `RULES.md` 第八节，
> 完整准则 / 监管引用见 `../references/accounting_standards_basis.md`。

## 规则库怎么改

**改 `risk_rules.json`，不要动代码。** 一条规则长这样：

```jsonc
{
  "risk_id": "E01",
  "risk_name": "应收账款增速显著高于收入增速",
  "risk_name_en": "Receivables Growth",
  "category": "efficiency",
  "severity": "medium",                                        // 基础档
  "escalate_to": "high",                                      // 升级档
  "escalate_when": "(accounts_receivable_growth - revenue_growth) > 0.15",
  "trigger": "(accounts_receivable_growth - revenue_growth) > 0.05",
  "threshold": 0.05,
  "trigger_display": "应收账款增速 - 收入增速 > 5pp；超过 15pp 升级为重大",
  "evidence_required": ["revenue", "accounts_receivable"],
  "explanation_template": "应收账款同比增长 {accounts_receivable_growth:.1%}…",
  "suggestions": ["读取'应收账款'附注，按账龄结构看 1 年以上占比是否上升", ...],
  "confidence": 0.9
}
```

**表达式支持**：`+ - * / **`、比较符、 `and` / `or`（带短路）、`abs` / `min` / `max` / `round`。
**不支持**（会直接报错，不会静默执行）：函数调用以外的任何语法、属性访问、下标、lambda、导入。

### 变量从哪来

| 变量形式 | 来源 | 例子 |
|---|---|---|
| `<指标key>` | `ratios` 里的指标 | `dso`、`gross_margin`、`roe` |
| `<指标key>_prev` | 上期值 | `dso_prev` |
| `<指标key>_delta` | 变动值 | `dso_delta` |
| `<指标key>_pp` | 比率类 ×100（百分点） | `gross_margin_delta_pp` |
| `<指标key>_yi` | 金额类 ÷1e8（亿元） | `net_debt_yi`、`ocf_yi` |
| `raw_<字段>` | 原始抽取值（元） | `raw_cash_and_equivalents` |
| `wacc` | `assumptions.wacc` | |
| `audit_opinion_flag` | 标准无保留=0，其他=1 | |

需要新的中间变量，往 `risk_rules.json` 的 `derived_vars` 里加即可。

## 输出结构（贴进统一接口的部分）

```jsonc
{
  "summary": {
    "total_rules": 40, "triggered": 27, "passed": 11, "not_evaluable": 2,
    "by_severity": { "high": 7, "medium": 20, "low": 0 },
    "overall_risk_score": 78.9, "overall_risk_level": "高",
    "top_risks": [...]
  },
  "risks": [
    {
      "risk_id": "E01", "risk_name": "应收账款增速显著高于收入增速",
      "category": "efficiency", "status": "triggered",
      "severity": "high", "severity_tag": "重大", "score": 85,
      "trigger": "(accounts_receivable_growth - revenue_growth) > 0.05",
      "trigger_display": "应收账款增速 - 收入增速 > 5pp；超过 15pp 升级为重大",
      "evidence_required": ["revenue", "accounts_receivable"],
      "explanation": "应收账款同比增长 41.5%，收入增长 14.4%，差额 27.1 个百分点…",
      "suggestions": ["读取'应收账款'附注…", ...],
      "evidence_chain": [ { "step": "数据", ... }, { "step": "计算", ... }, ... ],
      "trigger_values": { "accounts_receivable_growth": 0.415, "revenue_growth": 0.144 },
      "confidence": 0.9
    }
  ],
  "review_queue": [...]
}
```

**给 D 的一句话**：`data.risks` 直接取 `output["risks"]`；`data.review_queue` 需要把 `output["review_queue"]` 合并进去
（它已经包含了 `financial-diagnosis` 的条目，用 `inherited_from` 标记了来源）。

## 证据链的六层（E 前端按这个顺序展开）

| 层 | 内容 |
|---|---|
| 数据 | 触发这条规则用到的原始字段、本期值、上期值、年报页码 |
| 计算 | 触发表达式 + 表达式里各变量的实际值 |
| 出处 | 涉及的年报清单与页码汇总 |
| 判断 | 触发条件的中文描述 + 判定结果 + 严重度 |
| 归因 | 杜邦分解、营业利润桥、现金流桥（直接引用 diagnosis 的结果） |
| 建议 | 下一步该查什么（3-4 条具体动作） |

## 严重度分档

| severity | tag | 含义 | 处理动作 |
|---|---|---|---|
| `high` | 重大 | 已构成实质性财务风险或报表可信度存疑 | 投研简报单列提示，必须追查年报附注原文 |
| `medium` | 关注 | 明确恶化趋势或结构性隐患 | 在归因中解释成因，列入持续跟踪 |
| `low` | 提示 | 偏离常态但未构成风险 | 列为观察项 |

> 分工文档示例里写的 `severity: "attention"` 已统一映射为 `medium`（关注档）。
> D 只需要读 `severity` 字段，不用管历史别名。

## 判断风险时的三条纪律

1. **规则是线索，不是结论。** 尤其是 A02「存贷双高」这类，触发后**必须回到年报附注与资金流水核实**，
   绝不能仅凭指标下结论——误报的代价很高。
2. **行业校准优先于通用阈值。** 现在的 60% / 120 天 / 1.0 倍是**制造业通用档**。
   银行地产的资产负债率、工程设备的 DSO，通用档会大量误报。正式使用必须按行业重设。
3. **演示样本是刻意构造的高风险样本**（最大化规则覆盖）。真实公司通常只触发 3-8 条，
   触发 27 条不代表这家公司"没救了"，只说明规则跑通了。

## 文件导航

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 本文件：怎么用 |
| `INPUT_SCHEMA.md` | 输入契约（我要什么） |
| `OUTPUT_SCHEMA.md` | 输出契约（我给 D / E 什么） |
| `RULES.md` | 风险分级标准、证据链规范、行业差异、误报控制 |
| **`risk_rules.json`** | **规则库本体（40 条通用规则），【分工文档点名要的】** |
| `data/industry_calibration.json` | 行业阈值校准表 |
| `data/industry_profiles/` | **行业剖面（银行业 / 制造业）**：指标屏蔽 + 阈值覆盖 + 专属规则 |
| `scripts/detect_risks.py` | 风险识别引擎 |
| `demo/` | 最小可运行案例（输入 + 输出） |
| `../references/accounting_standards_basis.md` | 风险判定的准则 / 监管依据（与 financial-diagnosis 共享） |
