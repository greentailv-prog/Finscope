# FinScope 估值模块 `valuation/`

三法互证的股权估值：**DCF（收益法）+ 相对估值（可比公司法）+ SOTP（分部估值）**，
融合成一个隐含股价，输出 Excel 底稿与统一 JSON。

覆盖 **A 股与美股**。

## 快速开始

```bash
cd valuation

# 1. 看看数据层能不能用
py cli.py health

# 2. 跑一家 A 股（自动取数 → 估值 → 出 Excel）
py cli.py value 600519 --peers demo/peers_baijiu.json

# 3. 跑一家美股（需要 yfinance）
py cli.py value AAPL --market US

# 4. 用现成的输入 JSON 跑（不取数，适合演示与测试）
py cli.py run demo/input_ashare_600519.json
```

产出在 `valuation/output/`：

```
<标的>_valuation.json   统一结果 JSON（D 的总集成读这个）
<标的>_valuation.xlsx   Excel 底稿（公式联动，蓝字可改）
```

## 依赖

| 用途 | 依赖 | 说明 |
|---|---|---|
| 生成 Excel | `openpyxl` | 主程序唯一必需依赖 |
| A 股取数 | `akshare` + `pandas` | 可跑在另一个解释器里，见下 |
| 美股取数 | `yfinance` | 装法：`py -m pip install yfinance` |
| iFinD 官方源 | `iFinDPy` | 可选，见「官方数据接口」 |
| Choice 官方源 | `EmQuantAPI` | 可选 |

**主程序与取数解释器分离**：主程序只需要 `openpyxl`；取数交给一个装了
`akshare`/`yfinance` 的解释器，通过 subprocess + JSON 交换数据。
`py cli.py health` 会告诉你当前用的是哪个解释器。

如果机器上有多个 Python，可以用环境变量指定：

```bash
set FINSCOPE_DATA_PYTHON=D:\path\to\python.exe
```

## 官方数据接口（iFinD / Choice）

免费源能拿到基础财务，但**行业分类、分业务收入、同业倍数**这些要靠官方接口。

### iFinD

1. 解压 `THSDataInterface_Windows_*.zip`
2. 运行 `bin/Tool/SuperCommand.exe`，用帐号登录（这一步注册本机）
3. 把 `bin/x64/iFinDPy.py` 复制到 Python 的 `site-packages`
4. 在 `valuation/.env` 写入：

```
IFIND_USER=你的账号
IFIND_PASSWORD=你的密码
```

5. 验证：`py tools/probe_ifind.py 600519`

> **指标 ID 需要实测**。iFinD 用形如 `ths_pe_stock` 的指标 ID 取数，
> 完整手册要从量化官网下载。`datasource/indicators.json` 里列了候选值，
> 跑 `probe_ifind.py` 会告诉你哪些有效，把结果填回去并把 `verified` 置为 `true`。
> **在实测通过之前，适配器不会启用 iFinD**——不会用没验证过的字段糊弄。

### Choice

1. 解压 `EMQuantAPI_Python.zip`，运行 `EmQuantAPISetup.exe` 安装
2. 把 `python3/EmQuantAPI.py` 复制到 `site-packages`
3. 在 `.env` 写入 `CHOICE_USER` / `CHOICE_PASSWORD`
4. 验证：`py tools/probe_choice.py`

**凭证只从本地 `.env` 或环境变量读取，不写进代码、不进日志、不回传。**
`.env` 不要提交到 git。

### 数据源优先级

```
iFinD 官方接口 > Choice 官方接口 > akshare（A股）/ yfinance（美股）
```

官方接口包装好后会自动启用，代码不用改。

## 目录结构

```
valuation/
├── SKILL.md              怎么估值（给 Agent 看的流程）
├── INPUT_SCHEMA.md       输入定义
├── OUTPUT_SCHEMA.md      输出定义（统一 valuation JSON）
├── RULES.md              金融规则、默认值及理由、边界条件
├── README.md             本文件
├── cli.py                命令行入口
├── .env.example          凭证模板
├── engine/
│   ├── models.py         数据结构
│   ├── methods.py        WACC / DCF / 相对估值 / SOTP
│   ├── fusion.py         三法融合 + 敏感性 + 三情景
│   └── excel.py          Excel 底稿渲染
├── datasource/
│   ├── __init__.py       可插拔数据层（解释器与数据源双可插拔）
│   ├── worker.py         跑在数据解释器下的取数进程
│   ├── ifind.py          iFinD 适配器
│   ├── choice.py         Choice 适配器
│   └── indicators.json   iFinD 指标映射（可配置）
├── demo/                 最小可运行案例
├── tools/                自检与冒烟测试
├── output/               运行产物（自动创建）
└── _extract/             官方接口包的临时解压目录（可删）
```

## 输出长什么样

```bash
$ py cli.py value 600519 --peers demo/peers_baijiu.json

贵州茅台（600519）
  DCF        每股 2,646.99  （WACC 4.64%，g 2.50%）
  相对估值   每股 421.80  （5 家可比）
  融合        每股 1,534.39  现价 1263.0  →  低估 +21.5%

  提示 6 条：
    ⚠ 算出的 WACC（4.64%）低于市场隐含折现率（8.31%）367bp。折现率偏低会让
      DCF 结果系统性高于市价——通常是无风险利率处在历史低位、Beta 偏低，或 ERP 偏小。
    ⚠ 终值两种算法偏离 136%，根因多半是 WACC − g 只有 2.14%……
    ⚠ DCF 与相对估值相差 528%。两者背离到这个程度，加权平均值参考价值有限……
```

**这些提示不是报错，是模型的交叉验证结果。** 上面这家的例子说明：
用当前 A 股的无风险利率算出来的折现率，显著低于市场定价用的折现率——
所以 DCF 结果偏高。这是真实结论，应该写进交付说明，而不是调参数把它抹平。

## 自检与测试

```bash
py cli.py health                     # 数据层自检
py tools/smoke_engine.py             # 引擎冒烟（离线，用样例数据）
py tools/probe_ifind.py 600519       # iFinD 连通性与指标实测
py tools/check_env.py                # 各解释器的依赖分布
```

## 与作业要求的对应

| 作业要求（C 的交付） | 本包对应 |
|---|---|
| SKILL.md | `SKILL.md` |
| Comps 与 DCF 的输入/输出定义 | `INPUT_SCHEMA.md`、`OUTPUT_SCHEMA.md` |
| demo/（估值结果 JSON） | `demo/` |
| 数据要求说明 | `RULES.md` 第七节 |
| README.md | 本文件 |
| Demo：给目标公司与可比公司，能得出估值 | `py cli.py value <代码> --peers <文件>` |
| Interface：输出统一的 valuation JSON | `output/<标的>_valuation.json`，结构见 `OUTPUT_SCHEMA.md` |
| Excel 底稿渲染 | `output/<标的>_valuation.xlsx` |

统一数据接口里 C 只填一段：

```json
"valuation": { "comps": { ... }, "dcf": { ... } }
```

本模块的完整输出可以直接整体放进 `valuation` 字段。

## 免责声明

本模块仅供研究与教学用途，输出结果不构成投资建议。
所有估值都建立在假设之上，**假设比模型重要**。
