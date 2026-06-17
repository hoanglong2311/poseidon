# Poseidon — Roadmap cải tiến

> Đánh giá sản phẩm hiện tại (v21, đã DEPLOYED) + backlog cải tiến **sắp theo độ cấp bách**.
> Góc nhìn: **OP/FA** (người dùng hằng ngày) + **Developer** (người vận hành).
> Last updated: 2026-06-17 · Liên quan: [`PRODUCT_CONTEXT.md`](PRODUCT_CONTEXT.md), ADR 0008–0013.
>
> ✅ Đã ship từ bảng này: #2 (comment ngược + audit, v22), #3 (track vòng đời CICD, v23).
> ✅ Thêm: **Dashboard read-only FA/OP** `/dashboard` (v24) — xem ticket tồn đọng + chart, query Jira
> live, gate bằng `DASHBOARD_TOKEN` (xem #9 — đã làm phần "xem ticket"; phần metrics triage/CICD vẫn open vì cần #1).

---

## Hiện trạng (v21)

Sản phẩm đã **khép vòng triage**: phát hiện ticket (OS+ZPI) → phân loại (complexity/risk/PIC) →
đọc runbook Confluence reason ra cách xử lý → tạo CICD ticket (ADF, link ticket gốc) → thông báo.
Đa kênh: **Web Chainlit** (OAuth, bảng báo cáo, chat history, starters) + **Zalo** (chat 2 chiều
read-only gated bằng mã, push report/alert). Có **bộ nhớ dài hạn** (recall/remember rule). Deploy
single-replica trên AgentBase.

→ Đã là trợ lý triage **dùng được thật**. Phần còn lại là biến nó từ *"trả lời khi được hỏi"*
thành *chủ động + đáng tin để dựa vào hằng ngày*.

---

## Bảng ưu tiên (sort theo độ cấp bách)

| # | Hạng mục | Tier | Giá trị cho | Effort | Phụ thuộc |
|---|----------|------|-------------|--------|-----------|
| 1 | Dữ liệu bền (Postgres thay SQLite) | 🥇 P0 | Dev (lòng tin) | Vừa | DB ngoài |
| 2 | Comment ngược ticket gốc + audit trail | 🥇 P0 | OP/FA + Dev | Nhẹ | — |
| 3 | Theo dõi vòng đời CICD ticket (đóng vòng) | 🥇 P0 | OP/FA | Vừa | #2 |
| 4 | Verify + hoàn thiện urgent alert end-to-end | 🥇 P0 | OP/FA | Nhẹ | — |
| 5 | Cảnh báo SLA/aging (ticket trượt) | 🥈 P1 | OP/FA | Vừa | — |
| 6 | Gợi ý PIC nên xử lý | 🥈 P1 | OP/FA | Vừa | Memory/lịch sử |
| 7 | Mỗi ticket trong report kèm runbook gợi ý | 🥈 P1 | OP/FA | Nhẹ | — |
| 8 | Feedback 👍/👎 → lưu Memory | 🥈 P1 | Dev + chất lượng | Nhẹ | data layer |
| 9 | Dashboard số liệu (triage/CICD/push) | 🥉 P2 | Dev/quản lý | Vừa | #1 | ⏳ phần "xem ticket tồn đọng" ✅ v24 (`/dashboard`); metrics triage/CICD còn lại |
| 10 | Escalation (urgent quá hạn → lead) | 🥉 P2 | OP/FA | Nhẹ | #4 |
| 11 | Zalo auth mạnh hơn (per-người + audit ghi) | 🥉 P2 | Bảo mật | Vừa | — |
| 12 | HA (bỏ single-replica) + multi-team + pagination + fallback MaaS | 🥉 P2 | Dev/scale | Cao | #1 |

---

## Tier 1 — Nền tảng & lòng tin (CẤP BÁCH, làm trước)

### 1. Dữ liệu bền — Postgres thay SQLite *(P0)*
- **Vấn đề:** ticket sync, report, `chat_id` bắt qua webhook, lịch sử chat đều nằm SQLite trong
  container → **mất khi redeploy/restart**. Một tool người ta dựa vào mà mất state là mất tin.
- **Làm:** chuyển `core/store.py` (và Chainlit data layer) sang **Postgres ngoài** (GreenNode
  managed DB). Giữ schema, đổi connection. `chat_id`/auth/rule không phải seed lại.
- **Đo:** redeploy mà ticket/chat_id/history còn nguyên.

### 2. Comment ngược ticket gốc + audit trail *(P0)* — ✅ **DONE (v22)**
- **Vấn đề:** agent gợi ý/tạo CICD nhưng **không để lại dấu vết trên ticket Jira nguồn**.
- **Đã làm:** khi tạo CICD → **comment vào ticket gốc** ("🤖 Poseidon đã tạo **CICD-N** (link)
  theo runbook — yêu cầu bởi *actor*"). Audit log SQLite (`audit_log`) ghi mọi hành động ghi
  (create_cicd_ticket, remember) kèm actor + thời gian. Xem qua lệnh `/audit` trên web.
  Actor lấy từ OAuth email (web) / tên Zalo, truyền qua contextvar `CURRENT_ACTOR`.
- **Còn lại (gắn với #1):** audit hiện ở SQLite ephemeral → bền hơn khi có Postgres.

### 3. Theo dõi vòng đời CICD ticket — đóng vòng *(P0)* — ✅ **DONE (v23)**
- **Vấn đề:** tạo CICD xong là "thả", không biết SRE đã làm chưa.
- **Đã làm:** mỗi CICD ticket tạo ra được lưu vào bảng `cicd_tracked` (cicd_key, source, status,
  notified_done). Job `run_cicd_tracking` chạy mỗi **15'** (+ lúc boot) poll status; khi
  `statusCategory=done` → **comment "✅ hoàn tất" lên ticket gốc** + push Zalo cho PIC (nếu có
  chat_id) + audit `cicd_done` + đánh dấu notified (dedup). Verify: CICD-21→Done → ZPI-4 nhận
  comment hoàn tất.
- **Còn lại (gắn #1):** `cicd_tracked` ở SQLite ephemeral → CICD tạo trước khi redeploy sẽ mất
  theo dõi. Cần **Postgres (#1)** để track bền.

### 4. Verify + hoàn thiện urgent alert end-to-end *(P0, nhẹ)*
- **Vấn đề:** cảnh báo urgent đã code nhưng **chưa test thật**; OP/FA sống nhờ "không bỏ sót khẩn".
- **Làm:** tạo ticket priority cao → kiểm vòng sync 30' phát hiện + push đúng PIC + dedup cờ
  `alerted`. Cân nhắc rút chu kỳ sync xuống 5–10' cho urgent.

---

## Tier 2 — Giá trị nghiệp vụ OP/FA

### 5. Cảnh báo SLA / aging *(P1)*
"Ticket To Do quá X giờ chưa ai đụng", "urgent chưa ack" — biến bot từ *liệt kê* thành *cảnh báo
cái đang trượt*. Hiện báo cáo còn phẳng, chưa nêu rủi ro tồn đọng.

### 6. Gợi ý PIC nên xử lý *(P1)*
Dựa lịch sử ai từng xử lý runbook tương tự → "refund này nên giao Long". Đòn bẩy lớn cho phân phối
(hiện cố ý chỉ gom theo assignee sẵn có — xem PRODUCT_CONTEXT). Có thể tận dụng Memory.

### 7. Mỗi ticket trong report kèm runbook gợi ý sẵn *(P1, nhẹ)*
Lúc classify, match runbook khớp nhất (CQL hoặc LLM) → đính link vào report. Đỡ phải hỏi từng cái.

### 8. Feedback 👍/👎 trên gợi ý *(P1)*
Cho user chấm gợi ý; lưu vào Memory để agent tốt dần. Chainlit có sẵn cơ chế feedback (cần wire
vào data layer).

---

## Tier 3 — Hoàn thiện & quy mô

### 9. Dashboard số liệu *(P2)*
Bao nhiêu ticket triage, runbook gợi ý, CICD tạo, push thành công → chứng minh giá trị + dễ debug.

### 10. Escalation *(P2)*
Urgent quá X phút chưa xử lý → báo team lead.

### 11. Zalo auth mạnh hơn *(P2)*
Mã đăng ký chung hiện hơi yếu (ADR 0012). Nên gắn danh tính per-người + audit hành động ghi.

### 12. HA + multi-team + pagination + fallback MaaS *(P2, cao)*
Bỏ single-replica khi cần (lưu ý cron double-fire — tách scheduler ra ngoài); cấu hình nhiều
team/project; pagination cho board lớn; fallback model khi MaaS chậm/lỗi.

---

## Khuyến nghị thứ tự làm

1. **#2 Comment ngược + audit** — nhẹ, tăng lòng tin ngay, không cần hạ tầng mới → **làm đầu tiên**.
2. **#4 Verify urgent alert** — nhẹ, đúng nỗi đau cốt lõi OP/FA.
3. **#1 Postgres** — nền tảng cho mọi thứ bền vững (và mở đường cho #3, #9).
4. **#3 Track CICD + #5 SLA alert** — chuyển bot sang *chủ động đóng vòng*.
5. Sau đó Tier 2 còn lại → Tier 3.

> **Tóm tắt 2 góc nhìn:**
> - *Dev:* hiện thiếu **persistence (#1)** + **observability/audit (#2, #9)** — 2 thứ quyết định
>   một tool nội bộ có được tin dùng lâu dài.
> - *OP/FA:* bot đang giỏi *"trả lời khi được hỏi"*; bước tiếp theo là **chủ động** (SLA #5,
>   escalation #10, đóng vòng CICD #3).
