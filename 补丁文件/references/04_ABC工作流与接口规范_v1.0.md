# FinScope 终期工作流与接口规范 v1.0

> 版本：v1.0（接口冻结候选版）
> 日期：2026-11-03
> 编写：D（余璐）
> 阅读对象：A / B / C 负责人；E 负责人抄送
> **冻结时间：2026-11-04（周三）20:00。冻结后字段名不再改，只允许加可选字段。**
> 依据：2026-11-02 小组会议纪要、`终期修改意见/想法.txt`、`FinScope参考模版/index.html`、现有 A/B/C/D 代码与产物。

---

**阅读指引：**

- A：0、1、2、4、5、10、12 节。
- B：0、1、3、4、6、10、12 节。
- C：0、1、3、4、7、10、12 节。
- E：0、1、4、8、9、10 节。
- 只看自己那一节也可以，但第 4 节的字段表和第六部分的接口必须先看，否则字段会对不上。

---

## 0. 一页速览

### 0.1 终期产品一句话

用户输入一个 A 股代码，或者上传一份年报 PDF，系统自动完成财务分析、风险识别、估值和投研报告，最后在一个 Agent 工作台里呈现。

**9 家公司只作为回归测试集，不再是产品边界。**

### 0.2 三条硬规则

1. **只做年报。** 季度报本期不做，字段和流程按年度报告设计。以后扩展季报时另开 `period_type`，不改现有字段。
2. **只用合并口径。** 所有财务数据默认合并报表；只有母公司报表时标 `scope="母公司报表"` 并在报告里注明。
3. **一个数只有一个值、一个来源。** 页面、报告、估值用的是同一份 `financials`；谁都不许在展示层重算或另取一个数。

### 0.3 四个角色本周交什么

| 角色 | 周五 6 号 20:00 前交 | 不做什么 |
|---|---|---|
| A | 上传 PDF → 统一 `financials`；联网取数的字段映射与口径校验；42 个科目里至少 30 个 P0、三年、带来源 | 不算指标、不做估值、不写报告 |
| B | `ratios`、`risks`、`rules_evaluated`、`comparison`；核心/诊断标记；动态阈值 | 不抽数、不做估值、不写报告 |
| C | `valuation`：DCF、Comps、情景、敏感性、假设台账、Excel 底稿、行业门槛 | 不抽数、不算财务指标、不写报告 |
| D | 联网取数落地、Schema、编排、数据质量闸门、报告、API、历史记录 | 不替 A/B/C 重算 |
| E | 7 页 Agent 工作台，按本文档接口渲染 | 不重算、不补数 |

**如果周五交不出全部，按这个顺序保：**

1. A 的 17 个 P0 科目 + 三年数据（不保这个，B 一半指标算不出来）。
2. B 的 `ratios` + `risks`（不保这个，页面 3/4 是空的）。
3. C 的 DCF（不保这个，页面 5 只剩 Comps）。
4. B 的 `comparison` + 动态阈值（可以先固定阈值）。
5. C 的 Comps + Excel（可以先只出 DCF，Excel 用 CSV 代替）。

缺的项按第 10 节降级矩阵处理，不要硬编。

**代码之外，Skill 文档要同步：**

- A：`financial-extraction/SKILL.md`、`schema/financial_schema.json` 按 42 个科目更新。
- B：`financial-diagnosis/OUTPUT_SCHEMA.md`、`risk-radar/SKILL.md`、`risk_rules.json` 按新字段更新。
- C：`valuation/SKILL.md`、`OUTPUT_SCHEMA.md` 按新 valuation 结构更新。
- 验收看接口和样例输出，不看文档写得多漂亮。

### 0.4 时间表

| 时间 | 事项 | 谁 |
|---|---|---|
| 11-04 周三 20:00 | 本文件冻结；D 交 mock 数据包和 API 桩 | D |
| 11-05 周四 | A/B/C 按本文件改代码，遇到字段问题当天提 | A/B/C |
| 11-06 周五 20:00 | A/B/C 交可运行模块和样例输出 | A/B/C |
| 11-07 周六 | D 串链路，E 接页面 | D/E |
| 11-08 周日 | 端到端联调：代码搜索、上传、报告 | D/E |
| 11-09 周一 | 最终页面、演示视频、展示文件 | 全组 |

### 0.5 周五最小集（周四中午前确认砍单）

| 角色 | 周五必须有的 | 可以降级的 |
|---|---|---|
| A | 上传 PDF 产出 30 个 P0 科目；字段字典；000858/000333/600036 的映射校验 | P1 的 12 个科目、三年补不全的附注科目 |
| B | 六类 `ratios` + `risks`；`name/role/source_fields`；固定阈值可用 | 同业对比矩阵、动态阈值（先 fixed） |
| C | DCF + 行情回显 + 6 条假设台账 + Excel 三表；行业门槛 | 第二张敏感性（growth×margin）、反向 DCF、Comps 无 peers 时跳过 |
| D | 联网取数 + 适配层透传 + 报告 + API 桩 | Word 导出、PDF 多风格（先做一版） |
| E | 7 页壳 + 首页搜索/上传 + 进度条 + 页面 2–6 读真数据 | 记忆区、右侧 Agent 接 DeepSeek（先标演示） |

周四中午前，谁做不完就在群里说，按这张表砍。不要周五晚上才说。

---

## 1. 终期产品是什么

### 1.1 用户路径

```
打开网页
  ├─ 输入 6 位股票代码，例如 600519
  │    → 联网取最近一期年报财务数据
  │    → 自动分析
  │
  └─ 上传年报 PDF
       → 解析 PDF、抽取财务数据
       → 自动分析

分析过程显示六步进度：
  ① 获取年报 / 接收文件
  ② 解析与抽取
  ③ 指标与风险
  ④ 同业对比
  ⑤ 估值
  ⑥ 生成报告

完成后进入 7 页工作台：
  研究首页 / 公司概览 / 财务诊断 / 风险识别 /
  估值实验室 / 年报证据中心 / 投研成果中心
```

### 1.2 两种取数模式，必须分开

| 模式 | `meta.source_mode` | 数据来源 | 出处怎么写 |
|---|---|---|---|
| 联网 | `online` | 东方财富 / akshare 等公开接口 | `source_type="online"`，写数据源、报表、字段、链接；**没有页码** |
| 上传 | `upload` | 用户上传的年报 PDF | `source_type="pdf"`，写文件名、页码、原文片段 |

**不能混。** 在线模式没有页码，不要在报告里假装有页码；上传模式有页码，不要退化成一个模糊的来源名。

两个字段的分工：`meta.source_mode` 描述这次分析怎么进来的（`online` / `upload`）；`financials.*.source_type` 描述这一条数据从哪来（`online` / `pdf`）。upload 模式下 `source_type` 固定 `pdf`，不要写 `upload`。

**本期联网取数的负责人写死：D 新建取数模块，直连公开财务数据源；A 只提供字段映射和口径校验。** 不走“先下载年报 PDF 再解析”的老路：那条路慢，而且对任意公司不稳。01/03 里的 `fetch_cninfo.py` 下载路径保留作备用，不是终期主路径。在线模式没有页码，这是产品要接受的取舍，报告出处写数据源 + 字段 + 链接。

### 1.3 9 家公司的定位

现有的 9 家抽取结果、9 份 `unified.json`、2 份 `memo` 继续保留，作用变成：

- A 的回归测试集：改完抽取后，9 家的 17 个老科目不能变差。
- B 的回归测试集：65 个指标的既有结果不能大面积变化。
- C 的回归测试集：600519 的 DCF/Comps 结果可对照。
- E 的视觉样例：不要求 9 家都能在生产入口点开。

**产品入口不再写死 9 家。** 前端“最近研究”里可以出现这 9 家，但它们只是历史记录。

---

### 1.4 想法.txt 九条 → 本文档落点

| 想法 | 落在哪 |
|---|---|
| 1. 口径统一，不能一家公司两个口径 | 2.3、4.4 |
| 2. 数据自检，单位/逻辑不对要回原文，可点击跳转 | 4.5、5.5、11 |
| 3. 估值股价实时更新；财报不止年报 | 7.3；季报本期不做，见 2.1 |
| 4. 报告分析文字可点击展开 | 8.4、9 |
| 5. 输入代码或名称检索，集团合并口径 | 1.1、2.2、14.7 |
| 6. 做进度条 | 1.1、3.2、8.2 |
| 7. 不显示 skill/包/步骤，用资深分析师口吻 | 8.4 |
| 8. 年报问答保留一个能用的 | 9 |
| 9. 导出 Word/PDF，PDF 多风格 | 8.4、9 |

