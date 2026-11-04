#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compute_wacc.py —— 每家公司现场计算 WACC 敏感性区间（工作台入口：--code 或 --name）。

与静态阈值表的本质区别
-----------------------
WACC 是公司专属参数，不允许手填单点数假装精确。本脚本对任意一家输入的
公司（代码或名称）现场计算：

    Rf   中债 10 年期国债收益率（共享配置 wacc_inputs.json，同批交付同一根）
    β    该公司周收益率对沪深 300 的回归（156 周），区间 = β ± 2×标准误
    MRP  惯例区间 6%–7%（无官方数，用区间进敏感性而不是拍单点）
    Re   rf + β×MRP（CAPM）
    Rd   公司自算：利息费用 / 平均有息负债（--ratios 提供）；缺则用
         中债商业银行 AAA 债收益率兜底并注明"市场口径"
    t    公司有效税率（--ratios）；缺则法定 25%
    E    东财行情总市值（f116）
    D    报表有息负债（账面值近似市值）

    WACC_low  = Re(rf, β-2σ, MRP 6%) × E/V + Rd×(1-t) × D/V
    WACC_high = Re(rf, β+2σ, MRP 7%) × E/V + Rd×(1-t) × D/V

输出 low/point/high 三档 + components 逐项出处。银行公司跳过经典 WACC
（存款是经营材料不是融资），只产出股权成本 Ke，供 B12 的 RAROC 口径使用。

用法
----
    python3 compute_wacc.py --code 600519                    # 上市公司全流程（联网）
    python3 compute_wacc.py --name 贵州茅台                  # 名称自动解析代码
    python3 compute_wacc.py --code 600519 --ratios r.json    # 债务成本/税率用公司报表数
    python3 compute_wacc.py --ratios demo.json --beta 1.0 --no-net   # 合成数据/离线

