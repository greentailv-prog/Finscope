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

**前五类 key 与统一 Schema 完全一致，不需要字段映射；`banking` 是行业专属第六类，只有银行业公司才出现。**

### 交付前先跑契约自检

```bash
# 只查指标
python3 scripts_check_contract.py --ratios out/600519.json

# 指标 + 风险（阈值与证据链只在风险卡里）
python3 scripts_check_contract.py --ratios out/600519.json --risks out/600519_risks.json

# 连 D 的适配器一起跑：能导入就真的调一遍 adapt_b，看字段有没有被吃掉
python3 scripts_check_contract.py --ratios ... --risks ... --with-d /path/to/D分支文件
```

退出码 0 才算能交。它查的是静态检查抓不到的东西：字段名拼错、单位词表不匹配、
页码取不到、状态值多出一个——这些都不报错，只会让 D 的适配器静默丢字段，
最后表现为「报告里没有出处」。

当前真实产物全部 0 失败：11 家 A 股 + 工行 + 合成样本 + 在线取数 600519。

### 交接字段（v1.4 起，对齐冻结规范 v1.0 第 4、6 节）

| 位置 | 字段 | 说明 |
|---|---|---|
| `company` | `ticker_full` / `exchange` | `600519.SH`、上海证券交易所 |
| `company` | `report_period` | 统一 4 位年份 `2025`，不是 `2025年度` |
| `company` | `industry` | 没有就写「未识别」，不留 null |
| `company` | `report_type` / `scope` / `amount_unit` | 年度报告 / 合并报表 / 元 |
| `meta` | `key` / `period_type` / `source_mode` / `consolidated` | `600519.SH_2025` / annual / online\|upload / true |
| `ratios.*.*` | `name` / `role` | 中文名；core 8 个 + diagnostic 其余 |
| `ratios.*.*` | `source_fields` / `source_pages` | 用了哪些科目、在年报第几页 |
| `ratios.*.*` | `status` | `ok` / `not_evaluable` / `not_meaningful`（口径不成立） |
| `risks[]` | `threshold_value` / `threshold_source` / `peer_sample_n` | 固定阈值还是同业分位 |
| 顶层 | `metric_evidence` | 指标 → 期间 → 页码，专给 `involved_values[].page` 用 |

`metric_evidence` 是为解决一个具体断点加的：`evidence` 按**科目**建树，而风险卡的
`trigger_values` 用的是**指标**名，D 拿指标名去 `evidence` 里查必然查不到，页码就是
null。这里按每条指标的 `source_fields` 把科目页码汇总到指标名下，并对
`roe_delta` 这类变动量做了继承（出处就是基期指标那几页）。同时把指标名以
`kind="metric_alias"` 的形式并进 `evidence`，老的查法也能取到。

### 三条刻意偏差（不是漏做，是权衡后选的）

1. **`company.ticker` 保持 6 位纯代码**，规范要的 `600519.SH` 写在 `ticker_full`。
   `ticker` 是文件名、矩阵行键、同业匹配键的唯一标识，改带后缀会连锁改一串产物。
2. **`risks` 保留全量 40 条**，规范要的「只含触发」单独放在 `risks_triggered`。
   D 现有 `from_b.py` 只认 `risks` 并按 status 自己分流，若这里只给触发卡，
   未触发的那 36 条会在 D 侧静默消失。等 D 改读 `rules_evaluated` 后可以收紧。
   注意：消费方按 status 分流，**不要把 `risks` 与 `rules_evaluated` 直接拼接**。
3. **证据链多一个「建议」步骤**。D 只读数据/计算/判断/出处，多出来的不影响；
   删掉反而丢掉可执行的整改动作。

### 工作台接入：D 的六步调用与 `peer_financials`

2026-11-06 与 D 对齐的口径，B 不起服务，D 用子进程调，输入输出全走 JSON 文件。

**输入**：D 写的 `b_input.json`，顶层比原来的抽取结果多一个数组 `peer_financials`，与
`company` / `financials` 平级：

```json
"peer_financials": [
  {"company": {"name": "宜宾五粮液股份有限公司", "ticker": "000858"},
   "financials": {"revenue": {"2025": {"value": 89175178322.7, "unit": "元", "page": 12}}}}
]
```

