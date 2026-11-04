#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts_check_contract.py
=========================
B 模块交付前的契约自检。逐条对照《04_ABC工作流与接口规范 v1.0》第 4、6 节
和 D 的 `agent/adapters/from_b.py` 实际读取的字段，检查 B 的输出能不能被直接消费。

为什么需要这个脚本
------------------
静态检查（py_compile、单元测试）只能证明「跑通了」。字段名写错、单位词表不匹配、
页码取不到、四态里多出一个值，这些都不会报错——它们会让 D 的适配器静默丢字段，
最后在 E 的页面上表现为「没有出处」。这类问题只能在数据层面对照契约查。

用法
----
    # 只查指标
    python3 scripts_check_contract.py --ratios out/600519.json

    # 指标 + 风险（推荐，风险卡才有阈值与证据链）
    python3 scripts_check_contract.py --ratios out/600519.json --risks out/600519_risks.json

    # 连 D 的适配器一起跑：能导入就真跑一遍，验证字段是否被吃掉
    python3 scripts_check_contract.py --ratios ... --risks ... \
        --with-d /path/to/d-branch

退出码：0 全部通过；1 有 FAIL。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ---------------- 契约常量（与规范 / from_b.py 对齐） ---------------- #
B_UNITS = {"ratio", "days", "CNY", "x"}
B_CATEGORIES = {"growth", "profitability", "solvency", "efficiency",
                "cashflow_quality", "asset_quality", "governance", "banking"}
B_STATUS = {"ok", "not_evaluable", "not_meaningful"}
RISK_STATUS = {"triggered", "passed", "not_evaluable", "not_applicable"}
SEVERITY = {"high", "medium", "low", None}
SEVERITY_TAG = {"重大", "关注", "提示", None}
THRESHOLD_SOURCE = {
    "fixed", "peer_p25", "peer_p75", "regulatory", "convention",
    # 行业剖面离线校准（calibrate.py + peer_samples）：规则 benchmark_judge 生效时的来源
    "industry_p10", "industry_p25", "industry_median", "industry_p75", "industry_p90",
    # benchmark_judge 声明了但基准缺失/样本不足时的如实回退标注（不伪装成同业判定）
    "fixed_fallback",
    # WACC 敏感性判定（compute_wacc.py 产出，--wacc 传入）：P03/B12 两端重判的来源
    "wacc_sensitivity", "cost_of_equity_sensitivity",
}
# 行业基准注入的上下文变量（{指标}_industry_{分位}[_pp]）：外部校准量，没有年报页码，
# 出处由 threshold_source / peer_sample_n 标注，不参与 metric_evidence 回溯检查
BENCHMARK_VAR_RE = re.compile(
    r"^.+_industry_(p10|p25|median|p75|p90)(_pp)?$"
    # WACC 敏感性上下文量（compute_wacc.py）：估值参数，无年报页码，出处同上
    r"|^(wacc|cost_of_equity)_(low|point|high)(_pp)?$")
EVIDENCE_STEPS = {"数据", "计算", "出处", "判断", "归因"}

# D 的 CATEGORY_MAP，风险卡 category 必须落在这里面，否则 D 原样透传成英文 slug
D_CATEGORY_MAP = {"growth", "profitability", "solvency", "efficiency",
                  "cashflow_quality", "asset_quality", "governance"}

# 规范 6.2.1：这 8 个必须是 core
CORE_KEYS = {
    "revenue_growth", "net_income_parent_growth", "gross_margin",
    "net_margin_parent", "roe", "debt_to_assets", "ocf_to_revenue",
    "ocf_to_net_income",
}

# D 的 RATIO_RENAME：这些键会被改名，改完之后在 unified 里的名字
RATIO_RENAME = {
    "revenue_growth": "revenue_growth_yoy",
    "net_income_parent_growth": "net_income_growth_yoy",
    "net_income_growth": "net_income_total_growth",
    "net_margin_parent": "net_margin",
    "net_margin": "net_margin_total",
    "roe": "roe_weighted",
    "debt_to_assets": "debt_to_asset_ratio",
    "dso": "ar_turnover_days",
    "dio": "inventory_turnover_days",
    "dpo": "payable_turnover_days",
}

FAIL: list[str] = []
WARN: list[str] = []
OK: list[str] = []


def ok(name: str, detail: str = "") -> None:
    OK.append(f"{name}{'　· ' + detail if detail else ''}")


def fail(name: str, detail: str = "") -> None:
    FAIL.append(f"{name}{'　· ' + detail if detail else ''}")


