# poseidon-agent

Jira Triage Bot — GreenNode AgentBase Custom Agent (Claw-a-thon 2026). 🟢 **Deployed & ACTIVE (v26)**.

Tự động scan Jira (`OS` + `ZPI`), phân loại ticket (complexity/risk/PIC), tổng hợp báo cáo,
đọc **runbook** Confluence để gợi ý cách xử lý, **tạo ticket CICD** (comment ngược + link + theo
dõi tới khi Done), nhớ **rule/fact** dài hạn. Chat 2 kênh: **Web Chainlit** (Google OAuth + lịch
sử chat) và **Zalo** (chat read-only, gated bằng mã đăng ký). Push báo cáo + cảnh báo urgent.
Có **dashboard read-only** cho FA/OP tại `/dashboard` (2 tab persona, chart, query Jira live, gate
bằng `DASHBOARD_TOKEN`) — **nhúng sẵn chat Poseidon** (Chainlit Copilot, read-only) ngay trong trang.

> Thiết kế: [`../docs/product/PRODUCT_CONTEXT.md`](../docs/product/PRODUCT_CONTEXT.md) ·
> Roadmap: [`../docs/product/IMPROVEMENTS.md`](../docs/product/IMPROVEMENTS.md)
> · ADR [0008 REST↔MCP](../docs/decisions/0008-rest-instead-of-mcp-for-atlassian.md)
> · [0009 Chainlit](../docs/decisions/0009-chainlit-instead-of-copilot-kit.md)
> · [0010 Notifier/Zalo](../docs/decisions/0010-telegram-mvp-single-replica-scheduler.md)
> · [0011 Tạo ticket CICD](../docs/decisions/0011-agent-write-create-cicd-ticket.md)
> · [0012 Zalo chat](../docs/decisions/0012-zalo-conversational-agent.md)
> · [0013 Memory](../docs/decisions/0013-agentbase-memory-longterm-facts.md)

## Kiến trúc

```
app.py — Chainlit (port 8080, /health) + Google OAuth + chat history (data layer)
         lệnh: /report · /report now · /audit (nhật ký hành động) · chat tự do
         welcome + @cl.set_starters (thẻ bấm nhanh) ; history trong cl.user_session
         POST /zalo/webhook — chat 2 chiều Zalo (read-only, gated mã đăng ký) +
              bắt chat_id + push; trả 200 ngay, agent chạy nền; flatten bảng markdown
core/
  scheduler.py  — APScheduler (single replica): sync 30' (+boot) · cicd_track 15' (+boot)
                  · report 09:00 & 17:30. classify song song (ThreadPoolExecutor).
                  run_cicd_tracking: CICD Done → comment ticket gốc + push PIC.
  jira_client.py— Jira/Confluence REST (ADR 0008): team_jql, search_jira, get_ticket,
                  get_status, add_comment, create_jira_ticket (CICD, ADF v3, link Relates
                  + comment ngược), search_confluence (CQL text~), get_confluence_page,
                  list_runbooks (children của runbook index)
  classifier.py — Qwen 3.5 27B (tắt thinking → ~1-3s): complexity/risk (L/M/H) + lý do
  report.py     — build_report (bảng md, Chainlit) · build_report_plain (Zalo) · build_member_report
  agent.py      — MiniMax M2.5 (có history). Tools đọc (web+Zalo): list_team_tickets,
                  get_jira_ticket, list_available_runbooks, search_confluence_docs,
                  read_confluence_page, recall_memory. Tools ghi (chỉ web): create_cicd_ticket
                  (xác nhận trước + comment ngược + track + link), remember. CURRENT_ACTOR contextvar.
  memory.py     — AgentBase Memory REST (ADR 0013): recall / remember (insert-directly,
                  field memoryRecords); actor chung "team"; token từ creds inject
  notifier.py   — Notifier: Zalo (zapps.me, mặc định) | Telegram; chunk >1900 + parse_mode
  datalayer.py  — Chainlit chat-history (SQLAlchemy + SQLite, full StepDict schema)
  store.py      — SQLite: tickets · reports · chat_ids (+authorized, seed) · audit_log · cicd_tracked
```

## Chạy local

```bash
cd agent
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # điền LLM_API_KEY, JIRA_*, ZALO_BOT_TOKEN, OAUTH_GOOGLE_*, MEMORY_*, ...
chainlit run app.py --host 0.0.0.0 --port 8080 --headless
```
- UI: http://localhost:8080 · Health: http://localhost:8080/health
- Lưu ý: OAuth redirect + Zalo webhook dùng URL public (`CHAINLIT_URL`) nên test tốt nhất trên bản deploy.

## Cấu hình (env) chính

| Nhóm | Biến |
|------|------|
| LLM (MaaS) | `LLM_API_KEY` (hoặc `AI_PLATFORM_API_KEY`), `LLM_BASE_URL`, `LLM_MODEL_CHAT`, `LLM_MODEL_CLASSIFY` |
| Jira/Confluence | `JIRA_URL/USERNAME/API_TOKEN`, `CONFLUENCE_URL`, `JIRA_PROJECTS=OS,ZPI`, `JIRA_ISSUE_TYPES` (trống=mọi type), `JIRA_TEAM_ACCOUNT_IDS`, `CONFLUENCE_RUNBOOK_PAGE_ID=360449`, `CICD_PROJECT=CICD` |
| Notifier (Zalo) | `NOTIFY_BACKEND=zalo`, `ZALO_BASE_URL`, `ZALO_BOT_TOKEN`, `SEED_CHAT_IDS` (JSON), `ZALO_WEBHOOK_SECRET`, `ZALO_REGISTER_CODE` (mã đăng ký chat) |
| Web auth | `CHAINLIT_AUTH_SECRET`, `CHAINLIT_URL`, `OAUTH_GOOGLE_CLIENT_ID/SECRET`, `AUTH_ALLOWED_EMAILS`/`AUTH_ALLOWED_DOMAIN` |
| Memory | `MEMORY_ID`, `MEMORY_STRATEGY_ID`, `MEMORY_ACTOR_ID=team` |

## Deploy

Từ repo root: build `linux/amd64` (context `agent/`) → push AgentBase CR → `runtime.sh update <id> --from-cr --env-file agent/.env`. Container chỉ cần port 8080 + `/health` 200. Sau deploy lần đầu: `setWebhook` trỏ Zalo về `<endpoint>/zalo/webhook`.

> ⚠️ State ở **SQLite trong container = ephemeral** (mất khi redeploy): tickets/report tự nạp lại;
> `chat_ids` giữ qua `SEED_CHAT_IDS`; nhưng `audit_log`, `cicd_tracked`, chat history **mất** →
> xem [`IMPROVEMENTS.md`](../docs/product/IMPROVEMENTS.md) #1 (Postgres) để bền.