一家一条，结构与目标 `financials` 完全一样（指标 → 期间 → `{value, unit, source, page}`），
只放当期需要的那三年。没有同业就是空数组 `[]`，B 回退固定阈值，不报错。

**调用顺序**（D 侧实际执行，B 的入口都已就绪）：

```bash
# 1. D 写 b_input.json（含 peer_financials）
# 2. 目标公司指标
python3 financial-diagnosis/scripts/compute_ratios.py -i b_input.json -o b_ratios.json --pretty
# 3. D 为每个 peer 写 peer_inputs/<ticker>.json（company + financials 即可，无需 meta）
# 4. 同业指标
python3 financial-diagnosis/scripts/compute_ratios.py -i peer_inputs/<ticker>.json -o peer_ratios/<ticker>.json
# 5. 同业对比
python3 risk-radar/scripts/build_comparison.py --target b_ratios.json --peers peer_ratios --out comparison.json
# 6. 风险判定
python3 risk-radar/scripts/detect_risks.py --ratios b_ratios.json --rules risk_rules.json \
        --comparison comparison.json -o b_risks.json --pretty
```

第 2 步会忽略顶层的 `peer_financials`（只读 `meta` 与 `financials`）；第 4 步的 peer 输入即使
没有 `meta.periods`，也能从 `financials` 的期间键推断，实测 4 家全过。

**链路自检**（联调时一条命令判断有没有断）：

```bash
python3 scripts_link_check.py --b-input b_input.json
# 逐步打印 6 步退出码，最后汇总 comparison 状态、peer_set、当次同业阈值条数
```

`comparison` 放统一对象顶层，B 输出单独文件，D 原样合并；`comparison.multiples` 由 D 在 C 跑完后补，
B 不碰。`peer_set` 里每家同时给 `ticker`（6 位）与 `ticker_full`（`000858.SZ`），
D 拿 `ticker_full` 就能和 C 的 `valuation.comps.peer_companies` 对齐，不必自己拼后缀。

**两条阈值通道不要混**：`peer_*` 是这次请求用 `peer_financials` 现场算的，
`industry_*` 是本地池（年报季后刷新）的历史基准，D 页面上分开显示。优先级：
当次同业 → 离线池 → `fixed_fallback`。

### D 侧两处透传：已补齐

下面两项 2026-11-06 已由 D 改好，B 按原字段输出即可：

- `_ratio_record` 现在透传 `name` / `role` / `source_fields` / `source_pages`；
- `_adapt_risk_card` 现在透传 `threshold_value` / `threshold_source` / `peer_sample_n`。

自检里这两项不再报 WARN。若换新版本适配器后又出现，说明改动被回退，照「交接字段」那张表核对。

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
4. **`from_b.py` 的两处透传已补齐**（2026-11-06 确认）：
   `_ratio_record` 透传 `name`、`role`、`source_fields`、`source_pages`；
   `_adapt_risk_card` 透传 `threshold_value`、`threshold_source`、`peer_sample_n`。
   换适配器版本时留意别回退，这两项一丢，页面就分不出核心指标、也看不到阈值来源。
5. **`involved_values[].page` 已经能取到**：我加了 `metric_evidence`，并把指标名以别名并进
   `evidence`（带 `kind="metric_alias"`），你现有的 `_evidence_page(evidence, metric, period)`
   不改也能命中。实测 4 条触发卡的 4 个变量全部拿到页码。
6. `risks` 给的是**全量**（40 条），你按 `status` 分流即可；规范要的「只含触发」在
   `risks_triggered`。**不要把 `risks` 和 `rules_evaluated` 拼接**，会重复。
