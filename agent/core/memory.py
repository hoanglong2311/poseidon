"""AgentBase Memory (long-term facts/rules) via REST.

recall(query) — semantic search records; remember(text) — insert-directly a fact/rule.
Token lấy từ GREENNODE_CLIENT_ID/SECRET (runtime auto-inject; local fallback .greennode.json).
Records dùng chung 1 actor "team" → tri thức/rule chung cho cả đội.
"""
import json
import os
import pathlib
import time

import httpx

MEMORY_BASE = os.getenv("AGENTBASE_MEMORY_URL", "https://agentbase.api.vngcloud.vn/memory")
MEMORY_ID = os.getenv("MEMORY_ID", "")
STRATEGY_ID = os.getenv("MEMORY_STRATEGY_ID", "")
ACTOR = os.getenv("MEMORY_ACTOR_ID", "team")
_IAM_TOKEN_URL = "https://iam.api.vngcloud.vn/accounts-api/v2/auth/token"

_tok = {"v": None, "exp": 0.0}


def enabled() -> bool:
    return bool(MEMORY_ID and STRATEGY_ID)


def _namespace() -> str:
    return f"/strategies/{STRATEGY_ID}/actors/{ACTOR}"


def _creds():
    cid, sec = os.getenv("GREENNODE_CLIENT_ID"), os.getenv("GREENNODE_CLIENT_SECRET")
    if cid and sec:
        return cid, sec
    for p in (".greennode.json", "../.greennode.json", "/app/.greennode.json"):
        try:
            if pathlib.Path(p).is_file():
                d = json.loads(pathlib.Path(p).read_text())
                if d.get("client_id") and d.get("client_secret"):
                    return d["client_id"], d["client_secret"]
        except Exception:
            pass
    return None, None


def _token():
    if _tok["v"] and _tok["exp"] > time.time() + 30:
        return _tok["v"]
    cid, sec = _creds()
    if not (cid and sec):
        return None
    try:
        r = httpx.post(_IAM_TOKEN_URL, auth=(cid, sec),
                       data={"grant_type": "client_credentials"}, timeout=20)
        tok = (r.json() or {}).get("access_token")
        if tok:
            _tok.update(v=tok, exp=time.time() + 3000)  # ~50 phút
        return tok
    except Exception:
        return None


def _records_from(data) -> list[str]:
    items = data if isinstance(data, list) else (
        data.get("listData") or data.get("data") or data.get("results") or [])
    out = []
    for it in items:
        if isinstance(it, dict):
            m = it.get("memory") or it.get("content") or it.get("text")
            if m:
                out.append(m)
    return out


def recall(query: str, limit: int = 5) -> str:
    """Search facts/rules đã lưu; trả về text (rỗng nếu tắt/không có)."""
    if not enabled():
        return ""
    tok = _token()
    if not tok:
        return ""
    try:
        r = httpx.post(
            f"{MEMORY_BASE}/memories/{MEMORY_ID}/memory-records:search",
            params={"namespace": _namespace()},
            json={"query": query, "limit": limit},
            headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        return "\n".join(f"- {m}" for m in _records_from(r.json()))
    except Exception:
        return ""


def remember(text: str) -> bool:
    """Chèn thẳng 1 fact/rule (insert-directly)."""
    if not enabled() or not (text or "").strip():
        return False
    tok = _token()
    if not tok:
        return False
    try:
        r = httpx.post(
            f"{MEMORY_BASE}/memories/{MEMORY_ID}/memory-records:insert-directly",
            params={"namespace": _namespace()},
            json={"memoryRecords": [text.strip()]},
            headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        return r.status_code in (200, 201)
    except Exception:
        return False
