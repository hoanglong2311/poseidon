# Product Context — Jira Triage Bot (Poseidon)

> Claw-a-thon 2026 · VNG Group · GreenNode AgentBase
> Last updated: 2026-06-14 (cập nhật theo bản đã **DEPLOYED** — v9)
> Code: [`../../agent/`](../../agent/) · Trạng thái: 🟢 **ACTIVE trên AgentBase**
> Roadmap cải tiến (sort theo cấp bách): [`IMPROVEMENTS.md`](IMPROVEMENTS.md)

---

## Vấn đề

OP và FA phải thủ công phân phối và theo dõi Jira ticket cho từng thành viên trong team. Quy trình phân tán, tốn sức người, dễ bỏ sót context, và không có cơ chế gợi ý hướng giải quyết dựa trên runbook/kinh nghiệm cũ.

---

## Giải pháp

AI Bot tự động scan, phân loại và tổng hợp Jira ticket được assign cho team — kết hợp Confluence để **đọc runbook và reason ra các bước xử lý** cho từng ticket.

**Workflow chính:**

1. OP/FA assign ticket trên Jira như bình thường — **không thay đổi quy trình hiện tại**.
2. Agent tự động scan ticket từ 2 project **`OS`** (Operation Support) và **`ZPI`** (Zalopay production issue), lọc theo `assignee` là thành viên team (lọc theo `issuetype` là tuỳ chọn — mặc định lấy mọi type).
3. Agent phân loại (complexity/risk) + tổng hợp báo cáo → hiển thị trên **Chainlit UI** (`/report`) và push qua **Notifier** (mặc định **Zalo**).
4. Thành viên chat hỏi agent trên UI; agent đọc ticket + **xem danh sách runbook + đọc nội dung runbook Confluence** → reason → suggest các bước xử lý cụ thể.
5. Sau khi gợi ý, agent **hỏi user có muốn tạo ticket CICD** (nhờ SO/SRE thực hiện) không — nếu user xác nhận, agent **tạo ticket trong project `CICD`** (kèm bước/câu lệnh + link runbook). Chat agent có **bộ nhớ hội thoại** trong phiên để hỗ trợ luồng hỏi→xác nhận.

**Team hiện tại (test site `buuquang102.atlassian.net`):** Quang, Long, Tín.

---

## Polling Architecture

Bot chạy **2 tầng poll** (APScheduler nội bộ container, single replica → không double-fire):

### Tầng 1 — Report Trigger (2 lần/ngày)

| Thời điểm | Hành động |
|-----------|-----------|
| **9:00** | Poll + classify → lưu SQLite + push báo cáo toàn đội ra **Zalo** |
| **17:30** | Poll + classify → lưu SQLite + push báo cáo toàn đội ra **Zalo** |

> Report được **pre-compute** + lưu SQLite. Team xem lại bất cứ lúc nào bằng `/report` (instant); `/report now` để tính lại + push ngay.

### Tầng 2 — Background Sync (mỗi 30 phút, + 1 lần ngay khi khởi động)

- Poll Jira (`project in (OS, ZPI)` + `assignee in (team)`) → upsert SQLite.
- Phát hiện ticket **urgent/critical mới** → push **Zalo ngay tới PIC** (assignee), dedup bằng cờ `alerted`.
- Chat hỏi → trả lời từ data đã sync (nhanh), tra Confluence khi cần.

> **Open question (ĐÃ CHỐT):** ticket urgent giữa ngày → **push Zalo ngay tới PIC**, không chờ 17:30.

---

## Output của Bot

1. **Báo cáo dạng bảng** — Chainlit `/report` hiện **bảng markdown** (Key · Tiêu đề · Trạng thái · PIC · Phức tạp · Rủi ro); Zalo nhận bản text gọn theo nhóm PIC. Có thống kê tổng/trạng thái/đếm urgent.
2. **Phân loại từng ticket** (Qwen 3.5 27B, tắt thinking → ~1-3s/ticket, classify song song):
   - complexity — Low/Medium/High + 1 câu lý do
   - risk — Low/Medium/High + 1 câu lý do
   - PIC — **gom theo assignee sẵn có** (bot không reassign)
