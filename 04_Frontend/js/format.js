/* ============================================================================
 * format.js —— 全站统一口径
 * ----------------------------------------------------------------------------
 * 这个文件存在的唯一目的：同一个数在全站长得一模一样。
 * 不允许任何页面自己拼字符串（如 value + "亿元"），一律调用这里的函数。
 *
 * 三条约定（与 D / B / C 对齐，写进 INTERFACE_CONTRACT.md）：
 *   1. 金额一律以「亿元」为单位显示；
 *   2. 百分数一律用小数表示：0.184 代表 18.4%（前端负责 ×100 显示）；
 *   3. 缺失值一律传 null，不要传 ""、0、"N/A" —— 0 是有效值，不能当缺失。
 *
 * ★ 2026-10-13 对齐 D 的真实数据后，上面第 1、2 条各有一个现实修正：
 *
 *   1'. D 的 financials 单位是 **"元"**（原始元，如 168838102514.79），
 *       不是亿元。所以 money() 改成**认单位**：元 / 万元 / 亿元 一律归一到
 *       亿元再显示。这不是「E 重算数据」—— 单位换算是显示刻度，
 *       与画柱状图要算坐标同类。而且 D 自己的投研简报就是按亿元写的
 *       （memo.json 里 revenue = "1,688.38 亿元"），E 只是跟 D 的口径一致。
 *
 *   2'. D 比率的 unit 有四类：**"小数" / "倍" / "次" / "天"**。
 *       其中 "小数" 是个**混装桶** —— 它同时装着「该显示成百分数的」
 *       （gross_margin 0.9118）和「本来就是倍数的」（equity_multiplier 1.242）。
 *       光看 unit 分不出来。所以百分数化这件事改由 dataLoader 的
 *       RATIO_META 按指标逐条声明（那是呈现决定），这里只提供工具函数。
 *
 * 两套颜色系统（勿混用，见 css/base.css 注释）：
 *   tone()   —— 数值方向（涨/跌），A股惯例红涨绿跌；
 *   status   —— 财务健康度（good/watch/bad），绿/黄/红。
 *   本项目以诊断为主，主色调走 status 系统；tone 仅在必要时使用。
 * ==========================================================================*/

