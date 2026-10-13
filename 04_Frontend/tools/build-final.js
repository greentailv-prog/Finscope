/* ============================================================================
 * build-final.js —— 把 04_Frontend 打成一个可以直接双击的 05_Output/Final.html
 * ----------------------------------------------------------------------------
 * 做法：读 index.html，把里面**每一个 <link> / <script src> 引用的本地文件
 *       按原顺序内联进去**，然后把 window.FINSCOPE_DEMO 改成 true
 *       （演示模式：隐藏六页的「本页待实现」开发卡）。
 *
 * ★ 有一件事**故意不内联**，这是本脚本唯一需要解释的决定：
 *
 *   A 的 17 MB 年报正文（a/data/shard_*.js）不进 HTML，仍然放在
 *   Final.html 旁边的 a/data/ 里，运行期按需注入。
 *
 *   理由有两条，都不是风格问题：
 *   ① 内联之后是**一个 18 MB 的 HTML**。浏览器要先解析完这 18 MB 才画第一屏，
 *      双击打开会白屏好几秒 —— 而这份交付物最要紧的性质就是「双击就能打开」。
 *   ② 内联等于**取消按需加载**。现在点某一家公司才读那 1–2 MB，
 *      点了才花。全塞进 HTML 就变成「一打开先读 17 MB」，
 *      而首页看板实际只用得到 95 KB 的 metrics.js。
 *
 *   代价说明白：**只把 Final.html 这一个文件发给别人，
 *   年报问答会用不了**（会看到一条「分片没读进来」的说明，不会白屏）。
 *   六页的其余部分、上传校验、数据看板全都能用，因为它们的依赖都内联了。
 *   要问答能把 05_Output/ 整个目录一起拷走即可。
 *
 * 用法：
 *   node tools/build-final.js
 * 退出码：0 = 写成；1 = 读不动
 * ==========================================================================*/

"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const OUT_DIR = path.join(ROOT, "..", "05_Output");
const OUT = path.join(OUT_DIR, "Final.html");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* 内联进 <script> 的代码里只要出现 `</script`，浏览器就会认为脚本结束。
   这是个真会踩的坑（字符串里写 `"</script>"` 就中），所以统一转义。 */
function safe(code) {
  return code.replace(/<\/script/gi, "<\\/script");
}

function label(rel) {
  return "\n/* ================= " + rel + " ================= */\n";
}

let html;
try {
  html = read("index.html");
} catch (e) {
  console.error("读不到 index.html：" + e.message);
  process.exit(1);
}

const inlined = [];
let bytesIn = 0;

/* ★ 先摘掉 HTML 注释再扫引用。
   不摘会踩一个很难看的坑：index.html 里有一段**注释掉的**历史记录，
   正文就是 `<!-- … <script src="vendor/chart.umd.min.js"></script> … -->`
   （记着 Chart.js 为什么被撤）。不摘的话脚本会去读那个早被删掉的文件，
   直接 ENOENT 退出 —— 而它其实只是注释里的一句话。
   做法：注释换成占位符，全部替换做完再放回去，一个字符不改原注释。 */
const comments = [];
html = html.replace(/<!--[\s\S]*?-->/g, function (m) {
  comments.push(m);
  return "\u0000C" + (comments.length - 1) + "\u0000";
});

/* ---- ① <link rel="stylesheet" href="x"> → <style>…</style> ---- */
html = html.replace(/[ \t]*<link[^>]*href="([^"]+\.css)"[^>]*>\s*/g, function (m, href) {
  let css;
  try { css = read(href); } catch (e) {
    console.error("读不到样式 " + href + "：" + e.message);
    process.exit(1);
  }
  inlined.push(href);
  bytesIn += css.length;
  return "<style>" + label(href) + css + "\n</style>\n";
});

/* ---- ② <script src="x"></script> → <script>…</script> ----
   按文件在 index.html 里出现的顺序替换，顺序天然保持不变。 */
