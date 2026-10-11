"""取数工作进程 —— 独立跑在「数据 Python」下（含 akshare / yfinance / pandas）。

为什么要单独一个进程：主程序可能跑在只有 openpyxl 的解释器里，而取数需要
pandas 等重型依赖。用 subprocess + JSON 交换数据，主程序保持轻量。

协议：
    <data python> worker.py <request.json> <response.json>
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import date

# ------------------------------------------------------------------ 环境清理
# Windows 系统代理会挡住部分财经数据接口，而 requests 会经 urllib.getproxies()
# 读到注册表里的代理设置，所以要在导入第三方库之前清掉。
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

MAX_YEARS = 8


# ================================================================== 工具


def num(value):
    """把各种脏值统一成 float 或 None。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return None if v != v else v      # NaN
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in ("", "--", "-", "None", "nan", "NaN", "null"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_period(raw):
    """把报告期统一成 (年, 月, 日)。兼容 20251231 / 2025-12-31 / 2025/12/31。"""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) < 8:
        return None
    try:
        return int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
    except ValueError:
        return None


def annual_rows(df, date_col="报告日"):
    """只保留年报（12-31），按年份升序。"""
    if df is None or df.empty or date_col not in df.columns:
        return []
    out = []
    for _, row in df.iterrows():
        p = parse_period(row[date_col])
        if p and (p[1], p[2]) == (12, 31):
            out.append((p[0], row))
    out.sort(key=lambda x: x[0])
    return out[-MAX_YEARS:]


def pick(row, names, scale=1.0):
    """按候选列名依次取第一个有值的字段。"""
    for name in names:
        if name in row.index:
            v = num(row[name])
            if v is not None:
                return v * scale
    return None


def to_yuan(v):
    """新浪/东财的财报有时以元、有时以万元给出，这里统一到元。"""
    return v


# ================================================================== A 股


