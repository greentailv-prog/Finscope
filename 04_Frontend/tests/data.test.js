/* FinScope 数据层冒烟测试
 * 在 node 里模拟浏览器全局，跑通「格式化口径 + 取数 + 中文名 + 溯源 + 契约 + memo」。
 * 查的是「写得对不对」；页面能不能跑起来看 render.test.js。
 *
 * 用法：node tests/data.test.js
 *      node tests/data.test.js <04_Frontend 目录>   # 显式指定
 *
 * 【2026-10-13 重写：从 mock 换挂 D 的真实交付物】
 *
 *   改之前这份测试读的是 data/mock_data.js。那份 mock 是 C 那版契约的产物，
 *   带着 business_mix / history / ratios.*._score / risk.calculation 这些
 *   **D 并不产出的字段**。所以它验的是一个已经不存在的世界 ——
 *   而且它验得很绿，绿到把 dataLoader 里一个真的 ReferenceError
 *   （ratioGroups 里裸调 ratioItems）盖了整整一轮。
 *
 *   换挂 data/real_data.js + data/real_memo.js（都由 tools/build-data.js
 *   从 D 的 .json 原样搬运）。于是这份测试验的正好是**要交付的那份数据**。
 *
 *   随之而来的一条纪律：**断言尽量写成不变式，不写死数值**。
 *   写死 128.6 那种数，D 一重新交付就红一片，而红的原因跟 E 毫无关系。
 *   凡是「口径」类的断言（元→亿元、×100、千分位）一律喂**构造的输入**，
 *   不读数据 —— 那本来就是在测 format.js，不是在测 D。
 * ==========================================================================*/
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const ROOT = process.argv[2] || path.join(__dirname, "..");
const files = [
  "data/real_data.js",
  "data/real_memo.js",
  "js/format.js",
  "js/contract.js",
  "js/dataLoader.js"
];

const sandbox = {};
sandbox.window = sandbox;                 // 模拟浏览器：window === 全局
sandbox.globalThis = sandbox;
sandbox.console = { log: () => {}, warn: () => {}, error: () => {} };
vm.createContext(sandbox);

for (const f of files) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, f), "utf8"), sandbox, { filename: f });
}

const F = sandbox.FinScope;
const out = [];
let pass = 0, total = 0;

function t(label, got, want) {
  total++;
  const ok = String(got) === String(want);
  if (ok) pass++;
  out.push(`${ok ? "PASS" : "FAIL"}  ${label}${ok ? "" : `\n        得到: ${got}\n        期望: ${want}`}`);
}

F.data.load();

/* 基线：真实交付物上本来就有的提醒条条数。下面做降级实验时会反复 load
   别的数据，最后要断言「还原后回到这个数」—— 不多报也不吞掉真缺口。 */
const BASE_WARN = F.data.status().warnings.length;

out.push(`数据源: ${F.data.status().sourceName} / 校验提醒: ${F.data.status().warnings.length} 项`);
if (F.data.status().warnings.length) {
  out.push(F.data.status().warnings.map(m => "        · " + m).join("\n"));
}
out.push("");

/* ==================================================================== */
/* 一、format.js 口径（喂构造输入，不读数据）                            */
/* ==================================================================== */
/* 这一节的输入全部是当场造的字面量。理由：测的是 E 的换算规则本身。
   D 换了数字不该让这一节变色，E 改了换算才该。 */

out.push("=== format.js 口径 ===");

/* 元 → 亿元：÷1e8，且**2 位小数 + 千分位**（跟 D 的 memo 同一个写法） */
t("元 → 亿元（÷1e8、2 位、千分位）",
  F.fmt.metric({ value: 168838102514.79, unit: "元" }), "1,688.38 亿元");
t("万元 → 亿元（÷1e4）",
  F.fmt.metric({ value: 128600, unit: "万元" }), "12.86 亿元");
t("亿元原样（1 位）",
  F.fmt.metric({ value: 128.6, unit: "亿元" }), "128.6 亿元");