## 2. 三条硬规则展开

### 2.1 只做年报

- `meta.period_type` 固定 `"annual"`。
- 财务科目按年度取数，利润表/现金流量表取全年累计数，资产负债表取年末数。
- 不处理季报、半年报、单季拆分。用户输入季度代码时，提示“本版只支持年报”。

### 2.2 合并口径

- 每条 `financials` 记录必须有 `scope`，取值 `合并报表` 或 `母公司报表`。
- 优先合并口径。只有母公司数据时，允许出数，但：
  - `scope="母公司报表"`；
  - `data_quality` 里记一条 `PARENT_ONLY`；
  - 报告“数据来源”注明“本次仅有母公司报表口径，与合并口径不可直接比较”。

### 2.3 一个数一个值、一个来源

数据流只允许一个方向：

```
A 的 financials
   → B 的 ratios / risks
   → C 的 valuation
   → D 的 report
```

- B 不许自己重新抽数，只从 `financials` 取。
- C 不许自己改财务数，只从 `financials` / `ratios` 取。
- D 的报告不许自己格式化出一个新数，只从统一对象取。
- E 不许自己算同比、算占比、算每股价值。

同一个指标在页面 2、页面 3、页面 6 必须完全一样。出现不一致，以 `financials` / `ratios` 的原值为准，展示层改。

---

## 3. 总体工作流

### 3.1 单公司主链路

```
① 用户输入代码 / 上传 PDF
        ↓
② A：取数 + 归一化
   输出 company + financials + sources
        ↓
③ C：选出 3–6 家同业，产出 peer_set.json；D 按名单补同业财务
   A：取同业财务数据
        ↓
④ B：指标 + 风险 + 同业对比
   输出 ratios + risks + rules_evaluated + comparison
        ↓
⑤ C：估值
   输出 valuation
        ↓
⑥ D：拼统一对象 + 数据质量闸门 + 异动 + 报告
        ↓
⑦ E：渲染 7 页
```

### 3.2 每一步的输入输出

| 步 | 谁 | 输入 | 输出 | 失败怎么办 |
|---|---|---|---|---|
| 1 | D/E | 代码或 PDF | 任务参数 | 代码格式错，直接提示 |
| 2 | A | 代码 / PDF | `company`、`financials`、`sources` | 取不到数：报 `E_FETCH_FAILED`，建议上传 |
| 3 | C/D/A | `company`、行业 | 同业代码列表 + 同业财务 | 没有同业：`comparison.status="not_available"`，不阻塞 |
| 4 | B | `financials`、同业财务 | `ratios`、`risks`、`rules_evaluated`、`comparison` | 缺科目：相关指标 `not_evaluable`，不编 |
| 5 | C | `financials`、`ratios`、行情、同业 | `valuation` | 缺行情/同业：降级为 DCF 或不出估值 |
| 6 | D | 以上全部 | 统一对象 + 报告 | 数据质量不过：阻断结论，报告写原因 |
| 7 | E | 统一对象 + 报告 | 页面 | 缺块：显示“数据缺失”，不崩 |

### 3.3 同业对比的职责边界

同业对比是本期新增，必须说清谁做什么：

| 事 | 谁 | 说明 |
|---|---|---|
| 选 3–6 家同业 | C | 按行业、规模、商业模式选，输出代码和理由 |
| 取同业财务数据 | D（调 A 的取数能力） | 与目标公司同一套字段、同一套口径 |
| 算同业分位数、对比矩阵 | B | 中位数、P25、P75、目标公司分位、异常标记 |
| 算同业估值倍数 | C | PE/PB/PS/EV-EBITDA，用于 Comps |
| 拼进统一对象 | D | 放 `comparison`，不放进 `valuation` |

**如果周五前做不完：** B 先交 `comparison.status="partial"` 和目标公司自己的指标；C 先交 `valuation.comps.ok=false`。D 在页面上写“同业数据不足”，不阻塞主链路。

---

## 4. 统一数据对象 v2.0

### 4.1 顶层结构

```json
{
  "schema_version": "2.0",
  "meta": { ... },
  "company": { ... },
  "financials": { ... },
  "ratios": { ... },
  "risks": [ ... ],
  "rules_evaluated": [ ... ],
  "comparison": { ... },
  "valuation": { ... },
  "changes": [ ... ],
  "review_queue": [ ... ],
  "sources": [ ... ],
  "data_quality": { ... }
}
```

字段负责人：

| 键 | 谁填 | 说明 |
|---|---|---|
| `meta` | D | 模式、期间、币种、单位、版本、展示配置 |
| `company` | A（D 补交易所/币种） | 公司基本信息 |
| `financials` | A | 财务科目，每条带来源 |
| `ratios` | B | 六类指标 |
| `risks` | B | 触发的风险卡 |
| `rules_evaluated` | B | 未触发/不可评估的规则 |
| `comparison` | B + C + D | 同业对比与分位数 |
| `valuation` | C | 估值全部结果 |
| `changes` | B 优先，D 兜底 | 异动清单 |
| `review_queue` | B/C/D | 待核验事项 |
| `sources` | A 归集，C 补估值来源 | 全部出处 |
| `data_quality` | D | 数据质量检查结果 |

### 4.2 `meta`

```json
{
  "key": "600519.SH_2025",
  "source_mode": "online",
  "report_period": "2025",
  "period_type": "annual",
  "currency": "CNY",
  "amount_unit": "元",
  "consolidated": true,
  "data_source": "eastmoney",
  "data_as_of": "2026-11-03",
  "generated_at": "2026-11-03T15:30:00+08:00",
  "versions": { "schema": "2.0", "a": "a-20261103", "b": "b-20261103", "c": "c-20261103", "d": "d-20261103" },
  "display": {
    "overview_financials": ["revenue", "net_income_parent", "total_assets", "cfo"]
  }
}
```

- `key` 统一为 `<ticker>_<year>`，ticker 带交易所后缀。
- `display.overview_financials` 由 D 定：公司概览只放不需要计算的原始科目。增长率、毛利率、EBITDA、周转率一律放财务诊断。
- `data_as_of` 是行情/数据的日期，报告里要显示。

### 4.3 `company`

```json
{
  "name": "贵州茅台酒股份有限公司",
  "ticker": "600519.SH",
  "exchange": "上海证券交易所",
  "industry": "食品饮料-白酒",
  "industry_code": "SW:340000",
  "report_period": "2025",
  "report_type": "年度报告",
  "currency": "CNY",
  "amount_unit": "元",
  "scope": "合并报表",
  "auditor": "……",
  "audit_opinion": "标准无保留意见",
  "source_url": "https://……"
}
```

- `industry` 用数据源给的行业；没有就写“未识别”，不要猜。
- `industry_code` 可选，用于同业筛选。
- `source_url` 是公司/年报页面，用于“打开原文”。

### 4.4 `financials` 记录

下面这条是**上传模式**的例子；在线模式把 `source_type` 改成 `online`、`page`/`pdf_page` 置 `null`、`source_field` 填数据源字段。

```json
"revenue": {
  "value": 168838102514.79,
  "unit": "元",
  "unit_raw": "元",
  "period": "2025",
  "prior_value": 170899152276.34,
  "prior_period": "2024",
  "series": { "2023": 147693604700.0, "2024": 170899152276.34, "2025": 168838102514.79 },
  "basis": "合并",
  "scope": "合并报表",
  "source_id": "S01",
  "source_type": "pdf",
  "page": 6,
  "pdf_page": 8,
  "source": "贵州茅台2025年年度报告",
  "source_url": null,
  "source_field": null,
  "raw_text": "营业收入 168,838,102,514.79 …",
  "confidence": 0.95,
  "status": "found",
  "status_note": null
}
```

规则：

