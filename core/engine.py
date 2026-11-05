"""估值主编排：数据 → 假设 → 方法 → 规则定权 → 融合 → 披露。

对外只有一个入口 `run(payload)`，输入输出都是纯 JSON。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from statistics import median

from . import assumptions as asm_rules
from . import comps as comps_engine
from . import dcf as dcf_engine
from . import ddm as ddm_engine
from . import defaults
from . import narrative
from . import rules
from . import sensitivity
from . import sotp as sotp_engine
from .metrics import safe_div, series_growth
from .models import Assumptions, Financials, Peer, Segment, ValuationInput
from ..data import adapters
from ..data import akshare_provider as ak
from ..data.peer_selector import segment_peer_multiple
from ..data.sources import merge, source
from ..research.driver_forecast import project as project_operating_forecast


DISCLAIMER = ("本结果由模型按既定假设计算，仅供研究与教学用途，不构成投资建议。"
              "估值结论依赖假设，假设比模型重要。")


def _method_label(key: str) -> str:
    return {"dcf": "DCF（收益法）", "comps": "Comps（相对估值）",
            "sotp": "SOTP（分部估值）", "ddm": "DDM/剩余收益"}.get(key, key)


def _package_root() -> Path:
    """交付包根目录（valuation 的上一级）。"""
    return Path(__file__).resolve().parents[2]


def _as_return_path(path: Path) -> str:
    """对外返回包内相对路径；包外路径保持绝对路径。"""
    path = Path(path).resolve()
    try:
        return path.relative_to(_package_root()).as_posix()
    except ValueError:
        return str(path)


def _abs_output_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else (_package_root() / path)


def _ratio_series(num, den, absolute=False):
    out = []
    for a, b in zip(num or [], den or []):
        r = safe_div(a, b)
        if r is not None and absolute:
            r = abs(r)
        out.append(r)
    return out


def _history_block(fin: Financials) -> dict:
    """历史财务与比率：给前端画「实际 5 年 + 预测 5 年」的对照图。"""
    years = list(fin.years or [])
    revenue = list(fin.revenue or [])
    return {
        "years": years,
        "revenue": revenue,
        "ebit": list(fin.ebit or []),
        "net_income": list(fin.net_income or []),
        "net_income_parent": list(fin.net_income_parent or []),
        "cogs": list(fin.cogs or []),
        "gross_profit": list(fin.gross_profit or []),
        "da": list(fin.da or []),
        "capex": list(fin.capex or []),
        "cfo": list(fin.cfo or []),
        "delta_nwc": list(fin.delta_nwc or []),
        "revenue_growth": series_growth(revenue),
        "ebit_margin": _ratio_series(fin.ebit, revenue),
        "net_margin": _ratio_series(fin.net_income, revenue),
        "gross_margin": _ratio_series(fin.gross_profit, revenue),
        "capex_pct": _ratio_series(fin.capex, revenue, absolute=True),
        "da_pct": _ratio_series(fin.da, revenue, absolute=True),
        "nwc_pct": _ratio_series(fin.delta_nwc, revenue, absolute=False),
        "tax_rate": _ratio_series(fin.tax_provision, fin.pretax_income),
    }


def _selected_methods(method_selection: str, gate: dict) -> tuple[list[str], str]:
    sel = (method_selection or "auto").lower()
    if sel in ("dcf", "comps", "sotp", "ddm"):
        methods = [sel]
        reason = f"使用者选择单一方法：{_method_label(sel)}。"
    elif sel in ("auto", "blended", ""):
        methods = ["dcf", "comps", "sotp"]
        reason = "自动模式：运行所有结构上适用的方法，并按规则定权融合。"
    else:
        methods = [m.strip() for m in sel.replace("+", ",").split(",") if m.strip()]
        reason = f"使用者选择方法组合：{', '.join(_method_label(m) for m in methods)}。"

    if gate.get("support") == "unsupported" or gate.get("standard_fcff_supported") is False:
        if "dcf" in methods:
            alt = gate.get("primary_absolute")
            methods = [m for m in methods if m != "dcf"]
            if alt and alt not in methods:
                methods.insert(0, alt)
            reason += (f" 行业门槛：{gate.get('reason')} 标准 DCF 已替换为"
                       f"{_method_label(alt) if alt else '行业适用口径'}。")
        gate_text = (gate.get("reason") or "") + " ".join(gate.get("keywords") or [])
        if "sotp" in methods and any(
                k in gate_text for k in ("银行", "保险", "证券", "券商", "房地产", "地产", "REIT")):
            methods = [m for m in methods if m != "sotp"]
            reason += " 金融/地产的分部口径不适用，SOTP 未纳入。"
    if not methods:
        methods = ["comps"]
        reason += " 没有可用的绝对估值替代，回退到 Comps。"
    return methods, reason


def _segment_multiple_for(seg: Segment, peer_cache: dict,
                          fallback_ev_revenue: float | None,
                          fallback_ev_ebitda: float | None) -> None:
    if seg.multiple:
        return
    info = segment_peer_multiple(seg.name, max_peers=4, cache=peer_cache)
    if info.get("ok"):
        seg.peer_names = info.get("peer_names") or []
        seg.peer_tickers = info.get("peer_tickers") or []
        seg.peer_median_ev_revenue = (info.get("medians") or {}).get("ev_revenue")
        seg.peer_median_ev_ebitda = (info.get("medians") or {}).get("ev_ebitda")
        seg.peer_median_pe = (info.get("medians") or {}).get("pe")
        seg.note = (f"纯业务同业：{', '.join(seg.peer_names)}；"
                    "优先 EV/EBITDA，缺失时用 EV/Revenue")
    else:
        seg.peer_median_ev_revenue = None
        seg.peer_median_ev_ebitda = None
        seg.note = f"{info.get('reason') or '未匹配到纯业务同业'}；没有可验证的纯业务倍数，禁止用集团倍数兜底"


def _blend(method_values: dict, weights: dict, fin: Financials,
           values_equity: dict) -> dict:
    usable = {k: v for k, v in method_values.items() if v is not None and v > 0}
    if not usable:
        return {"ok": False, "error": "没有任何方法得出有效每股价值。"}
    total_w = sum(weights.get(k, 0.0) for k in usable) or 1.0
    blended_ps = sum(usable[k] * weights.get(k, 0.0) for k in usable) / total_w
    blended_eq = sum((values_equity.get(k) or 0.0) * weights.get(k, 0.0) for k in usable) / total_w
    price = fin.price
    upside = (blended_ps / price - 1) if (price and blended_ps) else None
    return {
        "ok": True,
        "blended_per_share": blended_ps,
        "blended_equity_value": blended_eq,
        "current_price": price,
        "upside": upside,
        "verdict": rules.verdict_from_upside(upside),
        "weights": {k: round(weights.get(k, 0.0), 4) for k in usable},
        "components": [
            {"key": k, "label": _method_label(k), "per_share": usable[k],
             "weight": round(weights.get(k, 0.0), 4),
             "equity_value": values_equity.get(k)}
            for k in usable
        ],
    }


def run(payload: dict | ValuationInput, fetch: bool | None = None,
        export_excel: bool = True, excel_path: str | None = None) -> dict:
    # D 是数据质量闸门的唯一负责人；上游阻断时 C 不给出可用目标价。
    if isinstance(payload, dict) and (payload.get("data_quality") or {}).get("blocked") is True:
        return {
            "schema_version": "2.0", "status": "failed",
            "company": payload.get("company") or {},
            "error": "D 统一对象数据质量闸门已阻断，本次估值不生成方向性结论。",
            "warnings": ["请检查上游 data_quality.checks、review_queue 及受影响财务科目后重试。"],
            "sources": payload.get("sources") or [],
            "gates": [{"code": "UPSTREAM_DATA_BLOCKED", "severity": "block",
                       "message": "上游数据质量检查未通过，禁止使用估值结论。",
                       "affected_paths": ["valuation"]}],
            "disclaimer": DISCLAIMER,
        }
    # ---------------------------------------------------------------- 输入 + 数据
    if isinstance(payload, ValuationInput):
        inp, ctx = adapters.prepare(payload, fetch=fetch)
    else:
        inp, _ = adapters.normalize(payload)
        inp, ctx = adapters.prepare(inp, fetch=fetch)

    company = inp.company
    fin = inp.financials
    market = company.market or "A"
    fin.industry = fin.industry or company.industry
    fin.sector = fin.sector or company.sector

    warnings: list[str] = list(ctx.get("warnings") or [])
    sources = list(ctx.get("sources") or [])
    # 300757 has had material business mix changes. Explicit peers must pass both
    # product overlap and a same-as-of, same-segment, signed-off multiple check.
    # Doing this AFTER prepare is important: canonical / manual input can bypass
    # auto-selection otherwise, silently reintroducing unverified proxy multiples.
    if str(company.ticker) == "300757" and inp.peers:
        from ..research.peer_registry import research, validate_for_comps
        date = company.price_date or company.report_period or ""
        raw = payload.get("peers", []) if isinstance(payload, dict) else []
        peer_review = validate_for_comps(research(company.ticker, as_of=date),raw,date)
        if peer_review.get("ok"):
            # Only keep one homogeneous segment/multiple/date group.
            approved_tickers=set(peer_review["usable_groups"][0]["tickers"])
            inp.peers=[p for p in inp.peers if p.ticker in approved_tickers]
            ctx["peer_selection"]={"tier":"analyst_approved","peers":inp.peers,
                                    "peer_review":peer_review,"selection_note":"已签核纯业务与同口径日期的可比样本"}
        else:
            warnings.append("罗博特科可比公司未完成业务纯度、日期、估值口径及分析师签核，Comps已拦截。")
            inp.peers=[]
            ctx["peer_selection"]={"tier":"review_required","peers":[],
                                    "peer_review":peer_review,"selection_note":"缺少已核验的可比样本"}
    gate = defaults.industry_gate(company.industry, company.business)

    if not fin.revenue:
        return {
            "schema_version": "2.0",
            "status": "failed",
            "industry_support": gate.get("support"),
            "company": company.to_dict(),
            "error": "缺少营业收入历史数据，估值无法开始。",
            "warnings": warnings + ["请通过 D 传入 financials 或检查联网取数。"],
            "sources": merge(sources),
            "disclaimer": DISCLAIMER,
        }

    # ---------------------------------------------------------------- 假设
    market_rates = ctx.get("market_rates") or {}
    asm, ledger, asm_warnings = asm_rules.resolve(fin, company, inp.assumptions, market_rates)
    warnings.extend(asm_warnings)
    # 把估算来源挂到对象上，供可靠性评分使用
    for label, key in (("折旧摊销", "da_pct_revenue"), ("资本开支", "capex_pct_revenue"),
                       ("营运资本", "nwc_pct_revenue")):
        entry = next((e for e in ledger if e["name"].startswith(label)), None)
        setattr(asm, "_assumption_source_" + label, (entry or {}).get("source", ""))

    # 用户明确提交分业务预测时，预测结果直接驱动 DCF，而非保持旧的统一利润率插值。
    # 注意三表基期资产负债缺失则不伪造完整三表，仍能在有营运资本期初的情况下做 FCFF。
    driver_config = ((payload.get("operating_forecast") or payload.get("meta", {}).get("operating_forecast"))
                     if isinstance(payload, dict) else ((inp.meta or {}).get("operating_forecast")))
    operating_forecast = None
    if driver_config is not None:
        operating_forecast = project_operating_forecast(driver_config, fin)
        if operating_forecast.get("ok"):
            setattr(asm,"_operating_driver_rows",operating_forecast["rows"])
            setattr(asm,"_driver_review_required",operating_forecast.get("status")!="ok")
            warnings.extend(operating_forecast.get("warnings") or [])
            ledger.append({"name":"预测方法","value":"分部订单/收入+周转天数驱动",
                           "source_type":"model","source":"使用者提交的分部预测情景；假设来源见 operating_forecast",
                           "confidence":"待核验" if operating_forecast.get("warnings") else "中",
                           "unit":"", "overridable":True})
        else:
            warnings.append("分部预测未通过校验："+str(operating_forecast.get("error")))

    # ---------------------------------------------------------------- 方法计划
    methods, plan_reason = _selected_methods(inp.method_selection,
                                             gate)
    if inp.assumptions.selected_methods:
        methods = list(inp.assumptions.selected_methods)
        plan_reason = f"使用者显式选择：{', '.join(_method_label(m) for m in methods)}。"

    method_results: dict[str, dict] = {}
    run_status = {}

    # DCF
    if "dcf" in methods:
        dcf = (dcf_engine.build_dcf(fin, asm, market, inp.peers)
               if (operating_forecast is None or operating_forecast.get("ok")) else
               {"ok":False,"status":"blocked","error":"分部预测校验未通过："+operating_forecast.get("error","")})
        method_results["dcf"] = dcf
        run_status["dcf"] = "ok" if dcf.get("ok") else "failed"
        warnings.extend(dcf.get("warnings") or [])

    # Comps
    comps = {"ok": False, "error": "未运行"}
    if "comps" in methods:
        target_growth = asm.revenue_growth_y1
        comps = comps_engine.build_comps(
            fin, inp.peers, asm,
            multiples=(inp.relative_multiples or asm.multiples or None),
            industry_support=gate.get("support", "supported"),
            peer_selection=ctx.get("peer_selection") or {},
            target_growth=target_growth,
        )
        method_results["comps"] = comps
        run_status["comps"] = ("review_required" if comps.get("review_required")
                               else ("ok" if comps.get("ok") else "failed"))
        warnings.extend(comps.get("warnings") or [])

    # SOTP
    sotp = {"ok": False, "skipped": True, "reason": "未运行"}
    if "sotp" in methods:
        fallback_ev_rev = None
        fallback_ev_ebitda = None
        if comps.get("ok"):
            for r in comps.get("results") or []:
                if r.get("multiple") == "ev_revenue":
                    fallback_ev_rev = r.get("peer_median")
                if r.get("multiple") == "ev_ebitda":
                    fallback_ev_ebitda = r.get("peer_median")
            # 高毛利公司会把 EV/Revenue 排除出结论，但 SOTP 的小分部仍需要兜底倍数
            pm = comps.get("peer_multiples") or {}
            if fallback_ev_rev is None:
                fallback_ev_rev = (pm.get("ev_revenue") or {}).get("median")
            if fallback_ev_ebitda is None:
                fallback_ev_ebitda = (pm.get("ev_ebitda") or {}).get("median")
        peer_cache = {}
        for seg in inp.segments:
            _segment_multiple_for(seg, peer_cache, fallback_ev_rev, fallback_ev_ebitda)
        sotp = sotp_engine.build_sotp(fin, inp.segments, asm,
                                      fallback_ev_revenue=None,
                                      fallback_ev_ebitda=None)
        method_results["sotp"] = sotp
        run_status["sotp"] = "ok" if sotp.get("ok") else "skipped"
        warnings.extend(sotp.get("warnings") or [])

    # DDM
    ddm = {"ok": False, "error": "未运行"}
    if "ddm" in methods:
        ddm = ddm_engine.build_ddm(fin, asm, market)
        method_results["ddm"] = ddm
        run_status["ddm"] = "ok" if ddm.get("ok") else "failed"
        warnings.extend(ddm.get("warnings") or [])

    # ---------------------------------------------------------------- 可靠性
    reliabilities = {}
    if "dcf" in method_results:
        reliabilities["dcf"] = rules.dcf_reliability(method_results["dcf"], asm, fin, market)
    if "comps" in method_results and method_results["comps"].get("ok"):
        reliabilities["comps"] = rules.comps_reliability(method_results["comps"])
    if "sotp" in method_results and method_results["sotp"].get("ok"):
        reliabilities["sotp"] = rules.sotp_reliability(method_results["sotp"])
    if "ddm" in method_results and method_results["ddm"].get("ok"):
        reliabilities["ddm"] = rules.ddm_reliability(method_results["ddm"])

    # ---------------------------------------------------------------- 权重
    # 原始方法的 ok 表示算术完成；review_required 表示不得自动纳入融合。
    method_values = {}
    values_equity = {}
    if method_results.get("dcf", {}).get("ok") and not method_results["dcf"].get("review_required"):
        method_values["dcf"] = method_results["dcf"].get("per_share")
        values_equity["dcf"] = method_results["dcf"].get("equity_value")
    if method_results.get("comps", {}).get("ok") and not method_results["comps"].get("review_required"):
        method_values["comps"] = method_results["comps"].get("implied_per_share")
        values_equity["comps"] = method_results["comps"].get("implied_equity_value")
    if method_results.get("sotp", {}).get("ok"):
        method_values["sotp"] = method_results["sotp"].get("per_share")
        values_equity["sotp"] = method_results["sotp"].get("equity_value")
    if method_results.get("ddm", {}).get("ok"):
        method_values["ddm"] = method_results["ddm"].get("per_share")
        values_equity["ddm"] = method_results["ddm"].get("equity_value")

    is_financial = any(k in (company.industry or "") for k in ("银行", "保险", "证券", "券商"))
    weight_info = rules.resolve_weights(
        method_values, reliabilities,
        method_selection=inp.method_selection,
        user_weights=asm.weights,
        weight_mode=asm.weight_mode,
        has_sotp=bool(method_results.get("sotp", {}).get("ok")),
        is_financial=is_financial,
    )
    blended = _blend(method_values, weight_info.get("weights") or {}, fin, values_equity)
    if blended.get("ok"):
        blended["weight_source"] = weight_info.get("source")
        blended["confidence"] = weight_info.get("confidence")
        blended["primary"] = weight_info.get("primary")
        blended["divergence"] = weight_info.get("divergence")
        blended["trace"] = weight_info.get("trace")
        # 方法分歧超过 50% 时，不再给单一方向性判断，改为「区间参考」
        if (weight_info.get("divergence") or 0) > 0.50:
            blended["verdict"] = "估值分歧较大（区间参考）"
            blended["confidence"] = "低"
            vals = [v for v in method_values.values() if v is not None]
            blended["range_low"] = min(vals) if vals else None
            blended["range_high"] = max(vals) if vals else None
            blended["range_note"] = (
                f"方法间最高/最低估值相差 {weight_info['divergence']:.0%}，"
                "规则已按可靠性确定主方法并降权其余方法；建议以区间而非单点作为参考。"
            )
    elif not method_values:
        blended = {"ok": False, "error": "没有任何方法得出有效每股价值。",
                   "current_price": fin.price, "verdict": "无法判断"}

    # 有财务口径重大异常时保留分方法结果用于核查，不自动给综合单点价格。
    if ctx.get("data_review_required") and blended.get("ok"):
        blended["diagnostic_blended_per_share"] = blended.get("blended_per_share")
        blended["blended_per_share"] = None
        blended["blended_equity_value"] = None
        blended["upside"] = None
        blended["verdict"] = "历史财务存在重大跳变，基期/合并口径待核验"
        blended["confidence"] = "低"
        blended["status"] = "review_required"
    # 严重分歧时只能输出参考区间，不再输出加权计算的单点目标价。
    # 金融行业的 DDM/剩余收益与 PB/PE Comps 本来就是两套结构性不同的尺子，
    # 差异超过 100% 并不意味着模型失效；保留加权参考值并强制区间口径，
    # 而不是把 blended 清空、让 D 无法判断该不该用 DDM。
    if (blended.get("ok") and (weight_info.get("divergence") or 0) > 1.00
            and not (is_financial and method_results.get("ddm", {}).get("ok"))):
        blended["diagnostic_blended_per_share"] = blended.get("blended_per_share")
        blended["blended_per_share"] = None
        blended["blended_equity_value"] = None
        blended["upside"] = None
        blended["verdict"] = "方法差异超过100%，单点估值暂停，需人工复核"
        blended["confidence"] = "低"
        blended["status"] = "review_required"

    # 未获取到行情：不输出每股目标价，但保留股权价值供研究使用。
    # 这与 D 的工作流 7.3 / 12.1 一致：market_data.price=null → per_share=null。
    if not fin.price:
        warnings.append("未获取到实时行情，每股价值未计算。")
        if blended.get("ok"):
            if blended.get("blended_per_share") is not None:
                blended["diagnostic_blended_per_share"] = blended["blended_per_share"]
            blended["blended_per_share"] = None
            blended["upside"] = None
            blended["verdict"] = "未获取到实时行情，每股价值未计算"

    # ---------------------------------------------------------------- 敏感性 / 情景
    # 任何 DCF 路径都输出 WACC×g；分业务驱动模式下 growth_margin 不适用，
    # 三情景按分部预测行缩放收入/利润率后重算 FCFF，避免图表与分部预测脱节。
    sens = {}
    scen = {}
    if method_results.get("dcf", {}).get("ok"):
        base_wacc = method_results["dcf"]["wacc"]
        base_g = method_results["dcf"]["terminal_growth"]
        wg = sensitivity.wacc_g_matrix(fin, asm, inp.peers, base_wacc, base_g, market)
        sens = {
            "wacc_axis": wg["wacc_axis"],
            "growth_axis": wg["growth_axis"],
            "grid": wg["grid"],
            "wacc_g": wg,
            "growth_margin": None,
            "base_wacc": base_wacc,
            "base_growth": base_g,
            "unit": "元/股",
        }
        if operating_forecast is None:
            sens["growth_margin"] = sensitivity.growth_margin_matrix(
                fin, asm, inp.peers, base_wacc, base_g, market)
        else:
            sens["note"] = ("分业务驱动模式下，收入与利润率由分部预测固定；"
                            "growth_margin 二维敏感性不适用，仅输出 WACC×g。")
            warnings.append("分业务驱动模式：growth_margin 敏感性不适用，已输出 WACC×g 敏感性。")
        scen = sensitivity.scenarios(fin, asm, inp.peers, base_wacc, base_g, market)
        if not fin.price:
            sens["note"] = ((sens.get("note") + " ") if sens.get("note") else "") + \
                "未获取到实时行情，敏感性矩阵中的每股价值为 null。"
    elif operating_forecast is not None:
        warnings.append("DCF 未产出，分业务驱动情景与敏感性均未计算。")
    # ---------------------------------------------------------------- 交叉验证
    gates = rules.cross_validate(
        method_results.get("dcf") or {},
        method_results.get("comps") or {},
        method_results.get("sotp") or {},
        method_results.get("ddm") or {},
        fin, asm, weight_info.get("weights") or {},
    )
    if ctx.get("data_review_required"):
        gates.insert(0, {"code": "HISTORICAL_FINANCIAL_SCOPE_REVIEW", "severity": "block",
                          "message": "财务历史出现重大跳变，停止自动目标价；不得删除最新年份换旧基期。",
                          "affected_paths": ["valuation.blended", "valuation.history"]})
    if gate.get("support") == "unsupported":
        gates.insert(0, {
            "code": "INDUSTRY_UNSUPPORTED",
            "severity": "warn",
            "message": gate.get("reason"),
            "affected_paths": ["valuation.status", "valuation.industry_support"],
        })
    elif gate.get("standard_fcff_supported") is False:
        gates.insert(0, {
            "code": "STANDARD_FCFF_UNSUPPORTED",
            "severity": "warn",
            "message": gate.get("reason"),
            "affected_paths": ["valuation.dcf", "valuation.ddm", "valuation.comps"],
        })
    if driver_config is not None and (not operating_forecast or not operating_forecast.get("ok")):
        gates.append({"code":"OPERATING_FORECAST_BLOCKED","severity":"block",
                      "message":(operating_forecast or {}).get("error","分业务预测缺失"),
                      "affected_paths":["valuation.dcf"]})
    if ctx.get("peer_selection", {}).get("tier") in ("review_required", "user_failed", "none"):
        gates.append({
            "code": "PEER_SELECTION_REVIEW", "severity": "warn",
            "message": "缺少已核验的纯业务可比样本，Comps 停止计价，等待同业确认。",
            "affected_paths": ["valuation.comps"],
        })
    for w in warnings:
        if any(k in str(w) for k in ("估算", "近似", "兜底", "缺失")):
            gates.append({
                "code": "DATA_ESTIMATED",
                "severity": "info",
                "message": str(w),
                "affected_paths": ["valuation.assumptions"],
            })
            break

    # 情景单调性
    if scen.get("warnings"):
        warnings.extend(scen["warnings"])

    # 置信度：出现 warn/block 级门槛时下调，不让「高置信度」与风险提示自相矛盾
    if blended.get("ok"):
        levels = {"高": 3, "中": 2, "低": 1}
        current = levels.get(blended.get("confidence"), 2)
        if any(g.get("severity") == "block" for g in gates):
            current = min(current, 1)
        elif any(g.get("severity") == "warn" for g in gates):
            current = min(current, 2)
        blended["confidence"] = {v: k for k, v in levels.items()}[current]
        # 低置信度 + 大幅偏离时，给判断加限定，避免把高不确定性结论说成确定目标价
        if (blended["confidence"] == "低"
                and blended.get("upside") is not None
                and abs(blended["upside"]) > 0.50
                and "区间" not in str(blended.get("verdict"))):
            blended["verdict"] = f"{blended.get('verdict')}（高不确定性）"

    # ---------------------------------------------------------------- 状态
    # support 表示「本行业能不能给出可用的估值」；standard_fcff_supported
    # 只表示「标准 FCFF 是否适用」。银行/保险/证券前者为 limited、后者为 False，
    # 因此 DDM/剩余收益 + PB/PE Comps 有结果时应输出 partial，而不是 unsupported。
    ok_methods = [k for k, v in method_results.items() if v.get("ok")]
    has_price = bool(fin.price and fin.shares_outstanding)
    support = gate.get("support", "supported")
    standard_fcff = gate.get("standard_fcff_supported", support != "unsupported")
    # 行业结构性不支持：即使 Comps 能跑出诊断值，也不输出可用的单点目标价。
    if support == "unsupported":
        status = "unsupported"
    elif not ok_methods:
        status = "failed"
    elif not standard_fcff:
        status = "partial"
    elif (len(ok_methods) == 1 or not has_price
          or (blended.get("divergence") or 0) > 0.50):
        status = "partial"
    else:
        status = "ok"
    if blended.get("status") == "review_required":
        status = "partial"
    gate_reason = None
    if not standard_fcff:
        # D 的 C3 约定：primary_absolute 方法成功时写 ddm_used；
        # 只有 Comps 可用时写 comps_used；两者都不可用则只留前半段。
        if method_results.get("ddm", {}).get("ok"):
            gate_reason = "standard_fcff_unsupported; ddm_used"
        elif method_results.get("comps", {}).get("ok"):
            gate_reason = "standard_fcff_unsupported; comps_used"
        else:
            gate_reason = "standard_fcff_unsupported"
    if status == "partial" and support == "limited" and gate_reason is None:
        warnings.append("行业未识别，估值按通用口径，仅供参考。")
    if support == "unsupported" and blended.get("ok"):
        # 地产/REITs 等没有 NAV/FFO 口径时，Comps 只留作诊断，不给目标价。
        if blended.get("blended_per_share") is not None:
            blended["diagnostic_blended_per_share"] = blended["blended_per_share"]
        blended["blended_per_share"] = None
        blended["upside"] = None
        blended["verdict"] = "行业无可用估值方法，仅保留诊断数据"

    # ---------------------------------------------------------------- 输出
    peer_selection_out = dict(ctx.get("peer_selection") or {})
    if peer_selection_out.get("peers"):
        peer_selection_out["peers"] = [
            p.to_dict() if hasattr(p, "to_dict") else p for p in peer_selection_out["peers"]
        ]
    result = {
        "schema_version": "2.0",
        "status": status,
        "industry_support": support,
        "gate_reason": gate_reason,
        "industry_gate": gate,
        "company": company.to_dict(),
        "as_of": fin.years[-1] if fin.years else None,
        "currency": company.currency,
        "market_data": {
            "price": fin.price,
            "shares_outstanding": fin.shares_outstanding,
            "market_cap": fin.market_cap,
            "price_date": fin.price_date or company.price_date,
            "price_time": fin.price_time or company.price_time,
            "price_source": fin.price_source or company.price_source,
        },
        "method_selection": inp.method_selection,
        "history": _history_block(fin),
        "operating_forecast": operating_forecast or {"ok":False,"reason":"未启用分业务预测"},
        "historical_financials": fin.to_dict(),
        "financial_records": (payload.get("financials") if isinstance(payload, dict)
                              and isinstance(payload.get("financials"), dict)
                              and isinstance(payload.get("financials", {}).get("revenue"), dict) else {}),
        "method_plan": {
            "methods": methods,
            "reason": plan_reason,
            "status": run_status,
        },
        "assumptions": ledger,
        "reliabilities": reliabilities,
        "dcf": method_results.get("dcf") or {"ok": False, "error": "未运行"},
        # 兼容 D 的 from_c：C 原生字段名保留
        "relative": method_results.get("comps") or {"ok": False, "error": "未运行"},
        # 新字段名，便于前端直接读
        "comps": method_results.get("comps") or {"ok": False, "error": "未运行"},
        "sotp": method_results.get("sotp") or {"ok": False, "skipped": True, "reason": "未运行"},
        "ddm": method_results.get("ddm") or {"ok": False, "error": "未运行"},
        "blended": blended,
        "scenarios": scen,
        "sensitivity": sens,
        "peer_selection": peer_selection_out,
        "segment_meta": ctx.get("segment_meta") or {},
        "segment_source": ctx.get("segment_source") or "",
        "data_source": {
            "requested": ctx.get("data_source_requested") or "auto",
            "used": ctx.get("data_source_used") or "",
            "fallback": bool(ctx.get("source_fallback")),
        },
        "gates": gates,
        "warnings": list(dict.fromkeys([str(w) for w in warnings if w])),
        "sources": merge(sources),
        "disclaimer": DISCLAIMER,
    }

    # 兼容 canonical：扁平的市场/区间字段
    result["valuation_range"] = (result["comps"] or {}).get("valuation_range")
    result["presentation"] = {
        "narrative": narrative.build_narrative(result),
        "charts": narrative.build_charts(result),
    }

    # Excel：每次估值都同步生成，不返回静态/历史文件。
    # 优先 18 表 artifact_tool；该运行时不可用时回退 12 表兼容底稿。
    if export_excel:
        target = _abs_output_path(excel_path or _default_excel_path(company))
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = False
        if (operating_forecast and operating_forecast.get("ok")
                and operating_forecast.get("mode") == "three_statement"):
            try:
                from ..research import forecast_workbook
                forecast_workbook.render(result, target)
                result["excel_format"] = "three_statement_formula_5_sheets"
                rendered = True
            except Exception as exc:  # noqa: BLE001
                result.setdefault("warnings", []).append(
                    "三表公式底稿生成失败，改用标准估值底稿：" + type(exc).__name__)
        if not rendered:
            try:
                from ..export import institutional as excel_export
                excel_export.render(result, target)
                result["excel_format"] = "professional_18_sheets"
            except Exception as exc:  # noqa: BLE001
                from ..export import excel as fallback_export
                fallback_export.render(result, target)
                result["excel_format"] = "legacy_12_sheets"
                result.setdefault("warnings", []).append(
                    "专业 Excel 18 表生成器不可用，已使用 12 表兼容底稿：" + type(exc).__name__)
        result["excel_path"] = _as_return_path(target)
        result["excel_generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return result


def _default_excel_path(company) -> str:
    import os
    year = company.report_period[:4] if company.report_period else "latest"
    stem = f"{company.ticker or 'valuation'}_{year}_估值底稿.xlsx"
    out_dir = os.environ.get("FINSCOPE_OUTPUT_DIR", "valuation/output")
    return (Path(out_dir) / stem).as_posix()


def next_questions(payload: dict) -> dict:
    """给交互式对话框：当前缺什么、默认值是什么。"""
    inp, _ = adapters.normalize(payload)
    if not inp.financials.revenue and inp.company.ticker and inp.fetch_data:
        data = ak.fetch_company(inp.company.ticker, inp.company.market or "A")
        if data.get("ok"):
            inp.financials = adapters.financials_from_any(data["financials"])
            inp.company.name = inp.company.name or data.get("name") or inp.company.ticker
            inp.company.industry = inp.company.industry or data.get("industry") or ""
    gate = defaults.industry_gate(inp.company.industry, inp.company.business)
    return {
        "company": inp.company.to_dict(),
        "financials_available": bool(inp.financials.revenue),
        "industry_support": gate.get("support"),
        "industry_reason": gate.get("reason"),
        "questions": rules.next_questions(inp.financials, inp.company, gate),
        "defaults": {
            "method_selection": "auto",
            "forecast_years": 5,
            "terminal_growth": defaults.market_defaults(inp.company.market or "A")["default_terminal_growth"],
            "ebit_margin": None,
            "revenue_growth_y1": None,
            "wacc_mode": "capm",
            "multiples": "按行业与盈利特征自动选择",
            "peers": "仅核验业务匹配与倍数口径后计算；转型标的需审批",
        },
    }
