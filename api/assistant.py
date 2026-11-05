"""AI 研究助手：把用户问题接到后端规则/估值结果。

两种模式：
  1. 规则助手（默认）：解析问题中的 WACC/增速/利润率/同业/解释分歧等意图，
     直接调用估值引擎重算，再用结构化结果回答。不依赖外部模型。
  2. LLM 模式（可选）：设置 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL，
     走 OpenAI 兼容的 /chat/completions 接口。ChatGPT Plus 订阅本身不提供 API，
     需要 API Key 或本地桥接服务。

所有数字都来自后端结果，不让模型自由编造。
"""
from __future__ import annotations

import json
import os
import re

import requests


def llm_config() -> dict:
    """OpenAI 先于可选 DeepSeek；密钥只在服务端配置，不返回给页面。"""
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ASSISTANT_API_KEY")
    if key:
        base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("ASSISTANT_BASE_URL") or "https://api.openai.com/v1"
        return {
            "connected": True,
            "provider": "OpenAI-compatible",
            "base_url": base.rstrip("/"),
            "model": os.environ.get("OPENAI_MODEL") or os.environ.get("ASSISTANT_MODEL") or "gpt-4o-mini",
            "note": "使用服务端 OpenAI API；与 ChatGPT Plus 网页订阅权限和计费分开。",
        }
    if os.environ.get("DEEPSEEK_API_KEY"):
        return {
            "connected": True,
            "provider": "DeepSeek",
            "base_url": (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/"),
            "model": os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat",
            "note": "已配置 DeepSeek；规则与估值结果作为回答上下文。",
        }
    return {"connected": False, "provider": "规则助手", "base_url": "", "model": "rules",
            "note": "当前为本地规则助手；设置服务端 OPENAI_API_KEY 后启用 OpenAI 模型。"}


def _chat(messages: list[dict], max_tokens: int = 1200) -> str | None:
    cfg = llm_config()
    if not cfg.get("connected"):
        return None
    if cfg.get("provider") == "DeepSeek":
        key = os.environ.get("DEEPSEEK_API_KEY")
    else:
        key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ASSISTANT_API_KEY")
    try:
        r = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": cfg["model"], "messages": messages,
                  "temperature": 0.3, "max_tokens": max_tokens},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return None


def extract_intent(message: str) -> dict:
    """Conservative, explicit-only valuation edits.

    A question about a hypothetical change must never silently mutate the
    persisted session. In a "from 8% to 7.5%" instruction, use the target
    (7.5%), never the historical value (8%).
    """
    text = (message or "").strip()
    intent = {"action": "answer", "changes": {}, "peers": None}
    if not text:
        return intent

    # Explanatory and hypothetical queries are read-only, even if they quote
    # a proposed adjustment in their wording.
    read_only = bool(re.match(
        r"^(?:请|帮我|麻烦|能否|可以)?(?:解释|分析|为什么|为何|如果|假设|假如|假定|若|当|比较|说明|请问|我想问|我想知道|想知道)",
        text, re.I,
    ))

    peer_change = re.search(
        r"(?:重选|重新选择|重新选|替换|换一批|更换).{0,12}(?:可比公司|可比|同业)|"
        r"(?:可比公司|同业).{0,10}(?:换一批|重选|重新选择|更换)", text,
    )
    if peer_change and not read_only:
        intent["action"] = "reselect_peers"
        codes = re.findall(r"(?<!\d)\d{6}(?!\d)", text)
        if codes:
            intent["peers"] = list(dict.fromkeys(codes))

    if not read_only:
        # Only accept an explicit assignment / target instruction. Relative
        # changes such as "降低0.5个百分点" need a separate delta calculator.
        patterns = [
            ("wacc", r"WACC|折现率|资本成本"),
            ("growth", r"收入增速|营收增速|收入增长率|营收增长率"),
            ("margin", r"EBIT\s*利润率|营业利润率|利润率|EBIT\s*margin"),
            ("g", r"永续增长率|永续增长|长期增长率|terminal\s*g"),
        ]
        combined = re.compile("|".join(f"(?P<{k}>{pt})" for k, pt in patterns), re.I)
        matches = list(combined.finditer(text))
        target = re.compile(
            r"(?:[=＝:：]|(?:调(?:整|高|低)?|上调|下调|提高|降低|改(?:为|成|到)?|"
            r"设(?:置|定)?|变)(?:为|到|至|成)?|(?:到|至|为))\s*"
            r"(\d+(?:\.\d+)?)\s*%", re.I,
        )
        for i, m in enumerate(matches):
            key = m.lastgroup
            segment = text[m.end():matches[i+1].start() if i + 1 < len(matches) else len(text)]
            values = target.findall(segment)
            if not values:
                continue
            num = float(values[-1])
            if not (0.0 <= num <= 100.0):
                continue
            value = num / 100.0
            if key == "wacc":
                intent["changes"].update({"wacc_mode": "manual", "wacc_override": value})
            elif key == "growth":
                intent["changes"]["revenue_growth_y1"] = value
            elif key == "margin":
                intent["changes"]["ebit_margin"] = value
            elif key == "g":
                intent["changes"]["terminal_growth"] = value

    if intent["changes"] and intent["action"] == "answer":
        intent["action"] = "update_assumptions"
    elif intent["action"] == "answer" and re.search(r"(解释|为什么|为何|分歧|差异|原因|怎么理解|会怎样|影响)", text):
        intent["action"] = "explain"
    return intent


