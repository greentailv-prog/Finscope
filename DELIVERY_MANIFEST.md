# FinScope 2.0 · C 估值实验室 v3 交付清单

版本：**v3.3（2026-11-05 D 终期 C1–C4 修订）**  |  产物性质：**本机独立可运行 + ABC 接口适配，尚需小组联调**

## 入口

- Windows：`启动估值实验室_Windows.bat`
- macOS / Linux：`启动估值实验室_mac_linux.sh`
- 网页：`http://127.0.0.1:8010/ui/valuation_lab.html`
- 测试：`python -m valuation.tests.test_v3_integration`（在本目录运行）

## 主要交付文件

| 路径 | 用途 |
| --- | --- |
| `valuation/frontend/valuation_lab.html` | 估值实验室最终交互 UI：搜索、方法、假设、同业、分部、历史与预测、情景、敏感性、会话和导出 |
| `valuation/frontend/sample_data.js` | 由当前代码动态生成的四家离线样例（600519、000333、000858、600036），展示样例而非实时数据 |
| `valuation/frontend/FinScope_估值实验室_v3_*.png` | 浏览器截图（首屏、完整页、悬停、银行 DDM） |
| `valuation/api/server.py` | FastAPI 会话、搜索、估值、**同步 Excel 导出**、API 和上传 |
| `valuation/api/assistant.py` | AI 参数解析、只读问答、规则回答、可选服务端 OpenAI API |
| `valuation/data/adapters.py` | ABC 统一财务对象适配与保留来源信息 |
| `valuation/export/institutional.py` | 可审计 18 表 Excel 导出（artifact_tool / artifact_tool_v2） |
| `valuation/export/artifact_runtime.py` | 运行时探测（含 `FINSCOPE_ARTIFACT_TOOL_PATH`） |
| `valuation/export/excel.py` | 原始可移植的 12 表兼容导出（每表带来源与生成时间） |
| `valuation/output/600519_2025_result.json` | 600519 结果 JSON：dcf / comps / scenarios / sensitivity / assumptions 均非空 |
| `valuation/output/600519_2025_估值底稿.xlsx` | 与上述 JSON 同源的 18 表底稿，原生 Excel 重算 EXCEL_OK |
| `valuation/output/000333_2025_result.json` + `000333_2025_估值底稿.xlsx` | 美的集团动态样例 |
| `valuation/output/000858_2024_result.json` + `000858_2024_估值底稿.xlsx` | 五粮液动态样例（最新财报年度 2024） |
| `valuation/output/600036_2025_result.json` + `600036_2025_估值底稿.xlsx` | 招商银行：partial / limited / DDM+Comps |
| `valuation/output/*.native_check.json` | 每份底稿的 Microsoft Excel COM 原生校验报告 |
| `valuation/output/SYNTHETIC_ONLY_*` | 合成三表案例的结果、5 表底稿、审计与原生校验 |
| `valuation/output/v3_3_回归测试日志.txt` | 40 项单元测试 + 集成测试的完整输出 |
| `valuation/docs/CHANGES_v3_3.md` | C1–C4、P1 的修订说明 |
| `valuation/tests/test_v3_integration.py` | ABC / 估值 / Excel / 规则 AI / WACC 改参回归测试 |
| `valuation/tests/test_delivery_rules.py` | D 的 C1–C4 回归：银行语义、无行情、敏感性与 Excel 路径 |
| `valuation/tests/sample_inputs.py` | 从年报/公开财报快照构造 canonical 输入的测试工具 |
| `valuation/scripts/build_sample_pack.py` | 重新生成四家样例 JSON、18 表底稿和前端样例 |
| `ABC_对接说明.md` | 给 D / E 同学的统一接口文档 |
| `UI_与Claude开发说明.md` | 给 Claude 的前端开发与交互详细指导 |
| `估值模型与Excel说明.md` | 估值、数据来源与工作簿勾稽 |
| `测试和未完成项.md` | 实测、限制与部署前需要人工核验的问题 |
| `valuation/SKILL_v3.md` | 估值 Agent 详细 Skill |
| `references/04_ABC工作流与接口规范_v1.0.md` | ABC 工作流规范副本（含 2026-11-05 银行语义修订） |

## 关键行为

1. 综合/Comps/DCF/SOTP 支持勾选和行业门槛；银行/保险/证券输出 `status="partial"`、`industry_support="limited"`、`gate_reason="standard_fcff_unsupported; ddm_used"`，使用 DDM/剩余收益 + PB/PE Comps。
2. 研究任务若提供 `window.FINSCOPE_UNIFIED`，C 优先取同一份 canonical 财务、价格与来源；没有时独立模式按配置搜索/取数。
3. **每次估值都同步生成 Excel**：`/from-workflow`、`/run`、会话运行、改参重算都会返回 `excel_path`，按 `<ticker>_<year>_估值底稿.xlsx` 覆盖写入 `valuation/output/`，不返回静态样例。
4. 右侧规则助手在不配置大模型时可用，明确改假设可触发重算并重生成底稿；解释性问题不会静默改参。
5. `OPENAI_API_KEY` 是可选独立 API 凭证；**ChatGPT Plus 无法直接当作第三方 API 访问凭证**。
6. Excel 优先用 `artifact_tool`/`artifact_tool_v2` 生成 18 表；运行时不可用时自动降级为 12 表兼容底稿（四类表仍齐全）。已附四家公司 18 表底稿和 Excel COM 原生校验报告。
7. 无行情时 `dcf.per_share`、`blended.blended_per_share`、`scenarios`/`sensitivity` 的每股值为 null，`equity_value` 保留。

## 尚未完成的外部依赖

- A/B/D/E 完整工程的实际联合部署；任意 A 股的实时联网取数回归。
- 用户本人 OpenAI API 授权、密钥配置和真实模型响应。
- 用户所给 Workbuddy 页面源码/悬停组件读取；当前 Tooltip 是根据需求自行实现。
- 全行业与所有敏感性/同业倍数的 Excel 逐格重算测试。

详见 `README_交付总览.md` 和 `测试和未完成项.md`。