7. 银行专属规则（B01–B13）的 `category` 我按你 `CATEGORY_MAP` 的 7 类映射过了
   （资本/流动性归 `solvency`，不良与拨备归 `asset_quality`，息差与成本归 `profitability`），
   原值留在 `category_internal="banking"` 备查。

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
| **行业阈值已校准 3 项（roe / nim / cost_to_income，覆盖度 60%）** | 银行业 20 家上市银行真实样本（v1.6，`fetch_bank_samples.py` 可年度刷新）。npl / 拨备覆盖率 / 资本充足率属 regulatory 阈值，判定走法规硬线，**不参与分位校准**；`benchmarks_calibrated: false` 与 `benchmarks_coverage: 0.6` 如实透出 | 样本池由 B 自己维护（`risk-radar/data/peer_samples/`），年报季后跑 `fetch_bank_samples.py --write && calibrate.py --write` 刷新。制造业同业池待建 |
| **WACC 已解决（v1.6c）** | 不再等 C：`compute_wacc.py` 输入公司代码/名称现场计算敏感性区间（每家公司的 β 回归、市值、债务成本、税率全自算），P03/B12 用区间两端重判。详情见下文 v1.6c 节 | 与 C 对齐：估值模块建议读同一份 wacc 输出，避免两处口径打架 |
| **只有两个行业剖面** | 目前只有 banking / manufacturing | 按同一份剖面 schema 继续加：地产、券商、保险、医药、零售 |
| **只覆盖 A 股** | 港股、美股、新三板不在范围内 | 需接入其他公开披露渠道 |
| **部分上游抽取缺印刷页码** | 天赐材料（002709）34 个科目只有 PDF 物理页、没有印刷页码；工行手工底稿整体没有 `pdf_page` | 属 A 侧抽取完整性。B 原样透传、不补造页码，契约自检会报 WARN 并注明归属 |
| **在线模式没有页码** | 接口取数只有数据源与字段，没有年报页码 | 规范明确接受这个取舍：不编页码。报告出处写「东方财富·F10 财务报表（年报）」+ 字段名 |

### v1.6c 已解决：WACC 来源口径（2026-11-05）

WACC 是**公司专属参数**，不允许手填单点数假装精确。落地为「每家公司现场计算 + 敏感性两端判定」：

**来源逐项可核对**（`risk-radar/scripts/compute_wacc.py`，输入 `--code 600519` 或 `--name 贵州茅台`）：

| 参数 | 来源 |
|---|---|
| Rf 无风险利率 | 中债 10 年期国债收益率 1.65%（2026-10-30，中国债券信息网；`data/wacc_inputs.json` 统一配置，年报季后刷新，同批交付同一根 Rf） |
| β | 该公司 156 周周收益率对沪深 300 的 OLS 回归，区间 = β±2×标准误 |
| MRP | 惯例区间 6%–7%（无官方数，用区间进敏感性，不假装有精确值） |
| Rd | 公司自算：利息费用 ÷ 平均有息负债；缺则中债商业银行 AAA 债兜底并注明"市场口径" |
| t | 公司有效税率；缺则法定 25% |
| E / D | 东财行情总市值 / 报表有息负债账面值 |

**诚实防线（不猜数的三道闸）**：① β 回归 R²<0.05 拒绝采信（工行实证：R²=0.001，回退 20 家银行同业 β 中位数 0.391，13 家达标）；② 回归不可得且无 `--beta` 显式传入时**拒绝产出**；③ 市值/有息负债缺则全权益近似并注明"门槛偏严"。

**判定（`detect_risks.py --wacc`）**：P03/B12 用区间两端重判——两端都低于区间 → triggered，两端都高于 → passed，**落在区间内 → not_evaluable + review_queue 转人工**（结论随假设翻转本身是有信息量的结论，呼应敏感性分析，绝不取中值硬判）。

**银行口径单列**：存款是经营材料非融资，经典 WACC 失真。银行门槛用股权成本 Ke；B12 的 RWA 收益率与 WACC 不同尺度不可直接比，折算 RAROC = 净利润/资本净额（`rwa_return/capital_adequacy_ratio`，资本充足率的分子分母对消）后与 Ke 同尺度。

**实证**：工行 ROE 8.97% > Ke 区间 3.99%–4.38% → passed（P03/B12 从 not_evaluable 全部激活，待核验 64→0 项）；demo 合成数据 β=1.0（manual 标注）WACC 7.65%–8.65%，ROE 9.46% passed；茅台全流程 ROE 34.5% vs 6.20%–9.88% passed。

**工作台接入（与同业对比一致的入口）**：

```
python3 risk-radar/scripts/compute_wacc.py --code <公司代码> --ratios <ratios.json> \
    [--industry banking] --out risk-radar/data/wacc_<code>.json --write
python3 risk-radar/scripts/detect_risks.py --ratios ... --rules ... --wacc risk-radar/data/wacc_<code>.json -o ...
```

