"""Notifier abstraction (ADR 0010): one `send(chat_id, text)` over swappable backends.

Zalo (default, PRIVATE 1-1) + Telegram (fallback). The two bot APIs are near-identical
clones, so a single payload shape works for both. Push-only — no webhook needed.

Endpoints/tokens are configurable. Zalo base defaults to https://bot-api.zapps.me
(the host used by scripts/zalo-bot-test.mjs — verified working), NOT the
bot-api.zaloplatforms.com host shown in some docs.
"""
import os
import httpx

BACKEND = os.getenv("NOTIFY_BACKEND", "zalo").lower()

ZALO_BASE = os.getenv("ZALO_BASE_URL", "https://bot-api.zapps.me").rstrip("/")
TELEGRAM_BASE = os.getenv("TELEGRAM_BASE_URL", "https://api.telegram.org").rstrip("/")

# Accept both naming conventions for the token.
ZALO_TOKEN = os.getenv("ZALO_BOT_TOKEN") or os.getenv("BOT_ZALO_TOKEN") or ""
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TELEGRAM_TOKEN") or ""


def _endpoint(method: str) -> tuple[str, str]:
    """Return (url, token) for the active backend + method."""
    if BACKEND == "telegram":
        return f"{TELEGRAM_BASE}/bot{TELEGRAM_TOKEN}/{method}", TELEGRAM_TOKEN
    return f"{ZALO_BASE}/bot{ZALO_TOKEN}/{method}", ZALO_TOKEN


_MAX = 1900  # Zalo sendMessage giới hạn ~2000 ký tự/tin


def _chunks(text: str):
    """Chia text dài thành các đoạn <= _MAX, ưu tiên cắt ở ranh giới dòng."""
    text = text or " "
    while len(text) > _MAX:
        cut = text.rfind("\n", 0, _MAX)
        if cut < _MAX // 2:
            cut = _MAX
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


def _post_one(chat_id: str, text: str, parse_mode: str | None) -> bool:
    url, token = _endpoint("sendMessage")
    if not token or not chat_id:
        return False
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = httpx.post(url, json=payload, timeout=15)
        return r.status_code == 200 and bool(r.json().get("ok", True))
    except Exception:
        return False


def send(chat_id: str, text: str, parse_mode: str | None = None) -> bool:
    """Push a message; tự chia nhỏ nếu > giới hạn. Returns True nếu mọi đoạn gửi OK."""
    ok = True
    for part in _chunks(text):
        ok = _post_one(chat_id, part, parse_mode) and ok
    return ok


def get_updates() -> list[dict]:
    """Fetch pending updates — used to discover a member's chat_id after they DM the bot."""
    url, token = _endpoint("getUpdates")
    if not token:
        return []
    try:
        r = httpx.post(url, json={"offset": 0, "timeout": 0}, timeout=20)
        data = r.json()
        return data.get("result", []) if isinstance(data, dict) else []
    except Exception:
        return []
