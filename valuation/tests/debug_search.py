import requests

base = "http://127.0.0.1:8010"
s = requests.post(base + "/api/valuation/session", json={
    "ticker": "600519", "market": "A", "method_selection": "auto", "data_source": "auto"}).json()
sid = s["session_id"]
requests.post(base + f"/api/valuation/session/{sid}/run").json()
r = requests.post(base + "/api/valuation/search", json={
    "session_id": sid, "query": "这家公司最近公告和行业估值情况", "history": []}, timeout=120)
print(r.status_code)
j = r.json()
print("provider", j.get("provider"), "llm", j.get("llm_connected"),
      "sources", len(j.get("search_results") or []))
print(j.get("answer", "")[:300])
