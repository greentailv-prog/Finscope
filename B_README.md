# B 部分交付包 — 财务指标计算 + 财务风险诊断

> FinRadar（财报雷达）｜负责人：B
> 上游 A（`financial-extraction`）→ **本包** → 下游 `risk-radar`（自含）→ C（`valuation`）→ D（编排）→ E（前端）

---

## 一、交付清单（对照分工文档第三节与第七节）

### 分工文档点名要求的文件，全部齐备

| 要求 | 位置 | 状态 |
|---|---|---|
| 两个 SKILL.md | `financial-diagnosis/SKILL.md`、`risk-radar/SKILL.md` | ✅ |
| `risk_rules.json` | `risk-radar/risk_rules.json`（40 条） | ✅ |
| `ratio_formulas.md` | `financial-diagnosis/ratio_formulas.md`（65 指标 + 阈值表 + 归因法） | ✅ |
| `demo/`（风险输出 JSON） | `risk-radar/demo/output_risks.json` | ✅ |
| `README.md` | 两个包各一份 + 本文件 | ✅ |

### 分工文档第三节要求的统一结构，也全部补齐

| 要求 | financial-diagnosis | risk-radar |
|---|---|---|
| `SKILL.md` | ✅ | ✅ |
| `INPUT_SCHEMA.md` / `OUTPUT_SCHEMA.md` | ✅ | ✅ |
| `RULES.md` | ✅ | ✅ |
| `demo/`（input + output） | ✅ | ✅ |
| `data/` | ✅ `ratio_catalog.json` | ✅ `industry_calibration.json` |
| `README.md` | ✅ | ✅ |

### 额外加的东西（超出要求，但让 D 更好接）

- **`scripts/` 可执行引擎**：指标与风险都是**代码实算**的，不是大模型口算的。同样的输入必然同样的输出，可复算、可回归测试。
- **`B_demo_dashboard.html`**：单文件可视化看板，双击即开，中期展示直接用。
  **指标总览里的每一行都可点击**，展开后显示该指标的计算公式、代入数据（本期 / 上期对照）与年报出处页码，可逐项复算。
- **`run_demo.sh`**：一条命令跑通全流程。
- **`scripts_check_coverage.py`**：覆盖度自检，一键区分「行业口径不适用」与「真的缺数据」。

### v1.1 新增（回应三个关键问题）

| 新增 | 位置 | 回应 |
|---|---|---|
| **年报自动抓取模块** | `report-fetcher/` | 问题 1：给代码就能拉年报，已实跑验证 |
| **行业自适应阈值** | `risk-radar/data/industry_profiles/` | 问题 2：支持指标屏蔽 / 阈值覆盖 / 行业专属规则 |
| **真实公司案例** | `cases/icbc-601398/` | 问题 3：工商银行 2023–2025，数据可回溯到页码 |

---

## 二、一分钟跑通全流程

```bash
cd 财报雷达
bash run_demo.sh
```

或者手动两步：

```bash
cd financial-diagnosis
python scripts/compute_ratios.py -i demo/input_financials.json -o demo/output_ratios.json --pretty

cd ../risk-radar
python scripts/detect_risks.py \
    --ratios ../financial-diagnosis/demo/output_ratios.json \
    --rules  risk_rules.json \
    --output demo/output_risks.json --pretty
```

预期输出：

```
[OK] ratios -> demo/output_ratios.json
     期间: 2025 （对比期 2024）
     指标数: 65   待核验: 0

[OK] risks -> demo/output_risks.json
     规则 40 条 | 触发 27 (重大 7 / 关注 20 / 提示 0) | 通过 11 | 不可评估 2
     综合风险：高（78.9）  待核验 2 项
```

**依赖**：Python 3.9+，**零第三方库**。

### 真实案例（工商银行，推荐在汇报时用这个）

```bash
cd cases/icbc-601398
bash run_case.sh
```

