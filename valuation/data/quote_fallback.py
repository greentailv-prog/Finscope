"""腾讯财经 A 股行情备用源。

仅在 C 单独运行、没有 ABC 上游权威行情时使用；不会覆盖 D 的 canonical 行情。
腾讯总市值的单位为亿元，股本按总市值/最新价反推，**只能视为近似值**。
"""
from __future__ import annotations

import re
from datetime import datetime

import requests

from . import cache


def code6(value: str) -> str:
    raw = str(value or "").strip().upper().replace(" ", "")
    m = re.fullmatch(r"(?:(?:SH|SZ|BJ))?(\d{6})(?:\.(?:SH|SZ|BJ))?", raw)
    if not m:
        raise ValueError(f"无效的 A 股代码：{value!r}")
    return m.group(1)


def symbol(code: str) -> str:
    code = code6(code)
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("0", "3")):
        return "sz" + code
    return "bj" + code


def parse_tencent_quote(content: bytes | str, code: str) -> dict:
    """解析腾讯标准 ~ 分隔报价，不根据可疑字段猜测市值。"""
    text = content.decode("gbk", errors="replace") if isinstance(content, bytes) else content
    match = re.search(r'="([^"]+)"', text)
    if not match:
        raise ValueError("腾讯行情响应为空或格式不匹配")
    parts = match.group(1).split("~")
    if len(parts) <= 45:
        raise ValueError("腾讯行情未返回完整的总市值字段")
    expected = code6(code)
    if parts[2] != expected:
        raise ValueError(f"腾讯返回股票代码 {parts[2]} 与请求代码 {expected} 不一致")
    try:
        price = float(parts[3])
        cap_yi = float(parts[45])    # 0-based index 45 = 总市值（亿元）
    except (TypeError, ValueError) as exc:
        raise ValueError("行情中最新价或总市值不是有效数字") from exc
    if not (0 < price < 100000 and 0 < cap_yi < 1e9):
        raise ValueError("腾讯行情股价或总市值超出合理范围")
    market_cap = cap_yi * 1e8
    estimated_shares = int(round(market_cap / price))
    if not 100000 <= estimated_shares <= 1e14:
        raise ValueError("按市值/价格推算的股本超出合理范围")
    try:
        quote_time = datetime.strptime(parts[30], "%Y%m%d%H%M%S")
    except (ValueError, IndexError):
        raise ValueError("行情缺少可识别的交易时间，不能确定报价有效期") from None
    return {
        "ok": True, "name": parts[1].strip(), "industry": "",
        "price": price, "shares_outstanding": estimated_shares,
        "market_cap": market_cap,
        "shares_estimated": True,
        "shares_source": "腾讯财经总市值÷最新价反推（近似）",
        "price_date": quote_time.date().isoformat(),
        "price_time": quote_time.strftime("%H:%M:%S"),
        "price_source": "腾讯财经·行情",
        "source_url": f"https://qt.gtimg.cn/q={symbol(expected)}",
        "warnings": ["东方财富公司信息无法读取时使用腾讯财经备用行情；总股本为按总市值/股价反推的近似值，请核对公司公告或交易所数据。"],
    }


def quote_tencent(code: str, use_cache: bool = True) -> dict:
    code = code6(code)
    key = f"tencent_quote_{code}"
    if use_cache:
        existing = cache.get(key, ttl_seconds=180)
        if isinstance(existing, dict) and existing.get("ok"):
            return existing
    r = requests.get(
        f"https://qt.gtimg.cn/q={symbol(code)}",
        headers={"User-Agent": "Mozilla/5.0 (FinScope valuation)",
                 "Referer": "https://gu.qq.com/"},
        timeout=9,
    )
    r.raise_for_status()
    data = parse_tencent_quote(r.content, code)
    if use_cache:
        cache.put(key, data)
    return data