t("三位数不加千分位", F.fmt.money(999), "999.0 亿元");
t("四位数加千分位",   F.fmt.money(1688.3810251479, 2), "1,688.38 亿元");
t("负数也加千分位",   F.fmt.money(-1688.38, 2), "-1,688.38 亿元");

t("百分数 ×100",     F.fmt.metric({ value: 0.124, unit: "%" }), "12.40%");
t("倍数",            F.fmt.metric({ value: 1.62, unit: "倍" }), "1.62 倍");
t("次数",            F.fmt.metric({ value: 3.32, unit: "次" }), "3.32 次");
t("天数",            F.fmt.metric({ value: 30.49, unit: "天" }), "30.49 天");
t("小数 → 裸数字（单位分不出该不该 ×100）",
  F.fmt.metric({ value: 0.124, unit: "小数" }), "0.1");

t("缺失值 → 破折号", F.fmt.metric(null), "—");
t("undefined → 破折号", F.fmt.metric(undefined), "—");
t("零值 ≠ 缺失",     F.fmt.num(0), "0.0");
t("字符串数字也能吞掉（年报 PDF 抽出来常是串）",
  F.fmt.metric({ value: "168838102514.79", unit: "元" }), "1,688.38 亿元");
/* 输入里本来就有千分位时要能吃掉，否则会 Number() 出 NaN ——
   页面 6 之类的下游把 D 的 "1,688.38 亿元" 再喂回来的情况真会发生。
   这里显式给 2 位小数，因为位数是按**来源单位**分档的（见 money 的注释）。 */
t("输入自带千分位也能吞掉（不是 NaN）",
  F.fmt.money("1,688.3810251479", 2), "1,688.38 亿元");

t("带符号：正", F.fmt.signed(0.184), "+0.2");
t("带符号：负", F.fmt.signed(-0.184), "-0.2");
t("带符号百分数", F.fmt.signedPercent(-0.0121), "-1.21%");

out.push("\n=== format.js 状态词：两套口径并存 ===");
/* D 的 status 讲「算不算得出来」不是「好不好」，所以 ok 绝不能染成 is-good。 */
t("ok 不着色",           F.fmt.statusClass("ok"), "");
t("not_evaluable → 橙（唯一需要动作的一档）", F.fmt.statusClass("not_evaluable"), "is-watch");
t("not_meaningful 不着色", F.fmt.statusClass("not_meaningful"), "");
t("not_applicable 不着色", F.fmt.statusClass("not_applicable"), "");
t("B 的 good → is-good", F.fmt.statusClass("good"), "is-good");
t("状态词：ok",        F.fmt.statusLabel("ok"), "正常");
t("状态词：not_evaluable", F.fmt.statusLabel("not_evaluable"), "待核验");
t("状态词：not_applicable", F.fmt.statusLabel("not_applicable"), "不适用");
t("已抽到 / 正常 不占胶囊", F.fmt.statusQuiet("found"), true);
t("待核验 要占胶囊",   F.fmt.statusQuiet("not_evaluable"), false);

t("风险等级 high → sev-high",       F.fmt.severityClass("high"), "sev-high");
t("风险等级 medium → sev-attention", F.fmt.severityClass("medium"), "sev-attention");
t("风险等级 low → sev-normal",      F.fmt.severityClass("low"), "sev-normal");

/* ==================================================================== */
/* 二、取数（读真实交付物，但只断言结构不变式）                          */
/* ==================================================================== */

out.push("\n=== dataLoader 取数 ===");
t("get 深层路径（公司名非空）",
  typeof F.data.get("company.name") === "string" && F.data.get("company.name").length > 0, true);
t("get 断链兜底", F.data.get("a.b.c.d", "兜底"), "兜底");
t("数据已加载", F.data.status().loaded, true);
t("没有类型 / 范围异常", F.data.status().warnings.filter(m => m.indexOf("类型不对") >= 0 || m.indexOf("超出约定范围") >= 0).length, 0);

/* 五个维度组都在，且**都有指标**（空分组不应出现） */
const groups = F.data.ratioGroups();
t("五个维度组齐全", groups.map(g => g.key).join(","),
  "growth,profitability,solvency,efficiency,cashflow_quality");