产出 `output_ratios.json` / `output_risks.json` / `output_risks_generic.json`（口径误用对照组）/
`dashboard.html`。数据来自巨潮公开披露的年报 PDF，逐项与年报披露值核对通过。

---

## 三、目录结构

```
财报雷达/
├── B_README.md                    ← 本文件（交付总说明）
├── run_demo.sh                    ← 一键跑通全流程
├── B_demo_dashboard.html          ← 单文件可视化看板（双击即开）
│
├── financial-diagnosis/           ← B 的第 1 段：指标计算
│   ├── SKILL.md  INPUT_SCHEMA.md  OUTPUT_SCHEMA.md  RULES.md  README.md
│   ├── ratio_formulas.md          ← 【分工文档点名】公式手册
│   ├── data/ratio_catalog.json    ← 65 个指标的机器可读字典
│   ├── scripts/compute_ratios.py  ← 计算引擎
│   └── demo/input_financials.json → demo/output_ratios.json
│
├── risk-radar/                    ← B 的第 2 段：风险诊断
│   ├── SKILL.md  INPUT_SCHEMA.md  OUTPUT_SCHEMA.md  RULES.md  README.md
│   ├── risk_rules.json            ← 【分工文档点名】40 条通用规则库
│   ├── data/
│   │   ├── industry_calibration.json
│   │   └── industry_profiles/     ← 【v1.1 新增】行业自适应阈值
│   │       ├── _index.json        剖面索引（关键词→行业 自动匹配）
│   │       ├── banking.json       银行业：屏蔽 36 指标 + 阈值覆盖 + 13 条专属规则
│   │       └── manufacturing.json 制造业：通用档基线
│   ├── scripts/detect_risks.py    ← 风险识别引擎
│   └── demo/input_analysis.json → demo/output_risks.json
│
├── report-fetcher/                ← 【v1.1 新增】年报自动抓取
│   ├── SKILL.md  README.md
│   ├── data/industry_hint.json    行业粗判词表
│   ├── scripts/fetch_report.py    检索 + 下载 + 三重校验（零依赖）
│   └── demo/output_manifest.json  工行真实抓取清单
│
└── cases/                         ← 【v1.1 新增】真实公司案例
    └── icbc-601398/              中国工商银行 2023–2025
        ├── input_financials.json  从年报抽取，带页码出处
        ├── output_ratios.json     88 个指标实算结果
        ├── output_risks.json      银行业口径诊断
        ├── output_risks_generic.json  对照组（误用制造业口径）
        ├── dashboard.html         可视化看板
        └── run_case.sh            一键复算
```

> **放到 GitHub 时的目录映射**（分工文档第八节的团队结构）：
> `financial-diagnosis/` → `01_Skills/Financial_Diagnosis/`
> `risk-radar/` → `01_Skills/Risk_Radar/`

---

## 四、我填统一数据对象的哪两块

分工文档第四节定义的统一对象里，**B 负责 `ratios` 和 `risks` 两个字段**：

```jsonc
{
  "company": { ... },              // D 定义，A 补全
  "financials": { ... },           // A 填
  "ratios": {                      // ← B 填（financial-diagnosis）
    "growth": {}, "profitability": {}, "solvency": {},
    "efficiency": {}, "cashflow_quality": {}
  },
  "risks": [ ... ],                // ← B 填（risk-radar）
  "valuation": { ... },            // C 填
  "sources": [ ... ],              // A 主导，B 追加
  "review_queue": [ ... ]          // A/B 共同写入
}
```

### D 只要这三行

```python
diag  = json.load(open("output_ratios.json"))
risks = json.load(open("output_risks.json"))

unified["ratios"] = diag["ratios"]
unified["risks"]  = risks["risks"]
unified["review_queue"] = diag["review_queue"] + risks["review_queue"]
```

**五类 key 与统一 Schema 完全一致，不需要字段映射。**

---

## 五、对其他四个人的对接请求

### 给 A（@A）