def _fmt(v, digits=2):
    return "—" if v is None else f"{v:,.{digits}f}"


def _pct(v, digits=1):
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def _yi(v, digits=1):
    return "—" if v is None else f"{v / 1e8:,.{digits}f}"


def compact_result(result: dict) -> str:
    """给 LLM 的结构化摘要；只放结果，不让模型自行取数。"""
    c = result.get("company") or {}
    d = result.get("dcf") or {}
    cp = result.get("comps") or {}
    s = result.get("sotp") or {}
    dd = result.get("ddm") or {}
    b = result.get("blended") or {}
    m = result.get("market_data") or {}
    lines = [
        f"公司：{c.get('name')}（{c.get('ticker')}），行业：{c.get('industry')}，行业支持：{result.get('industry_support')}",
        f"现价：{_fmt(b.get('current_price') or m.get('price'))} 元；融合每股：{_fmt(b.get('blended_per_share'))}；判断：{b.get('verdict')}；置信度：{b.get('confidence')}",
        f"方法权重：{json.dumps(b.get('weights') or {}, ensure_ascii=False)}；主方法：{b.get('primary')}",
        f"DCF：ok={d.get('ok')}，每股={_fmt(d.get('per_share'))}，WACC={_pct(d.get('wacc'),2)}，CAPM={_pct(d.get('wacc_capm'),2)}，隐含={_pct(d.get('implied_wacc'),2)}，g={_pct(d.get('terminal_growth'))}，终值占比={_pct(d.get('tv_ratio'))}",
        f"Comps：ok={cp.get('ok')}，每股={_fmt(cp.get('implied_per_share'))}，同业数={cp.get('peer_count')}，判断={cp.get('judgment')}",
        f"SOTP：ok={s.get('ok')}，每股={_fmt(s.get('per_share'))}，分部数={s.get('segment_count')}",
        f"DDM：ok={dd.get('ok')}，每股={_fmt(dd.get('per_share'))}，Ke={_pct(dd.get('cost_of_equity'),2)}",
        f"Warnings：{'; '.join([str(x)[:120] for x in (result.get('warnings') or [])[:6]])}",
    ]
    return "\n".join(lines)


