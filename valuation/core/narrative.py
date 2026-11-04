"""把结构化估值结果翻译成「中文结论 + 图表数据」。

原则：
  · 每个数字都来自 result，不在这里另算或编造；
  · 先给结论，再给依据，再给风险；
  · 图表数据是给前端直接画的，字段名稳定、单位明确。
"""
from __future__ import annotations


def yi(value, digits=1):
    if value is None:
        return "—"
    return f"{value / 1e8:,.{digits}f}"


def pct(value, digits=1):
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def num(value, digits=2):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def x(value, digits=2):
    if value is None:
        return "—"
    return f"{value:.{digits}f}x"


def _section(title, paragraphs, metrics=None, kind="text"):
    return {"title": title, "kind": kind, "paragraphs": [p for p in paragraphs if p],
            "metrics": metrics or []}


def build_narrative(result: dict) -> dict:
    company = result.get("company") or {}
    dcf = result.get("dcf") or {}
    comps = result.get("comps") or result.get("relative") or {}
    sotp = result.get("sotp") or {}
    ddm = result.get("ddm") or {}
    blended = result.get("blended") or {}
    scen = result.get("scenarios") or {}
    gate = result.get("industry_gate") or {}
    weights = blended.get("weights") or {}
    conf = blended.get("confidence") or "中"

    name = company.get("name") or company.get("ticker") or "标的"
    price = blended.get("current_price")
    value = blended.get("blended_per_share")
    upside = blended.get("upside")
    verdict = blended.get("verdict") or "无法判断"

    # ---------------------------------------------------------------- 头条
    if result.get("status") == "failed":
        headline = f"{name} 的估值模型未能完成：{result.get('error') or '原因见提示'}。"
    elif result.get("status") == "unsupported":
        alt = []
        if comps.get("ok"):
            alt.append("相对估值（PB/PE）")
        if ddm.get("ok"):
            alt.append("DDM/剩余收益")
        headline = (
            f"{name} 属于{gate.get('reason') or '标准 DCF 不适用的行业'}，"
            f"系统未输出标准 DCF；已切换为{' + '.join(alt) if alt else '行业诊断'}口径。"
        )
        if value is not None:
            headline += f" 替代方法给出的每股价值约 {num(value)} {company.get('currency', 'CNY')}。"
    elif value is None:
        headline = f"{name} 的估值已计算，但缺少股价/股本，无法给出每股价值；股权价值见明细。"
    else:
        headline = (
            f"按规则层选定的方法组合，{name} 的每股价值约 {num(value)} "
            f"{company.get('currency', 'CNY')}，较现价 {num(price)} "
            f"{'有' if (upside or 0) >= 0 else '有'}{pct(abs(upside)) if upside is not None else '—'}"
            f"{'上行' if (upside or 0) >= 0 else '下行'}空间，判断为「{verdict}」。"
            f"综合置信度：{conf}。"
        )
        if blended.get("range_low") is not None and blended.get("range_high") is not None:
            low, high = blended["range_low"], blended["range_high"]
            position = None
            if price is not None and high > low:
                position = (price - low) / (high - low)
            headline += (
                f" 方法区间为每股 {num(low)}–{num(high)} 元"
                + (f"，现价位于区间 {position:.0%} 分位" if position is not None else "")
                + "；单点加权值仅作参考，不宜直接当作目标价。"
            )

    method_parts = [f"{_method_label(k)} {pct(w)}" for k, w in weights.items() if w > 0.001]
    method_para = (
        f"本次采用：{'；'.join(method_parts) if method_parts else '无'}。"
        f"权重规则：{blended.get('weight_source') or '—'}。"
    )
    if blended.get("divergence") is not None:
        method_para += (
            f" 方法之间的估值分歧为 {pct(blended['divergence'])}；"
            + ("分歧超过 50%，规则层已降低次要方法权重，以可靠性更高的方法为主。"
               if blended["divergence"] > 0.5 else "分歧在可接受范围内。")
        )
    if blended.get("primary"):
        method_para += f" 主方法为 {_method_label(blended['primary'])}。"

    sections = []
    sections.append(_section(
        "结论摘要",
        [headline, method_para],
        metrics=[
            {"label": "融合每股价值", "value": value, "unit": company.get("currency", "CNY"), "fmt": "money"},
            {"label": "当前股价", "value": price, "unit": company.get("currency", "CNY"), "fmt": "money"},
            {"label": "上行/下行空间", "value": upside, "unit": "%", "fmt": "pct"},
            {"label": "估值判断", "value": verdict, "unit": "", "fmt": "text"},
            {"label": "置信度", "value": conf, "unit": "", "fmt": "text"},
        ],
    ))

    # ---------------------------------------------------------------- 方法选择
    selection_paras = []
    plan = result.get("method_plan") or {}
    if plan.get("reason"):
        selection_paras.append(plan["reason"])
    if gate:
        support_label = {"supported": "支持", "limited": "有限支持",
                         "unsupported": "不支持"}.get(gate.get("support"), gate.get("support"))
        selection_paras.append(f"行业门槛：{support_label}。{gate.get('reason')}")
    rel = result.get("reliabilities") or {}
    if rel:
        selection_paras.append(
            "可靠性评分：" + "；".join(
                f"{_method_label(k)} {v.get('score', '—')} 分（{v.get('level', '—')}）"
                for k, v in rel.items() if v.get("score") is not None
            ) + "。"
        )
    if selection_paras:
        sections.append(_section("方法选择与权重", selection_paras))

    # ---------------------------------------------------------------- Comps
    if comps.get("ok"):
        sel = comps.get("peer_selection") or {}
        paras = []
        if sel.get("selection_note"):
            paras.append(sel["selection_note"])
        if sel.get("peers"):
            paras.append(
                "可比公司：" + "、".join(
                    f"{p.get('name')}（{p.get('ticker')}）" for p in sel["peers"][:8]
                ) + "。逐家选取理由见下表。"
            )
        for r in (comps.get("results") or [])[:6]:
            paras.append(
                f"{r['label']}：同业中位 {x(r['peer_median'])}（{r['sample_count']} 家），"
                f"调整 {r['adjustment']:+.1%} 后采用 {x(r['applied_multiple'])}，"
                f"隐含股权价值 {yi(r['implied_equity_value'])} 亿元、每股 {num(r['implied_per_share'])} 元。"
                f"调整理由：{r.get('adjustment_reason') or '—'}。"
            )
        if comps.get("judgment"):
            paras.append("目标估值水平：" + comps["judgment"] + "。")
        vr = comps.get("valuation_range") or {}
        paras.append(
            f"相对估值区间：每股 {num(vr.get('low_per_share'))}–{num(vr.get('high_per_share'))} 元，"
            f"中位 {num(vr.get('mid_per_share'))} 元。"
        )
        sections.append(_section(
            "相对估值（Comps）",
            paras,
            metrics=[
                {"label": "同业中位隐含每股", "value": comps.get("implied_per_share"), "unit": company.get("currency", "CNY"), "fmt": "money"},
                {"label": "区间下限", "value": vr.get("low_per_share"), "unit": company.get("currency", "CNY"), "fmt": "money"},
                {"label": "区间上限", "value": vr.get("high_per_share"), "unit": company.get("currency", "CNY"), "fmt": "money"},
                {"label": "采用倍数", "value": len(comps.get("results") or []), "unit": "个", "fmt": "int"},
            ],
        ))

    # ---------------------------------------------------------------- DCF
    if dcf.get("ok"):
        wb = dcf.get("wacc_block") or {}
        paras = [
            f"预测期 {dcf.get('forecast_years')} 年；首年收入增速 {pct(dcf.get('revenue_growth_y1'))}，"
            f"线性衰减至永续增长率 {pct(dcf.get('terminal_growth'))}；EBIT 利润率 {pct(dcf.get('ebit_margin'))}，"
            f"资本开支/收入 {pct(dcf.get('capex_pct'))}，折旧摊销/收入 {pct(dcf.get('da_pct'))}，"
            f"营运资本增加/收入 {pct(dcf.get('nwc_pct'))}，所得税率 {pct(dcf.get('tax_rate'))}。",
            f"WACC：rf {pct(wb.get('risk_free'))} + β {num(wb.get('beta'))} × ERP {pct(wb.get('erp'))}"
            f"（+ 规模溢价 {pct(wb.get('size_premium'))}）= Ke {pct(wb.get('cost_of_equity'))}；"
            f"Kd {pct(wb.get('cost_of_debt'))}，D/(D+E) {pct(wb.get('debt_ratio'))}，"
            f"CAPM WACC {pct(wb.get('wacc_capm'))}，最终采用 {pct(dcf.get('wacc'))}。",
        ]
        if dcf.get("wacc_reconciliation"):
            recon = dcf["wacc_reconciliation"]
            paras.append(
                f"折现率校准：CAPM 与市场隐含折现率相差 {abs(recon.get('gap', 0)) * 10000:.0f}bp，"
                f"规则向市场隐含值靠拢 {abs(recon.get('adjustment', 0)) * 10000:.0f}bp；"
                f"市场隐含 WACC 为 {pct(recon.get('implied_wacc'))}。"
            )
        paras.append(
            f"终值：Gordon {yi(dcf.get('tv_gordon'))} 亿元、退出倍数 {yi(dcf.get('tv_exit'))} 亿元、"
            f"ROIC 再投资口径 {yi(dcf.get('tv_roic'))} 亿元，采用 {yi(dcf.get('tv_base'))} 亿元；"
            f"终值占企业价值 {pct(dcf.get('tv_ratio'))}。"
        )
        paras.append(
            f"DCF 结论：企业价值 {yi(dcf.get('enterprise_value'))} 亿元，股权价值 {yi(dcf.get('equity_value'))} 亿元，"
            f"每股 {num(dcf.get('per_share'))} 元。"
        )
        sections.append(_section(
            "绝对估值（DCF / FCFF）",
            paras,
            metrics=[
                {"label": "DCF 每股价值", "value": dcf.get("per_share"), "unit": company.get("currency", "CNY"), "fmt": "money"},
                {"label": "WACC", "value": dcf.get("wacc"), "unit": "%", "fmt": "pct"},
                {"label": "永续增长率", "value": dcf.get("terminal_growth"), "unit": "%", "fmt": "pct"},
                {"label": "终值占比", "value": dcf.get("tv_ratio"), "unit": "%", "fmt": "pct"},
            ],
        ))

    # ---------------------------------------------------------------- SOTP
    if sotp.get("ok"):
        paras = [
            f"分部来源：{result.get('segment_source') or '—'}；收入覆盖 {pct(sotp.get('revenue_coverage'))}。",
        ]
        for r in (sotp.get("rows") or [])[:8]:
            paras.append(
                f"{r['name']}：收入 {yi(r.get('revenue'))} 亿元，采用 {r.get('multiple_type')} "
                f"{x(r.get('multiple'))}（{', '.join(r.get('peer_names') or []) or '公司整体倍数'}），"
                f"分部 EV {yi(r.get('segment_ev'))} 亿元。"
            )
        paras.append(
            f"分部 EV 合计 {yi(sotp.get('segment_ev_total'))} 亿元，扣总部费用 {yi(sotp.get('corporate_cost'))} 亿元、"
            f"净负债 {yi(sotp.get('net_debt'))} 亿元后，股权价值 {yi(sotp.get('equity_value'))} 亿元，"
            f"每股 {num(sotp.get('per_share'))} 元。"
        )
        if sotp.get("conglomerate_discount") is not None:
            disc = sotp["conglomerate_discount"]
            paras.append(
                f"SOTP 每股相对现价：{disc:+.1%}"
                + ("（SOTP 高于现价，现价相对分部价值折价）" if disc > 0
                   else "（SOTP 低于现价，现价相对分部价值溢价）") + "。"
            )
        sections.append(_section(
            "分部估值（SOTP）",
            paras,
            metrics=[
                {"label": "SOTP 每股价值", "value": sotp.get("per_share"), "unit": company.get("currency", "CNY"), "fmt": "money"},
                {"label": "分部数量", "value": sotp.get("segment_count"), "unit": "个", "fmt": "int"},
                {"label": "收入覆盖", "value": sotp.get("revenue_coverage"), "unit": "%", "fmt": "pct"},
            ],
        ))

    # ---------------------------------------------------------------- DDM
    if ddm.get("ok"):
        sections.append(_section(
            "绝对估值替代（DDM / 剩余收益）",
            [
                f"金融行业不适用标准 FCFF/WACC：{ddm.get('note')}",
                f"Ke {pct(ddm.get('cost_of_equity'))}、增长率 {pct(ddm.get('growth'))}、"
                f"分红率 {pct(ddm.get('payout_ratio'))}（{ddm.get('payout_source')}）、ROE {pct(ddm.get('roe'))}。",
                f"稳定增长 DDM {yi(ddm.get('ddm_value'))} 亿元，剩余收益 {yi(ddm.get('ri_value'))} 亿元，"
                f"取中点得股权价值 {yi(ddm.get('equity_value'))} 亿元，每股 {num(ddm.get('per_share'))} 元。",
            ],
            metrics=[
                {"label": "DDM/RI 每股价值", "value": ddm.get("per_share"), "unit": company.get("currency", "CNY"), "fmt": "money"},
                {"label": "股权成本 Ke", "value": ddm.get("cost_of_equity"), "unit": "%", "fmt": "pct"},
            ],
        ))

    # ---------------------------------------------------------------- 情景与敏感性
    if scen.get("base"):
        paras = []
        for key in ("bull", "base", "bear"):
            s = scen.get(key) or {}
            paras.append(
                f"{s.get('label', key)}：每股 {num(s.get('per_share'))} 元；"
                f"首年增速 {pct(s.get('growth_y1'))}、EBIT 利润率 {pct(s.get('ebit_margin'))}、"
                f"WACC {pct(s.get('wacc'))}。"
            )
        sections.append(_section("三情景", paras))

    # ---------------------------------------------------------------- 风险
    risk_paras = []
    for g in result.get("gates") or []:
        risk_paras.append(f"[{g.get('severity', 'info')}] {g.get('message')}")
    for w in (result.get("warnings") or [])[:10]:
        risk_paras.append(str(w))
    if risk_paras:
        sections.append(_section("关键风险与待核验", risk_paras))

    return {
        "headline": headline,
        "verdict": verdict,
        "confidence": conf,
        "sections": sections,
        "disclaimer": result.get("disclaimer") or
        "本结果由模型按既定假设计算，仅供研究与教学用途，不构成投资建议。",
    }


