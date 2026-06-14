"""Build the triage report from synced SQLite state.

- build_report: markdown TABLE (đẹp trên Chainlit /report).
- build_report_plain: text gọn theo nhóm PIC (cho Zalo — không render bảng md).
- build_member_report: bản cá nhân (hiện không dùng cho push, giữ lại nếu cần).
"""
from collections import Counter, defaultdict

from . import store
from .jira_client import is_urgent

_HEADERS = {
    "morning": "☀️ Báo cáo Jira Triage — đầu ngày",
    "evening": "🌙 Báo cáo Jira Triage — cuối ngày",
}


def _header(kind: str) -> str:
    return _HEADERS.get(kind, "📋 Báo cáo Jira Triage")


def _stats_line(tickets: list[dict]) -> str:
    urgent = sum(1 for t in tickets if is_urgent(t.get("priority")))
    by_status = Counter(t.get("status") or "?" for t in tickets)
    status = " · ".join(f"{k}={v}" for k, v in by_status.items())
    return f"**{len(tickets)} ticket** · 🔴 urgent: {urgent}\nTrạng thái: {status}"


def _cell(s: str, n: int = 48) -> str:
    s = (s or "").replace("|", "¦").replace("\n", " ").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


def build_report(kind: str = "daily") -> str:
    """Markdown table — render đẹp trên Chainlit."""
    tickets = store.all_tickets()
    if not tickets:
        return "Chưa có ticket nào được sync. (Scheduler poll mỗi 30 phút.)"

    rows = [
        "| Key | Tiêu đề | Trạng thái | PIC | Phức tạp | Rủi ro |",
        "|-----|---------|------------|-----|:--------:|:------:|",
    ]
    for t in sorted(tickets, key=lambda x: ((x.get("assignee") or "~"), x.get("key") or "")):
        key = ("🔴 " if is_urgent(t.get("priority")) else "") + (t.get("key") or "")
        rows.append(
            f"| {key} | {_cell(t.get('summary'))} | {t.get('status','?')} | "
            f"{_cell(t.get('assignee') or '(chưa assign)', 22)} | "
            f"{t.get('complexity') or '—'} | {t.get('risk') or '—'} |"
        )
    return f"{_header(kind)}\n\n{_stats_line(tickets)}\n\n" + "\n".join(rows)


def build_report_plain(kind: str = "daily") -> str:
    """Text gọn theo nhóm PIC — cho Zalo (không có bảng markdown)."""
    tickets = store.all_tickets()
    if not tickets:
        return "Chưa có ticket nào được sync."

    urgent = sum(1 for t in tickets if is_urgent(t.get("priority")))
    by_status = Counter(t.get("status") or "?" for t in tickets)
    out = [
        _header(kind),
        f"Tổng: {len(tickets)} ticket · 🔴 urgent: {urgent}",
        "Trạng thái: " + " · ".join(f"{k}={v}" for k, v in by_status.items()),
        "",
    ]
    by_pic = defaultdict(list)
    for t in tickets:
        by_pic[t.get("assignee") or "(chưa assign)"].append(t)
    for pic, items in sorted(by_pic.items(), key=lambda kv: -len(kv[1])):
        out.append(f"👤 {pic} ({len(items)})")
        for t in items:
            tag = "🔴 " if is_urgent(t.get("priority")) else ""
            cr = f"C:{t.get('complexity') or '—'}/R:{t.get('risk') or '—'}"
            out.append(f"  • {tag}{t.get('key')} · {t.get('summary','')} · {t.get('status','?')} · {cr}")
        out.append("")
    return "\n".join(out).strip()


def build_member_report(assignee_id: str, display_name: str = "") -> str:
    """Bản cá nhân (chỉ ticket của 1 người) — giữ lại nếu muốn push per-member."""
    tickets = [t for t in store.all_tickets() if t.get("assignee_id") == assignee_id]
    if not tickets:
        return ""
    name = display_name or (tickets[0].get("assignee") or "bạn")
    out = [f"📋 Chào {name}, bạn có {len(tickets)} ticket:", ""]
    for t in tickets:
        tag = "🔴 " if is_urgent(t.get("priority")) else ""
        cr = f"C:{t.get('complexity') or '—'}/R:{t.get('risk') or '—'}"
        line = f"{tag}{t.get('key')} · {t.get('summary','')} · {t.get('status','?')} · {cr}"
        if t.get("reason"):
            line += f"\n    ↳ {t['reason']}"
        out.append(line)
    return "\n".join(out).strip()