def answer_with_rules(result: dict, message: str, intent: dict,
                      previous: dict | None = None) -> str:
    b = result.get("blended") or {}
    d = result.get("dcf") or {}
    cp = result.get("comps") or {}
    s = result.get("sotp") or {}
    dd = result.get("ddm") or {}
    m = result.get("market_data") or {}
    name = (result.get("company") or {}).get("name") or "标的"
    action = intent.get("action")

    if action == "reselect_peers":
        peers = (cp.get("peer_companies") or [])[:8]
        items = []
        for p in peers:
            comp = p.get("comparability") or {}
            items.append(f"{p.get('name')}（{p.get('ticker')}，可比性 {comp.get('score','—')} 分/{comp.get('level','—')}）：{p.get('selection_reason') or '—'}")
        return (
            f"已按当前数据重新选择可比公司。核心观点：Comps 的可比性取决于行业、规模、增速与利润率是否接近，而不是简单凑够 5 家。\n\n"
            f"本次样本（{cp.get('peer_count',0)} 家）：\n- " + "\n- ".join(items) +
            f"\n\n可比性判断：{cp.get('comparability_note') or ''}\n"
            f"对结论的影响：Comps 隐含每股 {_fmt(cp.get('implied_per_share'))} 元，"
            f"相对现价 {_fmt(b.get('current_price') or m.get('price'))} 元的空间为 {_pct(b.get('upside'))}。"
        )

    if action == "explain":
        vals = []
        for key, label, v in (("dcf", "DCF", d.get("per_share")),
                              ("comps", "Comps", cp.get("implied_per_share")),
                              ("sotp", "SOTP", s.get("per_share")),
                              ("ddm", "DDM", dd.get("per_share"))):
            if v is not None:
                vals.append((key, label, v))
        gap = (max(v for _, _, v in vals) / min(v for _, _, v in vals) - 1) if len(vals) >= 2 else None
        parts = [
            f"核心观点：{name} 的方法间分歧"
            + (f"为 {gap:.0%}" if gap is not None else "暂无法计算")
            + "，应先定位假设差异，而不是把几个数机械平均。",
            f"数据：DCF {_fmt(d.get('per_share'))} 元、Comps {_fmt(cp.get('implied_per_share'))} 元、"
            f"SOTP {_fmt(s.get('per_share'))} 元、DDM {_fmt(dd.get('per_share'))} 元；"
            f"现价 {_fmt(b.get('current_price') or m.get('price'))} 元。",
        ]
        if d.get("ok"):
            parts.append(
                f"因果分析：DCF 的折现率用 {_pct(d.get('wacc'),2)}（CAPM {_pct(d.get('wacc_capm'),2)}，"
                f"市场隐含 {_pct(d.get('implied_wacc'),2)}），永续 g {_pct(d.get('terminal_growth'))}，"
                f"终值占企业价值 {_pct(d.get('tv_ratio'))}。若 WACC 偏低或 g 偏高，DCF 会被系统性放大；"
                f"反之则偏低。"
            )
        if cp.get("ok"):
            parts.append(
                f"Comps 的同业中位倍数来自 {cp.get('peer_count',0)} 家样本，"
                f"目标与同业的差异已做调整；{cp.get('judgment') or ''}。"
            )
        if result.get("warnings"):
            parts.append("需要核验：" + "；".join(str(w)[:140] for w in result["warnings"][:3]))
        return "\n\n".join(parts)

    # 一般回答：结论 + 方法 + 关键假设 + 风险
    parts = [
        f"核心观点：{name} 的融合每股价值约 {_fmt(b.get('blended_per_share'))} 元，"
        f"现价 {_fmt(b.get('current_price') or m.get('price'))} 元，"
        f"判断为「{b.get('verdict')}」，置信度 {b.get('confidence')}。",
        f"依据：方法权重 {json.dumps(b.get('weights') or {}, ensure_ascii=False)}，"
        f"主方法 {b.get('primary')}；DCF {_fmt(d.get('per_share'))} 元、"
        f"Comps {_fmt(cp.get('implied_per_share'))} 元、SOTP {_fmt(s.get('per_share'))} 元、"
        f"DDM {_fmt(dd.get('per_share'))} 元。",
    ]
    if previous:
        old = previous.get("blended") or {}
        parts.append(
            f"变化：融合每股从 {_fmt(old.get('blended_per_share'))} 变为 "
            f"{_fmt(b.get('blended_per_share'))}，判断从「{old.get('verdict')}」变为「{b.get('verdict')}」。"
        )
    if result.get("warnings"):
        parts.append("待核验：" + "；".join(str(w)[:150] for w in result["warnings"][:3]))
    return "\n\n".join(parts)


def answer_with_llm(result: dict, message: str, history: list[dict] | None = None) -> str | None:
    cfg = llm_config()
    if not cfg["connected"]:
        return None
    system = (
        "你是 FinScope 的估值研究助手。只根据下面给出的结构化估值结果回答问题，"
        "不得编造数字。回答用中文，按「核心观点 → 数据依据 → 因果分析 → 风险/待核验」组织，"
        "至少两段；涉及方法分歧时先解释假设差异，不要机械平均。\n\n"
        + compact_result(result)
    )
    messages = [{"role": "system", "content": system}]
    for m in (history or [])[-8:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])})
    messages.append({"role": "user", "content": message})
    return _chat(messages)


def answer_search_llm(result: dict, query: str, search_results: list[dict],
                      history: list[dict] | None = None) -> str | None:
    """把「估值结果 + 联网检索片段」交给 DeepSeek/OpenAI，返回研究回答。"""
    cfg = llm_config()
    if not cfg["connected"]:
        return None
    snippets = []
    for i, r in enumerate((search_results or [])[:6], start=1):
        snippets.append(
            f"[{i}] {r.get('title','')}\nURL: {r.get('url','')}\n摘要: {r.get('snippet','')[:500]}"
        )
    system = (
        "你是 FinScope 的估值研究员。你必须优先使用给定的估值结果中的数字；"
        "联网检索只用于补充公告、行业、可比公司等背景，不得用搜索摘要里的数字替换估值结果。"
        "回答用中文，按「核心观点 → 数据依据 → 因果分析 → 对估值的影响 → 来源」组织，"
        "至少两段；引用检索内容时标注 [编号]。不要编造 URL。\n\n"
        "【当前估值结果】\n" + compact_result(result) +
        "\n\n【联网检索片段】\n" + ("\n\n".join(snippets) if snippets else "（本次未取得检索结果）")
    )
    messages = [{"role": "system", "content": system}]
    for m in (history or [])[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])})
    messages.append({"role": "user", "content": query})
    return _chat(messages, max_tokens=1600)