1. **请给三期数据。** 只有两期的话，`roe` / `roa` / `roic` / 周转率的**上期值**算不出来（需要 t-2 的资产负债表余额做分母），所有"变化类"风险规则会退化成 `not_evaluable`。
2. **页码必须给。** 没有页码，风险证据链和 E 的"点击展开看原文"就断了——那是整个产品最核心的卖点。
3. **字段清单在 `financial-diagnosis/INPUT_SCHEMA.md`**，里面有 ✅ 必需 / ⭐ 建议 / ⭕ 可选 三级标注。跑之前可以先用我的脚本自检：
   ```bash
   python scripts/compute_ratios.py -i <你的json> -o /tmp/check.json --pretty
   # 看 "待核验: N"，打开 /tmp/check.json 的 review_queue 就知道缺什么
   ```

### 给 C（@C）

1. **请回填两个数给我**：`meta.wacc` 和 `meta.industry_gross_margin_benchmark`。
   填了之后 `roic_minus_wacc` 与 P06 规则才会生效，否则返回 `not_evaluable`。
2. **你要的估值输入我已经算好了，请不要重复计算**：
   EBIT / EBITDA / NOPAT / 净负债 / 有息负债 / FCF / 资本开支 / 营运资金 —— 见 `financial-diagnosis/README.md` 的「给 C 的接入方式」对照表。
3. **我的风险结论会传导给你**：ROIC < WACC → 建议下修成长性假设；流动性紧张（S03）→ 建议加入再融资失败情景。
   这些写在规则 `suggestions` 里，用「向 C 明确：」开头，可以 grep 出来。

### 给 D（@D）

1. 调用顺序：`financial-extraction` → **`financial-diagnosis`** → **`risk-radar`** → `valuation` → `report`。
2. 我的两个模块都是**纯 Python 脚本**，无第三方依赖，用 `subprocess` 或 `exec` 调用都行，输入输出都是 JSON 文件。
3. `review_queue` 记得**合并**两段的（`diag["review_queue"] + risks["review_queue"]`），我这边已经用 `inherited_from` 标记了来源。

### 给 E（@E）

1. **只读不写，不重新判断。** 风险等级、严重度都由我这边给全。
2. 页面 3「Financial Diagnosis」读 `ratios`（按 `unit` 决定格式化：`ratio`→百分比，`days`→天，`x`→倍，`CNY`→亿元）。
3. 页面 4「Risk Radar」读 `risks[]`，证据链的六层（`数据 → 计算 → 出处 → 判断 → 归因 → 建议`）已经按你要的展开顺序排好，直接渲染即可。
4. **`B_demo_dashboard.html` 可以直接当参考实现**，里面的配色、卡片布局、证据链展开交互都能抄。

---

## 六、演示样本说明（重要，避免被误解）

`demo/` 里的公司（华衍智能装备股份有限公司，DEMO.SH，专用设备制造业）是 **合成数据**，
**刻意构造成高风险样本**以最大化规则覆盖：收入增长但利润下滑、应收暴增、现金流恶化、加杠杆扩产。

> **v1.1 补充**：合成样本只用于演示规则覆盖；**真实公司案例请看 `cases/icbc-601398/`**
> （中国工商银行 2023–2025，数据取自巨潮公开披露年报，逐项与年报披露值核对通过）。
> 汇报时建议以真实案例为主，合成样本只用来说明"规则跑得通"。

- **触发 27 条不代表真实公司的常态。** 真实公司通常触发 3–8 条。
- 演示里保留了 **11 条 `passed`** 和 **2 条 `not_evaluable`**，这是故意的：
  - `passed` 证明"这条我查过了，确实没事"；
  - `not_evaluable` 证明"缺数据的时候我不硬判"。
  - 三态齐全才是可信的风险系统，只有一片红色反而是不可信的。

---

## 七、三个关键问题的回答

> 这一节是新增的。它对应三个直指交付包边界的提问，逐个给结论，并附上能复现的证据。