t("没有空分组", groups.every(g => F.data.ratioItems(g.key).length > 0), true);

/* 指标项：每项都得有中文名和格式化好的显示值。
   ★ 这两条是 dataLoader 对页面的承诺，不是对 D 的期待。 */
const allItems = [];
groups.forEach(g => F.data.ratioItems(g.key).forEach(x => allItems.push(x)));
t("每个指标都有中文名", allItems.filter(x => !x.label || x.label === x.key).length, 0);
t("每个指标都有显示值 text", allItems.filter(x => typeof x.text !== "string" || !x.text).length, 0);
/* 页码：**比值项基本没有**（比率由几个科目算出，不对应某一页），
   但有两个例外 —— ocf / capex 是从现金流量表直接透传的行，D 给了它们的页码。
   所以断言不写「一律 null」（那是错的），写不变量：只可能是 null 或数字。 */
t("页码只可能是 null 或数字",
  allItems.every(x => x.page === null || typeof x.page === "number"), true);
t("纯比率（roe_weighted）没有页码", F.data.item("ratios.profitability.roe_weighted").page, null);
t("_score 被跳过（D 不产出，guard 留着）",
  allItems.some(x => x.key === "_score"), false);
t("status 只用得到这三档",
  allItems.every(x => ["ok", "not_evaluable", "not_meaningful"].indexOf(x.status) >= 0), true);

const noLabel = allItems.filter(x => !x.label || x.label === x.key);
t("所有指标都有中文名（无遗漏）",
  noLabel.length ? noLabel.map(x => x.key).join(",") : "无遗漏", "无遗漏");

out.push("\n=== ratioLabel 中文名：三级兜底 ===");
t("映射表命中", F.data.ratioLabel("roe_weighted"), "加权 ROE");
/* ★ 签名在 2026-10-13 收成单参：ratioLabel(key)。
   原来还有个 item 参数，让「数据自带 name」优先于映射表 —— 但 D **不产出
   name**（见 contract.js 一·6），那一级永远是空的，索性撤掉。
   现在只有两级：映射表命中 → 中文名；没登记 → **原样返回英文键名**，不猜。 */
t("未知键原样返回", F.data.ratioLabel("some_new_ratio"), "some_new_ratio");

out.push("\n=== metricLabel：风险场景的三级词表 ===");
/* ★ 这里最容易踩的坑：ratios 的键名和 risks 引用的键名**不是同一套**。
   ratios 叫 revenue_growth_yoy / roe_weighted / cfo_to_net_income，
   risks 叫 revenue_growth / roe_delta / ocf_to_net_income_parent。
   所以页面 4 不能拿 ratioLabel 去查风险里的键 —— 那是 metricLabel 的活。 */
t("财报科目键 → 中文名", F.data.metricLabel("goodwill"), "商誉");
t("规则短名 → 中文名", F.data.metricLabel("debt_to_assets"), "资产负债率");
t("没登记的键原样返回（不猜）", F.data.metricLabel("brand_new_key"), "brand_new_key");
t("null 不炸", F.data.metricLabel(null), null);

out.push("\n=== 风险：只装已触发的 ===");
const risks = F.data.sortedRisks();
t("有触发的风险", risks.length > 0, true);
t("每条都有 severity 与 severity_tag",
  risks.every(r => r.severity && r.severity_tag), true);
t("按 severity 排序（high 在前）", risks[0].severity, "high");
/* rules_evaluated 是**全部** 36 条规则，含未触发的 —— 和 risks 不是一回事 */
t("rules_evaluated 条数多于 risks（它装全部规则）",
  F.data.get("rules_evaluated", []).length > risks.length, true);

/* ==================================================================== */
/* 三、页面2 财报科目分组（financialGroups）                             */
/* ==================================================================== */

out.push("\n=== 页面2 财报科目分组 ===");
const books = F.data.financialGroups();
const bookItems = books.flatMap(b => b.items);
t("按三张报表分组", books.map(b => b.label).join("/"), "利润表/资产负债表/现金流量表");
t("科目名已中文化", bookItems.every(r => /[一-龥]/.test(r.name)), true);
t("科目名不是英文键名（兜底没被触发）",
  bookItems.filter(r => r.name === r.key).map(r => r.key).join(",") || "无", "无");
