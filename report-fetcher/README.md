# report-fetcher · 年报自动检索与下载

> FinRadar B 部分 · 输入侧入口模块
> 一句话：**给个证券代码，就把年报 PDF 拉下来，产出可被 A 直接消费的清单。**

---

## 1. 这个模块解决什么问题

原来的 FinRadar 流程里有个隐含前提：**年报得由用户自己找、自己上传**。

这意味着：

- 用户得先去交易所或巨潮网站翻公告、下载 PDF、再传回来
- 想对比一家公司三年数据，得手动找三份
- 想批量看二十家公司，得重复二十遍

`report-fetcher` 把这一步自动化：

```bash
python3 scripts/fetch_report.py --code 601398 --years 3 -o manifest.json
```

输出：

```
[OK] manifest -> manifest.json
     601398 工商银行 | 命中公告 6 | 选用 3 | 下载成功 3
     覆盖会计年度：[2025, 2024, 2023]（满足平均余额口径）
       - 601398_2025_annual_report.pdf  9.3MB  408页
       - 601398_2024_annual_report.pdf  9.9MB  410页
       - 601398_2023_annual_report.pdf  9.5MB  394页
```

**这是实跑结果，不是设计稿。**

---

## 2. 目录结构

```
report-fetcher/
├── SKILL.md                     智能体可加载的技能说明
├── README.md                    本文件
├── scripts/
│   └── fetch_report.py          抓取 + 下载 + 校验（零第三方依赖）
├── demo/
│   └── output_manifest.json     工行真实案例的抓取清单
└── data/
    ├── industry_hint.json       行业识别辅助词表（供风险引擎自动匹配行业剖面）
    └── reports/                 PDF 落地目录（运行时生成）
```

---

## 3. 快速开始

```bash
cd report-fetcher

# 抓最近 3 期年报
python3 scripts/fetch_report.py --code 601398 --years 3 \
        --outdir data/reports -o demo/output_manifest.json --pretty

# 只看看有哪些年报，先不下载
python3 scripts/fetch_report.py --code 601398 --no-download -o /tmp/peek.json

# 用公司简称
python3 scripts/fetch_report.py --keyword 工商银行 --years 3 -o /tmp/m.json
```

---

## 4. 输出字段说明

### `summary`

| 字段 | 含义 |
|---|---|
| `announcements_found` | 接口原始命中的公告数（**含摘要、英文版**） |
| `reports_selected` | 过滤掉摘要/英文/H股/更正后剩下的正文年报数 |
| `downloaded_ok` | 下载且校验通过的份数 |
| `periods_covered` | 覆盖的会计年度（倒序） |
| `periods_enough_for_average_balance` | 是否 ≥3 期（**决定周转率/回报率能不能算全**） |

### `files[]`

| 字段 | 含义 |
|---|---|
| `file` / `path` | 本地文件名与相对路径 |
| `pdf_url` | 原始公开 PDF 地址（可复核） |
| `title` / `publish_date` / `fiscal_year` | 公告标题、披露日期、会计年度 |
| `status` | `ok` / `download_failed` / `invalid_pdf` / `not_downloaded` |
| `sha256` / `size_bytes` / `pages` | 校验指纹 |

---

## 5. 设计取舍

### 5.1 为什么用巨潮，不直接爬交易所

- 巨潮是**证监会指定**披露平台，A 股年报覆盖最全
- 接口结构稳定、无需登录
- 静态文件服务（`static.cninfo.com.cn`）直连，不需要处理复杂的下载鉴权

### 5.2 为什么要做三重校验

年报 PDF 抓取最常见的两个坑：

1. **返回的是 HTML 错误页**（被限流、URL 失效），但程序以为下载成功
2. **文件截断**（网络中断），后续解析时才发现

所以：魔数校验挡掉错误页，SHA256 挡掉篡改与重复，页数校验挡掉截断。

### 5.3 为什么失败要显式上报

智能体流水线里最危险的不是报错，是**假装成功**。所以 `status` 严格区分四种状态，任何非 `ok` 都会同时进 `errors[]`，下游一看就知道这份数据不能用。

---

## 6. 已知边界

- 目前只覆盖**A 股**。港股、美股、新三板不在范围内
- 只抓**年度报告正文**，不含季报、半年报、招股书
- 依赖巨潮接口的可用性；若接口改版，需同步调整 `fetch_report.py` 中的 URL 与表单字段
- 未做代理池 / 分布式抓取——这是作业级工具，不是生产级爬虫

---

## 7. 与其他模块的接口

```
report-fetcher（本模块）
   │  files[].path
   ▼
A · 文档解析层
   │  input_financials.json
   ▼
B · financial-diagnosis（指标） → B · risk-radar（风险）
   │  ratios / risks
   ▼
D · 统一数据对象 → C（估值） → E（前端）
```
