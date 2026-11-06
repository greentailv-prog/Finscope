# 终期修改回执（B 模块）· 2026-11-05

对应 `调整意见/06_B必须修改项.md`。每条给出：改了什么、证据文件、复现命令。
目录里两份文档不在本目录，路径见各条。

---

## B1　动态阈值进了主输出

**改了什么**

1. `threshold_source` 原来只有 `peer_*` 一套，把离线行业池和当次同业混在一起。
   与 D 对齐后拆成两条通道：当次同业（`--comparison`，用 D 传的 `peer_financials` 现场算）写
   `peer_p25` / `peer_p75` / `peer_median`；离线行业池（年报季后刷新，与本次请求无关）写
   `industry_p10` / `industry_p25` / `industry_median` / `industry_p75` / `industry_p90`。D 两种都接收。
2. 篮子新增逐公司风险输出：`cases/a-share-basket/run_basket.sh` 第 4 步对 11 家公司分别跑
   `detect_risks --comparison comparison/<code>.json`，产物在 `cases/a-share-basket/risk/<code>.json`。
   此前只有 `risk_matrix.json` 带同业阈值，而 D 不读那份。
3. `threshold_value` 只放数值。P06 原来把变量名 `industry_gross_margin_benchmark` 抄进数值字段，现输出 `null`。
4. 契约自检白名单按两条通道分开校验：`peer_*` 必须 `peer_sample_n >= 3`，
   `industry_*` 必须 `>= 5`，否则 FAIL。`cost_of_equity_sensitivity` 已并入 `wacc_sensitivity`，不再单列。

**证据**

`risk_peer_000858.json`（五粮液，40 条规则）

| 规则 | 阈值来源 | 阈值 | 样本 | 结论 |
|---|---|---|---|---|
| E01 应收增速快于收入 | `peer_p75` | 3.66% | 9 | triggered |
| E04 存货增速快于成本 | `peer_p75` | 10.76% | 9 | triggered |
| P06 毛利率低于同业 | `peer_p25` | 23.25% | 10 | passed |
| S01 资产负债率偏高 | `peer_p75` | 61.89% | 10 | passed |

`risk_peer_icbc_601398.json`（工行，离线行业池）：B06 净息差 `industry_median` 1.49%（n=20）triggered；
B07 成本收入比 `industry_p75` 31.89%（n=18）passed。这两条用的是本地银行样本池，不是当次同业，
所以走 `industry_*`；篮子里的 P06/S01/E01/E04 用的是当次 11 家同业，走 `peer_*`。

全篮 11 家合计 `peer_p75` 31 条、`peer_p25` 11 条，样本量 9–10 家。

**B1 备注：两处没按原意见做**

- E02（应收周转天数变动）本轮仍是固定阈值。11 家输入只有 2024/2025 两期应收，
  周转天数用平均余额，变动值需要 2023 年应收。A5 补三年覆盖后可自动恢复，B 侧不换口径凑数。
  同业阈值算不出来时卡片会写“同业阈值不可算：该指标在同业内均缺上期数据”，不谎称样本不足。
- B06 净息差判定口径是“低于同业中位数”，规范 §6.3 的枚举没有中位数一项。
  现输出 `industry_median`（离线银行池）或 `peer_median`（当次同业），D 已确认两种都接收，
  不必改规则口径，工行结论不动。

**复现**

```bash
cd cases/a-share-basket && bash run_basket.sh
python3 -c "import json;d=json.load(open('risk/000858.json'));print([(r['risk_id'],r['threshold_source'],r['peer_sample_n']) for r in d['risks'] if r['threshold_source'].startswith('peer_')])"
```

---

## B2　缺输入与口径不适用分成两种状态

**改了什么**：`compute_ratios.py` 的 `put()` 原来只要算出 `None` 就写 `not_meaningful`。
现按原因分流——缺科目、分母为 0、缺上期 → `not_evaluable`；口径本身不适用（银行算流动比率等）
仍走 `not_applicable → not_meaningful` 的映射。

**证据**

| 文件 | `ok` | `not_evaluable` | `not_meaningful` | review_queue |
|---|---|---|---|---|
| `ratios_000333.json`（原 12 条 not_meaningful） | 53 | 12 | 0 | 12 |
| `ratios_600519.json`（原 14 条） | 51 | 14 | 0 | 14 |
| 工行 `output_ratios.json`（对照组） | 45 | 0 | 43 | 0 |

银行 43 条不适用项一条没少，语义与原来一致；缺数据的现在都进了 `not_evaluable`。
`status` 的三种含义写进了 `financial-diagnosis/OUTPUT_SCHEMA.md`。

---

## B3　没有同业不再报错退出

**改了什么**：`build_comparison.py` 的 `--peers` 改为可选。不传或目录为空时输出
`status="not_available"`、`peer_set=[]`、8 个指标的数值全为 `null`、5 条阈值全为 `null`，退出码 0。
`detect_risks --comparison` 读到该状态时五条规则全部回退固定阈值，不中断。

**证据**

- `comparison_not_available.json`：`status=not_available`，`sample_n=0`。
- `risk_with_not_available.json`：40 条规则全部完成，`threshold_source` 为 `fixed` 38 条、`fixed_fallback` 2 条，
  `comparison_status=not_available`，退出码 0。

**复现**

