"""FinScope 估值引擎。

三法方法论取自 finance-skills 的 company-valuation（MIT），
适配了 A 股参数口径，并接上了原两个交付包的 Excel 底稿渲染能力。
"""
from .models import (  # noqa: F401
    Assumptions,
    Company,
    Financials,
    Peer,
    SotpSegment,
    ValuationInput,
)
from . import fusion, methods  # noqa: F401

__all__ = [
    "Assumptions", "Company", "Financials", "Peer", "SotpSegment", "ValuationInput",
    "fusion", "methods", "run",
]


def run(payload: dict) -> dict:
    """对外统一入口：吃一个 dict，吐一个 dict。

    这是 D 的总集成要调的那个函数——不需要理解任何 Python 对象。
    """
    data = ValuationInput.from_dict(payload)
    return fusion.value(
        company=data.company,
        fin=data.financials,
        peers=data.peers,
        asm=data.assumptions,
        segments=data.sotp_segments,
        multiples=data.relative_multiples,
        sources=data.sources,
    )