- `unit` 一律 `元`；A 在内部把千元/万元/亿元折成元，同时保留 `unit_raw`。
- `value` 为 `null` 时，`status` 必须是 `not_found`、`not_applicable` 或 `extraction_error`，不能写 0。
- `status` 取值：`found` / `not_found` / `not_applicable` / `extraction_error`。解析出错用 `extraction_error`，不要伪装成 `not_found`。
- 真实零值写 `0`，`status="found"`。
- `series` 至少三年：2023、2024、2025（或最近三个年度）。给不了三年就少给，但要在 `status_note` 里写清。
- `basis` 是 A 现有的口径字段（`合并` / `母公司`），保留；`scope` 是 D 的 canonical 字段（`合并报表` / `母公司报表`）。两个都有时以 `scope` 为准；只有 `basis` 时 D 按映射补 `scope`，不要默认成合并。
- 上传模式：`page`（印刷页码）和 `pdf_page`（PDF 物理页）**都要给**，E 的 PDF 预览靠 `pdf_page` 定位。`source_type="pdf"`，`raw_text` 建议保留。
- 在线模式：`page=null`、`pdf_page=null`，`source_type="online"`，`source_field` 写数据源字段名，`source_url` 写可打开的数据页。
- `source_id` 指回 4.5 的 `sources[]`，每条记录都要有；没有来源就不算 `found`。

### 4.5 `sources`

A 和 C 都往里写，D 合并成一个数组：

```json
{
  "source_id": "S01",
  "metric": "revenue",
  "source_type": "online",
  "source": "东方财富·利润表",
  "source_url": "https://……",
  "source_field": "TOTAL_OPERATE_INCOME",
  "page": null,
  "pdf_page": null,
  "pdf_url": null,
  "upload_id": null,
  "retrieved_at": "2026-11-03T15:20:00+08:00",
  "quote": null,
  "purpose": "财务数据"
}
```

- 上传模式：`source_type="pdf"`，`page` 和 `pdf_page` 必填，`quote` 尽量给；再给 `pdf_url`（相对路径，如 `../uploads/<upload_id>.pdf`）或 `upload_id`，否则 E 只能显示文件名，打不开 PDF。
- 在线模式：`page=null`、`pdf_page=null`，`source_field` 和 `source_url` 必填。
- C 的来源（行情、利率、可比公司）也用这个结构：`metric` 写 `price`/`wacc`/`peers`，`purpose` 写“估值输入”，`official` 可保留。
- 一条来源对应一个科目/一页；不要只写一个笼统的“年报”。
- **A 要新增顶层 `sources[]`**（现有输出只有 `company/financials/extraction_meta`，没有 sources）。D 优先读它；没有的话 D 只能从记录的 `page` 反推，在线模式会丢来源。

### 4.6 `data_quality`

由 D 填，A/B/C 不用填，但要能读懂：

```json
{
  "status": "ok",
  "checks": [
    { "code": "BALANCE_SHEET", "status": "pass", "detail": "资产 = 负债 + 权益，差异 0.02%", "metric": null, "page": null, "pdf_page": null, "source_id": null },
    { "code": "GROSS_MARGIN_RANGE", "status": "pass", "detail": "毛利率 91.18%", "metric": "gross_margin", "page": 6, "pdf_page": 8, "source_id": "S01" }
  ],
  "blocked": false
}
```

`status` 取 `ok / warn / blocked`。`blocked=true` 时，估值结论不可用。

### 4.7 `review_queue`

待核验事项，B/C/D 都可以往里加，D 汇总：

```json
{
  "item_id": "RQ01",
  "type": "assumption",
  "reason": "WACC 4.63% 低于市场隐含折现率 194bp",
  "affected_paths": ["valuation.dcf.inputs.wacc", "valuation.blended"],
  "suggested_action": "把 WACC 调到 5.5% 重算",
  "owner": "C",
  "status": "open"
}
```

`type` 取 `data / assumption / ratio / risk / valuation`；`status` 取 `open / resolved / rejected`。报告第六节按这个列表渲染，不另写一套。

### 4.8 `rules_evaluated`

沿用现有结构，每条去掉 `risk_` 前缀的展示字段，保留：

```json
{
  "rule_id": "S06",
  "rule_name": "流动比率未偏低",
  "category": "偿债与流动性",
  "status": "passed",
  "trigger": "current_ratio < 1.2",
  "threshold_value": 1.2,
  "threshold_source": "fixed",
  "peer_sample_n": 0,
  "explanation": "……",
  "trigger_values": { "current_ratio": 1.82 }
}
```

`status` 取 `passed / not_evaluable / not_applicable`；`threshold_*` 与 `risks` 同义。`comparison` 见 6.4，`changes` 见 6.5。D 在 `orchestrator` 里合并这些键，合并顺序是 A → B → C → D。

---

## 5. A 的工作：取数 + 归一化

### 5.1 你交什么

周五 20:00 前交三样：

1. **上传 PDF 的统一财务数据**：`company` + `financials` + 新增的 `sources[]`，结构按第 4 节。`sources` 是新增的，现有输出里没有。
2. **字段字典与映射表**：每个 canonical 科目对应的数据源字段/年报科目名、单位、口径；D 的联网取数按这张表落地。
3. **联网取数的口径校验**：D 取到 000858、000333、600036 三家原始数据后，A 负责核对字段映射和单位，签字确认。
4. **数据自检报告**：对 9 家老样例 + 至少 3 家新公司跑一遍，列出缺哪些科目、哪些数可疑。

### 5.2 42 个科目，分两档

**P0 必交（30 个）**：缺了 B 的核心指标或 C 的估值输入会算不出来。

| 报表 | 科目（canonical 键） |
|---|---|
| 利润表 | revenue、operating_cost、operating_profit、pretax_profit、income_tax_expense、net_income、net_income_parent、net_income_excl_nonrecurring、selling_expense、admin_expense、finance_expense、interest_expense、depreciation_amortization |
| 资产负债表 | cash_and_equivalents、accounts_receivable、inventory、current_assets、total_assets、accounts_payable、current_liabilities、short_term_borrowings、current_portion_lt_debt、long_term_borrowings、bonds_payable、total_liabilities、equity_parent、total_equity |
| 现金流量表 | cfo、capex、cash_received_from_sales |

**现有 17 个科目里，13 个已经在 P0**（revenue、operating_cost、net_income、net_income_parent、net_income_excl_nonrecurring、total_assets、total_liabilities、equity_parent、cash_and_equivalents、accounts_receivable、inventory、cfo、capex）。**需要新补的 P0 是 17 个**：

operating_profit、pretax_profit、income_tax_expense、selling_expense、admin_expense、finance_expense、interest_expense、depreciation_amortization、current_assets、accounts_payable、current_liabilities、short_term_borrowings、current_portion_lt_debt、long_term_borrowings、bonds_payable、total_equity、cash_received_from_sales。

**P1 尽量交（12 个）**：影响风险覆盖和报告完整度，缺了标 `not_found`，不要编。

| 报表 | 科目（canonical 键） |
|---|---|
| 利润表 | rnd_expense、impairment_loss、rd_capitalized |
| 资产负债表 | restricted_cash、notes_receivable、contract_assets、fixed_assets、goodwill |
| 现金流量表 | cfi、cff、interest_paid、dividend_paid |

> **`interest_bearing_debt` 不在 42 个抽取科目里。** 它由 D 用 `short_term_borrowings + current_portion_lt_debt + long_term_borrowings + bonds_payable` 派生；缺项就 `null`，不猜。A 不用单独抽这一项。
>
> 现有 A 的 17 个科目键与 canonical 的映射：
> `net_profit_attr → net_income_parent`、`net_profit_deducted → net_income_excl_nonrecurring`、`equity_attr → equity_parent`、`cash → cash_and_equivalents`、`rd_expense → rnd_expense`、`net_profit → net_income`；`cfo/cfi/cff/capex/revenue/operating_cost/total_assets/total_liabilities/accounts_receivable/inventory/goodwill` 同名。
>
> canonical 与 B 引擎输入名的映射（D 的 `to_b_input.py` 已处理，B 不用改引擎输入）：
> `operating_cost → cost_of_revenue`、`net_income_excl_nonrecurring → net_income_deducted`、`rnd_expense → rd_expense`、`cfo → ocf`、`cfi → cf_investing`、`cff → cf_financing`、`current_assets → total_current_assets`、`current_liabilities → total_current_liabilities`；其余同名。
>
> **A 新交的数据请直接用 canonical 键。** D 会同步改 `from_a.py`、`to_b_input.py`、`to_c_input.py` 三处，并做新旧双键兼容；老的 9 家样例保留旧键，D 兼容两套，不要求 A 重抽老数据。