(function () {
  "use strict";

  window.FinScope = window.FinScope || {};

  /* 缺失值的统一显示符号：破折号。改这里 = 改全站 */
  var MISSING = "—";

  /* ------------------------------------------------------------------ */
  /* 基础判断                                                            */
  /* ------------------------------------------------------------------ */

  function isNil(v) {
    return v === null || v === undefined || v === "";
  }

  /* 判断是否是「带元信息的数据项」，即 { value, unit, period, ... } */
  function isItem(v) {
    return !!v && typeof v === "object" && !Array.isArray(v) && "value" in v;
  }

  /* 取出裸值：传数据项取 .value，传裸值原样返回 */
  function raw(v) {
    return isItem(v) ? v.value : v;
  }

  /* 取单位：传数据项取 .unit，否则返回默认值 */
  function unitOf(v, dflt) {
    return isItem(v) && v.unit ? v.unit : (dflt || "");
  }

  function toNum(v) {
    var x = raw(v);
    if (isNil(x)) return null;
    if (typeof x === "number") return isFinite(x) ? x : null;
    var n = Number(String(x).replace(/[,\s%]/g, ""));
    return isFinite(n) ? n : null;
  }

  /* ------------------------------------------------------------------ */
  /* 格式化                                                              */
  /* ------------------------------------------------------------------ */

  /* 补零小数位 */
  function fix(n, digits) {
    return Number(n).toFixed(digits === undefined ? 1 : digits);
  }

  /* 千分位：1688.38 → "1,688.38"。只加给整数部分的**四位及以上**，
     三位数不加（"128.6" 不是 "128.6"→"128.6"，"999" 也不该变 "999"）。
     ★ 2026-10-13 新增，起因见 money() 的注释。 */
  function group(s) {
    var parts = String(s).split(".");
    var sign = "";
    var int = parts[0];
    if (int.charAt(0) === "-") { sign = "-"; int = int.slice(1); }
    if (int.length <= 3) return parts.length > 1 ? sign + int + "." + parts[1] : sign + int;
    int = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.length > 1 ? sign + int + "." + parts[1] : sign + int;
  }

  /* 金额：128.6 → "128.6 亿元"
     认单位：元 / 万元 会先归一到亿元再显示（见文件头 1'）。

     小数位**按来源单位分档**，这不是随手定的 —— 两个上游各有各的写法：
       · 亿元量级（mock 数据、页面里的同比口径）用 1 位，够读；
       · 原始元换算过来的用 2 位。D 的 memo 里 168838102514.79 写作
         "1,688.38 亿元"，E 跟着它，否则同一个数在页面 2 和页面 6 上
         会显示成两个精度，读的人会以为其中一处算错了。

     ★ 2026-10-13：这句「跟着它」原来只兑现了一半 —— 位数对了，
       千分位没跟上（E 出 "1688.38 亿元"，页面 6 出 "1,688.38 亿元"）。
       同一个数在两页上长得不一样，正是上面这句话要防的事，所以补上 group()。
       千分位只加给金额：它是**万位起跳**的数（亿元量级动辄四位数），
       而百分比、倍数、天数都是两三位，加了只是噪声。 */
  function money(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;

    var unit = unitOf(v, "亿元") || "亿元";
    var scale = 1;
    if (unit === "元") scale = 1e8;
    else if (unit === "万元") scale = 1e4;

    var d = digits === undefined ? (scale === 1 ? 1 : 2) : digits;
    return group(fix(n / scale, d)) + " 亿元";
  }

  /* 每股价格：1431.3033 → "1,431.30 元/股"。
     ★ 2026-10-13 新增：页面 5 通篇是「每股多少元」—— 融合每股价值、现价、
     两条估值区间、倍数法推出来的每股价值、三情景、敏感性矩阵。
     它们以前各自拼字符串（fmt.num(v,2) 后手工接单位），小数位与千分位
     三处不一致。收进这里，跟 money() 一个道理：单位口径归 format.js 管。

     千分位对它比对金额更要紧：DCF 区间上限 24,654.14 元/股，不加分隔符
     读的人要数位数。默认 2 位小数 —— A 股报价就是 2 位，
     而 D 的原始值给到 4 位（1431.3033），多出来的两位是计算过程，不是报价。 */
  function price(v, digits, unit) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return group(fix(n, digits === undefined ? 2 : digits)) + " " + (unit || "元/股");
  }

  /* 只补千分位、不接单位：给表格和矩阵的单元格用（单位在表头写一次就够）。
     fmt.group(fmt.num(24654.1353, 2)) → "24,654.14" */
  function grouped(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return group(fix(n, digits === undefined ? 2 : digits));
  }

  /* 百分数：0.184 → "18.40%"（自动 ×100）
     ★ 2026-10-13：小数位从 1 位改到 **2 位**。这不是调美观，是消掉一处**同数不同形**：
       D 的 memo 一律写 2 位（"13.33%" / "34.46%" / "-1.21%" / "50.00%"），
       E 的页面写 1 位（"13.3%" / "34.5%"）。同一个 ROE 在页面 2 和页面 6 上
       长得不一样 —— 跟 money() 的千分位是同一类毛病（见那边的注释）。
       谁跟谁：**E 往 D 靠**。理由是 D 是口径的**生产方**（INTERFACE_CONTRACT.md
       开头就写着「字段名以 D 的为准」），而且 E 这边已经有 money() 为元→亿元
       的换算跟过一次 D（memo 里就是 2 位）。
       ⚠️ 只动 percent / signedPercent 两个函数的**默认值**，不动 fix()：
         fix() 被 num/signed/multiple/times/days 共用，那些的单位是倍/次/天，
         跟百分数不是一回事，一起改会顺手改掉十几种显示。 */
  function percent(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return fix(n * 100, digits === undefined ? 2 : digits) + "%";
  }

  /* 倍数：1.62 → "1.62 倍" */
  function multiple(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return fix(n, digits === undefined ? 2 : digits) + " 倍";
  }

  /* 次数：3.32 → "3.32 次" */
  function times(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return fix(n, digits === undefined ? 2 : digits) + " 次";
  }

  /* 天数：30.49 → "30.49 天"（D 的周转天数用 unit "天"） */
  function days(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return fix(n, digits === undefined ? 2 : digits) + " 天";
  }

  /* 纯数字：按位数补齐 */
  function num(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return fix(n, digits === undefined ? 1 : digits);
  }

  /* ------------------------------------------------------------------ */
  /* 智能分派：给一个数据项，按 unit 自动选格式化函数                      */
  /* 页面里最常用就是它：fmt.metric(data.financials.revenue)              */
  /* ------------------------------------------------------------------ */
  function metric(v) {
    if (isNil(raw(v))) return MISSING;
    var u = unitOf(v, "");
    if (u === "%") return percent(v);
    if (u === "倍") return multiple(v);
    if (u === "次") return times(v);
    if (u === "天") return days(v);
    if (u.indexOf("元") >= 0) return money(v);
    /* "小数" 落在这里 → 显示成裸数字。
       该百分数化的那些由 dataLoader 的 ratioValue() 按 RATIO_META 处理，
       不走这个分派 —— 因为 "小数" 既可能是百分比也可能是倍数，光看 unit 分不出来。 */
    return num(v);
  }

  /* 带正负号：用于同比、净额等有方向的数 */
  function signed(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    var s = fix(Math.abs(n), digits === undefined ? 1 : digits);
    if (n > 0) return "+" + s;
    if (n < 0) return "-" + s;
    return s;
  }

  /* 带正负号的百分数：0.184 → "+18.40%"（同上，跟 D 的 2 位） */
  function signedPercent(v, digits) {
    var n = toNum(v);
    if (n === null) return MISSING;
    return signed(n * 100, digits === undefined ? 2 : digits) + "%";
  }

  /* ------------------------------------------------------------------ */
  /* 颜色语义                                                            */
  /* ------------------------------------------------------------------ */

  /* 数值方向 → CSS 类名（如需涨跌配色时用） */
  function tone(v) {
    var n = toNum(v);
    if (n === null) return "tone-flat";
    if (n > 0) return "tone-up";
    if (n < 0) return "tone-down";
    return "tone-flat";
  }

  /* ★ 上游给的 status → CSS 类名。前端不自己下结论，只翻译。
     ------------------------------------------------------------------
     两套取值并存，因为上游换过口径：

     A. **D 的比值 / 财务状态**（现在的真数据）—— 含义是「**算不算得出来**」，
        不是「好不好」：
          ok              算出来了          → 不着色（正常不必喊）
          not_evaluable   输入缺失，待人工核验 → is-watch（橙 = 需要有人去做点什么）
          not_meaningful  这项对该公司无意义   → 不着色（不是问题，是事实）
          not_applicable  科目本身不存在（如茅台无商誉）→ 不着色
          found           财务科目已抽到      → 不着色

     B. **B 的健康度**（早期契约、mock 数据仍在用）good / watch / bad。
        留着的唯一原因是 data/mock_data.js 还没退役。

     ⚠️ 这里**没有** ok → is-good 的映射，是有意的：
        「算出来了」不等于「好」。把它染成绿色就是 E 替 B 下了判断。
        测试也钉着这条 —— .ratio-row.st-good 必须不存在。 */
  function statusClass(s) {
    if (s === "watch") return "is-watch";          /* B */
    if (s === "bad")   return "is-bad";            /* B */
    if (s === "good")  return "is-good";           /* B */
    if (s === "not_evaluable") return "is-watch";  /* D：唯一需要动作的一档 */
    return "";
  }

  /* 上游给的 status → 中文标签。同样是两套口径并存，见上。
     not_meaningful / not_applicable 都读作「不适用」—— 对读的人来说是同一件事：
     这一格没有数，而且不是数据出错。为什么没有，展开行里说。 */
  function statusLabel(s) {
    if (s === "ok")             return "正常";
    if (s === "not_evaluable")  return "待核验";
    if (s === "not_meaningful") return "不适用";
    if (s === "not_applicable") return "不适用";
    if (s === "found")          return "已提取";
    if (s === "missing")        return "未提取";
    return { good: "健康", watch: "关注", bad: "预警" }[s] || MISSING;
  }

  /* 「这个状态值不值得在版面上占一个胶囊」。
     已抽到 / 正常 的行不挂胶囊 —— 16 行全挂「已提取」等于没挂。
     值的（不适用、待核验）才出来，扫视时也就有了落点。 */
  function statusQuiet(s) {
    return s === "ok" || s === "found" || isNil(s);
  }

  /* ★ 风险等级 → 中文标签。
     两套并存：D 用 high / medium / low（并另给 severity_tag 中文标签），
     早期契约与 mock 数据用 high / attention / normal。
     D 的 severity_tag 已经写好了「重大 / 关注 / 一般」，页面 4 优先直接用它，
     这里的映射只在 severity_tag 缺失时兜底。 */
  function severityLabel(s) {
    return {
      high: "重大", medium: "关注", low: "一般",
      attention: "需关注", normal: "正常"
    }[s] || MISSING;
  }

  /* 风险等级 → CSS 类名。medium 落到 sev-attention（橙），low 落到 sev-normal。
     D 没有比 high 更高的档，也没有「无风险」这一档 —— 未触发的规则
     根本不会出现在 risks[] 里（D 已按 status == "triggered" 过滤）。 */
  function severityClass(s) {
    return {
      high: "sev-high",
      medium: "sev-attention", attention: "sev-attention",
      low: "sev-normal", normal: "sev-normal"
    }[s] || "";
  }

  /* ------------------------------------------------------------------ */
  /* 溯源展示                                                            */
  /* ------------------------------------------------------------------ */

  /* 页码：82 → "P.82" */
  function page(n) {
    return isNil(n) ? MISSING : "P." + n;
  }

  /* 出处：数据项 → "2025年年度报告 P.82" */
  function source(v) {
    if (!isItem(v)) return MISSING;
    var parts = [];
    if (!isNil(v.source)) parts.push(v.source);
    if (!isNil(v.page)) parts.push("P." + v.page);
    return parts.length ? parts.join(" ") : MISSING;
  }

  /* 兜底文本：空值统一显示破折号 */
  function text(v, dflt) {
    if (isNil(v)) return MISSING;
    return String(v);
  }

  window.FinScope.fmt = {
    MISSING: MISSING,
    isNil: isNil,
    isItem: isItem,
    raw: raw,
    unitOf: unitOf,
    toNum: toNum,
    num: num,
    group: group,
    grouped: grouped,
    money: money,
    price: price,
    percent: percent,
    multiple: multiple,
    times: times,
    days: days,
    metric: metric,
    signed: signed,
    signedPercent: signedPercent,
    tone: tone,
    statusClass: statusClass,
    statusLabel: statusLabel,
    statusQuiet: statusQuiet,
    severityLabel: severityLabel,
    severityClass: severityClass,
    page: page,
    source: source,
    text: text
  };
})();