t("科目无重复", new Set(bookItems.map(r => r.key)).size, bookItems.length);
t("每项都带原始 item（数值/页码从它读）",
  bookItems.every(r => r.item && r.item.value !== undefined), true);
t("每个科目都能溯源（都有 page）",
  bookItems.filter(r => r.item.page != null).length, bookItems.length);

/* 每块有自己的形状，页面 2 靠它决定比例条怎么画 */
t("每块带 shape（plain / diverging）",
  books.every(b => b.shape === "plain" || b.shape === "diverging"), true);
t("每块带 headline（头条科目）", books.every(b => !!b.headline), true);
t("每块的 headline 在块内真的存在",
  books.every(b => b.items.some(r => r.key === b.headline)), true);
t("每块都带上期值（D 的 prior_value / prior_period）",
  bookItems.filter(r => r.prior && r.prior.value !== undefined).length > 0, true);

/* 行级形状覆写：只有资本开支该从左右分流里退出来。
   它是流出额、不是净额 —— 数据里是正的，不许翻符号来迁就图形。 */
const overridden = bookItems.filter(r => r.shape);
t("只有资本开支覆写了形状", overridden.map(r => r.key).join(","), "capex");
t("资本开支覆写成普通幅度条", overridden[0] && overridden[0].shape, "plain");
t("资本开支的原始值没被翻符号", F.data.item("financials.capex").value > 0, true);

/* 词汇表没登记的科目必须兜进「其他」，不能静默丢失 ——
   D 换了数据源、多抽一个科目，前端不该假装它不存在。 */
const fin = F.data.get("financials");
fin.__probe_metric__ = { value: 1, unit: "亿元", period: "2025" };
const books2 = F.data.financialGroups();
const extra = books2.filter(b => b.label === "其他");
t("未登记科目兜进「其他」组", extra.length, 1);
t("「其他」组里就是那个科目",
  extra.length && extra[0].items.length === 1 && extra[0].items[0].key === "__probe_metric__",
  "true");
t("原三组不受影响", books2.filter(b => b.label !== "其他").length, 3);
delete fin.__probe_metric__;

/* ---- not_applicable：不画，但「缺值」照画 -------------------------- */
/* 这两条是**一对**，钉的是同一个判据的两面：
     status === "not_applicable"  → 这一项对这家公司不成立，**整行不画**；
     value === null 且 status 不是 → **抽取失败**，照画一个破折号。
   ★ 只能按 status 判，不能按 value 判。按 value 判会把「上游没抽到」
   静默抹掉 —— 那正是本页「数字必须可验证」要防的事。
   真例：茅台没有商誉（D 给 goodwill.status = "not_applicable"，page 57）。 */
const bookKeys = bookItems.map(r => r.key);
t("不适用（not_applicable）的科目不进表 —— 真数据里是商誉",
  bookKeys.includes("goodwill"), false);
t("真数据：被滤掉的正好是 1 个", 17 - bookItems.length, 1);
/* 兜底组不能按「词汇表没登记」把它重新收编 ——
   判的是它有没有真的消失，不是代码里写没写 return。 */
t("不适用时不会被「其他」组收回去", books.some(b => b.label === "其他"), false);

/* 反向：把商誉改成「抽取失败」（value 仍是 null，只把 status 换掉），
   它必须**回到表里**，带一个破折号。这一条挡的是「按 value 判」那个改法。 */
const gw = F.data.get("financials").goodwill;
const gwStatus = gw.status;
gw.status = "found";
const books3 = F.data.financialGroups();
const gwRow = books3.flatMap(b => b.items).filter(r => r.key === "goodwill");
t("同一条目 status 改成 found 就回到表里（所以判据是 status 不是 value）",
  gwRow.length, 1);
t("回到表里时它的值仍是 null（页面负责画破折号）", gwRow[0].item.value, null);
gw.status = gwStatus;
t("改回去之后又消失（有进有出，不是单向丢弃）",
  F.data.financialGroups().flatMap(b => b.items).some(r => r.key === "goodwill"), false);

