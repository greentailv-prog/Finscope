"""Fast artifact_tool-only financial forecast workbook, bulk-write first.
No substitute for desktop Excel recalc; audit independently after export.
"""
from pathlib import Path
from artifact_tool import Workbook, SpreadsheetFile


def render(result:dict,output:str|Path)->Path:
    proj=result.get('operating_forecast') or {}
    if not proj.get('ok') or proj.get('mode')!='three_statement':
        raise ValueError('仅完整分业务联动三表可用此导出器')
    cfg=proj['inputs_snapshot']; rows=proj['rows']; segs=cfg['segments']; n=len(rows)
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    wb=Workbook.create()
    s=wb.worksheets.add('分部收入与EBIT')
    a=wb.worksheets.add('三表驱动参数')
    x=wb.worksheets.add('三表联动预测')
    z=wb.worksheets.add('财务一致性校验')
    w=wb.worksheets.add('DCF验证')
    # worksheet 1, 10 rows and 6 input/formula columns
    s.get_range('A1:J2').values=[
      ['FinScope v3.2 分业务收入与利润驱动（亿元）']+['']*9,
      ['所有蓝字历史输入来自用户/上游；预测增长、毛利与费用率为分析师情景，不是已披露事实']+['']*9]
    s.get_range('A4:L4').values=[['年份','业务','上年营收','增长率','本年营收','毛利率','期间费用率','毛利润','EBIT','营业成本','历史收入来源URL','预测假设说明']]
    input_rows=[];formula_sales=[];formula_profit=[];row_refs={}
    ri=5
    for seg in segs:
        for j in range(n):
            input_rows.append([rows[j]['year'],seg['name'],seg['base_revenue']/1e8 if j==0 else None,
                               seg['growth_path'][j],None,seg['gross_margin_path'][j],seg['opex_ratio_path'][j],None,None,None])
            formula_sales.append([f'=C{ri}*(1+D{ri})'])
            formula_profit.append([f'=E{ri}*F{ri}',f'=H{ri}-E{ri}*G{ri}',f'=E{ri}-H{ri}'])
            row_refs[(seg['name'],j)]=ri;ri+=1
    end=ri-1
    s.get_range(f'A5:J{end}').values=input_rows
    s.get_range(f'K5:L{end}').values=[[seg.get('source_url') or '待核验', '增长、毛利率、费用率均为预测情景，非历史披露'] for seg in segs for _ in range(n)]
    s.get_range('K:K').format.column_width=60
    s.get_range('L:L').format.column_width=42
    for seg_index,seg in enumerate(segs):
        if n>1:
            start=5+seg_index*n+1
            s.get_range(f'C{start}:C{start+n-2}').formulas=[[f'=E{r-1}'] for r in range(start,start+n-1)]
    s.get_range(f'E5:E{end}').formulas=formula_sales
    s.get_range(f'H5:J{end}').formulas=formula_profit
    # worksheet 2 assumptions / year
    ar=cfg['opening_balance']
    a.get_range('A1:M2').values=[
      ['FinScope v3.2 业务及三表驱动参数（单位：亿元，比例为小数）']+['']*12,
      ['可调参数仅代表建模情景。改参后应运行Excel原生校验，并让后端重新计算目标价。']+['']*12]
    a.get_range('A4:M4').values=[['年份','现金税率','折旧/收入','资本开支/收入','应收天数','存货天数',
                               '应付天数','利息率','新增净债务','股利','股权融资','其他NWC期初','其他NWC/收入']]
    assumed=[]
    for j,row in enumerate(rows):
        assumed.append([row['year'],cfg['tax_rate'],cfg['da_ratio_path'][j],cfg['capex_ratio_path'][j],
                        cfg['dso_days_path'][j],cfg['dio_days_path'][j],cfg['dpo_days_path'][j],
                        cfg['interest_rate_path'][j],cfg.get('debt_change_path',[0]*n)[j]/1e8,
                        cfg.get('dividend_path',[0]*n)[j]/1e8,
                        cfg.get('equity_issue_path',[0]*n)[j]/1e8,
                        cfg.get('other_nwc_opening',0)/1e8,cfg['other_nwc_ratio_path'][j]])
    a.get_range(f'A5:M{4+n}').values=assumed
    a.get_range('A12:B23').values=[
        ['期初现金',ar['cash']/1e8],['期初应收',ar['receivables']/1e8],
        ['期初存货',ar['inventory']/1e8],['期初应付',ar['payables']/1e8],
        ['期初PPE',ar['ppe']/1e8],['期初其他资产',ar['other_assets']/1e8],
        ['期初债务',ar['debt']/1e8],['期初其他负债',ar['other_liabilities']/1e8],
        ['期初股东权益',ar['equity']/1e8],['期初少数权益',ar.get('minority_interest',0)/1e8],
        ['模型基准年度',cfg['base_year']],['说明','未列入的租赁、递延税和商誉损益不得自行假定为零']]
    # worksheet 3 all forecasting formulas written as a single rectangular matrix
    x.get_range('A1:AA2').values=[
      ['FinScope v3.2 利润表 / 现金流量表 / 资产负债表联动（亿元）']+['']*26,
      ['AA 平衡检查应约为0；所有金额由当前预测情景公式推导']+['']*26]
    x.get_range('A4:AA4').values=[['年度','收入','成本','EBIT','D&A','CAPEX','应收','存货','应付','NWC','ΔNWC','NOPAT','FCFF',
                                   '利息','税前利润','所得税','净利润','CFO','CFI','CFF','期末现金','期末PPE','期末有息债务',
                                   '期末权益','总资产','负债及权益','资产负债检查']]
    x.get_range(f'A5:A{4+n}').values=[[row['year']] for row in rows]
    grid=[]
    for j,row in enumerate(rows):
        rr=j+5; pr=rr-1
        refs=lambda col: '+'.join(f"'分部收入与EBIT'!{col}{row_refs[(seg['name'],j)]}" for seg in segs)
        fs={
          'B':f'={refs("E")}','C':f'={refs("J")}','D':f'={refs("I")}',
          'E':f"=B{rr}*'三表驱动参数'!C{rr}",
          'F':f"=B{rr}*'三表驱动参数'!D{rr}",
          'G':f"=B{rr}*'三表驱动参数'!E{rr}/365",
          'H':f"=C{rr}*'三表驱动参数'!F{rr}/365",
          'I':f"=C{rr}*'三表驱动参数'!G{rr}/365",
          'J':f"=G{rr}+H{rr}-I{rr}+B{rr}*'三表驱动参数'!M{rr}",
          'K':f"=J{rr}-"+("('三表驱动参数'!B13+'三表驱动参数'!B14-'三表驱动参数'!B15)" if j==0 else f'J{pr}'),
          'L':f"=D{rr}-MAX(0,D{rr})*'三表驱动参数'!B{rr}",
          'M':f'=L{rr}+E{rr}-F{rr}-K{rr}',
          'W':f"="+("'三表驱动参数'!B18" if j==0 else f'W{pr}')+f"+'三表驱动参数'!I{rr}",
          'N':f"=("+("'三表驱动参数'!B18" if j==0 else f'W{pr}')+f"+W{rr})/2*'三表驱动参数'!H{rr}",
          'O':f'=D{rr}-N{rr}',
          'P':f"=MAX(0,O{rr})*'三表驱动参数'!B{rr}",
          'Q':f'=O{rr}-P{rr}',
          'R':f'=Q{rr}+E{rr}-K{rr}',
          'S':f'=-F{rr}',
          'T':f"='三表驱动参数'!I{rr}-'三表驱动参数'!J{rr}+'三表驱动参数'!K{rr}",
          'U':f"="+("'三表驱动参数'!B12" if j==0 else f'U{pr}')+f'+R{rr}+S{rr}+T{rr}',
          'V':f"="+("'三表驱动参数'!B16" if j==0 else f'V{pr}')+f'+F{rr}-E{rr}',
          'X':f"="+("'三表驱动参数'!B20" if j==0 else f'X{pr}')+f"+Q{rr}-'三表驱动参数'!J{rr}+'三表驱动参数'!K{rr}",
          'Y':f"=U{rr}+G{rr}+H{rr}+V{rr}+'三表驱动参数'!B17",
          'Z':f"=I{rr}+W{rr}+X{rr}+'三表驱动参数'!B19+'三表驱动参数'!B21",
          'AA':f'=Y{rr}-Z{rr}',
        }
        grid.append([fs[chr(i)] for i in range(ord('B'),ord('Z')+1)]+[fs['AA']])
    x.get_range(f'B5:AA{4+n}').formulas=grid
    # verification sheet: modeled engine snapshot check versus formulas
    z.get_range('A1:F2').values=[['双重核验：公式求值与Python引擎结果对照','','','','',''],
                                 ['A/B分别是Excel值与Python独立计算值，差额为0才是正确','','','','','']]
    z.get_range('A4:F4').values=[['年度','Excel FCFF（亿）','Python FCFF（亿）','FCFF差异','Excel平衡差异','检查结论']]
    z.get_range(f'A5:A{4+n}').values=[[row['year']] for row in rows]
    z.get_range(f'C5:C{4+n}').values=[[row['fcff']/1e8] for row in rows]
    z.get_range(f'B5:B{4+n}').formulas=[[f"='三表联动预测'!M{j}"] for j in range(5,5+n)]
    z.get_range(f'D5:D{4+n}').formulas=[[f'=B{j}-C{j}'] for j in range(5,5+n)]
    z.get_range(f'E5:E{4+n}').formulas=[[f"='三表联动预测'!AA{j}"] for j in range(5,5+n)]
    z.get_range(f'F5:F{4+n}').formulas=[[f'=IF(AND(ABS(D{j})<0.01,ABS(E{j})<0.01),"PASS","REVIEW")'] for j in range(5,5+n)]
    # additional DCF with PV & capital bridge; all figures from same engine result
    dcf=result.get('dcf') or {}; dcfr=dcf.get('rows') or []
    w.get_range('A1:E2').values=[['FCFF / PV / EV / Equity Bridge — 独立重算单元','','','',''],
                                ['更改三表驱动参数会联动FCFF与DCF；相对估值/SOTP须在后端重算','','','','']]
    w.get_range('A4:E4').values=[['年度','FCFF（亿）','折现系数','PV FCFF（亿）','后端PV FCFF（亿）']]
    w.get_range(f'A5:A{4+n}').values=[[r['year']] for r in dcfr]
    w.get_range(f'B5:B{4+n}').formulas=[[f"='三表联动预测'!M{j}"] for j in range(5,5+n)]
    w.get_range('A12:B20').values=[['WACC',dcf.get('wacc')],['永续g',dcf.get('terminal_growth')],
                                  ['期中现金流现值',None],['Gordon终值现值',None],['EV',None],
                                  ['现金',dcf.get('cash',0)/1e8],['债务+少数股权等',sum(dcf.get(q,0) for q in ('debt','minority_interest','preferred_stock'))/1e8],
                                  ['估值股数（亿股）',(result.get('market_data',{}).get('shares_outstanding') or 0)/1e8],
                                  ['每股价值（元）',None]]
    w.get_range(f'C5:C{4+n}').formulas=[[f'=1/(1+$B$12)^({j-4}-0.5)'] for j in range(5,5+n)]
    w.get_range(f'D5:D{4+n}').formulas=[[f'=B{j}*C{j}'] for j in range(5,5+n)]
    w.get_range(f'E5:E{4+n}').values=[[dcfr[j-5]['pv_fcff']/1e8] for j in range(5,5+n)]
    w.get_range('B14:B16').formulas=[[f'=SUM(D5:D{4+n})'],
                                    [f'=B{4+n}*(1+B13)/(B12-B13)/(1+B12)^{n}'],
                                    ['=B14+B15']]
    w.get_range('B20').formulas=[['=IF(B19>0,(B16+B17-B18)/B19,0)']]
    # semantic formatting, bulk operations
    for ws in (s,a,x,z,w):
        ws.get_range('A1:AC1').format={'fill':'#172D46','font':{'bold':True,'color':'#FFFFFF','size':13},'row_height':31}
        ws.get_range('A4:AC4').format={'fill':'#345B7E','font':{'bold':True,'color':'#FFFFFF'},'row_height':27}
        ws.get_range('A:A').format.column_width=18
    s.get_range('B:B').format.column_width=33
    a.get_range('A:A').format.column_width=28
    z.get_range('A:A').format.column_width=20
    w.get_range('A:A').format.column_width=25
    x.get_range('B:AA').format.column_width=17
    w.get_range(f'B12:B13').set_number_format('0.00%')
    SpreadsheetFile.export_xlsx(wb).save(str(path))
    return path
