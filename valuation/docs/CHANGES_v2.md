# 估值模块 v2 改动清单

> 对照对象：`FinScope中期汇报/final/Finscope-C-/Finscope-C-Comps-DCF/valuation` 的 v1。
> v1 原文件完整保留在 `_legacy/`（`engine/`、`datasource/`、`tools/`、`cli.py`）。

## 一、一句话总结

v1 是「三法计算器」：有输入就算，没输入就跳过，最后把结果按固定权重平均。
v2 是「估值决策系统」：缺输入时按规则补假设、选同业、选指标，按可靠性和分歧度定权，
输出结论、区间、证据、图表数据和公式联动底稿，并接上 D 的 ABC 接口规范。

## 二、旧版实测问题（改造依据）

用同一套免费数据跑 v1，得到：

| 公司 | v1 WACC | v1 DCF 每股 | 现价 | 结论 | 问题 |
|---|---:|---:|---:|---|---|
| 600519 贵州茅台 | 3.98% | 4,117 | 1,478 | 显著低估 +178.6% | CAPM 折现率远低于市场隐含 9.94%；终值占比 90% |
| 000333 美的集团 | 3.56% | 501.79 | 89.44 | 显著低估 +461% | WACC−g 仅 1.06%，Gordon 终值爆炸 |
| 600036 招商银行 | — | 崩溃 | — | 程序异常 | 无 upsides 时格式化 None 崩溃；银行仍跑标准 DCF |

根因不是数据，是**规则层缺失**：

1. CAPM 在低利率环境算出 3%–4% 的 WACC，没有和市场定价交叉验证；
2. 终值只做 Gordon + 退出倍数，没有 ROIC 再投资口径，也没有“WACC−g 太小”的硬约束；
3. 没有行业门槛，银行也跑 FCFF；
4. 没有方法可靠性，只有固定 50/50；
5. 没有同业自动选择，`--peers` 不给就跳过 Comps；
6. 没有分部数据来源，SOTP 永远空表；
7. 没有数据口径异常检测，五粮液 2025 年营收 -55% 直接进入预测。

## 三、结构性改动

### 1. 分层重构

| 层 | 目录 | 职责 |
|---|---|---|
| 核心计算 | `core/` | DCF、Comps、SOTP、DDM、敏感性、情景；不碰网络 |
| 规则 | `core/rules.py`、`core/assumptions.py` | 补假设、可靠性评分、定权、交叉验证、问题清单 |
| 数据 | `data/` | akshare 取数、同业选择、分部解析、canonical 适配、缓存、来源台账 |
| 输出 | `core/narrative.py`、`export/excel.py` | 中文叙述 + 图表数据；公式联动 Excel |
| 接口 | `api/server.py`、`cli.py` | HTTP 会话 + 命令行 |

v1 的 `engine/*.py` 是一个大文件式实现；v2 拆成单一职责模块，便于前端/Agent 分别调用。

### 2. 新增能力

| 能力 | v2 实现 |
|---|---|
| 缺同业不跳过 | 行业池（35 个主题）→ 板块代理 → 无样本才降级；逐家 `selection_reason` |
| 缺假设不跳过 | 近 3/5 年 CAGR + 最近同比加权；利润率/费率近三年中位数；税率夹 15%–30%；全部进台账 |
| 缺分部不跳过 | 东财「主营构成」最新年报；自动展开「其中:」子分部；无数据时整体业务兜底并降权 |
| 方法选择 | `auto / dcf / comps / sotp / blended / ddm`；单一方法也可独立运行 |
| 多倍数 | PE、前瞻 PE、PEG、PB、PS、PCF、EV/Revenue、EV/EBITDA、EV/EBIT |
| 高毛利保护 | EBIT 利润率 >50% 时，PS/EV-Revenue 只作参考，不进入 Comps 结论 |
| 可靠性评分 | DCF/Comps/SOTP/DDM 各自 0–100 分，列出扣分项 |
| 动态定权 | 默认权重 × 可靠性系数；分歧 >50% 改为主方法 70%+其余 30%；>100% 主方法 80% |
| 区间参考 | 分歧 >50% 输出区间，不强行给误导性单点目标价 |
| WACC 市场校准 | CAPM vs 市场隐含 WACC，差 >150bp 时按 60% 靠拢，最多 ±4% |
| DDM 市场校准 | 金融行业 Ke 同理，最多 ±8% |
| 数据口径检测 | 营收/净利同比同时 <-40% → 剔除该年流量数据，改用上一可靠年度，显著告警 |
| 三情景 | Bull/Base/Bear 单调性检查（增速、利润率、WACC） |
| 两张敏感性 | WACC×g；首年增速×EBIT 利润率 |
| 中文叙述 | 结论先行 → 方法选择 → Comps → DCF → SOTP → 情景 → 风险 |
| 图表数据 | FCF 预测、终值构成、估值区间、两张敏感性、情景、倍数定位、权重 |
| HTTP 服务 | 会话创建、问题清单、补输入、运行、改假设重算、结果、Excel 下载 |
| Excel 底稿 | 12 张表，参数假设单一真源，Comps/融合公式联动 |

