"""年报分部证据的轻量解析。

上游（Agent / D / 使用者）把年报「主营业务分行业、分产品情况」的表格
整理成文本或 CSV 传进来，这里转成 `build_segments` 需要的行结构。

不做 PDF 全文解析——PDF 抽取是 A 的职责；C 只接收**已经定位到分部表**的证据。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path


_NUM = re.compile(r"-?\d[\d,]*\.?\d*%?")


def _num(text: str) -> float | None:
    text = str(text or "").replace(",", "").strip()
    pct = text.endswith("%")
    text = text.rstrip("%")
    try:
        v = float(text)
    except ValueError:
        return None
    return v / 100 if pct else v


def parse_segment_text(text: str, period: str = "") -> list[dict]:
    """解析「分部名 收入 占比 毛利率」这类行。

    容忍两种输入：
      智能家居业务  299,927,239,000  65.71%  29.90%
      智能家居业务  2999.27  65.71  29.90   （单位由调用方说明）
    """
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "分部", "项目", "合计")):
            continue
        nums = _NUM.findall(line)
        if len(nums) < 2:
            continue
        name = _NUM.sub("", line).strip(" \t|:：")
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            continue
        values = [_num(x) for x in nums]
        values = [v for v in values if v is not None]
        if not values:
            continue
        revenue = max(values)
        share = next((v for v in values if 0 < v <= 1), None)
        margin = None
        # 若最后一个数是 0–1 之间且不是 share，视为毛利率
        if len(values) >= 3 and 0 < values[-1] <= 1 and values[-1] != share:
            margin = values[-1]
        rows.append({
            "name": name,
            "level": "top",
            "parent": "",
            "revenue": revenue,
            "gross_margin": margin,
            "gross_profit": (revenue * margin) if margin is not None else None,
            "revenue_share": share,
            "period": period,
            "source": "年报分部证据（文本解析）",
        })
    return rows


def parse_segment_csv(path: str | Path, period: str = "") -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            name = (r.get("分部") or r.get("名称") or r.get("name") or "").strip()
            revenue = _num(r.get("收入") or r.get("营业收入") or r.get("revenue") or "")
            margin = _num(r.get("毛利率") or r.get("gross_margin") or "")
            share = _num(r.get("占比") or r.get("收入比例") or r.get("share") or "")
            if not name or revenue is None:
                continue
            rows.append({
                "name": name,
                "level": "top",
                "parent": "",
                "revenue": revenue,
                "gross_margin": margin,
                "gross_profit": (revenue * margin) if margin is not None else None,
                "revenue_share": share,
                "period": period,
                "source": f"年报分部证据（{path.name}）",
            })
    return rows


def rows_from_evidence(evidence: dict | None) -> tuple[list[dict], str]:
    """从 segment_evidence 里取行：rows / text / csv_path 三种。"""
    if not evidence:
        return [], ""
    if evidence.get("rows"):
        return list(evidence["rows"]), evidence.get("source_text") or "证据包"
    if evidence.get("text"):
        rows = parse_segment_text(evidence["text"], evidence.get("period", ""))
        return rows, "年报分部证据（文本）"
    if evidence.get("csv_path"):
        rows = parse_segment_csv(evidence["csv_path"], evidence.get("period", ""))
        return rows, f"年报分部证据（{Path(evidence['csv_path']).name}）"
    return [], ""
