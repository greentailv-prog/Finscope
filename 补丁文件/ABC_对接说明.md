# FinScope C v3 与 ABC 工作流统一数据对象对接

## 1. 遵守 2026-11-03《04_ABC工作流与接口规范_v1.0.md》

- **年报口径**：只支持 `meta.period_type="annual"`，利润/现金流表用全年累计，资产负债表用年末。
- **合并口径优先**：只有母公司数据时需要被上游 D 标记为口径不一致并提示；不能把母公司和合并值混起来算。
- **一数一源**：A/D 提供唯一 `financials` 和 `market_data`；C 不重新取一份营业收入、现价、总股本；E 只展示 C 的估值结果，不前端重算财务指标。
- **数据来源**：`source_mode=online` 时没有 PDF 页码，`source_mode=upload` 可提供 page/pdf_page；不能假造 PDF 页码。
- **D 的数据质量闸门为最高优先级**：当 `data_quality.blocked=true`，E 应禁用明确投资方向结论，而不是仅靠 C 的 `partial` 绕开。

## 2. D 调 C 的统一 HTTP 接口

`POST /api/valuation/from-workflow`

请求 body 为 D 组织的 canonical 统一对象：

```json
{
  "schema_version": "2.0",
  "meta": {"source_mode":"online", "period_type":"annual", "currency":"CNY"},
  "company": {"ticker":"600519.SH", "name":"贵州茅台酒股份有限公司", "market":"A", "industry":"食品饮料-白酒"},
  "financials": {
    "revenue": {
      "value":168838102514.79,
      "series":{"2023":147693604700,"2024":170899152276.34,"2025":168838102514.79},
      "period":"2025", "unit":"元", "scope":"合并报表",
      "source_id":"S01", "source_type":"online", "status":"found"
    }
  },
  "market_data": {"price":1480.0, "shares_outstanding":1250081601, "price_date":"2026-11-03"},
  "peer_financials": [],
  "peer_market_data": [],
  "sources": [{"source_id":"S01", "source":"财务在线数据源", "source_type":"online", "source_url":"https://...", "page":null}],
  "method_selection":"auto"
}
```

以上只是**结构例子**，不是对上述年度或行情有效性的实时确认；未获取的报表字段保留 `null` 和 `status=not_found`，不能凭例子补数。

返回：`{"valuation":{...C 估值结果...},"status":"ok|partial|unsupported|failed","excel_path":"valuation/output/<ticker>_<year>_估值底稿.xlsx"}`。

`/from-workflow` 每次调用都会同步生成该标的自己的 Excel（18 表；运行时不可用时回退 12 表），
并在 `valuation.excel_path` 返回相对交付包根目录的路径。D 按包根解析即可下载，
不需要另调导出接口，也不会拿到其它公司的静态样例。

C 通过 `data/adapters.py::canonical_records_to_history()` 转成历史序列，原始逐字段记录同步保留到结果 `financial_records`，用于 Excel 可追溯来源。如果 D 提供完整 `financials`，`fetch_data=false`，C 不重新向公开数据源取一次价格/营收；若 D 尚未返回可比公司财务，则 Comps 需要降级或等待上游补充。D 中由 C 提供同业代码与筛选理由，A/D 统一补同业财务，B 负责同业指标矩阵，C 使用同业估值倍数。

## 3. E 与 C 页面组件

E 若将估值实验室嵌入统一工作台，应保持 D 的 7 页壳与右侧助手容器，只复用 `valuation_lab.html` 中 **中间估值内容、Assumption Studio、四张历史预测趋势图、情景、可比与分部**；不重复渲染第二个侧边栏。

- 独立页面可用 `http://127.0.0.1:8010/ui/valuation_lab.html?company=600519&run=1` 启动；其他六位代码亦可传入。
- **同页集成且已存在完整 unified 对象**时，可在页面脚本运行前注入 `window.FINSCOPE_UNIFIED = unified`，估值会话创建时将 `inputs` 传给 C，自动启用 canonical、跳过 C 独立取数。注意对象只从受信任的 D 服务端注入，不接受 URL 直接拼 JSON，也不在浏览器泄露凭证。
- 后端服务不在同源时，应由 D 的服务器代理 `/api/valuation/*`，避免浏览器跨域共享 API Key/统一财务对象。
- 切换公司后应清空旧会话与旧估值。若旧样例可展示，应始终标为“离线样例”，不得与实时结果混用。