### 3. 关键 bug 修复

| 问题 | 修复 |
|---|---|
| v1 隐含 WACC 反解用 15x 兜底退出倍数，正式 DCF 用同业倍数 → 反解值系统性偏高（000333 从 13.19% 降到 9.81%） | 退出倍数只算一次，隐含反解与正式 DCF 共用 |
| v1 银行资产负债表取不到「所有者权益」，DDM/ PB 全空 | 增加「股东权益」「归属于母公司股东的权益」等键名与兜底 |
| v1 Comps 的 `applied_multiple` 与 `implied_equity` 口径不一致 | 统一用 `applied = peer_median × (1+adjust)` |
| v1 Excel Comps 没有应用调整比例，底稿与 JSON 不一致 | Excel 增加「调整比例」「采用倍数」两行，隐含价值引用采用倍数 |
| v1 Excel WACC 只写 CAPM，未写市场校准 | 参数假设拆成「CAPM WACC + 市场校准 + 采用 WACC」三行 |
| v1 Excel 敏感矩阵引用不存在的函数/错位 | v2 改为引擎逐格重算的静态矩阵，明确标注 |
| v1 无行情时 summary 格式化 None 崩溃 | v2 所有 per_share/upside 允许 None，摘要分支处理 |
| v1 五粮液 -55% 营收直接进入预测 | v2 自动剔除异常年，改用 2024 年基准 |

## 四、文件变更

### 新增

```
core/models.py            数据结构
core/metrics.py           数学工具
core/defaults.py          配置读取/行业匹配/行业门槛
core/assumptions.py       规则补假设 + 台账
core/dcf.py               DCF + 市场隐含 WACC 校准
core/comps.py             多倍数 Comps + 定位 + 调整
core/sotp.py              分部估值
core/ddm.py               金融行业 DDM/剩余收益
core/sensitivity.py       两张敏感性 + 三情景
core/rules.py             可靠性/定权/交叉验证/问题清单
core/narrative.py         中文叙述 + 图表数据
core/engine.py            主编排
data/akshare_provider.py  新浪财报 + 东财信息/主营构成 + 中债利率
data/peer_selector.py     行业池/代理/分部同业
data/segments.py          主营构成 → SOTP 分部
data/adapters.py          D canonical / v1 / 代码 输入适配 + 口径检测
data/web_provider.py      巨潮资讯年报检索 + PDF 解析（联网搜索取数）
data/official_provider.py iFinD / Choice 适配器与探测
data/cache.py             本地缓存
data/sources.py           来源台账
export/excel.py           12 张表公式联动底稿
api/server.py             FastAPI 会话服务
config/industry_peers.json 35 个行业的可比公司池
config/sector_params.json  市场参数、行业锚点、门槛、阈值
tests/simulate_three.py   三家公司端到端检验（akshare）
tests/simulate_web.py     三家公司联网年报 PDF 检验
docs/API.md               接口文档
docs/DATA_SOURCES.md      数据源与接入说明
docs/CHANGES_v2.md        本文件
schema/                   （预留 JSON Schema）
```

### 重写

```
README.md / RULES.md / SKILL.md / INPUT_SCHEMA.md / OUTPUT_SCHEMA.md
cli.py（保留 value/run/health，新增 questions；支持 --method）
```

### 保留

```
_legacy/                   v1 engine/datasource/tools/cli
demo/                      旧演示输入/输出
output/                    运行产物
_extract/                  官方接口临时解压目录
.env.example / .gitignore
```

## 五、与 ABC 接口规范的对接