### 5.3 两种模式怎么取

**联网模式（`source_mode="online"`）**

- 输入 6 位代码 + 年份。
- 取最近一期年报的三张表，至少三年。
- 推荐东方财富/akshare；具体接口由 D 落地，A 提供字段映射和口径校验。
- 每个科目写 `source_type="online"`、`source_field`、`source_url`、`retrieved_at`。
- 没有页码，不要编页码。

**上传模式（`source_mode="upload"`）**

- 输入 PDF，沿用现有 `pdf_pagemap.py` + `indicators.py`。
- 每个科目写 `source_type="pdf"`、`page`、`raw_text`。
- 三年数据优先从“主要会计数据”表取；附注级科目做不到三年，就给当期 + 上期，`status_note` 写“仅两期”，不要硬凑。
- 扫描件、图片型 PDF 不处理，直接报 `E_PARSE_FAILED`，提示换文本版。

### 5.4 单位与口径

- 内部一律折成 **元**；原始单位写 `unit_raw`，例如 `"千元"`。
- 同一科目的三年必须同单位。发现不同，先归一，再写 `data_quality` 提示。
- 利润表/现金流量表取全年累计；资产负债表取年末。
- 合并报表优先；只有母公司时按 2.2 处理。
- 金额为负直接写负，不要取绝对值。资本开支 `capex` 传正数（流出额），在 `status_note` 里写“流出”。

### 5.5 数据自检（交付前必跑）

| 检查 | 规则 | 不通过怎么办 |
|---|---|---|
| 资产 = 负债 + 权益 | 差异 ≤ 0.5% | 标 `warn`，回原文核对 |
| 营业成本 ≤ 营业收入 | 允许微差，不允许成本 > 收入 2 倍 | 标 `blocked`，多半是单位错 |
| 毛利率 | -100% ~ 100% | 超出标 `blocked` |
| 资产负债率 | 0 ~ 100% | 超出标 `blocked` |
| 同一科目三年量级 | 相差不超过 100 倍 | 标 `blocked`，多半是千元/元混用 |
| 经营/投资/筹资现金流 | 三者之和 ≈ 现金净增加 | 差异大标 `warn` |
| 页码/字段 | 每个 found 科目都有 page 或 source_field | 缺了标 `not_found`，不要留空 |

自检结果写进 `extraction_meta.self_check[]`（A 自己的字段），D 读完后再统一写 `data_quality`。D 会再跑一遍，但 A 先跑能省一轮返工。

### 5.6 验收

- 600519：17 个老科目与基线逐科目对比，差异有记录；不是笼统的“不能变差”。
- 000858 五粮液：不在 9 家里，能取到 3 年、30 个 P0 科目。
- 000333 美的：上传 PDF 模式，`page` 和 `pdf_page` 都有，E 能定位。
- 002594 比亚迪：单位错必须被自检拦住，不能把 6.6 万亿成本交给 B。
- 000651 格力 / 002415 海康：`series` 里不再出现 -9.89、0.01、57.93 这类同比数。
- 600031 三一：revenue / cfo 的 2023 与 2024 不再完全相同。
- 缺科目：`status="not_found"` 或 `extraction_error`，不是 0。

---

## 6. B 的工作：指标 + 风险 + 同业对比

### 6.1 你交什么

周五 20:00 前交四样：

1. `ratios`：六类指标，结构按 6.2。
2. `risks` + `rules_evaluated`：按 6.3，带动态阈值信息。
3. `comparison`：同业对比矩阵，按 6.4。
4. `changes`：异动清单，按 6.5；做不完可交空数组，D 兜底。

### 6.2 `ratios` 结构

**B 交六类嵌套结构，键名用 B 现有的原生键**（如 `growth.revenue_growth`）。D 的 `from_b.py` 负责映射成 canonical 键（如 `growth.revenue_growth_yoy`）。**不要平铺，也不要在 B 里改成 canonical 键**：平铺会让 `from_b` 按类遍历时崩，改名会让 E 找不到。

示例（B 原生输出）：

```json
"ratios": {
  "growth": {
    "revenue_growth": {
      "name": "营业收入同比",
      "value": -0.0121,
      "prev": null,
      "delta": null,
      "unit": "小数",
      "formula": "revenue / prior_revenue - 1",
      "inputs": { "revenue": 168838102514.79, "prior_revenue": 170899152276.34 },
      "page": 6,
      "source_pages": [6],
      "source_fields": ["revenue"],
      "status": "ok",
      "role": "core",
      "higher_is_better": true
    }
  }
}
```

新增字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 中文名，E 直接显示，不再靠前端映射表 |
| `role` | ✅ | `core` 或 `diagnostic`；见 6.2.1 |
| `source_pages` | ⭕ | 上传模式给页码数组；在线模式给空数组。现有 `page` 保留，`source_pages` 是补充 |
| `source_fields` | ✅ | 这个指标用了哪些 canonical 科目 |
| `status` | ✅ | `ok / not_evaluable / not_meaningful` |

> **D 必须同步改 `from_b.py`。** 现在 `_ratio_record` 只回传 value/unit/period/formula/page/prev/delta/inputs/status/higher_is_better，B 新加的 `name`、`role`、`source_fields`、`source_pages` 会被丢掉。周五 D 要把这四个字段透传到 unified，并在验收里检查 `unified.ratios.*.role` 有值。

#### 6.2.1 核心 / 诊断怎么分

会上定了：公司概览只放不需要计算的原始科目，增长率、毛利率、EBITDA、周转率放财务诊断。

- **公司概览**：D 用 `meta.display.overview_financials` 取 4 个原始科目（默认 revenue、net_income_parent、total_assets、cfo），不显示比率。
- **财务诊断**：显示全部 `ratios`。
- B 仍然要给每个 ratio 标 `role`：
  - `core`：营收增速、归母净利增速、毛利率、归母净利率、加权 ROE、资产负债率、经营现金流收入比、净现比。
  - `diagnostic`：其余。
- `role` 只影响财务诊断页的分组和排序；**公司概览页不读 `ratios`**，只读 `meta.display.overview_financials` 里的原始科目。
- 如果 E 以后想在概览放一两个比率，先改 `meta.display`，再由 D 统一发布，不在前端自己挑。

### 6.3 `risks` 与动态阈值

沿用现有风险卡结构，每条补三个字段：

```json
{
  "risk_id": "E01",
  "risk_name": "应收账款增速显著高于收入增速",
  "category": "收入与资产",
  "severity": "high",
  "severity_tag": "重大",
  "score": 85,
  "status": "triggered",
  "trigger": "应收账款增速 - 收入增速 > 阈值",
  "threshold_value": 0.15,
  "threshold_source": "peer_p75",
  "peer_sample_n": 5,
  "involved_values": [
    { "metric": "accounts_receivable", "value": 11895319134.75, "unit": "元", "period": "2025", "page": 59, "pdf_page": 61 }
  ],
  "numeric_evidence": "……",
  "text_evidence": { "quote": "……", "page": 80, "pdf_page": 82, "pages": [80], "found": true },
  "explanation": "……",
  "suggested_action": "……",
  "evidence_chain": [ ... ]
}
```

> 这是**完整风险卡**，不是精简版。现有的 `status/category/severity_tag/score/involved_values` 必须保留；`text_evidence.pages` 是多页数组，不要只留一个 `page`。D 的 `from_b._adapt_risk_card` 现在不回传 `threshold_value`、`threshold_source`、`peer_sample_n`，周五要一起补上，否则 B 交了页面看不到。

动态阈值规则：

1. 对每条有数值阈值的规则，先看 `comparison.metrics` 里有没有同名指标，且 `sample_n >= 3`。
2. 有：`threshold_value` 取同业 P75（“越高越差”的指标）或 P25（“越低越差”的指标），`threshold_source="peer_p75"` / `"peer_p25"`。
3. 没有：用规则文件里的固定阈值，`threshold_source="fixed"`，`peer_sample_n=0`。
4. 同业样本少于 3 家：回退固定阈值，并在 `rules_evaluated` 里记一条 `PEER_SAMPLE_SMALL`。
5. 阈值变了，风险卡的 `trigger` 文字要同步显示实际阈值，不要还写死 15%。

