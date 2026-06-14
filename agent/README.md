# poseidon-agent

Jira Triage Bot — GreenNode AgentBase Custom Agent (Claw-a-thon 2026). 🟢 **Deployed & ACTIVE**.

Tự động scan Jira (project `OS` + `ZPI`), phân loại ticket (complexity/risk/PIC), tổng hợp
báo cáo, đọc runbook Confluence để gợi ý hướng xử lý, và push qua Zalo. Chat hỏi đáp qua
Chainlit (Google OAuth + lịch sử chat).

> Thiết kế: [`../docs/product/PRODUCT_CONTEXT.md`](../docs/product/PRODUCT_CONTEXT.md)
> · ADR [0008 REST↔MCP](../docs/decisions/0008-rest-instead-of-mcp-for-atlassian.md)
> · [0009 Chainlit↔Copilot Kit](../docs/decisions/0009-chainlit-instead-of-copilot-kit.md)
> · [0010 Notifier/Zalo + scheduler](../docs/decisions/0010-telegram-mvp-single-replica-scheduler.md)

## Kiến trúc

```
app.py — Chainlit (port 8080, /health) + Google OAuth + chat history (data layer)
         /report (bảng markdown) · /report now (tính lại + push) · chat tự do
         welcome đầy đủ command + @cl.set_starters (thẻ bấm nhanh)
         giữ history hội thoại trong cl.user_session → truyền vào agent
core/
  scheduler.py  — APScheduler: sync 30' (+ lúc boot) · report 09:00 & 17:30 ; classify song song
  jira_client.py— Jira/Confluence REST: team_jql, search_jira, get_ticket,
                  search_confluence (CQL text~), get_confluence_page (đọc body),
                  list_runbooks (children của index), create_jira_ticket (CICD, ADF v3)
  classifier.py — Qwen 3.5 27B (tắt thinking): complexity/risk (Low/Med/High) + lý do
  report.py     — build_report (bảng md, Chainlit) · build_report_plain (Zalo) · build_member_report
  agent.py      — MiniMax M2.5 (có history) + tools: list_team_tickets, get_jira_ticket,
                  list_available_runbooks, search_confluence_docs, read_confluence_page,
                  create_cicd_ticket (hỏi xác nhận trước khi tạo)
  notifier.py   — Notifier abstraction: Zalo (zapps.me, mặc định) | Telegram
  datalayer.py  — Chainlit chat-history (SQLAlchemy + SQLite, full StepDict schema)
  store.py      — SQLite: tickets + reports + chat_id map (+ seed từ env)
```

## Chạy local

```bash
cd agent
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # điền LLM_API_KEY, JIRA_*, ZALO_BOT_TOKEN, OAUTH_GOOGLE_*, SEED_CHAT_IDS...
chainlit run app.py --host 0.0.0.0 --port 8080 --headless
```
- UI: http://localhost:8080 · Health: http://localhost:8080/health
- Lưu ý: OAuth redirect dùng `CHAINLIT_URL` (= endpoint deploy) nên login Google test tốt nhất trên bản deploy.

## Cấu hình (env) chính

| Nhóm | Biến |
|------|------|
| LLM (MaaS) | `LLM_API_KEY` (hoặc `AI_PLATFORM_API_KEY`), `LLM_BASE_URL`, `LLM_MODEL_CHAT`, `LLM_MODEL_CLASSIFY` |
| Jira/Confluence | `JIRA_URL/USERNAME/API_TOKEN`, `CONFLUENCE_URL` (default theo Jira), `JIRA_PROJECTS=OS,ZPI`, `JIRA_ISSUE_TYPES` (trống=mọi type), `JIRA_TEAM_ACCOUNT_IDS`, `CONFLUENCE_RUNBOOK_PAGE_ID=360449`, `CICD_PROJECT=CICD` |
| Notifier | `NOTIFY_BACKEND=zalo`, `ZALO_BASE_URL`, `ZALO_BOT_TOKEN`, `SEED_CHAT_IDS` (JSON map) |
| Auth/UI | `CHAINLIT_AUTH_SECRET`, `CHAINLIT_URL`, `OAUTH_GOOGLE_CLIENT_ID/SECRET`, `AUTH_ALLOWED_EMAILS`/`AUTH_ALLOWED_DOMAIN` |

## Deploy

Từ repo root: build `linux/amd64` (context `agent/`) → push AgentBase CR → `runtime.sh create/update --from-cr --env-file agent/.env`. Xem `/agentbase-deploy`. Container chỉ cần port 8080 + `/health` 200.
