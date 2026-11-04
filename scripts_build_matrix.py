#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts_build_matrix.py
=======================
把 `risk_matrix.json` 渲染成单文件 HTML：行=风险项，列=公司。

为什么行是风险、列是公司
------------------------
公司数量通常个位数，风险规则几十条。反过来排（行=公司）会把几十列挤成竖排文字，
在屏幕上无法读。行=风险时，公司列固定 3–10 个，一眼能看出"同一条规则谁中招"。

页面上要能区分三件事，否则矩阵会骗人
------------------------------------
1. 阈值来源：同一条规则，A 公司用固定阈值、B 公司用同业 P75，两个色块不可直接横比。
   用右上角小三角标出动态阈值格，并在详情里写清阈值数值与样本量。
2. 结论可信度：勾稽不平或大面积无法评估的公司，其"通过"不等于没风险，只是没查到。
   低可信度公司整列加警示色 + 顶部可信度条单独列出原因。
3. 可比性：行业字段缺失时矩阵只在同一剖面内可比，不能当严格同业对比。

用法
----
    python3 scripts_build_matrix.py --matrix risk-radar/demo/matrix/risk_matrix.json \
        --out risk-radar/demo/matrix/risk_matrix.html
"""

from __future__ import annotations

import argparse
import json
import os

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>多公司风险矩阵 · __TITLE__</title>
<style>
:root{
  --bg:#F6F7F9; --panel:#FFFFFF; --line:#E3E6EB; --tx:#1A1D21; --tx2:#5B6472; --tx3:#8B95A5;
  --red:#C0392B; --org:#E67E22; --yel:#E0A800; --grn:#2E7D32; --gry:#90A4AE; --blu:#2D6CB5;
  --redbg:#FBEBE9; --orgbg:#FDF1E5; --yelbg:#FCF6E0; --grnbg:#EDF6EE; --grybg:#F1F3F5;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
  font-size:13px;line-height:1.55}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:20px;font-weight:600;margin:0 0 6px}
h2{font-size:13px;font-weight:600;margin:22px 0 8px;color:var(--tx2)}
.sub{color:var(--tx2);font-size:12px;margin-bottom:18px}
.banner{background:#FFF8E1;border:1px solid #F0D48A;border-left:4px solid var(--yel);
  border-radius:0 8px 8px 0;padding:10px 14px;color:#6B5300;font-size:12px;margin-bottom:10px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:12px 16px;min-width:130px;flex:1}
.card .v{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.card .l{color:var(--tx3);font-size:11px;margin-top:2px}

/* 可信度条 */
.relbar{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}
.relrow{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--gry);
  border-radius:0 8px 8px 0;padding:8px 12px;font-size:12px;display:flex;gap:10px;
  align-items:baseline;flex-wrap:wrap}
.relrow.lv-高{border-left-color:var(--grn)}
.relrow.lv-中{border-left-color:var(--org)}
.relrow.lv-低{border-left-color:var(--red);background:#FFFCFC}
.relrow .nm{font-weight:600}
.relrow .nt{color:var(--tx2);flex:1;min-width:220px}
.relrow .dq{color:var(--tx3);font-size:11px;font-variant-numeric:tabular-nums}
.rchip{display:inline-block;font-size:10.5px;padding:0 6px;border-radius:4px;
  line-height:17px;border:1px solid transparent;white-space:nowrap}
.rchip.lv-高{background:var(--grnbg);color:var(--grn);border-color:#CFE5D2}
.rchip.lv-中{background:var(--orgbg);color:#B35C00;border-color:#F3D6BB}
.rchip.lv-低{background:var(--redbg);color:var(--red);border-color:#F0C4BE}

.toolbar{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:10px;
  color:var(--tx2);font-size:12px}
.toolbar label{cursor:pointer;user-select:none}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;color:var(--tx2)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;
  vertical-align:-2px;border:1px solid rgba(0,0,0,.08)}
.legend .pk{position:relative;width:13px;height:13px;background:#E9EDF2;
  border:1px solid #C4CBD4;border-radius:3px}
.legend .pk::after{content:'';position:absolute;top:-1px;right:-1px;width:0;height:0;
  border-top:7px solid var(--blu);border-left:7px solid transparent}

table{border-collapse:separate;border-spacing:0;width:100%;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:0;border-bottom:1px solid var(--line)}
thead th{position:sticky;top:0;background:#FBFCFD;z-index:2;padding:9px 8px;
  font-size:12px;font-weight:600;text-align:center;color:var(--tx2);vertical-align:top}
thead th.rule{text-align:left;padding-left:14px;width:40%}
thead th.lowrel{background:#FFF7F5;box-shadow:inset 0 -2px 0 #EDC6BF}
tbody td.rule{padding:8px 10px 8px 14px;border-right:1px solid var(--line)}
tbody td.rule .id{font-family:ui-monospace,Menlo,monospace;color:var(--tx3);
  font-size:11px;margin-right:6px}
tr.grp td{background:#F2F4F7;color:var(--tx2);font-size:11px;font-weight:600;
  padding:6px 14px;letter-spacing:.4px}
td.c{text-align:center;width:14%}
td.c.lowrel{background:#FFFCFC}
.cell{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;
  border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;transition:transform .08s;
  position:relative}
.cell:hover{transform:scale(1.12)}
.cell.peer::after{content:'';position:absolute;top:0;right:0;width:0;height:0;
  border-top:8px solid var(--blu);border-left:8px solid transparent;border-top-right-radius:6px}
.c-high{background:var(--red);color:#fff}
.c-medium{background:var(--org);color:#fff}
.c-low{background:var(--yel);color:#4A3B00}
.c-passed{background:var(--grnbg);color:var(--grn);border:1px solid #CFE5D2}
.c-na{background:var(--grybg);color:var(--gry);border:1px solid #DFE4E9}
.c-ne{background:var(--grybg);color:var(--tx3);border:1px dashed #C4CBD4}
.co{font-size:11px;color:var(--tx3);font-weight:400;display:block;margin-top:2px}
.co.sc{font-weight:600;font-size:11.5px;color:var(--tx2)}
#detail{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);width:min(700px,92vw);
  background:#1F2328;color:#E8EAED;border-radius:12px;padding:14px 18px;font-size:12.5px;
  box-shadow:0 8px 32px rgba(0,0,0,.28);display:none;z-index:20}
#detail b{color:#fff}
#detail .x{position:absolute;right:12px;top:10px;cursor:pointer;color:#9AA4B2}
#detail .kv{margin-top:7px;color:#9AA4B2}
#detail .kv em{color:#E8EAED;font-style:normal}
.hint{color:var(--tx3);font-size:11px;margin-top:10px}

/* 二维矩阵图 */
.chartcard{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px 10px;margin-bottom:14px}
.chartcard .hd{font-size:12.5px;font-weight:600;margin-bottom:2px}
.chartcard .ax{font-size:11.5px;color:var(--tx3);margin-bottom:8px;line-height:1.6}
.chartcard svg{display:block;width:100%;height:auto}
.chartcard .foot{font-size:11px;color:var(--tx3);margin-top:4px}
.clegend{display:flex;gap:12px;flex-wrap:wrap;font-size:11.5px;color:var(--tx2);margin-top:6px}
.clegend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;
  vertical-align:1px}
.ql{margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
.qlr{display:flex;gap:10px;align-items:baseline;font-size:11.5px;color:var(--tx2);
  padding:3px 0;border-bottom:1px dashed #EEF0F3}
.qlr:last-child{border-bottom:0}
.qlr .rid{font-family:ui-monospace,Menlo,monospace;color:var(--tx3);width:32px;flex:none}
.qlr .nm{flex:1;min-width:110px;color:var(--tx);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.qlr .num{font-variant-numeric:tabular-nums;color:var(--tx3);white-space:nowrap}
.qtag{font-size:10.5px;padding:0 6px;border-radius:4px;line-height:17px;white-space:nowrap;flex:none}
.qtag.q-tr{background:var(--redbg);color:var(--red)}
.qtag.q-tl{background:var(--orgbg);color:#B35C00}
.qtag.q-br{background:var(--yelbg);color:#7A5E00}
.qtag.q-bl{background:var(--grybg);color:var(--tx3)}

@media(max-width:720px){.card{min-width:110px}thead th.rule{width:34%}
  .cell{width:23px;height:23px;font-size:11px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>多公司风险矩阵</h1>
  <div class="sub">__SUBTITLE__</div>
  <div class="banner">__BANNER__</div>
  <div class="banner" id="cmpnote" style="display:none"></div>

  <div class="cards" id="cards"></div>

  <h2>风险矩阵：触发广度 × 触发强度</h2>
  <div class="chartcard">
    <div class="hd">每条规则落在哪一格</div>
    <div class="ax">横轴 = 该风险项在本批公司中触发的比例（触发家数 / 可评估家数）；纵轴 = 触发公司的平均风险分。气泡越大，中招的公司越多；颜色区分风险类别。</div>
    <svg id="mxchart" viewBox="0 0 780 470" role="img" aria-label="风险矩阵散点图"></svg>
    <div class="clegend" id="mlegend"></div>
    <div class="foot" id="mxnote"></div>
    <div class="ql" id="qlist"></div>
  </div>

  <h2>公司风险定位</h2>
  <div class="chartcard">
    <div class="hd">每家公司落在哪一格</div>
    <div class="ax">横轴 = 该公司触发的规则占可评估规则的比例；纵轴 = 综合风险分。气泡越大，不可评估的规则越多，结论越要打折看；颜色是结论可信度。</div>
    <svg id="cochart" viewBox="0 0 780 360" role="img" aria-label="公司风险定位散点图"></svg>
    <div class="clegend" id="colegend"></div>
  </div>

  <h2>结论可信度</h2>
  <div class="relbar" id="relbar"></div>

  <h2>逐项明细</h2>

  <div class="toolbar">
    <label><input type="checkbox" id="f-trig"> 只看有触发的风险项</label>
    <label><input type="checkbox" id="f-ne"> 只看存在不可评估的风险项</label>
    <label><input type="checkbox" id="f-peer"> 只看阈值取同业分位的风险项</label>
    <span id="cnt"></span>
  </div>

  <div class="legend" id="legend"></div>

  <table>
    <thead><tr id="thead"></tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="hint">点矩阵图上的气泡或下方清单，看该风险项的判定范围与中招公司；点明细表里的色块，看某家公司在该项上的具体说明。右上角带蓝三角的格子，阈值取自同业分位数，不同公司的阈值并不相同。</div>
</div>

<div id="detail"><span class="x" onclick="document.getElementById('detail').style.display='none'">✕</span><div id="dbody"></div></div>

<script>
const MX = __DATA__;
const TAG = {triggered:{high:'重',medium:'关',low:'提'},passed:'·',
             not_evaluable:'?',not_applicable:'—'};
const CLS = {triggered:{high:'c-high',medium:'c-medium',low:'c-low'},
             passed:'c-passed',not_evaluable:'c-ne',not_applicable:'c-na'};
const LABEL = {triggered:'触发',passed:'通过',not_evaluable:'不可评估',not_applicable:'行业不适用'};
const SRCLABEL = {fixed:'固定阈值',peer_p25:'同业 P25',peer_p75:'同业 P75',
                  regulatory:'监管红线',convention:'行业惯例'};
// 类别配色：同一类在全页保持同色，矩阵图与明细表能对上
const CATCOLOR = {growth:'#2D6CB5',profitability:'#7B4FB0',solvency:'#C0392B',
                  efficiency:'#E67E22',cashflow_quality:'#2E7D32',asset_quality:'#00838F'};
const CATFALLBACK = '#78909C';
const RELCOLOR = {'高':'#2E7D32','中':'#E67E22','低':'#C0392B'};
function catColor(k){ return CATCOLOR[k] || CATFALLBACK; }

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function fmtThr(v){
  if(v==null) return '—';
  if(Math.abs(v)<=2) return (v*100).toFixed(2)+'%';
  return (Math.round(v*100)/100).toString();
}
function cellOf(k,r){
  return (MX.matrix[k]||{})[r.risk_id] || {status:'not_applicable'};
}
function dqText(d){
  if(!d) return '';
  const p=['勾稽平衡 '+d.balanced+' 项'];
  if(d.imbalanced) p.push('不平 '+d.imbalanced+' 项');
  if(d.not_evaluable) p.push('无法评估 '+d.not_evaluable+' 项');
  if(d.reviews_inherited) p.push('继承待核 '+d.reviews_inherited+' 项');
  return p.join(' · ');
}

// ---- 二维风险矩阵图 ----
const QUADLABEL = {q_tr:'多家触发·强度偏高',q_tl:'少数触发·强度偏高',
                   q_br:'多家触发·强度偏低',q_bl:'少数触发·强度偏低'};
function quadOf(b,s,mx,my){
  return (b>=mx) ? (s>=my?'q_tr':'q_br') : (s>=my?'q_tl':'q_bl');
}

function drawMatrix(){
  const svg = document.getElementById('mxchart');
  const V = MX.risk_matrix_view || {};
  const all = V.points || [];
  const pts = all.filter(p=>p.intensity!=null);
  if(!pts.length){ svg.parentNode.removeChild(svg); return; }

  const L=76,R=754,T=26,B=394, W=R-L, H=B-T;
  const Y0=40, Y1=100;            // 无触发项低于 40 分，纵轴从 40 起只为去掉空白，刻度等距
  const mx = V.mid_x==null?50:V.mid_x, my = V.mid_y==null?70:V.mid_y;
  const px = b => L + Math.min(Math.max(b,0),100)/100*W;
  const py = v => B - (Math.min(Math.max(v,Y0),Y1)-Y0)/(Y1-Y0)*H;
  let h='';

  // 四象限底色
  const xm=px(mx), ym=py(my);
  h+='<rect x="'+L+'" y="'+T+'" width="'+(xm-L)+'" height="'+(ym-T)+'" fill="#FBFCFD"/>';
  h+='<rect x="'+xm+'" y="'+T+'" width="'+(R-xm)+'" height="'+(ym-T)+'" fill="#FDF4F1"/>';
  h+='<rect x="'+L+'" y="'+ym+'" width="'+(xm-L)+'" height="'+(B-ym)+'" fill="#F6F9F6"/>';
  h+='<rect x="'+xm+'" y="'+ym+'" width="'+(R-xm)+'" height="'+(B-ym)+'" fill="#FDFAF1"/>';

  // 网格与刻度
  for(let b=0;b<=100;b+=20){
    h+='<line x1="'+px(b)+'" y1="'+T+'" x2="'+px(b)+'" y2="'+B+'" stroke="#E9ECF0"/>'
     + '<text x="'+px(b)+'" y="'+(B+17)+'" font-size="11" fill="#8B95A5" text-anchor="middle">'+b+'%</text>';
  }
  for(let v=Y0;v<=Y1;v+=10){
    h+='<line x1="'+L+'" y1="'+py(v)+'" x2="'+R+'" y2="'+py(v)+'" stroke="#E9ECF0"/>'
     + '<text x="'+(L-10)+'" y="'+(py(v)+4)+'" font-size="11" fill="#8B95A5" text-anchor="end">'+v+'</text>';
  }
  // 中线
  h+='<line x1="'+xm+'" y1="'+T+'" x2="'+xm+'" y2="'+B+'" stroke="#AEB8C6" stroke-dasharray="5 4"/>'
   + '<line x1="'+L+'" y1="'+ym+'" x2="'+R+'" y2="'+ym+'" stroke="#AEB8C6" stroke-dasharray="5 4"/>';

  // 象限名：分界是相对本批的中位数，标签只描述相对位置，不下绝对判断
  h+='<text x="'+(L+10)+'" y="'+(T+16)+'" font-size="11" fill="#9AA4B2">'+QUADLABEL.q_tl+'</text>'
   + '<text x="'+(R-10)+'" y="'+(T+16)+'" font-size="11" fill="#C4705F" text-anchor="end">'+QUADLABEL.q_tr+'</text>'
   + '<text x="'+(L+10)+'" y="'+(B-8)+'" font-size="11" fill="#9AA4B2">'+QUADLABEL.q_bl+'</text>'
   + '<text x="'+(R-10)+'" y="'+(B-8)+'" font-size="11" fill="#B08A3E" text-anchor="end">'+QUADLABEL.q_br+'</text>';

  // 轴标题
  h+='<text x="'+((L+R)/2)+'" y="'+(B+36)+'" font-size="12" fill="#5B6472" text-anchor="middle">触发广度（触发家数 / 可评估家数）</text>'
   + '<text transform="translate(20,'+((T+B)/2)+') rotate(-90)" font-size="12" fill="#5B6472" text-anchor="middle">触发强度（平均风险分）</text>';

  // 气泡
  pts.forEach(p=>{
    const cx=px(p.breadth), cy=py(p.intensity);
    const r=(6+3.3*Math.sqrt(p.n_triggered)).toFixed(1);
    const col=catColor(p.category);
    const ub=V.x_axis&&V.x_axis.unit?V.x_axis.unit:'%';
    const tip=p.risk_id+' '+p.risk_name+'\\n'
      +'广度 '+p.breadth+ub+'（'+p.n_triggered+'/'+p.n_evaluable+' 家触发）\\n'
      +'强度 '+p.intensity+' 分　类别：'+(p.category_label||p.category)+'\\n'
      +'触发：'+p.companies.join('、');
    h+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+col+'" fill-opacity="0.8" '
     + 'stroke="#fff" stroke-width="1.5" style="cursor:pointer" data-rid="'+esc(p.risk_id)+'">'
     + '<title>'+esc(tip)+'</title></circle>';
    if(p.n_triggered>=3){
      h+='<text x="'+(cx+Number(r)+4)+'" y="'+(cy+4)+'" font-size="10.5" fill="#5B6472">'
       + esc(p.risk_id)+'</text>';
    }
  });
  svg.innerHTML=h;

  // 图例
  const cats=[...new Set(pts.map(p=>p.category))];
  document.getElementById('mlegend').innerHTML =
    cats.map(c=>{
      const p=pts.find(x=>x.category===c);
      return '<span><i style="background:'+catColor(c)+'"></i>'+esc((p.category_label||c).split('：')[0])+'</span>';
    }).join('')
    + '<span><i style="background:#C8CFD8"></i>气泡越大 = 触发家数越多</span>';

  document.getElementById('mxnote').textContent =
    '象限分界：广度 ' + mx + '%、强度 ' + my + ' 分，取本批中位数，表示相对位置，不是绝对红线。'
    + (pts.some(p=>p.breadth>=50) ? '' : '本批没有一条规则的触发面过半，点都落在左半区。')
    + '纵轴自 40 分起，只为压掉空白，刻度等距。样本 ' + (MX.companies||[]).length
    + ' 家公司；未触发的规则不落图。各规则的可评估家数不同，分母已逐条标注。';

  // 点清单：图中的点会重叠，这里给出可读的数值
  const sorted=pts.slice().sort((a,b)=>b.breadth-a.breadth||b.intensity-a.intensity);
  document.getElementById('qlist').innerHTML = sorted.slice(0,8).map(p=>{
    const q=quadOf(p.breadth,p.intensity,mx,my);
    return '<div class="qlr" data-rid="'+esc(p.risk_id)+'" style="cursor:pointer">'
      +'<span class="rid">'+esc(p.risk_id)+'</span>'
      +'<span class="nm">'+esc(p.risk_name)+'</span>'
      +'<span class="num">'+p.n_triggered+'/'+p.n_evaluable+' 家</span>'
      +'<span class="num">广度 '+p.breadth+'%</span>'
      +'<span class="num">强度 '+p.intensity+'</span>'
      +'<span class="qtag '+q+'">'+QUADLABEL[q]+'</span></div>';
  }).join('') + (sorted.length>8
    ? '<div class="qlr"><span class="nm" style="color:var(--tx3)">另有 '+(sorted.length-8)+' 条，见下方逐项明细</span></div>'
    : '');

  const open=e=>{
    let el=e.target;
    while(el && el.getAttribute){
      if(el.getAttribute('data-rid')){ showRule(el.getAttribute('data-rid')); return; }
      el=el.parentNode;
    }
  };
  svg.onclick=open;
  document.getElementById('qlist').onclick=open;
}

function showRule(rid){
  const rule=(MX.rules||[]).find(r=>r.risk_id===rid)||{};
  const p=((MX.risk_matrix_view||{}).points||[]).find(x=>x.risk_id===rid)||{};
  const V=MX.risk_matrix_view||{};
  const q=p.intensity!=null?quadOf(p.breadth,p.intensity,V.mid_x,V.mid_y):null;
  let h='<b>'+esc(rid)+' '+esc(rule.risk_name)+'</b>　<span style="color:#9AA4B2">'
       +esc(rule.category_label||rule.category||'')+'</span>';
  if(p.intensity!=null){
    h+='<div class="kv">触发广度：<em>'+p.breadth+'%</em>（'+p.n_triggered+' / '+p.n_evaluable
      +' 家可评估公司）　触发强度：<em>'+p.intensity+' 分</em></div>';
    h+='<div class="kv">所在象限：<em>'+QUADLABEL[q]+'</em>　触发公司：<em>'
      +esc((p.companies||[]).join('、'))+'</em></div>';
    h+='<div class="kv" style="color:#8FA0B5">广度衡量的是同批公司里已触发的比例，'
      +'不是未来发生概率的预测。</div>';
  }
  document.getElementById('dbody').innerHTML=h;
  document.getElementById('detail').style.display='block';
}

// ---- 公司风险定位 ----
function drawCompanies(){
  const svg=document.getElementById('cochart');
  const V=MX.company_view||{};
  const pts=(V.points||[]).filter(p=>p.breadth!=null&&p.score!=null);
  if(!pts.length){ svg.parentNode.removeChild(svg); return; }

  const L=64,R=750,T=22,B=300, W=R-L, H=B-T;
  const xMax=Math.max(30,Math.ceil(Math.max(...pts.map(p=>p.breadth))/10)*10);
  const px=b=>L+Math.min(b,xMax)/xMax*W;
  const py=s=>B-Math.min(Math.max(s,0),100)/100*H;
  let h='';

  for(let b=0;b<=xMax;b+=10){
    h+='<line x1="'+px(b)+'" y1="'+T+'" x2="'+px(b)+'" y2="'+B+'" stroke="#E9ECF0"/>'
     + '<text x="'+px(b)+'" y="'+(B+17)+'" font-size="11" fill="#8B95A5" text-anchor="middle">'+b+'%</text>';
  }
  for(let s=0;s<=100;s+=20){
    h+='<line x1="'+L+'" y1="'+py(s)+'" x2="'+R+'" y2="'+py(s)+'" stroke="#E9ECF0"/>'
     + '<text x="'+(L-10)+'" y="'+(py(s)+4)+'" font-size="11" fill="#8B95A5" text-anchor="end">'+s+'</text>';
  }
  h+='<text x="'+((L+R)/2)+'" y="'+(B+36)+'" font-size="12" fill="#5B6472" text-anchor="middle">触发规则占比（触发数 / 可评估数）</text>'
   + '<text transform="translate(18,'+((T+B)/2)+') rotate(-90)" font-size="12" fill="#5B6472" text-anchor="middle">综合风险分</text>';

  pts.forEach(p=>{
    const cx=px(p.breadth), cy=py(p.score);
    const r=(6+1.5*Math.sqrt(p.n_not_evaluable||0)).toFixed(1);
    const col=RELCOLOR[p.reliability]||'#78909C';
    const tip=p.name+'\\n综合 '+p.score+' 分（'+p.risk_level+'）\\n'
      +'触发 '+p.n_triggered+' / '+p.n_evaluable+' 条\\n'
      +'不可评估 '+p.n_not_evaluable+' 条　结论可信度 '+p.reliability;
    h+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+col+'" fill-opacity="0.78" '
     + 'stroke="#fff" stroke-width="1.5"><title>'+esc(tip)+'</title></circle>';
    h+='<text x="'+(cx+Number(r)+4)+'" y="'+(cy+4)+'" font-size="10.5" fill="#5B6472">'
     + esc(String(p.name||'').slice(0,4))+'</text>';
  });
  svg.innerHTML=h;

  document.getElementById('colegend').innerHTML =
    [['高','#2E7D32'],['中','#E67E22'],['低','#C0392B']].map(([k,c])=>
      '<span><i style="background:'+c+'"></i>可信度 '+k+'</span>').join('')
    + '<span><i style="background:#C8CFD8"></i>气泡越大 = 不可评估规则越多</span>';
}

// ---- 概览 ----
(function(){
  const c = MX.companies, s = MX.summary || {};
  let peerCells = 0;
  c.forEach(co=>Object.keys(MX.matrix[co.key]||{}).forEach(rid=>{
    const t=(MX.matrix[co.key][rid]||{}).threshold_source;
    if(t && t!=='fixed') peerCells++;
  }));
  const lowRel = c.filter(x=>x.conclusion_reliability==='低').length;
  const items = [
    ['公司数', c.length],
    ['风险规则', MX.rules.length],
    ['平均风险分', s.avg_risk_score],
    ['风险最高', s.worst_company ? s.worst_company.name : '—'],
    ['动态阈值格', peerCells],
    ['低可信度', lowRel ? lowRel+' 家' : '0 家'],
  ];
  document.getElementById('cards').innerHTML = items.map(([l,v])=>
    '<div class="card"><div class="v">'+esc(v)+'</div><div class="l">'+esc(l)+'</div></div>').join('');
})();

// ---- 可比性提示 ----
(function(){
  const cb = MX.comparability || {};
  if(!cb.note) return;
  const el = document.getElementById('cmpnote');
  el.textContent = cb.note;
  if(cb.same_industry === false){
    el.style.background='#FBEBE9';
    el.style.borderColor='#F0C4BE';
    el.style.borderLeftColor='var(--red)';
    el.style.color='#8C2B1F';
  }
  el.style.display='block';
})();

// ---- 可信度条：低可信度排前面 ----
(function(){
  const order = {'低':0,'中':1,'高':2};
  const list = MX.companies.slice().sort((a,b)=>
    (order[a.conclusion_reliability]??3) - (order[b.conclusion_reliability]??3));
  document.getElementById('relbar').innerHTML = list.map(c=>{
    const lv = c.conclusion_reliability || '—';
    return '<div class="relrow lv-'+esc(lv)+'">'
      + '<span class="nm">'+esc(c.name)+'</span>'
      + '<span class="rchip lv-'+esc(lv)+'">可信度 '+esc(lv)+'</span>'
      + '<span class="nt">'+esc(c.reliability_note||'勾稽与缺失项未影响结论口径')+'</span>'
      + '<span class="dq">'+esc(dqText(c.data_quality))+'</span>'
      + '</div>';
  }).join('');
})();

// ---- 图例 ----
(function(){
  const L = [['c-high','重大'],['c-medium','关注'],['c-low','提示'],
             ['c-passed','通过'],['c-ne','不可评估'],['c-na','行业不适用']];
  let h = L.map(([cls,t])=>
    '<span><i class="'+cls+'"></i>'+t+'</span>').join('');
  h += '<span><i class="pk"></i>阈值取同业分位（动态阈值）</span>';
  document.getElementById('legend').innerHTML = h;
})();

// ---- 表头 ----
(function(){
  let h = '<th class="rule">风险项</th>';
  MX.companies.forEach(c=>{
    const lvl = c.overall_risk_level, sc = c.overall_risk_score;
    const lv = c.conclusion_reliability || '—';
    const col = sc>=70?'color:var(--red)':(sc>=40?'color:var(--org)':'color:var(--grn)');
    h += '<th class="'+(lv==='低'?'lowrel':'')+'" title="'+esc(c.reliability_note||'')+'">'
       + '<span style="'+col+'">'+esc(lvl)+' '+esc(sc)+'</span>'
       + '<span class="co sc">'+esc(c.name)+'</span>'
       + '<span class="rchip lv-'+esc(lv)+'">可信度 '+esc(lv)+'</span></th>';
  });
  document.getElementById('thead').innerHTML = h;
})();

// ---- 表体：按类别分组 ----
const groups = [];
MX.rules.forEach(r=>{
  let g = groups.find(x=>x.cat===r.category);
  if(!g){ g = {cat:r.category,label:r.category_label||r.category,items:[]}; groups.push(g); }
  g.items.push(r);
});

function cellHtml(co, rule){
  const cell = cellOf(co.key, rule);
  const st = cell.status;
  const tag = st==='triggered' ? (TAG.triggered[cell.severity]||'!') : TAG[st];
  const cls = st==='triggered' ? (CLS.triggered[cell.severity]||'c-medium') : CLS[st];
  const dyn = cell.threshold_source && cell.threshold_source!=='fixed';
  const tip = rule.risk_name + '：' + LABEL[st]
    + (cell.severity_tag?('（'+cell.severity_tag+'）'):'')
    + (dyn?('　阈值 '+fmtThr(cell.threshold_value)+'（'
        + (SRCLABEL[cell.threshold_source]||cell.threshold_source)
        + '，样本 '+cell.peer_sample_n+' 家）'):'');
  return '<td class="c'+(co.conclusion_reliability==='低'?' lowrel':'')+'">'
       + '<span class="cell '+cls+(dyn?' peer':'')+'" title="'+esc(tip)+'" '
       + 'data-k="'+esc(co.key)+'" data-r="'+esc(rule.risk_id)+'">'+tag+'</span></td>';
}

function render(){
  const onlyTrig = document.getElementById('f-trig').checked;
  const onlyNe = document.getElementById('f-ne').checked;
  const onlyPeer = document.getElementById('f-peer').checked;
  let html = '', shown = 0;
  groups.forEach(g=>{
    const rows = g.items.filter(r=>{
      const cells = MX.companies.map(c=>cellOf(c.key, r));
      if(onlyTrig && !cells.some(x=>x.status==='triggered')) return false;
      if(onlyNe && !cells.some(x=>x.status==='not_evaluable')) return false;
      if(onlyPeer && !cells.some(x=>x.threshold_source && x.threshold_source!=='fixed')) return false;
      return true;
    });
    if(!rows.length) return;
    html += '<tr class="grp"><td colspan="'+(MX.companies.length+1)+'">'+esc(g.label)+'</td></tr>';
    rows.forEach(r=>{
      shown++;
      html += '<tr><td class="rule"><span class="id">'+esc(r.risk_id)+'</span>'+esc(r.risk_name)+'</td>';
      MX.companies.forEach(c=>{ html += cellHtml(c, r); });
      html += '</tr>';
    });
  });
  document.getElementById('tbody').innerHTML = html;
  document.getElementById('cnt').textContent = '显示 '+shown+' / '+MX.rules.length+' 条';
  bind();
}

function bind(){
  document.querySelectorAll('.cell').forEach(el=>{
    el.onclick = ()=>{
      const k = el.dataset.k, rid = el.dataset.r;
      const rule = MX.rules.find(r=>r.risk_id===rid)||{};
      const co = MX.companies.find(c=>c.key===k)||{};
      const cell = cellOf(k, rule);
      const st = cell.status;
      let head = '<b>'+esc(rule.risk_id)+' '+esc(rule.risk_name)+'</b>　'
               + esc(co.name)+'　·　'+LABEL[st]
               + (cell.severity_tag?('（'+esc(cell.severity_tag)+'）'):'');
      let body = cell.explanation
        ? '<div style="margin-top:6px;color:#C9D1DB">'+esc(cell.explanation)+'</div>' : '';
      let kv = '';
      if(cell.threshold_source){
        const dyn = cell.threshold_source!=='fixed';
        kv += '<div class="kv">本期阈值：<em>'+esc(fmtThr(cell.threshold_value))+'</em>'
            + '　来源：<em>'+esc(SRCLABEL[cell.threshold_source]||cell.threshold_source)+'</em>'
            + (dyn?('　样本：<em>'+esc(cell.peer_sample_n)+' 家</em>'):'')
            + '</div>';
        if(dyn) kv += '<div class="kv" style="color:#8FA0B5">动态阈值只在本公司与其同业样本之间成立，'
                    + '与同列其他公司的色块不可直接横比。</div>';
      }
      if(cell.score!=null) kv += '<div class="kv">风险分：<em>'+esc(cell.score)+'</em></div>';
      if(co.conclusion_reliability && co.conclusion_reliability!=='高'){
        kv += '<div class="kv">该公司结论可信度：<em>'+esc(co.conclusion_reliability)+'</em>'
            + '　'+esc(co.reliability_note||'')+'</div>';
      }
      document.getElementById('dbody').innerHTML = head + body + kv;
      document.getElementById('detail').style.display = 'block';
    };
  });
}

document.getElementById('f-trig').onchange = render;
document.getElementById('f-ne').onchange = render;
document.getElementById('f-peer').onchange = render;
drawMatrix();
drawCompanies();
render();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="渲染多公司风险矩阵 HTML")
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.matrix, encoding="utf-8") as f:
        mx = json.load(f)

    prof = mx.get("industry_profile") or {}
    cb = mx.get("comparability") or {}
    comps = mx.get("companies") or []
    periods = "、".join(cb.get("periods") or [])

    title = f"{prof.get('label', '')} · {len(comps)} 家公司"
    subtitle = (f"行业剖面 {prof.get('profile_id', '—')}　|　报告期 {periods or '—'}　|　"
                f"生成于 {mx.get('generated_at', '—')}　|　"
                f"规则版本 {mx.get('rules_version', '—')}")

    synthetic = any("合成" in str((c.get("source_diag") or "")) for c in comps) or \
                any("DEMO" in str(c.get("ticker") or "") for c in comps)
    if synthetic:
        banner = ("本页公司为合成演示数据（DEMO-A/B/C），仅用于验证矩阵引擎与呈现，"
                  "不得作为真实公司结论引用。")
    else:
        banner = ("矩阵只做同行业、同口径横向比较。不同行业的阈值与指标适用性不同，"
                  "跨行业结果不可比。右上角带蓝三角的格子阈值取自同业分位数，"
                  "同一条规则在不同公司的阈值并不相同。")

    html = (TEMPLATE
            .replace("__TITLE__", title)
            .replace("__SUBTITLE__", subtitle)
            .replace("__BANNER__", banner)
            .replace("__DATA__", json.dumps(mx, ensure_ascii=False)))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] matrix html -> {args.out}")
    print(f"     {len(comps)} 家公司 · {len(mx.get('rules') or [])} 条规则")


if __name__ == "__main__":
    main()
