# 可视化参考：Investor Cockpit

- URL：`https://f94ed955804d44bc89ebdd709d191ed8.app.workbuddy.host/`
- 标题：`ACT4244/6244 HW1 - Investor Cockpit - 226020861`
- 截图：`docs/reference_investor_cockpit.png`（整页，1012×6134）

> 这是前端设计阶段的视觉参考，不是要照搬内容。我们要复用的是
> 「一段中文判断 + 一张数据排布紧密的图表」的节奏，以及它的排版密度。

## 1. 版式

- 单页长报告，自上而下分区；每个区块是「编号 + 粗体标题 + 一句结论 + 小字说明 + 图表」。
- 顶部是 6 张摘要卡（3×2）：价格 vs 基本面、质量速览、盈利、投资逻辑、预测、股本。
- 中段是 2–3 列网格：左边文字/结论，右边图表；或三家公司并排的 grouped bar。
- 底部是密集表格 + 脚注 + 数据来源/限制说明。
- 图表与文字之间没有大留白，整体信息密度高；每张图下方都有一行小字解释
  「怎么读 / 数据口径 / 来源」。

## 2. 视觉规范（从页面计算样式提取）

| 项 | 值 |
|---|---|
| 页面背景 | `#F5F7FA`（浅灰蓝） |
| 面板背景 | `#FAFCFF`（近白） |
| 主文字 | `#2D3748` |
| 标题 | `#14263F`（深海军蓝） |
| 主色 / 边框 | `#1E3A5F`、`#B9C8DA` |
| 警示底色 | `#FDF6E4`（浅黄） |
| 危险底色 | `#FDF0EF`（浅红） |
| 正/安全底色 | `#EDF6F1`（浅绿） |
| 信息底色 | `#E7EAF6`（浅蓝紫） |
| 正文字体 | `"PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif` |
| 正文字号 | 13px，行高 1.5 |
| 二级标题 | 14px / 600 |
| 数字 | 等宽字体（monospace），表格与卡片里大量使用 |
| 圆角 | 小圆角（4–6px），细边框，不用重阴影 |

## 3. 图表类型（按区块）

| 区块 | 图表 |
|---|---|
| Price discipline | 水平 bullet/range 图：估值区间 + 目标点 + 当前点 |
| Reinvestment — ROIC vs five years | 双线折线图 |
| Counting the years | 三组 grouped bar（三家公司并排），柱上标数值 |
| Where each dollar goes | 水平堆叠条（100% 构成） |
| Cash quality | 柱 + 线组合（CFO / FCF / capex） |
| Diluted EPS indexed | 多线折线图（首年=100） |
| Verdict / scorecards | 三张并排卡片，每张内含小 bullet 图 |
| Deterioration | 折线图（多指标） |
| Five-year snapshot | 密集表格 |
| Cost of capital | 表格 + 脚注 |
| Laddered scorecard | 3×2 卡片网格，每张一个横向进度/评分条 |

## 4. 对我们估值工作台的映射

| 参考区块 | 我们的数据 |
|---|---|
| 顶部摘要卡 | `blended` + `market_data` + `reliabilities` |
| Price discipline | `presentation.charts.valuation_range`（low/mid/high/price/blended/dcf/sotp） |
| ROIC vs five years | `dcf.rows` 的 ROIC/EBIT 趋势（后续可加 `roic` 序列） |
| Counting the years | `comps_position`（目标 vs 同业 P25/中位/P75） |
| Where each dollar goes | `dcf_forecast` 的 capex/da/nwc 构成 |
| Cash quality | `dcf_forecast.series.fcff/ebit` |
| EPS indexed | `dcf_forecast` 可扩展 EPS（后续） |
| Verdict cards | `sensitivity` 的基准格 + 三情景 |
| Deterioration | `sensitivity_growth_margin` 热力矩阵 |
| Five-year snapshot | `dcf.rows` + `comps.results` |
| Cost of capital | `dcf.wacc_block` + `wacc_reconciliation` |
| Scorecards | `reliabilities` + `blended.trace` |

## 5. 设计原则（前端阶段）

1. **先结论后图表**：每块先给一句中文判断（来自 `narrative.sections[].paragraphs`），
   再放图；图下方一行小字写口径与来源。
2. **图表要「排布紧密」**：小字号、细边框、刻度精简、直接标注数值；
   不要大面积留白和粗重阴影。
3. **颜色只表达含义**：主色海军蓝；正/低估用绿，高估/风险用红，提示用黄；
   不要用彩虹色。
4. **数字等宽**：价格、倍数、百分比用 monospace，便于纵向对比。
5. **风险提示不折叠**：`warnings` / `gates` 放在结论旁边或下方，显著但不抢主结论。
6. **中文排版**：正文 13–14px，行高 1.6；标题 15–16px；避免英文全大写长句。

## 6. 与 FinScope 现有原型的关系

现有 `FinScope_2.0_可交互UI原型.html` 是整站骨架（首页/概览/诊断/风险/估值实验室/证据/报告）。
估值工作台应沿用其导航与卡片风格，只把「估值实验室」的内容替换成：

- 顶部：方法选择（DCF/Comps/SOTP/综合）+ 对话入口；
- 中部：结论卡 + 估值区间 bullet 图 + 权重/可靠性；
- 下部：Comps 表、DCF 预测表、两张敏感性热力图、三情景、假设台账；
- 右下：导出 Excel 按钮。

参考页的密度和「文字 + 图」的节奏可以直接借用；颜色可以收敛到 FinScope 已有的深蓝/米白体系。