无 `--wacc` 时 P03/B12 维持 not_evaluable（不伪装）；风险卡 `threshold_source=wacc_sensitivity`（银行用 Ke 替代 WACC，差异写在 `threshold_note` 里，不给 D 留第二套取值），`industry_profile.wacc` 透出区间与 β 出处给 D。

**与 C 的对齐请求**：C 的估值（戈登模型 r）建议读同一份 wacc 输出——否则 B 判"ROE 低于资本成本"而 C 估值用的 r 更低，两处结论会打架。

### v1.2 已补齐：三表勾稽自检

上一版 `RULES.md` 写了规则但代码没实现，这一版落地了，落在指标输出的 `checks` 节点：

- **资产负债表平衡**：总资产 = 总负债 + 归母股东权益 + 少数股东权益（逐期）
- **利润表勾稽①**：利润总额 − 所得税费用 = 净利润（逐期）
- **利润表勾稽②**：净利润 − 归母净利润 = 少数股东损益，**与附注独立披露值比对**（逐期）
- **现金净变动**：期末现金 − 期初现金 = 经营 + 投资 + 筹资 + 汇率影响（相邻期之间）

容差 1%，不平则进 `review_queue`。看板新增「三表勾稽」标签页，可点击展开每一项的代入数据与年报出处。
回归测试 `scripts_test_checks.py`：注入已知失衡，断言能被抓出（24 项断言）。

**过程中被测试抓出的两个真问题**（都记在 `financial-diagnosis/RULES.md` 第七节）：

1. 利润表②若用倒轧的少数股东损益，恒等式退化成 `A + (B − A) ≡ B`，**恒真、抓不到错**。
   → 改为只在附注独立披露时才判定，否则判"无法勾稽"。
2. 演示样本的现金流本来就差 1500 万，之前没人发现。→ 已修正合成数据使其内部自洽。

### v1.5 新增：识别抽取层的倒算值（2026-11-04）

**问题**：A 对「所有者权益合计」这类科目有一个补救逻辑——抽到的值小于归母权益时（会计上不可能），
改用「资产总计 − 负债合计」倒算，并在 `status_note` 里写明。五粮液、宁德时代、三一重工、万华化学
4 家的 2025 年报都是这种情况。经原文核对，五粮液抽到的 774.59 亿实为**母公司报表**的权益合计
（合并报表该行是 1221.81 亿），而倒算所用负债 586.80 亿同样抽错（真实 678.04 亿）。

倒算本身有两个隐患，B 侧已修复：

1. **推算值冒充披露值**：`from_a_extract.py` 此前不透传 `status_note` / `value_original` /
   `confidence`，B 无从知道这是推算值。→ 现已透传，且对倒算条目加 `derived: true` 标记。
2. **倒算 + 倒轧构成恒真式**：少数股东权益缺失时按 `te − ep` 倒轧，若 `te` 又是「资产 − 负债」
   倒算的，则勾稽右边 `tl + ep + (te − ep) ≡ 资产`——**资产或负债抽错多少亿都报 balanced**。
   五粮液 2025 年负债抽错 91.24 亿，勾稽却显示"差 0.00003 元"。→ 与利润表「伪勾稽」同理：
   `bs_balance` 遇倒算权益或倒轧出负的少数股东权益，判 `not_evaluable` 并写明病因与核对路径，
   不再产出无鉴别力的"平衡"。

**给 A**：这 4 家的「所有者权益合计」需回年报合并资产负债表重取披露行（如五粮液 2025 为
122,180,683,645.14，第 55 页）。另注意 A 的倒算会把 `raw_text` 覆盖成倒算式且两期共用，
原值出处随之一并丢失——建议保留 `value_original` 的独立出处。

**给 D**：勾稽 `not_evaluable` 的公司，`data_quality` 与结论可信度已在矩阵侧如实降级，
不需要 D 做额外处理。

### v1.6 新增：行业基准阈值真正接入规则判定（2026-11-04）

**此前的断点**：`detect_risks.py` 已把 `profile.benchmarks` 注入成 `{指标}_industry_pXX`
上下文变量，但没有任何规则引用它们——校准不改变判定结果，等于白校准。

