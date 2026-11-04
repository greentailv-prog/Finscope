> **FinScope C v3.1 审慎估值修订优先级提示（2026-11-04）**：本文部分旧版 v2/v3 规则已失效，尤其包括“无同业使用板块代理”“默认 Gordon 与退出倍数取中点”“市场隐含 WACC 默认校准”“缺分部构造单一整体业务”“总部费用按收入 2%×8 倍默认扣减”。上述规则不得再作为上线依据。请优先遵循工程根目录的《估值后端v3_1_审计修订与联调手册.md》及当前代码与测试。原文作为历史基线保留，不代表当期执行规则。

# FinScope 2.0 · C 估值实验室 v3 前后端交付包

版本：v3（以用户上传的 C 估值模块 v2 为基础增量开发）

## 一、交付内容

| 文件 | 内容 |
| --- | --- |
| `valuation/frontend/valuation_lab.html` | 新版估值实验室：企业查询、方法选择、参数/可比/分部设定、长期财务图表、情景与敏感性、会话及导出 |
| `valuation/frontend/sample_data.js` | 离线样例；浏览器断开后端时仅作显示，不冒充实时行情 |
| `valuation/frontend/FinScope_估值实验室_v3_首屏.png` | 浏览器实际渲染截图（桌面首屏） |
| `valuation/frontend/FinScope_估值实验室_v3_完整页.png` | 页面完整截图（向下滚动的整页） |
| `valuation/api/server.py` | FastAPI，搜索/取数/会话/重算/下载/Agent/统一对象入口 |
| `valuation/api/assistant.py` | 规则问答 + 可选 OpenAI API，解释与改假设实际调用 C rules / 引擎 |
| `valuation/data/adapters.py` | ABC v2 逐科目带来源对象转换；优先使用上游数据，不另取第二个价格 |
| `valuation/export/institutional.py` | 18 表公式联动的专业估值底稿导出（artifact_tool 环境） |
| `valuation/export/excel.py` | 原有 12 表导出器，普通 Python 环境兼容回退 |
| `valuation/output/600519_估值底稿_v3.xlsx` | 实际生成、校验过的 18 表公式底稿示例 |
| `valuation/tests/test_v3_integration.py` | 离线回归测试，覆盖 canonical → 会话 → DCF → Excel → AI 规则问答 |
| `ABC_对接说明.md` | D/E 负责人可直接照办的接口及统一数据协议 |
| `估值模型与Excel说明.md` | 技术口径、取数边界、表内公式和局限 |
| `UI_与Claude开发说明.md` | 前端图表、布局、分析叙事和悬停说明 |
| `测试和未完成项.md` | 实测与不能声称完成的部分 |

原始 C v2 的规则、Comps、SOTP、DCF、DDM 和来源配置、测试结果保留在 `valuation/` 下。

## 二、在自己的电脑上启动

Windows PowerShell，首先进入本包所在目录（`valuation` 的上一级）：

```powershell
python -m pip install -r valuation/requirements.txt
python -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
```

然后打开：

`http://127.0.0.1:8010/ui/valuation_lab.html`

或者执行根目录的 `启动估值实验室_Windows.bat`（假设已经安装依赖）。

**联网说明**：首次搜索或运行股票可能要访问东方财富、新浪、公告网站或巨潮资讯。没有互联网或对应接口出现反爬时，无法保证实时取数成功；此时页面预加载离线演示结果，绝不标记为新的实时计算。C 端只能作为独立开发/调试模式抓取。正式小组产品应由 D 统一取数、传入 `financials / market_data`。

## 三、对话 AI 接入

默认本地规则助手**实际可用**，可以解释估值分歧，询问选取理由，调整 WACC、收入增速、利润率或永续 g，并触发后台重算。需要 OpenAI 模型时在**服务端环境变量**中配置：

```powershell
$env:OPENAI_API_KEY="你的API密钥"
$env:OPENAI_MODEL="gpt-4o-mini"
python -m uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010
```

不要把密钥写进 HTML 或浏览器。ChatGPT Plus 网页订阅不等于 API 额度或任意第三方应用授权；因此页面不虚构“已连接你的 Plus”。OpenAI 模型调用成功与否取决于实际 API 权限、网络和单独计费。

## 四、Excel 环境说明（请阅读）

18 表专业底稿使用 `artifact_tool`，已在本次运行环境成功导出并验证关键公式；这个包**不附带内部运行时二进制组件**。如果目标电脑没有该库，服务端会自动回退到 C v2 已有的、基于 `openpyxl` 的 12 表底稿导出，确保至少能够导出。如果要在任何普通 Windows 环境都稳定生成 18 表，请将此部分移植为环境内可用的受支持 Excel 库，并重新跑公式一致性测试；不能假称当前 18 表模块在所有 Python 环境中都能直接 pip 安装。

## 五、功能范围与现实约束

1. 基于年报历史财务的五年经营驱动与 FCFF 预测、Comps/DCF/SOTP、行业适配 DDM、情景和敏感性均有后端基础，页面重排并增加详细说明。
2. 公开年报可支持部分三大报表历史科目；由于缺少业务量、单价、客户、营运资本分项和管理层预算，**没有构造伪完整的未来五年资产负债表和现金流量表**。新增预测展示的是收入、EBIT、NOPAT、折旧摊销、资本开支、ΔNWC、FCFF 等可由规则模型支持的指标。
3. 估值结论只作研究和教学用途，数据口径、市场价格日期、方法分歧、低置信度和模型估计比例应显著提示。
4. 本包是 **C 负责人可独立运行的后端 + 估值实验室页面**，不包含 A/B/D/E 全部其他同学的实际服务，因此不能宣称整个 FinScope 小组产品已统一部署上线。

## 六、离线验证

```powershell
python -m valuation.tests.test_v3_integration
```

测试会检查 ABC canonical 输入、跑 DCF、建立会话、导出 Excel、验证 DCF 每股公式、提问时不误修改可比名单；在线公司检索、OpenAI 实际调用和第三方网站图表样式尚不能在离线环境验证。

## 七、最终交互与导出优化

- `POST /api/valuation/session/{sid}/run` 默认先返回估值 JSON、暂不生成工作簿；需要立即导出时显式添加 `?export_excel=true`。
- 右侧助手的明确改参操作先由后端模型计算并更新当前会话，不在每次聊天时耗时生成 18 表；点击 `导出 Excel 底稿` 才调用 `GET /api/valuation/session/{sid}/excel` 用**当前会话最新结果**生成新文件。旧底稿在修改假设后自动失效。
- 对于“解释改变 WACC 会怎样”这种说明性问题，系统不修改用户的假设。对于“从 6% 调整到 7.5%”，采用后一个目标值重算。暂不自动执行“降低 0.5 个百分点”这种相对变化，避免发生数值歧义。
- 界面将“规则演示”“API 已配置”和“AI 模型实际回复”区分；**只有服务端 API 成功返回文字时**才标记后者。ChatGPT Plus 账户无法直接接入网页，仍需独立配置 API Key。
- 浏览器截图增加 `FinScope_估值实验室_v3_图表悬停.png`，展示深蓝高对比度数据标签。
