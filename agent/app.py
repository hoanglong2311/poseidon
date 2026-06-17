"""Poseidon — Jira Triage Bot (Chainlit entrypoint).

One Custom Agent container: Chainlit chat (MiniMax M2.5) + `/report` command,
APScheduler (sync 30' / reports 09:00 & 17:30), and `/health` for the AgentBase
runtime contract (port 8080). See docs/product/PRODUCT_CONTEXT.md + ADR 0008/0009/0010.
"""
import asyncio
import json
import logging
import os
from dotenv import load_dotenv
import chainlit as cl

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from core.store import init_db, latest_report, seed_chat_ids_from_env, audit_recent
from core.report import build_report
from core.scheduler import start_scheduler, run_report
from core import datalayer  # registers @cl.data_layer (chat history persistence)

# --- App startup (runs once when `chainlit run app.py` imports this module) ---
init_db()
seed_chat_ids_from_env()  # seed Zalo chat_id map (SQLite is ephemeral on a fresh container)
datalayer.init_chainlit_db()
start_scheduler()

# --- Zalo 2-way chat (read-only agent, registration-code gated) ---
from core import store as _store
from core import notifier as _notifier
from core.report import build_report_plain as _build_report_plain

ZALO_REGISTER_CODE = os.getenv("ZALO_REGISTER_CODE", "")
_zalo_history: dict[str, list] = {}  # chat_id -> messages (in-memory, capped)


def _flatten_md_tables(text: str) -> str:
    """Zalo không render bảng markdown → chuyển dòng bảng thành 'a · b · c' cho dễ đọc."""
    out = []
    for ln in (text or "").split("\n"):
        s = ln.strip()
        if s.startswith("|") and s.endswith("|") and "|" in s[1:-1]:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):  # dòng phân cách |---|---|
                continue
            out.append(" · ".join(c for c in cells if c))
        else:
            out.append(ln)
    return "\n".join(out)


def _zalo_agent_reply(chat_id: str, text: str, name: str) -> None:
    """Chạy trong thread (blocking): báo đang xử lý → gọi agent read-only → trả lời."""
    _notifier.send(chat_id, "⏳ Đang xử lý...")
    hist = _zalo_history.get(chat_id, []) + [{"role": "user", "content": text}]
    try:
        from core.agent import ask_sync
        reply = ask_sync(hist, False, f"{name or chat_id} (Zalo)")
    except Exception as e:
        reply = f"⚠️ Lỗi khi xử lý: {e}"
    _zalo_history[chat_id] = (hist + [{"role": "assistant", "content": reply}])[-24:]
    _notifier.send(chat_id, _flatten_md_tables(reply), parse_mode="markdown")