3. **Gợi ý hướng xử lý từ runbook** — agent **xem danh sách toàn bộ runbook** (`list_available_runbooks`) → **đọc nội dung** runbook phù hợp → reason → tóm tắt các bước áp dụng cho ticket, kèm link.
4. **Tạo ticket CICD theo runbook** *(có xác nhận — ADR 0011)* — sau khi gợi ý, agent hỏi user; nếu đồng ý → **tạo ticket trong project `CICD`** (type Task) với description **ADF** đẹp, **link `Relates` về ticket gốc**, **comment ngược lên ticket gốc** ("🤖 Poseidon đã tạo CICD-N — yêu cầu bởi <actor>"), và **ghi audit log** (xem `/audit` trên web). *(IMPROVEMENTS #2)*

---

## Kênh phân phối (MVP — đã triển khai)

- **Chainlit UI** — giao diện chat chính (port 8080).
  - **Đăng nhập Google OAuth** bắt buộc (`@cl.oauth_callback` + allowlist email/domain qua env). Test users của OAuth consent screen là lớp chặn truy cập.
  - **Lịch sử hội thoại** — Chainlit data layer (SQLAlchemy + SQLite) → có sidebar thread + resume.
  - Lệnh `/report` (báo cáo toàn đội đã tính sẵn) · `/report now` (tính lại + push) · chat tự do hỏi ticket/runbook.
  - **Welcome screen** liệt kê đầy đủ command + khả năng; có **Starters** (thẻ bấm nhanh: xem báo cáo, ticket của tôi, cách xử lý ticket, danh sách runbook).
- **Notifier (push)** — abstraction `send(chat_id, text)`, 2 backend hoán đổi bằng config:
  - **Zalo (mặc định)** — host `bot-api.zapps.me`. **Webhook 2 chiều** (`/zalo/webhook`): vừa push (báo cáo toàn đội + alert urgent tới PIC), vừa **chat với agent (read-only)** — hỏi ticket/runbook, gõ `/report`. Cấp quyền bằng **mã đăng ký** (`ZALO_REGISTER_CODE`); chat mới gửi mã mới dùng được; tạo ticket chỉ qua web. Xem ADR 0012 + [`../integrations/ZALO_BOT_INTEGRATION.md`](../integrations/ZALO_BOT_INTEGRATION.md)
  - **Telegram (dự phòng)** — cùng interface, bật bằng `NOTIFY_BACKEND=telegram`.
  - **Lấy `chat_id`:** member DM bot trong lúc chạy `getUpdates` (real-time long-poll) → map `{jira_account → chat_id}`. Map được **seed qua env `SEED_CHAT_IDS`** để sống sót qua redeploy (SQLite container ephemeral).

### Future (sau hackathon)

- **Zalo GROUP** push (mention/reply) — chờ group bot ra khỏi Beta; cần webhook bridge.
- **Push cá nhân hoá** — hiện push báo cáo toàn đội cho mọi member; `build_member_report` đã có sẵn nếu muốn chuyển lại per-member.
- **Copilot Kit UI**, **chat 2 chiều trong Zalo**, **agentbase-identity** cho outbound auth, **Postgres** cho chat-history bền qua redeploy.

---

## Tech Stack

| Thành phần | Công nghệ |
|-----------|-----------|
| Jira/Confluence access | **REST API** (`atlassian-python-api`) wrap thành LangChain tools — *không dùng MCP* (ADR 0008). Đọc (sync/search/runbook body) + **ghi** (tạo ticket CICD qua API v3 với ADF) |
| Workflow / orchestration | LangChain (`create_agent`, có bộ nhớ hội thoại trong phiên) + APScheduler (nội bộ) |
| Chat UI | **Chainlit** (FastAPI) + **Google OAuth** + chat-history data layer — *thay Copilot Kit* (ADR 0009) |
| State store | SQLite — `poseidon.db` (ticket/report/chat_id/auth) + `chainlit.db` (lịch sử chat web) |
| Long-term memory | **AgentBase Memory** `poseidon-mem` (SEMANTIC) — rule/fact của team. Tools `recall_memory` (web+Zalo) / `remember` (web). REST, actor chung `team`. ADR 0013 |
| Runtime | GreenNode AgentBase — **Custom Agent**, single replica (min=max=1), PUBLIC, port 8080 + `/health` |
| Model (chat) | `minimax/minimax-m2.5` — tool-calling ✅ (strip `<think>` khi hiển thị) |
| Model (classify/report) | `qwen/qwen3-5-27b` |
| LLM endpoint | `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` (OpenAI-compatible, API key BTC) |
| Notification | **Notifier** → **Zalo** (`bot-api.zapps.me`, mặc định) + **Telegram** (dự phòng). Zalo GROUP = future. ADR 0010 |

> **Custom Agent vs OpenClaw:** dùng Custom Agent (scaffold `/agentbase-wizard`) để kiểm soát orchestration + scheduler. Single replica tránh cron double-fire. `qwen3-reranker-8b` **không dùng** (Confluence search bằng CQL `text ~` + đọc body trực tiếp, không cần rerank endpoint).

---

## Models đang dùng (GreenNode MaaS)

**Endpoint chung (OpenAI-compatible):** `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1`
(API key BTC cấp, cấu hình qua env — đổi model không cần sửa code).

| Vai trò | Model (`path`) | Env | Tham số / ghi chú |
|---------|----------------|-----|-------------------|
| **Chat / Agent** (khối B) | `minimax/minimax-m2.5` | `LLM_MODEL_CHAT` | Tool-calling (chuẩn OpenAI — đã verify). Thinking BẬT → strip `<think>` khi hiển thị |
| **Classify / Report** (khối A) | `qwen/qwen3-5-27b` (Qwen 3.5 27B) | `LLM_MODEL_CLASSIFY` | `temperature=0`, `max_tokens=512`, **`enable_thinking=False`** → ~1–3s/ticket (trước ~35s) |
| Reranker *(khai báo, CHƯA dùng)* | `qwen/qwen3-reranker-8b` | `LLM_MODEL_RERANK` | Confluence dùng CQL `text~` + đọc body, không cần rerank |
| Embedding (Memory) | *(managed bởi platform)* | — | AgentBase Memory SEMANTIC tự lo embedding/search, ta không cấu hình |

**Lý do chọn:**
- **MiniMax M2.5** — model duy nhất xác nhận **emit `tool_calls` chuẩn OpenAI** trên MaaS → chạy được agent loop có tool.
- **Qwen 3.5 27B** — tiếng Việt tốt + rẻ cho classify; **tắt thinking** để nhanh (mặc định Qwen3 sinh ~1600 token reasoning → chậm).

---

## Luồng tổng thể

```
Custom Agent container (single replica, always-on, port 8080, /health)
│  APScheduler: sync 30' · cicd_track 15' · report 09:00/17:30  (+ tất cả chạy lúc boot)
│
[Jira: OS + ZPI] ←─ REST (assignee in team) ─poll 30'─► [SQLite]
                                                  │   └─ urgent mới → Notifier→Zalo (tới PIC)
                            ┌──────────┤ 9:00 / 17:30
                            ▼
                  [classify: Qwen 3.5 27B] → lưu SQLite
                            ├──► Notifier→Zalo (push báo cáo, chỉ chat_id đã cấp quyền)
                            └──► Chainlit /report (bảng)

[CICD tracking 15'] poll status CICD đã tạo → khi Done: comment "✅ hoàn tất" ticket gốc + báo PIC

Chat (web: login Google + history · Zalo: gated mã đăng ký, read-only) ─► [MiniMax M2.5]
   tools đọc: list_team_tickets · get_jira_ticket · list_available_runbooks ·
              search_confluence_docs · read_confluence_page · recall_memory
   tools ghi (chỉ web): create_cicd_ticket · remember
   → xem runbook → đọc → reason → suggest bước + link
   → hỏi "tạo ticket CICD?" → (đồng ý) tạo CICD (ADF) + link Relates + comment ngược + track + audit
OP/FA ──assign ticket──► Jira (quy trình không đổi) ; /audit xem nhật ký hành động
```

---

## Trạng thái triển khai (DEPLOYED 2026-06-14)

🟢 **ACTIVE** trên GreenNode AgentBase · **v26** · single replica 2x4 (2 CPU/4GB) · PUBLIC
- Runtime: `poseidon-agent` (`runtime-47ba8dda-fd9b-4f0b-a424-403211c32f54`) · flavor `runtime-s2-general-2x4` · CR repo `111480-abp111802` (`vcr.vngcloud.vn`)
- Endpoint: `https://endpoint-48095726-fd41-4c0a-b174-57656c1f8b2b.agentbase-runtime.aiplatform.vngcloud.vn`
- **Dashboard FA/OP**: `<endpoint>/dashboard` — bảng theo dõi ticket OS/ZPI (live từ Jira), gated bằng `DASHBOARD_TOKEN` (header `X-Dashboard-Token` hoặc `?key=`). Read-only, không cần Google OAuth.
- Redeploy: rebuild image (`linux/amd64`, context `agent/`) → push CR → `runtime.sh update <id> --image ... --from-cr --env-file agent/.env`.

### Đã chạy live ✅

- [x] Custom Agent (Chainlit, port 8080 + `/health`) — deploy ACTIVE
- [x] Jira REST sync (OS + ZPI, assignee team) → SQLite · poll 30' + lúc boot
- [x] Phân loại complexity/risk (Qwen 3.5 27B, tắt thinking + classify song song → nhanh)
- [x] Report **dạng bảng** 9:00/17:30 + `/report` + `/report now`
- [x] Chat agent (MiniMax M2.5 + tools) — **có bộ nhớ hội thoại trong phiên**
- [x] **Confluence: xem danh sách runbook → đọc → reason ra các bước** (`list_available_runbooks` + `read_confluence_page`)
- [x] **Tạo ticket CICD theo runbook (có xác nhận), description ADF đẹp, link `Relates` về ticket gốc**
- [x] Notifier Zalo (`zapps.me`) push báo cáo + alert urgent; Telegram fallback
- [x] `SEED_CHAT_IDS` env (mapping sống qua redeploy)
- [x] Google OAuth login + chat history (Chainlit SQLite data layer)
- [x] Welcome screen liệt kê đầy đủ command + Starters (thẻ bấm nhanh)
- [x] **Zalo chat 2 chiều với agent (read-only, gated bằng mã đăng ký)** — webhook event-driven, push chỉ tới chat_id đã cấp quyền
- [x] **Bộ nhớ dài hạn (AgentBase Memory)** — `recall_memory` nhớ rule/fact team xuyên phiên; `remember` lưu rule (web)
- [x] **Ghi ngược ticket gốc + audit** (v22) — comment lên ticket nguồn khi tạo CICD; audit log + `/audit`
- [x] **Track vòng đời CICD** (v23) — job 15' poll status; CICD Done → comment "✅ hoàn tất" lên ticket gốc + báo PIC
- [x] **Dashboard FA/OP** (v24, v25) — trang web read-only `/dashboard`, query Jira **live mỗi lần load**, gate bằng `DASHBOARD_TOKEN`, UI phong cách Claude. **v25 (theo feedback user)**: **2 tab theo persona** — *(a) Backlog phòng ban* cho OP/FA (4 thẻ số, donut theo trạng thái, bar **theo project/phòng ban** + theo PIC, bảng + filter chips: trạng thái/project/PIC/chưa-giao, không trộn Done vào tồn đọng) · *(b) Cần xử lý* cho PIC (chỉ ticket mở, gom theo To Do/In Progress, urgent lên đầu, badge **⚠ chưa giao**, nút **deep-link "Mở/Giao trong Jira"** — ghi do Jira lo, dashboard giữ read-only). Cột **Tuổi = số ngày từ lúc tạo** (đỏ nếu mở ≥7 ngày)
- [x] **Chat nhúng trong dashboard** (v26) — **Chainlit Copilot** floating widget ngay trong `/dashboard`: FA/OP hỏi agent (read-only) mà không rời trang. Cùng origin nên không vướng CORS. App bật OAuth → Copilot cần `accessToken`: endpoint `/api/copilot-token` đổi `DASHBOARD_TOKEN` lấy 1 JWT Chainlit ngắn hạn (danh tính `FA/OP (dashboard)`); `on_message` nhận diện `client_type=="copilot"` → ép read-only (không tạo CICD). Đã verify live: mount + auth + agent trả lời thật. *(Lưu ý lệch số: agent `list_team_tickets` chỉ đếm ticket giao cho team từ SQLite; dashboard đếm mọi ticket OS/ZPI live → cần đồng bộ sau.)*

### Còn lại / lưu ý

- [ ] Onboard `chat_id` cho Quang + Tín (hiện mới có Long) → seed thêm vào `SEED_CHAT_IDS`
- [ ] Test urgent alert end-to-end (cần 1 ticket priority cao)
- ⚠️ SQLite ephemeral: chat history mất khi redeploy (chat_id thì đã seed qua env). Muốn bền → Postgres.

---

## Liên hệ

- **Team:** longnh17@vng.com.vn
- **Event:** Claw-a-thon 2026 — GreenNode × VNG Group