> 规则里的指标名和 `ratios` / `comparison` 的键不完全一样（例如规则可能写 `dso_delta`，比率里是 `ar_turnover_days` 和 `delta`）。B 自己维护一张小映射表；映射不上就用固定阈值，`threshold_source="fixed"`，不要硬套。
>
> **本期只对下面 5 条做动态阈值**，其余规则一律 `fixed`，不要为了凑数硬改：
>
> | 规则 | 用哪个指标 | 方向 |
> |---|---|---|
> | 应收增速快于收入 | `accounts_receivable_growth - revenue_growth_yoy` | 越高越差，取 peer P75 |
> | 存货增速快于成本 | `inventory_growth - cost_of_revenue_growth` | 越高越差，取 peer P75 |
> | 毛利率低于同业 | `gross_margin` | 越低越差，取 peer P25 |
> | 应收周转天数延长 | `ar_turnover_days` 的 `delta` | 越高越差，取 peer P75 |
> | 资产负债率偏高 | `debt_to_asset_ratio` | 越高越差，取 peer P75 |
>
> 这 5 条覆盖主要风险，足够演示“阈值会跟着同业变”。其余规则写 `fixed`，验收不要求全部动态。
>
> 如果周五前动态阈值做不完：先输出 `threshold_source="fixed"`，保留字段。D 和 E 会显示“固定阈值”，不假装是动态的。

### 6.4 `comparison`

**B 的输入除了目标公司的 `financials`，还包括 `peer_financials[]`。** 这是 D 额外传的一份数据，结构和目标公司 `financials` 一样，一家一条：

```json
{
  "peer_financials": [
    { "company": { "name": "五粮液", "ticker": "000858.SZ" }, "financials": { "...": "同 canonical 结构" } }
  ]
}
```

B 用这份数据算分位数，**只回传 `comparison` 的汇总结果，不回传同业的全部财务数据**，避免统一对象膨胀。`comparison.peer_set` 保留代码、名称、理由，够前端展示即可。

```json
{
  "status": "ok",
  "peer_set": [
    { "ticker": "000858.SZ", "name": "五粮液", "reason": "同行业、相近规模" }
  ],
  "metrics": [
    {
      "metric": "gross_margin",
      "label": "毛利率",
      "target": 0.9118,
      "peer_median": 0.7500,
      "peer_p25": 0.7000,
      "peer_p75": 0.8000,
      "percentile": 0.95,
      "sample_n": 5,
      "better": "higher",
      "flag": "above_p75"
    }
  ],
  "risk_matrix": [
    { "dimension": "盈利质量", "target_level": "高", "peer_level": "中", "note": "净现比低于同业中位数" }
  ],
  "multiples": { "pe": { "target": 9.69, "peer_median": 12.3, "sample_n": 5 } }
}
```

- `peer_set` 由 C 决定，D 补数据；B 只读，不自己选同业。
- `metrics` 由 B 算：至少 8 个指标（营收增速、毛利率、净利率、ROE、资产负债率、应收周转天数、存货周转天数、净现比）。
- `risk_matrix` 由 B 算：五维（成长、盈利、偿债、营运、现金流），每维给目标 vs 同业，不给 0–100 的假评分。
- `multiples` 由 C 填，B 不碰。
- `status`：`ok`（peer ≥3 且指标齐）、`partial`（peer 1–2 家或部分指标缺）、`not_available`（没有 peer）。
- `sample_n < 3` 时，`metrics` 里的分位数可以给，但页面要写“样本不足，仅供参考”；不要下“显著高于/低于行业”的结论。

### 6.5 `changes`（异动清单）

如果时间够，B 交 `changes[]`，字段：

```json
{
  "change_id": "CH01",
  "metric": "revenue_growth_yoy",
  "metric_name": "营业收入同比",
  "current": -0.0121,
  "prior": null,
  "delta": null,
  "rule": "本期为负增长",
  "severity": "high",
  "company_reason": { "quote": null, "page": 6, "found": false },
  "system_reading": "……",
  "inference": true,
  "followups": ["分产品收入拆分"]
}
```

- 识别规则：增速转负、毛利率变动 ≥2pp、ROE 变动 ≥3pp、经营现金流同比 ≤-30%、净现比变动 ≥0.2、周转天数变动 ≥15 天、资产负债率变动 ≥5pp。
- 每条四段：观察 / 公司披露原因 / 系统解读（标推断）/ 待确认事项。
- 找不到公司披露原文，`quote=null`，报告写“未找到相关披露”，不要编。
- 做不完：交空数组 `[]`，D 从 `ratios` 生成最小版。

### 6.6 验收

- 600519：65 个指标结果与现有统一对象一致；新增 `role`、`source_fields` 不为空。
- 000858：P0 科目齐时，核心指标全部 `ok`；缺科目时 `not_evaluable`，不崩。
- 动态阈值：至少一条规则的 `threshold_source="peer_p75"` 或 `"peer_p25"`，且 `peer_sample_n >= 3`。
- 同业对比：3 家以上时 `comparison.status="ok"`，8 个指标都有 target/median/percentile。
- 风险卡：每条有 `threshold_value` 和 `threshold_source`；没有就写 `fixed`。

---

## 7. C 的工作：估值

### 7.1 你交什么

周五 20:00 前交五样：

1. `valuation`：DCF + Comps + 情景 + 敏感性 + 融合 + 警告。
2. 行情回显：D 统一传股价、股本、市值、日期、来源，C 校验后写进 `valuation.market_data`，**不自己另取一个价**。
3. 假设台账：每条假设带依据类型、来源、置信度、可覆盖。
4. Excel 底稿：至少假设、预测、敏感性、相对估值四张表。
5. 行业门槛：哪些行业能估、哪些不能，给明确状态。

### 7.2 `valuation` 结构

**C 不改现有输出名，D 的 `from_c.py` 负责映射到 canonical。** 两边对应关系：

| C 原生字段 | D canonical | 说明 |
|---|---|---|
| `relative` | `comps` | D 改名，C 不动 |
| `relative.peers_detail[]` | `comps.peer_companies[]` | D 改名 |
| `sensitivity {wacc_axis, growth_axis, grid}` | `sensitivity.wacc_g` | D 重排；C 不用改 |
| `dcf.rows` | `dcf.forecast` / `dcf.rows` | D 保留两者 |
| 无 | `status` / `industry_support` / `assumptions[]` / `excel_url` | **C 本期新增**，D 透传 |

C 原生输出保留，不要为了对齐 canonical 去改 `relative`、`sensitivity` 的名字；改了 D 的 `from_c` 反而找不到。C 只新增上表最后一行的四个字段。

```json
"valuation": {
  "status": "ok",
  "industry_support": "supported",
  "market_data": {
    "price": 1263.0,
    "shares_outstanding": 1256197800,
    "market_cap": 1586161714000,
    "price_date": "2026-11-03",
    "price_time": "15:00:00",
    "price_source": "腾讯行情"
  },
  "comps": { ... },
  "dcf": { ... },
  "scenarios": { ... },
  "assumptions": [ ... ],
  "sensitivity": { "wacc_g": { ... }, "growth_margin": { ... } },
  "blended": { ... },
  "gates": [ ... ],
  "warnings": [ ... ],
  "excel_url": "/api/export/600519.SH_2025?format=xlsx",
  "disclaimer": "……"
}
```

`valuation.status` 取值：

| 值 | 含义 |
|---|---|
| `ok` | DCF 和/或 Comps 正常产出 |
| `partial` | 只有一种方法、缺部分假设，或行业结构性不支持标准 FCFF 但替代方法已产出 |
| `unsupported` | 行业不支持，且没有任何可用替代方法，未出估值 |
| `failed` | 模型运行失败，看 `error` |

`blocked` 由 D 的数据质量闸门写入，**不是 C 写**。C 跑在闸门之前，拿不到 `data_quality`；D 在拼统一对象时把 `valuation.status` 改成 `blocked`。

`industry_support` 取值：`supported` / `limited` / `unsupported`。

`gate_reason`（C 新增）：行业结构性限制的机器可读原因，例如
`standard_fcff_unsupported; ddm_used`。当 `industry_support="limited"` 且
`gate_reason` 以 `standard_fcff_unsupported` 开头时，表示标准 FCFF 不适用，
但 DDM/剩余收益或 PB/PE Comps 已产出，D 可以按 `partial` 正常展示，
不应把它当成“没有估值”。

