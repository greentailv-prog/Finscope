"""Segment-driver 5Y model, with optional mechanically balanced three statements.
All amounts CNY; ratios decimals. Historical inputs must come from upstream evidence.
No automatic assumption interpolation masquerading as disclosed historical data.
"""
from __future__ import annotations
from math import isfinite


def _f(v, label, *, positive=False, nonnegative=False):
    if v is None or isinstance(v, bool):
        raise ValueError(f"缺少必填字段 {label}")
    v = float(v)
    if not isfinite(v):
        raise ValueError(f"无效数值 {label}")
    if (positive and v <= 0) or (nonnegative and v < 0):
        raise ValueError(f"{label} 数值不符合约束")
    return v


def _rate(v, label, low=0.0, high=1.0):
    r = _f(v, label)
    if not low <= r <= high:
        raise ValueError(f"{label} 超出 [{low},{high}] 范围")
    return r


def _path(s, field, n, *, low=None, high=None):
    v=s.get(field)
    if not isinstance(v,list) or len(v)!=n:
        raise ValueError(f"{s.get('name','分部')} 缺少 {n} 年 {field} 预测路径")
    out=[_f(x,f"{s.get('name')} {field}[{i}]") for i,x in enumerate(v)]
    if low is not None and any(x<low or x>high for x in out):
        raise ValueError(f"{s.get('name')} {field} 超出合理范围")
    return out


def _opening_bs(cfg):
    bs=cfg.get('opening_balance')
    if not bs:
        return None
    keys=('cash','receivables','inventory','other_assets','ppe','payables','other_liabilities','debt','equity')
    s={k:_f(bs.get(k),f'opening_balance.{k}',nonnegative=k not in ('equity',)) for k in keys}
    if 'minority_interest' in bs:
        s['minority_interest']=_f(bs['minority_interest'],'opening_balance.minority_interest',nonnegative=True)
    else:
        s['minority_interest']=0.0
    a=s['cash']+s['receivables']+s['inventory']+s['other_assets']+s['ppe']
    l=s['payables']+s['other_liabilities']+s['debt']+s['equity']+s['minority_interest']
    if abs(a-l)>max(1,abs(a))*1e-6:
        raise ValueError(f'期初资产负债表不平衡，差异 {a-l:,.2f} 元')
    return s