html = html.replace(/[ \t]*<script src="([^"]+)"><\/script>\s*/g, function (m, src) {
  let js;
  try { js = read(src); } catch (e) {
    console.error("读不到脚本 " + src + "：" + e.message);
    process.exit(1);
  }
  inlined.push(src);
  bytesIn += js.length;
  return "<script>" + label(src) + safe(js) + "\n</script>\n";
});

/* ---- ③ 演示模式开关：代码块形式的那个赋值改成 true ----
   ★ 只改 <script>window.FINSCOPE_DEMO = false;</script> 这一处，
     不去动 js/pages 里任何一处「if (!demo)」的判断 ——
     改数据不改逻辑，开关坏了也一眼能看出来是哪一步。 */
const before = html;
html = html.replace(/(<script>)window\.FINSCOPE_DEMO = false;(<\/script>)/,
  "$1window.FINSCOPE_DEMO = true;   /* 打包时由 tools/build-final.js 置 true */$2");
if (html === before) {
  console.error("没找到 window.FINSCOPE_DEMO = false; 那一行 —— " +
    "index.html 结构变了，先核对再打包（不打包一个开关没翻的版本）。");
  process.exit(1);
}

/* ---- ③.5 把摘走的注释原样放回去 ----
   放在打包说明那一步**之前**，这样下面 head 的替换面对的是完整文档。 */
html = html.replace(/\u0000C(\d+)\u0000/g, function (m, i) {
  return comments[+i];
});

/* ---- ④ 顶部加一段说明：这个文件是怎么来的、哪些没内联 ---- */
html = html.replace("<head>", "<head>\n  <!-- " +
  "本文件由 tools/build-final.js 从 04_Frontend/index.html 生成，" +
  "不要直接编辑 —— 改了会被下一次打包覆盖。源头在 04_Frontend/。 -->");

try {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(OUT, html, "utf8");
} catch (e) {
  console.error("写不出 " + OUT + "：" + e.message);
  process.exit(1);
}

/* ---- ⑤ 把 A 的分片拷到 Final.html 旁边（见文件头的那段说明） ---- */
const SRC_SHARDS = path.join(ROOT, "a", "data");
const DST_SHARDS = path.join(OUT_DIR, "a", "data");
let copied = 0, copiedBytes = 0, missing = [];
try {
  fs.mkdirSync(DST_SHARDS, { recursive: true });
  fs.readdirSync(SRC_SHARDS).filter(function (f) { return /^shard_.*\.js$/.test(f); })
    .forEach(function (f) {
      fs.copyFileSync(path.join(SRC_SHARDS, f), path.join(DST_SHARDS, f));
      copied++; copiedBytes += fs.statSync(path.join(DST_SHARDS, f)).size;
    });
} catch (e) {
  missing.push(e.message);
}
if (!copied && !missing.length) missing.push("a/data/ 下没有 shard_*.js");

/* ---- ⑥ 报告 ---- */
const kb = function (n) { return (n / 1024).toFixed(1) + " KB"; };
const mb = function (n) { return (n / 1048576).toFixed(1) + " MB"; };
const outSize = fs.statSync(OUT).size;

console.log("写成 " + OUT);
console.log("  HTML 体积   " + mb(outSize) + "   （内联了 " + inlined.length + " 个文件，" +
  mb(bytesIn) + "）");
inlined.forEach(function (f) { console.log("     · " + f); });
console.log("  未内联      A 的年报正文，拷到 Final.html 旁边的 a/data/");
if (missing.length) {
  console.log("  ★ 分片没拷成：" + missing.join("；") +
    " —— Final.html 里六个页面照常能用，只有年报问答会缺正文。");
} else {
  console.log("  a/data/     " + copied + " 个分片，" + mb(copiedBytes) +
    "（双击 Final.html 时按需注入，不随页加载）");
}
console.log("  演示模式    true（六页的「本页待实现」开发卡已隐藏）");