### 7.3 行情与实时价格

- **行情由 D 统一取**：D 的 `tools/fetch_quotes.py` 或 `server/market_data.py` 取腾讯行情，带 `price_date`、`price_time`、`price_source`，作为 C 的输入传进来。
- C 只校验并回显到 `valuation.market_data`，**不自己再取一个价**。同一份报告里不能出现两个日期的股价。
- 字段：`price`、`shares_outstanding`、`market_cap`、`price_date`、`price_time`、`price_source`。
- 取不到行情：
  - `market_data.price=null`，`per_share=null`；
  - 仍可给 DCF 的股权价值/企业价值；
  - `warnings` 写“未获取到实时行情，每股价值未计算”；
  - 不要拿上一家公司或上一次的股价顶替。

### 7.4 同业与 Comps

- **选同业只有一个负责人：C。** C 先产出 `peer_set.json`（代码、名称、选取理由），D 拿这份名单去补同业财务，B 的分位和 C 的倍数都读同一份，不允许各选一套。
- 本周可以先维护一张“行业 → 3–6 家同业”的配置表，覆盖消费、制造、科技、化工、医药几个大类；表里没有的行业，`comps.ok=false`，不要临时乱选。
- C 的输入包括 D 传的 `peer_financials[]` 和 `peer_market_data[]`（股价/股本）。C 不自己抓同行财务，只负责选名单、算倍数、出区间。
- `comparison.peer_set` 和 `valuation.comps.peers_detail` 必须回显同一组 ticker；D 在验收时比对两组代码，不一致就报错。
- 没有同业：
  - `comps.ok=false`，`comps.reason="无可用同业样本"`；
  - `blended` 只保留 DCF，`weight_source="仅 DCF 100%"`；
  - 不要伪造 peers，不要拿别的行业凑。
- 同业倍数至少给 PE、PB、PS；EV/EBITDA 有就算，没有标 `null`。
- 每个倍数要写 `sample_count`、`peer_median`、`metric_basis`。

### 7.4.1 C 的输入由 D 构造

C 不自己从年报里找数。D 的 `to_c_input.py` 把 canonical 财务数据转成 C 要的 `ebit / pretax_income / tax_provision / da / delta_nwc / total_debt / total_equity / minority_interest / preferred_stock`。对应关系：

| C 输入 | D 从哪来 |
|---|---|
| `ebit` | `operating_profit`（如 C 的口径要加财务费用，D 在这里加，C 不猜） |
| `pretax_income` | `pretax_profit` |
| `tax_provision` | `income_tax_expense` |
| `da` | `depreciation_amortization`（已提到 P0） |
| `delta_nwc` | `(current_assets - current_liabilities)` 本期减上期；缺一期就 `null` + warning |
| `total_debt` | `short_term_borrowings + current_portion_lt_debt + long_term_borrowings + bonds_payable` |
| `total_equity` | `total_equity`，没有就用 `equity_parent` + 少数股东权益 |
| `minority_interest` | `net_income - net_income_parent` 只能做近似；没有可靠数就 `null`，不编 |
| `preferred_stock` | 年报没有就 `null`，不要默认 0 |

- `da`、`delta_nwc`、`total_debt` 缺一个，C 要返回 `partial` 并写 warning，不能用默认值硬算。
- 000858 的 DCF 要能跑，前提是这四项里至少 `ebit`、`da`、`total_debt` 有值。A 的 P0 已经覆盖 `depreciation_amortization` 和三项有息负债，D 负责拼。

### 7.5 假设台账

每条假设：

```json
{
  "name": "WACC",
  "value": 0.0463,
  "unit": "小数",
  "source_type": "model",
  "source": "rf 1.8% + beta 0.55 × ERP 5.14% + Kd",
  "confidence": "中",
  "overridable": true
}
```

`source_type` 四选一：`history`（历史均值/趋势）、`management`（管理层指引）、`industry`（行业公开数据）、`model`（模型推断）。`confidence` 取 `高 / 中 / 低`。`model` 类必须可人工覆盖。

### 7.6 三情景与敏感性

- `bull/base/bear` 必须满足：
  - `bull.growth_y1 > base.growth_y1 > bear.growth_y1`
  - `bull.ebit_margin > base.ebit_margin > bear.ebit_margin`
  - `bull.wacc < base.wacc < bear.wacc`
- 不满足就不出报告，写 `warnings`，D 会拦。
- 敏感性至少两张：
  - `wacc_g`：WACC × 永续增长率，5×5；
  - `growth_margin`：首年收入增速 × EBIT 利润率，5×5（做不完可只做 `wacc_g`，但要在 `warnings` 写明）。
- 每个格子是每股价值；无效组合写 `null`，不要写 0。

### 7.7 给前端画图的数据

C 不用画图，但必须把图要的数据给全：

- **FCF 预测图**：`dcf.forecast` 或 `dcf.rows` 给逐年收入、EBIT、FCFF；至少 5 年。
- **估值水平图**：`comps.valuation_range` 给 low/mid/high，`market_data.price` 给现价，`blended` 给融合值。
- **敏感性图**：`sensitivity.wacc_g.matrix` 给完整 5×5，无效格写 `null`。
- **情景图**：`scenarios.bull/base/bear.per_share` 三个值。

缺一项，E 就画不出对应的图。不要只给结论不给中间数据。

### 7.8 行业门槛

| 行业 | `industry_support` | 行为 |
|---|---|---|
| 制造、消费、科技、化工、机械、医药等 | `supported` | 正常 DCF + Comps |
| 银行、保险、证券 | `limited` | 不出标准 FCFF；用 DDM/剩余收益 + PB/PE Comps；`status="partial"`，`gate_reason="standard_fcff_unsupported; ddm_used"` |
| 地产、REITs | `unsupported` | 不出 DCF；写“需 NAV/FFO 口径，本版未支持”；没有可用替代方法时 `status="unsupported"` |
| 行业识别不出来 | `limited` | 可以出 DCF，但 `warnings` 写“行业未识别，估值按通用口径，仅供参考”；`gate_reason=null` |

银行/保险/地产的判断，优先用 `company.industry`；没有就用数据源行业字段；再没有就 `limited`，不要猜。关键词至少覆盖：`银行`、`保险`、`证券`、`房地产`/`地产`、`REIT`。
银行/保险/证券命中后不跑标准 FCFF，改用 DDM/剩余收益 + PB/PE Comps，输出 `partial/limited`；
地产/REITs 命中后不跑标准 DCF，没有 NAV/FFO 口径时输出 `unsupported`。

### 7.9 Excel 底稿

- 文件名：`<key>_估值底稿.xlsx`，落在 `valuation/output/`。
- 至少四张表：`假设`、`预测`、`敏感性`、`相对估值`；C 的 18 表专业底稿全部覆盖。
- 每张表第一行写数据来源和生成时间。
- **每次估值请求都同步生成**，`valuation.excel_path` 返回相对交付包根目录的路径；D 按包根解析后生成下载 URL。
- 用户改假设重算时，C 重跑并覆盖同名文件，不返回上一次的静态文件。
- 如果运行环境没有 `artifact_tool`/`artifact_tool_v2`，C 自动回退 12 表兼容底稿，并在 `excel_format` 写明；仍必须四类表齐全、路径真实存在。

### 7.10 验收

- 600519：DCF/Comps/情景/敏感性结果与现有 C 输出一致；假设台账 6 条。
- 000858：能出 DCF；没有 peers 时 `comps.ok=false`，`blended` 只 DCF。
- 600036 招商银行：`status="partial"`、`industry_support="limited"`、`gate_reason="standard_fcff_unsupported; ddm_used"`，不出标准 DCF，但输出 DDM/剩余收益、PB/PE Comps 与 blended。
- 002594：C 先出估值；D 跑完数据质量闸门后，unified 里的 `valuation.status` 被改成 `blocked`，报告不写“显著低估”。
- 无行情：`per_share=null`，股权价值仍可给。
- Excel：能打开，四张表齐全。

---

## 8. D 的工作（供 A/B/C 了解边界）

### 8.1 Schema 与适配

