"""Independent arithmetic + XLSX OOXML structural gate.
This is NOT the native Excel/EXCEL_OK certification; use scripts/excel_native_verify.ps1.
"""
from __future__ import annotations
from pathlib import Path
import json,zipfile,xml.etree.ElementTree as ET


def _close(a,b,tol=1e-7):
    return a is not None and b is not None and abs(a-b)<=max(1,abs(a),abs(b))*tol


def audit_result(result:dict)->dict:
    checks=[]
    def chk(name,ok,detail=''):
        checks.append({'name':name,'pass':bool(ok),'detail':detail})
    d=result.get('dcf') or {}
    if d.get('ok'):
        rows=d.get('rows') or []
        for i,r in enumerate(rows):
            chk(f'DCF Y{i+1} FCFF identity',_close(r['fcff'],r['nopat']+r['da']-r['capex']-r['delta_nwc']))
            chk(f'DCF Y{i+1} PV identity',_close(r['pv_fcff'],r['fcff']*r['discount_factor']))
        chk('DCF PV explicit',_close(d['pv_explicit'],sum(r['pv_fcff'] for r in rows)))
        chk('DCF enterprise value',_close(d['enterprise_value'],d['pv_explicit']+d['pv_terminal']))
        eq=d['enterprise_value']+d['cash']-d['debt']-d['minority_interest']-d['preferred_stock']
        chk('DCF EV-to-equity bridge',_close(d['equity_value'],eq))
        if result.get('market_data',{}).get('shares_outstanding'):
            chk('DCF share bridge',_close(d['per_share']*result['market_data']['shares_outstanding'],d['equity_value']))
    proj=result.get('operating_forecast') or {}
    if proj.get('ok'):
        for r in proj['rows']:
            y=r['year']
            chk(f'{y} segment revenue',_close(sum(a['revenue'] for a in r['segments']),r['revenue']))
            chk(f'{y} segment EBIT',_close(sum(a['ebit'] for a in r['segments']),r['ebit']))
            chk(f'{y} FCFF bridge',_close(r['fcff'],r['nopat']+r['da']-r['capex']-r['delta_nwc']))
            if proj['mode']=='three_statement':
                s=r['balance_sheet']; inc=r['income_statement']; c=r['cash_flow_statement']
                chk(f'{y} balance sheet',_close(s['total_assets'],s['liabilities_equity']))
                chk(f'{y} CFO bridge',_close(c['cfo'],inc['net_income']+r['da']-r['delta_nwc']))
                chk(f'{y} cash flow balance',_close(c['ending_cash'],s['cash']))
    so=result.get('sotp') or {}
    if so.get('ok'):
        chk('SOTP EV sum',_close(so['segment_ev_total'],sum(i['segment_ev'] for i in so['rows'])))
        chk('SOTP equity',_close(so['equity_value'],so['segment_ev_total']-so['corporate_cost']-so['net_debt']-so['minority_interest']-so['preferred_stock']))
    b=result.get('blended') or {}
    if b.get('ok') and b.get('blended_per_share') is not None and b.get('components'):
        comps=b['components'];ws=[(c['per_share'],c['weight']) for c in comps]
        m=sum(v*w for v,w in ws)/sum(w for _,w in ws)
        chk('Blended weights and share price',_close(m,b['blended_per_share']))
    return {'engine_checks_total':len(checks),'engine_checks_failed':sum(not x['pass'] for x in checks),
            'engine_arithmetic_pass':all(x['pass'] for x in checks),
            'checks':checks}


def audit_xlsx(path:str|Path, *, expected_sheets:list[str]|None=None)->dict:
    path=Path(path); issues=[]; formulas=0; cached=0; errors=[]; sheet_names=[]
    ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    with zipfile.ZipFile(path) as z:
        files=z.namelist()
        if 'xl/workbook.xml' not in files: issues.append('workbook.xml missing')
        else:
            root=ET.fromstring(z.read('xl/workbook.xml'))
            sheet_names=[s.get('name') for s in root.findall('x:sheets/x:sheet',ns)]
        for fn in files:
            if fn.startswith('xl/externalLinks/'):
                issues.append('external link present: '+fn)
            if fn.startswith('xl/worksheets/sheet') and fn.endswith('.xml'):
                r=ET.fromstring(z.read(fn))
                for c in r.findall('.//x:c',ns):
                    f=c.find('x:f',ns);v=c.find('x:v',ns)
                    if f is not None:
                        formulas+=1
                        if v is not None and v.text not in (None,''): cached+=1
                        if '#REF!' in (f.text or ''):errors.append(f'{fn}:{c.get("r")} formula #REF!')
                    if c.get('t')=='e':errors.append(f'{fn}:{c.get("r")} cached Excel error: '+str(v.text if v is not None else ''))
        if expected_sheets:
            for name in expected_sheets:
                if name not in sheet_names:issues.append('sheet missing: '+name)
        if formulas==0:issues.append('no workbook formulas detected')
    return {'file':str(path),'xlsx_structure_pass':not (issues or errors),
            'sheet_count':len(sheet_names),'sheets':sheet_names,
            'formula_count':formulas,'formula_cached_count':cached,
            'issues':issues+errors,'native_excel_calculated':'PENDING',
            'EXCEL_OK':False,'status':'STRUCTURE_OK_NATIVE_RECALC_PENDING' if not issues and not errors else 'FAILED'}


def full_report(result:dict,workbook_path=None):
    r={'engine':audit_result(result)}
    if workbook_path:r['workbook']=audit_xlsx(workbook_path)
    r['certification']='EXCEL_OK_NOT_CERTIFIED' # native Excel required per comps Skill
    return r

if __name__=='__main__':
    import sys
    r=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    report=full_report(r,sys.argv[2] if len(sys.argv)>2 else None)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['engine']['engine_arithmetic_pass'] and report.get('workbook',{}).get('xlsx_structure_pass',True) else 1)