缺什么如实战什么：β 回归不可得且没给 --beta 时**拒绝产出**（exit 2），
绝不静默填数——这是 compute_ratios「不猜数」原则在估值参数上的延续。
"""

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS_PATH = os.path.normpath(os.path.join(HERE, "..", "data", "wacc_inputs.json"))
sys.path.insert(0, HERE)

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def _get(url, params, timeout=25):
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + q, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _bank_list():
    """复用 fetch_bank_samples 的 20 家上市银行名单（同业 β 中位数用）。"""
    from fetch_bank_samples import BANKS
    return BANKS


# ---------------------------------------------------------------- 名称/代码解析

def resolve_name(name: str):
    """东财搜索建议接口：公司名 → (code, secid, 全名)。"""
    d = _get("https://searchapi.eastmoney.com/api/suggest/get", {
        "input": name, "type": "14", "count": "5",
        "token": "D43B7950AB2E9D6994E9AFB12C6E2D6F"})
    rows = (d.get("QuotationCodeTable") or {}).get("Data") or []
    for s in rows:
        # 只要沪深 A 股（MktNum 1=沪 0=深），过滤债券/基金/港美股同名
        if s.get("MktNum") in ("0", "1") and len(s.get("Code") or "") == 6:
            return s["Code"], s["QuoteID"], s.get("Name")
    return None, None, None


def secid_from_code(code: str) -> str:
    return ("1." if code.startswith(("6", "9")) else "0.") + code


# ---------------------------------------------------------------- 行情

def get_market_cap(secid: str):
    """总市值（元）。接口不可得返回 None。"""
    try:
        d = _get("https://push2.eastmoney.com/api/qt/stock/get",
                 {"secid": secid, "invt": "2", "fltt": "2", "fields": "f57,f58,f116"})
        data = d.get("data") or {}
        v = data.get("f116")
        return float(v) if isinstance(v, (int, float)) else None, data.get("f58")
    except Exception:
        return None, None


def weekly_closes(secid: str, weeks: int):
    """周收盘 [(date, close)]，klt=102 周线，fqt=1 前复权。"""
    d = _get("https://push2his.eastmoney.com/api/qt/stock/kline/get",
             {"secid": secid, "klt": "102", "fqt": "1", "lmt": str(weeks),
              "end": "20500101", "fields1": "f1,f2,f3", "fields2": "f51,f53"})
    out = []
    for line in ((d.get("data") or {}).get("klines") or []):
        date, close = line.split(",")[0], float(line.split(",")[1])
        out.append((date, close))
    return out


def beta_regression(stock_closes, index_closes, idx_name):
    """按日期对齐后对周收益率做 OLS：β、斜率标准误、样本周数。

    β 区间取 ±2×标准误（约 95% 置信），是统计可辩护的敏感性撑开方式，
    与 MRP 惯例区间叠加成股权成本上下界。
    """
    idx = dict(index_closes)
    pairs = []          # (r_stock, r_index) 按周对齐
    prev_s = prev_i = None
    for date, cs in stock_closes:
        ci = idx.get(date)
        if ci is None:
            continue
        if prev_s is not None and prev_s > 0 and prev_i and prev_i > 0:
            pairs.append((cs / prev_s - 1.0, ci / prev_i - 1.0))
        prev_s, prev_i = cs, ci
    n = len(pairs)
    if n < 40:
        return None
    mx = sum(r for _, r in pairs) / n
    my = sum(r for r, _ in pairs) / n
    sxx = sum((r - mx) ** 2 for _, r in pairs)
    sxy = sum((r - mx) * (y - my) for r, y in pairs)
    if sxx <= 0:
        return None
    beta = sxy / sxx
    sse = sum((y - my - beta * (r - mx)) ** 2 for r, y in pairs)
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 else None
    r2 = (sxy ** 2) / (sxx * sum((y - my) ** 2 for _, y in pairs)) if n > 2 else None
    return {"value": beta, "std_error": se, "n_weeks": n,
            "r_squared": r2, "index": idx_name}


def sector_beta_median(own_code, idx_cfg):
    """同业 β 中位数：上市银行逐家对指数回归，只取 R² 达标者，取中位数。

    出处与自家回归同等可核对（每家的 β/R²/周数都来自公开行情），且与项目
    「同业池校准」的哲学一致——本公司回归无解释力时，用行业实测水平代替。
    """
    index = weekly_closes(idx_cfg["secid"], idx_cfg["weeks"])
    r2_min = idx_cfg.get("r2_min", 0.05)
    vals, peer_total = [], 0
    for code, _name in _bank_list():
        peer_total += 1
        if code == own_code:
            continue
        try:
            b = beta_regression(weekly_closes(secid_from_code(code), idx_cfg["weeks"]),
                                index, idx_cfg["name"])
        except Exception:
            continue
        if b and (b.get("r_squared") or 0) >= r2_min:
            vals.append(b["value"])
    if len(vals) < 5:
        return None
    vals.sort()
    m = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals)//2 - 1] + vals[len(vals)//2]) / 2
    return {"value": m, "std_error": None, "n_weeks": len(vals), "r_squared": None,
            "index": idx_cfg["name"], "peer_total": peer_total, "_own_r2": None}


# ---------------------------------------------------------------- 公司报表数

def _ratio_entry(diag, key):
    r = (diag or {}).get("ratios") or {}
    for items in r.values():
        if key in items:
            return items[key]
    return None


def _derived(diag, key, period):
    d = (diag or {}).get("derived") or {}
    return ((d.get(period) or {}).get(key)) if period else None


def company_inputs_from_ratios(diag):
    """从 ratios 文档取：有效税率、利息费用、平均有息负债、当期有息负债。"""
    cur = ((diag or {}).get("period") or {}).get("current")
    out = {}
    etr = _ratio_entry(diag, "effective_tax_rate")
    if etr and isinstance(etr.get("value"), (int, float)):
        out["tax"] = etr["value"]
    ic = _ratio_entry(diag, "interest_coverage")
    ie = ((ic or {}).get("inputs") or {}).get("interest_expense")
    if isinstance(ie, (int, float)) and ie > 0:
        out["interest_expense"] = ie
    ibd_cur = _derived(diag, "interest_bearing_debt", cur)
    if ibd_cur is None:
        e = _ratio_entry(diag, "interest_bearing_debt_ratio")
        ibd_cur = ((e or {}).get("inputs") or {}).get("interest_bearing_debt")
    ibd_prev = _derived(diag, "interest_bearing_debt",
                        ((diag or {}).get("period") or {}).get("previous"))
    if isinstance(ibd_cur, (int, float)) and ibd_cur > 0:
        out["debt_book"] = ibd_cur
        if isinstance(ibd_prev, (int, float)) and ibd_prev > 0 and out.get("interest_expense"):
            out["rd"] = out["interest_expense"] / ((ibd_cur + ibd_prev) / 2.0)
    return out


def is_bank(diag, industry):
    if industry == "banking":
        return True
    return bool(_ratio_entry(diag, "rwa_return"))


# ---------------------------------------------------------------- 主流程

def compute(args) -> dict:
    inputs = json.load(open(INPUTS_PATH, encoding="utf-8"))
    rf = inputs["risk_free_rate"]
    mrp = inputs["mrp"]

    # 1) 公司解析（--no-net 允许合成数据不带代码）
    if args.code:
        code, secid = args.code, secid_from_code(args.code)
        name = None
    elif args.name:
        code, secid, name = resolve_name(args.name)
        if not code:
            sys.exit("找不到该公司（仅支持沪深 A 股）：%s" % args.name)
    elif args.no_net:
        code, secid, name = None, None, "合成数据（离线）"
    else:
        sys.exit("必须给 --code 或 --name")

    # 2) β
    if args.beta is not None:
        beta = {"value": args.beta, "std_error": None, "n_weeks": None,
                "r_squared": None, "index": None, "source": "manual(--beta)"}
        if args.beta <= 0 or args.beta > 3:
            sys.exit("--beta 必须在 (0, 3] 内")
    elif args.no_net:
        sys.exit("--no-net 下没有行情，β 不可回归，必须显式给 --beta（不猜数）")
    else:
        idx_cfg = inputs["index_for_beta"]
        r2_min = inputs.get("beta_r2_min", 0.05)
        try:
            stock = weekly_closes(secid, idx_cfg["weeks"])
            index = weekly_closes(idx_cfg["secid"], idx_cfg["weeks"])
            beta = beta_regression(stock, index, idx_cfg["name"])
            if not beta:
                sys.exit("β 回归样本不足（周收益率对齐后 <40 周），拒绝产出；可用 --beta 显式传入并留痕")
            beta["source"] = "回归(%d 周周收益率 vs %s)" % (beta["n_weeks"], idx_cfg["name"])
            if (beta.get("r_squared") or 0) < r2_min:
                # 回归无解释力（如分红驱动的独立行情），采信就是掩耳盗铃。
                # 银行回退同业 β 中位数；非银行拒绝，要求显式传入。
                own_r2 = beta.get("r_squared")
                fallback = sector_beta_median(code, idx_cfg) if args.industry == "banking" else None
                if fallback:
                    peer_total = fallback.pop("peer_total")
                    beta = fallback
                    beta["source"] = ("本公司回归 R²=%.3f < %.2f 无解释力，改用同业 β 中位数"
                                      "（%d 家上市银行逐家回归，%d 家 R²≥%.2f）"
                                      % (own_r2, r2_min, peer_total, beta["n_weeks"], r2_min))
                else:
                    sys.exit("β 回归解释力不足（R²=%.3f < %.2f），拒绝采信；"
                             "可用 --beta 显式传入（会标注 manual）"
                             % ((beta.get("r_squared") or 0), r2_min))
        except SystemExit:
            raise
        except Exception as e:
            sys.exit("行情接口不可用（%s）。β 拿不到就拒绝产出，可 --beta 显式传入" % e)

    b_raw_lo = beta["value"] - 2 * (beta.get("std_error") or 0.0)
    b_raw_hi = beta["value"] + 2 * (beta.get("std_error") or 0.0)
    # 截断可能使上下界翻转（β 极小且标准误大时），先排序再算成本，保证 low ≤ high
    b_lo, b_hi = min(max(0.3, b_raw_lo), 2.5), max(min(2.5, b_raw_hi), 0.3)
    b_lo, b_hi = min(b_lo, b_hi), max(b_lo, b_hi)

    # 3) 股权成本
    coe_low = rf["value"] + b_lo * mrp["low"]
    coe_point = rf["value"] + beta["value"] * mrp["point"]
    coe_high = rf["value"] + b_hi * mrp["high"]

    # 4) 公司报表数（税率/债务成本/资本结构）
    diag = json.load(open(args.ratios, encoding="utf-8")) if args.ratios else None
    ci = company_inputs_from_ratios(diag) if diag else {}
    tax = ci.get("tax", inputs["tax_fallback"]["value"])
    tax_src = "公司有效税率（所得税费用/利润总额）" if "tax" in ci else "法定 25%（公司有效税率不可得）"
    if is_bank(diag, args.industry):
        banking = True
        rd = rd_src = None
    else:
        banking = False
        rd = ci.get("rd", inputs["rd_fallback"]["value"])
        rd_src = ("公司自算：利息费用/平均有息负债" if "rd" in ci
                  else "中债商业银行 AAA 债 10Y（公司利息费用不可得，市场口径兜底）")

    # 5) WACC（非银行）
    wacc = None
    if not banking:
        mcap = None
        if not args.no_net:
            mcap, _ = get_market_cap(secid)
        debt = ci.get("debt_book")
        if mcap and debt and mcap > 0:
            we = mcap / (mcap + debt)
            wd = 1 - we
            wacc = {"low": coe_low * we + rd * (1 - tax) * wd,
                    "point": coe_point * we + rd * (1 - tax) * wd,
                    "high": coe_high * we + rd * (1 - tax) * wd,
                    "e_ratio": we, "d_ratio": wd,
                    "note": "E=总市值（东财行情），D=报表有息负债账面值近似"}
        else:
            wacc = {"low": coe_low, "point": coe_point, "high": coe_high,
                    "e_ratio": 1.0, "d_ratio": 0.0,
                    "note": "市值或有息负债不可得，按全权益近似（=股权成本）；"
                            "全权益假设使门槛偏高、触发偏严，不会把风险藏起来"}

    doc = {
        "schema": "finradar.wacc/1.0",
        "generator": "risk-radar/scripts/compute_wacc.py",
        "company": {"code": code, "name": name, "secid": secid, "banking": banking},
        "generated_at": None,   # detect 侧不依赖时间，这里留运行时填
        "cost_of_equity": {"low": coe_low, "point": coe_point, "high": coe_high},
        "wacc": wacc,
        "components": {
            "risk_free_rate": {"value": rf["value"], "as_of": rf["as_of"], "source": rf["source"]},
            "beta": {"low": round(b_lo, 4), "point": round(beta["value"], 4),
                     "high": round(b_hi, 4), "source": beta["source"],
                     "std_error": beta.get("std_error"), "n_weeks": beta.get("n_weeks"),
                     "r_squared": beta.get("r_squared")},
            "mrp": {"low": mrp["low"], "high": mrp["high"], "basis": mrp["basis"]},
            "tax": {"value": tax, "source": tax_src},
            "rd": {"value": rd, "source": rd_src} if rd is not None else None,
            "capital_structure": ({"e_ratio": wacc["e_ratio"], "d_ratio": wacc["d_ratio"],
                                   "note": wacc["note"]} if wacc else None),
        },
        "banking_note": ("银行为存款经营类负债结构，经典 WACC 失真。门槛统一用股权成本 Ke；"
                         "B12 的 RAROC 口径 = 净利润/资本净额（rwa_return/capital_adequacy_ratio），"
                         "与 Ke 同尺度可比" if banking else None),
    }
    doc["generated_at"] = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
    return doc


def main():
    ap = argparse.ArgumentParser(description="按公司现场计算 WACC 敏感性区间")
    ap.add_argument("--code", help="6 位公司代码")
    ap.add_argument("--name", help="公司名称（自动解析代码）")
    ap.add_argument("--ratios", help="B 的 ratios 文档（取有效税率/利息费用/有息负债）")
    ap.add_argument("--industry", default=None, choices=["banking", None], help="强制按银行业口径")
    ap.add_argument("--beta", type=float, default=None, help="显式传入 β（回归不可得时用，会标注 manual）")
    ap.add_argument("--no-net", action="store_true", help="离线模式（合成数据/测试），必须配合 --beta")
    ap.add_argument("--out", default=None, help="输出路径（缺省只打印预览）")
    ap.add_argument("--write", action="store_true", help="允许写盘（与 --out 搭配）")
    args = ap.parse_args()

    doc = compute(args)

    def show(x):
        return "%.2f%%" % (x * 100)

    print("%s(%s) %s口径" % (doc["company"]["name"] or doc["company"]["code"],
                             doc["company"]["code"],
                             "银行 Ke" if doc["company"]["banking"] else "WACC"))
    print("  β = %.3f（%s）" % (doc["components"]["beta"]["point"],
                               doc["components"]["beta"]["source"]))
    print("  区间: low %s | point %s | high %s" % (
        show((doc["wacc"] or doc["cost_of_equity"])["low"]),
        show((doc["wacc"] or doc["cost_of_equity"])["point"]),
        show((doc["wacc"] or doc["cost_of_equity"])["high"])))
    if args.write:
        if not args.out:
            sys.exit("--write 需要配合 --out")
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("  已写入:", args.out)


if __name__ == "__main__":
    main()
