"""Offline correctness tests. No public company market cap or peer multiple is fabricated."""
import unittest, json, tempfile, zipfile
from pathlib import Path
from valuation.research.driver_forecast import project
from valuation.research.peer_registry import research,validate_for_comps
from valuation.core.models import Financials
from valuation.core import dcf


def fixture():
    return {
      'base_year':2025,'years':5,'as_of':'2025-12-31','version':'synthetic_only',
      'segments':[
        {'name':'业务A','base_revenue':600,'growth_path':[.1,.08,.06,.05,.04],
         'gross_margin_path':[.45]*5,'opex_ratio_path':[.16]*5,'source_url':'synthetic:test'},
        {'name':'业务B','base_revenue':400,'growth_path':[.03,.03,.03,.03,.03],
         'gross_margin_path':[.25]*5,'opex_ratio_path':[.12]*5,'source_url':'synthetic:test'}],
      'tax_rate':.2,'capex_ratio_path':[.07]*5,'da_ratio_path':[.04]*5,
      'dso_days_path':[60]*5,'dio_days_path':[50]*5,'dpo_days_path':[65]*5,
      'other_nwc_opening':0,'other_nwc_ratio_path':[0]*5,
      'opening_balance':{'cash':100,'receivables':200,'inventory':100,'ppe':500,'other_assets':100,
                         'payables':150,'debt':250,'other_liabilities':100,'equity':500},
      'interest_rate_path':[.05]*5,
      'debt_change_path':[0]*5,'dividend_path':[0]*5,'equity_issue_path':[0]*5}

class UpgradeTests(unittest.TestCase):
    def test_driver_full_3statements_reconcile(self):
        result=project(fixture())
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result['mode'],'three_statement')
        self.assertEqual(len(result['rows']),5)
        for r in result['rows']:
            b=r['balance_sheet'];c=r['cash_flow_statement'];inc=r['income_statement']
            self.assertAlmostEqual(b['balance_check'],0,places=7)
            self.assertAlmostEqual(r['fcff'],r['nopat']+r['da']-r['capex']-r['delta_nwc'],places=7)
            self.assertAlmostEqual(c['cfo'],inc['net_income']+r['da']-r['delta_nwc'],places=7)
            self.assertAlmostEqual(sum(s['revenue'] for s in r['segments']),r['revenue'],places=7)
    def test_missing_nwc_blocks(self):
        f=fixture();f.pop('opening_balance')
        self.assertFalse(project(f)['ok'])
    def test_unbalanced_opening_bs_blocks(self):
        f=fixture();f['opening_balance']['equity']+=10
        self.assertFalse(project(f)['ok'])
    def test_segment_revenue_mismatch_blocks(self):
        f=Financials(years=[2025],revenue=[2000])
        self.assertFalse(project(fixture(),f)['ok'])
    def test_negative_cash_is_not_silently_financed(self):
        f=fixture();f['dividend_path']=[2000]*5
        self.assertFalse(project(f)['ok'])
    def test_no_fake_peers(self):
        r=research('300757')
        self.assertEqual(r['status'],'review_required')
        self.assertGreaterEqual(len(r['candidates']),4)
        self.assertTrue(all(not a['approved'] for a in r['candidates']))
        self.assertFalse(validate_for_comps(r,[],"2026-11-04")['ok'])
    def test_asof_market_late_blocks(self):
        r=research('300757')
        v=validate_for_comps(r,[{'ticker':'300724','segment_id':'pv_equipment',
            'ev_revenue':3,'caliber':'LTM','data_source_url':'test',
            'market_as_of':'2026-12-01'}],'2026-11-04')
        self.assertFalse(v['ok'])
        self.assertIn('倍数取数日期缺失或晚于估值基准日',v['rejected'][0]['reasons'])
    def test_cross_segment_multiples_cannot_pool(self):
        r=research('300757')
        def peer(ticker,segment):
            return {'ticker':ticker,'segment_id':segment,'analyst_approved':True,
                    'approved_by':'测试员','approval_date':'2026-11-04',
                    'business_evidence_url':'https://example.com/business',
                    'pure_play_financials_confirmed':True,'pure_play_financials_source_url':'https://example.com/segments','data_source_url':'https://example.com/market',
                    'market_as_of':'2026-11-04','caliber':'NTM','currency':'CNY','ev_revenue':3.0}
        v=validate_for_comps(r,[peer('MYCR.ST','photonics'),peer('300724','pv_equipment')],'2026-11-04')
        self.assertFalse(v['ok'])
    def test_analyst_approval_dated_same_segment(self):
        r=research('300757')
        def peer(ticker):
            return {'ticker':ticker,'segment_id':'photonics','analyst_approved':True,
                    'approved_by':'测试员','approval_date':'2026-11-04',
                    'pure_play_financials_confirmed':True,'pure_play_financials_source_url':'https://example.com/segments','data_source_url':'https://example.com/market',
                    'market_as_of':'2026-11-04','caliber':'NTM','currency':'CNY','ev_revenue':3.0}
        v=validate_for_comps(r,[peer('MYCR.ST'),peer('0522.HK')],'2026-11-04')
        self.assertTrue(v['ok'])
        self.assertEqual(v['usable_groups'][0]['ticker_count'],2)
    def test_research_asof_has_lookahead_gate(self):
        r=research('300757',as_of='2025-12-31')
        self.assertTrue(r['source_after_as_of'])
        v=validate_for_comps(r,[{'ticker':'300724','segment_id':'pv_equipment'}],'2025-12-31')
        self.assertIn('业务证据发布时间晚于估值基准日，存在前瞻信息偏差',v['rejected'][0]['reasons'])
    def test_robotechnik_unapproved_manual_peers_blocked(self):
        # Supplying a made-up low multiple by hand must not bypass business diligence.
        from valuation.tests.build_synthetic_example import payload
        from valuation.core.engine import run
        q=payload()
        q['company'].update({'ticker':'300757','name':'罗博特科','price_date':'2026-11-04'})
        q.pop('operating_forecast',None)
        q['method_selection']='comps'
        q['peers']=[{'ticker':'300724','name':'捷佳伟创','pe':8,'source':'manual','as_of':'2026-11-04'}]
        result=run(q,fetch=False,export_excel=False)
        self.assertFalse(result.get('comps',{}).get('ok'))
        self.assertEqual(result.get('peer_selection',{}).get('tier'),'review_required')
    def test_legacy_proper_returns(self):
        from valuation.tests import test_v3_1_integrity
        self.assertTrue(hasattr(dcf,'build_dcf'))

if __name__=='__main__':unittest.main()
