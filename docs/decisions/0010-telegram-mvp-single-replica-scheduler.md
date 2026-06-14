# 0010 Notifier abstraction (Zalo PRIVATE mặc định), single-replica + APScheduler nội bộ

Date: 2026-06-13

## Status

Accepted

> Lịch sử: bản đầu của ADR này chốt "Telegram lên MVP". Sau khi review
> `docs/integrations/ZALO_BOT_INTEGRATION.md`, quyết định được tinh chỉnh sang
> Notifier abstraction với Zalo PRIVATE làm mặc định (lý do bên dưới).

## Context

Ba vấn đề liên quan nhau:

1. Chainlit là UI session-based → không có "channel" để push report 9:00/17:30
   hay alert urgent giữa ngày khi không ai mở UI. Cần một kênh push thật.
2. AgentBase Custom Agent always-on (min replicas = 1, không scale-to-zero)
   nhưng không có cron native. Bật autoscale (max>1) sẽ làm scheduler nội bộ
   chạy trên mỗi replica → report gửi trùng.
3. Chọn kênh push nào: Telegram hay Zalo? Đối chiếu doc tích hợp cho thấy
   **Zalo Bot API gần như là bản sao Telegram** (cùng URL pattern
   `/bot<token>/<method>`, cùng method `sendMessage/getUpdates/setWebhook`,
   cùng `secret_token` header, cùng shape `chat_id`/`text`/`parse_mode`).
   Khác biệt then chốt: **Zalo GROUP còn Beta**, nhưng **PRIVATE đã GA**. Team
   là ZaloPay → sống trên Zalo, Telegram là kênh lạ.

## Decision

- **Notifier abstraction**: một interface `send(chat_id, text)` với 2 backend
  hoán đổi bằng config — `zalo` (mặc định) và `telegram` (dự phòng). Vì 2 API
  giống nhau ~90%, đổi kênh là việc config, không phải kiến trúc.
- **Zalo PRIVATE (1-1) làm mặc định**: né hoàn toàn rào cản Beta group (PRIVATE
  đã GA), và đúng kênh native của team. Push **cá nhân hóa**: mỗi member nhận
  report phần mình + alert urgent khi mình là PIC, thay vì spam group.
- **Chỉ outbound `sendMessage`, KHÔNG dựng webhook** cho push-only. Lấy
  `chat_id` member bằng cách: member DM bot 1 lần → `getUpdates` lấy `chat.id`
  → lưu mapping `{jira_assignee → zalo_chat_id}` trong SQLite/config.
- Push **cả** report định kỳ (9:00/17:30) **và** alert urgent/critical tức thì
  (phát hiện ở vòng sync 30'), dedup bằng cờ `alerted` trong SQLite.
- **Single replica (min=max=1)** + **APScheduler trong process** (gắn vào
  FastAPI startup của Chainlit) → tránh cron double-fire.
- Đóng open question "alert urgent giữa ngày": **có, push Zalo ngay tới PIC**.

## Alternatives Considered

1. Telegram làm kênh chính MVP. Telegram group chạy ngay hôm nay, nhưng team
   không dùng Telegram → kênh lạ. Giữ Telegram làm backend dự phòng thay vì
   kênh chính.
2. Zalo GROUP push (vào nhóm team). Bị hoãn: group bot còn Beta + cần webhook
   bridge. Để future.
3. Pull-on-open thuần (không push): user phải mở Chainlit mới thấy. Bị loại vì
   mất giá trị "không bỏ sót / alert ngay".
4. Multi-replica + external cron. Over-engineer cho hackathon; state phải ra
   store ngoài.

## Consequences

Positive:

- Đúng kênh native của team (Zalo), push cá nhân hóa tới từng người.
- Notifier giúp đổi/đa kênh dễ; Telegram có thể bật làm dự phòng tức thì.
- Push-only không cần webhook → ít hạ tầng.
- Scheduler đơn giản, không gửi trùng.

Tradeoffs:

- Cần bước onboarding: mỗi member DM bot 1 lần để lấy `chat_id`.
- Zalo GROUP (push vào nhóm) chưa làm được ở MVP do Beta.
- Single replica: mất autoscale chat (tải hackathon thừa sức); SQLite mất khi
  container tạo lại — chấp nhận vì sync 30' tự nạp lại.

## Cập nhật khi triển khai (2026-06-14)

- Host Zalo thực tế = **`bot-api.zapps.me`** (không phải zaloplatforms.com); `getUpdates`
  là long-poll real-time (chỉ bắt tin nhắn tới trong lúc poll).
- `chat_id` được **seed qua env `SEED_CHAT_IDS`** để sống sót qua redeploy (SQLite ephemeral).
- **Phạm vi report push:** ban đầu định push cá nhân hoá per-member; theo yêu cầu, đổi sang
  push **báo cáo toàn đội** cho mọi member (khớp Chainlit `/report`). `build_member_report`
  vẫn còn nếu muốn quay lại per-member. Urgent alert vẫn nhắm đúng PIC.

## Follow-Up

- Khi Zalo group bot ra GA: thêm webhook bridge để push vào nhóm + chat 2 chiều.
- Khi cần scale / chat-history bền: tách state ra Postgres ngoài.