# --- Health + Zalo webhook endpoints (mounted on Chainlit's FastAPI app) ---
try:
    import pathlib as _pathlib
    import datetime as _dt
    from chainlit.server import app as _fastapi_app
    from fastapi import Request
    from fastapi.responses import JSONResponse, HTMLResponse
    from core import jira_client as _jira

    @_fastapi_app.get("/health")
    def _health():
        return {"status": "ok"}

    @_fastapi_app.post("/zalo/webhook")
    async def _zalo_webhook(request: Request):
        """Event-driven Zalo chat: capture chat_id, gate bằng mã đăng ký, route tin
        đã cấp quyền vào agent (read-only). Trả 200 ngay, xử lý agent ở background."""
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
        if not chat_id or frm.get("is_bot"):
            return JSONResponse({"ok": True})
        text = (msg.get("text") or "").strip()
        name = frm.get("display_name") or ""
        _store.touch_chat(chat_id, name)

        def bg(fn, *a):
            asyncio.create_task(asyncio.to_thread(fn, *a))

        if not _store.chat_authorized(chat_id):
            if ZALO_REGISTER_CODE and text == ZALO_REGISTER_CODE:
                _store.authorize_chat(chat_id, name)
                bg(_notifier.send, chat_id,
                   f"✅ Đã kích hoạt! Chào {name or 'bạn'}. Hỏi tôi về ticket/runbook, "
                   "hoặc gõ `/report` để xem báo cáo team.")
            else:
                bg(_notifier.send, chat_id,
                   "👋 *Poseidon — Jira Triage Bot*. Vui lòng gửi **mã đăng ký** để bắt đầu dùng.")
            return JSONResponse({"ok": True})

        if not text:
            bg(_notifier.send, chat_id, "Mình chỉ xử lý tin nhắn văn bản 🙏")
        elif text.lower().startswith("/report") or text.lower() in ("báo cáo", "bao cao"):
            bg(_notifier.send, chat_id, _build_report_plain("daily"))
        else:
            bg(_zalo_agent_reply, chat_id, text, name)
        return JSONResponse({"ok": True})

    # --- Landing page (giới thiệu sản phẩm, public) ---
    @_fastapi_app.get("/landing")
    async def _landing_page():
        html = (_pathlib.Path(__file__).parent / "landing.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    # --- Dashboard FA/OP (read-only, query Jira live, gated bằng DASHBOARD_TOKEN) ---
    @_fastapi_app.get("/dashboard")
    async def _dashboard_page():
        html = (_pathlib.Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @_fastapi_app.get("/api/dashboard")
    async def _dashboard_api(request: Request):
        token = os.getenv("DASHBOARD_TOKEN", "")
        given = request.headers.get("x-dashboard-token") or request.query_params.get("key")
        if token and given != token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            tickets = await asyncio.to_thread(_jira.dashboard_tickets, 200)
        except Exception as e:
            return JSONResponse({"error": str(e)[:200]}, status_code=502)
        for t in tickets:
            t["open"] = (t.get("category") or "") != "done"
            t["urgent"] = _jira.is_urgent(t.get("priority"))
        return JSONResponse({
            "tickets": tickets,
            "jira_base": _jira.JIRA_URL.rstrip("/"),
            "generatedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        })

    @_fastapi_app.get("/api/copilot-token")
    async def _copilot_token(request: Request):
        """Đổi DASHBOARD_TOKEN lấy 1 JWT Chainlit ngắn hạn để Copilot widget (nhúng
        trong /dashboard) kết nối được — app đang bật OAuth nên Copilot bắt buộc accessToken.
        Danh tính cố định 'FA/OP (dashboard)'; chat qua Copilot là read-only (xem on_message)."""
        token = os.getenv("DASHBOARD_TOKEN", "")
        given = request.headers.get("x-dashboard-token") or request.query_params.get("key")
        if token and given != token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if not os.getenv("CHAINLIT_AUTH_SECRET"):
            return JSONResponse({"error": "auth not configured"}, status_code=503)
        try:
            from chainlit.user import User as _CLUser
            from chainlit.auth.jwt import create_jwt as _create_jwt
            jwt_tok = _create_jwt(_CLUser(identifier="FA/OP (dashboard)",
                                          metadata={"role": "fa-op", "via": "dashboard"}))
        except Exception as e:
            return JSONResponse({"error": str(e)[:200]}, status_code=500)
        return JSONResponse({"token": jwt_tok})

    # Chainlit registers a SPA catch-all `GET /{full_path:path}` at import time.
    # Our GET routes are appended after it, so they'd be shadowed — move them ahead.
    _routes = _fastapi_app.router.routes
    _catch_idx = next((i for i, r in enumerate(_routes)
                       if getattr(r, "path", None) == "/{full_path:path}"), None)
    if _catch_idx is not None:
        _ours = [r for r in _routes if getattr(r, "path", None) in ("/landing", "/dashboard", "/api/dashboard", "/api/copilot-token")]
        for r in _ours:
            _routes.remove(r)
        _catch_idx = next(i for i, r in enumerate(_routes)
                          if getattr(r, "path", None) == "/{full_path:path}")
        for r in _ours:
            _routes.insert(_catch_idx, r)
            _catch_idx += 1
except Exception:
    logging.exception("failed to mount FastAPI routes")


@cl.password_auth_callback
def password_auth(username: str, password: str):
    """Đăng nhập user/password cho BAN GIÁM KHẢO (demo) — hiện song song với nút Google.

    Credential lấy từ env:
    - DEMO_AUTH_USERS = JSON {"username": "password", ...} (nhiều giám khảo), HOẶC
    - DEMO_USERNAME + DEMO_PASSWORD (1 cặp).
    So sánh constant-time. Không cấu hình thì tắt (trả None)."""
    import hmac
    users: dict[str, str] = {}
    raw = os.getenv("DEMO_AUTH_USERS", "").strip()
    if raw:
        try:
            users = {str(k): str(v) for k, v in json.loads(raw).items()}
        except Exception:
            logging.warning("DEMO_AUTH_USERS không phải JSON hợp lệ — bỏ qua")
    u, p = os.getenv("DEMO_USERNAME", "").strip(), os.getenv("DEMO_PASSWORD", "")
    if u and p:
        users.setdefault(u, p)
    if not users:
        return None  # demo login chưa bật

    expected = users.get(username)
    if expected and hmac.compare_digest(password, expected):
        return cl.User(identifier=username, metadata={"role": "judge", "via": "password"})
    logging.warning("Demo login thất bại cho user %r", username)
    return None


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

    if text.lower().startswith("/audit"):
        rows = await asyncio.to_thread(audit_recent, 15)
        if not rows:
            await cl.Message(content="Chưa có hành động nào được ghi nhận.").send()
        else:
            lines = ["🧾 **Audit log** (15 gần nhất):", ""]
            for r in rows:
                lines.append(f"- `{r['ts'][:19]}` · **{r['action']}** · {r['actor']} · {r['detail']}")
            await cl.Message(content="\n".join(lines)).send()
        return

    from core.agent import ask_sync

    user = cl.user_session.get("user")
    actor = getattr(user, "identifier", None) or "web-user"
    # Copilot = chat nhúng trong dashboard FA/OP → read-only (không tạo CICD), giống Zalo.
    is_copilot = cl.user_session.get("client_type") == "copilot"
    allow_write = not is_copilot
    if is_copilot:
        actor = "FA/OP (dashboard)"
    history = cl.user_session.get("history") or []
    history.append({"role": "user", "content": text})

    async with cl.Step(name="Đang xử lý..."):
        try:
            reply = await asyncio.to_thread(ask_sync, history, allow_write, actor)
        except Exception as e:
            reply = f"⚠️ Lỗi khi gọi agent: {e}"

    history.append({"role": "assistant", "content": reply})
    cl.user_session.set("history", history[-24:])  # giữ ~12 lượt gần nhất
    await cl.Message(content=reply).send()
