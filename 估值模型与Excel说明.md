# C v3 估值引擎及 Excel 底稿设计说明

## 1. 设计依据

本次检查了用户提交的 Sunflower Financial Model（58 个工作表，含 DCF、FCF Walkdown、IS、BS、CFS、收入与成本费用驱动表），以及 `comps-valuation-model.skill`、`dcf-valuation-model_v1.2.skill` 和 `finance-skills-main` 的相关估值方法。所参考的是其**可审核的模型逻辑和假设/结果分层**，不是将非公开创业公司模型值挪到 A 股上市公司，也没有复制无法从公开年报取得的运营明细。

## 2. 统一财务数据 → 模型输入

1. 历史利润表：revenue、operating_cost、operating_profit、income_tax_expense、net_income、net_income_parent、费用科目。
2. 历史资产负债表：cash_and_equivalents、accounts_receivable、inventory、total_assets、current_assets、current_liabilities、total_equity、有息债务分项。
3. 历史现金流量表：cfo、capex、depreciation_amortization 等。缺项留空或写模型估计，不将零当作缺失值。
4. 市值与 WACC/Comps：用户选定评价日、当日市场价格、股数、同业行情、利率等来自 D（独立调试模式来自 C 内置数据源）。
5. 历史长度最多 5 年展示，有多少原始已取得数据就展示多少。不补造第四或第五年。

## 3. 五年预测的公式依赖

- 首年收入：`Revenue_t = Revenue_(t-1) × (1+g_t)`，增长路径来自用户手动值或 `core/assumptions.py` 规则。
- `EBIT_t = Revenue_t × EBIT_Margin_t`。当前模型 margin 可以固定/按后端规则变化。
- `Cash_Tax_t = EBIT_t × Tax_Rate_t`。
- `NOPAT_t = EBIT_t − Cash_Tax_t`。
- `D&A_t = Revenue_t × D&A_to_Revenue_t`。
- `CAPEX_t = Revenue_t × CAPEX_to_Revenue_t`。
- `ΔNWC_t = Revenue_t × DeltaNWC_to_Revenue_t`。
- `FCFF_t = NOPAT_t + D&A_t − CAPEX_t − ΔNWC_t`。
- `PV(FCFF_t) = FCFF_t/(1+WACC)^(t−0.5)`，采用本 C 后端期中折现口径。
- `EV = PV(显式期 FCFF) + PV(Terminal Value)`；`Equity Value = EV + Cash − Debt − Minority Interest − Preferred Stock`，`Price = Equity Value / Shares`。
- Gordon 终值：`FCFF_last×(1+g)/(WACC−g)`；也保留 Exit Multiple 和 ROIC 终值的后端择取规则。

**重要边界**：当前 C 模型没有分别预测未来资产负债表全部科目、损益明细与融资现金流。历史三大报表已尽量进入底稿，但预测页只展示现有可支持的经营/自由现金流驱动，不宣称未来三表已经平衡。

## 4. 可比公司估值

Comps 用企业经营模式、所属赛道、增长、规模、利润率和上市市场形成候选同业，前端保留选择理由和可比性等级/得分。当有原始同业数据时，企业价值及 PE/PS/PB/EV/EBITDA 等倍数在 Excel 里由指标引用算出，并通过异常值筛选、行业中位数、目标折溢价和市场/利润口径计算隐含价值；结果与后端方法选择存在差异时，需要审查剔除规则与调整倍数，不能改表格里的目标值来强行对齐。

## 5. 分部与行业适配

SOTP 分部表引用分部收入、分部盈利及可比倍数，汇总分部 EV 后扣总部成本、净债务及折价。若只有“主营收入构成”而无分部 EBIT，则分配盈利是估算，要标低置信度。金融行业保留 DDM/剩余收益模型，区分 Ke 与工业企业 WACC。主业/数据不适合当前方法时应降级。

## 6. 专业 Excel 表单目录

| 表名 | 作用 |
|---|---|
| 底稿说明 | 标的、来源、单位、编辑指南、置信度及适用范围 |
| 参数假设 | WACC、g、税率、EBIT margin、现金/债务、增速轨迹等单一输入来源 |
| 历史利润表 | 年报经营、利润科目以及来源/状态 |
| 历史资产负债表 | 现金、债务、资产和营运资本等历史数据 |
| 历史现金流量表 | CFO、CAPEX、D&A 等历史现金流 |
| 历史指标 | 增速、margin、资本开支率等可视化历史基准 |
| 预测经营与FCFF | 收入、EBIT、税、NOPAT、D&A、CAPEX、ΔNWC、FCFF 的五年公式 |
| WACC测算 | CAPM、Ke、债务成本、市场隐含 WACC 对照 |
| DCF估值 | 折现现值、三种终值、EV→股权桥、每股价值、后端对账差异 |
| 可比公司明细 | 同业估值倍数和选择理由，保留来源 |
| 相对估值 | 方法倍数分布与对应隐含股权价值 |
| SOTP分部估值 | 分部业务估值与汇总桥 |
| 融合估值 | 方法结果、权重与差异 |
| 敏感性-WACC与g | 每格以预测 FCFF 与 WACC/g 公式联动 |
| 敏感性-增长与利润率 | 当前后端重算值作为结果快照，须重跑后端刷新 |
| 假设台账 | 每条假设的来源、可靠性、允许覆盖 |
| 数据来源 | 官方/非官方原始出处、年度、用途 |
| 校验与风险 | 规则门槛、方法分歧、敏感性和相关风险 |

颜色：蓝字为外部原始输入，绿字为跨表引用，黑字为公式，黄底蓝字为可修改关键假设。金额单位为亿元，股数单位亿股，每股价格单位元。

## 7. 已完成的数值勾稽

2025 年贵州茅台历史测试样例 `tests/reports_web/600519_result.json`：

- DCF 后端：约 `1,739.387482` 元/股。
- 18 表 Excel `DCF估值!B17`：约 `1,739.387482` 元/股。
- `DCF估值!B18` 差异：约 `−4.5×10⁻¹³` 元/股，属于浮点误差。

该结果证明**该测试样例的 DCF 路径**与 Excel 公式对齐，不表示其他公司、联网数据或所有估值口径均完成逐格核验。

## 8. 跨电脑安装说明

18 表专业版当前依赖 `artifact_tool` 运行时，本包包含其 Python 源代码和一个已生成的实际 XLSX 示例，但**不提供受限/内部二进制组件**。普通 Windows/Python 环境如未预装 `artifact_tool`，自动回退原 C v2 的 12 表公开库版本。要在普通 Python 环境保证 18 表专业底稿完整导出，需要将 `export/institutional.py` 适配到受支持的公开 Excel 库并针对每个方法执行对账测试。
