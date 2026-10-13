# 05_Output/ —— 最终交付物

团队分工说明里约定本目录存放 `Demo_Report.md` 与 `Final.html`。

## 当前状态

**已产出。** `Final.html` 由 `04_Frontend/tools/build-final.js` 从
`04_Frontend/index.html` 生成 —— **不要直接编辑它**，改了会被下一次打包覆盖，
源头在 `04_Frontend/`。

| 文件 | 说明 |
|---|---|
| `Final.html` | 主交付物。双击即开，六页 + 上传 + 数据看板 + 年报问答 |
| `a/data/shard_*.js` | A 的 9 家年报正文，16.2 MB，**按需加载**（见下） |
| `Demo_Report.md` | 由 D 的报告生成模块产出，不是 E 的交付物 |

重新打包：

```
cd 04_Frontend
node tools/build-final.js
```

## Final.html 里有什么

内联进去的（约 0.7 MB，双击打开不依赖任何外部文件）：

- 三个 CSS（`base` / `layout` / `components`）
- A 的检索内核（`a/tokenize.js`、`a/search.js`）与 95 KB 的 `a/data/metrics.js`
- `data/real_data.js`（D 的统一对象）、`data/real_memo.js`（D 的 memo）
- 六个页面脚本、`app.js`

**六页全部可用**：页面 1 的上传窗口能点/能拖/能键盘触发，
9 家 chips 能切、看板表 17 科目 × 三年能读、页码能溯源，
年报问答 14 道预设题 + 自由提问能跑出答案与证据块。

## ★ 有一件事故意没有内联：A 的 17 MB 年报正文

它们留在 `Final.html` 旁边的 `a/data/`，运行期按需注入。两条理由：

1. **内联之后是一个 18 MB 的 HTML。** 浏览器要先解析完这 18 MB 才画第一屏，
   双击打开会白屏好几秒 —— 而这份交付物最要紧的性质就是「双击就能打开」。
2. **内联等于取消按需加载。** 现在点某一家公司才读那 1–2 MB，点了才花；
   全塞进 HTML 就变成「一打开先读 17 MB」，而首页看板实际只用得到 95 KB 的 `metrics.js`。

**代价要说清楚**：**只把 `Final.html` 这一个文件发给别人，年报问答用不了。**
这时它会显示一条「分片没读进来」的说明，**不会白屏**，其余全部照常。
要让问答也能用，把 `05_Output/` **整个目录**拷走即可。

## 怎么验证（不是「看着像对的」）

| 验什么 | 命令 |
|---|---|
| 六页版式（重叠 / 字体 / 溢出 / 看板墨迹） | `node tools/layout-probe.js --page all` |
| 量**打包后**的交付物 | `node tools/layout-probe.js --final --page all` |
| 带公司数据与问答一起量 | `node tools/layout-probe.js --page p1 --chip 3 --qa --widths 1366x768` |
| 配色/裸值/令牌审计 | `node tools/layout-audit.js` |
| 接口体检 | `node tools/interface-check.js` |
| 全部断言 | `node tests/run.js` |

## 注意

- `Demo_Report.md` 由 D 的报告生成模块产出（Report Generation skill），
  不是 E 的交付物。E 负责的是它的网页渲染版本（页面 6）。
- 本目录里的 `_*.html`（临时探针页）**不该存在**。`layout-probe.js`
  用完会自动删掉自己那份；如果看到残留，说明它中途被打断了，删掉即可。