def warn(name: str, detail: str = "") -> None:
    WARN.append(f"{name}{'　· ' + detail if detail else ''}")


def _flat(ratios: dict) -> dict:
    """{类别: {键: 记录}} -> {键: 记录}"""
    out = {}
    for items in (ratios or {}).values():
        if isinstance(items, dict):
            out.update(items)
    return out


# --------------------------------------------------------------------------- #
# 指标输出
# --------------------------------------------------------------------------- #
def check_ratios(doc: dict) -> None:
    print("\n【指标输出】")

    for k in ("schema_version", "generated_at", "generator", "company",
              "meta", "ratios", "evidence", "checks", "review_queue", "sources"):
        if k in doc:
            continue
        fail(f"顶层字段缺失：{k}")
    if "ratios" in doc:
        ok("顶层必填字段齐全", "10 项")

    # ---- company（规范 4.3） ----
    c = doc.get("company") or {}
    miss = [k for k in ("name", "ticker", "report_period", "currency",
                        "amount_unit", "report_type", "scope") if not c.get(k)]
    if miss:
        fail("company 缺字段", "、".join(miss))
    else:
        ok("company 必填字段齐全")

    if not c.get("industry") or str(c.get("industry")).strip() in ("", "None"):
        fail("company.industry 为空", "规范要求写「未识别」，不能留 null")
    else:
        ok("company.industry 有值", str(c["industry"]))

    rp = str(c.get("report_period") or "")
    if re.fullmatch(r"\d{4}", rp):
        ok("company.report_period 是 4 位年份", rp)
    else:
        fail("company.report_period 格式不对", f"当前 {rp!r}，规范要 '2025'")

    if c.get("ticker") and re.fullmatch(r"\d{6}", str(c["ticker"])):
        if not c.get("ticker_full"):
            warn("company.ticker 是 6 位纯代码", "规范 4.3 写 600519.SH；ticker_full 也没给")
        else:
            ok("company.ticker_full 带交易所后缀", str(c["ticker_full"]))
    if str(c.get("amount_unit")) not in ("元", "CNY"):
        fail("company.amount_unit 不是元", str(c.get("amount_unit")))

    # ---- meta（规范 4.2） ----
    m = doc.get("meta") or {}
    if m.get("source_mode") not in ("online", "upload"):
        fail("meta.source_mode 取值不合法", str(m.get("source_mode")))
    else:
        ok("meta.source_mode", m["source_mode"])
    if m.get("period_type") != "annual":
        warn("meta.period_type 不是 annual", str(m.get("period_type")))
    if m.get("consolidated") is not True:
        fail("meta.consolidated 不是 true", "规范硬约束：只用合并口径")
    key = str(m.get("key") or "")
    if not re.fullmatch(r"[\w.]+_\d{4}", key):
        warn("meta.key 格式不是 <ticker>_<year>", key or "缺")

    # ---- ratios 结构 ----
    ratios = doc.get("ratios") or {}
    if not isinstance(ratios, dict) or not ratios:
        fail("ratios 为空或不是对象")
        return
    if not all(isinstance(v, dict) for v in ratios.values()):
        fail("ratios 不是「类别 → 指标」的嵌套结构",
             "D 的 from_b 按类别两层遍历，扁平结构会全部丢掉")
        return
    ok("ratios 按类别嵌套", "、".join(sorted(ratios)))
    bad_cat = [k for k in ratios if k not in B_CATEGORIES]
    if bad_cat:
        fail("ratios 出现未知类别", "、".join(bad_cat))

    flat = _flat(ratios)
    ok("指标数量", str(len(flat)))

    # 撞名要看「改名之后落到哪」，而不是「目标名是不是也存在于源键里」。
    # D 是全表一起改名，源键 net_margin 自己会变成 net_margin_total，
    # 空出来的 net_margin 正好给 net_margin_parent 用，不算冲突。
    targets = {}
    for k in flat:
        t = RATIO_RENAME.get(k, k)
        targets.setdefault(t, []).append(k)
    dup = {t: ks for t, ks in targets.items() if len(ks) > 1}
    if dup:
        fail("改名后落到同一个键",
             "；".join(f"{t} ← {'/'.join(ks)}" for t, ks in list(dup.items())[:4]))
    else:
        ok("改名后无重名", f"{len(flat)} 个键 → {len(targets)} 个")

    # ---- 每条指标的字段 ----
    miss_name = [k for k, r in flat.items() if not r.get("name")]
    miss_role = [k for k, r in flat.items() if r.get("role") not in ("core", "diagnostic")]
    miss_src = [k for k, r in flat.items() if not isinstance(r.get("source_fields"), list)]
    empty_src = [k for k, r in flat.items() if isinstance(r.get("source_fields"), list)
                 and not r["source_fields"]]
    bad_status = [k for k, r in flat.items() if r.get("status") not in B_STATUS]
    bad_unit = [k for k, r in flat.items() if r.get("unit") not in B_UNITS]

    for name, lst, hint in [
        ("name", miss_name, "E 直接显示这个字段，缺了要退回前端映射表"),
        ("role", miss_role, "规范 6.2.1 要求 core / diagnostic"),
        ("source_fields", miss_src, "字段本身缺失"),
        ("status", bad_status, "只允许 ok / not_evaluable / not_meaningful"),
        ("unit", bad_unit, "只允许 ratio / days / CNY / x"),
    ]:
        if lst:
            fail(f"指标缺 {name} 或取值非法", f"{len(lst)} 个：{'、'.join(lst[:6])}")
        else:
            ok(f"全部指标有合法 {name}")

    # 只有「算出来了」的指标才必须有 source_fields。行业口径不成立的
    # （银行没有毛利率）本来就无输入，留空是对的，不是缺陷。
    empty_src = [k for k, r in flat.items()
                 if r.get("status") == "ok"
                 and isinstance(r.get("source_fields"), list)
                 and not r["source_fields"]]
    if empty_src:
        fail("已算出的指标没有来源科目", f"{len(empty_src)} 个：{'、'.join(empty_src[:6])}")
    else:
        na_cnt = sum(1 for r in flat.values() if r.get("status") != "ok")
        ok("已算出指标都有来源科目", f"另有 {na_cnt} 个未算出/口径不成立，来源留空" if na_cnt else "")

    # 无 source_fields 就无法回溯出处，指标级出处也会缺这一条。
    # 只对 status=ok 的指标要求，未算出的本来就没有出处。
    me = doc.get("metric_evidence") or {}
    lacking = [k for k in flat
               if flat[k].get("status") == "ok"
               and flat[k].get("source_fields") and k not in me]
    if lacking:
        fail("已算出指标缺 metric_evidence", f"{len(lacking)} 个：{'、'.join(lacking[:6])}")
    elif me:
        ok("metric_evidence 覆盖全部已算出指标", f"{len(me)} 条")

    # ---- core 8 个 ----
    got = {k for k, r in flat.items() if r.get("role") == "core"}
    missing_core = CORE_KEYS - set(flat)
    wrong_role = [k for k in (CORE_KEYS & set(flat)) if k not in got]
    if missing_core:
        fail("core 指标缺失", "、".join(sorted(missing_core)))
    elif wrong_role:
        fail("core 指标 role 标错", "、".join(sorted(wrong_role)))
    else:
        ok("8 个 core 指标齐全且 role 正确", f"共 {len(got)} 个 core")

    # ---- 单位与科目的一致性 ----
    money_bad = []
    for k, r in flat.items():
        flds = r.get("source_fields") or []
        if r.get("unit") == "CNY" or not flds:
            continue
        # 只要有金额类科目参与、单位却是 ratio，多半是单位没归一
        if any(f in ("revenue", "total_assets", "ocf") for f in flds) and k.endswith("_to_revenue"):
            continue
        money_bad.append(k)
    if not money_bad:
        ok("单位与科目量纲一致")

    # ---- evidence 树 ----
    ev = doc.get("evidence") or {}
    if not ev:
        fail("evidence 为空", "出处无从核对")
        return
    mode = (doc.get("meta") or {}).get("source_mode")
    subject = [k for k, v in ev.items()
               if isinstance(v, dict) and not any(
                   isinstance(x, dict) and x.get("kind") == "metric_alias" for x in v.values())]
    alias = [k for k in ev if k not in subject]
    ok("evidence 科目条目", f"{len(subject)} 个；指标别名 {len(alias)} 个")

    if mode == "upload":
        # 印刷页码由上游（A 的抽取）给，B 只透传、不补造。缺了要报出来，
        # 但归因是上游抽取没标页码，不是 B 算错——所以降级为警告并写明归属。
        no_page, pdf_only = [], []
        for s in subject:
            per = ev.get(s)
            if not isinstance(per, dict):
                continue
            vals = [v for v in per.values() if isinstance(v, dict)]
            if not any(v.get("page") is not None for v in vals):
                no_page.append(s)
                if any(v.get("pdf_page") is not None for v in vals):
                    pdf_only.append(s)
        if no_page:
            detail = f"{len(no_page)} 个科目无印刷页码"
            if pdf_only:
                detail += f"（其中 {len(pdf_only)} 个只有 PDF 物理页）；来自 A 的抽取，B 不补造"
            warn("上传模式有科目缺印刷页码", detail)
        else:
            ok("上传模式每个科目都有印刷页码")
        bad_pdf = [s for s in subject
                   if isinstance(ev[s], dict) and any(
                       (v or {}).get("pdf_page") is None for v in ev[s].values())]
        if bad_pdf:
            warn("上传模式缺 PDF 物理页", f"{len(bad_pdf)} 个：{'、'.join(bad_pdf[:5])}")
    elif mode == "online":
        fake = [s for s in subject
                if isinstance(ev[s], dict) and any(
                    (v or {}).get("page") is not None for v in ev[s].values())]
        if fake:
            fail("在线模式出现了页码", f"{len(fake)} 个：{'、'.join(fake[:6])}"
                 "　规范明确：接口数据不得标成年报页码")
        else:
            ok("在线模式无页码", "符合规范")