| 规范要求 | v2 实现 |
|---|---|
| `valuation.status` | `ok / partial / unsupported / failed` |
| `industry_support` | `supported / limited / unsupported`，银行/保险/证券/地产命中门槛 |
| `market_data` 回显 | D 传入优先，C 取完财务后再次覆盖，不自己另取价 |
| `relative` → `comps` | 同时输出 `relative` 与 `comps` 别名 |
| `peers_detail` → `peer_companies` | 两边都输出；`peer_selection` 给理由 |
| `sensitivity.wacc_g` | 新增；旧 `wacc_axis/growth_axis/grid` 保留 |
| `dcf.forecast` | 新增；`dcf.rows` 保留 |
| `assumptions[]` | 17 条左右，带 source_type/source/confidence/overridable |
| `excel_path` | 返回本地路径；D 生成 `excel_url` |
| `blocked` | C 不写；只给 `gates.severity=block`，由 D 的质量闸门决定 |
| 无同业 | `comps.ok=false` + `warnings`；但 v2 会先尝试行业池/代理，不轻易跳过 |
| 无行情 | `per_share=null`，股权价值仍给 |
| 银行 | `status=unsupported`，不跑标准 DCF；输出 DDM + PB/PE Comps 作为替代 |

## 五点半、数据源接入（本轮新增）

### 1. 联网年报取数（`data_source="web"`）

- 巨潮资讯年报检索（结构化，按代码+orgId）→ 下载年报 PDF → pdfplumber 解析；
- 抽取合并利润表、合并现金流量表、合并资产负债表、现金流量表补充资料、主营业务分产品；
- 自动识别 `元 / 千元 / 万元 / 百万元 / 亿元`；
- 支持「合并及公司」四列表（取合并列）、母公司/合并同页、银行科目别名；
- 分部父级小计与子项同时出现时，按收入合计自动去重；
- 证据包写入 `web_evidence`，可复核后复用；
- 默认不走系统代理，避免代理软件挂掉导致整条数据链失败。

新增文件：`data/web_provider.py`、`tests/simulate_web.py`、`docs/DATA_SOURCES.md`。

### 2. iFinD / Choice 适配器

- 新增 `data/official_provider.py`，与 A 共用 `.env` 凭证约定；
- `probe-sources` / `/api/valuation/sources/probe` 可探测 installed / DLL / credentials / login；
- 本机实测：iFinD 无客户端/DLL/账号；Choice 有 Python 包但缺 DLL/账号，均不可用；
- 适配器已留好接入点；A 装好客户端并写 `.env` 后，设置 `FINSCOPE_OFFICIAL=1` 即可启用。

### 3. 数据源选择

`data_source`：`auto / canonical / ifind / choice / web / akshare`。
D 传入 `financials` / `market_data` 时优先使用，C 不另取一套数。

## 六、三家公司模拟检验

运行：

```bash
python -m valuation.tests.simulate_three
```

产出 `tests/reports/`：

| 文件 | 内容 |
|---|---|
| `00_模拟检验报告.md` | 中文总览、逐家结果、门槛、提示 |
| `summary.json` | 机器可读汇总 |
| `<ticker>_result.json` | 完整 valuation JSON |
| `<ticker>_估值底稿.xlsx` | 公式联动底稿 |

### 结果

| 公司 | 状态 | DCF | Comps | SOTP | DDM | 融合 | 现价 | 判断 | 置信度 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 600519 贵州茅台 | partial | 1,815.59 | 1,360.48 | 1,075.70 | — | 1,383.81 | 1,480.00 | 区间参考 | 低 |
| 000333 美的集团 | partial | 102.55 | 66.51 | 80.60 | — | 73.63 | 88.88 | 区间参考 | 低 |
| 600036 招商银行 | unsupported | — | 29.23 | — | 60.57 | 54.30 | 42.69 | 区间参考 | 低 |
| 000858 五粮液 | ok | 165.88 | 155.14 | 140.28 | — | 154.57 | 75.55 | 显著低估（高不确定性） | 低 |

### 联网年报 PDF 对照（`tests/simulate_web.py`）

| 公司 | 年报年度 | DCF | Comps | SOTP | DDM | 融合 | 判断 |
|---|---|---|---:|---:|---:|---:|---:|---|
| 600519 贵州茅台 | 2023–2025 | 1,739.39 | 1,376.73 | 1,104.04 | — | 1,592.41 | 区间参考 |
| 000333 美的集团 | 2023–2025 | 99.73 | 73.44 | 98.33 | — | 90.90 | 大致合理 |
| 600036 招商银行 | 2024–2025 | — | 29.23 | — | 59.67 | 35.31 | 区间参考 |

三份底稿同样通过真机 Excel 重算：零错误格，关键值与 JSON 一致。

### 底稿验证

用真机 Excel 打开、`CalculateFullRebuild` 后：

