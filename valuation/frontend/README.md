# 估值实验室（产品内页面）

主页面：`valuation_lab.html`
离线样例：`sample_data.js`
旧版页面：`valuation_workbench_v1.html`（保留对照；`valuation_workbench.html` 会自动跳转到新版）

## 打开方式

### 方式 A：连后端（推荐）

在 `Finscope-C-Comps-DCF` 目录（`valuation` 的上一级）启动：

```bash
python -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
```

打开：

```
http://127.0.0.1:8010/ui/valuation_lab.html
```

根路径 `/` 会自动跳转到这个页面。

页面能力：

- 选择标的（600519 / 000333 / 600036 / 000858），切换数据源（自动 akshare / 联网年报 PDF / D+A）；
- 输入研究问题，点「开始研究」；
- 上传年报 PDF，解析成财务/分部证据后直接估值；
- 方法卡（综合 / Comps / DCF / SOTP）多选；
- 估值设定台：核心假设 / 可比公司 / 业务分部；
- 运行、重算、导出 Excel；
- 右侧 AI 研究助手：解释结果、按自然语言改 WACC/增速/利润率、重选同业。

### 方式 B：离线看样例

直接双击 `valuation_lab.html`，加载 `sample_data.js` 中的四份真实估值结果。
离线模式下不能运行/重算/导出/对话，但所有图表、文字、表格可完整查看。

## 页面结构

| 区块 | 内容 |
|---|---|
| 左侧 | 产品导航：研究任务、公司研究、行业研究、财务分析、数据中心、估值实验室、财务模型、情景分析、AI 助手 |
| 顶部 | 估值实验室标题、状态、运行估值、导出 Excel |
| 研究任务入口 | **股票代码/公司简称搜索框**（下拉候选）→ 自动读取财务数据 → 运行估值；数据源、研究问题、上传年报 PDF、开始研究 |
| 方法选择 | 综合估值 / Comps / DCF / SOTP |
| 估值设定台 | WACC/无风险/ERP/β；收入增速/永续 g/预测期；税率/资本开支/营运资本；可比公司；业务分部 |
| 结果总览 | 综合估值、DCF、Comps、SOTP、现价/上行空间、权重 |
| 估值区间 | DCF/Comps/SOTP/综合的行式区间图 + 现价竖线 |
| 结论摘要 | 方法选择、Comps、DCF、SOTP 的分段文字（核心观点 + 数据 + 因果） |
| Comps | 可比公司表、目标/中位倍数、可比性评分、逐家选取理由、隐含每股 |
| DCF | 实际 5 年 FCF + 预测 5 年 FCFF 柱/线图，悬停看年份与数值 |
| 预测财务报表 | 历史 5 年 + 预测 5 年的收入/增速/EBIT/利润率/净利/CFO/Capex/D&A/FCFF |
| 增长假设 | 收入增速、EBIT 利润率、Capex/收入、D&A/收入 的历史 vs 预测小图 |
| SOTP | 分部 EV 条形图 + 分部表 |
| 敏感性 | WACC × g 5×5 热力矩阵，悬停看组合 |
| 三情景 | Bull/Base/Bear 柱图 + 假设卡 |
| 关键提示 | gates / warnings |
| 右侧 | AI 研究助手：对话、快捷操作、输入框 |

## 悬停提示

所有图表元素（区间点、FCF 柱、增长点、SOTP 条、敏感性格、情景柱）都带
`data-tip`，鼠标移动时显示深色浮层，包含年份、数值、口径；离开即隐藏。
实现见 `valuation_lab.html` 的 `hover-tip` 与全局 `mousemove`。

## AI 助手与 ChatGPT Plus

- 默认是**规则助手**：解析 WACC/增速/利润率/同业/解释分歧等意图，直接调用后端
  估值引擎重算，再用结构化结果回答；不编数字。
- 推荐接入 **DeepSeek**：在 `valuation/.env` 设置
  `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL=https://api.deepseek.com`、
  `DEEPSEEK_MODEL=deepseek-chat`。页面会显示「DeepSeek 已连接」。
- 也支持 OpenAI 兼容接口：`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`。
- **ChatGPT Plus 订阅本身不提供 API**；需要 API Key，或你本地已有的桥接服务地址。
  没有配置时，规则助手仍可完整回答估值问题。
- 右侧 AI 助手可以结合估值结果回答；公司搜索框负责「代码/简称 → 财务数据 → 估值」。
- 可选的后端检索接口 `/api/valuation/search` 仍保留（公告/行业 + 估值结果 → 模型），
  但页面主入口是公司搜索，不是估值问答。

## 截图

- `lab_600519.png`：600519 首屏
- `lab_full2.png`：600519 整页（含预测表/增长假设/SOTP/敏感性/情景）
- `lab_online.png`：后端运行态
- `lab_600036.png`：银行 DDM / PB-PE Comps 场景
- `screenshot_000333.png` / `screenshot_000858.png`：旧版页面样例（保留）

## 注意

- 离线样例是上一次真实运行快照；点「开始研究/运行估值」后数据会刷新，数值可能小幅变化。
- 首次联网年报取数较慢（下载 PDF），之后走 `.cache/`。
- 银行 600036：自动切换 DDM，Comps 只显示 PB/PE；SOTP 与 DCF 敏感性显示不适用说明。