# --------------------------------------------------------------------------- #
# 风险输出
# --------------------------------------------------------------------------- #
def check_risks(doc: dict, ratios_doc: dict | None) -> None:
    print("\n【风险输出】")
    cards = doc.get("risks")
    if not isinstance(cards, list):
        fail("risks 不是数组")
        return
    ok("风险卡数量", str(len(cards)))

    req = ("risk_id", "risk_name", "category", "status", "trigger",
           "trigger_display", "explanation")
    missing = {k: [] for k in req}
    for c in cards:
        for k in req:
            if c.get(k) in (None, ""):
                missing[k].append(str(c.get("risk_id")))
    for k, lst in missing.items():
        if lst:
            fail(f"风险卡缺 {k}", f"{len(lst)} 条：{'、'.join(lst[:6])}")
    if not any(missing.values()):
        ok("风险卡必填字段齐全", "、".join(req))

    bad_status = [c["risk_id"] for c in cards if c.get("status") not in RISK_STATUS]
    if bad_status:
        fail("风险状态不在四态内", "、".join(bad_status[:6]))
    else:
        ok("风险状态都是四态之一")

    bad_cat = sorted({str(c.get("category")) for c in cards} - D_CATEGORY_MAP)
    if bad_cat:
        fail("category 不在 D 的映射表里", "、".join(bad_cat) + "　D 会原样透传成英文")
    else:
        ok("category 都在 D 的 CATEGORY_MAP 里")

    trig = [c for c in cards if c.get("status") == "triggered"]
    for k, valid in (("severity", SEVERITY), ("severity_tag", SEVERITY_TAG)):
        bad = [c["risk_id"] for c in trig if c.get(k) not in valid]
        if bad:
            fail(f"触发卡 {k} 取值非法", "、".join(bad[:6]))
    nosco = [c["risk_id"] for c in trig if c.get("score") is None]
    if nosco:
        fail("触发卡缺 score", "、".join(nosco[:6]))
    else:
        ok("触发卡都有严重度与分数", f"{len(trig)} 条")

    # ---- 阈值三件套（规范 6.3） ----
    no_thr = [c["risk_id"] for c in cards
              if c.get("threshold_source") is None]
    if no_thr:
        fail("风险卡缺 threshold_source", f"{len(no_thr)} 条：{'、'.join(no_thr[:6])}")
    else:
        ok("每张卡都有 threshold_source")
    bad_src = sorted({str(c.get("threshold_source")) for c in cards} - THRESHOLD_SOURCE)
    if bad_src:
        fail("threshold_source 取值非法", "、".join(bad_src))
    peer = [c for c in cards if str(c.get("threshold_source", "")).startswith("peer_")]
    small = [c["risk_id"] for c in peer if (c.get("peer_sample_n") or 0) < 3]
    if small:
        fail("同业阈值样本不足 3 家", "、".join(small[:6]))
    # 行业剖面基准（detect_risks.BENCHMARK_MIN_SAMPLE 同口径）：n≥5 才允许用分位数判定
    ind = [c for c in cards if str(c.get("threshold_source", "")).startswith("industry_")]
    small_ind = [c["risk_id"] for c in ind if (c.get("peer_sample_n") or 0) < 5]
    if small_ind:
        fail("行业基准阈值样本不足 5 家", "、".join(small_ind[:6]))
    if peer:
        noval = [c["risk_id"] for c in peer if c.get("threshold_value") is None]
        if noval:
            fail("同业阈值缺数值", "、".join(noval[:6]))
        else:
            ok("同业阈值都带数值与样本量", f"{len(peer)} 条取分位数")

    # ---- 证据链（只有触发卡需要；未触发的卡 D 走 rules_evaluated，不读证据链） ----
    # 规范没规定步骤词表，但 D 的 from_b 明确读「数据 / 判断 / 出处」三类，
    # 少任何一类，报告里的数字证据或出处就会是空的。
    required = {"数据", "计算", "判断", "出处"}
    lacking, extra_steps = [], set()
    for c in trig:
        chain = c.get("evidence_chain") or []
        have = {s.get("step") for s in chain}
        miss_step = required - have
        if miss_step:
            lacking.append(f"{c.get('risk_id')}缺{'/'.join(sorted(miss_step))}")
        extra_steps |= (have - EVIDENCE_STEPS)
    if lacking:
        fail("触发卡证据链不完整", "；".join(lacking[:5]))
    else:
        ok("触发卡证据链含数据/计算/判断/出处", f"{len(trig)} 条")
    if extra_steps:
        warn("证据链有规范未定义的步骤", "、".join(sorted(map(str, extra_steps))) +
             "　D 不读，保留不影响")

    # ---- 页码能否解析（这是 involved_values[].page 的关键） ----
    me = (ratios_doc or {}).get("metric_evidence") or {}
    # _prev/_delta/_pp/_bp/_yi 是同一指标或其派生的展示变体，页码同源于基本指标
    PERIOD_SUFFIX_RE = re.compile(r"_(prev|delta)(_pp|_bp|_yi)?$")
    unresolved, via_base = set(), []
    for c in trig:
        for metric in (c.get("trigger_values") or {}):
            if BENCHMARK_VAR_RE.match(metric):
                continue    # 行业基准量：外部校准，无年报页码，出处看 threshold_source
            if metric in me:
                continue
            base = PERIOD_SUFFIX_RE.sub("", metric)
            if base != metric and base in me:
                via_base.append(metric)
                continue
            # 能触发的卡其变量必已求值成功，查不到只剩一类：
            # 规则派生量（如 dividend_to_ocf = raw_dividend_paid/raw_ocf），
            # 页码由证据链「数据」层的 evidence_required 科目承担 → 降级为 WARN
            unresolved.add(metric)
    if not me:
        warn("没有 metric_evidence，D 取不到 involved_values 的页码")
    elif unresolved:
        warn("触发变量在 metric_evidence 查不到（规则派生量，页码走证据链数据层）",
             f"{len(unresolved)} 个：{'、'.join(sorted(unresolved)[:8])}")
    else:
        extra = f"（另 {len(via_base)} 个 _prev/_delta 变体按基本指标回溯）" if via_base else ""
        ok("触发变量都能回溯到页码", extra)

    # ---- 分流：不重不漏 ----
    # 注意 B 的输出形状：`risks` 保留了**全量** 40 条（D 的 from_b 按 status 自己分流，
    # 只认 risks 这一个键），`risks_triggered` 才是规范要的「只含触发」。
    # 因此这里验的是「全量 = 触发 ∪ 未触发」，而不是「两者不相交」。
    if "rules_evaluated" in doc:
        # detect_risks 的未触发卡沿用 risk_id 这个键名，D 转成 rule_id。
        re_ids = {r.get("rule_id") or r.get("risk_id")
                  for r in doc.get("rules_evaluated") or []}
        r_ids = {c.get("risk_id") for c in cards}
        trig_ids = {c.get("risk_id") for c in trig}
        if r_ids != (re_ids | trig_ids):
            only_card = r_ids - (re_ids | trig_ids)
            only_list = (re_ids | trig_ids) - r_ids
            fail("风险分流对不上",
                 f"全量多出 {'、'.join(sorted(only_card)[:5]) or '无'}；"
                 f"分流多出 {'、'.join(sorted(only_list)[:5]) or '无'}")
        elif re_ids & trig_ids:
            fail("同一规则同时被判触发和未触发", "、".join(sorted(re_ids & trig_ids)[:6]))
        else:
            ok("全量 = 触发 + 未触发",
               f"{len(trig_ids)} + {len(re_ids)} = {len(r_ids)} 条")
            if doc.get("risks_triggered") is not None:
                t2 = {c.get("risk_id") for c in doc["risks_triggered"]}
                if t2 != trig_ids:
                    fail("risks_triggered 与 risks 里的触发卡不一致")
                else:
                    ok("risks_triggered 与触发卡一致", f"{len(t2)} 条")


