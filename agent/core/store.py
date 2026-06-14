"""SQLite state store: synced tickets, pre-computed reports, alert dedup, chat_id map."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "poseidon.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                key TEXT PRIMARY KEY,
                project TEXT,
                summary TEXT,
                status TEXT,
                assignee TEXT,
                assignee_id TEXT,
                priority TEXT,
                complexity TEXT,
                risk TEXT,
                reason TEXT,
                alerted INTEGER DEFAULT 0,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                body TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_ids (
                jira_account TEXT PRIMARY KEY,
                chat_id TEXT,
                display_name TEXT
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- tickets ---

def upsert_ticket(t: dict) -> None:
    """Insert/update a ticket; preserves existing classification + alerted flag."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tickets (key, project, summary, status, assignee, assignee_id,
                                 priority, updated_at)
            VALUES (:key, :project, :summary, :status, :assignee, :assignee_id,
                    :priority, :updated_at)
            ON CONFLICT(key) DO UPDATE SET
                project=excluded.project, summary=excluded.summary,
                status=excluded.status, assignee=excluded.assignee,
                assignee_id=excluded.assignee_id, priority=excluded.priority,
                updated_at=excluded.updated_at
            """,
            {**t, "updated_at": _now()},
        )


def set_classification(key: str, complexity: str, risk: str, reason: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tickets SET complexity=?, risk=?, reason=? WHERE key=?",
            (complexity, risk, reason, key),
        )


def mark_alerted(key: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE tickets SET alerted=1 WHERE key=?", (key,))


def all_tickets() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY updated_at DESC")]


def unclassified_tickets() -> list[dict]:
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute("SELECT * FROM tickets WHERE complexity IS NULL")
        ]


def unalerted_by_keys(keys: list[str]) -> list[dict]:
    """Return tickets among `keys` that have not yet been alerted."""
    if not keys:
        return []
    qmarks = ",".join("?" * len(keys))
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM tickets WHERE alerted=0 AND key IN ({qmarks})", keys
            )
        ]


# --- reports ---

def store_report(kind: str, body: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reports (kind, body, created_at) VALUES (?, ?, ?)",
            (kind, body, _now()),
        )


def latest_report() -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT body FROM reports ORDER BY id DESC LIMIT 1").fetchone()
        return row["body"] if row else None


# --- chat_id map (jira_account -> notifier chat_id) ---

def set_chat_id(jira_account: str, chat_id: str, display_name: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO chat_ids (jira_account, chat_id, display_name)
               VALUES (?, ?, ?)
               ON CONFLICT(jira_account) DO UPDATE SET
                 chat_id=excluded.chat_id, display_name=excluded.display_name""",
            (jira_account, chat_id, display_name),
        )


def get_chat_id(jira_account: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT chat_id FROM chat_ids WHERE jira_account=?", (jira_account,)
        ).fetchone()
        return row["chat_id"] if row else None


def all_chat_ids() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM chat_ids")]


def seed_chat_ids_from_env() -> int:
    """Seed the chat_ids map from SEED_CHAT_IDS env (JSON) so the mapping survives
    a fresh container (SQLite is ephemeral). Format:
      {"<jira_account_id>": "<chat_id>"}  or
      {"<jira_account_id>": {"chat_id": "...", "name": "..."}}
    """
    import json
    raw = os.getenv("SEED_CHAT_IDS", "").strip()
    if not raw:
        return 0
    try:
        data = json.loads(raw)
    except Exception:
        return 0
    n = 0
    for account, val in (data or {}).items():
        if isinstance(val, dict):
            chat_id, name = val.get("chat_id", ""), val.get("name", "")
        else:
            chat_id, name = str(val), ""
        if account and chat_id:
            set_chat_id(account, chat_id, name)
            n += 1
    return n
