#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts_build_peer_view.py
==========================
把 peer_view.json 渲染成单文件 HTML 同业对比页（三个视图，全部静态 SVG、零依赖、零 JS）：

1. 逐指标点图    —— 每个指标一条横轴：篮子每家一个点、目标公司高亮、
                   板块池 P25/中位数/P75 三条分位线（对数刻度指标注明）。
2. 差距条形图    —— 目标公司相对行业中位数的偏离，以四分位距（IQR）为单位画长度，
                   红=不利偏离、绿=有利偏离；旁边标注实际数值与相对偏离百分比。
3. 杜邦三因子并排 —— 净利率 × 总资产周转率 × 权益乘数 = ROE，10 家公司逐列对比，
                   目标行高亮；不可计算的公司如实灰行标注原因。

页面上必须诚实标出的三件事（否则图会骗人）
----------------------------------------
1. 篮子是跨行业的：池线（如白酒Ⅱ）只对同板块公司严格可比，
   其他公司的点仅作参照——顶部横幅写明。
2. 池分位线有样本量与状态（calibrated/indicative），不是绝对标准。
3. 缺值公司（如格力 ROE not_meaningful）不画点，在图下方列出原因，
   绝不当作零值落图。

用法
----
    python3 scripts_build_peer_view.py --view cases/a-share-basket/peer_view.json \
        --out cases/a-share-basket/peer_view.html
