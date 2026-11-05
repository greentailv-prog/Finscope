> **FinScope C v3.1 审慎估值修订优先级提示（2026-11-04）**：本文部分旧版 v2/v3 规则已失效，尤其包括“无同业使用板块代理”“默认 Gordon 与退出倍数取中点”“市场隐含 WACC 默认校准”“缺分部构造单一整体业务”“总部费用按收入 2%×8 倍默认扣减”。上述规则不得再作为上线依据。请优先遵循工程根目录的《估值后端v3_1_审计修订与联调手册.md》及当前代码与测试。原文作为历史基线保留，不代表当期执行规则。

> **FinScope C v3 增量交付提醒**：本目录基于原 C v2 保留代码，v3 的新版工作台为 `frontend/valuation_lab.html`，估值 Excel 专业版为 `export/institutional.py`，普通 Python 使用原导出器兼容回退。详见上一级 `README_交付总览.md`、`ABC_对接说明.md` 与 `SKILL_v3.md`。

# FinScope 估值模块 v2

面向 FinScope 产品的估值后端：**DCF / Comps / SOTP / DDM** 四种口径，
通过规则层自动补假设、选同业、选指标、定权重，输出「中文结论 + 图表数据 + 公式联动 Excel 底稿」。

> v1 的代码完整保留在 `_legacy/`，没有删除。新代码在 `core/`、`data/`、`export/`、`api/`。

## 1. 它解决什么问题

旧版三个关键问题：

1. **缺输入就跳过方法**：没有同业就不做 Comps，没有假设就不做 DCF。
2. **三法机械平均**：DCF 与 Comps 差 5 倍仍然按 50/50 平均，输出「显著低估」。
3. **CAPM 折现率失真**：低利率环境下 WACC 被算到 3%–4%，DCF 被系统性放大。

v2 的对应规则：

- 缺同业 → 按「行业池 → 板块代理」自动选 4–6 家，逐家披露选取理由；仍无样本才降级。
- 缺假设 → 用近 3/5 年 CAGR、近三年中位数、市场利率按规则合成，写入假设台账并标置信度。
- 缺分部 → 用年报「主营构成」自动拆分；再没有就构造「整体业务」兜底并明确降权。
- 三法融合 → 先算可靠性评分，再按可靠性、方法分歧度动态定权；分歧 >50% 时输出区间参考，不给误导性的单点目标价。
- WACC → 同时给 CAPM 值与市场隐含值；差距 >150bp 时按规则校准，并披露校准幅度。

## 2. 快速开始

```bash
# 在 valuation 的上一级目录
set FINSCOPE_DATA_PYTHON=D:\path\to\python.exe

python -m valuation.cli value 600519
python -m valuation.cli value 600519 --method dcf
python -m valuation.cli value 000333 --method sotp
python -m valuation.cli value 600036 --method auto
python -m valuation.cli value 600519 --source web     # 联网年报 PDF 取数
python -m valuation.cli search 600519 --years 2022-2025
python -m valuation.cli probe-sources                 # iFinD / Choice 探测
python -m valuation.cli questions 600519
python -m valuation.cli health

# 三家公司端到端检验
python -m valuation.tests.simulate_three
python -m valuation.tests.simulate_web

# HTTP 服务 + 前端估值工作台
python -m valuation.api.server       # http://127.0.0.1:8010/ui/valuation_lab.html
                                     # API 文档：http://127.0.0.1:8010/docs
```

也可以直接 `cd valuation; python cli.py value 600519`。

## 3. 目录结构

```
valuation/
├── core/                     纯计算与规则，不碰网络
│   ├── models.py             数据结构（Company/Financials/Peer/Segment/Assumptions）
│   ├── metrics.py            数学工具（中位数、分位、CAGR、离散度、二分法）
│   ├── defaults.py           配置读取、行业匹配、行业门槛
│   ├── assumptions.py        规则补假设 + 假设台账
│   ├── dcf.py                FCFF / 终值 / 市场隐含 WACC 校准
│   ├── comps.py              多倍数、同业统计、目标定位、倍数调整
│   ├── sotp.py               分部估值、总部费用、集团折价
│   ├── ddm.py                金融行业 DDM / 剩余收益
│   ├── sensitivity.py        WACC×g、增速×利润率、三情景
│   ├── rules.py              可靠性评分、定权、交叉验证、问题清单
│   ├── narrative.py          中文结论 + 图表数据
│   └── engine.py             主编排 run(payload)
├── data/                     数据层
│   ├── akshare_provider.py   新浪财报 + 东财公司信息/主营构成 + 中债收益率
│   ├── peer_selector.py      行业池/代理样本/分部纯业务同业
│   ├── segments.py           主营构成 → SOTP 分部
│   ├── adapters.py           D canonical / v1 JSON / 代码 三种输入适配
│   ├── cache.py              本地 JSON 缓存
│   └── sources.py            来源台账
├── export/excel.py           公式联动 Excel 底稿（12 张表）
├── api/server.py             FastAPI 服务（会话 + 交互 + 下载）
├── frontend/                 估值工作台（HTML + 离线样例 + 截图）
├── config/                   行业可比公司池、市场参数、门槛
├── tests/simulate_three.py   三家公司端到端检验
├── output/                   运行产物
└── _legacy/                  v1 原实现（保留对照）
```