def build_charts(result: dict) -> dict:
    company = result.get("company") or {}
    dcf = result.get("dcf") or {}
    comps = result.get("comps") or result.get("relative") or {}
    sotp = result.get("sotp") or {}
    blended = result.get("blended") or {}
    scen = result.get("scenarios") or {}
    sens = result.get("sensitivity") or {}

    charts = {}

    # FCF 预测图
    if dcf.get("ok"):
        rows = dcf.get("rows") or []
        charts["dcf_forecast"] = {
            "title": "未来 5 年收入、EBIT 与自由现金流预测",
            "unit": "亿元",
            "years": [r.get("year") for r in rows],
            "series": {
                "revenue": [round((r.get("revenue") or 0) / 1e8, 2) for r in rows],
                "ebit": [round((r.get("ebit") or 0) / 1e8, 2) for r in rows],
                "fcff": [round((r.get("fcff") or 0) / 1e8, 2) for r in rows],
                "capex": [round((r.get("capex") or 0) / 1e8, 2) for r in rows],
                "da": [round((r.get("da") or 0) / 1e8, 2) for r in rows],
                "delta_nwc": [round((r.get("delta_nwc") or 0) / 1e8, 2) for r in rows],
            },
            "ratios": {
                "growth": [r.get("growth") for r in rows],
                "ebit_margin": [r.get("ebit_margin") for r in rows],
                "capex_pct": [r.get("capex_pct") for r in rows],
                "da_pct": [r.get("da_pct") for r in rows],
                "nwc_pct": [r.get("nwc_pct") for r in rows],
            },
            "base_year": dcf.get("base_year"),
        }
        charts["tv_composition"] = {
            "title": "终值三种口径与企业价值构成",
            "unit": "亿元",
            "items": [
                {"label": "Gordon 永续法", "value": round((dcf.get("tv_gordon") or 0) / 1e8, 2)},
                {"label": "退出倍数法", "value": round((dcf.get("tv_exit") or 0) / 1e8, 2)},
                {"label": "ROIC 再投资法", "value": round((dcf.get("tv_roic") or 0) / 1e8, 2)},
                {"label": "采用终值", "value": round((dcf.get("tv_base") or 0) / 1e8, 2)},
            ],
            "tv_ratio": dcf.get("tv_ratio"),
        }

    # 估值水平图
    vr = comps.get("valuation_range") or {}
    charts["valuation_range"] = {
        "title": "估值水平：相对估值区间 vs 现价 vs 融合值",
        "unit": company.get("currency", "CNY"),
        "low": vr.get("low_per_share"),
        "mid": vr.get("mid_per_share"),
        "high": vr.get("high_per_share"),
        "price": blended.get("current_price"),
        "blended": blended.get("blended_per_share"),
        "dcf": dcf.get("per_share") if dcf.get("ok") else None,
        "sotp": sotp.get("per_share") if sotp.get("ok") else None,
    }

    # 敏感性
    if sens.get("wacc_g"):
        charts["sensitivity_wacc_g"] = sens["wacc_g"]
    if sens.get("growth_margin"):
        charts["sensitivity_growth_margin"] = sens["growth_margin"]

    # 情景
    if scen.get("base"):
        charts["scenarios"] = {
            "title": "Bull / Base / Bear 每股价值",
            "unit": company.get("currency", "CNY"),
            "labels": [scen["bull"].get("label"), scen["base"].get("label"), scen["bear"].get("label")],
            "values": [scen["bull"].get("per_share"), scen["base"].get("per_share"), scen["bear"].get("per_share")],
            "levers": [scen["bull"].get("levers"), scen["base"].get("levers"), scen["bear"].get("levers")],
        }

    # Comps 倍数定位
    if comps.get("ok"):
        pos = comps.get("positioning") or {}
        charts["comps_position"] = {
            "title": "目标公司倍数在同业分布中的位置",
            "items": [
                {
                    "multiple": key,
                    "label": v.get("label"),
                    "target": v.get("target"),
                    "peer_median": v.get("peer_median"),
                    "peer_min": v.get("peer_min"),
                    "peer_max": v.get("peer_max"),
                    "percentile": v.get("percentile"),
                    "premium_discount": v.get("premium_discount"),
                }
                for key, v in pos.items()
            ],
            "peer_count": comps.get("peer_count"),
        }

    # 权重与可靠性
    charts["weights"] = {
        "title": "方法权重与可靠性",
        "items": [
            {"method": k, "label": _method_label(k), "weight": w,
             "reliability": (result.get("reliabilities") or {}).get(k, {}).get("score")}
            for k, w in (blended.get("weights") or {}).items() if w > 0.001
        ],
    }
    return charts


def _method_label(key: str) -> str:
    return {
        "dcf": "DCF（收益法）",
        "comps": "Comps（相对估值）",
        "sotp": "SOTP（分部估值）",
        "ddm": "DDM/剩余收益",
    }.get(key, key)
