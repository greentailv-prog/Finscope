"""Financial correctness gates added in FinScope C v3.1.
All fixtures synthetic and offline. Run: python -m unittest valuation.tests.test_v3_1_integrity -v
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from valuation.core.models import Assumptions, Company, Financials, Peer, Segment, ValuationInput
from valuation.core.dcf import build_dcf
from valuation.core.sotp import build_sotp
from valuation.core.comps import build_comps
from valuation.core.engine import run
from valuation.data.peer_selector import select_peers
from valuation.data.adapters import prepare


def fin(**kw):
    f = Financials(
        years=[2023, 2024, 2025],
        revenue=[1_000_000_000, 1_100_000_000, 1_300_000_000],
        ebit=[100_000_000, 110_000_000, 160_000_000],
        net_income=[60_000_000, 70_000_000, 90_000_000],
        da=[20_000_000, 22_000_000, 25_000_000],
        capex=[30_000_000, 33_000_000, 40_000_000],
        delta_nwc=[10_000_000, 12_000_000, 13_000_000],
        cash=200_000_000,
        total_debt=100_000_000,
        total_equity=700_000_000,
        shares_outstanding=100_000_000,
        market_cap=3_000_000_000,
        price=30.0,
        industry="工业自动化",
    )
    for k, v in kw.items(): setattr(f, k, v)
    return f


def asm(**kw):
    a = Assumptions(
        risk_free=.025, erp=.055, beta=1.2,
        revenue_growth_y1=.09, terminal_growth=.02,
        ebit_margin=.15, tax_rate=.25,
        capex_pct_revenue=.03, da_pct_revenue=.02,
        nwc_pct_revenue=.01,
    )
    for k, v in kw.items(): setattr(a, k, v)
    return a


class IntegrityTests(unittest.TestCase):
    def test_robotechnik_requires_business_peer_review_no_network(self):
        c = Company(name="罗博特科", ticker="300757", industry="专用设备", business="硅光封装和光伏自动化")
        with patch('valuation.data.peer_selector._fetch_one', side_effect=AssertionError("no network expected")):
            res = select_peers(c, fin())
        self.assertEqual(res['tier'], 'review_required')
        self.assertEqual(res['peers'], [])

    def test_unknown_industry_does_not_use_proxy_no_network(self):
        with patch('valuation.data.peer_selector._fetch_one', side_effect=AssertionError('no proxy fetch')):
            res = select_peers(Company(ticker='300001', industry='未分类神秘行业'), fin())
        self.assertEqual(res['tier'], 'none')
        self.assertEqual(res['peers'], [])

    def test_failed_user_selection_does_not_fallback_to_other_peers(self):
        with patch('valuation.data.peer_selector._fetch_one', return_value={'ok':False,'error':'offline'}):
            res = select_peers(Company(ticker='300757'), fin(), user_peer_set=['688000'])
        self.assertEqual(res['tier'], 'user_failed')
        self.assertEqual(res['peers'], [])

    def test_comps_proxy_blocked(self):
        fake = [Peer(name='X', ticker='600001', pe=15), Peer(name='Y', ticker='600002',pe=20)]
        res = build_comps(fin(), fake, asm(), peer_selection={'tier':'proxy'})
        self.assertFalse(res['ok'])
        self.assertEqual(res['status'],'blocked')

    def test_comps_ev_needs_net_debt_cannot_treat_unknown_as_zero(self):
        fake = [Peer(name='X', ticker='600001', ev_revenue=2),Peer(name='Y',ticker='600002',ev_revenue=3)]
        res = build_comps(fin(cash=None), fake, asm(peer_growth_adjustment=False), multiples=['ev_revenue'],
                          peer_selection={'tier':'user'})
        self.assertFalse(res['ok'])

    def test_dcf_negative_equity_is_diagnostic_not_price(self):
        x = build_dcf(fin(total_debt=20_000_000_000), asm(), solve_implied=False)
        self.assertFalse(x['ok'])
        self.assertEqual(x['status'],'blocked')
        self.assertLess(x['diagnostic_values']['equity_value'],0)

    def test_dcf_missing_assets_not_zero(self):
        x = build_dcf(fin(cash=None), asm(), solve_implied=False)
        self.assertFalse(x['ok'])
        self.assertIn('净债务', x['error'])

    def test_dcf_default_market_independent_wacc(self):
        a = asm()
        a.wacc_mode = 'capm'
        x = build_dcf(fin(price=30, market_cap=3_000_000_000), a)
        y = build_dcf(fin(price=300,market_cap=30_000_000_000), a)
        self.assertTrue(x['ok'],x)
        self.assertTrue(y['ok'],y)
        self.assertAlmostEqual(x['wacc'],y['wacc'],places=8)

    def test_dcf_blend_blocks_incoherent_terminals(self):
        a=asm(terminal_method='blend')
        x=build_dcf(fin(),a,solve_implied=False,peers=[])
        self.assertFalse(x['ok'])
        self.assertEqual(x['status'],'blocked')

    def test_dcf_nwc_driver_revenue_vs_incremental_revenue(self):
        x=build_dcf(fin(), asm(nwc_forecast_basis='revenue',nwc_pct_revenue=.1),solve_implied=False)
        y=build_dcf(fin(), asm(nwc_forecast_basis='delta_revenue',nwc_investment_ratio=.1),solve_implied=False)
        self.assertTrue(x['ok'])
        self.assertTrue(y['ok'])
        self.assertLess(y['rows'][0]['delta_nwc'],x['rows'][0]['delta_nwc'])
        self.assertNotEqual(x['per_share'],y['per_share'])

    def test_sotp_single_segment_is_not_sotp(self):
        x=build_sotp(fin(),[Segment(name='整体业务',revenue=1.3e9,metric='revenue',value=1.3e9,multiple=2)],
                     asm(sotp_corporate_cost=0))
        self.assertFalse(x['ok'])

    def test_sotp_no_corporate_cost_is_blocked(self):
        ss=[Segment(name='业务甲',revenue=5e8,metric='revenue',multiple_type='ev_revenue',multiple=2),
            Segment(name='业务乙',revenue=8e8,metric='revenue',multiple_type='ev_revenue',multiple=2.5)]
        x=build_sotp(fin(),ss,asm())
        self.assertFalse(x['ok'])
        self.assertIn('总部',x['reason'])

    def test_sotp_reported_components_and_zero_corporate(self):
        ss=[Segment(name='业务甲',revenue=5e8,metric='ebitda',value=1e8,ebitda=1e8,multiple_type='ev_ebitda',multiple=10),
            Segment(name='业务乙',revenue=8e8,metric='revenue',value=8e8,multiple_type='ev_revenue',multiple=2.5)]
        x=build_sotp(fin(),ss,asm(sotp_corporate_cost=0))
        self.assertTrue(x['ok'],x)
        self.assertAlmostEqual(x['segment_ev_total'],3e9,places=4)
        self.assertEqual(ss[0].ebitda,1e8)
        self.assertEqual(x['rows'][0]['multiple_type'],'ev_ebitda')
        self.assertEqual(x['rows'][0]['value'],1e8)

    def test_sotp_ev_ebit_cannot_borrow_ebitda_multiple(self):
        ss=[Segment(name='业务甲',revenue=5e8,metric='ebit',value=5e7,ebit=5e7,multiple_type='ev_ebit',
                    peer_median_ev_ebitda=19),
            Segment(name='业务乙',revenue=8e8,metric='revenue',value=8e8,multiple_type='ev_revenue',multiple=2)]
        x=build_sotp(fin(),ss,asm(sotp_corporate_cost=0))
        self.assertFalse(x['ok'])

    def test_high_volatility_keeps_latest_year_and_flags_review(self):
        f=fin(years=[2023,2024,2025],revenue=[1e9,1.1e9,4e8],net_income=[7e7,8e7,2e7])
        inp=ValuationInput(company=Company(ticker='123456',industry='制造'),financials=f,
                           assumptions=asm(),data_source='auto',fetch_data=False)
        out,ctx=prepare(inp,fetch=False)
        self.assertEqual(out.financials.years,[2023,2024,2025])
        self.assertEqual(out.financials.revenue[-1],4e8)
        self.assertTrue(ctx['data_review_required'])


    def test_comps_trailing_pe_uses_parent_attributable_earnings(self):
        from valuation.core.comps import target_metrics
        f = fin(net_income_parent=[20_000_000, 30_000_000, 50_000_000])
        self.assertEqual(target_metrics(f)["net_income"], 50_000_000)

    def test_comps_forward_pe_without_forward_income_does_not_reuse_trailing(self):
        peers = [Peer(name="甲", ticker="600001", pe_forward=15),
                 Peer(name="乙", ticker="600002", pe_forward=20)]
        x = build_comps(fin(), peers, asm(), multiples=["pe_forward"],peer_selection={"tier":"user"})
        self.assertFalse(x["ok"])
        self.assertTrue(any("前瞻PE" in w for w in x.get("warnings", [])))

    def test_comps_peg_requires_profit_growth_not_revenue_growth(self):
        peers = [Peer(name="甲", ticker="600001", peg=1.2),
                 Peer(name="乙", ticker="600002", peg=1.5)]
        f = fin(revenue=[1e9, 1.1e9, 1.6e9])
        x = build_comps(f, peers, asm(), multiples=["peg"],peer_selection={"tier":"user"},target_growth=.30)
        self.assertFalse(x["ok"])

    def test_comps_ebitda_requires_da_cannot_assume_zero(self):
        from valuation.core.comps import target_metrics
        f=fin(da=[])
        self.assertIsNone(target_metrics(f)["ebitda"])

    def test_comps_market_ev_without_cash_debt_unknown(self):
        from valuation.core.comps import target_multiples
        f=fin(total_debt=None)
        self.assertIsNone(target_multiples(f)["enterprise_value"])

    def test_comps_missing_peer_provenance_cannot_be_blended(self):
        peers=[Peer(name="甲",ticker="600001",pe=16), Peer(name="乙",ticker="600002",pe=18)]
        res=build_comps(fin(),peers,asm(),multiples=["pe"],peer_selection={"tier":"user"})
        self.assertTrue(res["ok"])
        self.assertTrue(res["review_required"])
        self.assertEqual(res["status"],"review_required")

    def test_comps_with_complete_peer_provenance_not_review_blocked(self):
        peers=[Peer(name="甲",ticker="600001",pe=16,source="test only",as_of="2025-12-31"),
               Peer(name="乙",ticker="600002",pe=18,source="test only",as_of="2025-12-31")]
        res=build_comps(fin(),peers,asm(),multiples=["pe"],peer_selection={"tier":"user"})
        self.assertTrue(res["ok"])
        self.assertFalse(res["review_required"])

    def test_dcf_without_history_capex_is_marked_for_review(self):
        x=build_dcf(fin(capex=[]),asm(),solve_implied=False)
        self.assertTrue(x["ok"])
        self.assertTrue(x["review_required"])


if __name__ == '__main__': unittest.main()