| 公司 | 错误格 | DCF 底稿 vs JSON | Comps 底稿 vs JSON | 融合底稿 vs JSON |
|---|---:|---|---|---|
| 600519 | 0 | 1,815.59 = 1,815.59 | 1,360.48 = 1,360.48 | 1,383.81 = 1,383.81 |
| 000333 | 0 | 102.55 = 102.55 | 66.51 = 66.51 | 73.63 = 73.63 |
| 600036 | 0 | — | 29.23 = 29.23 | 54.30 = 54.30 |
| 000858 | 0 | 165.88 = 165.88 | 155.14 = 155.14 | 154.57 = 154.57 |

### 交互式方法选择回归（000333）

| 选择 | 计划方法 | 状态 | 融合每股 | 判断 |
|---|---|---|---:|---|
| 只做 DCF | dcf | partial | 102.55 | 低估 |
| 只做 Comps | comps | partial | 66.51 | 高估 |
| 只做 SOTP | sotp | partial | 76.95 | 高估 |

## 六点半、前端估值工作台

新增 `frontend/valuation_lab.html`（+ `sample_data.js`），按产品完整壳子重做：

- **公司搜索入口**：输入股票代码/公司简称 → `/api/valuation/companies/search` → 下拉候选 →
  `/api/valuation/companies/{ticker}/data` 读取全部历史财务/分部/行情/来源 → 运行估值；

- 左侧产品导航 + 中间估值实验室 + 右侧 AI 研究助手；
- 研究任务入口：公司/行业/数据源、研究问题、上传年报 PDF、开始研究；
- 方法卡（综合/Comps/DCF/SOTP）+ 估值设定台（核心假设/可比公司/业务分部）；
- 结果区：综合估值、三方法权重、区间图、分段式结论摘要；
- Comps：可比公司表 + 可比性评分 + 逐家理由 + 隐含每股；
- DCF：实际 5 年 FCF + 预测 5 年 FCFF 柱/线图，悬停看数据；
- 预测财务报表核心指标（历史 5 年 + 预测 5 年）；
- 增长假设小图（收入增速/EBIT 利润率/Capex/收入/D&A/收入）；
- SOTP 条形图+表、敏感性热力矩阵、三情景图+卡、关键提示；
- 所有图表元素带悬停浮层；
- 离线样例：600519 / 000333 / 600036 / 000858 四份真实结果，可直接双击打开；
- 连后端：FastAPI 挂载 `/ui`，打开 `http://127.0.0.1:8010/ui/valuation_lab.html`。

新增后端支持：

- `history`：历史财务与比率（给前端画实际 vs 预测）；
- `comps.peer_companies[].comparability`：逐家可比性评分与理由；
- `POST /api/valuation/assistant`：规则助手 + 可选 OpenAI 兼容模型；
- `POST /api/valuation/upload`：年报 PDF 上传解析。

详见 `frontend/README.md`。

## 七、已知限制 / 下一步

1. **美股内置数据源未实现**：当前以 A 股为主；美股可由 D 传 canonical 数据。
2. **分部利润只到毛利**：EBIT/EBITDA 按毛利占比分摊，已披露；接入 iFinD/Wind 后可改真实分部利润。
3. **同业倍数**：默认免费源 / 行业池，`tier` 会标 curated/proxy；iFinD/Choice 适配器已就位，
   但本机缺客户端 DLL 与账号，装好后设置 `FINSCOPE_OFFICIAL=1` 即可启用。
4. **敏感性矩阵在 Excel 中是静态值**：主链（参数→DCF→融合）公式联动；矩阵/情景改假设需重新导出。
5. **银行 DDM 的 Ke 校准**：最多 ±8%，仍可能与市场有偏差；建议前端显著展示 `ke_reconciliation`。
6. **前端可视化参考页已抓取**：`https://f94ed955804d44bc89ebdd709d191ed8.app.workbuddy.host/` 已用浏览器打开并截图，配色/字号/图表类型整理在 `docs/visual_reference.md`，整页截图在 `docs/reference_investor_cockpit.png`。后端已把「中文叙述 + 图表数据」拆好，等确认后再做前端。

## 八、给前端的最小接入清单

- 直接打开：`http://127.0.0.1:8010/ui/valuation_lab.html`（离线可双击 `frontend/valuation_lab.html`）；
- 方法选择：`auto / dcf / comps / sotp / blended`；
- 对话：`POST /api/valuation/questions` → 渲染问题与默认值；
- 运行：`POST /api/valuation/session` → `PATCH inputs` → `POST run`；
- 展示：`presentation.narrative`（中文段落 + 指标卡）、`presentation.charts`（图数据）；
- 下载：`GET /api/valuation/session/{id}/excel`；
- 改假设：`POST /api/valuation/session/{id}/recalculate`。
