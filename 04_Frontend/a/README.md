# `a/` —— A 的产物（原样搬运，E 一字节未改）

这个目录里的每一个文件都是 **A 的交付物**，从 `A/web/` 下原样复制过来。
E 没有改过其中任何一行 —— 这不是「E 重写了 A 的东西」，是「E 把 A 的东西
接到了自己的页面上」。

## 为什么单独开一个目录，而不是塞进 `data/`

因为**来源必须看得出来**。`data/real_data.js` 是 D 的统一对象、`data/real_memo.js`
是 D 的报告模块产出，两份文件头都写着「由 tools/build-data.js 自动生成」。
A 的东西不属于这一类：它是 A 自己写的引擎 + A 自己抽的语料，
E 只是调用方。混进 `data/` 之后，下一个人看到 `metrics.js` 会以为
也是 `build-data.js` 生成的，改 D 的适配层时顺手把它改了。

分开放，是让**「谁能改谁」这件事在目录结构上就成立**：

| 目录 | 谁的东西 | E 能不能改 |
|---|---|---|
| `data/` | D（`build-data.js` 生成） | 不能，要改去改 D 的适配层 |
| `a/` | A | 不能，要改去改 A 的源文件 |
| `js/` `css/` | E 自己 | 能 |

## 逐文件：这是什么、页面哪一块在用它

| 文件 | 是什么 | 谁在用 |
|---|---|---|
| `search.js` | A 的检索内核：BM25 + 向量混合，`FinSearch.searchAll()` | 页面 1 的年报问答 |
| `tokenize.js` | A 的中文分词器 `FinTok`，BM25 的词表就建在它上面 | 同上 |
| `data/metrics.js` | **9 家公司 × 17 个指标**的抽取结果，每条带三年 `series`、页码、章节、原文、口径、置信度 | 页面 1 的数据看板；页面 2 的三年序列 |
| `data/manifest.js` | 9 个分片的清单（公司名 / 块数 / 体积 / 文件名） | 页面 1 的公司列表与按需加载 |
| `data/queries.js` | A 出的 **14 道核验题**，每题带**预计算的查询向量** | 页面 1 的预设问题 |
| `data/tokens_golden.js` | 分词器的黄金样本（A 用它自检分词是否漂移） | 随 `tokenize.js` 一起加载 |
| `data/shard_*.js` | 9 份年报正文切块（共 17 MB，约 5,400 块），每块带 `text` / `printed_page` / `section` / `is_table` | **只在真的要提问时才注入** |

## 三条必须记住的事实

**① 这里的问答不需要后端。**
A 的原页面在 `file://` 下也能跑 —— 分片是用 `document.createElement('script')`
注入的（不是 `fetch`，`file://` 下 `fetch` 会被 CORS 拦掉），
而 14 道预设题各自带着预计算向量，所以连语义检索都是离线算的。
自由提问没有预计算向量时，`search.js` 会自动退回纯 BM25 ——
实测（茅台分片、`file://`）：预设题与自由提问都返回 8 条带页码的命中。

A 的 `serve.py` 只提供两件事：`/api/embed`（现场算自由提问的向量，
让召回更准）和 `/api/upload`（解析新上传的 PDF）。
**这两件都不影响本页能不能用** —— 前者是锦上添花，后者本来就不是静态页的活。

**② 17 MB 不能随页加载。**
`data/shard_*.js` 合计 17 MB，全量注入会让首屏卡住好几秒。
页面 1 的做法是**按需加载**：打开页面只注入 `manifest` / `metrics` / `queries`
（合计约 110 KB），只有用户真的点了一个问题时，才注入**那一家**的分片
（1.2–2.2 MB）—— 而且只注入一次，注过就留在 `window.FINSCOPE_SHARDS` 里。
见 `js/pages/p1-upload.js` 的 `ensureShard()`。

**③ E 不算同比。**
A 自己的看板里有「同比」一列，是 A 的 `app.js` 用 `pct(v25, v24)` 现算的。
E 的页面**不画这一列**，改成把 `series` 里的 **2023 / 2024 / 2025 三年原值**
并列 —— 三年原值是 A 抽出来的数据，照搬不算重算；同比是增长率，
那是 B 的成长性维度的活（见 `README.md` 的「E 的边界」）。

## 来源与校验

搬运日期：2026-10-13。来源目录：`A/web/`。
下面这 15 个文件逐一做过 sha256 对比，与 A 的源文件**逐字节一致**：

```
search.js                 5c03ee9a38ac9a3c
tokenize.js               8da27e173305a34c
data/metrics.js           e7eb82e2fd106c02
data/manifest.js          7e138366d29b6f7e
data/queries.js           45394d304116cef3
data/tokens_golden.js     f10e4e9adb54b69c
data/shard_000333.js      892e3ec1aadaa8dc
data/shard_000651.js      61b90f915a91089d
data/shard_002415.js      c5d19dc231cd3d6d
data/shard_002594.js      305cf03f50be6129
data/shard_300750.js      cedea319f53a74c9
data/shard_600031.js      a489214c6ec7964d
data/shard_600309.js      3dd372218e9c3348
data/shard_600519.js      0d9982550e609e26
data/shard_600887.js      2e26d8e28fcc8e72
```

（前 16 位。A 换了新一版抽取结果时，重跑 `sha256sum` 对一遍就知道
E 这边该不该跟着更新。）

### 一处**已知且刻意不改**的不一致

`data/manifest.js` 里 `size_mb` 字段与文件实际大小对不上
（如 600519 标 `1.20`、实际 1,206,996 B ≈ 1.15 MiB）。
那是 A 按 MB 记的、E 按 MiB 算的，差的是单位不是数据。
**E 不改它** —— 改一个字就不再是「原样搬运」了，而这一页要显示的
是公司名与块数（`n_chunks`），`size_mb` 只用于排序，不显示。