---

### 问题 1 · 能不能自己爬取公司财报，还是只能手动上传？

**结论：能自动抓取，而且已经实跑通过；手动上传仍然是并存的另一条入口。**

新增了第三个模块 **`report-fetcher/`**，专门做这件事。它只访问**巨潮资讯网**（证监会指定的上市公司
信息披露平台）的**无需登录的公开查询接口**，不绕过任何鉴权、不使用非公开接口、不抓取需会员权限的内容。

流程是三步：

```
① 证券代码 / 简称  ──►  /new/information/topSearch/query  ──►  orgId
② orgId + 年报类别 ──►  /new/hisAnnouncement/query        ──►  公告列表
③ adjunctUrl       ──►  static.cninfo.com.cn            ──►  PDF 落地
```

实跑结果（工商银行）：

```
[OK] manifest -> report-fetcher/demo/output_manifest.json
     601398 工商银行 | 命中公告 6 | 选用 3 | 下载成功 3
     覆盖会计年度：[2025, 2024, 2023]（满足平均余额口径）
       - 601398_2025_annual_report.pdf  9.3MB  408页  sha256=e2edab73…
       - 601398_2024_annual_report.pdf  9.9MB  410页  sha256=27b9c08e…
       - 601398_2023_annual_report.pdf  9.5MB  394页  sha256=e310e8a5…
```

可靠性不是靠嘴说的，是靠三重校验 + 幂等 + 限流堆出来的：

| 机制 | 做法 |
|---|---|
| 三重校验 | PDF 魔数 `%PDF-` → SHA256 → 页数 |
| 幂等 | 已存在且 SHA256 一致则跳过（已验证复跑不重复下载） |
| 重试 | 每步最多 3 次，退避 1.5s / 3s |
| 限流 | 请求间隔可配，默认 1 秒 |
| 失败可见 | 失败一律 `status != ok` 且进 `errors[]`，**绝不当作成功** |

**与手动上传的关系**：两条路并存，最终都汇到同一个 `input_financials.json`。
下游引擎完全不关心数据是抓来的还是传来的——**入口不同，契约相同**。

顺带一个关键设计：`--years` 默认 3 不是随手定的。因为周转率、回报率的分母
一律用**平均余额** = (期末+期初)/2，还要再算上期做同比，
所以 `N 期数据 → 能算 N-1 期指标 → 能算 N-2 期同比`。不足 3 期时缺期指标自动转待核验，
绝不拿期末数当分母糊弄。

---

### 问题 2 · 风险阈值怎么定的，能否结合行业情况？

**结论：能做，已经做了。而且这不是锦上添花——用错行业口径会把一家稳健大行判成重大风险。**

#### 原来的做法（v1.0）

阈值写死在规则里，取制造业通用经验档：资产负债率 60%、DSO 120 天、利息保障倍数 1.0 倍……
对制造业没问题，**对银行全面失效**。

#### 现在的做法（v1.1）：行业剖面机制

新增 `risk-radar/data/industry_profiles/`，每个行业一个 JSON，三层能力：

```
industry_profiles/
├── _index.json        剖面索引：关键词 → profile_id 自动匹配
├── banking.json       银行业：屏蔽不适用指标 + 阈值覆盖 + 13 条专属规则
└── manufacturing.json 制造业：通用档基线
```

**第一层：指标适用性屏蔽**
银行业剖面列出 `metrics_not_applicable`，把毛利率、应收周转、存货周转、流动比率、
利息保障倍数、自由现金流等 **36 个**在银行语境下不成立的指标标记为不适用，
不计算、不进待核验队列。

**第二层：阈值覆盖**
同一条规则在不同行业用不同阈值，无需改代码：

```jsonc
"threshold_overrides": {
  "S01": { "debt_to_assets": 0.95 }   // 银行 95%，制造业 60%
}
```

