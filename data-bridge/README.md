# data-bridge — 数据接入桥

把外部数据接成 B 引擎能吃的格式。**只做结构转换与字段改名，不重算、不补数。**

```
外部数据 ──[ 本目录 ]──  B 输入（financial-diagnosis/INPUT_SCHEMA.md）──> compute_ratios ──> detect_risks
```

两个入口，覆盖规范里的两种取数模式：

| 脚本 | 模式 | 输入 | 出处写法 |
|---|---|---|---|
| `scripts/fetch_eastmoney.py` | `online` | 6 位股票代码 | 数据源 + 字段名 + 链接，**无页码** |
| `scripts/from_a_extract.py` | `upload` | A 的抽取结果 JSON | 印刷页码 + PDF 物理页 + 原文片段 |

`scripts/field_map.py` 是唯一的映射表，加数据源只改它。

## 用法

```bash
# 输入代码，直接出一家公司的 B 输入
python3 data-bridge/scripts/fetch_eastmoney.py --code 600519 --out /tmp/input_600519.json

# 批量取同业（用于同业对比与阈值校准）
python3 data-bridge/scripts/fetch_eastmoney.py --codes 600519,000858,000568 --out-dir /tmp/peers

# 接 A 的抽取结果（带页码）
python3 data-bridge/scripts/from_a_extract.py --dir <A目录> --out-dir /tmp/a_inputs
```

取数结果缓存 7 天，落在 `cache/`（不进版本库）。`--refresh` 可强制重抓。

## 三个必须守住的点

**1. 在线模式没有页码，就不要编。** 接口数据写 `source_type="online"`、`source_field`、
`source_url`；只有 PDF 抽取才写 `page` / `pdf_page`。

**2. 收入用「营业收入」不用「营业总收入」。** 东财 `OPERATE_INCOME` 是营业收入，
`TOTAL_OPERATE_INCOME` 含利息收入、已赚保费等。用后者去减 `OPERATE_COST`（营业成本）
会虚增毛利率——茅台 2025 两者差 32 亿元，毛利率差约 1.9 个百分点。

**3. 现金勾稽要声明口径不可比。** 在线源和 A 抽的都是资产负债表「货币资金」，
与现金流量表「现金及现金等价物」不同源（茅台上限差 400 多亿）。
桥接层在 `meta.alignment_flags.cash_bridge = "not_comparable"` 里声明，
引擎据此判「口径不成立」，不会倒着报成公司账不平。

## 已知边界

- 东财 `END_CASH_EQUIVALENTS` 字段量级与货币资金对不上（茅台 2025 报 84.73 亿 vs 约 516 亿），
  **不做映射**。宁可缺，不可错。
- 少数股东权益 / 少数股东损益不在接口里，`minority_*` 类勾稽判 `not_evaluable`。
- 折旧摊销由 `FA_IR_DEPR + IA_AMORTIZE + LPE_AMORTIZE + USERIGHT_ASSET_AMORTIZE` 相加，
  部分公司不全给，缺则该项为空。
- 只覆盖 A 股年报。季报、半年报不支持（与规范 §2.1 一致）。
- 接口是公开页面背后的私有接口，字段可能变。变了改 `field_map.py`，不用动引擎。