/* ==================================================================== */
/* 四、溯源反查（findSource）                                            */
/* ==================================================================== */
/* ★ 语义在 2026-10-13 换过：不再按「指标名 + 页码」两路匹配，
   改成**按页码**去 sources[] 里找条目 —— 因为 D 的 sources[] 现在是
   「这份 PDF 我抽了哪一页」的清单（{company_name, file_name, page, ...}），
   不再带 metric 字段。metric 参数保留只为兼容调用点，不参与匹配。 */

out.push("\n=== findSource 溯源反查 ===");
const srcList = F.data.get("sources", []);
const firstPageSrc = srcList.find(s => s && typeof s.page === "number");
t("sources[] 有带页码的条目", !!firstPageSrc, true);
t("按页码命中", F.data.findSource("任意指标", firstPageSrc.page) === firstPageSrc, true);
t("页码为 null → null（没有页码就没有出处可查）", F.data.findSource("营业收入", null), null);
t("页码为 undefined → null", F.data.findSource("营业收入", undefined), null);
t("查不到的页码 → null", F.data.findSource("营业收入", 99999), null);

/* ==================================================================== */
/* 五、消费端契约（js/contract.js）                                      */
/* ==================================================================== */
/* 这一层拿一份**逐路径的消费契约**走查整份数据，喂两个出口 ——
   页面上的校验提醒条，和 tools/interface-check.js。 */

out.push("\n=== 消费端契约：契约自身 ===");
const C = F.contract;
t("契约已加载", !!C, true);
t("契约路径数 > 100（够细才有意义）", C.allPaths().length > 100, true);
t("路径不重复", new Set(C.allPaths()).size, C.allPaths().length);

/* ★ 防漂移：contract.js 的 INDICATORS 与 dataLoader.js 的 RATIO_META
   是同一批指标的两种切法，一个管「组 → 有哪些键」，一个管「键 → 中文名」。
   谁多一个键就是漏登记。这条断言就是让它们不能各走各的。 */
const indKeys = [];
Object.keys(C.INDICATORS).forEach(g => C.INDICATORS[g].forEach(k => indKeys.push(g + "." + k)));
const actualKeys = groups.flatMap(g => F.data.ratioItems(g.key).map(x => g.key + "." + x.key));
/* ★ 这条原来断言的是**完全相等**，那是错的：INDICATORS 不是「有哪些指标」的
   全清单，是「哪几项常显」的核心名单（页面 3 靠 isCore 决定谁折进折叠组）。
   D 一个维度有 10–18 项，核心名单每个维度只有 2–4 项。
   真正要防的漂移是：核心名单里出现一个数据里根本没有的键 ——
   那样页面 3 会去找一个不存在的指标，而折叠组里少了那一项，静默出错。 */
t("核心名单登记数少于实际指标数（它是核心名单不是全清单）",
  indKeys.length < actualKeys.length, true);
const actualSet = new Set(actualKeys);
t("核心名单里没有一个不在数据里的键（无漏登记）",
  indKeys.filter(k => !actualSet.has(k)).join(",") || "无", "无");
t("核心名单每项都真的被标成 isCore",
  indKeys.every(k => {
    const g = k.split(".")[0], key = k.slice(g.length + 1);
    const it = F.data.ratioItems(g).find(x => x.key === key);
    return it && it.isCore;
  }), true);

out.push("\n=== 消费端契约：走查 D 的真实交付物 ===");
const cs = F.data.contractStatus();
t("contractStatus 可用", !!cs, true);
/* ★ 2026-10-13 改判：**七块全部完整可渲染**。
   改之前这里是「6/7，缺的那块是财务概览，因为它缺商誉（core）· 欠方 A」——
   那条断言当时是对的，它把「A 还没抽这一行」如实记了下来。
   但现在知道得更清楚了：D 在 goodwill 上标了 status: "not_applicable"，
   即「年报的资产负债表上本来就没有『商誉』这一行」。
   所以那不是一个**待补的缺口**，是一个**已经答复了的不适用** ——
   提醒条上挂着「缺商誉 · 找 A」，是让 E 去找 A 要一个根本不存在的数。
   一条指错的欠账，比没有欠账更坏。

   现在商誉走 na（不适用）：不进 coreMiss、不进欠账清单、不影响可渲染判定。
   下面两条把这件事的两面都钉住 —— 只钉「7/7」是不够的，
   还得钉住「它没被悄悄塞进别的桶里」。 */
