---
name: valuation
description: >
  FinScope 估值后端 v2：对 A 股（及 D 传入的 canonical 数据）做 DCF/FCFF、Comps 相对估值、
  SOTP 分部估值、金融行业 DDM/剩余收益；缺输入时由规则层自动补假设、选同业、选指标、
  定权重，输出融合结论、区间、敏感性、三情景、中文叙述、图表数据与公式联动 Excel 底稿。
  当用户问「这家公司值多少钱」「做个 DCF」「做可比公司估值」「分部估值」「估值建模」
  「高估还是低估」时触发。
---

# FinScope 估值模块 v2

## 交付物

| 文件 | 作用 |
|---|---|
| `README.md` | 架构、快速开始、规则摘要、三家检验结果 |
| `RULES.md` | 金融规则、默认值、可靠性评分、定权、交叉验证 |
| `INPUT_SCHEMA.md` / `OUTPUT_SCHEMA.md` | 输入/输出定义（含 ABC canonical 映射） |
| `docs/API.md` | HTTP 接口与会话流 |
| `docs/CHANGES_v2.md` | 相对 v1 的改动清单 |
| `core/` / `data/` / `export/` / `api/` | 可执行实现 |
| `tests/simulate_three.py` | 三家公司端到端检验 |

## 工作流程

### 第 1 步 · 识别输入与行业门槛

输入可以是：

1. `{"company":{"ticker":"600519","market":"A"}}` —— 自动联网取数；
2. D 的 canonical 对象 —— 使用 `financials` / `market_data` / `peer_financials`；
3. v1 JSON —— 兼容 `peers` / `sotp_segments` / `assumptions`。

数据源用 `data_source` 选择：`canonical`（D 传入）/ `web`（巨潮年报 PDF）/
`ifind` / `choice` / `akshare` / `auto`。D 已传财务与行情时优先 canonical，
C 不另取一套数。详见 `docs/DATA_SOURCES.md`。

行业门槛：

| 行业 | 处理 |
|---|---|
| 制造、消费、科技、化工、机械、医药等 | supported：DCF + Comps + SOTP |
| 银行、保险、证券 | limited：标准 FCFF 不适用，改用 DDM/剩余收益 + PB/PE Comps；status=partial，gate_reason=standard_fcff_unsupported; ddm_used |
| 地产 / REITs | unsupported：只用 Comps（PB）；NAV/FFO 未支持 |
| 行业识别不出来 | limited：DCF + Comps，warnings 标注「仅供参考」 |

### 第 2 步 · 规则补假设

不要求用户先回答。默认规则：

- 首年增速 = 近 3 年 CAGR 50% + 近 5 年 CAGR 30% + 最近同比 20%；
- 利润率/费率 = 近三年中位数；
- 税率夹 15%–30%；
- 永续 g 2.5%，不超过市场 GDP 上限；
- WACC = CAPM，若与市场隐含 WACC 差 >150bp，向市场值校准 60%。

所有假设写入 `assumptions[]`，带 `source_type`（history/management/industry/model）、
`source`、`confidence`（高/中/低）、`overridable`。

### 第 3 步 · 选同业与分部

- 同业：行业池 4–6 家 → 板块代理 → 无样本才降级；逐家写 `selection_reason`。
- 分部：使用者/D 数据 → 东财「主营构成」最新年报 → 整体业务兜底。
- 倍数：按目标盈利性、增速、资本密集度、行业选择；高毛利公司不把 PS/EV-Revenue
  放进结论（只作参考）。

### 第 4 步 · 计算

**DCF**：

```
FCFF = EBIT×(1−t) + D&A − CapEx − ΔNWC
终值 = (Gordon + 退出倍数) / 2；ROIC 再投资法作交叉校验
期中折现 (1+WACC)^(i+0.5)
```

**Comps**：同业中位数 × 目标指标；EV 类扣净负债/少数股东权益；PEG 用
`隐含 PE = PEG × 增速%`；目标与同业差异做 ±30% 内调整并披露理由。

**SOTP**：分部 EV = 指标 × 纯业务同业中位倍数；扣总部费用、净负债、少数股东权益。

**DDM**：金融行业替代绝对估值；DDM 与剩余收益取中位；Ke 做市场校准。

### 第 5 步 · 可靠性 + 定权 + 融合

- 每个方法打 0–100 分，列出扣分项；
- 默认权重按有无 SOTP/是否金融决定，再乘可靠性系数；
- 方法分歧 >50% 时以可靠性更高者为主方法（70%），输出「区间参考」，不强行给单点；
- 最终给 `blended_per_share / upside / verdict / confidence / weights / trace`。

### 第 6 步 · 输出

- `presentation.narrative`：中文结论、方法选择、DCF/Comps/SOTP/DDM、情景、风险；
- `presentation.charts`：FCF 预测、估值区间、两张敏感性矩阵、情景、倍数定位、权重；
- `excel_path`：每次估值同步生成的公式联动 Excel 底稿（18 表；运行时不可用则 12 表），相对包根；
- `gates` / `warnings` / `sources`：必须逐条回应。

### 第 7 步 · 自检

```bash
python -m valuation.tests.simulate_three     # 三家公司端到端
python -m valuation.cli health               # 依赖自检
```

Excel 底稿验收：

1. 真机 Excel 重算后零错误格；
2. DCF/Comps/融合关键值与 JSON 结论一致；
3. 五粮液类口径异常必须被识别并提示。

## 关键规则

- **缺输入不跳过方法**：规则补假设、选同业、选指标，并披露。
- 所有数值由 Python 计算；模型只产出结构化参数与叙述，不在自由文本里另算数字。
- 负净利润跳过 PE/PEG；负 EBITDA 跳过 EV/EBITDA；金融行业跳过 EV 类。
- `WACC ≤ g`、`Ke ≤ g` 必须处理，不能输出 `#DIV/0!`。
- 终值占比、两法偏离、方法分歧、市场隐含折现率是核心交叉验证。
- 交付稿必须声明：仅供研究与教学用途，不构成投资建议。