**本版打通的链路**：`fetch_bank_samples.py`（抓样本）→ `peer_samples/banking.json`
（样本池）→ `calibrate.py`（算分位、写剖面）→ 规则 `benchmark_judge` 声明 →
`detect_risks.py` 通用引擎判定。四个环节都落了盘：

1. **样本池补齐**：新增 `risk-radar/scripts/fetch_bank_samples.py`，抓 20 家上市银行
   （六大行 6 + 股份制 9 + 头部城商行 5）2025 年报的净息差（20/20）与成本收入比
   （18/20，平安、宁波缺业务及管理费行，如实记 null）。口径已用工行年报复算核对
   （NIM 1.28%、成本收入比 28.05%，与 B 指标引擎一致）。银行板块现在 **3 项 calibrated**
   （roe / nim / cost_to_income，覆盖度 60%）。
2. **npl / 拨备覆盖率 / 资本充足率不参与分位校准**：这三项是 regulatory 阈值，
   判定走法规硬线（行业剖面 `regulatory_basis`），样本池里改标 `type: regulatory`。
   **分位数不能替代监管红线**，样本不足的空位不再是"待补"，而是"不该用分位数"。
3. **规则侧声明、引擎侧通用处理**：banking 剖面的 B06 / B07 声明 `benchmark_judge`
   （metric + quantile + peer_expr），引擎见到声明且基准样本 n≥5（calibrated/indicative）
   就用同业阈值重判；基准缺失或样本不足则回退规则默认阈值，**回退原因写进
   `threshold_source = fixed_fallback` + `threshold_note`**，不伪装成同业判定。
   13 条银行规则全部带上 `threshold_basis`（regulatory / self_delta / convention），
   静态标注规则默认阈值的性质——与动态的 `threshold_source` 一静一动，不要混。
4. **工行实证**：B06 判定改用"行业中位数 1.49%（样本 20 家）"——工行 NIM 1.28% 低于
   中位数，triggered；B07 改用"行业 P75 31.89%（样本 18 家）"——工行 28.05% 未及 P75，
   passed。证据链"计算"层写的是实际参与比较的两个数。

**契约增量**（都是增量字段，D 不改代码也能跑，建议后续透传）：

- 风险卡新增 `threshold_basis`（规则默认阈值性质）、`threshold_note`（回退原因 / 声明依据）、
  `benchmark_status`（行业基准状态）；`threshold_source` 词表扩充
  `industry_p10/p25/median/p75/p90` 与 `fixed_fallback`。
- `industry_profile` 新增 `benchmarks_coverage` 与 `benchmarks_calibrated_metrics`
  （全有全无的 `benchmarks_calibrated` 布尔看不出 3/5 的进度）。
- 门禁脚本同步：`threshold_source` 白名单、行业基准变量豁免页码回溯（外部校准量没有
  年报页码）、行业阈值样本 <5 家判 FAIL。
- demo 契约此前漏放的两个既有缺口一并修正：`_prev/_delta` 变体按基本指标回溯页码；
  规则派生量（如 dividend_to_ocf）页码由证据链"数据"层承担，降级为 WARN。

**给 D**：`from_b.py` 适配器建议透传 `threshold_value / threshold_source / peer_sample_n`
三件套 + 新增的 `threshold_basis / threshold_note`，页面上才能显示"阈值是同业分位还是
法规硬线"。本地无 D 分支解包目录，`--with-d` 实测未复跑（字段均为增量，不影响现有适配）。

### v1.6b 增补：同业对比扩展到任意行业（板块级基准池）

银行业的专属建池脚本升级为**通用机制**，任何行业的公司输入后都能做同业对比：

- **`risk-radar/scripts/fetch_industry_samples.py`**：输入东财板块代码 / 名称 /
  公司代码（自动解析所属板块，如 600519 → 白酒Ⅱ），抓成分股按市值前 40 家的
  8 项指标（ROE、毛利率、净利率、资产负债率、流动/速动比率、应收/存货周转天数），
  算分位数落盘 `peer_samples/boards/<BK>.json`。指标单位已用茅台 2025 年报逐项复核。
- **引擎侧 `--benchmarks` 参数**：板块池与剖面基准合并（同一指标板块池优先，
  n<5 的指标不参与合并），注入同一命名空间变量。声明了 `benchmark_judge` 的规则
  在任何行业自动改用板块分位数判定，缺失则回退固定阈值并标注 `fixed_fallback`。