t("可完整渲染 7/7（商誉不是缺口，是「不适用」）",
  cs.pages.filter(p => p.core > 0).map(p => p.title).join(","), "");
t("财务概览没有 core 缺口了", cs.pages.find(p => p.id === "p2").core, 0);
t("但商誉确实被记成了 na，不是被丢掉",
  cs.pages.find(p => p.id === "p2").na, 4);
t("商誉也不欠任何人（不进 byOwner）",
  (cs.byOwner.A || { core: [] }).core.some(m => /goodwill/.test(m.spec.p)), false);
t("页面 6 没有 core 缺口（memo 绑定表齐全）",
  cs.pages.find(p => p.id === "p6").core, 0);
t("没有类型 / 范围异常（problems）", cs.totals.problems, 0);

/* 待交付项是**已知欠账**（B 的三张偿债指标、D 的来源 URL），
   不算这份数据的错。所以它绝不能进校验提醒条 ——
   否则提醒条会常年挂着同一批字，变成没人看的墙纸。 */
t("有已知待交付项（B 的指标 / D 的来源 URL）", cs.totals.open > 0, true);

/* D 自己的合规闸门：memo 里 151 个数字 token 全部可溯源 */
const memoV = F.data.memoValidation();
t("memo 数字校验通过", memoV && memoV.passed, true);
t("扫描到的 token 数与放行数一致",
  memoV.scannedTokens === memoV.allowedCount, true);
t("没有越界数字", memoV.violations.length, 0);
t("没有合规命中", memoV.hits.length, 0);

out.push("\n=== 消费端契约：走查一份「坏数据」===");

/* 改数据用「深拷一份 → load → 跑完立刻还原」。直接改 ctx 里的对象是不行的：
   ctx 是 dataLoader 的私有变量。 */
const ORIG_DATA = JSON.parse(JSON.stringify(sandbox.FINSCOPE_DATA));
const ORIG_MEMO = JSON.parse(JSON.stringify(sandbox.FINSCOPE_MEMO));
function withData(mutate) {
  const d = JSON.parse(JSON.stringify(ORIG_DATA));
  mutate(d);
  F.data.load(d, ORIG_MEMO);
}
function withMemo(mutate) {
  const m = JSON.parse(JSON.stringify(ORIG_MEMO));
  mutate(m);
  F.data.load(ORIG_DATA, m);
}
function restoreData() { F.data.load(ORIG_DATA, ORIG_MEMO); }

/* 模拟「只有 A 交了一半」：抽掉四块。
   这时五页应该集体报缺口 —— 而不是像浅检查那样只报一句「缺少顶层字段 ratios」。 */
withData(d => {
  delete d.ratios; delete d.risks; delete d.valuation; delete d.sources;
});
const bad = F.data.status().warnings;
t("缺四块时提醒条有内容", bad.length > 0, true);
t("提醒条点名了页面（不是只报顶层键）", bad.some(m => m.indexOf("【") >= 0), true);
t("提醒条点出了找谁", bad.some(m => m.indexOf("找 ") >= 0), true);
t("缺 ratios 时财务诊断被点名", bad.some(m => m.indexOf("财务诊断") >= 0), true);
t("缺 risks 时风险雷达被点名", bad.some(m => m.indexOf("风险雷达") >= 0), true);
t("缺 valuation 时估值分析被点名", bad.some(m => m.indexOf("估值分析") >= 0), true);
/* 一条真缺口不能被一堆子路径淹没：ratios 整块没了，
   不该冒出 68 条「成长性·revenue_yoy 缺失」。每组最多一条。 */
