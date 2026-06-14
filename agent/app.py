"""Poseidon — Jira Triage Bot (Chainlit entrypoint).

One Custom Agent container: Chainlit chat (MiniMax M2.5) + `/report` command,
APScheduler (sync 30' / reports 09:00 & 17:30), and `/health` for the AgentBase
runtime contract (port 8080). See docs/product/PRODUCT_CONTEXT.md + ADR 0008/0009/0010.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv
import chainlit as cl

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from core.store import init_db, latest_report, seed_chat_ids_from_env
from core.report import build_report
from core.scheduler import start_scheduler, run_report
from core import datalayer  # registers @cl.data_layer (chat history persistence)

# --- App startup (runs once when `chainlit run app.py` imports this module) ---
init_db()
seed_chat_ids_from_env()  # seed Zalo chat_id map (SQLite is ephemeral on a fresh container)
datalayer.init_chainlit_db()
start_scheduler()

# --- Health + Zalo webhook endpoints (mounted on Chainlit's FastAPI app) ---
try:
    from chainlit.server import app as _fastapi_app
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from core import store as _store
    from core import notifier as _notifier

    @_fastapi_app.get("/health")
    def _health():
        return {"status": "ok"}

    @_fastapi_app.post("/zalo/webhook")
    async def _zalo_webhook(request: Request):
        """Event-driven: Zalo POSTs every incoming message here → capture chat_id ngay.
        Không cần polling. Thay vì đợi getUpdates, ai nhắn bot là được lưu liền."""
        secret = os.getenv("ZALO_WEBHOOK_SECRET", "")
        if secret and request.headers.get("x-bot-api-secret-token") != secret:
            return JSONResponse({"ok": False}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": True})
        result = body.get("result") if isinstance(body.get("result"), dict) else body
        msg = (result or {}).get("message") or {}
        chat = msg.get("chat") or {}
        frm = msg.get("from") or {}
        chat_id = chat.get("id")
        name = frm.get("display_name") or ""
        if chat_id:
            key = "zalo:" + str(frm.get("id") or chat_id)
            is_new = _store.get_chat_id(key) is None
            _store.set_chat_id(key, chat_id, name)
            logging.info("zalo webhook: captured chat_id=%s name=%s new=%s", chat_id, name, is_new)
            if is_new:  # ack lần đầu, không block response
                asyncio.create_task(asyncio.to_thread(
                    _notifier.send, chat_id,
                    f"✅ Đã đăng ký nhận báo cáo Poseidon. Chào {name or 'bạn'}!"))
        return JSONResponse({"ok": True})
except Exception:
    logging.exception("failed to mount FastAPI routes")


@cl.oauth_callback
def oauth_callback(provider_id: str, token: str, raw_user_data: dict, default_user: cl.User):
    """Gate access via Google OAuth. Restrict to an allowlist (emails or a domain)
    if configured; otherwise allow any authenticated Google account."""
    email = (raw_user_data or {}).get("email", "").lower()
    allowed_emails = {e.strip().lower() for e in os.getenv("AUTH_ALLOWED_EMAILS", "").split(",") if e.strip()}
    allowed_domain = os.getenv("AUTH_ALLOWED_DOMAIN", "").strip().lower().lstrip("@")

    if not allowed_emails and not allowed_domain:
        return default_user  # no restriction configured
    if email in allowed_emails:
        return default_user
    if allowed_domain and email.endswith("@" + allowed_domain):
        return default_user
    logging.warning("OAuth denied for %s (not in allowlist)", email or "<no email>")
    return None


@cl.set_starters
async def starters():
    return [
        cl.Starter(label="📋 Xem báo cáo team", message="/report"),
        cl.Starter(label="🔄 Tính lại báo cáo ngay", message="/report now"),
        cl.Starter(label="🎫 Ticket của tôi", message="Có ticket nào đang giao cho tôi không?"),
        cl.Starter(label="🛠️ Cách xử lý một ticket", message="Ticket ZPI-4 nên xử lý như thế nào?"),
        cl.Starter(label="📚 Có những runbook nào?", message="Liệt kê các runbook hiện có"),
    ]


WELCOME = (
    "👋 **Poseidon — Jira Triage Bot**\n\n"
    "**Lệnh:**\n"
    "- `/report` — báo cáo team mới nhất (dạng bảng)\n"
    "- `/report now` — tính lại báo cáo ngay (+ push Zalo)\n\n"
    "**Hỏi tự do bằng tiếng Việt — tôi có thể:**\n"
    "- 📋 Liệt kê ticket của team / của một người — vd *“ticket nào của Long?”*\n"
    "- 🔎 Xem chi tiết một ticket — vd *“ZPI-4 là gì?”*\n"
    "- 🛠️ Gợi ý cách xử lý ticket theo **runbook** — vd *“xử lý ZPI-4 thế nào?”*\n"
    "- 📚 Liệt kê các **runbook** đang có\n"
    "- 🎫 **Tạo ticket CICD** theo runbook (tôi sẽ hỏi xác nhận trước, và tự link về ticket gốc)\n\n"
    "Gõ lệnh, bấm gợi ý bên dưới, hoặc hỏi tự nhiên nhé!"
)


@cl.on_chat_start
async def on_start():
    cl.user_session.set("history", [])
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(msg: cl.Message):
    text = (msg.content or "").strip()

    if text.lower().startswith("/report"):
        if "now" in text.lower():
            # run_report is blocking (Jira poll + LLM classify) — run off the event
            # loop so /health stays responsive and the platform doesn't restart us.
            async with cl.Step(name="Đang tính báo cáo..."):
                await asyncio.to_thread(run_report, "daily")
        body = await asyncio.to_thread(lambda: latest_report() or build_report())
        await cl.Message(content=body).send()
        return

    from core.agent import ask_sync

    history = cl.user_session.get("history") or []
    history.append({"role": "user", "content": text})

    async with cl.Step(name="Đang xử lý..."):
        try:
            reply = await asyncio.to_thread(ask_sync, history)
        except Exception as e:
            reply = f"⚠️ Lỗi khi gọi agent: {e}"

    history.append({"role": "assistant", "content": reply})
    cl.user_session.set("history", history[-24:])  # giữ ~12 lượt gần nhất
    await cl.Message(content=reply).send()