def fetch_ashare(code: str) -> dict:
    """A 股：用 akshare 的新浪源取财务，新浪行情取价格，自算倍数。"""
    import akshare as ak

    raw = str(code).strip().lower()
    for p in ("sh", "sz", "bj"):
        if raw.startswith(p):
            raw = raw[len(p):]
    code = raw.zfill(6)
    symbol = ("sh" if code[0] in "69" else "sz" if code[0] in "023" else "bj") + code

    warnings: list[str] = []
    sources = []

    def grab(name):
        try:
            df = ak.stock_financial_report_sina(stock=symbol, symbol=name)
            sources.append({"name": f"新浪财经·{name}", "as_of": date.today().isoformat(),
                            "official": False})
            return df
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name}取数失败：{str(exc)[:70]}")
            return None

    income = grab("利润表")
    balance = grab("资产负债表")
    cash = grab("现金流量表")

    inc_rows = dict(annual_rows(income))
    bal_rows = dict(annual_rows(balance))
    cfs_rows = dict(annual_rows(cash))
    years = sorted(inc_rows)

    if not years:
        return {"ok": False, "error": "没有取到任何年度财务数据（新浪接口可能不可用）",
                "warnings": warnings}

    def series(rows_map, names):
        return [pick(rows_map[y], names) if rows_map.get(y) is not None else None for y in years]

    fin = {
        "years": years,
        "revenue": series(inc_rows, ["营业总收入", "营业收入"]),
        "cogs": series(inc_rows, ["营业成本"]),
        "pretax_income": series(inc_rows, ["利润总额"]),
        "tax_provision": series(inc_rows, ["所得税费用"]),
        "net_income": series(inc_rows, ["净利润", "归属于母公司所有者的净利润"]),
        "interest_expense": series(inc_rows, ["利息费用", "利息支出"]),
        "da": [None] * len(years),
        "capex": series(cfs_rows, ["购建固定资产、无形资产和其他长期资产所支付的现金"]),
        "delta_nwc": [None] * len(years),
        "total_debt": None,
        "cash": None,
        "minority_interest": None,
        "preferred_stock": 0.0,
        "total_assets": None,
        "total_equity": None,
        "price": None,
        "shares_outstanding": None,
        "market_cap": None,
        "beta": None,
    }

    # 营业利润作为 EBIT 的近似（利润总额含营业外收支）
    fin["ebit"] = series(inc_rows, ["营业利润"])

    # 折旧摊销：现金流量表补充资料里没有，用「固定资产折旧」近似；取不到则留空
    for key, names in (("da", ["固定资产折旧、油气资产折耗、生产性生物资产折旧", "固定资产折旧"]),):
        vals = series(cfs_rows, names)
        if any(v is not None for v in vals):
            fin[key] = vals

    if years[-1] in bal_rows:
        row = bal_rows[years[-1]]
        short = pick(row, ["短期借款"]) or 0.0
        long_ = pick(row, ["长期借款"]) or 0.0
        bond = pick(row, ["应付债券"]) or 0.0
        fin["total_debt"] = short + long_ + bond
        fin["cash"] = pick(row, ["货币资金"])
        fin["minority_interest"] = pick(row, ["少数股东权益"])
        fin["total_assets"] = pick(row, ["资产总计"])
        fin["total_equity"] = pick(row, ["所有者权益(或股东权益)合计", "所有者权益"])
        shares = pick(row, ["实收资本(或股本)"])
        if shares:
            # 实收资本以元计、面值 1 元 → 股数
            fin["shares_outstanding"] = shares

    # ΔNWC：用应收账款+存货−应付账款 的同比变化近似
    if bal_rows:
        def pair(names):
            return [pick(bal_rows[y], names) if bal_rows.get(y) is not None else None
                    for y in years]
        ar = pair(["应收账款", "应收票据及应收账款"])
        inv = pair(["存货"])
        ap = pair(["应付账款", "应付票据及应付账款"])
        nwc = [(a or 0) + (i or 0) - (p or 0) for a, i, p in zip(ar, inv, ap)]
        fin["delta_nwc"] = [None] + [nwc[i] - nwc[i - 1] for i in range(1, len(nwc))]
        warnings.append("营运资本变动为「（应收账款＋存货−应付账款）的同比变化」近似值，"
                        "与现金流量表口径可能有差异。")

    # 行情
    try:
        import requests
        r = requests.get(f"https://hq.sinajs.cn/list={symbol}",
                         headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn"},
                         timeout=15)
        r.encoding = "gbk"
        payload = r.text.split('="', 1)[1].rstrip('";\n')
        parts = payload.split(",")
        if len(parts) > 3:
            fin["price"] = num(parts[3])
            name = parts[0]
            sources.append({"name": "新浪财经·行情", "as_of": date.today().isoformat(),
                            "official": False})
    except Exception as exc:  # noqa: BLE001
        name = code
        warnings.append(f"行情取数失败：{str(exc)[:70]}")

    if fin["price"] and fin["shares_outstanding"]:
        fin["market_cap"] = fin["price"] * fin["shares_outstanding"]

    # Beta：对沪深300 回归 500 个交易日
    try:
        import numpy as np
        idx = ak.stock_zh_index_daily(symbol="sh000300")[["date", "close"]].tail(505)
        idx["date"] = idx["date"].astype(str)
        ir = idx.set_index("date")["close"].pct_change().dropna()
        d = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")[["date", "close"]].tail(505)
        d["date"] = d["date"].astype(str)
        sr = d.set_index("date")["close"].pct_change().dropna()
        j = sr.to_frame("s").join(ir.to_frame("i"), how="inner").dropna()
        if len(j) >= 60:
            fin["beta"] = float(np.cov(j["s"], j["i"])[0][1] / np.var(j["i"], ddof=1))
            fin["beta_note"] = f"对沪深300 回归 {len(j)} 个交易日"
            sources.append({"name": "新浪财经·日行情（Beta 回归）",
                            "as_of": date.today().isoformat(), "official": False})
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Beta 计算失败：{str(exc)[:60]}")

    return {
        "ok": True,
        "market": "A",
        "currency": "CNY",
        "code": code,
        "name": name,
        "financials": fin,
        "sources": sources,
        "warnings": warnings,
    }


# ================================================================== 美股