- 维护本文件第 4 节的 canonical schema。
- 改 `from_a.py`：A 新 canonical 键 + 老键双兼容；读 A 的 `sources`、`pdf_page`、`basis`，保留 `extraction_error`。
- 改 `to_b_input.py`：A 新 canonical 键 + 老键双兼容，不能因为键名变了就 `continue` 丢掉。
- 改 `from_b.py`：透传 `name`、`role`、`source_fields`、`source_pages`、`threshold_value`、`threshold_source`、`peer_sample_n`。不改这一处，B 交了页面也看不到。
- 改 `to_c_input.py`：按 7.4.1 构造 C 的输入，新键 + 老键双兼容。
- 改 `from_c.py`：C 原生 `relative`/`sensitivity` 映射到 canonical；透传新增的 `status`、`industry_support`、`gate_reason`、`assumptions`、`excel_path`；把 C 的 `sources` 合并进 4.5 的统一 `sources[]`。
- 所有字段变更先改本文件，再改代码。验收用 A 的新 canonical 输出跑一遍 `agent/run_pipeline.py`，对比字段数不减少。

### 8.2 编排

- `mode="code"`：代码 → D 取数 → C 选 peer_set → D 补同业财务 → B → C → D 合并 → 报告。
- `mode="upload"`：PDF → 解析 → 抽取 → C 选 peer_set → D 补同业财务 → B → C → D 合并 → 报告。
- 合并顺序固定 A → B → C → D；`comparison.multiples` 在 C 跑完后由 D 合并进 `comparison`，B 不负责这一块。
- 每一步有状态、耗时、失败原因；支持取消和从失败步骤重试。

### 8.3 数据质量闸门

- 跑第 11 节的检查。
- `blocked` 时改写 `valuation.blended.verdict` 和 `valuation.status="blocked"`，报告头条写“数据异常，估值结论不可用”。
- 闸门放在编排层，不只放报告模板，保证 E 和报告读同一个结论。

### 8.4 报告

- 七栏目：结论摘要、关键指标、经营与异动、风险、预测估值、待核验、来源。
- 资深分析师口吻，不写“调用了哪个 skill / 哪个包 / 第几步”。
- 每个数字带出处：上传模式 `[P.6]`，在线模式 `[东财·利润表]`。
- 关键判断可展开，展开后给推理过程。
- 导出 Markdown / PDF 必做，PDF 给 `academic` 和 `business` 两种风格；Word 尽力，环境里有 `python-docx` 就出 docx，没有就导 HTML 另存 `.doc`，并在 README 写明，不为了 Word 安装新依赖。
- Excel 底稿由 C/D 提供，见 7.9。

### 8.5 API v2 变更清单

**原则：现有接口不删，只加。** E 现在接的 `/api/companies`、`/api/upload`、`/api/analyze`、`/api/jobs/<id>`、`/api/unified/<key>`、`/api/report/<key>` 继续可用；新增的字段和接口标注清楚。

| 接口 | 状态 | 用途 / 变更 |
|---|---|---|
| `GET /api/companies` | 沿用 | 公司列表，补 `unified_exists` / `report_exists` |
| `GET /api/search?q=` | 新增 | 代码/名称检索；先只做代码 |
| `POST /api/upload` | 沿用 | 上传 PDF，返回 `upload_id` |
| `POST /api/analyze` | 扩展 | `mode` 从 `existing\|upload` 增加 `code`；upload 仍要先 `/api/upload` |
| `GET /api/jobs/<id>` | 扩展 | 返回 `steps[]`，见下 |
| `POST /api/jobs/<id>/cancel` | 沿用 | 取消 |
| `POST /api/jobs/<id>/retry` | 新增 | 从失败步骤重试 |
| `GET /api/unified/<key>` | 沿用 | 页面 2–5 数据 |
| `GET /api/report/<key>` | 沿用 | `format=md\|html\|json\|csv` 不变 |
| `GET /api/export/<key>` | 新增 | `format=pdf\|docx\|xlsx\|md`，PDF 加 `style=academic\|business` |
| `GET /api/history` | 新增 | 最近分析/记忆区，见下 |
| `PUT /api/assumptions/<key>` | 新增 | 改假设后重算，请求见下 |
| `GET /api/qa` | 新增（可选） | 证据中心问答，带 `key`、`q`、`k` |

**`job.steps[]` 的字段（E 直接用）：**

```json
{
  "name": "解析与抽取",
  "status": "running",
  "started_at": "2026-11-03T15:30:12+08:00",
  "elapsed_ms": 12500,
  "error": null
}
```

`status` 取 `pending / running / done / failed / skipped`；`elapsed_ms` 是毫秒；失败时 `error` 给 `{code, message, hint}`。

**`/api/history` 返回：**

```json
{
  "items": [
    { "key": "600519.SH_2025", "name": "贵州茅台", "ticker": "600519.SH",
      "year": "2025", "analyzed_at": "2026-11-03T15:30:00+08:00",
      "unified_exists": true, "report_exists": true, "source_mode": "online" }
  ]
}
```

**`PUT /api/assumptions/<key>` 请求：**

```json
{ "overrides": { "wacc": 0.055, "terminal_growth": 0.025 }, "force": true }
```

返回新的 `job_id`；D 重跑 C 和报告，旧版本移到 `out_data/_versions/<key>/<timestamp>/`。只允许改 `overridable=true` 的假设。

**`/api/qa`**：A 提供检索索引，D 提供接口；答案必须带 `sources[]`（文件/页码或在线字段），找不到就返回“未找到”，不要编。

---

## 9. E 的消费方式（抄送）

- 7 页：研究首页、公司概览、财务诊断、风险识别、估值实验室、年报证据中心、投研成果中心。
- 三栏：左导航、中工作区、右 Agent。右侧 Agent 做问答 + 执行记录；接 DeepSeek 就标“AI 助手”，没接就标“演示问答”，不要假装。
- 首页：代码搜索必做；名称搜索如果没做“名称→代码”表，就只支持代码，输入框写清。上传 PDF、最近研究、任务模板、六步进度。
- 公司概览：只放 `meta.display.overview_financials` 的原始科目 + 趋势图 + 风险摘要；不放增长率/毛利率/ROE。
- 财务诊断：全部 `ratios` + 研究判断；指标展开显示 `inputs`；数据项悬浮显示口径、单位、来源、是否存疑。同业对比矩阵、分位、异常标记放在这一页，读 `comparison.metrics` 和 `comparison.risk_matrix`。
- 风险识别：风险卡 + 证据链 + 阈值来源（固定/同业分位）；页码/来源可点击。
- 估值实验室：滑块（WACC、g、增长率、FCF、PE）→ 调 D 的重算接口或本地重算；显示假设台账、FCF 预测图、估值水平图、敏感性图、Excel 下载。
- 证据中心：来源列表、数据/计算/来源三栏、上传模式 PDF 预览 / 在线模式来源链接、一个 AI 问答入口。原页面 1 的 14 道题不要全搬，留一个能用的问答框。
- 成果中心：报告可编辑、复制、关键判断可展开、导出 PDF（学术风/商务风）/Markdown；Word 有就出，没有就隐藏按钮，不要放一个点了没反应的按钮。

---

## 10. 错误码与降级

### 10.1 错误码

| code | 触发 | 页面提示 |
|---|---|---|
| `E_CODE_FORMAT` | 不是 6 位代码 | 股票代码是 6 位数字，例如 600519 |
| `E_CODE_NOT_FOUND` | 代码不存在 | 没找到这家公司，检查代码 |
| `E_NO_ANNUAL_REPORT` | 当年没有年报 | 该公司 {year} 年年报未披露，试试上一年 |
| `E_FETCH_FAILED` | 数据源失败 | 数据源没连上，稍后重试或上传 PDF |
| `E_PARSE_FAILED` | PDF 解析失败 | PDF 读不出来，可能是扫描件，换文本版 |
| `E_EXTRACT_INCOMPLETE` | 关键科目缺失 | 抽取不完整，已标出缺失科目 |
| `E_UNSUPPORTED_INDUSTRY` | 地产/REITs | 该行业没有可用估值方法，只出诊断和风险；银行/保险/证券改走 DDM + PB/PE Comps，返回 `partial/limited` |
| `E_NO_MARKET_DATA` | 无行情 | 未获取到实时行情，每股价值未计算 |
| `E_NO_PEERS` | 无同业 | 同业样本不足，仅出 DCF |
| `E_VALUATION_FAILED` | 估值失败 | 估值没有跑出来，原因：…… |
| `E_DATA_QUALITY_BLOCKED` | 数据质量不过 | 数据异常，估值结论不可用 |

