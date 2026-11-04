"""FinScope 估值模块 HTTP 服务。

启动（在 valuation 的上一级目录）：
    python -m valuation.api.server
或：
    uvicorn valuation.api.server:app --host 127.0.0.1 --port 8010

端点：
    POST /api/valuation/questions              交互式对话框的问题清单
    POST /api/valuation/session                创建估值会话
    PATCH /api/valuation/session/{id}/inputs   补充/修改假设、同业、分部
    POST /api/valuation/session/{id}/run       运行估值（取数 → 假设 → 方法 → 融合 → Excel）
    POST /api/valuation/session/{id}/recalculate 改假设后重算（不重新取数）
    GET  /api/valuation/session/{id}/result    取结果
    GET  /api/valuation/session/{id}/excel     下载 Excel 底稿
    POST /api/valuation/run                    无状态运行（给 D 的总集成调用）
    POST /api/valuation/upload                 上传年报 PDF，解析成证据包
    POST /api/valuation/assistant              AI 研究助手（规则 / 可选 LLM）
    GET  /api/valuation/assistant/config       助手模型配置状态
    GET  /                                    跳转估值实验室页面
    GET  /ui/valuation_lab.html               前端估值实验室
    GET  /api/valuation/health                 自检
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from valuation.api import assistant as assistant_mod

from valuation import next_questions, run
from valuation.core import defaults
from valuation.core.engine import _history_block
from valuation.core.models import Financials
from valuation.data import akshare_provider as ak
from valuation.data import official_provider as official
from valuation.data import web_provider as web

SESSION_DIR = ROOT / "output" / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = Lock()

app = FastAPI(title="FinScope Valuation API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")


@app.get("/")
def root():
    return RedirectResponse(url="/ui/valuation_lab.html")


class SessionCreate(BaseModel):
    ticker: str
    market: str = "A"
    method_selection: str = "auto"
    data_source: str = "auto"
    assumptions: dict = Field(default_factory=dict)
    peers: list[dict] = Field(default_factory=list)
    peer_set: list[str] = Field(default_factory=list)
    segments: list[dict] = Field(default_factory=list)
    web_evidence: dict | None = None
    inputs: dict = Field(default_factory=dict)


class InputsUpdate(BaseModel):
    method_selection: str | None = None
    data_source: str | None = None
    assumptions: dict | None = None
    peers: list[dict] | None = None
    peer_set: list[str] | None = None
    segments: list[dict] | None = None
    web_evidence: dict | None = None
    weights: dict | None = None


class EvidenceRequest(BaseModel):
    ticker: str
    name: str = ""
    years: list[int] | None = None
    max_reports: int = 3


class AssistantRequest(BaseModel):
    session_id: str
    message: str
    history: list[dict] = Field(default_factory=list)


class SearchRequest(BaseModel):
    session_id: str
    query: str
    history: list[dict] = Field(default_factory=list)


class RunRequest(BaseModel):
    payload: dict
    export_excel: bool = True


def _session_path(sid: str) -> Path:
    return SESSION_DIR / f"{sid}.json"


def _load(sid: str) -> dict:
    path = _session_path(sid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="会话不存在")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(sid: str, data: dict) -> None:
    _session_path(sid).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str),
                                  encoding="utf-8")


def _payload_from_session(s: dict) -> dict:
    """ABC canonical 统一对象优先；会话的改动只覆盖估值参数，不更改 A 的财务值。"""
    # inputs 可能是 D 传入的完整 unified 对象，也可能是空字典。
    upstream = s.get("inputs") or {}
    upstream = upstream.get("unified", upstream) if isinstance(upstream, dict) else {}
    payload = dict(upstream)
    company = dict(payload.get("company") or {})
    company.setdefault("ticker", s["ticker"])
    company.setdefault("market", s["market"])
    payload["company"] = company
    payload.update({
        "method_selection": s.get("method_selection") or "auto",
        "assumptions": {**(payload.get("assumptions") if isinstance(payload.get("assumptions"), dict) else {}),
                        **(s.get("assumptions") or {})},
    })
    is_canonical = isinstance(payload.get("financials"), (dict, list)) and bool(payload.get("financials"))
    payload["data_source"] = "canonical" if is_canonical else (s.get("data_source") or "auto")
    payload["fetch_data"] = not is_canonical and s.get("fetch_data", True)
    if s.get("peers"):
        payload["peers"] = s["peers"]
    if s.get("peer_set"):
        payload["peer_set"] = s["peer_set"]
    if s.get("segments"):
        payload["segments"] = s["segments"]
    if s.get("web_evidence"):
        payload["web_evidence"] = s["web_evidence"]
    # 行情绝不由 C 覆盖：D 的 market_data 不被会话重新读取。
    return payload


@app.get("/api/valuation/health")
def health():
    import importlib
    mods = {}
    for m in ("akshare", "pandas", "numpy", "artifact_tool", "fastapi"):
        try:
            mods[m] = getattr(importlib.import_module(m), "__version__", "ok")
        except Exception:  # noqa: BLE001
            mods[m] = None
    return {"ok": True, "version": "3.0.0", "modules": mods,
            "themes": len(defaults.industry_peers().get("themes", {})),
            "data_sources": official.probe_all(),
            "assistant": assistant_mod.llm_config()}


@app.post("/api/valuation/questions")
def questions(payload: dict):
    payload = payload or {}
    if "ticker" in payload and "company" not in payload:
        payload = {"company": {"ticker": payload["ticker"], "market": payload.get("market", "A")}}
    return next_questions(payload)


@app.get("/api/valuation/industries")
def industries():
    cfg = defaults.industry_peers()
    return {
        "themes": [
            {"theme": name, "sector": (v or {}).get("sector"),
             "peers": (v or {}).get("peers")}
            for name, v in (cfg.get("themes") or {}).items()
        ],
        "gates": defaults.sector_params().get("industry_gates"),
    }


@app.get("/api/valuation/companies/{ticker}/segments")
def company_segments(ticker: str):
    return ak.fetch_segments(ticker)


@app.get("/api/valuation/companies/{ticker}/peer-research")
def company_peer_research(ticker: str, as_of: str = ""):
    from valuation.research.peer_registry import research
    return research(ticker, as_of=as_of or None)


@app.get("/api/valuation/companies/{ticker}/peers")
def company_peers(ticker: str):
    data = ak.fetch_company(ticker)
    if not data.get("ok"):
        raise HTTPException(status_code=502, detail=data.get("error"))
    from valuation.core.models import Company, Financials
    from valuation.data.peer_selector import select_peers
    company = Company(ticker=ticker, market="A", name=data.get("name"),
                      industry=data.get("industry", ""))
    fin = Financials.from_dict(data["financials"])
    sel = select_peers(company, fin)
    # Peer 对象转 dict
    out = dict(sel)
    out["peers"] = [p.to_dict() for p in sel.get("peers") or []]
    return out


@app.get("/api/valuation/companies/search")
def search_companies(q: str, limit: int = 10):
    """股票代码 / 公司简称 → 候选公司。"""
    results = ak.search_companies(q, limit=limit)
    return {"ok": bool(results), "query": q, "results": results}


@app.get("/api/valuation/companies/{ticker}/data")
def company_data(ticker: str):
    """读取一家公司的完整财务、行情、分部与来源，供估值前预览。"""
    data = ak.fetch_company(ticker, "A")
    if not data.get("ok"):
        raise HTTPException(status_code=502, detail=data.get("error") or "取数失败")
    fin = Financials.from_dict(data.get("financials") or {})
    seg = ak.fetch_segments(ticker)
    sources = list(data.get("sources") or [])
    if seg.get("ok") and seg.get("source"):
        sources.append(seg["source"])
    return {
        "ok": True,
        "company": {
            "name": data.get("name") or ticker,
            "ticker": data.get("code") or ticker,
            "market": "A",
            "currency": "CNY",
            "industry": data.get("industry") or "",
            "report_period": f"{fin.years[-1]}-12-31" if fin.years else "",
        },
        "financials": data.get("financials") or {},
        "history": _history_block(fin),
        "segments": seg.get("rows") or [],
        "sources": sources,
        "warnings": data.get("warnings") or [],
        "market_data": {
            "price": fin.price,
            "shares_outstanding": fin.shares_outstanding,
            "market_cap": fin.market_cap,
            "price_date": fin.price_date,
            "price_source": fin.price_source,
        },
    }


@app.post("/api/valuation/evidence/search")
def search_evidence(body: EvidenceRequest):
    """联网搜索 + 年报 PDF 解析，返回证据包（不直接估值）。"""
    name = body.name
    if not name:
        info = ak.company_info(body.ticker)
        name = info.get("name") or body.ticker
    result = web.gather_company(name, body.ticker, years=body.years,
                                max_reports=body.max_reports)
    result["ticker"] = body.ticker
    result["name"] = name
    return result


@app.get("/api/valuation/sources/probe")
def probe_sources():
    return official.probe_all()


@app.get("/api/valuation/assistant/config")
def assistant_config():
    return assistant_mod.llm_config()


@app.post("/api/valuation/search")
def valuation_search(body: SearchRequest):
    """估值搜索：联网检索 + 当前估值结果 → DeepSeek/规则回答。"""
    s = _load(body.session_id)
    result = s.get("result")
    if not result:
        payload = _payload_from_session(s)
        result = run(payload, export_excel=False)
        s["result"] = result
        with _LOCK:
            _save(body.session_id, s)
    search = {"ok": False, "results": [], "error": ""}
    try:
        search = web.search(body.query, max_results=6)
    except Exception as exc:  # noqa: BLE001
        search = {"ok": False, "results": [], "error": f"{type(exc).__name__}: {exc}"}
    results = search.get("results") or []
    if not results:
        # 通用搜索不可用时，退回巨潮资讯最新公告（结构化、稳定）
        try:
            results = web.company_announcements(s.get("ticker") or "", limit=8)
            if results:
                search["engine"] = "巨潮资讯"
        except Exception as exc:  # noqa: BLE001
            search["error"] = f"{search.get('error') or ''}；公告检索：{type(exc).__name__}: {exc}"
    answer = assistant_mod.answer_search_llm(result, body.query, results, body.history)
    cfg = assistant_mod.llm_config()
    if not answer:
        base = assistant_mod.answer_with_rules(
            result, body.query, {"action": "answer", "changes": {}}, None)
        if results:
            base += "\n\n【联网检索】\n" + "\n".join(
                f"- {r.get('title','')}：{r.get('snippet','')[:160]}"
                for r in results[:5]
            )
        else:
            base += "\n\n【联网检索】本次未取得搜索结果（可配置 TAVILY_API_KEY / SERPAPI_KEY 提高稳定性）。"
        answer = base
    return {
        "answer": answer,
        "search_results": results,
        "search_engine": search.get("engine") or "",
        "search_error": search.get("error") or "",
        "llm_connected": cfg.get("connected", False),
        "provider": cfg.get("provider", "规则助手"),
    }


@app.post("/api/valuation/upload")
async def upload_report(file: UploadFile = File(...), report_year: int = Form(2025)):
    """上传年报 PDF，解析成 financials / segments 证据包。"""
    content = await file.read()
    if len(content) > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF 超过 60MB，请压缩后再上传")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持 PDF 年报")
    upload_dir = SESSION_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (file.filename or "report.pdf"))
    path = upload_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    path.write_bytes(content)
    parsed = web.parse_annual_report(path, int(report_year))
    if not parsed.get("ok"):
        raise HTTPException(status_code=422, detail=f"PDF 解析失败：{parsed.get('error') or '未抽到报表'}")
    from valuation.data.web_provider import _merge_year_data
    financials = _merge_year_data(parsed.get("years") or {})
    return {
        "ok": True,
        "filename": file.filename,
        "pdf_path": str(path),
        "report_year": int(report_year),
        "financials": financials,
        "segments": parsed.get("segments") or [],
        "warnings": [],
        "sources": [{"name": f"上传年报·{file.filename}", "purpose": "财务报表/分部",
                     "as_of": f"{int(report_year)}-12-31", "official": True,
                     "note": str(path)}],
    }


@app.post("/api/valuation/assistant")
def assistant_chat(body: AssistantRequest):
    """AI 研究助手：解释结果 / 按自然语言改假设 / 重选同业。"""
    s = _load(body.session_id)
    old_result = s.get("result")
    result = old_result
    if not result:
        payload = _payload_from_session(s)
        result = run(payload, export_excel=False)
        s["result"] = result
        s["status"] = result.get("status")
        with _LOCK:
            _save(body.session_id, s)
    intent = assistant_mod.extract_intent(body.message)
    changed = False
    if intent.get("changes"):
        s["assumptions"] = {**(s.get("assumptions") or {}), **intent["changes"]}
        changed = True
    if intent.get("action") == "reselect_peers":
        s["peers"] = []
        s["peer_set"] = intent.get("peers") or []
        changed = True
    if changed:
        payload = _payload_from_session(s)
        xlsx = SESSION_DIR / f"{body.session_id}_估值底稿.xlsx"
        # Chat edits recalculate immediately; XLSX is generated only when downloaded.
        result = run(payload, export_excel=False)
        s["result"] = result
        s["excel_path"] = None
        s["status"] = result.get("status")
        with _LOCK:
            _save(body.session_id, s)

    answer = assistant_mod.answer_with_llm(result, body.message, body.history)
    llm_used = bool(answer)
    if not answer:
        answer = assistant_mod.answer_with_rules(
            result, body.message, intent,
            previous=old_result if changed else None,
        )
    return {
        "answer": answer,
        "result": result,
        "intent": intent,
        "changed": changed,
        "llm_connected": assistant_mod.llm_config().get("connected", False),
        "llm_used": llm_used,
    }


@app.post("/api/valuation/from-workflow")
def from_workflow(payload: dict):
    """给小组 D 统一编排：接受完整 canonical，不在 C 重新取数/股价。"""
    if not isinstance(payload.get("financials"), (dict, list)):
        raise HTTPException(status_code=422, detail="缺少 ABC 统一对象 financials")
    actual = {**payload, "fetch_data": False, "data_source": "canonical"}
    result = run(actual, export_excel=False)
    return {"valuation": result, "status": result.get("status")}


@app.post("/api/valuation/session")
def create_session(body: SessionCreate):
    sid = uuid.uuid4().hex[:12]
    session = {
        "id": sid,
        "ticker": body.ticker,
        "market": body.market,
        "method_selection": body.method_selection,
        "data_source": body.data_source,
        "assumptions": body.assumptions or {},
        "peers": body.peers or [],
        "peer_set": body.peer_set or [],
        "segments": body.segments or [],
        "web_evidence": body.web_evidence,
        "inputs": body.inputs or {},
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "created",
        "result": None,
        "excel_path": None,
    }
    with _LOCK:
        _save(sid, session)
    # 仅当 D 已经注入统一财务对象时提供问题清单；避免创建会话重复联网取价。
    if isinstance((session.get("inputs") or {}).get("financials"), dict):
        try:
            q = next_questions(_payload_from_session(session))
        except Exception as exc:  # noqa: BLE001
            q = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        q = {"status": "pending", "note": "首轮运行后显示行业假设与待回答问题"}
    return {"session_id": sid, "state": session, "questions": q}


@app.get("/api/valuation/session/{sid}")
def get_session(sid: str):
    return _load(sid)


@app.patch("/api/valuation/session/{sid}/inputs")
def update_inputs(sid: str, body: InputsUpdate):
    with _LOCK:
        s = _load(sid)
        if body.method_selection is not None:
            s["method_selection"] = body.method_selection
        if body.data_source is not None:
            s["data_source"] = body.data_source
        if body.assumptions is not None:
            s["assumptions"] = {**(s.get("assumptions") or {}), **body.assumptions}
        if body.peers is not None:
            s["peers"] = body.peers
        if body.peer_set is not None:
            s["peer_set"] = body.peer_set
            s["peers"] = []          # 强制按新名单/自动池重选
        if body.segments is not None:
            s["segments"] = body.segments
        if body.web_evidence is not None:
            s["web_evidence"] = body.web_evidence
        if body.weights is not None:
            s["assumptions"]["weights"] = body.weights
            s["assumptions"]["weight_mode"] = "manual"
        s["status"] = "inputs_updated"
        _save(sid, s)
    return {"session_id": sid, "state": s}


@app.post("/api/valuation/session/{sid}/run")
def run_session(sid: str, export_excel: bool = False):
    with _LOCK:
        s = _load(sid)
    payload = _payload_from_session(s)
    xlsx = SESSION_DIR / f"{sid}_估值底稿.xlsx"
    try:
        result = run(payload, export_excel=export_excel, excel_path=str(xlsx))
    except Exception as exc:  # noqa: BLE001
        s["status"] = "failed"
        s["error"] = f"{type(exc).__name__}: {exc}"
        with _LOCK:
            _save(sid, s)
        raise HTTPException(status_code=500, detail=s["error"])
    s["status"] = result.get("status")
    s["result"] = result
    s["excel_path"] = result.get("excel_path")
    s["run_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with _LOCK:
        _save(sid, s)
    return result


@app.post("/api/valuation/session/{sid}/recalculate")
def recalculate(sid: str, body: InputsUpdate | None = None):
    force_peers = body is not None and body.peer_set is not None
    with _LOCK:
        s = _load(sid)
        if body:
            if body.method_selection is not None:
                s["method_selection"] = body.method_selection
            if body.data_source is not None:
                s["data_source"] = body.data_source
            if body.assumptions is not None:
                s["assumptions"] = {**(s.get("assumptions") or {}), **body.assumptions}
            if body.peers is not None:
                s["peers"] = body.peers
            if body.peer_set is not None:
                s["peer_set"] = body.peer_set
                s["peers"] = []
            if body.segments is not None:
                s["segments"] = body.segments
            if body.web_evidence is not None:
                s["web_evidence"] = body.web_evidence
            if body.weights is not None:
                s["assumptions"]["weights"] = body.weights
                s["assumptions"]["weight_mode"] = "manual"
        payload = _payload_from_session(s)
        # 重算走本地缓存（财报/行情 12 小时、同业 12 小时），通常秒级返回；
        # 不把上次结果里的财务数组塞回 payload，避免口径漂移。
        prev = s.get("result") or {}
        if prev and not payload.get("peers") and not payload.get("peer_set") and not force_peers:
            peers = (prev.get("comps") or {}).get("peers_detail") or []
            if peers:
                payload["peers"] = peers
        xlsx = SESSION_DIR / f"{sid}_估值底稿.xlsx"
        # Avoid a costly workbook re-export for each assumption change.
        result = run(payload, export_excel=False)
        s["status"] = result.get("status")
        s["result"] = result
        s["excel_path"] = None
        _save(sid, s)
    return result


@app.get("/api/valuation/session/{sid}/result")
def session_result(sid: str):
    s = _load(sid)
    if not s.get("result"):
        raise HTTPException(status_code=404, detail="尚未运行估值")
    return s["result"]


@app.get("/api/valuation/session/{sid}/excel")
def session_excel(sid: str):
    """Generate the workbook from the same saved calculation, only on demand.

    An assumption edit invalidates prior Excel exports; the new file is never
    generated from stale results nor requires a second data-fetch/valuation.
    """
    with _LOCK:
        s = _load(sid)
        result = s.get("result")
        if not result:
            raise HTTPException(status_code=404, detail="尚未运行估值，无可导出的 Excel 结果")
        path = s.get("excel_path")
        if not path or not Path(path).exists():
            xlsx = SESSION_DIR / f"{sid}_估值底稿.xlsx"
            try:
                from valuation.export import institutional as excel_export
                excel_export.render(result, xlsx)
                result["excel_format"] = "professional_18_sheets"
            except Exception as exc:  # noqa: BLE001
                try:
                    from valuation.export import excel as fallback_export
                    fallback_export.render(result, xlsx)
                    result["excel_format"] = "legacy_12_sheets"
                    result.setdefault("warnings", []).append(
                        "18 表专业底稿不可用，已回退兼容格式：" + type(exc).__name__)
                except Exception as fallback_exc:  # noqa: BLE001
                    raise HTTPException(status_code=500, detail=(
                        "Excel 导出失败：" + type(fallback_exc).__name__))
            path = str(xlsx)
            result["excel_path"] = path
            s["result"] = result
            s["excel_path"] = path
            _save(sid, s)
    ticker = s.get("ticker") or "valuation"
    return FileResponse(path, filename=f"{ticker}_估值底稿.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/valuation/run")
def run_stateless(body: RunRequest):
    xlsx = ROOT / "output" / f"api_{int(time.time())}_估值底稿.xlsx"
    result = run(body.payload, export_excel=body.export_excel, excel_path=str(xlsx))
    return result


def main():
    import uvicorn
    uvicorn.run("valuation.api.server:app", host="127.0.0.1", port=8010, reload=False)


if __name__ == "__main__":
    main()
