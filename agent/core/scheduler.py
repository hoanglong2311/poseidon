"""APScheduler jobs (ADR 0010): 30-min Jira sync + reports at 09:00 and 17:30.

Single replica (min=max=1) → no cron double-fire. Push via Notifier (Zalo default).
"""
import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from . import store, notifier
from .jira_client import team_jql, search_jira, is_urgent
from .classifier import classify_ticket
from .report import build_report, build_report_plain

log = logging.getLogger("poseidon.scheduler")
TZ = os.getenv("TZ", "Asia/Ho_Chi_Minh")
_scheduler: BackgroundScheduler | None = None


def run_sync() -> dict:
    """Poll Jira → upsert SQLite → push Zalo for NEW urgent tickets (deduped)."""
    try:
        tickets = search_jira(team_jql())
    except Exception as e:
        log.warning("sync poll failed: %s", e)
        return {"polled": 0, "error": str(e)}

    for t in tickets:
        store.upsert_ticket(t)

    urgent_keys = [t["key"] for t in tickets if is_urgent(t.get("priority"))]
    alerted = 0
    for t in store.unalerted_by_keys(urgent_keys):
        chat_id = store.get_chat_id(t.get("assignee_id") or "")
        text = (
            f"🔴 Ticket URGENT mới cho bạn:\n[{t['key']}] {t.get('summary','')}\n"
            f"Priority: {t.get('priority')} · Status: {t.get('status')}"
        )
        if chat_id and notifier.send(chat_id, text):
            alerted += 1
        store.mark_alerted(t["key"])  # dedupe regardless of send result
    log.info("sync: polled=%d urgent_alerted=%d", len(tickets), alerted)
    return {"polled": len(tickets), "alerted": alerted}


def run_report(kind: str = "daily") -> dict:
    """Re-poll + classify unclassified → build report → store → push per member."""
    try:
        for t in search_jira(team_jql()):
            store.upsert_ticket(t)
    except Exception as e:
        log.warning("report poll failed: %s", e)

    # Classify unclassified tickets CONCURRENTLY (each is a blocking LLM call) —
    # sequential was the main cause of slow /report now.
    unclassified = store.unclassified_tickets()
    classified = 0
    if unclassified:
        from concurrent.futures import ThreadPoolExecutor

        def _one(t):
            return t["key"], classify_ticket(t)

        with ThreadPoolExecutor(max_workers=min(8, len(unclassified))) as ex:
            for key, c in ex.map(_one, unclassified):
                store.set_classification(key, c["complexity"], c["risk"], c["reason"])
                classified += 1

    # Store the markdown-table version for Chainlit /report; push the plain version to Zalo.
    store.store_report(kind, build_report(kind))
    plain = build_report_plain(kind)

    pushed = 0
    seen = set()
    for row in store.all_chat_ids():
        cid = row["chat_id"]
        if cid in seen:
            continue
        seen.add(cid)
        if notifier.send(cid, plain):
            pushed += 1
    log.info("report(%s): classified=%d pushed=%d", kind, classified, pushed)
    return {"classified": classified, "pushed": pushed}


def _sync_job():
    run_sync()


def _report_job(kind: str):
    run_report(kind)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone=TZ)
    # Run an initial sync right away so the bot has data immediately on boot,
    # then every 30 minutes.
    sched.add_job(_sync_job, "interval", minutes=30, id="sync", next_run_time=datetime.now())
    sched.add_job(_report_job, "cron", hour=9, minute=0, args=["morning"], id="report_am")
    sched.add_job(_report_job, "cron", hour=17, minute=30, args=["evening"], id="report_pm")
    sched.start()
    _scheduler = sched
    return sched
