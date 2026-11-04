"""通用计算工具：只做数学，不碰业务规则。"""
from __future__ import annotations

import math
from statistics import median, mean, pstdev


def normalize_name(name) -> str:
    """A 股简称常被数据源写成「五 粮 液」，展示前去掉中文姓名里的空格。"""
    text = str(name or "")
    if any("一" <= ch <= "鿿" for ch in text):
        return text.replace(" ", "")
    return text


def clean(seq) -> list[float]:
    return [float(v) for v in (seq or []) if v is not None and not _is_nan(v)]


def _is_nan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


def median_of(seq, default=None):
    vals = clean(seq)
    return median(vals) if vals else default


def mean_of(seq, default=None):
    vals = clean(seq)
    return mean(vals) if vals else default


def safe_div(a, b, default=None):
    try:
        if a is None or b in (None, 0):
            return default
        return a / b
    except (TypeError, ZeroDivisionError):
        return default


def clamp(value, low, high):
    if value is None:
        return None
    return max(low, min(high, value))


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def num(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def cagr(first, last, periods: int) -> float | None:
    if first is None or last is None or periods <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / periods) - 1


def growth_rate(prev, curr) -> float | None:
    if prev is None or curr is None or prev == 0:
        return None
    return curr / prev - 1


def series_growth(series: list[float | None]) -> list[float | None]:
    """同比增速序列。缺失年份保留 None。"""
    out: list[float | None] = []
    for i, value in enumerate(series or []):
        if i == 0 or series[i - 1] in (None, 0) or value is None:
            out.append(None)
        else:
            out.append(value / series[i - 1] - 1)
    return out


def last_n(seq, n: int = 3) -> list[float]:
    vals = [v for v in (seq or []) if v is not None]
    return vals[-n:]


def median_last_n(seq, n: int = 3, default=None):
    return median_of(last_n(seq, n), default)


def percentile_rank(value, sample: list[float]) -> float | None:
    """value 在 sample 中的分位（0–100）。"""
    vals = clean(sample)
    if value is None or not vals:
        return None
    below = sum(1 for v in vals if v < value)
    equal = sum(1 for v in vals if v == value)
    return (below + 0.5 * equal) / len(vals) * 100


def percentile(sample: list[float], q: float) -> float | None:
    """线性插值分位数。q 取 0–1。"""
    vals = sorted(clean(sample))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def dispersion(sample: list[float]) -> float | None:
    """离散度 = 四分位距 / 中位数。越大说明同业估值越不一致。"""
    vals = clean(sample)
    if len(vals) < 2:
        return None
    med = median(vals)
    if med == 0:
        return None
    return (percentile(vals, 0.75) - percentile(vals, 0.25)) / abs(med)


def volatility(series: list[float | None]) -> float | None:
    vals = clean(series)
    if len(vals) < 3:
        return None
    mean_v = mean(vals)
    if mean_v == 0:
        return None
    return pstdev(vals) / abs(mean_v)


def weighted_average(pairs: list[tuple[float, float]]) -> float | None:
    """pairs = [(value, weight), ...]；权重自动归一化。"""
    usable = [(v, w) for v, w in pairs if v is not None and w and w > 0]
    if not usable:
        return None
    total = sum(w for _, w in usable)
    if total <= 0:
        return None
    return sum(v * w for v, w in usable) / total


def solve_bisection(fn, target: float, lo: float, hi: float, tol: float = 1e-5, max_iter: int = 80):
    """求 fn(x)=target 的根。fn 单调递增时使用。找不到返回 None。"""
    f_lo = fn(lo)
    f_hi = fn(hi)
    if f_lo is None or f_hi is None:
        return None
    if (f_lo - target) * (f_hi - target) > 0:
        # 端点同侧，无法保证有根
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = fn(mid)
        if f_mid is None:
            return None
        if abs(f_mid - target) <= tol:
            return mid
        if (f_lo - target) * (f_mid - target) <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2
