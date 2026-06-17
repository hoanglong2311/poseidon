# 0012 Zalo trở thành kênh chat 2 chiều với agent (read-only, gated)

Date: 2026-06-15

## Status

Accepted

## Context

Ban đầu Zalo chỉ là kênh push (report/alert) + bắt chat_id qua webhook. Yêu cầu mới:
cho phép **chat với agent qua Zalo** giống Chainlit web (hỏi ticket, gợi ý runbook).
Khác biệt then chốt: **web có Google OAuth, Zalo KHÔNG có login**, và agent đọc được
data Jira nội bộ + có tool ghi (tạo ticket CICD). Webhook cũng chỉ nhận `from.id` +
`display_name` (KHÔNG có số điện thoại) nên không thể lọc theo phone.

## Decision

Mở rộng `POST /zalo/webhook` thành kênh chat 2 chiều, qua phiên grill chốt:

- **Cấp quyền bằng mã đăng ký** (`ZALO_REGISTER_CODE`, passphrase chung): chat mới phải
  gửi đúng mã mới được chat; chat_id trong `SEED_CHAT_IDS` **auto-cấp-quyền**. (Không
  dùng phone vì webhook không cấp; không dùng allowlist-env vì khó biết chat_id trước.)
- **Read-only qua Zalo:** agent dùng tập tool KHÔNG có `create_cicd_ticket` (tạo ticket
  chỉ qua web có OAuth). `ask_sync(messages, allow_write=False)`.
- **Lưu trạng thái:** cờ `authorized` → SQLite (cột `chat_ids.authorized`); lịch sử hội
  thoại → in-memory dict theo chat_id (cap ~12 lượt, mất khi restart).
- **Async:** webhook trả 200 ngay → gửi "⏳ Đang xử lý..." → chạy agent ở background
  (`asyncio.to_thread`) → `sendMessage` (tránh block event loop / Zalo timeout).
- **Format:** `parse_mode=markdown` + tự chunk >2000 ký tự (thay vì cắt cụt).
- **Push báo cáo** chỉ gửi tới chat_id **đã cấp quyền** (`authorized_chat_ids()`) — tránh
  rò rỉ báo cáo nội bộ cho người chưa đăng ký.

## Alternatives Considered

1. Lọc theo số điện thoại Zalo. Bất khả thi: webhook không cấp phone.
2. Allowlist chat_id qua env. Bị loại: phải biết chat_id trước + sửa env mỗi lần thêm người.
3. Full agent (cho tạo ticket qua Zalo). Bị loại: hành động ghi qua kênh không-OAuth rủi ro
   hơn; giữ tạo ticket ở web.
4. Polling getUpdates thay webhook. Đã bỏ (0011/quá trình): miss event, bị trợ lý mặc định
   Zalo nuốt tin; webhook là event-driven, đáng tin.

## Consequences

Positive:

- Team chat agent qua Zalo (kênh native) — hỏi ticket/runbook mọi lúc, không cần mở web.
- Có lớp chặn (mã đăng ký) dù Zalo không có OAuth; report không lộ cho người lạ.

Tradeoffs:

- Mã đăng ký là passphrase chung (không phải auth per-người mạnh) — đủ cho nội bộ.
- Lịch sử chat Zalo in-memory → mất khi redeploy/restart (ngữ cảnh ngắn hạn, chấp nhận).
- Tạo ticket không làm được qua Zalo (cố ý) — phải dùng web.

## Follow-Up

- Nếu cần auth mạnh hơn: liên kết chat_id ↔ danh tính Jira khi đăng ký (email), hoặc
  per-người code.
- Lịch sử bền: chuyển sang SQLite/Postgres nếu muốn giữ qua restart.