**第三层：行业专属规则**
银行业追加 13 条：资本充足率下滑、核心一级资本缓冲、不良率上升、
不良与拨备双降、净息差收窄、信用成本上升、存款增速匹配度、RWA 收益率……

**第四层：监管底线与同业水平分离**
银行业剖面里带 `regulatory_basis`，明确把"低于监管红线"和"低于同业均值"区分开：

| 项目 | 数值 | 性质 |
|---|---|---|
| 拨备覆盖率底线 | 150%（差异化可调至 120%–150%） | 监管要求 |
| 贷款拨备率底线 | 2.5% | 监管要求 |
| 核心一级资本充足率底线 | 8.25%（工行 G-SIB 第三组，附加 0.75%） | 监管要求 |
| 资本充足率底线 | 11.25% | 监管要求 |

**越线是合规问题，低于同业是竞争问题——这两件事的风险含义完全不同。**

#### 实证：同一家公司，两种口径

拿工商银行真实数据跑了两遍，唯一变量是行业剖面：

| | 银行业剖面（正确） | 制造业通用口径（误用） |
|---|---|---|
| 规则总数 | 53（40 通用 + 13 专属） | 40 |
| 适用规则 | 23 | 40 |
| 不适用（正确屏蔽） | **30** | 0 |
| 触发 | 3（重大 0 / 关注 2 / 提示 1） | 2（**重大 1** / 关注 1） |
| 不可评估 | 2 | 23 |
| 待核验项 | **2** | **66** |
| 综合风险 | 低（19.2） | 较低（25.9） |

误用口径触发的两条：

- **S01 资产负债率偏高（重大）** —— 91.5% 远超 60% 阈值。
  但银行资产负债率常态就在 90% 以上，**这是纯误报**。
- **P03 ROE 低于资本成本（关注）** —— 用 WACC 当资本成本。
  但银行的"资本"约束来自资本充足率，不是 WACC，**口径错误**。

正确口径下触发的三条：

- **B04 资本充足率下滑（关注）** —— 18.76%，同比 −0.63pp
- **B06 净息差收窄（关注）** —— NIM 1.28%，同比 −14BP
- **B13 分红率与资本充足率同时承压（提示）** —— 分红率 35.86% 且资本充足率下降

**同样是工行，同一份数据，换个口径，结论从"息差承压的稳健大行"
变成"资产负债率 91.5% 的重大风险企业"。**

#### 诚实的边界

当前银行业剖面的阈值来自**公开监管规则与公开行业统计均值**，
**不是我们自己跑可比公司分位数算出来的**。
manifest 里用 `benchmarks_calibrated: false` 明确标注了，没有伪装成已校准。

要真正做到"结合行业情况"，需要 C 从可比公司池给出分位数（P25 / P50 / P75），
填进 `meta.industry_*_benchmark` 字段，重算即可——**改数据不改代码**。

---

### 问题 3 · 财务数据是你编的，我要一个真实公司的

**结论：已换成真实公司——中国工商银行（601398.SH），数据全部来自巨潮公开披露的年报 PDF，逐项与年报披露值核对通过。**

新增 `cases/icbc-601398/`：

| 文件 | 说明 |
|---|---|
| `input_financials.json` | 从年报 PDF 抽取的三期真实数据，每个字段带 `source` + `page` |
| `output_ratios.json` | 指标引擎实算结果（88 个指标，待核验 0） |
| `output_risks.json` | 银行业剖面下的风险诊断 |
| `output_risks_generic.json` | 对照组（误用制造业口径） |
| `dashboard.html` | 可视化看板 |
| `run_case.sh` | 一键复算 |

### 真实性是怎么保证的

**① 数据来自公开披露文件，不是模型生成的**

年报 PDF 直接从巨潮资讯网下载（`report-fetcher` 干的活），
SHA256 记录在 manifest 里。抽取过程用 `pdfplumber` 定位表格，人工核对科目与页码。

