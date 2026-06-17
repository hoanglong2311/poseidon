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
                display_name TEXT,
                authorized INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                action TEXT,
                actor TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS cicd_tracked (
                cicd_key TEXT PRIMARY KEY,
                source_key TEXT,
                status TEXT,
                notified_done INTEGER DEFAULT 0,
                created_at TEXT
            );
            """
        )
        try:  # migrate pre-existing DB
            conn.execute("ALTER TABLE chat_ids ADD COLUMN authorized INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass


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

def set_chat_id(jira_account: str, chat_id: str, display_name: str = "", authorized: int = 1) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO chat_ids (jira_account, chat_id, display_name, authorized)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(jira_account) DO UPDATE SET
                 chat_id=excluded.chat_id, display_name=excluded.display_name,
                 authorized=excluded.authorized""",
            (jira_account, chat_id, display_name, authorized),
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


# --- Zalo chat access (registration-code gated) ---

def touch_chat(chat_id: str, display_name: str = "") -> None:
    """Record a Zalo chat_id on first contact (authorized=0, không clobber nếu đã có)."""
    key = "zalo:" + str(chat_id)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO chat_ids (jira_account, chat_id, display_name, authorized)
               VALUES (?, ?, ?, 0)
               ON CONFLICT(jira_account) DO UPDATE SET display_name=excluded.display_name""",
            (key, chat_id, display_name),
        )


def chat_authorized(chat_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM chat_ids WHERE chat_id=? AND authorized=1 LIMIT 1", (chat_id,)
        ).fetchone()
        return row is not None


def authorize_chat(chat_id: str, display_name: str = "") -> None:
    set_chat_id("zalo:" + str(chat_id), chat_id, display_name, authorized=1)


def authorized_chat_ids() -> list[str]:
    """Distinct chat_ids được phép nhận push (report/alert)."""
    with get_conn() as conn:
        return [r["chat_id"] for r in conn.execute(
            "SELECT DISTINCT chat_id FROM chat_ids WHERE authorized=1")]


# --- audit log (ghi lại hành động write của agent) ---

def audit_add(action: str, actor: str, detail: str = "") -> None:
    """Best-effort — không bao giờ làm hỏng hành động chính nếu audit lỗi."""
    try:
        with get_conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " ts TEXT, action TEXT, actor TEXT, detail TEXT)")
            conn.execute(
                "INSERT INTO audit_log (ts, action, actor, detail) VALUES (?, ?, ?, ?)",
                (_now(), action, actor or "?", detail),
            )
    except Exception:
        pass


def audit_recent(limit: int = 15) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]


# --- CICD ticket lifecycle tracking ---

def track_cicd(cicd_key: str, source_key: str, status: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO cicd_tracked (cicd_key, source_key, status, notified_done, created_at)
               VALUES (?, ?, ?, 0, ?)
               ON CONFLICT(cicd_key) DO UPDATE SET source_key=excluded.source_key""",
            (cicd_key, source_key, status, _now()),
        )


def cicd_open() -> list[dict]:
    """CICD ticket đang theo dõi, chưa báo Done."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cicd_tracked WHERE notified_done=0")]


def update_cicd(cicd_key: str, status: str, notified_done: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE cicd_tracked SET status=?, notified_done=? WHERE cicd_key=?",
            (status, notified_done, cicd_key),
        )


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