t("同名缺口被压成一条（不逐路径刷屏）", bad.length < 12, true);
restoreData();

/* 脏数据比缺数据更严重：缺数据只是显示成空状态，脏数据是显示成假的。
   所以类型 / 范围异常永远要报，哪怕它挂在一个可选字段上。 */
withData(d => { d.financials.revenue = { value: "一百六十八亿" }; });
t("数值字段传成中文数字被走查器抓出来",
  F.data.status().warnings.some(m => m.indexOf("类型不对") >= 0), true);
restoreData();

t("还原后提醒条回到基线（不多报、不少报）",
  F.data.status().warnings.length, BASE_WARN);
t("还原后可渲染页面数不变", F.data.contractStatus().totals.renderable, cs.totals.renderable);
t("还原后 ratioGroups 仍然工作", F.data.ratioGroups().length, 5);

/* ==================================================================== */
/* 六、页面6 的 memo 绑定表                                              */
/* ==================================================================== */
/* memo 与统一对象是**两份独立产物**，所以要单独验：
   交叉验（同一份数据两份产物）在下一节。 */

out.push("\n=== 页面6 memo：绑定表结构 ===");
t("memo 已加载", F.data.hasMemo(), true);
t("meta 带公司名", !!(F.data.memoMeta() && F.data.memoMeta().company_name), true);
t("meta 带引擎标识（决定读者怎么读这份简报）",
  !!(F.data.memoMeta() && F.data.memoMeta().engine), true);

const cols = F.data.memoColumns();
t("七节标题来自 D 的 columns[]", cols.length, 7);
t("节标题都是中文（E 不自己起标题）",
  cols.every(c => /[一-龥]/.test(c)), true);

const scalars = F.data.memoScalars();
t("标量绑定表非空", Object.keys(scalars).length > 0, true);
t("同名 placeholder 取第一条（值必然相同）",
  Array.isArray(sandbox.FINSCOPE_MEMO.scalars)
    && sandbox.FINSCOPE_MEMO.scalars.filter(s => s.placeholder === "revenue_growth").length > 1, true);
t("标量直出 formatted（E 不重算）",
  F.data.memoValue("revenue"), sandbox.FINSCOPE_MEMO.scalars.find(s => s.placeholder === "revenue").formatted);
t("没绑到的 placeholder → null", F.data.memoValue("no_such_placeholder"), null);

const colls = F.data.memoCollections();
t("collections 转成 {name: items[]}",
  Object.keys(colls).length, sandbox.FINSCOPE_MEMO.collections.length);
t("风险集合在场", F.data.memoCollection("risks").length > 0, true);
t("仪表盘集合在场", F.data.memoCollection("dashboard").length > 0, true);
t("敏感性矩阵五行", F.data.memoCollection("sensitivity_rows").length > 0, true);
t("取不存在的集合 → 空数组（不是 undefined）", F.data.memoCollection("nope").length, 0);

/* memoRow：{col: {formatted}} → {col: "文字"}，空值统一成 null */
const dashRow = F.data.memoCollection("dashboard")[0];
const parsed = F.data.memoRow(dashRow, ["label", "value_str", "no_such_col"]);
t("memoRow 取出 formatted 字符串", typeof parsed.label === "string", true);
t("memoRow 缺的列 → null（不是 undefined）", parsed.no_such_col, null);
t("memoRow 对 null 行不炸", F.data.memoRow(null, ["a"]).a, null);
t("memoRow 会把空串归一成 null",
  F.data.memoRow({ a: { formatted: "" } }, ["a"]).a, null);

out.push("\n=== 页面6 memo：降级路径 ===");
withMemo(m => { m.validation = { passed: false, allowed_count: 150, scanned_tokens: 151, violations: ["p3: 数字 42 无出处"] }; });
t("校验未通过时 passed 为 false", F.data.memoValidation().passed, false);
t("越界数字被带出来", F.data.memoValidation().violations.length, 1);
restoreData();

withMemo(m => { delete m.validation; });
t("validation 缺席时仍返回对象（只要 compliance 有 hits）",
  F.data.memoValidation() === null, true);
