"""FinScope 估值模块 v2。

用法：
    from valuation import run
    result = run({"company": {"ticker": "600519", "market": "A"}})
"""
from .core.engine import next_questions, run
from .core.models import Assumptions, Company, Financials, Peer, Segment, ValuationInput

__all__ = ["run", "next_questions", "ValuationInput", "Company", "Financials",
           "Peer", "Segment", "Assumptions"]
__version__ = "2.1.0"
