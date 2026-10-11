"""估值引擎的数据结构。

设计原则：**输入与输出都是纯 JSON 可序列化的**，这样 D 的总集成可以直接
把它们塞进统一数据对象里，不需要理解 Python 对象。

单位约定（全项目统一）：
  · 金额一律用**报表原始货币的「元」**，展示层再换算成亿元/百万
  · 比率一律用**小数**（15% 写作 0.15）
  · 股价用「元 / 美元」
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Company:
    """标的或可比公司的基础信息。"""
    name: str = ""
    ticker: str = ""
    market: str = "A"            # "A"（A股）或 "US"（美股）
    currency: str = "CNY"        # CNY / USD
    industry: str = ""
    sector: str = ""
    report_period: str = ""      # 如 2025-12-31
    price_date: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Financials:
    """历史财务。金额单位=元，按年份升序。

    年份索引的数组一律与 `years` 等长；缺失值用 None，不要用 0 冒充。
    """
    years: list[int] = field(default_factory=list)

    # 利润表
    revenue: list[float | None] = field(default_factory=list)
    cogs: list[float | None] = field(default_factory=list)
    ebit: list[float | None] = field(default_factory=list)
    pretax_income: list[float | None] = field(default_factory=list)
    tax_provision: list[float | None] = field(default_factory=list)
    net_income: list[float | None] = field(default_factory=list)
    interest_expense: list[float | None] = field(default_factory=list)
    sbc: list[float | None] = field(default_factory=list)

    # 现金流量表
    da: list[float | None] = field(default_factory=list)          # 折旧摊销
    capex: list[float | None] = field(default_factory=list)       # 资本开支（正数=流出）
    delta_nwc: list[float | None] = field(default_factory=list)   # 营运资本变动（正数=占用增加）

    # 资产负债表（最新一期）
    total_debt: float | None = None
    cash: float | None = None
    minority_interest: float | None = None
    preferred_stock: float | None = None
    total_assets: float | None = None
    total_equity: float | None = None

    # 市场
    price: float | None = None
    shares_outstanding: float | None = None   # 稀释后股本
    market_cap: float | None = None
    beta: float | None = None

    def latest(self, series: list[float | None]) -> float | None:
        for value in reversed(series or []):
            if value is not None:
                return value
        return None

    def net_debt(self) -> float:
        return (self.total_debt or 0.0) - (self.cash or 0.0)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Financials":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Peer:
    """可比公司。倍数缺哪个就留 None，别用 0 冒充。"""
    name: str = ""
    ticker: str = ""
    pe: float | None = None            # 市盈率
    pe_forward: float | None = None    # 预期市盈率
    pb: float | None = None
    ps: float | None = None
    ev_revenue: float | None = None
    ev_ebitda: float | None = None
    ev_ebit: float | None = None
    peg: float | None = None
    revenue_growth: float | None = None     # 小数
    gross_margin: float | None = None
    ebitda_margin: float | None = None
    ebit_margin: float | None = None
    market_cap: float | None = None
    net_debt: float | None = None
    ebitda: float | None = None
    revenue: float | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Peer":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Assumptions:
    """估值假设。所有默认值都给出理由（见 RULES.md）。"""
    # 预测期
    forecast_years: int = 5

    # 收入
    revenue_growth_y1: float | None = None     # 首年增速；None=用历史 CAGR
    terminal_growth: float = 0.025             # 永续增速

    # 利润率（None = 用近三年中位数）
    ebit_margin: float | None = None
    da_pct_revenue: float | None = None
    capex_pct_revenue: float | None = None
    nwc_pct_revenue: float | None = None
    tax_rate: float | None = None
    sbc_is_cash: bool = False                  # SaaS 一般算现金支出

    # WACC
    risk_free: float | None = None
    erp: float = 0.0514                        # 中国用 Damodaran 中国值；美国用 4.28%
    beta: float | None = None                  # None = 用数据源给的市场 beta
    cost_of_debt: float | None = None          # None = 用利息费用/有息负债
    size_premium: float = 0.0
    target_debt_ratio: float | None = None     # None = 用当前市值口径

    # 相对估值
    multiple_adjustment: dict[str, float] = field(default_factory=dict)  # {"pe": 0.1, ...}

    # 方法权重（None = 按有无 SOTP 自动取默认）
    weights: dict[str, float] = field(default_factory=dict)

    # 情景
    bull_growth_delta: float = 0.03
    bull_margin_delta: float = 0.02
    bull_wacc_delta: float = -0.01
    bear_growth_delta: float = -0.03
    bear_margin_delta: float = -0.02
    bear_wacc_delta: float = 0.01

    # 敏感性轴
    wacc_steps: list[float] = field(default_factory=lambda: [-0.01, -0.005, 0.0, 0.005, 0.01])
    growth_steps: list[float] = field(default_factory=lambda: [-0.01, -0.005, 0.0, 0.005, 0.01])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Assumptions":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class SotpSegment:
    """分部估值的一个分部门。"""
    name: str = ""
    metric: str = "ebitda"          # ebitda / revenue / ebit
    value: float | None = None      # 该分部的指标值（元）
    multiple: float | None = None   # 纯业务可比公司的中位倍数
    peer_names: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValuationInput:
    """一个完整的估值请求。"""
    company: Company = field(default_factory=Company)
    financials: Financials = field(default_factory=Financials)
    peers: list[Peer] = field(default_factory=list)
    assumptions: Assumptions = field(default_factory=Assumptions)
    sotp_segments: list[SotpSegment] = field(default_factory=list)
    # 多倍数加权（相对估值用哪些倍数、各自权重）
    relative_multiples: list[str] = field(default_factory=lambda: ["pe", "ev_ebitda"])
    sources: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "company": self.company.to_dict(),
            "financials": self.financials.to_dict(),
            "peers": [p.to_dict() for p in self.peers],
            "assumptions": self.assumptions.to_dict(),
            "sotp_segments": [s.to_dict() for s in self.sotp_segments],
            "relative_multiples": self.relative_multiples,
            "sources": self.sources,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ValuationInput":
        data = data or {}
        return cls(
            company=Company.from_dict(data.get("company")),
            financials=Financials.from_dict(data.get("financials")),
            peers=[Peer.from_dict(p) for p in (data.get("peers") or [])],
            assumptions=Assumptions.from_dict(data.get("assumptions")),
            sotp_segments=[SotpSegment(**{k: v for k, v in s.items()
                                          if k in SotpSegment.__dataclass_fields__})
                           for s in (data.get("sotp_segments") or [])],
            relative_multiples=data.get("relative_multiples") or ["pe", "ev_ebitda"],
            sources=data.get("sources") or [],
            meta=data.get("meta") or {},
        )
