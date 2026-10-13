/* ============================================================================
 * app.js —— 入口 / 调度
 * ----------------------------------------------------------------------------
 * 页面加载后第一个执行的文件，干三件事：
 *   ① 调用 dataLoader 加载数据；
 *   ② 生成左侧导航 + 六段切换路由；
 *   ③ 依次叫六个页面渲染器开工（懒加载：切到哪页才渲染哪页）。
 *
 * 另外在这里提供 FinScope.ui —— 页面共用的 DOM 小工具，
 * 避免六个页面各写一遍建元素的样板代码。
 * ==========================================================================*/

(function () {
  "use strict";

  var F = (window.FinScope = window.FinScope || {});
  F.pages = F.pages || {};

  /* 六个页面的固定顺序（团队分工说明第六节） */
  var ORDER = ["p1", "p2", "p3", "p4", "p5", "p6"];

  /* ==================================================================== */
  /* FinScope.ui —— 建 DOM 的小工具                                        */
  /* ==================================================================== */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  /* 加一个类，**且只在类名非空时才加**。
     ★ 2026-10-13：这个助手是补一次线上报错补出来的 ——
     页面 2 整页白屏，控制台一句
     「Failed to execute 'add' on 'DOMTokenList': The token provided must not be empty.」
     原因是 `classList.add(fmt.statusClass(s))`，而 statusClass 对
     「不需要上色」的那几档（ok / found / not_applicable / not_meaningful）
     正是返回空串 —— 空串不是「什么都不做」，是**抛异常**。
     同理 severityClass 对没映射上的等级也返回空串。

     为什么不把 statusClass 改成返回 null：那个 "" 是有用的信号
     （调用方靠它判断「这一档不上色」），改掉要动好几处。真正该固定的是
     「空类名不能进 classList」这一条 —— 它归 DOM 层管，所以修在这里。
     ⚠️ 别为了省事写成 `n.className += " " + cls`，那会在 cls 为空时
     留下尾随空格，也绕过了下面这种用法的一致性。 */
  function addClass(n, cls) {
    if (cls) n.classList.add(cls);
    return n;
  }

  /* 区块标题：<h2> + 说明 */
  function section(title, desc) {
    var box = el("div", "sec-head");
    box.appendChild(el("h2", "sec-title", title));
    if (desc) box.appendChild(el("p", "sec-desc", desc));
    return box;
  }

  /* 小标题 */
  function subhead(title) {
    return el("h3", "blk-title", title);
  }

  /* "本页待实现" 清单：骨架阶段用来标记进度 */
  function todoList(items) {
    var ul = el("ul", "todo-list");
    items.forEach(function (t) {
      var li = el("li", "todo-item");
      li.appendChild(el("span", "todo-box", "☐"));
      li.appendChild(el("span", "todo-text", t));
      ul.appendChild(li);
    });
    return ul;
  }

  /* 键值对网格：用于数据预览 */
  function kv(pairs) {
    var grid = el("div", "kv-grid");
    pairs.forEach(function (p) {
      var cell = el("div", "kv-cell");
      cell.appendChild(el("div", "kv-key", p[0]));
      var val = el("div", "kv-val" + (p[2] ? " " + p[2] : ""));
      val.textContent = p[1];
      cell.appendChild(val);
      if (p[3]) cell.appendChild(el("div", "kv-note", p[3]));
      grid.appendChild(cell);
    });
    return grid;
  }

  /* 说明条 */
  function note(text, tone) {
    return el("p", "note" + (tone ? " note-" + tone : ""), text);
  }

  /* 空状态 */
  function empty(msg) {
    return el("div", "empty-state", msg);
  }

  /* 通用卡片 */
  /* extraClass 用来挂标记类。目前只有 "dev-card" 一种 ——
     六页的「本页待实现」开发卡靠它被演示模式一次性隐藏。 */
  function card(extraClass) {
    return el("div", "card" + (extraClass ? " " + extraClass : ""));
  }

  /* ---- 2026-10-13 撤：chartBox(canvasId) ----
     它造的是 .chart-box + <canvas>，当年给 Chart.js 的 radar() / trend() 用。
     这两张图早就撤了，全站零调用（唯一的引用是下面 ui 的导出）。
     随 vendor/chart.umd.min.js 与 js/charts.js 一起删。
     ★ 留着想恢复的话：六个页面现在**一张 canvas 都没有**，
       标尺 / 比例条 / 风险区分流都是 DOM + CSS 画的 ——
       恢复 canvas 前先读 css/components.css 里 .vr-track 那段注释
       （为什么当初选了 DOM 而不是 canvas）。 */


  /* ------------------------------------------------------------------ */
  /* 溯源弹窗                                                            */
  /* 金融场景的核心要求：任何一个数字都必须能回答「从哪来」。              */
  /* 点击 .page-link 弹出一个浮层，显示指标、数值、期间、来源文件、章节、页码。 */
  /* 页面上同时只允许存在一个弹窗；点别处或按 ESC 关闭。                   */
  /* ------------------------------------------------------------------ */

  var popoverEl = null;

  function onDocClick(e) {
    if (!popoverEl) return;
    if (popoverEl.contains(e.target)) return;
    // 点在另一个溯源链接上时不关，交给它自己的 click 处理（会先关掉再开新的）
    if (e.target && e.target.closest && e.target.closest(".page-link")) return;
    closePopover();
  }

  function onEsc(e) {
    if (e.key === "Escape") closePopover();
  }

  /* 弹窗用 fixed 定位，不跟随滚动。页面一滚就关掉，避免浮在半空对不上位置。 */
  function onScroll() {
    closePopover();
  }

  function closePopover() {
    if (popoverEl && popoverEl.parentNode) {
      popoverEl.parentNode.removeChild(popoverEl);
    }
    popoverEl = null;
    document.removeEventListener("click", onDocClick, true);
    document.removeEventListener("keydown", onEsc, true);
    window.removeEventListener("scroll", onScroll, true);
  }

  /**
   * 把「出处」解析成一个可跳转的地址，没有就返回 null。
   *
   * ★ 2026-10-13：删掉了最后一段 fallback `company.report_url`。
   *   D 的 company **没有这个字段**（它只有 name / ticker / industry /
   *   report_period / exchange / report_type / auditor / audit_opinion /
   *   currency / amount_unit），而 E 已经从所有页面撤掉对它的消费。
   *   留着一行永远取不到值的 fallback，只会让人以为数据里有年报链接。
   *
   * 取用顺序：来源条目自己的 url → 证据项自己的 url。
   * D 的 sources[] 目前只有 { name, as_of, official, purpose }，没有 url，
   * 所以实际会走 null 分支 —— 浮层照常显示，只是没有链接。这是如实反映：
   * 数据里没有的东西，界面上就不假装有。
   *
   * 页码锚点：url 里已经有 # 就不再追加，避免拼出两个 # 的坏地址。
   * 只有 Chrome 系内置 PDF 阅读器认 #page=N，认不出也只是从第 1 页开始，不会报错。
   */
  function resolveSourceUrl(src, item, page) {
    var url = (src && src.url) || (item && item.url);
    if (!url || typeof url !== "string") return null;
    if (page === null || page === undefined) return url;
    if (url.indexOf("#") >= 0) return url;
    return url + "#page=" + page;
  }

  /** rows: [[键, 值], ...]；link 可选，给了就在底部加一个「打开原文」 */
  function openPopover(anchor, rows, link) {
    closePopover();

    var p = el("div", "popover");
    p.appendChild(el("div", "popover-title", "数据溯源"));

    var body = el("div", "popover-body");
    rows.forEach(function (r) {
      if (r[1] === null || r[1] === undefined || r[1] === "") return;   // 空值不占行
      var line = el("div", "popover-row");
      line.appendChild(el("span", "popover-key", r[0]));
      line.appendChild(el("span", "popover-val", r[1]));
      body.appendChild(line);
    });
    p.appendChild(body);

    if (link && link.href) {
      var a = el("a", "popover-open", link.text || "打开原文 ↗");
      a.href = link.href;
      a.target = "_blank";
      a.rel = "noopener";
      a.addEventListener("click", function (e) { e.stopPropagation(); });
      p.appendChild(a);
    }

    p.appendChild(el("div", "popover-foot", "按 ESC 或点击空白处关闭"));

    document.body.appendChild(p);
    popoverEl = p;

    /* 定位：优先贴在锚点下方，下方放不下就翻到上方，再夹到视口内 */
    var a = anchor.getBoundingClientRect();
    var pw = p.offsetWidth;
    var ph = p.offsetHeight;
    var vw = document.documentElement.clientWidth;
    var vh = document.documentElement.clientHeight;

    var left = a.left;
    if (left + pw > vw - 12) left = vw - pw - 12;
    if (left < 12) left = 12;

    var top = a.bottom + 8;
    if (top + ph > vh - 12) top = a.top - ph - 8;
    if (top < 12) top = 12;

    p.style.left = left + "px";
    p.style.top = top + "px";

    /* 延到下一个事件循环再挂全局监听，
       否则当前这次点击会立刻把刚打开的弹窗关掉 */
    setTimeout(function () {
      document.addEventListener("click", onDocClick, true);
      document.addEventListener("keydown", onEsc, true);
      window.addEventListener("scroll", onScroll, true);
    }, 0);
  }

  /**
   * 生成一个可点击的溯源链接。
   * @param text 链接文字（如「2025年年度报告 P.82」）
   * @param opts { metric: 中文指标名, page: 页码, item: 数据项对象 }
   */
  function sourceLink(text, opts) {
    opts = opts || {};

    var s = el("span", "page-link", text);
    s.title = "点击查看数据出处";

    s.addEventListener("click", function (e) {
      e.stopPropagation();

      var item = opts.item || null;
      var page = opts.page !== undefined ? opts.page : (item ? item.page : null);
      var src = F.data.findSource(opts.metric, page);

      openPopover(s, [
        ["指标",     opts.metric || null],
        ["数值",     item ? F.fmt.metric(item) : null],
        ["期间",     item ? item.period : null],
        ["来源文件", (src && src.source) || (item && item.source) || null],
        ["章节",     src ? src.section : null],
        ["页码",     F.fmt.page(page)]
      ], {
        href: resolveSourceUrl(src, item, page),
        text: "打开原文 ↗"
      });
    });

    return s;
  }

  F.ui = {
    el: el,
    addClass: addClass,
    section: section,
    subhead: subhead,
    todoList: todoList,
    kv: kv,
    note: note,
    empty: empty,
    card: card,
    sourceLink: sourceLink,
    resolveSourceUrl: resolveSourceUrl,     /* 导出是为了让冒烟测试能覆盖到 */
    closePopover: closePopover
  };

  /* ==================================================================== */
  /* 路由                                                                  */
  /* ==================================================================== */

  var mounted = {};     // 已渲染过的页面
  var current = null;

  function navEl() { return document.getElementById("nav"); }
  function mainEl() { return document.getElementById("main"); }

  /* 生成左侧导航 */
  function buildNav() {
    var nav = navEl();
    if (!nav) return;
    nav.innerHTML = "";

    var brand = el("div", "brand");
    brand.appendChild(el("div", "brand-mark", "FinScope"));
    brand.appendChild(el("div", "brand-sub", "财报理解 · 财务诊断 · 风险识别 · 估值分析"));
    nav.appendChild(brand);

    var ul = el("ul", "nav-list");
    ORDER.forEach(function (id) {
      var p = F.pages[id];
      if (!p) return;

      var li = el("li", "nav-item");
      var a = el("a", "nav-link");
      a.href = "#" + id;
      a.dataset.page = id;

      a.appendChild(el("span", "nav-idx", String(p.index || "").padStart(2, "0")));
      var txt = el("span", "nav-text");
      txt.appendChild(el("span", "nav-title", p.title || id));
      if (p.subtitle) txt.appendChild(el("span", "nav-sub", p.subtitle));
      a.appendChild(txt);

      li.appendChild(a);
      ul.appendChild(li);
    });
    nav.appendChild(ul);

    var foot = el("div", "nav-foot");
    var st = F.data.status();
    foot.appendChild(el("div", "nav-source", "数据源：" + st.sourceName));
    foot.appendChild(el("div", "nav-hint", st.loaded ? "已就绪" : "未就绪"));
    nav.appendChild(foot);
  }

  /* 顶部数据校验提示条 */
  function renderWarnings() {
    var main = mainEl();
    if (!main) return;
    var old = main.querySelector(".warn-bar");
    if (old) old.parentNode.removeChild(old);

    var w = F.data.status().warnings;
    if (!w.length) return;

    var bar = el("div", "warn-bar");
    bar.appendChild(el("div", "warn-title", "数据校验提醒（" + w.length + " 项，不影响页面运行）"));
    var ul = el("ul", "warn-list");
    w.slice(0, 8).forEach(function (m) { ul.appendChild(el("li", null, m)); });
    if (w.length > 8) ul.appendChild(el("li", null, "…… 其余 " + (w.length - 8) + " 项见控制台"));
    bar.appendChild(ul);
    main.insertBefore(bar, main.firstChild);
  }

  /* 确保某页的容器存在，并完成首次渲染 */
  function mount(id) {
    var main = mainEl();
    if (!main) return null;

    var sec = document.getElementById("page-" + id);
    if (!sec) {
      sec = el("section", "page");
      sec.id = "page-" + id;
      main.appendChild(sec);
    }

    var p = F.pages[id];
    if (!p) {
      sec.appendChild(empty("页面模块未加载：" + id));
      return sec;
    }

    if (!mounted[id]) {
      sec.innerHTML = "";
      try {
        p.render(sec);
      } catch (err) {
        sec.innerHTML = "";
        sec.appendChild(empty("渲染出错：" + err.message));
        console.error("[FinScope] 页面 " + id + " 渲染失败", err);
      }
      mounted[id] = true;
    }

    // 每次显示都通知一次，页面可在此 resize 图表
    if (typeof p.onShow === "function") {
      try { p.onShow(sec); } catch (e) { console.warn("[FinScope] onShow 出错", e); }
    }
    return sec;
  }

  /* 切页 */
  function show(id) {
    if (ORDER.indexOf(id) < 0) id = ORDER[0];
    if (id === current) return;

    // 隐藏旧的
    if (current) {
      var old = document.getElementById("page-" + current);
      if (old) old.classList.remove("is-active");
      var oldLink = document.querySelector('.nav-link[data-page="' + current + '"]');
      if (oldLink) oldLink.classList.remove("is-active");
    }

    var sec = mount(id);
    if (sec) sec.classList.add("is-active");

    var link = document.querySelector('.nav-link[data-page="' + id + '"]');
    if (link) link.classList.add("is-active");

    current = id;
    if (mainEl()) mainEl().scrollTop = 0;
    window.scrollTo(0, 0);
  }

  function fromHash() {
    return (location.hash || "").replace(/^#/, "") || ORDER[0];
  }

  /* ==================================================================== */
  /* 启动                                                                  */
  /* ==================================================================== */

  function boot() {
    // ⓪ 演示模式。打包前把 index.html 里的 window.FINSCOPE_DEMO 改成 true，
    //    六页的「本页待实现」开发卡会一起隐藏。**不删 DOM** ——
    //    测试与开发期照常看得见，只是演示时不显示。
    if (window.FINSCOPE_DEMO) document.body.classList.add("app-demo");

    // ① 加载数据。换真数据时只改 index.html 里引用的那个 data/*.js
    F.data.load();

    // ② 建导航
    buildNav();
    renderWarnings();

    // ③ 路由
    window.addEventListener("hashchange", function () { show(fromHash()); });
    show(fromHash());

    // ④ 打印 / 导出 PDF 前，把折叠的证据链全部展开。
    //    否则页面上「高风险已展开、其余折叠」的层级设计会在打印稿里变成半截内容。
    function expandAll() {
      var nodes = document.querySelectorAll(".risk-card:not(.is-open)");
      for (var i = 0; i < nodes.length; i++) {
        var btn = nodes[i].querySelector(".risk-toggle");
        if (btn) btn.click();            // 走正常交互，保证按钮文案同步
        else nodes[i].classList.add("is-open");
      }
    }
    window.addEventListener("beforeprint", expandAll);
    // Chrome 下 beforeprint 在部分场景不触发，用媒体查询监听兜底
    if (window.matchMedia) {
      var mq = window.matchMedia("print");
      var onMq = function (e) { if (e.matches) expandAll(); };
      if (mq.addEventListener) mq.addEventListener("change", onMq);
      else if (mq.addListener) mq.addListener(onMq);
    }

    console.log(
      "%cFinScope 前端骨架已启动",
      "color:#4a6785;font-weight:bold",
      "\n数据源：" + F.data.status().sourceName,
      "\n校验提醒：" + F.data.status().warnings.length + " 项",
      "\n演示模式：" + (window.FINSCOPE_DEMO ? "开（开发卡已隐藏）" : "关（开发卡可见）")
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