### 10.2 降级矩阵

| 缺什么 | 还能出什么 | 不能出什么 | 谁负责标 |
|---|---|---|---|
| 没有同业 | 财务诊断、风险、DCF | Comps、融合结论 | C |
| 没有行情 | 财务诊断、风险、DCF 股权价值 | 每股价值、Comps | C |
| 没有三年数据 | 单期指标 | 同比、周转率上期、CAGR | B |
| 缺 P1 科目 | 大部分指标 | 依赖该科目的风险规则 | B |
| 行业不支持 | 财务诊断、风险 | DCF、Comps | C |
| 数据质量 blocked | 原始数据、异常清单 | 估值结论 | D |
| 报告生成失败 | 页面 2–5 | 页面 6 | D |

降级必须**写在结果里**，不能悄悄发生。`status`、`warnings`、`review_queue` 至少有一处记录。

---

## 11. 数据质量检查（D 执行，A 先自检）

| code | 检查 | 规则 | 失败级别 |
|---|---|---|---|
| `BALANCE_SHEET` | 资产 = 负债 + 权益 | 差异 ≤ 0.5% | warn |
| `COST_VS_REVENUE` | 成本 ≤ 收入 | 成本不超过收入 2 倍 | blocked |
| `GROSS_MARGIN_RANGE` | 毛利率 | -100% ~ 100% | blocked |
| `DEBT_RATIO_RANGE` | 资产负债率 | 0 ~ 100% | blocked |
| `GROWTH_RANGE` | 同比增速 | -500% ~ 500% | blocked |
| `SERIES_SCALE` | 同科目三年量级 | 相差 ≤ 100 倍 | blocked |
| `CASH_FLOW_BRIDGE` | OCF+CFI+CFF ≈ 现金净增加 | 差异 ≤ 5% | warn |
| `PER_SHARE_POSITIVE` | 每股价值 | > 0 | blocked |
| `PARENT_ONLY` | 只有母公司报表 | 标 warn，报告注明 | warn |
| `SOURCE_COMPLETE` | 每个 found 科目有来源 | page 或 source_field | warn |

`blocked` 时：`data_quality.blocked=true`，D 阻断估值结论，报告头条改写。`warn` 时：照常出结果，但在“待核验”里列出。

每条 check 除了 `code/status/detail`，还要带 `metric`、`page`、`pdf_page`、`source_id`（能定位就填，不能就 `null`）。E 靠这四个字段生成“点回原文”的链接。A 的 `extraction_meta.self_check[]` 用同样结构。

---

## 12. 验收用例

### 12.1 必测

| 用例 | 输入 | 期望 |
|---|---|---|
| 老公司回归 | 600519 | 17 个老科目、65 个指标与现有结果一致；报告七节齐全 |
| 新公司联网 | 000858 五粮液 | 取到 3 年、30 个 P0 科目；核心指标 ok；DCF 出结果；Comps 可缺 |
| 银行门槛 | 600036 招商银行 | `status="partial"`、`industry_support="limited"`、`gate_reason="standard_fcff_unsupported; ddm_used"`；DDM/剩余收益 + PB/PE Comps + blended 可用 |
| 上传 PDF | 000333 美的 PDF | `source_mode="upload"`；页码可点；报告出处是 `[P.x]` |
| 错误代码 | 999999 | `E_CODE_NOT_FOUND`，不白屏 |
| 无同业 | 任一没有 peers 的公司 | `comps.ok=false`；`blended` 只 DCF；报告写“仅 DCF 口径” |
| 无行情 | 行情接口失败 | `per_share=null`；股权价值仍出；报告写“未获取行情” |
| 数据异常 | 002594 比亚迪 | `data_quality.blocked=true`；D 把 `valuation.status` 改成 `blocked`；不出“显著低估” |
| 缺三年 | 只有两期数据 | 同比/周转率标 `not_evaluable`；报告写“数据不足” |
| 适配层透传 | A 的新 canonical 输出 | `agent/run_pipeline.py` 跑完，`financials` 字段数不减少；`ratios.*.role/name/source_fields` 在 unified 里能看到 |
| 同源同业 | 任一有 peers 的公司 | `comparison.peer_set` 与 `valuation.comps.peers_detail` 是同一组 ticker |
| 在线出处 | 000858 | 每条 found 记录有 `source_type="online"`、`source_field`、`source_url`；报告不出现页码 |

### 12.2 回归命令

A/B/C 各自交模块时，附一条可复制命令和一份样例输出：

```bash
# A：输出落到 data/extracted/，没有 --out 参数
python src/indicators.py --pdf <pdf>

# D：联网取数 + 串联（本期新增，命令以实际实现为准）
python agent/runner/run_chain.py --code 000858 --year 2025

# B：两个脚本在不同目录，分两步跑
cd financial-diagnosis
python scripts/compute_ratios.py -i <A.json> -o <ratios.json> --pretty
cd ../risk-radar
python scripts/detect_risks.py --ratios <ratios.json> --rules risk_rules.json -o <risks.json> --pretty

# C：子命令 run，不是 --input
cd valuation
python cli.py run <input.json>
```

命令跑不通，视为未交付。

---

## 13. 协作与变更

### 13.1 D 在周三 20:00 前提供

- 本文件 v1.0。
- `schema_v2.json`：把第 4 节的字段写成 JSON Schema，A/B/C 可以直接拿去校验自己的输出。
- `mock/` 数据包：
  - `target_600519.json`：完整 canonical 对象；
  - `peers_000858_000568_600809.json`：3 家同业财务；
  - `b_input_sample.json`、`c_input_sample.json`；
  - `unified_v2_sample.json`。
- API 桩：`/api/search`、`/api/analyze`、`/api/jobs`、`/api/unified`、`/api/report` 先返回 mock。

### 13.2 字段冻结

- 周三 20:00 后，第 4 节的字段名冻结。
- 只允许加可选字段；改必填字段或改名，必须 D 同意并在群里发变更记录。
- 每次变更写进本文件末尾的“变更记录”。

### 13.3 每天同步

- 每天 21:00 群里发三行：今天交了什么、卡在哪、明天要谁配合。
- 周五 20:00 前交不出，提前说，不要等到联调才发现。

---

## 14. 待拍板的问题

下面几条需要周三前确认，默认按括号里的方案执行：

1. **联网数据源用哪家？**（默认 D 先实测东方财富/akshare/新浪，选一家能稳定取三年财务数据的；行情已知东财/akshare 在本机限流，用腾讯。A 负责字段映射，D 负责取数落地。不要凭“默认”写死，先跑通 000858 再定。）
2. **同业由谁选？**（默认 C 选 3–6 家，D 补数据，B 算分位。）
3. **实时股价用哪家？**（默认腾讯行情，**D 统一取**，传给 C 回显；C 不自己取，避免两个价。取不到就降级。）
4. **Word 导出做不做？**（PDF + Markdown 必做；Word 如果本机有 python-docx 就出 docx，没有就导 HTML 另存 `.doc`，不安装新依赖；两条都不行就在页面隐藏 Word 按钮，别放一个点了没反应的。）
5. **行业分类用哪套？**（默认用数据源行业字段；没有就“未识别”，不猜。）
6. **9 家老报告怎么处理？**（默认保留作回归测试，不进产品入口；新报告覆盖 `out_data/reports`。）
7. **公司名搜索做不做？**（默认只做 6 位代码；名称搜索需要一张“名称→代码”表，没有就写清“请输入代码”，不要让人输名称然后报错。）

---

## 变更记录

| 日期 | 版本 | 变更 | 谁 |
|---|---|---|---|
| 2026-11-03 | v1.0 | 初版，冻结字段与工作流 | D（余璐） |
| 2026-11-03 | v1.0 修订 | 按接口复核修正：canonical 改用 D 现有键；补 `basis/pdf_page/source_id/extraction_error`；明确 B 六类嵌套与 D 透传；明确 C 原生名与 canonical 名；联网取数、同业、行情、Word 导出、API v2、验收命令按实际代码修正 | D（余璐） |
