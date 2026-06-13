# Product Context — Jira Triage Bot

> Claw-a-thon 2026 · VNG Group · GreenNode AgentBase
> Last updated: 2026-06-13

---

## Vấn đề

Hiện tại, OP và FA phải thủ công phân phối và theo dõi Jira ticket cho từng thành viên trong team (a Khang, C Trần, a Tùng, Quang). Quy trình này phân tán, tốn sức người, dễ bỏ sót context, và không có cơ chế suggest giải pháp dựa trên kinh nghiệm cũ.

---

## Giải pháp

AI Bot tự động tổng hợp, phân tích và phân phối Jira ticket — kết hợp với Confluence để suggest hướng giải quyết từ các case đã có.

---

## Polling Architecture

Bot hoạt động theo **2 tầng poll**:

### Tầng 1 — Report Trigger (2 lần/ngày)

| Thời điểm | Hành động |
|-----------|-----------|
| **9:00 AM** | Kéo toàn bộ ticket, tổng hợp báo cáo đầu ngày, push ra Zalo/Telegram |
| **17:30** | Kéo toàn bộ ticket, tổng hợp báo cáo cuối ngày, push ra Zalo/Telegram |

### Tầng 2 — Background Sync (mỗi 30 phút)

- Poll Jira liên tục trong giờ làm việc để agent luôn có data mới nhất
- Không push notification, chỉ update internal state
- Khi user chat hỏi → bot trả lời từ data đã sync, không cần gọi Jira real-time → response nhanh

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

- **Zalo**: Bot được thêm vào group, mention để notify team
- **Telegram**: Qua BotFather

---

## Tech Stack

| Thành phần | Công nghệ |
|-----------|-----------|
| Jira access | MCP server |
| Confluence access | MCP server |
| Workflow / orchestration | LangChain |
| Chat UI | Copilot Kit UI |
| Runtime | GreenNode AgentBase (OpenClaw) |
| Model | *(chưa xác định — cần chọn từ GreenNode MaaS)* |
| Notification | Zalo Bot + Telegram BotFather |

---

## Luồng tổng thể

```
[Jira] ──poll 30 phút──► [Agent internal state]
                                  │
              ┌───────────────────┤
              │ 9:00 AM           │ 17:30
              ▼                   ▼
         [Report Engine] ◄── [Confluence MCP]
              │               (tìm case tương tự)
              ▼
    [Zalo Group / Telegram]
         (push báo cáo)

[User chat] ──► [Bot] ──► trả lời từ internal state
```

---

## Scope Claw-a-thon 2026

- **Hạn nộp bài:** 17/06/2026 · 12:00
- **Thời gian phát triển còn lại:** ~4 ngày (tính từ 13/06)
- **Platform target:** GreenNode AgentBase

### MVP cần có

- [ ] Jira MCP kết nối, poll được ticket
- [ ] Phân loại ticket (complexity, risk, PIC)
- [ ] Report format chuẩn push qua Telegram
- [ ] Background sync 30 phút
- [ ] Report trigger 9:00 và 17:30

### Nice-to-have (nếu còn thời gian)

- [ ] Confluence MCP — suggest case tương tự
- [ ] Zalo integration
- [ ] Chat UI qua Copilot Kit
- [ ] Alert ngay cho ticket urgent/critical

---

## Liên hệ

- **Team:** longnh17@vng.com.vn
- **Event:** Claw-a-thon 2026 — GreenNode × VNG Group