- **通用规则接线**：P06（毛利率 vs 行业中位数，peer_percentile 类）与
  S01（资产负债率 vs 行业 P75，convention 类——惯例 60% 为主、分位数辅助，
  避免对高杠杆行业跨行业误报）。
- **茅台实证（真实 A 股数据）**：不带池时 P06 `not_evaluable`（外部基准缺失）；
  带白酒池后 P06 用行业中位数 70.35% 判定 → passed（茅台 91.18%）。S01 用行业
  P75 36.61% 判定 → passed（茅台 16.42%）。**同业池不仅提供对比，还把原本
  不可评估的规则救活**。工行案例回归不受影响（B06 仍用银行业剖面中位数）。

**工作台接入方式**：输入公司 → detect_risks.py **`--benchmarks auto`** →
引擎按公司代码自动解析所属板块（东财 f127，结果缓存 `_company_board.json`，
第二次起零网络）→ 本地有池即用，无池不建、提示建池命令（`fetch_industry_samples.py
--code <公司> --write`，或加 `--ensure-pool` 现场建一次）。行业剖面同理：
不传 `--industry` 时按 company.industry 关键词自动匹配（三级解析，输出
`resolved_from` 写明）。板块池按年报季后刷新一次即可。

### v1.6d 同业对比可视化（2026-11-05 凌晨）

之前只有风险矩阵一个跨公司视图，`comparison/*.json` 和板块池分位数**没有任何页面渲染**。
本轮补齐，两个新文件 + 一条管线命令：

| 文件 | 作用 |
|---|---|
| `risk-radar/scripts/build_peer_view.py` | 数据层：篮子 11 家指标 + 板块池分位线 + 杜邦三因子 → `peer_view.json` |
| `scripts_build_peer_view.py` | 渲染层：`peer_view.json` → 单文件 `peer_view.html`（静态 SVG，零依赖、零 JS） |

三个视图：

1. **逐指标点图**（8 项指标）：每家一个点、目标公司红色高亮、板块池 P25/中位数/P75
   三条分位线；dso 跨 4 个数量级用对数刻度并在图上注明。
2. **差距条形图**：目标 − 行业中位数，条长以四分位距（IQR）为单位，
   红=不利偏离、绿=有利偏离，旁边标实际数值与相对偏离。
3. **杜邦三因子并排**：净利率 × 总资产周转率 × 权益乘数 = ROE，跨公司逐列对比、
   按 ROE 排序、目标行高亮；**闭合差随图透出**（1e-15 级浮点噪声属正常）。
   注意：杜邦此前只是单家公司自身两期对比（`attribution.dupont`），跨公司并排是本轮新增。

诚实标注三件事：① 篮子跨行业，池线只对同板块公司严格可比（顶部横幅写明）；
② 分位线带 n 与 calibrated/indicative 状态，不是合格线；③ 缺值公司不画点
（格力 ROE `not_meaningful` → 杜邦灰行说明原因），绝不按零值落图。
周转天数口径：篮子是次数（次/年）、池是天数，数据层按 `365/次数` 换算并在图下注明公式。

一键重生成：`bash cases/a-share-basket/run_basket.sh`（第 6 步自动产出 peer_view.*），
或手动：`build_peer_view.py --ratios-dir ... --board-pool ... --target 600519 -o peer_view.json`
→ `scripts_build_peer_view.py --view peer_view.json --out peer_view.html`。
换目标公司改 `--target` 即可；目标公司所属板块应与板块池一致，否则横幅的可比性提示会如实变弱。

---

## 十、命名说明（提请注意）

分工文档（10/02 版）里项目叫 **FinScope**，但你在需求描述里说的是 **FinRadar（财报雷达）**，
工作区目录也是「财报雷达」。

本交付包统一使用 **FinRadar**。如果 GitHub 仓库已经建成了 `FinScope`，
只需要把各 README / SKILL.md 里的项目名替换掉，**目录名和文件名不受影响**（`financial-diagnosis/`、`risk-radar/` 是分工文档定死的）。

需要我统一改成 FinScope 的话说一声，一条命令就能批量替换。
