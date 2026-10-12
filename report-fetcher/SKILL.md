---
name: report-fetcher
description: 年报自动检索与下载。输入证券代码或公司简称，从巨潮资讯网（证监会指定信息披露平台）检索并下载上市公司年度报告 PDF，输出可被文档解析层直接消费的清单 JSON。当用户提供证券代码、想自动获取年报、或不想手动上传 PDF 时使用。
version: 1.0.0
owner: B
input: 证券代码（如 601398）或公司简称（如 工商银行）+ 需要覆盖的会计年度数
output: report manifest JSON（含每份年报的 URL / SHA256 / 页数 / 披露日期 / 本地路径）
---

# report-fetcher · 年报自动检索与下载

## 定位

FinRadar 的**输入侧入口**。它回答一个问题：

> 用户不想手动找年报、不想手动上传 PDF——能不能给个代码就把年报拉下来？

答案是**能**，而且已经实跑验证过。

```
证券代码 ──► 巨潮公开接口 ──► 年报 PDF ──► manifest.json ──► A（解析层）
 601398      ① 代码→orgId     下载+校验     带 SHA256/页数     输出 input_financials.json
             ② orgId→公告列表
```

## 数据源与合规

| 项 | 内容 |
|---|---|
| 平台 | 巨潮资讯网 www.cninfo.com.cn |
| 性质 | 中国证监会**指定**的上市公司信息披露平台 |
| 接口 | `/new/information/topSearch/query`（代码→orgId）、`/new/hisAnnouncement/query`（公告列表）、`static.cninfo.com.cn`（静态 PDF） |
| 鉴权 | **无需登录**，均为公开查询接口 |
| 边界 | 不绕过任何鉴权、不使用非公开接口、不抓取需会员权限的内容、不做高频爬取 |

合规约束写在代码注释里，也体现在行为上：默认请求间隔 1 秒（`--pause` 可调），失败即上报、不静默重试掩盖问题。

## 用法

```bash
# 按代码抓最近 3 期年报（推荐，平均余额口径需要 ≥3 期）
python3 scripts/fetch_report.py --code 601398 --years 3 \
        --outdir data/reports -o demo/output_manifest.json --pretty

# 按公司简称
python3 scripts/fetch_report.py --keyword 工商银行 --years 3 -o manifest.json

# 只检索不下载（先看有哪些年报）
python3 scripts/fetch_report.py --code 601398 --no-download -o manifest.json
```

参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--code` / `--keyword` | 二选一必填 | 证券代码或公司简称 |
| `--years` | 3 | 抓取最近 N 个会计年度。**建议 ≥3** |
| `--outdir` | `data/reports` | PDF 落地目录 |
| `-o` | 必填 | 清单输出路径 |
| `--limit` | 10 | 最多处理几份 |
| `--pause` | 1.0 | 下载间隔（秒） |
| `--no-download` | 关 | 只检索不下载 |

## 为什么 `--years` 建议 ≥3

这不是随便定的。B 的口径铁律之一是：

> **周转率、回报率的分母一律用「平均余额」**。

平均余额 = (期末 + 期初) / 2，要算它就必须有上一期期末数。而还要算**上期**的 ROA / ROIC 做同比，就再多要一期。所以：

```
N 期数据  →  能算 N-1 期的周转率/回报率  →  能算 N-2 期的同比变动
3 期       →  2 期                        →  1 期
```

manifest 里会明确标注 `periods_enough_for_average_balance`，不足 3 期时给出提示，缺期指标会自动转进待核验队列，而不是偷偷拿期末数当分母糊弄过去。

## 输出结构

```jsonc
{
  "schema_version": "finradar.report-fetcher/1.0",
  "generated_at": "2026-10-10 19:13:58",
  "source": { "name": "巨潮资讯网", "endpoints": [...] },
  "query": { "keyword": "601398", "years_requested": 3 },
  "company": { "sec_code": "601398", "sec_name": "工商银行", "org_id": "jjxt0000019" },
  "summary": {
    "announcements_found": 6,        // 含摘要，原始命中
    "reports_selected": 3,           // 过滤摘要后的正文年报
    "downloaded_ok": 3,
    "periods_covered": [2025, 2024, 2023],
    "periods_enough_for_average_balance": true
  },
  "files": [{
    "file": "601398_2025_annual_report.pdf",
    "pdf_url": "http://static.cninfo.com.cn/finalpage/2026-03-28/1225047240.PDF",
    "title": "工商银行2025年度报告",
    "publish_date": "2026-03-28",
    "fiscal_year": 2025,
    "status": "ok",                  // ok / download_failed / invalid_pdf
    "sha256": "e2edab73...",
    "size_bytes": 9289165,
    "pages": 408
  }],
  "errors": [],
  "downstream": { "handoff_to": "A（文档解析层）" }
}
```

## 可靠性设计

| 机制 | 做法 |
|---|---|
| 三重校验 | PDF 魔数 `%PDF-` → SHA256 → 页数（装了 pypdf 才算） |
| 幂等 | 已存在且 SHA256 一致则跳过，不重复下载 |
| 重试 | 每步最多 3 次，退避 1.5s / 3s |
| 限流 | 请求间隔可配，默认 1 秒 |
| 失败可见 | 下载失败、校验失败都写进 `errors[]`，`status` 明确区分，**绝不当作成功** |
| 零依赖 | 只用标准库 `urllib`，装好 Python 就能跑 |

## 与手动上传的关系

两条路并存，不是替代关系：

- **自动抓取**：有代码就能拉，省事，适合批量 / 复盘
- **手动上传**：用户手上已有 PDF、或要分析非 A 股 / 非公开渠道的文件

两条路最终都汇到同一个 `input_financials.json`，下游 B 的引擎完全不关心数据是抓来的还是传来的——**入口不同，契约相同**。