```bash
cd deliverables/终期修改_2026-11-05
python3 ../../risk-radar/scripts/build_comparison.py --target ratios_000333.json --out /tmp/cmp.json; echo $?   # 0
python3 ../../risk-radar/scripts/detect_risks.py --ratios ratios_000333.json \
  --rules ../../risk-radar/risk_rules.json --comparison /tmp/cmp.json -o /tmp/risk.json; echo $?              # 0
```

---

## B4　文档按实际输出重写

**改了什么**

- `README.md`：六类指标（前五类通用 + `banking`）、金额单位元、比率为小数、
  `status` 三态、每个指标带 `name/role/source_fields/source_pages`；已知限制一节改成实际完成度。
- `financial-diagnosis/OUTPUT_SCHEMA.md`：`ratios` 六类结构、条目字段补全、`role` 分法、
  `status` 三态对照表（含触发条件与页面文案）。
- 同步修正 `B_README.md`、`financial-diagnosis/README.md`、`financial-diagnosis/SKILL.md`、
  `risk-radar/INPUT_SCHEMA.md` 里的“五类”表述。
- `risk-radar/OUTPUT_SCHEMA.md` 新增「阈值三件套」一节，列出 `threshold_source` 全部合法取值与样本门槛。

`README.md` 与 `OUTPUT_SCHEMA.md` 已搜不到“百万元”“百分数”。
（`financial-diagnosis/INPUT_SCHEMA.md` 仍保留「百万元 = 1e6」一行，那是**输入侧**单位换算表，
工行案例的年报原文就是百万元，删掉会让人不知道能不能直接喂百万元数据。）

---

## B5　补了 `rd_capitalized`

**改了什么**：`data-bridge/scripts/field_map.py` 的 `B_FIELDS` 增加 `rd_capitalized`，
`A_TO_B` 登记同名映射，金额类字段集合随之包含该键。

**证据**：构造一份带研发资本化金额的输入（资本化金额 = 研发费用 × 0.5），
A04 从 `not_evaluable` 变为 `triggered`，说明字段能从输入进到派生量再到规则，没有被白名单吞掉。

**复现**

```bash
python3 financial-diagnosis/scripts/compute_ratios.py -i /tmp/b5/input_with_rd.json -o /tmp/b5/ratios.json
python3 risk-radar/scripts/detect_risks.py --ratios /tmp/b5/ratios.json \
  --rules risk-radar/risk_rules.json -o /tmp/b5/risks.json
# A04：研发投入资本化率为 33.3%，高于 30%
```

---

## 工作台链路自检（2026-11-06 新增）

D 确认用子进程调、不起服务、`peer_financials` 放在 `b_input.json` 顶层。按他的六步顺序做了一遍
端到端联调，并固化成脚本，联调时一条命令就能判断链路有没有断：

```bash
python3 scripts_link_check.py --b-input /tmp/dlink/b_input.json
```

实测（茅台为目标，4 家同业：五粮液、伊利、美的、格力）：

| 环节 | 结果 |
|---|---|
| 第 2 步 目标指标 | 退出 0，65 个指标，顶层 `peer_financials` 未被误读 |
| 第 3 步 拆分 peer_inputs | 4 份，只写 `company` + `financials`（无 `meta.periods`） |
| 第 4 步 同业指标 | 4 家全退出 0，期间从 `financials` 键自动推断 |
| 第 5 步 comparison | 退出 0，`status=ok`，样本 4，`peer_set` 带 `ticker_full` |
| 第 6 步 风险卡 | 退出 0，40 张卡，当次同业阈值 4 条（P06/S01/E01/E04） |

同业为空数组时：`status=not_available`，40 张卡全走固定阈值（2 条 `fixed_fallback`），退出码 0。

`peer_set` 每项现在同时给 `ticker`（6 位）与 `ticker_full`（`000858.SZ`），D 直接拿去和 C 的
`valuation.comps.peer_companies` 对齐，不用自己拼后缀。

## 交付前自检

```bash
python3 scripts_test_checks.py                     # 32 通过 / 0 失败
python3 scripts_check_contract.py --ratios financial-diagnosis/demo/output_ratios.json \
  --risks risk-radar/demo/output_risks.json        # 退出码 0
python3 scripts_check_contract.py --ratios cases/icbc-601398/output_ratios.json \
  --risks cases/icbc-601398/output_risks.json      # 退出码 0
python3 scripts_check_contract.py --ratios cases/a-share-basket/ratios/000858.json \
  --risks cases/a-share-basket/risk/000858.json    # 退出码 0
python3 scripts_link_check.py --b-input <b_input.json>   # 工作台链路，退出码 0
```

## 与 D 已对齐（2026-11-06）

1. `threshold_source`：`peer_median` 与 `industry_*` 全部接收，D 不校验不改写。
2. `peer_financials`：放 `b_input.json` 顶层，数组，一家一条（`company` + `financials`）；
   为空数组时 B 回退固定阈值，不报错。`comparison` 由 D 合并到统一对象顶层。
3. 调用方式：B 不起服务，D 用子进程按六步顺序调用；代码换 JSON（`to_b_input.py`）由 D 负责。
4. `from_b.py` 的 6 个字段透传已由 D 补齐。

## 顺手修的一个环境问题

`run_demo.sh`、`run_case.sh`、`run_basket.sh` 的换行符原是 CRLF，
`set -euo pipefail` 会被读成 `pipefail\r` 直接报 invalid option。已统一为 LF。
