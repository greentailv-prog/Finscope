"""Evidence-first candidate registry. Product overlap != permission to calculate a median.
No online market multiples are invented or stored in this module.
"""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path

FILE=Path(__file__).resolve().parents[1]/'config'/'verified_peer_research.json'


def research(ticker:str, as_of: str|None=None)->dict:
    data=json.loads(FILE.read_text(encoding='utf-8'))
    profile=data.get('profiles',{}).get(str(ticker))
    if not profile:
        return {'ok':False,'status':'not_covered','ticker':str(ticker),'candidates':[],
                'message':'业务可比证据库尚未覆盖，不允许随意使用大行业代理。'}
    candidates=[]
    for seg in profile['segments']:
        for item in seg['candidates']:
            x={**item,'segment_id':seg['segment_id'],'segment_name':seg['name']}
            x['selection_score_research_only']=(x['business_overlap']*15+x['purity']*10)
            x['eligibility']='needs_market_caliber_and_approval'
            candidates.append(x)
    future=as_of and as_of < profile.get('as_of','')
    return {'ok':True,'ticker':str(ticker),'status':'review_required',
            'as_of_requested':as_of,'research_updated':data['database_version'],
            'source_after_as_of':bool(future),'segments':profile['segments'],
            'candidates':candidates,'material_events':profile.get('material_events',[]),
            'rules':{'minimum_verified_multiples':2,'same_period_required':True,
                     'same_currency_ev_adjustment':True,'must_confirm':True,
                     'forward_metrics_as_of_must_be_historical':True},
            'warnings':['产品相似性证据不等于可直接使用合并报表PE或EV/Revenue。',
                        '目前没有经核验的同基准日分部纯业务倍数，Comps/SOTP应保持待核验。']}


def validate_for_comps(record:dict, market_data:list[dict], valuation_date:str)->dict:
    """Business evidence and dated financial-market metrics must BOTH be approved.

    Approval is explicit, attributable and dated. Candidate registry is research-only,
    so this function never flips a candidate into an approved peer automatically.
    All usable samples must belong to one segment, one multiple caliber, one date.
    """
    byid={(str(x['ticker']),x['segment_id']):x for x in record.get('candidates',[])}
    accepted=[]; rejected=[]
    for item in market_data:
        key=(str(item.get('ticker')),str(item.get('segment_id')))
        candidate=byid.get(key)
        reasons=[]
        if record.get('source_after_as_of'):
            reasons.append('业务证据发布时间晚于估值基准日，存在前瞻信息偏差')
        if not candidate:
            reasons.append('不在核验过的业务证据候选库')
        else:
            approval=item.get('analyst_approved') is True
            analyst=item.get('approved_by')
            approval_date=item.get('approval_date')
            if not (approval and analyst and approval_date and approval_date<=valuation_date):
                reasons.append('缺少合规的业务可比性人工签核（人名及不晚于估值日的签核日期）')
            if not (item.get('business_evidence_url') or candidate.get('evidence_url')):
                reasons.append('缺少产品与客户的业务可比证据来源')
            if candidate.get('purity',0)<3 and not (
                item.get('pure_play_financials_confirmed') and item.get('pure_play_financials_source_url')):
                reasons.append('集团业务多元化，缺少已核验的纯业务财务及分部来源')
        if not item.get('data_source_url'): reasons.append('缺少倍数及财务数据来源')
        dt=item.get('market_as_of')
        if not dt or dt>valuation_date: reasons.append('倍数取数日期缺失或晚于估值基准日')
        if not item.get('caliber'): reasons.append('LYR/TTM/NTM口径缺失')
        if not item.get('currency'): reasons.append('缺少币种，无法进行汇率与EV调整')
        vals=[item.get(k) for k in ('ev_revenue','ev_ebitda','pe')]
        if not any(isinstance(v,(int,float)) and v>0 for v in vals):
            reasons.append('未提供合法正值的可比估值倍数')
        if reasons: rejected.append({'ticker':item.get('ticker'),'segment_id':item.get('segment_id'),'reasons':reasons})
        else: accepted.append(item)
    # Different segments and trailing vs forward denominators cannot be pooled.
    groups={}
    for item in accepted:
        for metric in ('ev_revenue','ev_ebitda','pe'):
            val=item.get(metric)
            if isinstance(val,(int,float)) and val>0:
                key=(item['segment_id'],item['caliber'],metric,item['currency'],item['market_as_of'])
                groups.setdefault(key,[]).append(item)
    usable=[]
    for key,items in groups.items():
        if len({i['ticker'] for i in items})>=2:
            usable.append({'segment_id':key[0],'caliber':key[1],'metric':key[2],
                           'currency':key[3],'market_as_of':key[4],
                           'ticker_count':len({i['ticker'] for i in items}),
                           'tickers':sorted(set(i['ticker'] for i in items))})
    return {'ok':bool(usable),'approved':accepted,'rejected':rejected,
            'usable_groups':usable,'status':'approved_for_specific_groups' if usable else 'review_required',
            'message':'仅同分部、同口径、同日、同币种至少2个通过的候选可进入倍数计算' if usable
            else '没有至少2家同分部同口径的已审查样本，停止可比估值'}