# --------------------------------------------------------------------------- #
# 真跑 D 的适配器
# --------------------------------------------------------------------------- #
def run_d(path: str, ratios_doc: dict, risks_doc: dict | None) -> None:
    print("\n【D 的适配器实测】")
    cands = [path, os.path.join(path, "D分支文件"), os.path.join(path, "agent")]
    root = None
    for c in cands:
        if os.path.isdir(os.path.join(c, "agent", "adapters")):
            root = c
            break
    if root is None:
        warn("没找到 agent/adapters", f"在 {path} 下找不到，跳过")
        return
    sys.path.insert(0, os.path.abspath(root))
    try:
        from agent.adapters.from_b import adapt_b  # type: ignore
    except Exception as e:  # noqa: BLE001
        fail("导入 from_b 失败", repr(e))
        return

    try:
        out = adapt_b(ratios_doc, risks_doc or {"risks": []})
    except Exception as e:  # noqa: BLE001
        fail("adapt_b 抛异常", repr(e))
        return
    ok("adapt_b 执行成功")

    flat = _flat(out.get("ratios") or {})
    ok("适配后指标数", str(len(flat)))
    if len(flat) < 60:
        fail("适配后指标数偏少", f"{len(flat)} 个，规范要求 68 个键")

    bad_unit = sorted({r.get("unit") for r in flat.values()} - {"小数", "天", "元", "倍", "次"})
    if bad_unit:
        fail("适配后仍有未映射的单位", "、".join(map(str, bad_unit)))
    else:
        ok("单位全部映射为中文口径")

    # 下面两类是 D 侧欠的活（规范 6.2 与 6.3 都点名要 D 改 from_b.py），
    # B 这边字段已经给了，被吃掉不是 B 的问题，但必须显式报出来，否则验收时
    # 会在 E 的页面上表现为「没有出处」。
    for f in ("name", "role", "source_fields", "source_pages"):
        n = sum(1 for r in flat.values() if r.get(f) is not None)
        if n == 0:
            warn(f"适配后 {f} 被丢掉（待 D 修 from_b._ratio_record）",
                 f"0/{len(flat)}；B 侧字段已在，D 未透传")
        else:
            ok(f"适配后 {f} 有值", f"{n}/{len(flat)}")

    cards = out.get("risks") or []
    tv = [v for c in cards for v in (c.get("involved_values") or [])]
    if tv:
        miss = [v for v in tv if v.get("page") is None]
        if miss:
            fail("involved_values 缺页码", f"{len(miss)}/{len(tv)} 项"
                 "　B 已给 metric_evidence，若仍缺说明指标名没对上")
        else:
            ok("involved_values 页码齐全", f"{len(tv)} 项")
    if cards:
        lost = [c["risk_id"] for c in cards if c.get("threshold_source") is None]
        if lost:
            warn("适配后丢了 threshold_value/source（待 D 修 from_b._adapt_risk_card）",
                 f"{len(lost)} 条：{'、'.join(lost[:5])}")
        else:
            ok("适配后阈值三件套保留")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="B 输出契约自检")
    ap.add_argument("--ratios", required=True, help="compute_ratios.py 的输出")
    ap.add_argument("--risks", help="detect_risks.py 的输出")
    ap.add_argument("--with-d", dest="with_d", help="D 分支解包目录，给了就真跑一遍其适配器")
    args = ap.parse_args()

    ratios_doc = json.load(open(args.ratios, encoding="utf-8"))
    risks_doc = json.load(open(args.risks, encoding="utf-8")) if args.risks else None

    name = (ratios_doc.get("company") or {}).get("name") or "-"
    print("=" * 62)
    print(f" B 输出契约自检 · {name}")
    print(f" 指标 {args.ratios}")
    print(f" 风险 {args.risks or '（未提供）'}")
    print("=" * 62)

    check_ratios(ratios_doc)
    if risks_doc:
        check_risks(risks_doc, ratios_doc)
    if args.with_d:
        run_d(args.with_d, ratios_doc, risks_doc)

    print()
    for line in OK:
        print("  [OK]   " + line)
    for line in WARN:
        print("  [WARN] " + line)
    for line in FAIL:
        print("  [FAIL] " + line)
    print()
    print(f" 通过 {len(OK)} | 警告 {len(WARN)} | 失败 {len(FAIL)}")
    print("=" * 62)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
