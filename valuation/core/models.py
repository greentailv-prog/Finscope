"""FinScope 估值引擎数据结构（v2）。

设计原则：
  · 输入、输出都是纯 JSON，可直接进 D 的统一数据对象；
  · 金额统一用「元」，比率用小数；
  · 任何缺失值用 None，不用 0 冒充；
  · 每条假设、每个可比公司、每个分部都带来源与理由，展示层不另编。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# 基础对象
# ---------------------------------------------------------------------------


@dataclass
class Company:
    name: str = ""
    ticker: str = ""
    market: str = "A"                 # A / US
    currency: str = "CNY"
    industry: str = ""
    sector: str = ""
    report_period: str = ""           # 估值基准期 2025-12-31
    price_date: str = ""
    price_time: str = ""
    price_source: str = ""
    listing_date: str = ""
    business: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Company":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Financials:
    """历史财务。金额单位=元，按年份升序；缺失用 None。"""
    years: list[int] = field(default_factory=list)

    # 利润表
    revenue: list[float | None] = field(default_factory=list)
    cogs: list[float | None] = field(default_factory=list)
    gross_profit: list[float | None] = field(default_factory=list)
    ebit: list[float | None] = field(default_factory=list)
    pretax_income: list[float | None] = field(default_factory=list)
    tax_provision: list[float | None] = field(default_factory=list)
    net_income: list[float | None] = field(default_factory=list)
    net_income_parent: list[float | None] = field(default_factory=list)
    interest_expense: list[float | None] = field(default_factory=list)
    finance_expense: list[float | None] = field(default_factory=list)
    sbc: list[float | None] = field(default_factory=list)
    eps: list[float | None] = field(default_factory=list)

    # 现金流量表
    da: list[float | None] = field(default_factory=list)
    capex: list[float | None] = field(default_factory=list)
    delta_nwc: list[float | None] = field(default_factory=list)
    cfo: list[float | None] = field(default_factory=list)
    dividends_paid: list[float | None] = field(default_factory=list)

    # 资产负债表（最新一期）
    total_debt: float | None = None
    cash: float | None = None
    minority_interest: float | None = None
    preferred_stock: float | None = None
    total_assets: float | None = None
    total_equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    inventory: float | None = None
    receivables: float | None = None
    payables: float | None = None

    # 市场
    price: float | None = None
    shares_outstanding: float | None = None
    market_cap: float | None = None
    beta: float | None = None
    beta_note: str = ""

    # 元数据
    industry: str = ""
    sector: str = ""
    price_date: str = ""
    price_time: str = ""
    price_source: str = ""
    data_notes: list[str] = field(default_factory=list)

    # ---- 便捷方法 ----
    def latest(self, series: list[float | None] | None) -> float | None:
        for value in reversed(series or []):
            if value is not None:
                return value
        return None

    def last_n(self, series: list[float | None] | None, n: int = 3) -> list[float | None]:
        values = [v for v in (series or []) if v is not None]
        return values[-n:]

    def net_debt(self) -> float:
        return (self.total_debt or 0.0) - (self.cash or 0.0)

    def ebitda_latest(self) -> float | None:
        ebit = self.latest(self.ebit)
        da = self.latest(self.da)
        if ebit is None and da is None:
            return None
        return (ebit or 0.0) + (da or 0.0)

    def book_equity(self) -> float | None:
        return self.total_equity

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Financials":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Peer:
    """可比公司。倍数缺哪个留 None；selection_reason 会原样披露。"""
    name: str = ""
    ticker: str = ""
    industry: str = ""
    pe: float | None = None
    pe_forward: float | None = None
    pb: float | None = None
    ps: float | None = None
    pcf: float | None = None
    peg: float | None = None
    ev_revenue: float | None = None
    ev_ebitda: float | None = None
    ev_ebit: float | None = None

    revenue_growth: float | None = None
    net_income_growth: float | None = None
    gross_margin: float | None = None
    ebitda_margin: float | None = None
    ebit_margin: float | None = None
    roe: float | None = None

    market_cap: float | None = None
    net_debt: float | None = None
    ebitda: float | None = None
    ebit: float | None = None
    revenue: float | None = None
    net_income: float | None = None
    equity: float | None = None
    cfo: float | None = None

    note: str = ""
    selection_reason: str = ""
    selection_score: float | None = None
    tier: str = "curated"             # curated / dynamic / proxy / user
    caliber: str = "LYR"
    source: str = ""
    as_of: str = ""
    data_ok: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Peer":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class Segment:
    """SOTP 的一个分部。"""
    name: str = ""
    level: str = "top"                # top / child
    parent: str = ""
    metric: str = "revenue"          # revenue / ebit / ebitda / gross_profit
    value: float | None = None       # 用于乘倍数的指标值（元）
    revenue: float | None = None
    gross_profit: float | None = None
    gross_margin: float | None = None
    ebit: float | None = None        # 规则分摊后的 EBIT
    ebitda: float | None = None      # 规则分摊后的 EBITDA
    revenue_share: float | None = None
    multiple_type: str = "ev_revenue"
    multiple: float | None = None
    peer_names: list[str] = field(default_factory=list)
    peer_tickers: list[str] = field(default_factory=list)
    peer_median_ev_revenue: float | None = None
    peer_median_ev_ebitda: float | None = None
    peer_median_pe: float | None = None
    segment_ev: float | None = None
    note: str = ""
    source: str = ""
    as_of: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Assumptions:
    """估值假设。字段为用户覆盖值；规则引擎会生成 effective 值并写入台账。"""
    # 方法
    method_selection: str = "auto"   # auto / dcf / comps / sotp / blended
    selected_methods: list[str] = field(default_factory=list)

    # 预测期
    forecast_years: int = 5
    revenue_growth_y1: float | None = None
    revenue_growth_path: list[float] = field(default_factory=list)
    terminal_growth: float | None = None
    terminal_method: str = "gordon"    # blend / gordon / exit / roic
    terminal_roic: float | None = None

    # 利润率
    ebit_margin: float | None = None
    da_pct_revenue: float | None = None
    capex_pct_revenue: float | None = None
    nwc_pct_revenue: float | None = None
    nwc_forecast_basis: str = "revenue"  # revenue: 每年增量占收入; delta_revenue: 营运资本投入率×增量收入
    nwc_investment_ratio: float | None = None  # 仅 delta_revenue 模式，需单独确认
    tax_rate: float | None = None
    sbc_is_cash: bool = False

    # WACC
    risk_free: float | None = None
    erp: float | None = None
    beta: float | None = None
    beta_mode: str = "blume"          # raw / blume / sector / manual
    cost_of_debt: float | None = None
    size_premium: float | None = None
    target_debt_ratio: float | None = None
    wacc_mode: str = "capm"      # capm / reconciled / manual
    wacc_override: float | None = None

    # 相对估值
    multiples: list[str] = field(default_factory=list)
    forward_net_income: float | None = None   # 与同行 forward PE 同期的归母预测净利润（元）
    forward_net_income_growth: float | None = None  # PEG 所需未来归母净利增速，小数
    multiple_adjustment: dict[str, float] = field(default_factory=dict)
    peer_growth_adjustment: bool = True

    # SOTP
    segment_allocation: str = "reported"  # gross_profit / revenue
    sotp_corporate_cost: float | None = None  # 对账后确认的总部成本现值；已计入时显式设0
    sotp_corporate_cost_pct: float = 0.02
    sotp_corporate_cost_cap_multiple: float = 8.0

    # 权重
    weights: dict[str, float] = field(default_factory=dict)
    weight_mode: str = "rules"        # rules / manual

    # 情景
    bull_growth_delta: float = 0.03
    bull_margin_delta: float = 0.02
    bull_wacc_delta: float = -0.01
    bear_growth_delta: float = -0.03
    bear_margin_delta: float = -0.02
    bear_wacc_delta: float = 0.01

    # 敏感性
    wacc_steps: list[float] = field(default_factory=lambda: [-0.01, -0.005, 0.0, 0.005, 0.01])
    growth_steps: list[float] = field(default_factory=lambda: [-0.01, -0.005, 0.0, 0.005, 0.01])

    # DDM（金融行业替代绝对估值）
    dividend_payout: float | None = None
    ddm_growth: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Assumptions":
        return cls(**{k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__})


@dataclass
class ValuationInput:
    """一次估值请求的完整输入。"""
    company: Company = field(default_factory=Company)
    financials: Financials = field(default_factory=Financials)
    peers: list[Peer] = field(default_factory=list)
    peer_set: list[str] = field(default_factory=list)       # 只有代码时由数据层补财务
    peer_financials: list[dict] = field(default_factory=list)
    peer_market_data: list[dict] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    segment_evidence: dict | None = None
    assumptions: Assumptions = field(default_factory=Assumptions)
    method_selection: str = "auto"
    relative_multiples: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    market_data: dict = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    fetch_data: bool = True            # 允许独立运行时联网取数
    allow_web: bool = True
    data_source: str = "auto"          # auto / ifind / choice / web / akshare / canonical
    web_evidence: dict | None = None   # Agent/D 复核后的网页/年报证据包
    as_of: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company.to_dict(),
            "financials": self.financials.to_dict(),
            "peers": [p.to_dict() for p in self.peers],
            "peer_set": self.peer_set,
            "segments": [s.to_dict() for s in self.segments],
            "assumptions": self.assumptions.to_dict(),
            "method_selection": self.method_selection,
            "relative_multiples": self.relative_multiples,
            "sources": self.sources,
            "market_data": self.market_data,
            "meta": self.meta,
            "data_source": self.data_source,
            "web_evidence": self.web_evidence,
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ValuationInput":
        data = data or {}
        assumptions = Assumptions.from_dict(data.get("assumptions"))
        method = data.get("method_selection") or (data.get("assumptions") or {}).get("method_selection") or "auto"
        return cls(
            company=Company.from_dict(data.get("company")),
            financials=Financials.from_dict(data.get("financials")),
            peers=[Peer.from_dict(p) for p in (data.get("peers") or [])],
            peer_set=list(data.get("peer_set") or []),
            peer_financials=list(data.get("peer_financials") or []),
            peer_market_data=list(data.get("peer_market_data") or []),
            segments=[Segment(**{k: v for k, v in s.items() if k in Segment.__dataclass_fields__})
                      for s in (data.get("segments") or [])],
            segment_evidence=data.get("segment_evidence"),
            assumptions=assumptions,
            method_selection=method,
            relative_multiples=list(data.get("relative_multiples") or []),
            sources=list(data.get("sources") or []),
            market_data=dict(data.get("market_data") or {}),
            meta=dict(data.get("meta") or {}),
            fetch_data=bool(data.get("fetch_data", True)),
            allow_web=bool(data.get("allow_web", True)),
            data_source=str(data.get("data_source") or "auto"),
            web_evidence=data.get("web_evidence"),
            as_of=str(data.get("as_of") or ""),
        )
