"""Synthetic test corporation only; never label as actual 300757 valuation."""
from __future__ import annotations
import json
from pathlib import Path
from valuation.tests.test_v3_2_upgrade import fixture
from valuation.core.engine import run
from valuation.research.excel_audit import full_report


def payload():
    f=fixture(); factor=1e8
    for s in f['segments']:s['base_revenue']*=factor
    for k in ('cash','receivables','inventory','ppe','other_assets','payables','debt','other_liabilities','equity'):
        f['opening_balance'][k]*=factor
    f['as_of']='2025-12-31'
    return {'company':{'name':'合成测试装备公司（非真实上市公司）','ticker':'DEMO32','industry':'工业装备','report_period':'2025-12-31','market':'A'},
            'financials':{'years':[2023,2024,2025],
              'revenue':[800*factor,900*factor,1000*factor],
              'ebit':[165*factor,175*factor,190*factor],
              'net_income':[105*factor,112*factor,126*factor],
              'net_income_parent':[105*factor,112*factor,126*factor],
              'da':[32*factor,36*factor,40*factor],
              'capex':[50*factor,56*factor,65*factor],
              'delta_nwc':[2*factor,5*factor,8*factor],
              'pretax_income':[140*factor,150*factor,170*factor],
              'tax_provision':[25*factor,30*factor,35*factor],
              'cash':100*factor,'total_debt':250*factor,'shares_outstanding':100*factor,
              'receivables':200*factor,'inventory':100*factor,'payables':150*factor,
              'total_equity':500*factor,'price':22.0},
            'method_selection':'dcf','fetch_data':False,'allow_web':False,
            'data_source':'synthetic_test_only','operating_forecast':f,
            'assumptions':{'risk_free':.02,'erp':.06,'beta':1.2,'terminal_growth':.025,
                           'forecast_years':5,'wacc_override':.09,'wacc_mode':'manual'}}

if __name__=='__main__':
    output=Path(__file__).resolve().parents[1]/'output'
    output.mkdir(exist_ok=True)
    xlsx=output/'SYNTHETIC_ONLY_three_statement_model.xlsx'
    r=run(payload(),fetch=False,export_excel=True,excel_path=str(xlsx))
    (output/'SYNTHETIC_ONLY_result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    report=full_report(r,xlsx)
    (output/'SYNTHETIC_ONLY_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'model_status':r['status'],'dcf_ok':r['dcf']['ok'],'dcf_value':r['dcf'].get('per_share'),
                      'excel_format':r.get('excel_format'),'sheets':report['workbook']['sheet_count'],
                      'formula_count':report['workbook']['formula_count'],
                      'arith_checks':report['engine']['engine_checks_total'],
                      'arith_fail':report['engine']['engine_checks_failed'],
                      'xlsx_structure_pass':report['workbook']['xlsx_structure_pass'],
                      'issues':report['workbook']['issues'][:8]},ensure_ascii=False,indent=2))
