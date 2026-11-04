"""离线行情备用源测试，不发真实互联网请求。运行：python -m valuation.tests.test_quote_fallback"""
from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock, patch

from valuation.data import akshare_provider as ak, cache, quote_fallback as q


def quote_bytes(code='600519', price=1480.0, cap_yi=18501.21):
    cells=[''] * 51
    cells[0]='1'; cells[1]='贵州茅台'; cells[2]=code
    cells[3]=str(price); cells[30]='20261103150505'
    cells[44]='18501.20'; cells[45]=str(cap_yi)
    return ('v_sh'+code+'="'+'~'.join(cells)+'";').encode('gbk')


def main():
    with TemporaryDirectory() as d, patch.object(cache, 'CACHE_DIR', Path(d)):
        quote = q.parse_tencent_quote(quote_bytes(), '600519.SH')
        assert quote['price'] == 1480.0
        assert quote['market_cap'] == 18501.21 * 1e8
        assert quote['shares_estimated'] is True
        assert quote['price_source'] == '腾讯财经·行情'
        assert quote['price_date'] == '2026-11-03'
        assert q.symbol('600519.SH') == 'sh600519'
        print('PASS tencent quote fields, share inference and source labels')
        try:
            q.parse_tencent_quote(quote_bytes(code='000333'), '600519')
            raise AssertionError('must reject mismatched ticker')
        except ValueError:
            pass
        try:
            q.parse_tencent_quote('empty', '600519')
            raise AssertionError('must reject bad quote')
        except ValueError:
            pass
        print('PASS malformed/mismatched quotes rejected')
        response = Mock(status_code=200, content=quote_bytes())
        response.raise_for_status.return_value=None
        with patch.object(q.requests,'get',return_value=response), patch.object(ak, '_ak', return_value=Mock(stock_individual_info_em=Mock(side_effect=RuntimeError('Push2RateLimitError: throttled')))):
            ak._PUSH2_COOLDOWN_UNTIL=0.0
            info = ak.company_info('600519')
            assert info['ok'] is True
            assert info['price']==1480
            assert info['shares_estimated']
            assert '腾讯财经' in info['price_source']
            assert ak._PUSH2_COOLDOWN_UNTIL > 0
            another = ak.company_info('600519')
            assert another == info
        print('PASS EM push2 throttling -> Tencent fallback, cached, cooldown')
        # 主行情服务可用时仍优先保留东方财富披露的精确总股本。
        import pandas as pd
        exact_rows = pd.DataFrame([
            {'item': '股票简称', 'value': '贵州茅台'},
            {'item': '行业', 'value': '白酒'},
            {'item': '最新', 'value': 1480.0},
            {'item': '总股本', 'value': 1250081601},
            {'item': '总市值', 'value': 1850120769480},
        ])
        with patch.object(ak, '_ak', return_value=Mock(stock_individual_info_em=Mock(return_value=exact_rows))):
            ak._PUSH2_COOLDOWN_UNTIL=0.0
            exact = ak.company_info('000858')
            assert exact['shares_estimated'] is False
            assert exact['shares_outstanding'] == 1250081601
            assert exact['industry'] == '白酒'
        print('PASS eastmoney original exact shares / industry preferred when available')
        # v3 stale result with missing market price/share must be repaired.
        fake = {'ok':True,'code':'600519', 'name':'600519','industry':'',
                'financials':{'years':[2023,2024,2025], 'revenue':[100,110,120],
                              'price':None,'shares_outstanding':None,'market_cap':None,'data_notes':[]},
                'warnings':['旧警告'],'sources':[]}
        cache.put('company_600519',fake)
        repaired=ak.fetch_company('600519')
        assert repaired['financials']['price'] == 1480
        assert repaired['financials']['shares_outstanding']>1e9
        assert repaired['financials']['market_cap']>1e12
        assert any('股本按腾讯财经' in n for n in repaired['financials']['data_notes'])
        assert any('腾讯财经' in s['name'] for s in repaired['sources'])
        print('PASS old missing-price cached financials repaired without re-fetch')
        from valuation.core.models import Financials
        from valuation.core.rules import cross_validate
        one = repaired['financials']
        fin = Financials(price=one['price'], shares_outstanding=one['shares_outstanding'],
                         market_cap=one['market_cap'], data_notes=one['data_notes'])
        gates = cross_validate({}, {}, {}, {}, fin, None, {})
        codes = {g['code'] for g in gates}
        assert 'NO_MARKET_PRICE' not in codes
        assert 'SHARES_ESTIMATED' in codes
        print('PASS no false NO_MARKET_PRICE; near-estimated share warning disclosed')
        # Canonical D upstream market_data is unmodified by provider.
        from valuation.data.adapters import normalize, prepare
        payload={
            'company':{'ticker':'600519','market':'A'}, 'data_source':'canonical',
            'financials': {'years':[2023,2024,2025], 'revenue':[100,110,120]},
            'market_data':{'price':1.23, 'shares_outstanding':78900,
                           'market_cap':97047, 'price_date':'2025-01-01', 'price_source':'ABC upstream'},
            'fetch_data':False,
        }
        inp, _=normalize(payload)
        inp, _=prepare(inp,fetch=False)
        assert inp.financials.price == 1.23
        assert inp.financials.shares_outstanding == 78900
        assert inp.financials.market_cap == 97047
        print('PASS ABC canonical upstream quote never overwritten')
    print('ALL PASS')


if __name__ == '__main__':
    main()
