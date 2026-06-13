# Product Context — Jira Triage Bot

> Claw-a-thon 2026 · VNG Group · GreenNode AgentBase
> Last updated: 2026-06-13

---

## Vấn đề

Hiện tại, OP và FA phải thủ công phân phối và theo dõi Jira ticket cho từng thành viên trong team (a Khang, C Trần, a Tùng, Quang). Quy trình này phân tán, tốn sức người, dễ bỏ sót context, và không có cơ chế suggest giải pháp dựa trên kinh nghiệm cũ.

---

## Giải pháp

AI Bot tự động scan, tổng hợp và phân tích Jira ticket được assign cho team — kết hợp với Confluence để suggest hướng giải quyết từ các case đã có.

**Workflow chính:**

1. OP/FA assign ticket trên Jira cho các thành viên (Quang, a Khang, chị Trần) như bình thường — không thay đổi quy trình hiện tại
2. Agent dùng **Account Jira Recon** tự động scan ticket từ 2 project `OS` (Operation Support) và `ISSUE` (ZaloPay Production Issue), lọc `type = Support / Production Support`, `assignee là các thành viên trong team`
3. Agent phân tích, phân loại và tổng hợp báo cáo hiển thị trên Copilot Kit UI
4. Các thành viên cũng có thể **chủ động gửi ticket vào UI** để hỏi agent về hướng xử lý

---

## Polling Architecture

Bot hoạt động theo **2 tầng poll**:

### Tầng 1 — Report Trigger (2 lần/ngày)

| Thời điểm | Hành động |
|-----------|-----------|
| **9:00 AM** | Kéo toàn bộ ticket, tổng hợp báo cáo đầu ngày, push ra Zalo/Telegram |
| **17:30** | Kéo toàn bộ ticket, tổng hợp báo cáo cuối ngày, push ra Zalo/Telegram |

### Tầng 2 — Background Sync (mỗi 30 phút)

- Dùng **Account Jira Recon** poll Jira, lọc ticket từ 2 project:
  - **Operation Support** (`OS`) — `type = Support`
  - **ZaloPay Production Issue** (`ISSUE`) — `type = Support` hoặc `Production Support`
  - `assignee là các thành viên trong team`
- Không push notification, chỉ update internal state
- Khi team member chat hỏi trên UI → bot trả lời từ data đã sync, không cần gọi Jira real-time → response nhanh

> **Open question:** Nếu có ticket critical/urgent mới tạo giữa ngày, có cần alert ngay không hay chờ 17:30?

---

## Output của Bot

Với mỗi batch ticket (report trigger), bot tạo:

1. **Thống kê issues PRD** — tổng quan số lượng, trạng thái
2. **Phân loại từng ticket** theo:
   - Độ phức tạp (complexity)
   - Risk level
   - PIC (Person In Charge)
3. **Suggest hướng giải quyết** — nếu tìm thấy case tương tự trong Confluence, link đến guide và đề xuất approach

---

## Kênh phân phối

### Phase hiện tại (MVP)

- **Copilot Kit UI** — giao diện chính. Quang, a Khang, chị Trần truy cập để xem báo cáo phân tích và chat hỏi agent về ticket được assign cho mình. OP/FA không cần thay đổi quy trình — vẫn assign ticket trên Jira như bình thường.

### Phase sau (future)

- **Zalo**: Thêm bot vào group, mention để notify team — chưa thực hiện trong hackathon này
- **Telegram**: Qua BotFather — chưa thực hiện trong hackathon này

---

## Tech Stack

| Thành phần | Công nghệ |
|-----------|-----------|
| Jira access | MCP server |
| Confluence access | MCP server |
| Workflow / orchestration | LangChain |
| Chat UI | Copilot Kit UI |
| Runtime | GreenNode AgentBase — **Custom Agent** (có Dockerfile, backend riêng) |
| Model | *(chưa xác định — cần chọn từ GreenNode MaaS)* |
| Notification | Zalo Bot + Telegram BotFather |

> **Custom Agent vs OpenClaw:** Dự án dùng Custom Agent runtime thay vì OpenClaw 1-click. Điều này cho phép kiểm soát hoàn toàn logic orchestration, polling scheduler, và tích hợp MCP — nhưng yêu cầu Dockerfile và pipeline deploy riêng.

---

## Luồng tổng thể

```
[Jira: OS + ISSUE] ←── Account Jira Recon ──poll 30 phút──► [Agent internal state]
  (type=Support/ProductionSupport, assignee=team)               │
                                               ┌────────┤
                                               │ 9:00   │ 17:30
                                               ▼        ▼
                                          [Report Engine] ◄── [Confluence MCP]
                                               │            (tìm case tương tự)
                                               ▼
                                        [Copilot Kit UI]
                                   (team xem báo cáo, chat hỏi)

OP/FA ──assign ticket──► Jira (quy trình không đổi)
Team member ──chat──► [Bot] ──► trả lời từ internal state
```

---

## Scope Claw-a-thon 2026

- **Hạn nộp bài:** 17/06/2026 · 12:00
- **Thời gian phát triển còn lại:** ~4 ngày (tính từ 13/06)
- **Platform target:** GreenNode AgentBase — Custom Agent runtime (không dùng OpenClaw)

### MVP cần có

- [ ] Jira MCP kết nối, poll được ticket
- [ ] Phân loại ticket (complexity, risk, PIC)
- [ ] Report hiển thị trên Copilot Kit UI
- [ ] Background sync 30 phút
- [ ] Report trigger 9:00 và 17:30

### Nice-to-have (nếu còn thời gian)

- [ ] Confluence MCP — suggest case tương tự
- [ ] Alert ngay cho ticket urgent/critical

### Future (sau hackathon)

- [ ] Zalo group bot integration
- [ ] Telegram BotFather integration

---

## Liên hệ

- **Team:** longnh17@vng.com.vn
- **Event:** Claw-a-thon 2026 — GreenNode × VNG Group