## 4. 会话 API

| 场景 | 方法 | URL | 注释 |
|---|---|---|---|
| 公司名称/简称/代码 | GET | `/api/valuation/companies/search?q=贵州茅台&limit=10` | 联网候选股票，仅 A 股范围，结果依赖数据源可访问性 |
| 独立模式公司财务预览 | GET | `/api/valuation/companies/600519/data` | 只供 C 单独开发；正式页面应使用 D 统一对象 |
| 新任务 | POST | `/api/valuation/session` | `ticker`、`method_selection`、`assumptions`、`inputs` |
| 开始估值 | POST | `/api/valuation/session/{id}/run` | 输出 JSON、生成 Excel |
| 应用假设并重算 | POST | `/api/valuation/session/{id}/recalculate` | `assumptions`、`peer_set`、`segments`、`weights` |
| 估值结果 | GET | `/api/valuation/session/{id}/result` | 保存后的结果 |
| Excel 底稿 | GET | `/api/valuation/session/{id}/excel` | 响应下载文件 |
| 问答 / 规则与 LLM | POST | `/api/valuation/assistant` | `session_id`、`message`、`history` |
| 后端健康状态 | GET | `/api/valuation/health` | 可检查缺模块和 AI 配置 |
| D 无状态调用 | POST | `/api/valuation/run` | `payload`、`export_excel`，独立网关 |

注意 `inputs` 为上游对象时，`market_data` 中价格日期、股本和财务单位需严格一致。

## 5. 编排与规则的界限

- D 负责抓公司财报与行情、汇总来源以及质量检查；C 不得产生新的 `financials` 真实值。
- C 可以估算 **未来假设**（增速、margin、CAPEX/收入、D&A/收入、ΔNWC 等），但必须在 `assumptions[]` 台账注明 `source_type`、`confidence`、`overridable`。
- Comps 样本用同业规模、行业、产品/服务结构与盈利模式评估，不因股票代码接近就认作可比。
- 银行/保险/券商：标准 FCFF 不适用，改用股权成本口径的 DDM/剩余收益 + PB/PE Comps；
  输出 `status="partial"`、`industry_support="limited"`、`gate_reason="standard_fcff_unsupported; ddm_used"`，
  保留 DDM、Comps 与 blended。房地产/REITs 只有在没有 NAV/FFO 口径时才输出 `unsupported`。
- 对于大分歧方法，不能机械平均形成误导性价格，继续沿用 C v2 的可靠性权重与区间参考规则。

## 6. 正式验收清单

1. 同一股票同一年度，E 页面、B 指标、C Excel 的营业收入与归母净利完全一致（含单位）。
2. 没有新行情时显示价格日期或“待更新”；不沿用演示 `1480` 冒充实时。
3. 传入 `financials` 时证实后台没有再调用自己的 `akshare.fetch_company`。
4. 可比样本更换后 Comps 和融合估值实际重算且自动更新来源/解释。
5. 预测历史五年不足时空缺可见，不以线性插值编造。
6. 部分字段缺失时有警告与降级；数据质量 `blocked` 时不显示方向性估值判断。
7. Excel 的关键估值与当前 JSON 误差可解释，公式不出现 `#REF!`/循环引用。

## 7. Excel 延迟导出和 AI 改参补充

- `POST /api/valuation/session/{sid}/run` 默认**同步生成** Excel 并返回 `excel_path`；`?export_excel=false` 只用于测试时显式关闭。
- `POST /api/valuation/session/{sid}/recalculate` 或聊天改参会立即重算并覆盖同名底稿，不会改变 A 的财务输入；`GET /api/valuation/session/{sid}/excel` 始终提供会话最新结果对应的文件。
- 底稿按标的和年度命名（如 `valuation/output/600519_2025_估值底稿.xlsx`），不是固定样例；换公司/换年份会生成新文件。
- `/api/valuation/assistant` 的 `llm_connected` 表示 API Key 已配置而非已真实调用成功；新增 `llm_used` 表示本次 LLM 的文字响应是否成功，前端状态提示以 `llm_used` 为准。
- 前端保留最近 12 条实际问答，发送时带最近 8 条 `history`；切换标的清除上下文，防止混用不同公司的结论。
