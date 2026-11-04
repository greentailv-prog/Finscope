# 数据源与接入方式

## 一、Provider 优先级

`data_source` 可选：

| 值 | 行为 |
|---|---|
| `canonical` | 只用 D / A 传入的 `financials` / `market_data` / `peer_financials` / `segments`，不联网；未传同业/分部时 Comps/SOTP 不启用 |
| `ifind` | 先试 iFinD；失败回退 akshare |
| `choice` | 先试 Choice；失败回退 akshare |
| `web` | 巨潮资讯找年报 PDF → 解析财务/分部；失败回退 akshare |
| `akshare` | 新浪财报 + 东财公司信息/主营构成（当前默认） |
| `auto` | D 有数据就用 D；否则 akshare；设置 `FINSCOPE_OFFICIAL=1` 时先探测 iFinD/Choice |

C **不会**在 D 已传入 `financials` / `market_data` 的情况下另取一套数据；
D 传入的行情会在取完财务后再次覆盖，保证同一份报告只有一个股价。

## 二、iFinD / Choice 当前状态

本机探测结果（`python cli.py probe-sources`）：

```json
{
  "iFinD":  {"installed": false, "dll_present": false, "credentials": false, "available": false},
  "Choice": {"installed": true,  "dll_present": false, "credentials": false, "available": false}
}
```

- iFinD：只有 `_extract/ths/iFinDPy.py`，没有 `x64/FTDataInterface.dll`，也没有账号；
- Choice：`EmQuantAPI.py` 可导入，但 `libs/windows/EmQuantAPI_x64.dll` 缺失，也没有账号；
- 因此当前无法直连，估值自动走 akshare / web。

### 接入步骤（A 装好后）

1. 安装官方客户端：
   - iFinD：运行 `SuperCommand.exe` 登录，确保 `FTDataInterface.dll` 与 `iFinDPy.py` 在 Python 路径下；
   - Choice：运行 `EmQuantAPISetup.exe`，确保 `libs/windows/EmQuantAPI_x64.dll` 与 `EmQuantAPI.py` 可用。
2. 在 `valuation/.env` 写入：
   ```
   IFIND_USER=...
   IFIND_PASSWORD=...
   CHOICE_USER=...
   CHOICE_PASSWORD=...
   FINSCOPE_OFFICIAL=1
   ```
3. 运行 `python cli.py probe-sources` 确认 `available=true`。
4. 运行 `python cli.py value 600519 --source ifind`（或 `choice`）验证取数。
5. 指标 ID 需要按账号权限实测：
   - iFinD 写入 `config/ifind_verified.json`（`mapping` 字段）；
   - Choice 写入 `config/choice_verified.json`；
   - 未实测前，官方适配器会明确返回「未配置映射」，不会猜字段。

> 如果 A 已经把官方源封装成自己的数据层，最稳妥的方式是 D 直接把
> `financials` / `market_data` / `peer_financials` 传给 C（`data_source="canonical"`），
> C 不再直连官方源。这样 A、C 用的是同一份数。

### A 的数据层直接注册进 C

如果希望 C 直接调用 A 的取数函数，可在进程启动时注册：

```python
from valuation.data.adapters import register_provider

register_provider(
    "a_data",
    fetch_company=my_fetch_company,    # (ticker, market) -> 与 akshare_provider.fetch_company 同结构
    fetch_segments=my_fetch_segments,  # (ticker) -> {"ok","rows","source",...}
)

result = run({"company": {"ticker": "600519", "market": "A"},
              "data_source": "a_data"})
```

这样 C 不新增任何数据源，只调用 A 已经接好的接口；失败时按 `warnings` 回退。

## 三、联网年报 PDF（`data_source="web"`）

### 链路

```
代码/公司名
  → 巨潮资讯年报检索（结构化，最可靠）
  → 下载年度报告 PDF
  → pdfplumber 抽取合并报表 + 主营业务分产品
  → 统一成 financials / segments
  → 估值
```

搜索兜底：DuckDuckGo HTML（无需密钥），也支持 Tavily / SerpAPI / Bing（有 key 时优先）。
**默认不走系统代理**；需要代理时设 `FINSCOPE_HTTP_PROXY`。

### 抽取内容

