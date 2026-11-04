"""FinScope v3 可审计估值底稿。只用 artifact_tool 写 XLSX；历史数据不可由 Excel 公式发明。

模型单位：历史/预测/估值金额=亿元，股本=亿股，每股价值=元。
蓝字=外部输入；黑字=本表公式；绿色=跨工作表公式；黄底=可编辑假设。
预测期仅按 C 已实现的经营驱动生成，明确不声称完整三表配平。
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any

from artifact_tool import Workbook, SpreadsheetFile

NAVY = "#172D46"
NAVY2 = "#345B7E"
WHITE = "#FFFFFF"
PALE = "#F2F6FA"
YELLOW = "#FFF0BC"
BLUE = "#1751D1"
GREEN = "#13805B"
RED = "#BB4242"
TEXT = "#253A50"
NUM = '#,##0.00;[Red](#,##0.00);–'
PCT = '0.0%;[Red](0.0%);–'
MULT = '0.00"x"'


def sheet(wb, name: str, title: str, source: str, width=20):
    ws = wb.worksheets.add(name)
    ws.get_range('A:A').format.column_width = 33
    ws.get_range('B:O').format.column_width = width
    ws.get_range('A1:O1').format = {'fill': NAVY, 'font': {'color': WHITE, 'bold': True, 'size': 13}, 'row_height': 29}
    ws.get_range('A1').values = [[title]]
    ws.get_range('A2').values = [[f'来源：{source} | 生成时间：{datetime.now():%Y-%m-%d %H:%M}']]
    ws.get_range('A2:O2').format = {'font': {'color': '#63788C', 'size': 9}, 'row_height': 23}
    ws.freeze_panes.freeze_rows(4)
    return ws


def v(ws, cell, value, style='input', number_format=None):
    if isinstance(value, (tuple, list, dict)):
        value = str(value)
    ws.get_range(cell).values = [[value]]
    if style == 'input' and isinstance(value, (float, int)):
        ws.get_range(cell).format.font.color = BLUE
    if number_format:
        ws.get_range(cell).set_number_format(number_format)


def f(ws, cell, expression, kind='cross', number_format=NUM):
    ws.get_range(cell).formulas = [[expression]]
    ws.get_range(cell).format.font.color = GREEN if kind == 'cross' else TEXT
    if number_format:
        ws.get_range(cell).set_number_format(number_format)


def hdr(ws, row, texts):
    last = chr(65+len(texts)-1)
    ws.get_range(f'A{row}:{last}{row}').values = [texts]
    ws.get_range(f'A{row}:{last}{row}').format = {
        'fill': NAVY2, 'font': {'color': WHITE, 'bold': True}, 'row_height': 25,
    }


def fmt_cells(ws, first, last, form=NUM):
    ws.get_range(f'{first}:{last}').set_number_format(form)


def rget(xs, index, ratio=False):
    if not isinstance(xs, list):
        return None
    return xs[index] if 0 <= index < len(xs) else None


def money(x):
    return x / 1e8 if isinstance(x, (float, int)) else None


def add_raw_source(ws, row, label, records, key):
    rec = records.get(key) if isinstance(records, dict) else None
    v(ws, f'A{row}', label, 'text')
    if isinstance(rec, dict):
        v(ws, f'G{row}', rec.get('source_id') or '', 'text')
        v(ws, f'H{row}', rec.get('source') or '', 'text')
        v(ws, f'I{row}', rec.get('source_url') or '', 'text')
        v(ws, f'J{row}', rec.get('status') or '', 'text')
        v(ws, f'K{row}', rec.get('scope') or rec.get('basis') or '', 'text')


def add_driver_sheets(wb, result: dict, source_name: str) -> None:
    """Fully linked 3-statement extension, only when opening balance is supplied.
    All workbook monetary amounts are 亿人民币; ratios and days are editable.
    """
    op=result.get('operating_forecast') or {}
    if not op.get('ok'):
        return
    cfg=op.get('inputs_snapshot') or {}
    rr=op.get('rows') or []
    n=len(rr); segs=cfg.get('segments') or []
    if not n or not segs: return
    stage=sheet(wb,'业务分部驱动','分业务经营预测（亿元；蓝字假设、黑字联动）', source_name)
    hdr(stage,4,['预测年份','分部','上年收入（亿）','收入增长率','预测收入（亿）',
                 '毛利率','经营费用率','预测毛利润（亿）','预测EBIT（亿）','预测COGS（亿）'])
    rowmap={}
    ix=5
    for sc in segs:
        name=sc['name']
        for j in range(n):
            rowmap[(name,j)]=ix
            v(stage,f'A{ix}',rr[j]['year'],'text');v(stage,f'B{ix}',name,'text')
            if j==0:v(stage,f'C{ix}',money(sc['base_revenue']),number_format=NUM)
            else:f(stage,f'C{ix}',f'=E{ix-1}','local')
            v(stage,f'D{ix}',sc['growth_path'][j],number_format=PCT)
            f(stage,f'E{ix}',f'=C{ix}*(1+D{ix})','local')
            v(stage,f'F{ix}',sc['gross_margin_path'][j],number_format=PCT)
            v(stage,f'G{ix}',sc['opex_ratio_path'][j],number_format=PCT)
            f(stage,f'H{ix}',f'=E{ix}*F{ix}','local')
            f(stage,f'I{ix}',f'=H{ix}-E{ix}*G{ix}','local')
            f(stage,f'J{ix}',f'=E{ix}-H{ix}','local')
            ix+=1
    stage.get_range('B:B').format.column_width=36
    inp=sheet(wb,'三表驱动假设','运营周转、资本开支、融资假设（原始金额显示亿元）',source_name)
    hdr(inp,4,['年度','税率','D&A/收入','CAPEX/收入','应收周转天数','存货周转天数',
               '应付周转天数','利息成本率','净债务变动（亿）','股利（亿）','权益融资（亿）',
               '其他经营NWC期初（亿）','其他经营NWC/收入'])
    for j,r in enumerate(rr,5):
        i=j-5
        v(inp,f'A{j}',r['year'],'text')
        for col,key in [('B','tax_rate'),('C','da_ratio_path'),('D','capex_ratio_path'),
                        ('E','dso_days_path'),('F','dio_days_path'),('G','dpo_days_path'),
                        ('H','interest_rate_path'),('I','debt_change_path'),('J','dividend_path'),
                        ('K','equity_issue_path'),('M','other_nwc_ratio_path')]:
            obj=cfg.get(key)
            val=obj[i] if isinstance(obj,list) else obj
            if col in ('I','J','K'): val=money(val) if val is not None else 0
            if val is None:val=0
            v(inp,f'{col}{j}',val,number_format=PCT if col in ('B','C','D','H','M') else NUM)
        v(inp,f'L{j}',money(cfg.get('other_nwc_opening') or 0),number_format=NUM)
    if op.get('mode') != 'three_statement':
        return
    init=cfg.get('opening_balance') or {}
    base_nwc=(init['receivables']+init['inventory']-init['payables'])/1e8
    forecast=sheet(wb,'三表联动预测','利润表、现金流量表及资产负债表联动（单位：亿元）',source_name)
    hdr(forecast,4,['年度','营业收入','营业成本','EBIT','D&A','CAPEX','应收','存货','应付','经营NWC','ΔNWC',
                    'NOPAT','FCFF','利息','利润总额','所得税','净利润','CFO','CFI','CFF',
                    '期末现金','期末PPE','期末有息债务','期末权益','资产合计','负债及权益合计','平衡差额'])
    for j,r in enumerate(rr,5):
        ix=j-5; prev=j-1
        v(forecast,f'A{j}',r['year'],'text')
        def sum_seg(col):
            refs=[f"'业务分部驱动'!{col}{rowmap[(seg['name'],ix)]}" for seg in segs]
            return '='+'+'.join(refs)
        for col,cc in [('B','E'),('C','J'),('D','I')]:f(forecast,f'{col}{j}',sum_seg(cc))
        for col,expr in [
            ('E',f"=B{j}*'三表驱动假设'!C{j}"),
            ('F',f"=B{j}*'三表驱动假设'!D{j}"),
            ('G',f"=B{j}*'三表驱动假设'!E{j}/365"),
            ('H',f"=C{j}*'三表驱动假设'!F{j}/365"),
            ('I',f"=C{j}*'三表驱动假设'!G{j}/365"),
            ('J',f"=G{j}+H{j}-I{j}+B{j}*'三表驱动假设'!M{j}"),
            ('K',f'=J{j}-'+(str(base_nwc) if ix==0 else f'J{prev}')),
            ('L',f"=D{j}-MAX(0,D{j})*'三表驱动假设'!B{j}"),
            ('M',f'=L{j}+E{j}-F{j}-K{j}'),
            ('W',(f"={money(init['debt'])}+'三表驱动假设'!I{j}" if ix==0
                  else f"=W{prev}+'三表驱动假设'!I{j}")),
            ('N',(f"=({money(init['debt'])}+W{j})/2*'三表驱动假设'!H{j}" if ix==0
                  else f"=(W{prev}+W{j})/2*'三表驱动假设'!H{j}")),
            ('O',f'=D{j}-N{j}'),
            ('P',f"=MAX(0,O{j})*'三表驱动假设'!B{j}"),
            ('Q',f'=O{j}-P{j}'),
            ('R',f'=Q{j}+E{j}-K{j}'),
            ('S',f'=-F{j}'),
            ('T',f"='三表驱动假设'!I{j}-'三表驱动假设'!J{j}+'三表驱动假设'!K{j}"),
            ('U',(f'={money(init["cash"])}+R{j}+S{j}+T{j}' if ix==0
                  else f'=U{prev}+R{j}+S{j}+T{j}')),
            ('V',(f'={money(init["ppe"])}+F{j}-E{j}' if ix==0
                  else f'=V{prev}+F{j}-E{j}')),
            ('X',(f"={money(init['equity'])}+Q{j}-'三表驱动假设'!J{j}+'三表驱动假设'!K{j}" if ix==0
                  else f"=X{prev}+Q{j}-'三表驱动假设'!J{j}+'三表驱动假设'!K{j}")),
            ('Y',f'=U{j}+G{j}+H{j}+V{j}+{money(init["other_assets"])}'),
            ('Z',f'=I{j}+W{j}+X{j}+{money(init["other_liabilities"])}+{money(init.get("minority_interest",0))}'),
            ('AA',f'=Y{j}-Z{j}')]:
            f(forecast,f'{col}{j}',expr,'local')
        v(forecast,f'AB{j}',r['fcff']/1e8,number_format=NUM)
        f(forecast,f'AC{j}',f'=M{j}-AB{j}','local')
    forecast.get_range('A:A').format.column_width=13
    forecast.get_range('B:AC').format.column_width=16
    v(forecast,'A12','模型说明：本表预测期财务三表可按蓝字假设联动，未覆盖收购、租赁、商誉减值、外币折算及所得税递延项目。','text')
    v(forecast,'A13','AA列需始终为零，AC列为对后端 FCFF 独立勾稽；修改参数后需要重新核对两列。','text')


def render(result: dict, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook.create()
    comp = result.get('company') or {}
    history = result.get('history') or {}
    financials = result.get('historical_financials') or {}
    records = result.get('financial_records') or {}
    dcf = result.get('dcf') or {}
    comps = result.get('comps') or result.get('relative') or {}
    sotp = result.get('sotp') or {}
    ddm = result.get('ddm') or {}
    blended = result.get('blended') or {}
    market = result.get('market_data') or {}
    sources = result.get('sources') or []
    company = comp.get('name') or comp.get('ticker') or '目标公司'
    source_name = (result.get('data_source') or {}).get('used') or '统一财务对象'
    hyears = (history.get('years') or [])[-5:]
    actual_years = list(hyears)
    h_indices = list(range(max(len(history.get('years') or [])-5, 0), len(history.get('years') or [])))
    prows = list(dcf.get('rows') or [])[:8]
    n = len(prows)
    nf = min(n, 5)
    R = lambda s: f"'{s}'!"
    note = sheet(wb, '底稿说明', f'{company} | FinScope 可审计估值底稿', source_name)
    lines = [
        '估值基准 / 股票代码', f"{comp.get('ticker','')} / {result.get('as_of','')}",
        '数据口径', '年度 + 合并报表优先；原始数据来自 A/D unified 或独立联网模式',
        '金额单位', '所有报表及估值金额均为亿元；股本为亿股；每股为元',
        '模型范围', '预测仅覆盖 EBIT、税额、D&A、CAPEX、ΔNWC 和 FCFF；不能代替完整预测三表',
        '数据完整性', f'实际年度 {len(actual_years)} 年（如不足 5 年保留缺口，不补造数据）',
        '修改方法', '蓝字为原始输入，黄色底纹为可调假设；公式引用跨表不硬编码',
        '终值方法', str(dcf.get('terminal_method') or '不可用'),
        '估值可靠性', f"{blended.get('confidence') or '未评分'} / {blended.get('verdict') or '未评估'}",
        '公式校验', '计算值与运行时后端结果可能随假设修改产生差异；以同一次重新计算的模型为准',
        '敏感性刷新', 'DCF WACC×g 每格公式可联动；增长率×利润率矩阵需要重新运行完整后端',
        '缺失数据', '年报未披露、未映射、口径不一致均保留空白，不将缺项认定为 0',
        '声明', '研究与教学用途，不构成投资建议；暂未进行桌面版 Excel 引擎重算校验',
    ]
    hdr(note, 4, ['项目', '说明'])
    for i in range(0,len(lines),2):
        v(note, f'A{5+i//2}',lines[i], 'text');v(note,f'B{5+i//2}',lines[i+1],'text')
    note.get_range('B:B').format.column_width = 79

    a = sheet(wb, '参数假设', '估值与预测关键参数（黄底蓝字可调）', source_name)
    hdr(a, 4, ['项目','采用值','来源/解释'])
    cash = financials.get('cash') if financials.get('cash') is not None else dcf.get('cash')
    debt = financials.get('total_debt') if financials.get('total_debt') is not None else dcf.get('debt')
    minority = financials.get('minority_interest') if financials.get('minority_interest') is not None else dcf.get('minority_interest')
    preferred = financials.get('preferred_stock') if financials.get('preferred_stock') is not None else dcf.get('preferred_stock')
    pairs = [
        (6,'WACC（采用）',dcf.get('wacc'),'后端规则 / CAPM + 市场隐含调整'),
        (7,'永续增长率 g',dcf.get('terminal_growth'),'后端规则 / 行业上限'),
        (8,'现金税率',dcf.get('tax_rate'),'后端 rules 与历史税负'),
        (9,'EBIT 利润率',dcf.get('ebit_margin'),'历史利润率与规则'),
        (10,'D&A/收入',dcf.get('da_pct'),'历史/模型估计'),
        (11,'CAPEX/收入',dcf.get('capex_pct'),'历史/模型估计'),
        (12,'ΔNWC/收入',dcf.get('nwc_pct'),'历史/模型估计'),
        (13,'退出 EV/EBITDA 倍数',dcf.get('exit_multiple'),'可比公司同业中位或披露的兜底'),
        (14,'现金及现金等价物（亿）',money(cash),'优先 A/D 合并财务；必要时沿用 C 的本次 DCF 股权价值桥接输入'),
        (15,'有息负债（亿）',money(debt),'优先 A/D 合并财务；必要时沿用 C 的本次 DCF 股权价值桥接输入'),
        (16,'少数股东权益（亿）',money(minority),'优先 A/D 财务；必要时沿用 C 的本次 DCF 股权价值桥接输入'),
        (17,'优先股（亿）',money(preferred),'优先 A/D 财务；必要时沿用 C 的本次 DCF 股权价值桥接输入'),
        (18,'总股本（亿股）', market.get('shares_outstanding')/1e8 if market.get('shares_outstanding') else None,'D 统一 market_data，不独立取价'),
        (19,'当前股价（元）', market.get('price'),'D 统一 market_data'),
        (20,'预测年度数',nf,'后端模型实际预测期'),
        (21,'历史基准收入（亿）',money(dcf.get('base_revenue') or (history.get('revenue') or [None])[-1]),'A/D 历史财务'),
        (22,'终值 ROIC',dcf.get('terminal_roic'),'后端假设/规则'),
    ]
    for rr, label, value, explanation in pairs:
        v(a, f'A{rr}',label, 'text');v(a,f'B{rr}',value);v(a,f'C{rr}',explanation,'text')
        if rr not in (14,15,16,17,18,19,20,21):a.get_range(f'B{rr}').format.fill = YELLOW
        if rr in (6,7,8,9,10,11,12,22):a.get_range(f'B{rr}').set_number_format(PCT)
        else:a.get_range(f'B{rr}').set_number_format(NUM)
    hdr(a, 24, ['年度','首年/后续收入增长率','假设性质'])
    for i, row in enumerate(prows[:5]):
        v(a,f'A{25+i}',str(row.get('year'))+'E','text')
        v(a,f'B{25+i}',row.get('growth'),number_format=PCT)
        a.get_range(f'B{25+i}').format.fill=YELLOW
        v(a,f'C{25+i}','可按逐年路径覆盖；当前采自后端 DCF', 'text')
    a.get_range('C:C').format.column_width=74

    # 三大报表：仅历史，不将未获得的详细科目补 0。
    keys = {
       '历史利润表': [('营业收入','revenue'),('营业成本','cogs'),('毛利润','gross_profit'),('EBIT（经营利润口径）','ebit'),('税前利润','pretax_income'),('所得税费用','tax_provision'),('净利润','net_income'),('归母净利润','net_income_parent')],
       '历史资产负债表':[('现金及现金等价物','cash'),('总资产','total_assets'),('总权益','total_equity'),('有息负债','total_debt'),('流动资产','current_assets'),('流动负债','current_liabilities'),('应收账款','receivables'),('存货','inventory'),('应付账款','payables')],
       '历史现金流量表':[('经营现金流净额','cfo'),('折旧摊销','da'),('资本开支','capex'),('营运资本变动','delta_nwc'),('股利支付','dividends_paid')],
    }
    canonical_mapping={'cogs':'operating_cost','ebit':'operating_profit','pretax_income':'pretax_profit','tax_provision':'income_tax_expense','da':'depreciation_amortization','cash':'cash_and_equivalents','receivables':'accounts_receivable','payables':'accounts_payable','dividends_paid':'dividend_paid'}
    for tab,rows in keys.items():
        ws = sheet(wb,tab,tab+'（历史已取财务值，不补造）',source_name)
        cols=['科目']+[f'{y}A' for y in actual_years]+['来源ID','原始来源','来源链接','数据状态','报表口径']
        hdr(ws,4,cols)
        ws.get_range('H:H').format.column_width=44
        ws.get_range('I:I').format.column_width=56
        for j,(label,key) in enumerate(rows,5):
            v(ws,f'A{j}',label,'text')
            src_key=canonical_mapping.get(key,key)
            rec=records.get(src_key) if isinstance(records,dict) else None
            for i,idx in enumerate(h_indices):
                raw=(history.get(key) or [])
                value = money(rget(raw,idx)) if isinstance(raw,list) else None
                if value is None and isinstance(rec,dict):
                    series=rec.get('series') or {}
                    yr=actual_years[i]
                    value=money(series.get(str(yr),series.get(yr)))
                if key=='total_debt':
                    value=money(debt) if i==len(h_indices)-1 else None
                elif key in ('cash','total_assets','total_equity','current_assets','current_liabilities','inventory','receivables','payables'):
                    value=money(cash if key=='cash' else financials.get(key)) if i==len(h_indices)-1 else None
                v(ws,f'{chr(66+i)}{j}',value,number_format=NUM)
            if isinstance(rec,dict):
                c=1+len(h_indices)
                for x in [rec.get('source_id'),rec.get('source'),rec.get('source_url'),rec.get('status'),rec.get('scope')]:
                    if c<15:v(ws,f'{chr(65+c)}{j}',x,'text');c+=1
    # 历史经营/收入和利润总表（脚本输入）
    y = sheet(wb,'历史指标','历史经营指标与增长质量',source_name)
    hdr(y,4,['项目']+[f'{yr}A' for yr in actual_years])
    for rr,(label,key,p) in enumerate([
       ('营业收入','revenue',False),('收入增速','revenue_growth',True),
       ('EBIT','ebit',False),('EBIT利润率','ebit_margin',True),
       ('净利润','net_income',False),('净利润率','net_margin',True),
       ('经营现金流净额','cfo',False),('资本开支','capex',False),
       ('折旧摊销','da',False),('毛利率','gross_margin',True),
       ('资本开支/收入','capex_pct',True),('折旧摊销/收入','da_pct',True)
    ],5):
        v(y,f'A{rr}',label,'text')
        for ii,idx in enumerate(h_indices):
            val=rget(history.get(key),idx)
            v(y,f'{chr(66+ii)}{rr}',val if p else money(val),number_format=PCT if p else NUM)

    # DCF 中间预测；全部依据参数页，历史起点链接参数假设!B21。
    p = sheet(wb,'预测经营与FCFF','预测经营指标和自由现金流（五年，公式联动）', '参数假设 + 历史基准收入')
    hdr(p,4,['项目']+[f'{rr.get("year")}E' for rr in prows[:5]])
    lbl={5:'收入增速',6:'营业收入（亿）',7:'EBIT（亿）',8:'现金税额（亿）',9:'NOPAT（亿）',10:'折旧摊销（亿）',11:'资本开支（亿）',12:'营运资本增加（亿）',13:'FCFF（亿）',14:'期中折现系数',15:'FCFF现值（亿）',16:'EBITDA（亿）',17:'EBIT利润率',18:'现金税率'}
    for rr,name in lbl.items():v(p,f'A{rr}',name,'text')
    for i in range(nf):
        col=chr(66+i);prev=chr(65+i)
        f(p,f'{col}5',f"='{a.name}'!B{25+i}",number_format=PCT)
        f(p,f'{col}6',(f"='{a.name}'!$B$21*(1+{col}5)" if i==0 else f'={prev}6*(1+{col}5)'),kind='local')
        for rr, expr in {
           7:f"={col}6*'参数假设'!$B$9",8:f"={col}7*'参数假设'!$B$8",9:f'={col}7-{col}8',
           10:f"={col}6*'参数假设'!$B$10",11:f"={col}6*'参数假设'!$B$11",12:f"={col}6*'参数假设'!$B$12",
           13:f'={col}9+{col}10-{col}11-{col}12',14:f"=1/(1+'参数假设'!$B$6)^({i}+0.5)",
           15:f'={col}13*{col}14',16:f'={col}7+{col}10',17:f'={col}7/{col}6',18:f'={col}8/{col}7'
        }.items():f(p,f'{col}{rr}',expr,kind='local',number_format=PCT if rr in (17,18) else ('0.00000' if rr==14 else NUM))
    p.get_range(f'A13:{chr(66+nf-1)}13').format.fill=PALE
    p.get_range(f'A15:{chr(66+nf-1)}15').format.fill=PALE

    w = sheet(wb,'WACC测算','权益成本与加权资本成本',source_name)
    hdr(w,4,['项目','数值','解释/来源'])
    wbk=dcf.get('wacc_block') or {}
    for rr,lab,key in [(5,'无风险利率 Rf','risk_free'),(6,'股权风险溢价 ERP','erp'),(7,'Beta','beta'),(8,'规模溢价','size_premium'),(9,'税前债务成本','cost_of_debt'),(10,'目标债务比率','debt_ratio'),(11,'税率','tax_rate'),(15,'市场隐含WACC','implied_wacc')]:
        v(w,f'A{rr}',lab,'text');v(w,f'B{rr}',wbk.get(key) if key != 'implied_wacc' else dcf.get('implied_wacc'),number_format=PCT if key != 'beta' else NUM)
    v(w,'A12','股权资本成本 Ke','text');f(w,'B12','=B5+B7*B6+B8','local',PCT)
    v(w,'A13','CAPM WACC','text');f(w,'B13','=B12*(1-B10)+B9*(1-B11)*B10','local',PCT)
    v(w,'A14','模型采用 WACC','text');f(w,'B14',"='参数假设'!B6",number_format=PCT)
    v(w,'A17','规则校准说明','text');v(w,'B17',dcf.get('wacc_source') or '不适用','text')
    w.get_range('B:B').format.column_width=29
    w.get_range('C:C').format.column_width=50

    d = sheet(wb,'DCF估值','DCF / FCFF 期中折现与终值', '预测经营与FCFF + 参数假设')
    hdr(d,4,['项目','公式结果','后端基准值（校验）'])
    terms=[(5,'显式期FCFF现值（亿）'),(6,'Gordon终值（亿）'),(7,'退出倍数终值（亿）'),(8,'ROIC再投资终值（亿）'),(9,'采用终值（亿）'),(10,'终值现值（亿）'),(11,'企业价值EV（亿）'),(12,'+现金（亿）'),(13,'-有息负债（亿）'),(14,'-少数股东权益（亿）'),(15,'-优先股（亿）'),(16,'股权价值（亿）'),(17,'每股价值（元）'),(18,'模型差异（元/股）'),(19,'终值现值/EV')]
    for rr,label in terms:v(d,f'A{rr}',label,'text')
    last=chr(66+nf-1) if nf else 'B'
    if nf:
        form={
            5:f"=SUM('预测经营与FCFF'!B15:{last}15)",
            6:f"='预测经营与FCFF'!{last}13*(1+'参数假设'!B7)/('参数假设'!B6-'参数假设'!B7)",
            7:f"='预测经营与FCFF'!{last}16*'参数假设'!B13",
            8:f"='预测经营与FCFF'!{last}9*(1+'参数假设'!B7)*(1-'参数假设'!B7/'参数假设'!B22)/('参数假设'!B6-'参数假设'!B7)",
            9:"=B6" if dcf.get('terminal_method')=='gordon' else ("=B7" if dcf.get('terminal_method')=='exit' else ("=B8" if dcf.get('terminal_method')=='roic' else '=AVERAGE(B6:B7)')),
            10:f"=B9/(1+'参数假设'!B6)^'参数假设'!B20",
            11:'=SUM(B5,B10)',12:"='参数假设'!B14",13:"='参数假设'!B15",14:"='参数假设'!B16",15:"='参数假设'!B17",
            16:'=B11+B12-B13-B14-B15',17:"=IFERROR(B16/'参数假设'!B18,\"\")",18:'=IFERROR(B17-C17,"")',19:'=IFERROR(B10/B11,"")'
        }
        for rr,expr in form.items():f(d,f'B{rr}',expr,number_format=PCT if rr==19 else NUM)
    for rr,key in [(5,'pv_explicit'),(6,'tv_gordon'),(7,'tv_exit'),(8,'tv_roic'),(9,'tv_base'),(10,'pv_terminal'),(11,'enterprise_value'),(16,'equity_value')]:
        v(d,f'C{rr}',money(dcf.get(key)),number_format=NUM)
    v(d,'C17',dcf.get('per_share'),number_format=NUM)
    v(d,'C19',dcf.get('tv_ratio'),number_format=PCT)
    d.get_range('A17:C17').format={'fill':YELLOW,'font':{'bold':True, 'color':NAVY}}

    pe = sheet(wb,'可比公司明细','Comps 公司原始财务与倍数（比例由公式计算）',source_name)
    peerrows=(comps.get('peers_detail') or comps.get('peer_companies') or [])
    hdr(pe,4,['公司名称','股票代码','市值（亿）','营收（亿）','净利（亿）','权益（亿）','EBITDA（亿）','企业价值（亿）','PE','PS','PB','EV/EBITDA','选择理由','数据源','取数日'])
    pe.get_range('M:M').format.column_width=47
    pe.get_range('N:N').format.column_width=33
    for ix,pv in enumerate(peerrows,5):
        v(pe,f'A{ix}',pv.get('name'),'text');v(pe,f'B{ix}',pv.get('ticker'),'text')
        for col,key in [('C','market_cap'),('D','revenue'),('E','net_income'),('F','equity'),('G','ebitda')]:v(pe,f'{col}{ix}',money(pv.get(key)),number_format=NUM)
        net_debt=pv.get('net_debt')
        if net_debt is not None:
            v(pe,f'O{ix}',money(net_debt),number_format=NUM)
            f(pe,f'H{ix}',f'=IF(C{ix}="","",C{ix}+O{ix})','local')
        for col,numer,denom in [('I','C','E'),('J','C','D'),('K','C','F'),('L','H','G')]:
            f(pe,f'{col}{ix}',f'=IFERROR({numer}{ix}/{denom}{ix},"")','local',MULT)
        v(pe,f'M{ix}',pv.get('selection_reason') or '', 'text')
        v(pe,f'N{ix}',pv.get('source') or '未注明','text')
        v(pe,f'P{ix}',pv.get('as_of') or '', 'text')
    hdr(pe,5+len(peerrows),['样本中位数','','','','','','','','PE','PS','PB','EV/EBITDA'])
    medrow=5+len(peerrows)
    if peerrows:
        for col in 'IJKL':f(pe,f'{col}{medrow}',f'=IFERROR(MEDIAN({col}5:{col}{medrow-1}),"")','local',MULT)

    cp = sheet(wb,'相对估值','多倍数调整及隐含股权价值',source_name)
    hdr(cp,4,['倍数','同业中位（公式）','调整比例','采用倍数','基准财务指标（亿）','隐含股权价值（亿）','隐含每股（元）','后端每股（元）','口径说明'])
    selected=comps.get('results') or []
    col_map={'pe':'I','ps':'J','pb':'K','ev_ebitda':'L'}
    for ix,rec in enumerate(selected,5):
        key=rec.get('multiple')
        v(cp,f'A{ix}',rec.get('label') or key or '', 'text')
        if key in col_map and peerrows:f(cp,f'B{ix}',f"='可比公司明细'!{col_map[key]}{medrow}",number_format=MULT)
        else:v(cp,f'B{ix}',rec.get('peer_median'),number_format=MULT)
        v(cp,f'C{ix}',rec.get('adjustment'),number_format=PCT)
        f(cp,f'D{ix}',f'=B{ix}*(1+C{ix})','local',MULT)
        v(cp,f'E{ix}',money(rec.get('metric_value')),number_format=NUM)
        is_ev=bool(str(key).startswith('ev_'))
        f(cp,f'F{ix}',(f"=D{ix}*E{ix}-'参数假设'!B15+'参数假设'!B14" if is_ev else f'=D{ix}*E{ix}'),'local')
        f(cp,f'G{ix}',f"=IFERROR(F{ix}/'参数假设'!B18,\"\")",number_format=NUM)
        v(cp,f'H{ix}',rec.get('implied_per_share'),number_format=NUM)
        v(cp,f'I{ix}',rec.get('metric_basis') or '实际采用财务口径以 C 规则为准','text')
    cp.get_range('I:I').format.column_width=53

    st = sheet(wb,'SOTP分部估值','分部指标 × 倍数 → 股权价值',source_name)
    hdr(st,4,['分部','指标类型','估值指标（亿）','选择倍数','分部EV（亿）','后端EV（亿）','同业/来源说明'])
    segment_rows=sotp.get('rows') or []
    for rr,seg in enumerate(segment_rows,5):
        v(st,f'A{rr}',seg.get('name'),'text');v(st,f'B{rr}',seg.get('metric_type') or seg.get('multiple_type') or '', 'text')
        v(st,f'C{rr}',money(seg.get('value')),number_format=NUM)
        v(st,f'D{rr}',seg.get('multiple'),number_format=MULT)
        f(st,f'E{rr}',f'=C{rr}*D{rr}','local')
        v(st,f'F{rr}',money(seg.get('segment_ev')),number_format=NUM)
        v(st,f'G{rr}', '、'.join(seg.get('peer_names') or []) or seg.get('source') or '', 'text')
    st.get_range('G:G').format.column_width=44
    srow=5+len(segment_rows)
    v(st,f'A{srow}','分部EV合计','text')
    if segment_rows:f(st,f'E{srow}',f'=SUM(E5:E{srow-1})','local')
    v(st,f'A{srow+1}','总部费用（亿）','text');v(st,f'F{srow+1}',money(sotp.get('corporate_cost')),number_format=NUM)
    v(st,f'A{srow+2}','后端SOTP每股价值（元）','text');v(st,f'F{srow+2}',sotp.get('per_share'),number_format=NUM)

    blend = sheet(wb,'融合估值','可靠性权重与方法间交叉验证',source_name)
    hdr(blend,4,['方法','计算每股（元）','采用权重','加权贡献','后端每股（元）','可靠性（分）'])
    components = blended.get('components') or []
    reliabilities = result.get('reliabilities') or {}
    for ix,cr in enumerate(components,5):
        key=cr.get('key')
        v(blend,f'A{ix}',cr.get('label') or key,'text')
        formula={'dcf':"='DCF估值'!B17",'comps':"=IFERROR(AVERAGE('相对估值'!G5:G18),\"\")",'sotp':f"='SOTP分部估值'!F{srow+2}"}
        if key in formula:f(blend,f'B{ix}',formula[key])
        else:v(blend,f'B{ix}',cr.get('per_share'),number_format=NUM)
        v(blend,f'C{ix}',cr.get('weight'),number_format=PCT)
        f(blend,f'D{ix}',f'=B{ix}*C{ix}','local')
        v(blend,f'E{ix}',cr.get('per_share'),number_format=NUM)
        rv=reliabilities.get(key) or {}
        v(blend,f'F{ix}',rv.get('score') if isinstance(rv,dict) else rv)
    tail=5+len(components)
    v(blend,f'A{tail}','综合估值（元/股）','text')
    if components:f(blend,f'B{tail}',f'=SUM(D5:D{tail-1})','local')
    v(blend,f'E{tail}',blended.get('blended_per_share'),number_format=NUM)
    v(blend,f'A{tail+1}','较现价上涨空间','text')
    if components:f(blend,f'B{tail+1}',f"=IFERROR(B{tail}/'参数假设'!B19-1,\"\")",number_format=PCT)
    v(blend,f'E{tail+1}',blended.get('upside'),number_format=PCT)
    v(blend,f'A{tail+2}','估值分歧与权重解释','text')
    v(blend,f'B{tail+2}',blended.get('weight_source') or '','text')
    blend.get_range('B:B').format.column_width=75
    # 公式联动敏感性：每个格子独立重算预测期现值与终值；无效 g>=WACC 用空值。
    wg=(result.get('sensitivity') or {}).get('wacc_g') or {}
    sw=sheet(wb,'敏感性-WACC与g','DCF WACC × g 敏感性（联动公式）','预测经营与FCFF + 参数假设')
    hdr(sw,4,['WACC / g']+[f'{x*100:.2f}%' for x in (wg.get('growth_axis') or [])])
    ws_axis=wg.get('wacc_axis') or []
    gs_axis=wg.get('growth_axis') or []
    if nf and ws_axis and gs_axis:
        for c,g in enumerate(gs_axis,1):v(sw,f'{chr(65+c)}5',g,number_format=PCT)
        for ri,wacc in enumerate(ws_axis,6):
            v(sw,f'A{ri}',wacc,number_format=PCT)
            for ci,g in enumerate(gs_axis,1):
                col=chr(65+ci)
                fcffpv='+'.join(f"'预测经营与FCFF'!{chr(66+i)}13/(1+$A{ri})^({i}+0.5)" for i in range(nf))
                final_fcf=f"'预测经营与FCFF'!{last}13"
                final_ebitda=f"'预测经营与FCFF'!{last}16"
                term_expr=(f'{final_fcf}*(1+{col}$5)/($A{ri}-{col}$5)' if dcf.get('terminal_method')=='gordon' else
                           (f'{final_ebitda}*\'参数假设\'!$B$13' if dcf.get('terminal_method')=='exit' else
                            f'({final_fcf}*(1+{col}$5)/($A{ri}-{col}$5)+{final_ebitda}*\'参数假设\'!$B$13)/2'))
                val=f"=IF($A{ri}<={col}$5,\"\",(({fcffpv})+({term_expr})/(1+$A{ri})^{nf}+'参数假设'!$B$14-'参数假设'!$B$15-'参数假设'!$B$16-'参数假设'!$B$17)/'参数假设'!$B$18)"
                f(sw,f'{col}{ri}',val,'local')
        sw.get_range(f'B6:{chr(65+len(gs_axis))}{5+len(ws_axis)}').conditional_formats.add_color_scale({'minColor':'#EAF3FC','midColor':'#BBD8ED','maxColor':'#3879AB'})
    gm=(result.get('sensitivity') or {}).get('growth_margin') or {}
    sg=sheet(wb,'敏感性-增长与利润率','收入增长 × EBIT 利润率（后端逐格重算基准快照）',source_name)
    hdr(sg,4,['首年增速 / 利润率']+[f'{x*100:.2f}%' for x in (gm.get('margin_axis') or [])])
    for ri, growth in enumerate(gm.get('growth_axis') or [],5):
        v(sg,f'A{ri}',growth,number_format=PCT)
        for ci,value in enumerate((gm.get('matrix') or gm.get('grid') or [])[ri-5] if ri-5<len(gm.get('matrix') or gm.get('grid') or []) else [],1):
            v(sg,f'{chr(65+ci)}{ri}',value,number_format=NUM)
    v(sg,'A13','注意：修改任一关键参数后需要后端重新计算本矩阵。','text')
    asum=sheet(wb,'假设台账','采用假设、生成规则、来源与置信度',source_name)
    hdr(asum,4,['假设名称','采用值','单位','依据类型','来源/公式','置信度','可覆盖','说明'])
    asum.get_range('E:E').format.column_width=76
    for ri,item in enumerate(result.get('assumptions') or [],5):
        for ci,key in enumerate(['name','value','unit','source_type','source','confidence','overridable','note']):
            v(asum,f'{chr(65+ci)}{ri}',item.get(key),'text' if key!='value' else 'input')
    src=sheet(wb,'数据来源','每个数据源及取数日期',source_name)
    hdr(src,4,['用途','来源名称','数据时间','官网/地址','原始字段','证据说明'])
    src.get_range('B:B').format.column_width=45
    src.get_range('D:D').format.column_width=75
    for ri,item in enumerate(sources,5):
        for col,key in [('A','purpose'),('B','name'),('C','as_of'),('D','source_url'),('E','source_field'),('F','note')]:
            v(src,f'{col}{ri}',item.get(key) or (item.get('source') if key=='name' else '') or '', 'text')
    gate=sheet(wb,'校验与风险','估值方法差异、核验事项和边界',source_name)
    hdr(gate,4,['类型','事项','严重程度','关联路径 / 说明'])
    cur=5
    for item in result.get('gates') or []:
        for col,key in [('A','code'),('B','message'),('C','severity')]:v(gate,f'{col}{cur}',item.get(key),'text')
        v(gate,f'D{cur}',str(item.get('affected_paths') or ''),'text');cur+=1
    for item in result.get('warnings') or []:
        v(gate,f'A{cur}','warning','text');v(gate,f'B{cur}',item,'text');cur+=1
    gate.get_range('B:B').format.column_width=90
    gate.get_range('D:D').format.column_width=46
    add_driver_sheets(wb,result,source_name)
    # 保存 xlsx；真正的 Excel native EXCEL_OK 必须运行另附验证脚本。
    SpreadsheetFile.export_xlsx(wb).save(str(path))
    return path
