# Poseidon — Jira Triage Bot · Claw-a-thon 2026

> **Project:** AI Agent tự động hóa luồng rà soát và phân loại Jira ticket cho team (OP/FA vẫn assign như cũ) — đọc runbook Confluence để gợi ý hướng xử lý. Chat qua Chainlit, push qua Zalo. 🟢 Đã deploy trên AgentBase.
>
> **Event:** Claw-a-thon 2026 · VNG Group · GreenNode AgentBase
> **Hạn nộp bài:** 17/06/2026 · 12:00
>
> **Product context:** [`docs/product/PRODUCT_CONTEXT.md`](docs/product/PRODUCT_CONTEXT.md)

---

## Mô tả AI Agent

Được xây dựng trên hạ tầng **GreenNode AgentBase** theo mô hình **Spec-Driven Development**, **Poseidon** tự động hóa luồng rà soát và phân loại Jira ticket ngay khi khởi tạo nhằm giải quyết bài toán quá tải hệ thống và chậm trễ SLA.

Agent liên tục rà soát ticket mới, phân tích ngữ cảnh để truy vấn kho tri thức **Runbook từ Confluence**, từ đó chủ động gửi báo cáo kèm gợi ý xử lý tới kỹ sư qua **Zalo** hoặc **Chatbox**.

Điểm nhấn của dự án là **Trung tâm điều khiển (Dashboard)** dành riêng cho bộ phận Vận hành và Tài chính (**OP/FA**) giúp trực quan hóa dữ liệu theo thời gian thực, hiển thị xu hướng sự cố và đánh giá hiệu suất của Agent. Sự kết hợp này giúp các điều phối viên có cái nhìn toàn cảnh để giám sát chất lượng gợi ý từ AI, đưa ra quyết định chính xác và giảm thiểu thời gian phục hồi dịch vụ (**MTTR**) mà không làm thay đổi quy trình phân luồng nhân sự truyền thống.

---

## 🔑 Tài khoản đăng nhập thử (cho Giám khảo)

Dùng tài khoản dưới đây để đăng nhập và trải nghiệm Dashboard / Chatbox:

| Username | Password |
|----------|----------|
| `giamkhao` | `poseidon2026` |

---