| 数据 | 来源 | 说明 |
|---|---|---|
| 营业收入/成本/EBIT/净利润/归母净利润 | 合并利润表 | 支持 4 列（合并+母公司）和 2 列表 |
| 经营现金流/资本开支/股利 | 合并现金流量表 | 资本开支取正数 |
| 折旧摊销 | 现金流量表补充资料 | 固定资产折旧+使用权资产+无形+长期待摊；也支持「折旧和摊销」合计 |
| 货币资金/有息负债/股东权益/总资产/股本 | 合并资产负债表 | 支持银行「百万元」口径 |
| 分部收入/成本/毛利率 | 「主营业务分产品情况」 | 有表格用表格，无边框用文字行；父级小计与子项同时出现时自动去重 |

### 单位

自动识别 `元 / 千元 / 万元 / 百万元 / 亿元`；每股收益保持「元/股」，不随报表单位缩放。

### 已知边界

- 年报 PDF 的「母公司报表」与「合并报表」可能同页；优先取合并列（前两列）。
- 部分银行/保险报表科目名与制造业不同，已补「营业收入合计」「本行股东的净利润」
  「股东权益合计」「负债及股东权益总计」等别名。
- 分部表如果是纯文字、且一行里数字不足 6 个，可能漏抽；此时回退到东财「主营构成」。
- 年报 PDF 解析失败时，`gather_company` 返回 `ok=false` + `warnings` + 已抓到的 URL，
  由 Agent / 使用者复核，不编数。

### 用法

```bash
# 只取证据，不估值
python cli.py search 600519 --years 2022-2025 --reports 2

# 直接用联网年报取数估值
python cli.py value 600519 --source web

# 端到端检验（三家公司）
python tests/simulate_web.py
```

API：

- `POST /api/valuation/evidence/search`：返回证据包；
- `POST /api/valuation/session` 时传 `data_source="web"`；
- 或把复核后的证据包放进 `web_evidence`，再 `PATCH /session/{id}/inputs` / `recompute`。

### 证据包结构

```json
{
  "financials": {
    "years": [2023, 2024, 2025],
    "revenue": [...], "cogs": [...], "ebit": [...],
    "net_income": [...], "da": [...], "capex": [...],
    "cfo": [...], "total_debt": ..., "cash": ..., "total_equity": ..., "shares": ...
  },
  "segments": [
    {"name": "智能家居业务", "revenue": 299927239000, "gross_margin": 0.299,
     "gross_profit": ..., "source": "年报第 49 页·分产品"}
  ],
  "sources": [
    {"name": "年报 PDF·2025", "purpose": "财务报表/分部", "as_of": "2025-12-31",
     "official": true, "note": "https://static.cninfo.com.cn/..."}
  ],
  "warnings": []
}
```

`web_evidence` 里的数字视为**已复核数据**，C 不再重新联网。

## 四、akshare（当前默认）

| 数据 | 接口 |
|---|---|
| A 股历史财务 | 新浪财经 `stock_financial_report_sina`（利润表/资产负债表/现金流量表） |
| 公司信息/行情/股本/行业 | 东方财富 `stock_individual_info_em` |
| 分部收入 | 东方财富 `stock_zygc_em`（主营构成） |
| 10 年期国债 | 中债 `bond_zh_us_rate` |

已知问题：

- 新浪折旧摊销常缺失 → 规则按资本开支/收入估算，并标低置信度；
- 五粮液类母公司/合并口径混用 → 引擎自动识别并剔除异常年；
- 同业倍数用免费源，精度低于 iFinD/Choice。

## 五、来源与 as-of

每条数据都写入 `sources[]`：

```json
{"name": "年报 PDF·2025", "purpose": "财务报表/分部", "as_of": "2025-12-31",
 "official": true, "note": "https://static.cninfo.com.cn/..."}
```

- 市场数据原则取基准日或之前；
- 使用基准日之后的数据必须标「后见信息」；
- D 传入的行情以 D 的 `price_date` / `price_source` 为准。

## 六、自检

```bash
python cli.py health            # 依赖
python cli.py probe-sources     # iFinD / Choice 状态
python cli.py search 600519     # 联网年报证据
python tests/simulate_web.py    # 三家年报 PDF 端到端
```