def project(config: dict, financials=None) -> dict:
    """Strict forecast. Segment sales and full-statement balances never invented.

    operating_forecast = {
      'base_year':2025, 'years':5, 'as_of':'2025-12-31',
      'segments':[{'name':'业务A','base_revenue':..., 'growth_path':[...],
           'gross_margin_path':[...], 'opex_ratio_path':[...] , 'source_url':...}],
      'tax_rate':0.2, 'capex_ratio_path':[...], 'da_ratio_path':[...],
      'dso_days_path':[...], 'dio_days_path':[...], 'dpo_days_path':[...],
      'opening_working_capital':{'receivables':...,'inventory':...,'payables':...},
      'other_nwc_opening':0, 'other_nwc_ratio_path':[0]*5,
      'opening_balance':{...}  # optional but required for full 3-statement
    }
    """
    try:
        n=int(config.get('years',5))
        if not 3<=n<=10: raise ValueError('预测期限必须在3–10年内')
        year=int(config['base_year'])
        segs=config.get('segments')
        if not isinstance(segs,list) or len(segs)<1: raise ValueError('必须提供至少一个真实业务分部')
        if len(set(s.get('name') for s in segs))!=len(segs): raise ValueError('业务分部名称重复')
        opening_wc=config.get('opening_working_capital') or {}
        full_bs=_opening_bs(config)
        if full_bs:
            base_ar,base_inv,base_ap=(full_bs[k] for k in ('receivables','inventory','payables'))
        elif opening_wc:
            base_ar,base_inv,base_ap=(_f(opening_wc.get(k),f'opening_working_capital.{k}',nonnegative=True) for k in ('receivables','inventory','payables'))
        elif financials and all(getattr(financials,k,None) is not None for k in ('receivables','inventory','payables')):
            base_ar,base_inv,base_ap=(float(getattr(financials,k)) for k in ('receivables','inventory','payables'))
        else:
            raise ValueError('缺少期初应收、存货与应付，禁止假定营运资本为零')
        other_nwc=_f(config.get('other_nwc_opening'), 'other_nwc_opening')
        tax=_rate(config.get('tax_rate'),'tax_rate',0,.5)
        da_path=_path(config,'da_ratio_path',n,low=0,high=.4)
        capex_path=_path(config,'capex_ratio_path',n,low=0,high=1.0)
        dso=_path(config,'dso_days_path',n,low=0,high=1000)
        dio=_path(config,'dio_days_path',n,low=0,high=1000)
        dpo=_path(config,'dpo_days_path',n,low=0,high=1000)
        other_ratio=_path(config,'other_nwc_ratio_path',n,low=-1,high=1)
        if full_bs is not None and (abs(other_nwc)>1e-9 or any(abs(x)>1e-9 for x in other_ratio)):
            raise ValueError('完整三表模式下其他经营营运资本尚无资产负债表映射，必须为零或先补齐明细')
        dividend_path=config.get('dividend_path',[0]*n)
        debt_change_path=config.get('debt_change_path',[0]*n)
        equity_issue_path=config.get('equity_issue_path',[0]*n)
        if full_bs:
            interest_rate_path=_path(config,'interest_rate_path',n,low=0,high=.4)
            for key,seq in [('dividend_path',dividend_path),('debt_change_path',debt_change_path),('equity_issue_path',equity_issue_path)]:
                if len(seq)!=n: raise ValueError(f'{key} 数组长度不符')
        revenue_base=0.0; paths=[]
        for s in segs:
            base=_f(s.get('base_revenue'),f"{s.get('name')}.base_revenue",positive=True)
            growth=_path(s,'growth_path',n,low=-.8,high=4)
            margins=_path(s,'gross_margin_path',n,low=-.5,high=1)
            opex=_path(s,'opex_ratio_path',n,low=0,high=1)
            revenue_base+=base
            paths.append((s,base,growth,margins,opex))
        if financials:
            known=financials.latest(financials.revenue)
            if known and abs(revenue_base-known)/known>.05:
                raise ValueError(f'分部历史基期收入合计与财报差异超过5%（{revenue_base/known-1:+.1%}），请核实并购并表时点')
            if financials.years and financials.years[-1]!=year:
                raise ValueError('预测模型基期与财报基期年份不符')
        warnings=[]
        if not config.get('as_of'): warnings.append('缺失预测基准日；不得作为正式目标价依据')
        if any(not s.get('source_url') for s in segs): warnings.append('存在未填写年报来源的分部基期，估值需人工复核')
        base_wc=base_ar+base_inv-base_ap+other_nwc
        rows=[]
        for j in range(n):
            pieces=[]; sales=0; cogs=0; ebit=0
            new_paths=[]
            for s,prev,gr,gm,op in paths:
                rev=prev*(1+gr[j]); gp=rev*gm[j]; sgna=rev*op[j]; e=gp-sgna
                pieces.append({'name':s['name'],'revenue':rev,'growth':gr[j], 'cogs':rev-gp,'gross_profit':gp,'opex':sgna,'ebit':e})
                sales+=rev; cogs+=rev-gp; ebit+=e
                new_paths.append((s,rev,gr,gm,op))
            paths=new_paths
            ar=sales*dso[j]/365; inv=cogs*dio[j]/365; ap=cogs*dpo[j]/365
            current_other=other_ratio[j]*sales
            wc=ar+inv-ap+current_other
            delta_wc=wc-base_wc
            da=sales*da_path[j]; capex=sales*capex_path[j]
            cash_tax=max(0.0,ebit)*tax
            nopat=ebit-cash_tax
            fcff=nopat+da-capex-delta_wc
            row={'year':year+j+1,'year_index':j+1,'segments':pieces,
                'revenue':sales,'cogs':cogs,'gross_profit':sales-cogs,'ebit':ebit,
                'ebit_margin':ebit/sales if sales else None,'cash_tax':cash_tax,'nopat':nopat,
                'da':da,'capex':capex,'delta_nwc':delta_wc,'fcff':fcff,
                'receivables':ar,'inventory':inv,'payables':ap,'other_nwc':current_other,'operating_nwc':wc,
                'da_pct':da_path[j],'capex_pct':capex_path[j],'nwc_pct':delta_wc/sales if sales else None,
                'source':'scenario_driver_estimate'}
            if full_bs:
                debt_start=full_bs['debt']; debt_end=debt_start+_f(debt_change_path[j],f'debt_change_path[{j}]')
                if debt_end < 0: raise ValueError('预测债务余额出现负数')
                interest=(debt_start+debt_end)/2*interest_rate_path[j]
                pretax=ebit-interest; tax_exp=max(0,pretax)*tax; net_income=pretax-tax_exp
                div=_f(dividend_path[j],f'dividend_path[{j}]',nonnegative=True)
                equity_issue=_f(equity_issue_path[j],f'equity_issue_path[{j}]',nonnegative=True)
                cfo=net_income+da-delta_wc
                cfi=-capex
                cff=debt_end-debt_start-div+equity_issue
                cash=full_bs['cash']+cfo+cfi+cff
                if cash < -1: raise ValueError('预测现金余额为负，缺少明确融资方案，模型不能自动补出资金')
                cash=max(cash,0)
                ppe=full_bs['ppe']+capex-da
                if ppe<0: raise ValueError('预测固定资产净额为负：折旧/资本开支不匹配')
                equity=full_bs['equity']+net_income-div+equity_issue
                total_assets=cash+ar+inv+full_bs['other_assets']+ppe
                total_liab_equity=ap+full_bs['other_liabilities']+debt_end+equity+full_bs['minority_interest']
                balance_error=total_assets-total_liab_equity
                if abs(balance_error)>max(1,abs(total_assets))*1e-7:
                    raise AssertionError(f'三表平衡错误: {balance_error:.2f}')
                row['income_statement']={'revenue':sales,'cogs':cogs,'gross_profit':sales-cogs,'opex':sum(x['opex'] for x in pieces),
                                         'ebit':ebit,'interest':interest,'pretax':pretax,'tax':tax_exp,'net_income':net_income}
                row['cash_flow_statement']={'cfo':cfo,'capex':capex,'cfi':cfi,'cff':cff,'change_cash':cfo+cfi+cff,'ending_cash':cash,
                                           'dividends':div,'debt_change':debt_end-debt_start,'equity_issue':equity_issue}
                row['balance_sheet']={'cash':cash,'receivables':ar,'inventory':inv,'ppe':ppe,
                                       'other_assets':full_bs['other_assets'],'total_assets':total_assets,
                                       'payables':ap,'other_liabilities':full_bs['other_liabilities'],
                                       'debt':debt_end,'equity':equity,'minority_interest':full_bs['minority_interest'],
                                       'liabilities_equity':total_liab_equity,'balance_check':balance_error}
                full_bs.update({'cash':cash,'receivables':ar,'inventory':inv,'payables':ap,'ppe':ppe,'debt':debt_end,'equity':equity})
            rows.append(row)
            base_wc=wc
        return {'ok':True,'status':'review_required' if warnings else 'ok',
                'mode':'three_statement' if full_bs is not None else 'operating_fcff',
                'years':n,'base_year':year,'rows':rows,'base_revenue':revenue_base,
                'inputs_snapshot':config,
                'warnings':warnings,'assumptions_version':config.get('version','manual_v1'),
                'note':'业务假设为预测情景，不代表财报披露或分析师一致预期。'}
    except (ValueError,KeyError,TypeError,AssertionError) as exc:
        return {'ok':False,'status':'blocked','error':str(exc),'rows':[]}
