# FinRadar · B 部分：财务指标计算 + 财务风险诊断

> 中山大学岭南学院《投资学》课程项目 **FinScope / FinRadar** 的 **B 模块交付包**。
> 产品主线：年报进 → 指标 / 风险 / 预测 / 估值出。本模块负责前两段——
> **财务指标计算** 与 **财务风险诊断**，全流程仅用公开披露信息，且**出处可核对**。

## 模块构成

| 目录 | 作用 | 一键运行 |
|---|---|---|
| `financial-diagnosis/` | 指标计算引擎（65 个指标，纯 Python 标准库实算） | `bash run_demo.sh` |
| `risk-radar/` | 风险诊断引擎（53 条规则，含 13 条银行业专属） | `bash run_demo.sh` |
| `report-fetcher/` | 从巨潮资讯网公开接口抓取年报 PDF | `python3 report-fetcher/scripts/fetch_report.py` |
| `cases/icbc-601398/` | 真实案例：工商银行 2023–2025 三期年报 | `cd cases/icbc-601398 && bash run_case.sh` |
| 同业对比看板 | 主看板内置「同业对比」板块（逐指标点图 / 差距条形图 / 杜邦并排，数据来自 A 股篮子 11 家） | `python3 scripts_build_dashboard.py`（自动读 `cases/a-share-basket/peer_view.json`，缺文件自动隐藏该板块） |
| `references/` | 口径与阈值的会计准则 / 监管依据（可复核） | — |

## 核心约定（不可违背）

1. **零第三方依赖**：只用 Python 标准库，指标与风险全部代码实算，禁止大模型口算。
2. **不猜数**：输入缺失 / 分母为 0 → 标 `null` 并进入 `review_queue`，绝不默认安全。
3. **四态判定**：`triggered / passed / not_applicable / not_evaluable`，语义严格区分。
4. **口径铁律**：金额归一到「元」；周转率/回报率分母用平均余额（需三期）；
   口径匹配（ROE 归母、ROA 全口径、ROIC 用归母权益）。
5. **出处可核对**：每个指标的输入都能回溯到年报 source + page；口径/阈值可上溯到准则条文。
6. **三表勾稽自检**：资产负债表平衡、利润表桥、现金净变动，差异超 1% 进 `review_queue`（只查不修）。

## 对接 D 的统一数据对象

本模块输出 `ratios` 与 `risks`（风险卡片），字段名对齐 D 定义的 `Schema.json`，供 D 直接填入统一数据对象。

- **`ratios` 分六类**：`growth`、`profitability`、`solvency`、`efficiency`、`cashflow_quality`，以及行业专属的 `banking`（仅银行业公司有该键）。
- **金额单位一律为元**（输入侧的年报原始单位在计算时已归一到元，`meta.amount_unit="元"`）。
- **比率一律为小数**：`0.2309` 即 23.09%，不要写成 `23.1` 这种以 100 为基数的数值。
- **每个指标三种状态**：`ok`（算出）／`not_evaluable`（缺科目、分母为 0、缺上期）／`not_meaningful`（口径本身不适用，如银行算流动比率）。
- **每个指标带出处**：`name`、`role`（core / diagnostic）、`source_fields`、`source_pages`。

## 快速开始

```bash
# 1) 端到端跑通合成样本（生成 output_ratios.json / output_risks.json / B_demo_dashboard.html）
bash run_demo.sh

# 2) 跑真实工行案例（覆盖度 / 勾稽 / 风险逐项核对）
cd cases/icbc-601398 && bash run_case.sh

# 3) 指标覆盖度体检
python3 scripts_check_coverage.py --all

# 4) 三表勾稽回归测试
python3 scripts_test_checks.py

# 5) 工作台链路自检：按 D 的六步顺序跑 b_input（含 peer_financials）→ 指标 → 同业对比 → 风险卡
python3 scripts_link_check.py --b-input <b_input.json>
```

`b_input.json` 由 D 写，顶层比抽取结果多一个 `peer_financials` 数组。结构、调用顺序与
`peer_*` / `industry_*` 两条阈值通道的区分，见 `B_README.md` 的「工作台接入」一节。

详细设计见各子目录的 `SKILL.md` / `RULES.md`，以及根目录 `B_README.md`。

## 已知限制（诚实标注）

- 行业阈值**只做了部分校准**：银行业 3 项（ROE、净息差、成本收入比，样本 20 家 / 18 家，`peer_samples/banking.json`）；
  板块池按需建（已有 `boards/BK1277.json` 白酒Ⅱ，20 家 8 项），其余行业无池时回退固定阈值并在
  `threshold_source` 标注 `fixed_fallback`，不假装是同业校准。
- 同业对比的应收周转天数变动（E02）需三期应收，A 侧目前只给两期，该规则本轮走固定阈值。
- WACC 由 `compute_wacc.py` 现场算敏感性区间；β 回归 R²<0.05 时拒采信（银行回退同业 β 中位数，非银行要求显式传入）。
- 仅覆盖 A 股；银行 LCR / NSFR 等流动性指标未纳入。
