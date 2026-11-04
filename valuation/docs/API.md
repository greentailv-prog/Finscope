# HTTP 接口

启动：

```bash
# 在 valuation 的上一级目录
python -m valuation.api.server
# 或
uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
```

- 前端估值实验室：`http://127.0.0.1:8010/ui/valuation_lab.html`
- Swagger：`http://127.0.0.1:8010/docs`
- 所有响应均为 UTF-8 JSON；Excel 下载为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

## 1. 自检

`GET /api/valuation/health`

```json
{"ok": true, "version": "2.0.0",
 "modules": {"akshare": "1.20.24", "pandas": "3.1.0", "openpyxl": "3.1.5", "fastapi": "..."},
 "themes": 35}
```

## 2. 交互式问题清单

`POST /api/valuation/questions`

```json
{"ticker": "600519", "market": "A"}
```

返回：

```json
{
  "company": {"ticker": "600519", "industry": "白酒Ⅱ"},
  "financials_available": true,
  "industry_support": "supported",
  "questions": [
    {"key": "assumptions.revenue_growth_y1", "question": "首年收入增速用多少？",
     "default": null, "default_rule": "近 3/5 年 CAGR 与最近一年同比加权",
     "required": false, "why": "..."},
    {"key": "peers", "question": "可比公司用系统推荐，还是你指定名单？", ...}
  ],
  "defaults": {"method_selection": "auto", "forecast_years": 5, ...}
}
```

> 前端可以用这个端点驱动「对话窗口」：显示问题、默认值、为什么问；
> 用户不回答也能继续运行，规则层会给默认值。

## 2.4 公司搜索与财务数据读取（估值入口）

`GET /api/valuation/companies/search?q=茅台&limit=10`

- `q` 支持 6 位代码或公司简称；
- 返回 `[{code, name, market}]`，用于搜索框下拉。

`GET /api/valuation/companies/{ticker}/data`

- 读取该公司全部历史财务、行情、分部与来源；
- 返回 `company / financials / history / segments / sources / market_data`；
- 前端选择公司后先调这个接口，再运行估值。

## 2.5 联网年报证据

`POST /api/valuation/evidence/search`

```json
{"ticker": "600519", "name": "贵州茅台", "years": [2022,2023,2024,2025], "max_reports": 2}
```

返回：`financials / segments / sources / reports / warnings`。可用于前端「联网取数」按钮，
也可以把结果复核后作为 `web_evidence` 传回会话。

`GET /api/valuation/sources/probe`：探测 iFinD / Choice 是否可用。

## 2.6 年报 PDF 上传

`POST /api/valuation/upload`（multipart/form-data）

```
file=@600519_2025.pdf
report_year=2025
```

返回：`financials / segments / sources / pdf_path`。前端把返回的
`financials/segments/sources` 放进 `web_evidence`，再运行估值。

## 2.7 AI 研究助手

`GET /api/valuation/assistant/config`

```json
{"connected": false, "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
 "provider": "OpenAI-compatible", "note": "ChatGPT Plus 订阅不提供 API…"}
```

`POST /api/valuation/assistant`

```json
{"session_id": "a1b2c3d4", "message": "把 WACC 调到 7.5%，并说明影响", "history": []}
```

返回：

```json
{"answer": "核心观点…", "result": {...更新后的 valuation...},
 "intent": {"action": "answer", "changes": {"wacc_mode": "manual", "wacc_override": 0.075}},
 "changed": true, "llm_connected": false}
```

- 优先 `DEEPSEEK_API_KEY`（`DEEPSEEK_BASE_URL=https://api.deepseek.com`，
  `DEEPSEEK_MODEL=deepseek-chat`）；
- 其次 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 的 OpenAI 兼容接口；
- 没有时走规则助手：解析 WACC/增速/利润率/同业/解释分歧，直接调用估值引擎重算；
- `answer` 只引用 `result` 中的数字，不让模型编数。

`POST /api/valuation/search`

```json
{"session_id": "a1b2c3d4", "query": "最近公告和行业估值情况", "history": []}
```

返回 `answer / search_results[] / search_engine / llm_connected / provider`。
检索优先通用搜索；失败时回退巨潮资讯最新公告。答案会把检索片段和当前估值结果一起交给
DeepSeek；未配置模型时用规则助手 + 公告摘要回答。

## 3. 创建会话

`POST /api/valuation/session`

```json
{"ticker": "600519", "market": "A", "method_selection": "auto", "data_source": "auto"}
```

`data_source` 可取 `auto / ifind / choice / web / akshare / canonical`。

返回：

```json
{"session_id": "a1b2c3d4e5f6", "state": {...}, "questions": {...}}
```

会话保存在 `output/sessions/<id>.json`，可重启后继续。

## 4. 补充输入

`PATCH /api/valuation/session/{id}/inputs`

```json
{
  "method_selection": "blended",
  "assumptions": {
    "forecast_years": 5,
    "revenue_growth_y1": 0.08,
    "ebit_margin": 0.65,
    "terminal_growth": 0.025,
    "wacc_mode": "manual",
    "wacc_override": 0.08
  },
  "peer_set": ["000858", "000568", "600809"],
  "segments": [...],
  "web_evidence": {"financials": {...}, "segments": [...], "sources": [...]},
  "weights": {"dcf": 0.5, "comps": 0.3, "sotp": 0.2}
}
```

- `weights` 会自动设置 `weight_mode="manual"`。
- `peer_set` 只给代码；C 取财务并算倍数。
- `peers` 给完整倍数时，C 直接使用。

## 5. 运行

`POST /api/valuation/session/{id}/run?export_excel=true`

返回完整的 `valuation` JSON（见 `OUTPUT_SCHEMA.md`），并生成
`output/sessions/<id>_估值底稿.xlsx`。

## 6. 改假设重算

`POST /api/valuation/session/{id}/recalculate`

请求体同 `PATCH inputs`。走本地缓存（财报/行情 12h、同业 12h），通常秒级返回；
会重新生成同路径 Excel。

```json
{"assumptions": {"wacc_mode": "manual", "wacc_override": 0.08, "ebit_margin": 0.60}}
```

## 7. 取结果 / 下载

- `GET /api/valuation/session/{id}/result`
- `GET /api/valuation/session/{id}/excel`

## 8. 无状态运行（给 D 的总集成）

`POST /api/valuation/run`

```json
{"payload": {"company": {"ticker": "600519", "market": "A"},
             "method_selection": "auto"},
 "export_excel": true}
```

直接返回 `valuation` JSON；D 把 `excel_path` 转成自己的 `excel_url`。

## 9. 辅助查询

- `GET /api/valuation/industries`：行业池与行业门槛。
- `GET /api/valuation/companies/{ticker}/segments`：主营构成分部。
- `GET /api/valuation/companies/{ticker}/peers`：自动选出的同业（含理由）。

## 10. 前端接入建议

估值工作台建议三步：

1. **方法选择**：`auto / dcf / comps / sotp / blended`；
2. **对话补输入**：用 `questions` 渲染问题，用户可跳过；提交到 `PATCH inputs`；
3. **运行与展示**：`run` 后用 `presentation.narrative` 渲染中文结论，
   用 `presentation.charts` 渲染 FCF 预测、估值区间、敏感性热力矩阵、情景柱状图、
   同业倍数定位；`excel` 端点做「导出估值底稿」按钮。

图表数据已按前端友好格式给出（金额亿元、比率小数、每股元）。
