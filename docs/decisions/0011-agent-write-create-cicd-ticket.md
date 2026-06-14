# 0011 Agent có quyền ghi: tạo ticket CICD (có xác nhận)

Date: 2026-06-14

## Status

Accepted

## Context

Ban đầu agent chỉ ĐỌC Jira/Confluence (sync, classify, suggest runbook). Theo yêu cầu
vận hành thực tế (các runbook OPF-RC thường kết thúc bằng "tạo CICD ticket nhờ SO/SRE
thực hiện"), agent cần thêm khả năng **tạo ticket** trong project `CICD` ngay sau khi
gợi ý hướng xử lý — biến agent từ "read-only advisor" thành có thể thực hiện 1 hành động
ghi. Đây là thay đổi về scope (write) và risk (tạo dữ liệu thật trên Jira).

## Decision

- Thêm tool `create_cicd_ticket(summary, description)` → `jira_client.create_jira_ticket`
  (project `CICD`, type Task), tạo qua **API v3 với description ADF**.
- **Cổng xác nhận (confirmation gate):** system prompt buộc agent, sau khi gợi ý runbook,
  HỎI user "tạo ticket CICD không?" và **chỉ gọi create khi user đồng ý ở lượt sau**.
  Để làm được, chat agent giữ **bộ nhớ hội thoại trong phiên** (history trong
  `cl.user_session`) — trước đó mỗi lượt là stateless.
- Phạm vi ghi giới hạn ở **đúng 1 project `CICD`** (qua env `CICD_PROJECT`), type Task.
  Agent KHÔNG sửa/xoá ticket, KHÔNG đổi assignee, KHÔNG đụng OS/ZPI.

## Alternatives Considered

1. Read-only (chỉ gợi ý, người dùng tự tạo ticket). Bị thay vì giảm thao tác thủ công là
   giá trị chính.
2. Tự động tạo ticket không hỏi. Bị loại: rủi ro tạo nhầm; phải có người xác nhận.
3. Nút xác nhận cứng (UI action) thay vì prompt-gate. Tốt hơn về đảm bảo nhưng tốn công;
   để nâng cấp sau (xem Follow-Up).

## Consequences

Positive:

- Khép kín luồng: phát hiện → gợi ý runbook → tạo ticket thực thi, ngay trong chat.
- Description ADF render đẹp (heading/đậm/code block/link).

Tradeoffs / Risk:

- Confirmation gate dựa trên prompt (best-effort), không phải ràng buộc cứng — về lý
  thuyết model có thể tạo khi chưa xác nhận rõ ràng. Chấp nhận cho hackathon; theo dõi.
- Agent có credential ghi Jira (qua token cấu hình) — giới hạn ở project CICD.

## Follow-Up

- Nếu cần chắc chắn hơn: thêm nút xác nhận cứng (Chainlit action) hoặc chặn theo người dùng.
- ✅ (v16) Đã đính **issue link "Relates"** giữa ticket CICD mới và ticket nguồn
  (`create_cicd_ticket(source_ticket=...)` → `rest/api/3/issueLink`).