"""
from __future__ import annotations

import argparse
import html
import json
import math

PAGE_W = 1060
PLOT_X = 168          # 点图绘图区起点
PLOT_W = 800
ROW_H = 46


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fmt(v, unit):
    if v is None:
        return "—"
    if unit == "days":
        return "%.2f 天" % v
    if unit == "multiplier":
        return "%.2f 倍" % v
    return "%.2f%%" % (v * 100)


def scale_fn(unit, lo, hi):
    """dso 跨 4 个数量级，天数指标用对数刻度；其余线性。"""
    if unit == "days" and lo > 0:
        l0, l1 = math.log10(lo), math.log10(hi)

        def xlog(v):
            if v <= 0:
                return PLOT_X
            return PLOT_X + PLOT_W * (math.log10(v) - l0) / (l1 - l0 or 1)
        return xlog, "log"
    span = (hi - lo) or 1

    def xlin(v):
        return PLOT_X + PLOT_W * (v - lo) / span
    return xlin, "linear"


def dot_strip(ind, target_code):
    unit = ind["unit"]
    vals = [r["value"] for r in ind["companies"] if r["value"] is not None]
    pool = ind["pool"] or {}
    ref = [v for v in vals + [pool.get("p25"), pool.get("p75")]
           if isinstance(v, (int, float))]
    if not ref:
        return ""
    lo, hi = min(ref), max(ref)
    pad = (hi - lo) * 0.08 or hi * 0.1 or 0.1
    lo, hi = max(lo - pad, 1e-4 if unit == "days" else lo - pad), hi + pad
    xf, mode = scale_fn(unit, lo, hi)
    cy = ROW_H / 2 + 4

    parts = ['<svg class="strip" viewBox="0 0 %d %d" width="100%%" role="img" aria-label="%s">'
             % (PAGE_W, ROW_H + 18, esc(ind["label"]))]
    # 轴线
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" class="axis"/>'
                 % (PLOT_X, cy, PLOT_X + PLOT_W, cy))
    # 板块池分位线
    if pool.get("p25") is not None:
        for q, cls, txt in (("p25", "qline", "P25"), ("median", "mline", "中位数"), ("p75", "qline", "P75")):
            v = pool.get(q)
            if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                continue
            x = xf(v)
            parts.append('<line x1="%.1f" y1="8" x2="%.1f" y2="%d" class="%s"/>'
                         % (x, x, ROW_H + 2, cls))
            parts.append('<text x="%.1f" y="%d" class="qlab" text-anchor="middle">%s %s</text>'
                         % (x, ROW_H + 14, txt, fmt(v, unit)))
    # 公司点：非目标灰点，目标红点；标签上下交替防重叠
    up = True
    for r in ind["companies"]:
        if r["value"] is None:
            continue
        x = xf(r["value"])
        tgt = r["code"] == target_code
        tip = "%s（%s）：%s" % (r["name"], r["code"], fmt(r["value"], unit))
        parts.append('<circle cx="%.1f" cy="%d" r="%s" class="%s"><title>%s</title></circle>'
                     % (x, cy, "6.5" if tgt else "4.5", "tdot" if tgt else "cdot", esc(tip)))
        if tgt or (unit == "days" and r["value"] > hi * 0.6):
            parts.append('<text x="%.1f" y="%d" class="%s" text-anchor="middle">%s</text>'
                         % (x, cy - 10 if up else cy + 18, "tlab" if tgt else "plab", esc(r["name"])))
            up = not up
    parts.append('</svg>')
    head = ('<div class="rowhead"><b>%s</b><span>%s · 池 n=%s（%s）</span></div>'
            % (esc(ind["label"]), "对数刻度" if mode == "log" else "线性刻度",
               esc(pool.get("n") or "—"), esc(pool.get("status") or "无池")))
    return head + "".join(parts)


def gap_chart(indicators, target_name):
    """目标 − 行业中位数，以 IQR 为单位；红=不利、绿=有利。"""
    rows, max_units = [], 0.0
    for ind in indicators:
        pool = ind["pool"] or {}
        tv, med = ind["target_value"], pool.get("median")
        if tv is None or not isinstance(med, (int, float)):
            rows.append((ind, None, None, None, None, "无池或目标缺值"))
            continue
        gap = tv - med
        iqr = (pool.get("p75") or 0) - (pool.get("p25") or 0)
        iqr = iqr if iqr else abs(med) or 1
        u = gap / iqr
        max_units = max(max_units, abs(u))
        rel = gap / abs(med) if med else None
        good = (gap > 0) == (ind["direction"] == "higher_better")
        rows.append((ind, gap, u, rel, good, None))
    if max_units <= 0:
        return "<p>无可画的差距。</p>"
    half = PLOT_W / 2
    parts = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="差距条形图">'
             % (PAGE_W, 34 * len(rows) + 26)]
    cx = PLOT_X + half
    parts.append('<line x1="%.1f" y1="4" x2="%.1f" y2="%d" class="axis"/>'
                 % (cx, cx, 34 * len(rows) + 12))
    y = 16
    for ind, gap, u, rel, good, err in rows:
        if err:
            parts.append('<text x="%d" y="%d" class="mlab">%s：无池或目标缺值，不画</text>'
                         % (PLOT_X, y + 8, esc(ind["label"])))
            y += 34
            continue
        w = min(abs(u) / max_units, 1.0) * (half - 30)
        cls = "gbar" if good else "rbar"
        x2 = cx + (w if gap > 0 else -w)
        pool = ind["pool"] or {}
        reltxt = ("（%+.1f%%）" % (rel * 100)) if rel is not None else ""
        tip = ("%s：%s vs 中位数 %s，偏离 %s%s，距中位数 %.1f 个四分位距"
               % (ind["label"], fmt(gap + med, ind["unit"]), fmt(med, ind["unit"]),
                  fmt(abs(gap), ind["unit"]), reltxt, abs(u)))
        parts.append('<rect x="%.1f" y="%d" width="%.1f" height="16" class="%s">'
                     '<title>%s</title></rect>' % (min(cx, x2), y, abs(w), cls, esc(tip)))
        parts.append('<text x="%d" y="%d" class="mlab">%s</text>' % (12, y + 12, esc(ind["label"])))
        parts.append('<text x="%.1f" y="%d" class="%s" text-anchor="%s">%s %s%s</text>'
                     % (x2 + (6 if gap > 0 else -6), y + 12, "glab" if good else "rlab",
                        "start" if gap > 0 else "end",
                        "高" if gap > 0 else "低", fmt(abs(gap), ind["unit"]), reltxt))
        y += 34
    parts.append('</svg>')
    legend = ('<p class="legend">条长 = 偏离中位数的四分位距（IQR）数；'
              '<span class="c-r">红 = 向不利方向偏离</span>、'
              '<span class="c-g">绿 = 向有利方向偏离</span>；'
              '相对偏离按 |中位数| 折算，池中位数接近 0 的指标（如 dso）相对值仅供参考。</p>')
    return legend + "".join(parts)


def dupont_chart(dupont, factors, target_code):
    ok = [r for r in dupont if r.get("roe") is not None]
    bad = [r for r in dupont if r.get("roe") is None]
    ok.sort(key=lambda r: -r["roe"])
    maxes = {f["key"]: max([abs(r.get(f["key"]) or 0) for r in ok] or [1]) or 1
             for f in factors}
    col_w = 176
    col_x = [200, 200 + col_w, 200 + 2 * col_w]
    H = 34 * (len(ok) + len(bad)) + 30
    parts = ['<svg viewBox="0 0 %d %d" width="100%%" role="img" aria-label="杜邦三因子并排">'
             % (PAGE_W, H)]
    for f, x in zip(factors, col_x):
        parts.append('<text x="%d" y="14" class="chd">%s</text>' % (x + 60, esc(f["label"])))
    parts.append('<text x="%d" y="14" class="chd">ROE（闭合校验）</text>' % (col_x[2] + col_w + 40))
    y = 22
    for r in ok:
        tgt = r["code"] == target_code
        if tgt:
            parts.append('<rect x="8" y="%d" width="%d" height="26" rx="6" class="trow"/>' % (y, PAGE_W - 20))
        parts.append('<text x="16" y="%d" class="%s">%s</text>'
                     % (y + 17, "tlab2" if tgt else "mlab", esc(r["name"])))
        for f, x in zip(factors, col_x):
            v = r.get(f["key"])
            if v is None:
                continue
            w = abs(v) / maxes[f["key"]] * (col_w - 52)
            parts.append('<rect x="%d" y="%d" width="%.1f" height="13" class="%s">'
                         '<title>%s：%s = %s</title></rect>'
                         % (x, y + 4, w, "tbar" if tgt else "bar",
                            esc(r["name"]), esc(f["label"]), fmt(v, f["unit"])))
            parts.append('<text x="%d" y="%d" class="vlab">%s</text>'
                         % (x + col_w - 46, y + 15, fmt(v, f["unit"])))
        cd = r.get("closure_delta") or 0
        parts.append('<text x="%d" y="%d" class="%s">%.2f%%　|差|=%.1e</text>'
                     % (col_x[2] + col_w + 40, y + 17, "tlab2" if tgt else "vlab",
                        r["roe"] * 100, abs(cd)))
        y += 34
    for r in bad:
        parts.append('<text x="16" y="%d" class="mlab" fill="#90A4AE">%s：ROE %s，杜邦不可计算</text>'
                     % (y + 17, esc(r["name"]), esc(r.get("missing_reason") or "not_evaluable")))
        y += 34
    parts.append('</svg>')
    note = ('<p class="legend">杜邦分解：净利率 × 总资产周转率 × 权益乘数 = ROE（平均口径）。\n'
            '「|差|」是三因子乘积与 ROE 的闭合差（量级 1e-15 级为浮点噪声，属正常）。\n'
            '杠杆（权益乘数）高不一定是坏事，要和净利率、周转放在一起读。</p>')
    return note + "".join(parts)


def main():
    ap = argparse.ArgumentParser(description="渲染同业对比页")
    ap.add_argument("--view", required=True, help="build_peer_view.py 产出的 JSON")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    d = json.load(open(args.view, "r", encoding="utf-8"))
    tgt = d["target"]
    board = d.get("board") or {}
    strips = []
    for ind in d["indicators"]:
        strips.append('<div class="indblock">%s%s</div>'
                      % (dot_strip(ind, tgt["code"]),
                         ('<p class="cnote">口径：%s</p>' % esc(ind["convert_note"]))
                         if ind.get("convert_note") else ""))
    banner = ""
    if board:
        banner = ('<div class="banner">板块池：<b>%s %s</b>（%s，n 以各指标为准）。'
                  '池线只对同板块公司严格可比——篮子里其他行业的公司仅作参照，'
                  '不构成同业结论。分位线是实测分布，不是合格线。</div>'
                  % (esc(board.get("code") or ""), esc(board.get("name") or ""),
                     esc(board.get("as_of") or "")))
    notes = ""
    if d.get("notes"):
        notes = '<div class="notes"><b>缺值说明（不猜数）：</b><ul>%s</ul></div>' % \
                "".join("<li>%s</li>" % esc(n) for n in d["notes"])

    doc = TEMPLATE.replace("__TITLE__", esc("%s 同业对比" % tgt["name"])) \
                  .replace("__BANNER__", banner) \
                  .replace("__NOTES__", notes) \
                  .replace("__STRIPS__", "".join(strips)) \
                  .replace("__TARGET__", esc(tgt["name"])) \
                  .replace("__GAPS__", gap_chart(d["indicators"], tgt["name"])) \
                  .replace("__DUPONT__", dupont_chart(d["dupont"], d["dupont_factors"], tgt["code"])) \
                  .replace("__GEN__", esc(d.get("generated_at") or ""))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("[OK] peer_view.html -> %s" % args.out)


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>同业对比 · __TARGET__</title>
<style>
:root{
  --bg:#F6F7F9; --panel:#FFFFFF; --line:#E3E6EB; --tx:#1A1D21; --tx2:#5B6472; --tx3:#8B95A5;
  --red:#C0392B; --grn:#2E7D32; --blu:#2D6CB5; --org:#E67E22;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  font-size:13px;line-height:1.55}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:20px;font-weight:600;margin:0 0 4px}
h2{font-size:14px;font-weight:600;margin:26px 0 4px}
.sub{color:var(--tx2);font-size:12px;margin-bottom:14px}
.banner{background:#FFF8E1;border:1px solid #F0D48A;border-left:4px solid #E0A800;
  border-radius:0 8px 8px 0;padding:10px 14px;color:#6B5300;font-size:12px;margin-bottom:6px}
.notes{background:#FBEBE9;border:1px solid #EBC4C0;border-left:4px solid var(--red);
  border-radius:0 8px 8px 0;padding:10px 14px;font-size:12px;color:#7A2E23;margin:6px 0 14px}
.notes ul{margin:4px 0 0;padding-left:18px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;margin-bottom:10px;overflow-x:auto}
.indblock{padding:6px 0;border-bottom:1px dashed var(--line)}
.indblock:last-child{border-bottom:none}
.rowhead b{font-size:13px}
.rowhead span{color:var(--tx3);font-size:11px;margin-left:10px}
svg.strip{display:block}
.axis{stroke:#C9CFD8;stroke-width:1}
.qline{stroke:var(--blu);stroke-width:1;stroke-dasharray:4 3;opacity:.75}
.mline{stroke:var(--blu);stroke-width:1.6}
.qlab{font-size:10px;fill:var(--blu)}
.cdot{fill:#9AA6B5;opacity:.85}
.tdot{fill:var(--red);stroke:#fff;stroke-width:1.5}
.plab{font-size:10px;fill:var(--tx3)}
.tlab{font-size:11px;fill:var(--red);font-weight:600}
.cnote{color:var(--tx3);font-size:11px;margin:2px 0 0}
.legend{color:var(--tx2);font-size:11px;margin:6px 0}
.c-r{color:var(--red)}.c-g{color:var(--grn)}
.rbar{fill:var(--red);opacity:.85}.gbar{fill:var(--grn);opacity:.85}
.rlab{fill:var(--red);font-size:11px}.glab{fill:var(--grn);font-size:11px}
.mlab{font-size:11.5px;fill:var(--tx2)}
.chd{font-size:11.5px;fill:var(--tx2);font-weight:600}
.bar{fill:#8FA8C8;opacity:.85}.tbar{fill:var(--org)}
.trow{fill:#FDF1E5}
.vlab{font-size:10.5px;fill:var(--tx2)}
.tlab2{font-size:12px;fill:var(--tx);font-weight:600}
.foot{color:var(--tx3);font-size:11px;margin-top:18px}
</style>
</head>
<body>
<div class="wrap">
<h1>同业对比 · __TARGET__</h1>
<div class="sub">逐指标点位 / 相对行业中位数的偏离 / 杜邦三因子并排 · 生成于 __GEN__</div>
__BANNER__
__NOTES__
<h2>一、逐指标点位（篮子全员 + 板块池分位线）</h2>
<div class="panel">
__STRIPS__
</div>
<h2>二、目标公司相对行业中位数的偏离</h2>
<div class="panel">
__GAPS__
</div>
<h2>三、杜邦三因子并排（跨公司）</h2>
<div class="panel">
__DUPONT__
</div>
<div class="foot">数据出处：公司指标 = compute_ratios.py 实算（ratios JSON）；分位线 = 东财板块成分股离线校准（fetch_industry_samples.py）；杜邦 = attribution.dupont（平均口径，闭合校验随图透出）。零第三方依赖、零运行时 JS。</div>
</div>
</body>
</html>
"""

if __name__ == "__main__":
    main()