withMemo(m => { delete m.validation; m.compliance = { hits: [{ rule: "x" }] }; });
t("只有 compliance 命中时也返回对象", F.data.memoValidation().hits.length, 1);
restoreData();

F.data.load(ORIG_DATA, null);
t("memo 单独缺席时不改变统一对象（两份产物互不牵连）", F.data.hasMemo(), false);
t("memo 缺席时 memoValue 返回 null 而不炸", F.data.memoValue("revenue"), null);
t("memo 缺席时 memoColumns 空数组", F.data.memoColumns().length, 0);
t("memo 缺席时 memoValidation 为 null", F.data.memoValidation(), null);
restoreData();
t("还原后 memo 回来", F.data.hasMemo(), true);

/* ==================================================================== */
/* 七、两份产物必须同一口径                                              */
/* ==================================================================== */
/* 这两份是 D 的两个出口：统一对象喂页面 1–5，memo 绑定表喂页面 6。
   同一个数在两边长得不一样，读的人会以为其中一处算错了 ——
   这正是 format.js 里 money() 那段注释要防的事，
   所以要有一条断言把它钉住，不能只写在注释里。 */

out.push("\n=== 两份产物口径一致 ===");

const PAIRS = [
  ["营业收入", "revenue", "financials.revenue", F.fmt.metric],
  ["归母净利润", "ni_parent", "financials.net_income_parent", F.fmt.metric],
  ["营业成本", "operating_cost", "financials.operating_cost", F.fmt.metric],
  ["经营活动现金流净额", "ocf", "financials.cfo", F.fmt.metric]
];

PAIRS.forEach(function (p) {
  const mine = p[3](F.data.item(p[2]));
  const theirs = F.data.memoValue(p[1]);
  t("页面2 与页面6 同口径：" + p[0], theirs === null ? "memo 未绑（跳过）" : mine,
    theirs === null ? "memo 未绑（跳过）" : theirs);
});

/* 百分比这一档曾经**没对上**：D 的 memo 写 2 位（"34.46%"），
   E 的 fmt.percent 写 1 位（"34.5%"）。两边都不算错，是两种读者习惯。
   ★ 2026-10-13 定案：**E 往 D 靠**（理由写在 format.js 的 percent 注释里 ——
   D 是口径的生产方）。于是这条从「已知差异」翻面成**一致性断言**：
   同一个 ROE 在页面 2/3 和页面 6 必须长得一模一样。
   它现在也在守反方向 —— 谁哪天单方面把精度调回 1 位，这里立刻红。 */
const memoRoe = F.data.memoValue("roe");
/* ★ 注意这里不能用 fmt.metric：D 的 unit 是 小数，而「小数」是混装桶
   （既可能是比率也可能是倍数），fmt.metric 分不出该不该 ×100。
   比率的百分数化由 dataLoader 的 ratioValue() 按 RATIO_META 逐条声明 ——
   页面 3 走的就是它，所以这里也必须走它，否则验的不是同一条路径。 */
const myRoe = F.data.ratioValue("roe_weighted", F.data.item("ratios.profitability.roe_weighted"));
t("百分比精度：两页同口径（ROE 页面3 == 页面6）", myRoe, memoRoe);
t("百分比精度：统一到 2 位小数", /^-?\d+\.\d{2}%$/.test(memoRoe), true);

/* 每股市值这类标量，D 不带 unit 字段 —— 单位由页面 6 的标签承担。
   这里断言的是「D 确实没给 unit」，好让 E 的硬编码有据可依；
   哪天 D 补了 unit，这条会红，届时页面 6 可以收掉一半硬编码。 */
t("每股标量不带单位（单位由页面标签承担）",
  sandbox.FINSCOPE_MEMO.scalars.some(s => s.placeholder === "blended_ps" && s.unit === undefined), true);
t("估值区间带货币单位（这才是每股单位的权威出处）",
  F.data.get("valuation.dcf.valuation_range.currency"), "元/股");

console.log(out.join("\n"));
console.log(`\n通过 ${pass}/${total}`);
process.exit(pass === total ? 0 : 1);
