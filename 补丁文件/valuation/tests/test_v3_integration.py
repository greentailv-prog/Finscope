"""FinScope C v3 offline smoke tests: canonical financials, API, workbook links, assistant intents.

Run from project root: python -m valuation.tests.test_v3_integration
"""
from __future__ import annotations
import json
import math
import os
import re
from pathlib import Path

# 测试生成的底稿放到单独目录，避免覆盖 valuation/output 下的交付样例。
os.environ.setdefault("FINSCOPE_OUTPUT_DIR", "valuation/output/_tests")

from fastapi.testclient import TestClient
from zipfile import ZipFile
from valuation.api.server import app
from valuation.api.assistant import extract_intent

ROOT = Path(__file__).resolve().parents[1]


def build_unified():
    sample = json.loads((ROOT / 'tests/reports_web/600519_result.json').read_text(encoding='utf-8'))
    hist = sample['history']
    years = [str(x) for x in hist['years']]
    mapping = {
        'revenue':'revenue', 'operating_cost':'cogs', 'operating_profit':'ebit',
        'net_income':'net_income', 'net_income_parent':'net_income_parent',
        'depreciation_amortization':'da', 'capex':'capex',
        'cash_and_equivalents':'cash', 'accounts_receivable':'receivables',
        'accounts_payable':'payables', 'inventory':'inventory',
        'total_assets':'total_assets', 'total_equity':'total_equity',
        'current_assets':'current_assets', 'current_liabilities':'current_liabilities',
    }
    fns={}
    for cname, hname in mapping.items():
        a=hist.get(hname)
        if not isinstance(a,list) or not any(v is not None for v in a):
            continue
        series={y:v for y,v in zip(years,a) if isinstance(v,(int,float))}
        if not series: continue
        fns[cname]={
            'value':series.get(years[-1]),'series':series,'period':years[-1],
            'status':'found','unit':'元','source_id':'TEST', 'scope':'合并报表',
            'source_type':'online','source':'test fixture, not live feed',
        }
    # C v3.1 要求完整 EV→股权桥。旧测试没有传入有息债务，
    # 此处使用历史快照里已经保存的同一估值基期数值，禁止缺失时暗填0。
    for cname, source_key in [('total_debt','debt'),('cash_and_equivalents','cash')]:
        value = sample.get('dcf', {}).get(source_key)
        if value is not None:
            fns[cname] = {'value':value,'period':years[-1],
                          'status':'found','unit':'元','source_id':'TEST',
                          'scope':'合并报表','source_type':'fixture',
                          'source':'same baseline snapshot'}
    # D upstream must provide its own market data and only one canonical quote
    return {
        'schema_version':'2.0','meta':{'source_mode':'online','period_type':'annual','currency':'CNY'},
        'company':{**sample['company'], 'report_period':f'{years[-1]}-12-31'}, 'financials':fns,
        'market_data':sample.get('market_data') or {},
        'sources':[{'source_id':'TEST','source':'local regression fixture','source_type':'online',
                    'source_url':'https://example.org/not-live','page':None}],
        'method_selection':'dcf',
    }


def main():
    cli=TestClient(app)
    assert cli.get('/api/valuation/health').status_code==200
    obj=build_unified()
    assert obj['financials']['revenue']['series']['2025']>0
    r=cli.post('/api/valuation/from-workflow', json=obj)
    assert r.status_code==200,r.text[:1000]
    base=r.json()['valuation']
    assert base.get('history',{}).get('years')==[2023,2024,2025]
    assert math.isclose(base['history']['revenue'][-1],obj['financials']['revenue']['value'])
    assert (base.get('data_source') or {}).get('used')=='canonical'
    print('PASS ABC /from-workflow canonical: one quote, three years, no double source')
    s=cli.post('/api/valuation/session',json={
        'ticker':'600519','method_selection':'dcf','data_source':'canonical',
        'inputs':obj,
    })
    assert s.status_code==200,s.text[:500]
    sid=s.json()['session_id']
    r=cli.post(f'/api/valuation/session/{sid}/run',params={'export_excel':'true'})
    assert r.status_code==200,r.text[:500]
    rr=r.json()
    assert rr.get('dcf',{}).get('ok')
    x=cli.get(f'/api/valuation/session/{sid}/excel')
    assert x.status_code==200
    assert len(x.content)>15000
    tmp=ROOT / 'output' / '_v3_smoke_test.xlsx'
    tmp.write_bytes(x.content)
    with ZipFile(tmp) as z:
        names=z.namelist()
        assert 'xl/workbook.xml' in names
        assert any(x.startswith('xl/worksheets/sheet') for x in names)
        assert any(b'<f' in z.read(x) or b'<x:f' in z.read(x) for x in names if x.startswith('xl/worksheets/sheet') and x.endswith('.xml'))
    tmp.unlink(missing_ok=True)
    print('PASS /session/run + valid formula Excel download; exporter:',rr.get('excel_format'))
    if rr.get('excel_format')=='professional_18_sheets':
        # 已确认官方 artifact_tool 工具可读取 600519 样例 B18 差异在浮点误差级。
        assert (rr['dcf']['per_share'] or 0)>0
    # Assistant explanation must not silently reselect peers
    assert extract_intent('请解释为什么选择这些可比公司')['action']=='explain'
    assert extract_intent('重新选择可比公司并解释原因')['action']=='reselect_peers'
    chat=cli.post('/api/valuation/assistant',json={'session_id':sid,'message':'请解释估值分歧的原因','history':[]})
    assert chat.status_code==200,chat.text[:500]
    assert len(chat.json().get('answer',''))>40
    assert chat.json().get('changed') is False
    print('PASS rules assistant uses actual result; explaining does not change peer set')
    # Read-only hypothetical questions must not mutate stored valuation inputs.
    probe = '请解释把 WACC 从 6.0% 调整到 7.5% 会对估值有什么影响'
    assert extract_intent(probe)['changes'] == {}
    before = cli.get(f'/api/valuation/session/{sid}').json()['assumptions']
    chat_ro = cli.post('/api/valuation/assistant', json={
        'session_id': sid, 'message': probe, 'history': [],
    })
    assert chat_ro.status_code == 200
    assert chat_ro.json()['changed'] is False
    assert cli.get(f'/api/valuation/session/{sid}').json()['assumptions'] == before
    # For a real from-to command, use the TARGET value, not the old value.
    edit = '请把 WACC 从 6.0% 调整到 7.5%，并解释变化'
    intent = extract_intent(edit)
    assert math.isclose(intent['changes']['wacc_override'], 0.075)
    chat_edit = cli.post('/api/valuation/assistant', json={
        'session_id': sid, 'message': edit, 'history': [],
    })
    assert chat_edit.status_code == 200, chat_edit.text[:300]
    assert chat_edit.json()['changed'] is True
    assert math.isclose(chat_edit.json()['result']['dcf']['wacc'], 0.075, abs_tol=1e-8)
    assert cli.get(f'/api/valuation/session/{sid}').json()['assumptions']['wacc_override'] == 0.075
    print('PASS conversational edit uses target 7.5%; hypothetical question is read-only')
    assert extract_intent('请重新选择可比公司并解释原因')['action'] == 'reselect_peers'
    assert extract_intent('为什么可比公司更换会影响估值？')['action'] != 'reselect_peers'
    assert extract_intent('请将收入增速调到6%，永续增长率改为2.5%')['changes']['terminal_growth'] == 0.025
    print('PASS assistant intent and multiple parameters parsed separately')
    # A live stock name search is intentionally not checked in offline test.
    print('PASS all offline smoke tests.')


if __name__=='__main__':main()
