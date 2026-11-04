# FinScope 2.0 · C 估值实验室 v3 交付清单

版本：**v3（2026-11-04 最终测试补丁）**  |  产物性质：**本机独立可运行 + ABC 接口适配，尚需小组联调**

## 入口

- Windows：`启动估值实验室_Windows.bat`
- macOS / Linux：`启动估值实验室_mac_linux.sh`
- 网页：`http://127.0.0.1:8010/ui/valuation_lab.html`
- 测试：`python -m valuation.tests.test_v3_integration`（在本目录运行）

## 主要交付文件

| 路径 | 用途 |
| --- | --- |
| `valuation/frontend/valuation_lab.html` | 估值实验室最终交互 UI：搜索、方法、假设、同业、分部、历史与预测、情景、敏感性、会话和导出 |
| `valuation/frontend/sample_data.js` | 离线案例（600519、000333、000858、600036），展示样例而非实时数据 |
| `valuation/frontend/FinScope_估值实验室_v3_首屏.png` | 最终首屏浏览器截图 |
| `valuation/frontend/FinScope_估值实验室_v3_完整页.png` | 最终整页浏览器截图 |
| `valuation/frontend/FinScope_估值实验室_v3_图表悬停.png` | 深蓝高对比度 Tooltip 效果 |
| `valuation/frontend/FinScope_估值实验室_v3_银行DDM.png` | 金融行业估值参数适配 |
| `valuation/api/server.py` | FastAPI 会话、搜索、估值、按需 Excel 下载、API 和上传 |
| `valuation/api/assistant.py` | AI 参数解析、只读问答、规则回答、可选服务端 OpenAI API |
| `valuation/data/adapters.py` | ABC 统一财务对象适配与保留来源信息 |
| `valuation/export/institutional.py` | 可审计 18 表 Excel 导出（artifact_tool 可用时） |
| `valuation/export/excel.py` | 原始可移植的 12 表兼容导出 |
| `valuation/output/600519_估值底稿_v3.xlsx` | 经 DCF 公式对账的 18 表实例 |
| `valuation/output/000333_估值底稿_v3.xlsx` | 美的集团 18 表实例 |
| `valuation/tests/test_v3_integration.py` | ABC / 估值 / Excel / 规则 AI / WACC 改参回归测试 |
| `ABC_对接说明.md` | 给 D / E 同学的统一接口文档 |
| `UI_与Claude开发说明.md` | 给 Claude 的前端开发与交互详细指导 |
| `估值模型与Excel说明.md` | 估值、数据来源与工作簿勾稽 |
| `测试和未完成项.md` | 实测、限制与部署前需要人工核验的问题 |
| `valuation/SKILL_v3.md` | 估值 Agent 详细 Skill |
| `references/04_ABC工作流与接口规范_v1.0.md` | 用户上传的 ABC 工作流规范副本，便于独立交付核对 |

## 关键行为

1. 综合/Comps/DCF/SOTP 支持勾选和行业门槛，银行切到 DDM/剩余收益与 Comps。
2. 研究任务若提供 `window.FINSCOPE_UNIFIED`，C 优先取同一份 canonical 财务、价格与来源；没有时独立模式按配置搜索/取数。
3. 模型 JSON 与图表先完成；只有点击 Excel 导出时才按当次模型结果生成底稿。更改参数自动废弃旧 Excel 下载路径。
4. 右侧规则助手在不配置大模型时可用，明确改假设可触发重算；解释性问题不会静默改参。
5. `OPENAI_API_KEY` 是可选独立 API 凭证；**ChatGPT Plus 无法直接当作第三方 API 访问凭证**。
6. 对于 Excel，`artifact_tool` 可用时生成 18 表专业版；普通 Python 环境自动降级为原 12 表。专业版样例已提供，但并不代表所有 Windows 环境均可重生成。

## 尚未完成的外部依赖

- A/B/D/E 完整工程的实际联合部署；任意 A 股的实时联网取数回归。
- 用户本人 OpenAI API 授权、密钥配置和真实模型响应。
- 用户所给 Workbuddy 页面源码/悬停组件读取；当前 Tooltip 是根据需求自行实现。
- 全行业与所有敏感性/同业倍数的 Excel 逐格重算测试。

详见 `README_交付总览.md` 和 `测试和未完成项.md`。
