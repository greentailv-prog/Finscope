#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 B_demo_dashboard.html —— 单文件可视化看板（数据内嵌，双击即开，无需联网）。

用法:
  # 合成样本（默认）
  python3 scripts_build_dashboard.py

  # 真实案例：工商银行
  python3 scripts_build_dashboard.py \
      --diag cases/icbc-601398/output_ratios.json \
      --risk cases/icbc-601398/output_risks.json \
      --out  cases/icbc-601398/dashboard.html \
      --note real
"""
import argparse
import io
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(description="生成 FinRadar B 模块可视化看板")
ap.add_argument("--diag", default=os.path.join("financial-diagnosis", "demo", "output_ratios.json"))
ap.add_argument("--risk", default=os.path.join("risk-radar", "demo", "output_risks.json"))
ap.add_argument("--rules", default=os.path.join("risk-radar", "risk_rules.json"))
ap.add_argument("-o", "--out", default="B_demo_dashboard.html")
ap.add_argument("--note", choices=["synthetic", "real"], default="synthetic",
                help="页脚数据来源说明口径")
args = ap.parse_args()


def _p(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


diag = json.load(io.open(_p(args.diag), encoding="utf-8"))
risk = json.load(io.open(_p(args.risk), encoding="utf-8"))
rules = json.load(io.open(_p(args.rules), encoding="utf-8"))

def _load_json(path, fallback):
    p = _p(path)
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else fallback


# 会计科目中文名（报表内科目名称）
labels = _load_json(os.path.join("financial-diagnosis", "data", "field_labels.json"),
                    {"fields": {}, "suffix_rules": {}})
# 指标中文名（报表 / 年报披露口径）
metric_labels = _load_json(os.path.join("financial-diagnosis", "data", "metric_labels.json"),
                           {"metrics": {}})

FOOT_NOTE = (
    "本看板数据来自 B 两个引擎的<b>脚本实算结果</b>，非人工填写。"
    "演示所用公司为<b>合成数据</b>（华衍智能装备股份有限公司 DEMO.SH），非任何真实上市公司。"
    "该样本被<b>刻意构造成高风险</b>以最大化规则覆盖——真实公司通常仅触发 3–8 条风险，"
    "此处触发 27 条只说明规则跑通了，不代表典型水平。"
    if args.note == "synthetic" else
    "本看板数据来自 B 两个引擎的<b>脚本实算结果</b>，非人工填写。"
    "年报原文取自<b>巨潮资讯网公开披露文件</b>（工商银行 2023 / 2024 / 2025 年度报告），"
    "所有数值均可按标注的年报页码回溯核对。"
)

data = {
    "diag": diag,
    "risk": risk,
    "categories": rules.get("categories", {}),
    "severity": {k: v for k, v in rules.get("severity_scale", {}).items() if not k.startswith("_")},
    "labels": labels,
    "metricLabels": metric_labels,
    "footNote": FOOT_NOTE,
}

payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
payload = payload.replace("</", "<\\/")  # 防止提前闭合 script 标签

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FinRadar · B 模块演示看板 · 财务诊断与风险雷达</title>
<style>
:root{
  --bg:#f5f6f8; --card:#ffffff; --line:#e4e7ec; --line2:#eef0f3;
  --tx:#16191d; --tx2:#5b6472; --tx3:#8b94a3;
  --blue:#1f4fd8; --blue-l:#eef3ff;
  --red:#d92d20; --red-l:#fef3f2;
  --org:#e07b00; --org-l:#fff8ec;
  --grn:#0e9f6e; --grn-l:#ecfdf3;
  --gry:#98a2b3; --gry-l:#f4f6f8;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 72px}
a{color:var(--blue);text-decoration:none}

/* ---------- header ---------- */
.hero{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:24px 26px;margin-bottom:18px}
.hero-top{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;flex-wrap:wrap}
.tag{display:inline-block;font-size:11px;letter-spacing:.08em;color:var(--blue);background:var(--blue-l);
  border:1px solid #d7e2ff;border-radius:5px;padding:3px 9px;font-weight:600;margin-bottom:10px}
h1{font-size:22px;font-weight:700;letter-spacing:-.01em}
.sub{color:var(--tx2);font-size:13px;margin-top:5px}
.meta{display:flex;gap:22px;flex-wrap:wrap;margin-top:16px;padding-top:16px;border-top:1px solid var(--line2)}
.meta div{font-size:12px;color:var(--tx3)}
.meta b{display:block;font-size:15px;color:var(--tx);font-weight:600;margin-top:2px}
.gauge{text-align:center;min-width:132px}
.gauge .num{font-size:40px;font-weight:800;line-height:1;letter-spacing:-.02em}
.gauge .lv{font-size:13px;font-weight:700;margin-top:8px}
.gauge .hint{font-size:11px;color:var(--tx3);margin-top:4px;max-width:190px;line-height:1.5}

/* ---------- nav ---------- */
.nav{display:flex;gap:4px;background:var(--card);border:1px solid var(--line);border-radius:11px;
  padding:5px;margin-bottom:18px;position:sticky;top:12px;z-index:20}
.nav button{flex:1;border:0;background:transparent;padding:9px 6px;border-radius:8px;font-size:13px;
  color:var(--tx2);cursor:pointer;font-weight:600;font-family:inherit;transition:.15s}
.nav button:hover{background:var(--gry-l)}
.nav button.on{background:var(--blue);color:#fff}

/* ---------- generic ---------- */
section{display:none}
section.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:20px;margin-bottom:16px}
.card h2{font-size:15px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:8px}
.card h2 .dot{width:6px;height:6px;border-radius:50%;background:var(--blue)}
.card .desc{font-size:12px;color:var(--tx3);margin-bottom:16px}
.card .warn{background:var(--blue-l);border:1px solid #d5e2ff;border-radius:8px;
  padding:10px 12px;font-size:12px;color:var(--tx2);margin-bottom:16px;line-height:1.65}
.mrow.na{opacity:.55}
.na-tag{font-size:10px;font-weight:700;color:var(--tx3);background:var(--gry-l);
  border:1px solid var(--line);border-radius:4px;padding:1px 6px}
.grid{display:grid;gap:14px}
.g4{grid-template-columns:repeat(4,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
.g5{grid-template-columns:repeat(5,1fr)}
@media(max-width:960px){.g4,.g5,.g2{grid-template-columns:repeat(2,1fr)}}

/* ---------- metric card ---------- */
.mc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.mc .cat{font-size:11px;font-weight:700;letter-spacing:.04em;color:var(--blue);margin-bottom:12px}
.mc .cat.growth{color:#7a5af8}.mc .cat.profitability{color:#0e9f6e}
.mc .cat.solvency{color:#e07b00}.mc .cat.efficiency{color:#1f4fd8}.mc .cat.cashflow_quality{color:#0ba5a5}
.mrow{display:flex;justify-content:space-between;align-items:baseline;padding:7px 0;
  border-top:1px dashed var(--line2);width:100%;background:none;border-left:0;border-right:0;border-bottom:0;
  font-family:inherit;cursor:pointer;text-align:left;border-radius:6px;transition:background .12s}
.mrow:hover{background:var(--blue-l)}
.mrow:first-of-type{border-top:0}
.mrow:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.mrow .k{font-size:12px;color:var(--tx2);display:flex;align-items:center;gap:5px}
.mrow .k::before{content:'▸';font-size:9px;color:var(--tx3);transition:transform .15s}
.mrow[aria-expanded="true"]{background:var(--blue-l)}
.mrow[aria-expanded="true"] .k{color:var(--blue);font-weight:700}
.mrow[aria-expanded="true"] .k::before{transform:rotate(90deg);color:var(--blue)}
.mrow .v{font-variant-numeric:tabular-nums;font-weight:700;font-size:14px}
.mrow .d{font-size:11px;font-variant-numeric:tabular-nums;margin-left:6px;font-weight:600}
.up{color:var(--red)}.dn{color:var(--grn)}.flat{color:var(--tx3)}

/* ---------- 指标详情（点击展开） ---------- */
.mdet{background:var(--blue-l);border:1px solid #d5e2ff;border-radius:9px;
  padding:11px 13px;margin:6px 0 8px;animation:fadeIn .16s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
.mf{margin-bottom:9px}
.mf:last-of-type{margin-bottom:0}
.mdet-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;
  padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid #d5e2ff}
.mdet-h b{font-size:13px;color:var(--tx)}
.mdet-c{font-size:10.5px;color:var(--tx3);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.mf .ml{display:block;font-size:10px;font-weight:700;letter-spacing:.05em;
  color:var(--blue);margin-bottom:4px}
.mf code{display:block;background:#fff;border:1px solid #e0e8ff;border-radius:6px;
  padding:6px 9px;font-size:11.5px;color:var(--tx2);line-height:1.55;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;word-break:break-all}
.mt{width:100%;border-collapse:collapse;font-size:11.5px}
.mt th{text-align:left;font-weight:700;color:var(--tx3);padding:3px 8px 4px 0;
  border-bottom:1px solid #dbe4fb;font-size:10px}
.mt td{padding:3px 8px 3px 0;color:var(--tx2);border-bottom:1px solid #e8eefc;vertical-align:top}
.mt tr:last-child td{border-bottom:0}
.mt .mv{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;color:var(--tx);white-space:nowrap}
.mt .ms{color:var(--tx3);font-size:10.5px;white-space:nowrap}
.mnote{font-size:10.5px;color:var(--tx3);background:#fff;border:1px dashed #d5e2ff;
  border-radius:6px;padding:5px 8px;margin-top:8px;line-height:1.55}

/* ---------- risk summary ---------- */
.sum{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
@media(max-width:960px){.sum{grid-template-columns:repeat(2,1fr)}}
.sc{border:1px solid var(--line);border-radius:11px;padding:14px 16px;background:var(--card)}
.sc .l{font-size:12px;color:var(--tx3)}
.sc .n{font-size:26px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums}
.sc.h .n{color:var(--red)}.sc.m .n{color:var(--org)}.sc.p .n{color:var(--grn)}.sc.x .n{color:var(--gry)}

.bar{display:flex;height:26px;border-radius:7px;overflow:hidden;margin:10px 0 8px;background:var(--line2)}
.bar span{display:block;height:100%}
.legend{display:flex;gap:16px;font-size:11px;color:var(--tx2);flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:-1px}

table{width:100%;border-collapse:collapse;font-size:12px;margin-top:12px}
th{text-align:left;padding:8px 10px;background:var(--gry-l);color:var(--tx2);font-weight:600;
   border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid var(--line2);font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}

/* ---------- risk item ---------- */
.filters{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px}
.filters button{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:6px 13px;
  font-size:12px;color:var(--tx2);cursor:pointer;font-weight:600;font-family:inherit}
.filters button.on{background:var(--tx);border-color:var(--tx);color:#fff}
.ri{border:1px solid var(--line);border-radius:11px;background:var(--card);margin-bottom:9px;overflow:hidden}
.ri.pass{opacity:.62}
.ri-head{display:flex;align-items:center;gap:11px;padding:13px 15px;cursor:pointer;user-select:none}
.ri-head:hover{background:#fafbfc}
.badge{flex:0 0 auto;font-size:11px;font-weight:700;border-radius:5px;padding:3px 8px;white-space:nowrap}
.b-high{background:var(--red-l);color:var(--red);border:1px solid #fda29b}
.b-medium{background:var(--org-l);color:var(--org);border:1px solid #f7d9a0}
.b-low{background:var(--grn-l);color:var(--grn);border:1px solid #a6f4c5}
.b-pass{background:var(--gry-l);color:var(--gry);border:1px solid var(--line)}
.b-ne{background:#f4f6f8;color:var(--tx2);border:1px solid var(--line);border-style:dashed}
.ri-title{flex:1;min-width:0}
.ri-title .t{font-size:13.5px;font-weight:600}
.ri-title .c{font-size:11px;color:var(--tx3);margin-top:1px}
.ri-id{font-size:11px;color:var(--tx3);font-weight:700;flex:0 0 auto}
.arrow{flex:0 0 auto;color:var(--tx3);font-size:11px;transition:transform .18s}
.ri.open .arrow{transform:rotate(90deg)}
.ri-body{display:none;padding:0 15px 16px;border-top:1px solid var(--line2)}
.ri.open .ri-body{display:block}
.expl{background:#fafbfc;border-left:3px solid var(--blue);border-radius:0 7px 7px 0;
  padding:11px 13px;margin:14px 0;font-size:13px;line-height:1.75}
.step{margin:14px 0}
.step .sh{font-size:12px;font-weight:700;color:var(--tx);margin-bottom:7px;display:flex;align-items:center;gap:7px}
.step .sn{width:17px;height:17px;border-radius:4px;background:var(--blue);color:#fff;font-size:10px;
  display:inline-flex;align-items:center;justify-content:center;font-weight:700}
.chips{display:flex;gap:7px;flex-wrap:wrap}
.chip{background:var(--gry-l);border:1px solid var(--line);border-radius:6px;padding:5px 9px;font-size:11.5px}
.chip b{font-weight:700;font-variant-numeric:tabular-nums}
.chip .pg{color:var(--blue);font-weight:600;margin-left:5px}
.fml{background:#0f1729;color:#c8d3e6;border-radius:8px;padding:11px 13px;font-size:12px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-x:auto;line-height:1.7}
.fml .cm{color:#6b7a99}
ul.acts{margin:0;padding-left:17px}
ul.acts li{font-size:12.5px;color:var(--tx2);margin-bottom:5px;line-height:1.65}
.tagline{font-size:11px;color:var(--tx3);margin-top:8px}

/* ---------- attribution ---------- */
.attr{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:960px){.attr{grid-template-columns:1fr}}
.abox{border:1px solid var(--line);border-radius:11px;padding:15px}
.abox h3{font-size:13px;font-weight:700;margin-bottom:3px}
.abox p.h{font-size:11.5px;color:var(--tx3);margin-bottom:12px;line-height:1.6}
.wrow{display:flex;align-items:center;gap:10px;margin-bottom:8px;font-size:12px}
.wrow .wl{flex:0 0 92px;color:var(--tx2)}
.wrow .wb{flex:1;height:19px;background:var(--line2);border-radius:4px;position:relative;overflow:hidden}
.wrow .wf{position:absolute;top:0;height:100%;border-radius:4px}
.wrow .wv{flex:0 0 78px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.cb{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--line2);font-size:12.5px}
.cb:last-child{border-bottom:0}
.cb .ck{color:var(--tx2)}
.cb .cv{font-variant-numeric:tabular-nums;font-weight:700}
.cb.sum-row{border-top:1px solid var(--line);border-bottom:0;margin-top:4px;padding-top:9px;font-weight:700}

/* ---------- 三表勾稽 ---------- */
.kdet-btn{background:none;border:0;padding:0;font-family:inherit;font-size:11.5px;font-weight:700;
  color:var(--blue);cursor:pointer;border-radius:5px;transition:background .12s}
.kdet-btn:hover{background:var(--blue-l)}
.kdet-btn:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.kdet{background:var(--blue-l);border:1px solid #d5e2ff;border-radius:8px;padding:9px 11px;margin-top:7px}
.kdet .cb{border-bottom-color:#e8eefc;font-size:11.5px;padding:4px 0}
.kdet .cb .cv{white-space:nowrap}

/* ---------- queue ---------- */
.q{border:1px solid var(--line);border-left:3px solid var(--org);border-radius:0 9px 9px 0;
  padding:12px 14px;margin-bottom:9px;background:var(--card)}
.q .qt{font-size:13px;font-weight:600}
.q .qr{font-size:12px;color:var(--tx2);margin-top:4px;line-height:1.65}
.q .qs{font-size:11.5px;color:var(--tx3);margin-top:5px}
.empty{padding:26px;text-align:center;color:var(--tx3);font-size:13px;background:var(--gry-l);
  border-radius:10px;border:1px dashed var(--line)}
.foot{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);font-size:11.5px;color:var(--tx3);line-height:1.8}
</style>
</head>
<body>
<div class="wrap">

  <div class="hero">
    <div class="hero-top">
      <div>
        <span class="tag">FinRadar · B 模块</span>
        <h1 id="co-name">—</h1>
        <div class="sub" id="co-sub">—</div>
        <div class="meta" id="co-meta"></div>
      </div>
      <div class="gauge">
        <div class="num" id="g-num">—</div>
        <div class="lv" id="g-lv">—</div>
        <div class="hint" id="g-hint">—</div>
      </div>
    </div>
  </div>

  <div class="nav">
    <button class="on" data-s="s1">指标总览</button>
    <button data-s="s2">风险雷达</button>
    <button data-s="s3">业绩归因</button>
    <button data-s="s5">三表勾稽</button>
    <button data-s="s4">待核验队列</button>
  </div>

  <!-- ============ 1. 指标总览 ============ -->
  <section id="s1" class="on">
    <div class="card">
      <h2><span class="dot"></span>五类财务指标<span id="m-prof" style="font-size:12px;font-weight:600;color:var(--tx3);margin-left:10px"></span></h2>
      <div class="desc">共 <b id="m-count">—</b> 个指标，由 <code>scripts/compute_ratios.py</code> 实算生成。<b>点击任意指标</b>可展开它的计算公式、代入数据与年报出处，逐项复算。</div>
      <div class="warn" id="m-note" style="display:none"></div>
      <div class="grid g5" id="m-grid"></div>
    </div>
  </section>

  <!-- ============ 2. 风险雷达 ============ -->
  <section id="s2">
    <div class="card">
      <h2><span class="dot" style="background:var(--red)"></span>风险概览</h2>
      <div class="desc">规则库 <code>risk_rules.json</code> 共 <b id="r-total">—</b> 条。未触发的规则同样输出，用于证明「查过且无异常」。</div>
      <div class="sum" id="r-sum"></div>
      <div class="bar" id="r-bar"></div>
      <div class="legend">
        <span><i style="background:var(--red)"></i>重大</span>
        <span><i style="background:var(--org)"></i>关注</span>
        <span><i style="background:var(--grn)"></i>通过</span>
        <span><i style="background:var(--gry)"></i>不可评估</span>
      </div>
      <table id="r-cat"><thead><tr><th>类别</th><th>触发</th><th>重大</th><th>关注</th><th>提示</th></tr></thead><tbody></tbody></table>
    </div>

    <div class="card">
      <h2><span class="dot" style="background:var(--org)"></span>风险清单</h2>
      <div class="desc">点击任意一条展开完整证据链：<b>数据 → 计算 → 出处 → 判断 → 归因 → 建议</b>。这是 E 前端「Risk Radar」页面的数据基础。</div>
      <div class="filters" id="filters">
        <button class="on" data-f="all">全部</button>
        <button data-f="high">重大</button>
        <button data-f="medium">关注</button>
        <button data-f="passed">通过</button>
        <button data-f="not_evaluable">不可评估</button>
      </div>
      <div id="r-list"></div>
    </div>
  </section>

  <!-- ============ 3. 业绩归因 ============ -->
  <section id="s3">
    <div class="card">
      <h2><span class="dot" style="background:#7a5af8"></span>三段业绩归因</h2>
      <div class="desc">分工文档要求 B 做「指标变动的原因分析、业绩归因」。三段分别回答：ROE 变动由什么驱动、利润变动由什么驱动、钱去哪了。</div>
      <div class="attr">
        <div class="abox">
          <h3>① 杜邦分解 —— ROE 变动由什么驱动</h3>
          <p class="h">ROE = 净利率 × 总资产周转率 × 权益乘数（平均口径，三项相乘严格闭合）</p>
          <div id="a-dupont"></div>
        </div>
        <div class="abox">
          <h3>② 营业利润桥 —— 利润变动由什么驱动</h3>
          <p class="h">规模效应 + 毛利率效应 + 费用率效应 + 其他 = Δ营业利润（单位：亿元）</p>
          <div id="a-bridge"></div>
        </div>
      </div>
      <div class="abox" style="margin-top:14px">
        <h3>③ 净利润 → 经营现金流桥 —— 利润和现金的缺口从哪来</h3>
        <p class="h">按间接法逐项拆解，最后一项倒轧。单位：亿元</p>
        <div id="a-cash"></div>
      </div>
    </div>
  </section>

  <!-- ============ 4. 待核验队列 ============ -->
  <section id="s4">
    <div class="card">
      <h2><span class="dot" style="background:var(--gry)"></span>待核验队列</h2>
      <div class="desc">所有「算不出来」的项目都停在这里，等待人工确认后重算下游。<b>绝不因为算不出来就默认安全。</b></div>
      <div id="q-list"></div>
    </div>
  </section>

  <!-- ============ 5. 三表勾稽自检 ============ -->
  <section id="s5">
    <div class="card">
      <h2><span class="dot" style="background:#0d9488"></span>三表勾稽自检</h2>
      <div class="desc">
        检验三张报表之间的恒等关系，用来<b>在算指标之前先验证抽取结果是否可信</b>。
        任一项差异超过对应科目绝对值的 <b>1%</b> 即判为不平，进待核验队列。
        <b>B 只负责查出不平，不自动修正</b>——修数归 A。
      </div>
      <div class="sum" id="k-sum"></div>
      <div id="k-list"></div>
    </div>
  </section>

  <div class="foot" id="foot"></div>
</div>

<script id="payload" type="application/json">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('payload').textContent);
  var diag = D.diag, risk = D.risk;
  var R = diag.ratios, S = risk.summary, comp = diag.company, per = diag.period;

  /* ---------- helpers ---------- */
  function fmt(v, unit){
    if(v===null||v===undefined) return '—';
    if(unit==='ratio') return (v*100).toFixed(2)+'%';
    if(unit==='pp')    return (v*100).toFixed(2)+'pp';
    if(unit==='days')  return v.toFixed(1)+' 天';
    if(unit==='x')     return v.toFixed(2)+' 倍';
    if(unit==='CNY')   return (v/1e8).toFixed(2)+' 亿';
    return String(v);
  }
  function delta(e){
    if(e.delta===null||e.delta===undefined) return '';
    var u=e.unit, d=e.delta, t;
    if(u==='ratio') t=(d*100).toFixed(2)+'pp';
    else if(u==='days') t=d.toFixed(1)+'天';
    else if(u==='x') t=d.toFixed(2);
    else if(u==='CNY') t=(d/1e8).toFixed(2)+'亿';
    else t=d.toFixed(2);
    var cls = (d>0?'up':(d<0?'dn':'flat'));
    return '<span class="d '+cls+'">'+(d>0?'▲':(d<0?'▼':'—'))+t+'</span>';
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }

  /* ---------- 中文名解析：会计科目表 + 指标名表，再按后缀规则拆解 ---------- */
  var FIELDS = (D.labels && D.labels.fields) || {};
  var SUF    = (D.labels && D.labels.suffix_rules) || {};
  var MLAB   = (D.metricLabels && D.metricLabels.metrics) || {};
  // 扁平化指标表：'efficiency.dso' -> 'dso'，供变量标签查找
  var FMLAB  = {};
  Object.keys(MLAB).forEach(function(mk){
    var short = mk.split('.').pop();
    if(!(short in FMLAB)) FMLAB[short] = MLAB[mk];
  });

  // 引擎 inputs 里的简写 -> 标准科目字段名（用于回查 evidence 出处）
  var EV_ALIAS = {
    rev:'revenue', ni:'net_income', ni_parent:'net_income_parent',
    ni_ded:'net_income_deducted', cogs:'cost_of_revenue', ar:'accounts_receivable',
    inv:'inventory', ap:'accounts_payable', ta:'total_assets', eq:'equity_parent',
    ibd:'interest_bearing_debt', spread:'net_interest_spread'
  };
  function lookupName(k){
    if(!k) return null;
    if(Object.prototype.hasOwnProperty.call(FIELDS, k)) return FIELDS[k];
    if(Object.prototype.hasOwnProperty.call(FMLAB, k)) return FMLAB[k];
    return null;
  }
  function labelOf(k){
    var hit = lookupName(k);
    if(hit) return hit;
    var base = k, suffix = '', changed = true;
    while(changed){
      changed = false;
      for(var s in SUF){
        if(base.length > s.length && base.slice(-s.length) === s && SUF[s].charAt(0) === '（'){
          base = base.slice(0, -s.length); suffix = SUF[s] + suffix; changed = true; break;
        }
      }
    }
    if(base.slice(0,4) === 'avg_' && SUF['avg_']){
      base = base.slice(4); suffix = SUF['avg_'] + '余额' + suffix;
    }
    return (lookupName(base) || base) + suffix;
  }

  /* ---------- 指标中文名：优先按 '类别.指标' 精确匹配 ---------- */
  function metricLabel(cat, k){
    return MLAB[cat + '.' + k] || MLAB[k] || FIELDS[k] || labelOf(k);
  }

  /* ---------- 公式里的英文变量名翻译成中文科目名 ---------- */
  // 这些是年报里直接印的通用缩写，保留原文更易与报表对照
  var KEEP_EN = {EBIT:1, EBITDA:1, NOPAT:1, WACC:1, ROE:1, ROA:1, ROIC:1, RWA:1, NIM:1};
  function zhFormula(f){
    if(!f) return '—';
    return String(f).replace(/[A-Za-z][A-Za-z0-9_]*(?:-1)?/g, function(t){
      var up = t.toUpperCase();
      if(KEEP_EN[up]) return t;
      // 公式里 t-1 与 inputs 里 _t_1 同义，先归一（Revenue_t-1 -> revenue_t_1）
      var low = t.replace(/-1$/, '_1').toLowerCase();
      var suffix = '', changed = true;
      while(changed){
        changed = false;
        for(var s in SUF){
          if(low.length > s.length && low.slice(-s.length) === s && SUF[s].charAt(0) === '（'){
            low = low.slice(0, -s.length); suffix = SUF[s] + suffix; changed = true; break;
          }
        }
      }
      if(low.slice(0,4) === 'avg_'){ low = low.slice(4); suffix = '平均余额' + suffix; }
      var hit = lookupName(low);
      return hit ? hit + suffix : t;
    });
  }

  /* ---------- 输入值单位推断（inputs 是归一到「元」的数值） ---------- */
  var UFACT = {'元':1,'千元':1e3,'万元':1e4,'百万元':1e6,'百万':1e6,'亿元':1e8,'亿':1e8};
  function inferUnit(k, v){
    if(k === 'days') return '天';
    var base = k.replace(/-1$/, '_1')
                .replace(/(_t_1|_t|_prev|_disclosed)$/, '').replace(/^avg_/, '');
    var ev = diag.evidence && diag.evidence[EV_ALIAS[base] || base];
    var node = ev && (ev[per.current] || ev[per.previous]);
    if(node && node.display_unit && UFACT[node.display_unit]){
      return { unit: node.display_unit, factor: UFACT[node.display_unit] };
    }
    if(v !== null && v !== undefined && Math.abs(v) >= 1e6)
      return { unit: '亿元', factor: 1e8 };
    if(v !== null && v !== undefined && Math.abs(v) <= 1.5)
      return { unit: 'ratio', factor: null };
    return { unit: 'x', factor: null };
  }
  function fmtInput(k, v){
    if(v===null||v===undefined) return '—';
    var u = inferUnit(k, v);
    if(u.unit === '天') return v.toFixed(0)+' 天';
    if(u.factor) return (v/u.factor).toLocaleString('zh-CN',{maximumFractionDigits:2})+' '+u.unit;
    if(u.unit === 'ratio') return (v*100).toFixed(2)+'%';
    return v.toFixed(2)+' 倍';
  }
  function sourceOf(k){
    var base = k.replace(/-1$/, '_1')
                .replace(/(_t_1|_t|_prev|_disclosed)$/, '').replace(/^avg_/, '');
    var ev = diag.evidence && diag.evidence[EV_ALIAS[base] || base];
    if(!ev) return null;
    var node = ev[per.current] || {};
    var pnode = ev[per.previous] || {};
    return { source: node.source || pnode.source, page: node.page !== undefined ? node.page : pnode.page };
  }

  /* ---------- header ---------- */
  document.getElementById('co-name').textContent = comp.name || '—';
  document.getElementById('co-sub').textContent =
    (comp.ticker||'') + ' · ' + (comp.industry||'') + ' · 报告期 ' + (per.current||'') ;
  var rv = diag.evidence && diag.evidence.revenue && diag.evidence.revenue[per.current];
  var np = diag.evidence && diag.evidence.net_income_parent && diag.evidence.net_income_parent[per.current];
  document.getElementById('co-meta').innerHTML =
    '<div>当期营业收入<b>'+ (rv? rv.display_value+' '+rv.display_unit : '—') +'</b></div>' +
    '<div>当期归母净利润<b>'+ (np? np.display_value+' '+np.display_unit : '—') +'</b></div>' +
    '<div>ROE<b>'+fmt(R.profitability.roe.value,'ratio')+'</b></div>' +
    '<div>资产负债率<b>'+fmt(R.solvency.debt_to_assets.value,'ratio')+'</b></div>' +
    '<div>对比期间<b>'+(per.all||[]).join(' / ')+'</b></div>';

  var lv = S.overall_risk_level, sc = S.overall_risk_score;
  var col = (lv==='高')?'var(--red)':(lv==='较高')?'var(--org)':(lv==='中等')?'#7a5af8':'var(--grn)';
  document.getElementById('g-num').textContent = sc.toFixed(1);
  document.getElementById('g-num').style.color = col;
  document.getElementById('g-lv').textContent = '综合风险：' + lv;
  document.getElementById('g-lv').style.color = col;
  document.getElementById('g-hint').textContent = S.suggested_action || '';

  /* ---------- 1. metrics ---------- */
  // 重点指标（卡片顶部固定展示）；其余指标在下方按类别全量列出
  var PICK = {
    growth:[['revenue_growth','营业收入增速'],['net_income_parent_growth','归母净利增速'],
            ['net_income_deducted_growth','扣非净利增速'],['ocf_growth','经营现金流增速'],
            ['profit_revenue_scissors','收入利润剪刀差']],
    profitability:[['gross_margin','毛利率'],['net_margin_parent','归母净利率'],
                   ['roe','ROE'],['roic','ROIC'],['period_expense_ratio','期间费用率'] ],
    solvency:[['debt_to_assets','资产负债率'],['cash_to_short_term_debt','现金/短期有息债'],
              ['interest_coverage','利息保障倍数'],['net_debt_to_ebitda','净负债/EBITDA'],
              ['interest_bearing_debt_ratio','有息负债率']],
    efficiency:[['dso','应收周转天数 DSO'],['dio','存货周转天数 DIO'],
                ['dpo','应付周转天数 DPO'],['cash_conversion_cycle','现金转换周期 CCC'],
                ['total_asset_turnover','总资产周转率']],
    cashflow_quality:[['ocf_to_net_income_parent','净现比'],['sales_cash_ratio','收现比'],
                      ['capex_to_ocf','资本开支/OCF'],['free_cash_flow','自由现金流'],
                      ['ocf_to_interest_paid','OCF/已付利息']]
  };
  // 类别中文名；未在表里出现的类别（如 banking）直接显示 key，并额外补一行说明
  var LBL={growth:'成长性',profitability:'盈利能力',solvency:'偿债能力',
           efficiency:'营运能力',cashflow_quality:'现金流质量',
           banking:'银行业专属',insurance:'保险业专属',brokerage:'券商业专属',
           real_estate:'地产业专属'};

  var mg='', cnt=0, na=0, ok=0;
  for(var c in R){ for(var k in R[c]){ cnt++;
    if(R[c][k] && R[c][k].status==='not_applicable') na++; else if(R[c][k] && R[c][k].value!==null) ok++; } }
  document.getElementById('m-count').textContent = cnt;

  // 覆盖度提示条（兼容两种形态：指标输出里 industry_profile 是字符串 id，
  // 风险输出里是带 label / benchmarks_calibrated 的详细字典）
  var rawProf = diag.industry_profile;
  var profObj = (rawProf && typeof rawProf === 'object')
      ? rawProf
      : ((risk && typeof risk.industry_profile === 'object') ? risk.industry_profile : null);
  var profLabel = (profObj && profObj.label) || null;
  var profCal  = (profObj && typeof profObj.benchmarks_calibrated === 'boolean')
      ? profObj.benchmarks_calibrated : null;

  if(profLabel){
    document.getElementById('m-prof').textContent =
      '· 行业剖面：' + profLabel + (profCal === false ? '（阈值未统计校准）' : '');
  }
  if(na>0){
    var note = '共 ' + cnt + ' 个指标：已算出 <b>' + ok + '</b> 个，'
      + '<b>' + na + '</b> 个因当前行业口径不成立被<b>主动跳过</b>'
      + '（口径不适用，非数据缺失、非算不出来）。';
    if(profLabel){
      note += '当前行业剖面：<b>' + esc(profLabel) + '</b>'
        + (profCal === false ? '，阈值<b>尚未用可比公司分位数统计校准</b>。' : '。');
    }
    document.getElementById('m-note').innerHTML = note;
    document.getElementById('m-note').style.display = 'block';
  }

  // 按 ratios 里实际存在的类别生成卡片（不再写死五类，行业专属类别也会出现）
  Object.keys(R).forEach(function(cat){
    var keys = Object.keys(R[cat]||{});
    if(!keys.length) return;
    var h='<div class="mc"><div class="cat '+(/^[a-z_]+$/.test(cat)?cat:'') +'">'
        + (LBL[cat]||cat) + ' <span style="color:var(--tx3);font-weight:600">'
        + keys.length + ' 个</span></div>';
    keys.forEach(function(k){
      var e = R[cat][k];
      if(!e) return;
      var isNA = (e.status === 'not_applicable');
      h += '<button type="button" class="mrow'+(isNA?' na':'')+'" aria-expanded="false"'
         + ' data-c="'+esc(cat)+'" data-k="'+esc(k)+'">'
         + '<span class="k">'+esc(metricLabel(cat, k))+'</span>'
         + (isNA ? '<span class="na-tag">不适用</span>'
                 : '<span class="v">'+fmt(e.value,e.unit)+delta(e)+'</span>')
         + '</button>';
    });
    h+='</div>'; mg+=h;
  });
  var gridEl = document.getElementById('m-grid');
  gridEl.innerHTML = mg;

  /* ---------- 点击指标行 → 展开公式与数据 ---------- */
  function detailHTML(cat, k){
    var e = (R[cat]||{})[k]; if(!e) return '';
    var inp = e.inputs || {}, inpP = e.inputs_prev || {};
    var h = '<div class="mdet">';
    h += '<div class="mdet-h"><b>' + esc(metricLabel(cat, k)) + '</b>'
       + '<span class="mdet-c">' + esc(k) + '　·　' + esc(LBL[cat] || cat) + '</span></div>';

    h += '<div class="mf"><span class="ml">计算公式</span>'
       + '<code>' + esc(zhFormula(e.formula)) + '</code></div>';

    var ks = Object.keys(inp);
    if(ks.length){
      h += '<div class="mf"><span class="ml">代入数据</span>'
         + '<table class="mt"><thead><tr><th>变量</th><th>本期</th><th>上期</th><th>出处</th></tr></thead><tbody>';
      ks.forEach(function(vk){
        var sv = sourceOf(vk) || {};
        var src = (sv.source || '') + (sv.page !== undefined && sv.page !== null ? (' P' + sv.page) : '');
        h += '<tr><td>'+esc(labelOf(vk))+'</td>'
           + '<td class="mv">'+esc(fmtInput(vk, inp[vk]))+'</td>'
           + '<td class="mv">'+esc((vk in inpP) ? fmtInput(vk, inpP[vk]) : '—')+'</td>'
           + '<td class="ms">'+(src.trim() ? esc(src) : '—')+'</td></tr>';
      });
      h += '</tbody></table></div>';
    }

    h += '<div class="mf"><span class="ml">计算结果</span>'
       + '<table class="mt"><tbody>'
       + '<tr><td>本期（'+esc(per.current)+'）</td><td class="mv">'+esc(fmt(e.value,e.unit))+'</td></tr>'
       + '<tr><td>上期（'+esc(per.previous)+'）</td><td class="mv">'+esc(fmt(e.prev,e.unit))+'</td></tr>'
       + '<tr><td>同比变动</td><td class="mv">'
       + (e.delta === null || e.delta === undefined ? '—'
            : esc((e.delta>0?'▲':(e.delta<0?'▼':'—')) + fmt(Math.abs(e.delta), e.unit==='ratio'?'pp':e.unit)))
       + '</td></tr></tbody></table></div>';

    var dirTxt = e.higher_is_better === true ? '越高越好'
               : (e.higher_is_better === false ? '越低越好' : '无方向性');
    var notes = [];
    notes.push('变动方向：' + dirTxt);
    if(e.unit === 'ratio') notes.push('比率口径：1.00 = 100%');
    if(e.note) notes.push(e.note);
    h += '<div class="mnote">' + esc(notes.join('　·　')) + '</div>';
    h += '</div>';
    return h;
  }

  gridEl.addEventListener('click', function(ev){
    var el = ev.target, row = null;
    while(el && el !== gridEl){
      if(el.classList && el.classList.contains('mrow')){ row = el; break; }
      el = el.parentNode;
    }
    if(!row) return;
    var isOpen = row.getAttribute('aria-expanded') === 'true';
    // 同一张卡片内保持单开，避免页面被撑得过长
    Array.prototype.slice.call(row.parentNode.querySelectorAll('.mrow[aria-expanded="true"]'))
      .forEach(function(x){
        x.setAttribute('aria-expanded','false');
        var p = x.nextSibling;
        if(p && p.className === 'mdet') p.parentNode.removeChild(p);
      });
    if(isOpen) return;
    row.setAttribute('aria-expanded','true');
    row.insertAdjacentHTML('afterend', detailHTML(row.getAttribute('data-c'), row.getAttribute('data-k')));
  });

  /* ---------- 2. risk summary ---------- */
  var bs=S.by_severity;
  document.getElementById('r-total').textContent = S.total_rules;
  document.getElementById('r-sum').innerHTML =
    '<div class="sc h"><div class="l">重大</div><div class="n">'+bs.high+'</div></div>'+
    '<div class="sc m"><div class="l">关注</div><div class="n">'+bs.medium+'</div></div>'+
    '<div class="sc x"><div class="l">提示</div><div class="n">'+bs.low+'</div></div>'+
    '<div class="sc p"><div class="l">通过 / 不可评估</div><div class="n">'+S.passed+' / '+S.not_evaluable+'</div></div>';
  var t=S.total_rules, seg=function(n,col){return '<span style="width:'+(n/t*100)+'%;background:'+col+'"></span>';};
  document.getElementById('r-bar').innerHTML =
    seg(bs.high,'var(--red)')+seg(bs.medium,'var(--org)')+seg(bs.low,'#a6f4c5')+
    seg(S.passed,'#c9d4e5')+seg(S.not_evaluable,'#e4e7ec');
  var tb='';
  Object.keys(S.by_category).forEach(function(c){
    var v=S.by_category[c];
    tb+='<tr><td>'+(D.categories[c]?D.categories[c].split('：')[0]:c)+'</td><td><b>'+v.triggered+'</b></td><td>'+v.high+'</td><td>'+v.medium+'</td><td>'+v.low+'</td></tr>';
  });
  document.getElementById('r-cat').querySelector('tbody').innerHTML=tb;

  /* ---------- risk list ---------- */
  var SEV={high:'重大',medium:'关注',low:'提示'};
  function chainHtml(ch){
    var h='';
    var sIdx = 0;
    ch.forEach(function(s){
      sIdx++;
      h+='<div class="step"><div class="sh"><span class="sn">'+sIdx+'</span>'+esc(s.step)+'</div>';
      if(s.step==='数据'){
        h+='<div class="chips">'+ '<div class="chip">'+esc(s.item)+' <b>'+s.value+' '+s.unit+'</b>'
          + (s.prev_value!==null&&s.prev_value!==undefined?' <span style="color:var(--tx3)">上期 '+s.prev_value+'</span>':'')
          + '<span class="pg">'+esc(s.source||'')+' P'+s.page+'</span></div></div>';
      } else if(s.step==='计算'){
        h+='<div class="fml"><span class="cm">// 触发表达式</span><br>'+esc(s.formula)+'<br><br>'
          +'<span class="cm">// 变量实际值</span><br>';
        for(var k in s.values){ h+=esc(k)+' = <b>'+s.values[k]+'</b><br>'; }
        h+='</div>';
      } else if(s.step==='出处'){
        h+='<div class="chips">';
        (s.sources||[]).forEach(function(x){ h+='<div class="chip">'+esc(x)+'</div>'; });
        (s.pages||[]).forEach(function(p){ h+='<div class="chip">第 '+p+' 页</div>'; });
        h+='</div>';
      } else if(s.step==='判断'){
        h+='<div class="chips"><div class="chip">'+esc(s.item)+'</div><div class="chip">结果：<b>'+esc(s.result)+'</b></div></div>';
      } else if(s.step==='归因'){
        var d=s.dupont, b=s.operating_profit_bridge_yi;
        h+='<div style="font-size:12px;line-height:1.9">';
        if(d){ h+='<b>杜邦分解（ROE 变动 '+(d.roe_delta*100).toFixed(2)+'pp）</b><br>'
          +'净利率效应 <b>'+(d.net_margin_effect*100).toFixed(2)+'pp</b>　'
          +'周转率效应 <b>'+(d.asset_turnover_effect*100).toFixed(2)+'pp</b>　'
          +'杠杆效应 <b>'+(d.leverage_effect*100).toFixed(2)+'pp</b><br>'; }
        if(b){ h+='<br><b>营业利润桥（Δ营业利润 '+b.delta_operating_profit+' 亿元）</b><br>'
          +'规模效应 <b>'+b.scale_effect+'</b>　毛利率效应 <b>'+b.gross_margin_effect+'</b><br>'
          +'费用率效应 <b>'+b.expense_ratio_effect+'</b>　其他 <b>'+b.other_effect+'</b><br>'; }
        if(s.cash_gap_yi!==null&&s.cash_gap_yi!==undefined){ h+='<br>利润与现金缺口 <b>'+s.cash_gap_yi+' 亿元</b>'; }
        h+='</div>';
      } else if(s.step==='建议'){
        h+='<ul class="acts">'; (s.actions||[]).forEach(function(a){ h+='<li>'+esc(a)+'</li>'; }); h+='</ul>';
      }
      h+='</div>';
    });
    return h;
  }
  var order={high:0,medium:1,low:2};
  var list=risk.risks.slice().sort(function(a,b){
    if(a.status!==b.status){ return (a.status==='triggered'?-1:1); }
    if(a.status==='triggered'){ return (order[a.severity]-order[b.severity]) || (b.score-a.score); }
    return a.risk_id<b.risk_id?-1:1;
  });
  var lh='';
  list.forEach(function(r){
    var sev = r.status==='triggered' ? r.severity : r.status;
    var badge = r.status==='triggered'
      ? '<span class="badge b-'+r.severity+'">'+SEV[r.severity]+' '+r.score+'</span>'
      : (r.status==='passed' ? '<span class="badge b-pass">通过</span>' : '<span class="badge b-ne">不可评估</span>');
    lh+='<div class="ri '+(r.status==='passed'?'pass':'')+'" data-sev="'+sev+'">'
      + '<div class="ri-head"><span class="arrow">▶</span>'+badge
      + '<div class="ri-title"><div class="t">'+esc(r.risk_name)+'</div>'
      + '<div class="c">'+esc(r.category_label||'')+'</div></div>'
      + '<span class="ri-id">'+esc(r.risk_id)+'</span></div>'
      + '<div class="ri-body">';
    lh+='<div class="expl">'+esc(r.explanation)+'</div>';
    if(r.trigger_display){
      lh+='<div class="step"><div class="sh"><span class="sn">!</span>触发条件</div>'
        +'<div class="chips"><div class="chip">'+esc(r.trigger_display)+'</div>'
        +'<div class="chip">表达式：<b style="font-family:ui-monospace,Menlo,monospace">'+esc(r.trigger)+'</b></div></div></div>';
    }
    if(r.evidence_chain && r.evidence_chain.length) lh+=chainHtml(r.evidence_chain);
    else lh+='<div class="tagline">本条无证据链（未触发或输入缺失）。</div>';
    lh+='</div></div>';
  });
  document.getElementById('r-list').innerHTML=lh;

  document.getElementById('r-list').addEventListener('click',function(e){
    var h=e.target.closest('.ri-head'); if(!h) return;
    h.parentNode.classList.toggle('open');
  });
  document.getElementById('filters').addEventListener('click',function(e){
    var b=e.target.closest('button'); if(!b) return;
    [].forEach.call(this.querySelectorAll('button'),function(x){x.classList.remove('on');});
    b.classList.add('on');
    var f=b.getAttribute('data-f');
    [].forEach.call(document.querySelectorAll('#r-list .ri'),function(it){
      it.style.display = (f==='all'||it.getAttribute('data-sev')===f)?'':'none';
    });
  });

  /* ---------- 3. attribution ---------- */
  var A=diag.attribution;
  var dp=A.dupont.contribution, mx=0;
  [dp.net_margin_effect,dp.asset_turnover_effect,dp.leverage_effect].forEach(function(v){ mx=Math.max(mx,Math.abs(v)); });
  function wbar(lbl,v){
    var w=Math.abs(v)/mx*100, pos=v>=0;
    return '<div class="wrow"><span class="wl">'+lbl+'</span>'
      +'<span class="wb"><span class="wf" style="left:'+(pos?50:50-w/2)+'%;width:'+w/2+'%;background:'+(pos?'var(--red)':'var(--grn)')+'"></span></span>'
      +'<span class="wv" style="color:'+(pos?'var(--red)':'var(--grn)')+'">'+(v*100).toFixed(2)+'pp</span></div>';
  }
  document.getElementById('a-dupont').innerHTML =
    wbar('净利率效应',dp.net_margin_effect)
    + wbar('周转率效应',dp.asset_turnover_effect)
    + wbar('杠杆效应',dp.leverage_effect)
    + '<div class="cb sum-row"><span class="ck">ROE 变动合计</span><span class="cv">'
    + (dp.roe_delta*100).toFixed(2)+'pp （'+ (A.dupont.previous.roe*100).toFixed(2)+'% → '+(A.dupont.current.roe*100).toFixed(2)+'%）</span></div>';

  var B=A.operating_profit_bridge, bmx=0;
  ['scale_effect','gross_margin_effect','expense_ratio_effect','other_effect'].forEach(function(k){ bmx=Math.max(bmx,Math.abs(B[k])); });
  var bl={scale_effect:'规模效应',gross_margin_effect:'毛利率效应',expense_ratio_effect:'费用率效应',other_effect:'其他（残差）'};
  var bh='';
  ['scale_effect','gross_margin_effect','expense_ratio_effect','other_effect'].forEach(function(k){
    var v=B[k]/1e8, w=Math.abs(v)/(bmx/1e8)*100;
    bh+='<div class="wrow"><span class="wl">'+bl[k]+'</span>'
      +'<span class="wb"><span class="wf" style="left:'+(v>=0?50:50-w/2)+'%;width:'+w/2+'%;background:'+(v>=0?'var(--red)':'var(--grn)')+'"></span></span>'
      +'<span class="wv" style="color:'+(v>=0?'var(--red)':'var(--grn)')+'">'+v.toFixed(2)+' 亿</span></div>';
  });
  bh+='<div class="cb sum-row"><span class="ck">营业利润变动合计</span><span class="cv">'
     +(B.delta_operating_profit/1e8).toFixed(2)+' 亿元</span></div>';
  document.getElementById('a-bridge').innerHTML=bh;

  var C=A.cash_flow_bridge, ch='';
  (C.items||[]).forEach(function(it){
    var v=(it.amount||0)/1e8;
    ch+='<div class="cb"><span class="ck">'+esc(it.item)+'</span><span class="cv" style="color:'+(v>=0?'var(--red)':'var(--grn)')+'">'
      +(v>=0?'+':'')+v.toFixed(2)+' 亿</span></div>';
  });
  ch+='<div class="cb sum-row"><span class="ck">净利润 → 经营现金流缺口</span><span class="cv">'
    +(C.gap/1e8).toFixed(2)+' 亿元</span></div>';
  document.getElementById('a-cash').innerHTML=ch;

  /* ---------- 5. 三表勾稽自检 ---------- */
  var CK = diag.checks || {items:[], summary:{}, overall:'not_evaluable'};
  var CK_TAG = {balanced:{t:'平衡', c:'b-pass'},
                imbalanced:{t:'不平', c:'b-high'},
                not_evaluable:{t:'无法勾稽', c:'b-ne'}};
  var ks = CK.summary || {};
  var overallTag = CK_TAG[CK.overall] || CK_TAG.not_evaluable;
  document.getElementById('k-sum').innerHTML =
      '<div class="sc '+(CK.overall==='imbalanced'?'h':'p')+'">'
        + '<div class="l">勾稽结论</div><div class="n" style="font-size:20px">'+esc(overallTag.t)+'</div></div>'
    + '<div class="sc"><div class="l">检查项</div><div class="n">'+(ks.total||0)+'</div></div>'
    + '<div class="sc p"><div class="l">平衡</div><div class="n">'+(ks.balanced||0)+'</div></div>'
    + '<div class="sc h"><div class="l">不平</div><div class="n">'+(ks.imbalanced||0)+'</div></div>'
    + '<div class="sc x"><div class="l">无法勾稽</div><div class="n">'+(ks.not_evaluable||0)+'</div></div>';

  // 统一以「亿元」呈现，带千分位；勾稽差异通常是 0，用 0.00 而非「—」更明确
  function yi(v){
    if(v===null||v===undefined) return '—';
    return (v/1e8).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2});
  }
  var kh='<table><thead><tr><th style="width:24%">勾稽关系</th><th style="width:9%">期间</th>'
       + '<th style="width:8%">结论</th><th style="width:11%">左值（亿元）</th><th style="width:11%">右值（亿元）</th>'
       + '<th style="width:10%">差异</th><th>说明 / 代入数据</th></tr></thead><tbody>';
  (CK.items||[]).forEach(function(it, ix){
    var tg = CK_TAG[it.status] || {t:it.status, c:'b-ne'};
    var dp = (it.diff_pct===null||it.diff_pct===undefined)
        ? '—' : (it.diff_pct*100).toFixed(3)+'%';
    // 代入数据表：本期各科目取值 + 出处
    var rows='';
    Object.keys(it.inputs||{}).forEach(function(vk){
      var nd = it.inputs[vk] || {};
      // 直取科目用年报原文口径（display_value + display_unit）；
      // 倒轧科目没有原文口径，value 已归一到「元」，转「亿元」需 /1e8。
      var dv = (nd.display_value!==null && nd.display_value!==undefined)
              ? nd.display_value
              : (nd.value===null||nd.value===undefined ? null : nd.value/1e8);
      var du = nd.display_unit || nd.unit || '';
      var val = (dv===null||dv===undefined) ? '—'
              : (typeof dv === 'number' ? dv.toLocaleString('zh-CN') : String(dv));
      var src = nd.derived ? ('倒轧：'+(nd.derived_from||''))
                           : ((nd.source||'—') + (nd.page!==null&&nd.page!==undefined ? (' P'+nd.page) : ''));
      rows += '<div class="cb"><span class="ck">'+esc(vk)+'</span>'
            + '<span class="cv">'+esc(val)+(du?(' '+esc(du)):'')
            + ' <span class="pg">'+esc(src)+'</span></span></div>';
    });
    kh += '<tr><td><b>'+esc(it.name)+'</b><br><span style="font-size:11px;color:var(--tx2)">'
        + esc(it.formula) + '</span></td>'
        + '<td>'+esc(it.period)+'</td>'
        + '<td><span class="badge '+tg.c+'">'+esc(tg.t)+'</span></td>'
        + '<td>'+yi(it.left)+'</td><td>'+yi(it.right)+'</td>'
        + '<td>'+yi(it.diff)+'<br><span style="font-size:11px;color:var(--tx3)">'+dp+'</span></td>'
        + '<td>'
        + (it.note ? '<div style="font-size:11.5px;color:var(--org);margin-bottom:6px">'+esc(it.note)+'</div>' : '')
        + '<button type="button" class="kdet-btn" data-i="'+ix+'" aria-expanded="false">▸ 查看代入数据</button>'
        + '<div class="kdet" id="kdet-'+ix+'" style="display:none">'+rows
        + '<div style="font-size:10.5px;color:var(--tx3);margin-top:6px">表达式：'
        + '<span style="font-family:ui-monospace,Menlo,monospace">'+esc(it.formula_symbolic)+'</span></div>'
        + '</div></td></tr>';
  });
  kh += '</tbody></table>';
  kh += '<div class="desc" style="margin-top:10px">容差口径：'
      + esc(CK.tolerance_basis||'') + '　｜　处置口径：' + esc(CK.policy||'') + '</div>';
  var klist = document.getElementById('k-list');
  klist.innerHTML = kh;
  klist.addEventListener('click', function(e){
    var b = e.target.closest('.kdet-btn'); if(!b) return;
    var box = document.getElementById('kdet-' + b.getAttribute('data-i'));
    var open = b.getAttribute('aria-expanded') === 'true';
    b.setAttribute('aria-expanded', open ? 'false' : 'true');
    b.textContent = open ? '▸ 查看代入数据' : '▾ 收起代入数据';
    box.style.display = open ? 'none' : 'block';
  });

  /* ---------- 4. queue ---------- */
  var qh='';
  (risk.review_queue||[]).forEach(function(q){
    qh+='<div class="q"><div class="qt">'+esc(q.item)+'</div>'
      +'<div class="qr"><b>'+esc(q.reason)+'</b>'+(q.missing_inputs&&q.missing_inputs.length?'（缺失：'+esc(q.missing_inputs.join('、'))+'）':'')+'</div>'
      +'<div class="qs">建议动作：'+esc(q.suggested_action||'—')
      +(q.inherited_from?'　｜　来源：'+esc(q.inherited_from):'')
      +(q.needs_human_judgement?'　｜　<b style="color:var(--org)">需人工判断</b>':'')+'</div></div>';
  });
  document.getElementById('q-list').innerHTML = qh ||
    '<div class="empty">待核验队列为空 —— 所有指标与规则均可计算。</div>';

  /* ---------- nav ---------- */
  document.querySelector('.nav').addEventListener('click',function(e){
    var b=e.target.closest('button'); if(!b) return;
    [].forEach.call(this.querySelectorAll('button'),function(x){x.classList.remove('on');});
    b.classList.add('on');
    [].forEach.call(document.querySelectorAll('section'),function(s){s.classList.remove('on');});
    document.getElementById(b.getAttribute('data-s')).classList.add('on');
    window.scrollTo({top:0,behavior:'smooth'});
  });

  /* ---------- foot ---------- */
  document.getElementById('foot').innerHTML =
    'FinRadar（财报雷达）· B 模块演示看板　｜　' + esc(risk.generator||'') + '　｜　生成时间 ' + esc(risk.generated_at||'')
    + '<br>' + (D.footNote || '')
    + '<br>本看板仅供 B 模块演示与 E 前端参考之用，最终页面由 E 负责实现。';
})();
</script>
</body>
</html>
"""

out = _p(args.out)
with io.open(out, "w", encoding="utf-8") as f:
    f.write(HTML.replace("__DATA__", payload))

print("已生成:", out)
print("大小: %.1f KB" % (os.path.getsize(out) / 1024))