> 顺带说个坑：2025 年报内嵌的是**子集字体**，`pypdf` 抽中文会乱码（数字正常）。
> 换成 `pdfplumber` 后正确解码。这也是为什么抽取环节不能只依赖单一解析库。

**② 每个数值都能回溯到页码**

```jsonc
"nim": {
  "2025": {
    "value": 0.0128, "unit": "ratio",
    "display_value": 0.0128, "display_unit": "ratio",
    "source": "2025年度报告 财务概要（净利息收益率）",
    "page": 11
  }
}
```

打开年报第 11 页，就能找到这个数。**不是"AI 说的"，是"年报写的，在第 11 页"。**

**③ 关键指标与年报披露值逐项比对**

| 指标 | 引擎算出 | 年报披露 | 状态 |
|---|---|---|---|
| 平均总资产回报率 | 0.72% | 0.72% | ✅ |
| 加权平均净资产收益率 | 9.51% | 9.45% | ✅ 口径一致，差异来自加权时点 |
| 成本收入比 | 28.05% | 28.05% | ✅ |
| 手续费及佣金净收入占比 | 13.26% | 13.26% | ✅ |
| 净利息收益率 | 1.28% | 1.28% | ✅ |
| 不良贷款率 | 1.31% | 1.31% | ✅ |
| 拨备覆盖率 | 213.60% | 213.60% | ✅ |
| 资本充足率 | 18.76% | 18.76% | ✅ |
| 核心一级资本充足率 | 13.57% | 13.57% | ✅ |
| 总权益对总资产比率 | 7.99% | 7.99% | ✅ |
| 风险加权资产占总资产比率 | 52.86% | 52.86% | ✅ |

**④ 审计意见是外部机构出的，不是我们判断的**

安永华明会计师事务所，**标准无保留意见**。这一条直接作为风险规则的输入，
是外部事实，不是我们的估计。

**⑤ 缺的数据就承认缺，不编**

两条依赖 WACC 的规则（P03、B12）因为没有合理的资本成本输入，
状态是 `not_evaluable` 并进待核验队列。**没有随手填一个看起来合理的数字**——
填了就无法分辨哪里是判断、哪里是编造。

---

## 八、中期展示（10/13）的 3 分钟演示脚本

```bash
# 真实案例（主讲用这个）
cd cases/icbc-601398 && bash run_case.sh
open cases/icbc-601398/dashboard.html

# 合成样本（用来说明规则覆盖范围）
bash run_demo.sh
open B_demo_dashboard.html
```

**讲解顺序（建议以真实案例为主线）**：

1. **"数据是真的，出处能翻到页码。"**（40s）
   展示工商银行看板：2023 / 2024 / 2025 三期真实年报数据。
   点开任意指标看 `source` + `page`——比如 NIM 1.28% 在 2025 年报第 11 页。
   > 关键论点：不是"AI 总结的财报"，是"年报原文写的，在第 11 页，你自己翻"。

2. **"指标能对上年报披露值。"**（30s）
   逐项比对：ROA 0.72% vs 披露 0.72%、成本收入比 28.05% vs 28.05%、
   不良率 1.31%、拨备覆盖率 213.60%、资本充足率 18.76% —— **全部一致**。
   > 关键论点：引擎算出来的数能跟会计师审过的数对上，这才是能用的工具。

3. **"行业口径错了，结论就全错了。"**（60s）★ 本场最有说服力的一段
   同一份工行数据跑两遍，只有一个变量不同：
   - **银行业剖面**：53 条规则，正确屏蔽 30 条不适用，触发 3 条（关注 2 / 提示 1），待核验 2 项 → **"低风险，息差承压"**
   - **制造业通用口径**：触发 2 条，其中 **S01 资产负债率 91.5% 判为重大**，待核验 66 项 → **"重大风险企业"**

   > 关键论点：银行资产负债率常态就在 90% 以上，用制造业 60% 的阈值判它是重大风险，
   > 是彻头彻尾的误报。**行业自适应阈值不是加分项，是必需品。**

