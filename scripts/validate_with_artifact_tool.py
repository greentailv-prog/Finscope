"""Portable formula recomputation checkpoint (NOT a native MS Excel COM signoff)."""
from __future__ import annotations
import json,sys
from pathlib import Path
from artifact_tool import Blob,SpreadsheetFile


def verify(path:Path, engine_output:Path|None=None)->dict:
    wb=SpreadsheetFile.import_xlsx(Blob.load(str(path)))
    result_path=engine_output
    model=json.loads(result_path.read_text(encoding='utf-8')) if result_path else None
    n=(model or {}).get('operating_forecast',{}).get('years',5)
    def values(rng):
        d=json.loads(wb.inspect({'kind':'table','range':rng,'include':'values,formulas',
                                 'table_max_rows':max(10,n+2),'table_max_cols':10}).ndjson)
        return d.get('values') or []
    checks=[]
    for i,row in enumerate(values(f'财务一致性校验!A5:F{4+n}')):
        yr,ex,py,delta,bs,st=row
        checks.append({'year':yr,'fcff_ok':abs(delta or 0)<.01,
                       'bs_ok':abs(bs or 0)<.01,'sheet_pass':st=='PASS'})
    val=values('DCF验证!A20:B20')[0][1]
    if model and model.get('dcf',{}).get('per_share') is not None:
        price_match=abs(val-model['dcf']['per_share'])<.01
    else:price_match=None
    errors=wb.inspect({'kind':'match','search_term':'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',
                       'options':{'use_regex':True,'max_results':200}}).ndjson
    try: match=json.loads(errors)
    except ValueError:match={}
    is_error=match.get('kind')!='notice' or '0 entries' not in match.get('message','')
    return {'workbook':str(path),'recalculation_engine':'artifact_tool',
            'five_year_checks':checks,'all_checks_pass':all(all(x[k] for k in ('fcff_ok','bs_ok','sheet_pass')) for x in checks)
                                         and price_match is not False and not is_error,
            'engine_value_matches':price_match,'formula_errors_found':is_error,
            'native_excel_com_run':False,'EXCEL_OK':False,
            'note':'artifact_tool计算通过不等于Windows Excel COM公式重算认证'}

if __name__=='__main__':
    out=verify(Path(sys.argv[1]),Path(sys.argv[2]) if len(sys.argv)>2 else None)
    print(json.dumps(out,ensure_ascii=False,indent=2))
    raise SystemExit(0 if out['all_checks_pass'] else 1)