def fetch_us(ticker: str) -> dict:
    """美股：yfinance 取三表 + 行情 + beta。"""
    try:
        import yfinance as yf
    except ImportError:
        return {"ok": False,
                "error": "未安装 yfinance。美股需要它：py -m pip install yfinance",
                "hint": "install_yfinance"}

    t = yf.Ticker(ticker)
    info = t.info or {}
    warnings: list[str] = []

    def row(df, names, years):
        """从 yfinance 的 DataFrame 取一行，按年份对齐。"""
        if df is None or df.empty:
            return [None] * len(years)
        out = []
        for y in years:
            val = None
            for col in df.columns:
                if str(col)[:4] == str(y):
                    for name in names:
                        if name in df.index:
                            val = num(df.loc[name, col])
                            break
                    break
            out.append(val)
        return out

    inc = t.income_stmt
    cfs = t.cashflow
    bal = t.balance_sheet

    cols = list(inc.columns) if inc is not None and not inc.empty else []
    years = sorted({int(str(c)[:4]) for c in cols})[-MAX_YEARS:]

    fin = {
        "years": years,
        "revenue": row(inc, ["Total Revenue", "Operating Revenue"], years),
        "cogs": row(inc, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], years),
        "ebit": row(inc, ["Operating Income", "EBIT"], years),
        "pretax_income": row(inc, ["Pretax Income"], years),
        "tax_provision": row(inc, ["Tax Provision"], years),
        "net_income": row(inc, ["Net Income Common Stockholders", "Net Income"], years),
        "interest_expense": row(inc, ["Interest Expense"], years),
        "da": row(cfs, ["Depreciation And Amortization", "Depreciation",
                        "Depreciation Amortization Depletion"], years),
        "capex": [abs(v) if v is not None else None
                  for v in row(cfs, ["Capital Expenditure"], years)],
        "delta_nwc": row(cfs, ["Change In Working Capital"], years),
        "sbc": row(cfs, ["Stock Based Compensation"], years),
        "total_debt": num(info.get("totalDebt")),
        "cash": num(info.get("totalCash")),
        "minority_interest": None,
        "preferred_stock": 0.0,
        "total_assets": None,
        "total_equity": None,
        "price": num(info.get("currentPrice") or info.get("regularMarketPrice")),
        "shares_outstanding": num(info.get("sharesOutstanding")),
        "market_cap": num(info.get("marketCap")),
        "beta": num(info.get("beta")),
    }

    if bal is not None and not bal.empty:
        col = bal.columns[0]
        for key, names in (("total_assets", ["Total Assets"]),
                           ("total_equity", ["Stockholders Equity", "Total Equity Gross Minority Interest"]),
                           ("minority_interest", ["Minority Interest"])):
            for n in names:
                if n in bal.index:
                    fin[key] = num(bal.loc[n, col])
                    break

    # 现金流量表的 ΔNWC 若为正表示占用增加，方向已一致
    if not any(v is not None for v in fin["delta_nwc"]):
        warnings.append("现金流量表未提供营运资本变动，已留空（模型会按收入比例估算）。")

    return {
        "ok": True,
        "market": "US",
        "currency": info.get("currency") or "USD",
        "code": ticker.upper(),
        "name": info.get("longName") or info.get("shortName") or ticker,
        "industry": info.get("industry", ""),
        "sector": info.get("sector", ""),
        "financials": fin,
        "sources": [{"name": "yfinance（Yahoo Finance）", "as_of": date.today().isoformat(),
                     "official": False}],
        "warnings": warnings,
    }


# ================================================================== 入口


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("用法: worker.py <request.json> <response.json>", file=sys.stderr)
        return 2

    request = json.loads(open(argv[1], encoding="utf-8").read())
    action = request.get("action")

    try:
        if action == "health":
            result = {"ok": True, "python": sys.version.split()[0]}
            for mod in ("akshare", "yfinance", "pandas", "numpy", "openpyxl"):
                try:
                    m = __import__(mod)
                    result[mod] = getattr(m, "__version__", "installed")
                except Exception:  # noqa: BLE001
                    result[mod] = None
        elif action == "ashare":
            result = fetch_ashare(request["code"])
        elif action == "us":
            result = fetch_us(request["ticker"])
        else:
            result = {"ok": False, "error": f"未知 action: {action}"}
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                  "traceback": traceback.format_exc()[-1200:]}

    with open(argv[2], "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