## 4. 输入与输出

### 输入（最小）

```json
{"company": {"ticker": "600519", "market": "A"}}
```

其余都可以由规则层补：假设、同业、分部、利率。

### 输入（D 的 canonical 对象）

直接传 `company` / `financials` / `market_data` / `comparison.peer_set` /
`peer_financials` / `peer_market_data` 即可；C 会优先使用 D 传入的数据，
**不自己另取一个价**。字段映射见 `INPUT_SCHEMA.md`。

### 输出

顶层字段与 ABC 接口规范第 7 节对齐：

```
status / industry_support / market_data / assumptions /
dcf / relative（=comps，兼容 D 的 from_c）/ comps / sotp / ddm /
blended / scenarios / sensitivity {wacc_g, growth_margin} /
gates / warnings / sources / excel_path /
presentation { narrative, charts }
```

`presentation.narrative` 是给前端的「中文文字 + 指标卡」；
`presentation.charts` 是给前端直接画的图数据（FCF 预测、估值区间、敏感性矩阵、情景、倍数定位、权重）。

## 5. 规则摘要

| 场景 | 规则 |
|---|---|
| 缺同业 | 行业池（4–6 家）→ 板块代理（低置信度），逐家披露理由 |
| 缺假设 | 近 3/5 年 CAGR + 最近同比加权；利润率/费率取近三年中位数；税率夹 15%–30% |
| 缺分部 | 东财「主营构成」最新年报；顶层有 ≥2 个「其中:」子项且覆盖 ≥80% 时展开 |
| 缺 D&A/资本开支/营运资本 | 按规则估算并标「低置信度」，不伪装成原始数据 |
| 银行/保险/证券/地产 | 标准 FCFF 不适用；银行/保险/证券改用 DDM/剩余收益 + PB/PE Comps，输出 `partial/limited`；地产只用 Comps，无 NAV/FFO 时 `unsupported` |
| 方法分歧 >50% | 按可靠性定主方法（70%–80%），其余降为参考；输出区间而非单点 |
| CAPM 与市场隐含 WACC 差 >150bp | 向市场隐含值靠拢 60%，最多 ±4%，同时披露两个值 |
| 营收/净利同比 < -40% | 判定口径异常，剔除该年流量数据，改用上一可靠年度，显著告警 |
| 终值占比 >85% / TV 两法偏离 >30% | 降低 DCF 可靠性评分，写入 gates |
| 三情景 | Bull/Base/Bear 必须满足增速、利润率、WACC 的单调性 |

## 6. 可靠性与定权

| 方法 | 扣分项（示例） |
|---|---|
| DCF | 终值占比 >85%（-25）、TV 两法偏离 >30%（-15）、CAPM/市场 WACC 差 >150bp（-15）、WACC−g <2%（-20）、历史 <3 年（-15）、费率估算（每项 -6） |
| Comps | 同业 <3 家（-25~-40）、动态/代理样本（-10/-25）、离散度 >60%（-15）、只有 1 个倍数（-15） |
| SOTP | 覆盖 <80%（-20）、只有 2 个分部（-15）、仅收入口径（-10）、总部费用估算（-5） |
| DDM | 分红率估算（-10）、DDM 与 RI 差 >35%（-15）、Ke−g <2%（-20） |

默认权重：无 SOTP → DCF 50% / Comps 50%；有 SOTP → 40%/30%/30%；
金融 → DDM 50% / Comps 50%。可靠性分数再乘 0.25–1.10 的权重乘数。
方法分歧 >50% 时改为「主方法 70% + 其余按可靠性分配 30%」；>100% 时主方法 80%。

## 6.5 前端估值实验室

- 页面：`frontend/valuation_lab.html`
- 启动后端后：`http://127.0.0.1:8010/ui/valuation_lab.html`
- 离线可双击 `frontend/valuation_lab.html` 看四家公司样例
- 功能：研究任务入口、上传年报 PDF、方法选择、估值设定台、结果总览、
  区间图、分段式结论、Comps 可比性、实际/预测 FCF 图、预测财务报表、
  增长假设图、SOTP、敏感性、三情景、风险提示、右侧 AI 研究助手
- AI 助手：默认规则助手；设置 `DEEPSEEK_API_KEY`（推荐，模型 `deepseek-chat`）
  或 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 可接 OpenAI 兼容模型
  （ChatGPT Plus 订阅本身不提供 API）
- 公司搜索：输入股票代码或公司简称，自动读取历史财务、分部、行情与来源，再运行估值
  （`/api/valuation/companies/search` + `/api/valuation/companies/{ticker}/data`）
- 右侧 AI 助手：规则助手 + 可选 DeepSeek/OpenAI 兼容模型

详见 `frontend/README.md`。

## 7. Excel 底稿

12 张表：

`说明 / 参数假设 / DCF测算 / 相对估值 / 分部估值 / DDM测算 / 三法融合 /
敏感性-WACC×g / 敏感性-增速×利润率 / 假设台账 / 数据来源 / 行业门槛与规则`