4. **"年报能自动抓，不用手动传。"**（30s）
   ```bash
   python3 report-fetcher/scripts/fetch_report.py --code 601398 --years 3 -o /tmp/m.json
   ```
   展示实跑输出：命中 6 条公告、下载 3 份、各带 SHA256 与页数。
   > 关键论点：入口自动化，下游契约不变——抓来的和传来的，走同一条流水线。

5. **"缺数据的时候我不瞎说。"**（30s）
   展示 P03 / B12 两条 `not_evaluable`（缺 WACC）与待核验队列。
   > 关键论点：在投研场景里，把"我不知道"说成"没问题"是最危险的。

---

---

## 九、已知限制与下一步

### 已在 v1.1 解决

| 原限制 | 解决方式 |
|---|---|
| 只能手动上传年报 | 新增 `report-fetcher/`，按代码自动检索并下载（已实跑验证） |
| 行业阈值写死、跨行业误报 | 新增 `industry_profiles/` 行业剖面机制（已用工行实证） |
| 演示数据是合成的 | 新增 `cases/icbc-601398/` 真实公司案例 |

### 仍然存在的限制

| 限制 | 影响 | 下一步 |
|---|---|---|
| **行业阈值未做统计校准** | 银行业剖面的阈值取自公开监管规则与公开行业均值，**未用可比公司分位数算过**。已用 `benchmarks_calibrated: false` 显式标注，没有伪装成已校准 | 等 C 提供可比公司池的 P25/P50/P75，填进 `meta.industry_*_benchmark` 后重算，**无需改代码** |
| **WACC 仍缺失** | P03 / B12 两条规则 `not_evaluable` | 等 C 的 WACC 模型。**没有随手填一个看起来合理的数** |
| **只有两个行业剖面** | 目前只有 banking / manufacturing | 按同一份剖面 schema 继续加：地产、券商、保险、医药、零售 |
| **只覆盖 A 股** | 港股、美股、新三板不在范围内 | 需接入其他公开披露渠道 |

### v1.2 已补齐：三表勾稽自检

上一版 `RULES.md` 写了规则但代码没实现，这一版落地了，落在指标输出的 `checks` 节点：

- **资产负债表平衡**：总资产 = 总负债 + 归母股东权益 + 少数股东权益（逐期）
- **利润表勾稽①**：利润总额 − 所得税费用 = 净利润（逐期）
- **利润表勾稽②**：净利润 − 归母净利润 = 少数股东损益，**与附注独立披露值比对**（逐期）
- **现金净变动**：期末现金 − 期初现金 = 经营 + 投资 + 筹资 + 汇率影响（相邻期之间）

容差 1%，不平则进 `review_queue`。看板新增「三表勾稽」标签页，可点击展开每一项的代入数据与年报出处。
回归测试 `scripts_test_checks.py`：注入已知失衡，断言能被抓出（19 项断言）。

**过程中被测试抓出的两个真问题**（都记在 `financial-diagnosis/RULES.md` 第七节）：

1. 利润表②若用倒轧的少数股东损益，恒等式退化成 `A + (B − A) ≡ B`，**恒真、抓不到错**。
   → 改为只在附注独立披露时才判定，否则判"无法勾稽"。
2. 演示样本的现金流本来就差 1500 万，之前没人发现。→ 已修正合成数据使其内部自洽。

---

## 十、命名说明（提请注意）

分工文档（10/02 版）里项目叫 **FinScope**，但你在需求描述里说的是 **FinRadar（财报雷达）**，
工作区目录也是「财报雷达」。

本交付包统一使用 **FinRadar**。如果 GitHub 仓库已经建成了 `FinScope`，
只需要把各 README / SKILL.md 里的项目名替换掉，**目录名和文件名不受影响**（`financial-diagnosis/`、`risk-radar/` 是分工文档定死的）。

需要我统一改成 FinScope 的话说一声，一条命令就能批量替换。
