"""Ticket classification via Qwen 3.5 27B.

complexity & risk = Low/Medium/High + 1-line reason (Vietnamese). PIC = existing
Jira assignee (bot does not reassign).
"""
import json
import re

from .llm import classify_llm, strip_think

LEVELS = ("Low", "Medium", "High")

_SYSTEM = (
    "Bạn là trợ lý phân loại ticket hỗ trợ kỹ thuật cho team ZaloPay. "
    "Với mỗi ticket, chấm 'complexity' (độ phức tạp xử lý) và 'risk' (rủi ro ảnh hưởng) "
    "theo thang Low/Medium/High, kèm 'reason' là MỘT câu ngắn tiếng Việt giải thích. "
    'Chỉ trả về JSON thuần: {"complexity":"...","risk":"...","reason":"..."} — không thêm chữ nào khác.'
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _coerce_level(v: str) -> str:
    v = (v or "").strip().lower()
    for lvl in LEVELS:
        if lvl.lower() in v:
            return lvl
    return "Medium"


def classify_ticket(ticket: dict) -> dict:
    """Return {"complexity", "risk", "reason"}; safe defaults on parse failure."""
    user = (
        f"Ticket {ticket.get('key')}:\n"
        f"- Tiêu đề: {ticket.get('summary')}\n"
        f"- Trạng thái: {ticket.get('status')}\n"
        f"- Priority: {ticket.get('priority')}\n"
        f"- Project: {ticket.get('project')}\n"
        f"- Mô tả: {(ticket.get('description') or '')[:1500]}"
    )
    try:
        msg = classify_llm().invoke(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]
        )
        text = strip_think(msg.content if hasattr(msg, "content") else str(msg))
        m = _JSON_RE.search(text)
        data = json.loads(m.group(0)) if m else {}
    except Exception as e:
        data = {"reason": f"(không phân loại được: {e})"}
    return {
        "complexity": _coerce_level(data.get("complexity")),
        "risk": _coerce_level(data.get("risk")),
        "reason": (data.get("reason") or "").strip()[:200],
    }