- **参数假设**是单一真源，DCF 与融合表公式引用它；
- WACC 拆成「CAPM 口径 + 市场校准 + 采用」三行，保证底稿与 JSON 结论一致；
- Comps 的调整比例、采用倍数、隐含价值、结论全部公式联动，异常值通过辅助列剔除；
- 敏感性矩阵与情景是引擎逐格重算的静态值，表内注明「改假设后重新导出刷新」。

已用真机 Excel 重算验证：四家 akshare 样本 + 三家年报 PDF 样本底稿 **零错误格**，
DCF/Comps/融合关键值与 JSON 完全一致。

## 8. 三家模拟检验结果

> 下表是 2026-11-03 的历史回归快照。当前代码每次运行都会重新生成
> `valuation/output/<ticker>_<year>_result.json` 与 18 表底稿；以那些文件为准。

| 公司 | 状态 | 方法 | 融合每股 | 判断 | 置信度 |
|---|---|---|---:|---|---|
| 600519 贵州茅台 | ok | DCF/Comps | 2,104.86 | 显著低估 | 中 |
| 000333 美的集团 | ok | DCF/Comps | 82.91 | 估值分歧较大（区间参考） | 低 |
| 600036 招商银行 | partial / limited | DDM/Comps | 53.77 | 估值分歧较大（区间参考） | 低 |
| 000858 五粮液 | ok（剔除异常年） | DCF/Comps | 146.84 | 显著低估（高不确定性） | 低 |

详见 `tests/reports/00_模拟检验报告.md`。

### 联网年报 PDF 对照检验

`python tests/simulate_web.py` 会走「巨潮资讯 → 年报 PDF → pdfplumber → 估值」：

| 公司 | 年报年度 | DCF | Comps | SOTP | DDM | 融合 | 判断 |
|---|---|---|---|---:|---:|---:|---:|---|
| 600519 贵州茅台 | 2023–2025 | 1,739.39 | 1,376.73 | 1,104.04 | — | 1,592.41 | 区间参考 |
| 000333 美的集团 | 2023–2025 | 99.73 | 73.44 | 98.33 | — | 90.90 | 大致合理 |
| 600036 招商银行 | 2024–2025 | — | 29.23 | — | 59.67 | 35.31 | 区间参考 |

详见 `tests/reports_web/00_联网年报检验.md`。其中 600036 在 2026-11-05 修订后
输出 `status="partial"`、`industry_support="limited"`、`gate_reason="standard_fcff_unsupported; ddm_used"`，
不再使用 `unsupported`。

## 9. 数据源

| 用途 | 来源 | 性质 |
|---|---|---|
| A 股历史财务 | 新浪财经（akshare `stock_financial_report_sina`） | 非官方 |
| 公司信息/行情/股本/行业 | 东方财富（akshare `stock_individual_info_em`） | 非官方 |
| 分部收入 | 东方财富「主营构成」（akshare `stock_zygc_em`） | 非官方，年报附注简化口径 |
| 10 年期国债收益率 | 中债（akshare `bond_zh_us_rate`） | 官方 |
| ERP | Damodaran 国家风险溢价表 | 官方研究数据 |
| 联网年报 PDF | 巨潮资讯年报检索 + pdfplumber 解析 | 官方披露原文 |
| 官方源 | iFinD / Choice 适配器（需客户端+账号+指标映射） | 官方 |

数据源选择：`data_source="auto"` 默认走 akshare；`web` 走年报 PDF；`ifind`/`choice` 走官方源；
D 已传 `financials`/`market_data` 时走 `canonical`，C 不再另取。

当前本机探测：iFinD 未安装客户端/DLL、无凭证；Choice 有 Python 包但缺 DLL、无凭证。
详见 `docs/DATA_SOURCES.md`。

所有来源写入 `sources[]`，带 `as_of`、`official`、`purpose`。

## 10. 已知边界

- 美股内置数据源未实现；可由 D 传 canonical 数据。
- 主营构成的「分部利润」只到毛利；EBIT/EBITDA 按毛利占比分摊，已披露。
- 分部纯业务同业倍数来自 A 股行业池；未接 iFinD/Wind 时是近似值，已在 `tier` 标注。
- 银行 DDM 的 Ke 采用「CAPM + 市场隐含 Ke 校准」；市场隐含 Ke 的校准幅度最多 8%，仍可能偏离。
- 敏感性矩阵 / 情景在 Excel 中是静态重算值，不是模拟运算表；改假设需重新导出。
- 联网年报 PDF 解析对「母公司/合并报表同页」「银行百万元口径」已做处理；极端排版仍可能漏抽，
  此时返回证据包与告警，由 Agent/使用者复核，不编数。
- 官方 iFinD / Choice 适配器已就位（`data/official_provider.py`），但本机缺客户端 DLL 与账号；
  A 接入后需先跑 `python cli.py probe-sources` 与指标映射实测。

## 免责声明

本模块仅供研究与教学用途，不构成投资建议。所有估值都建立在假设之上，**假设比模型重要**。
