# 0009 Chainlit thay vì Copilot Kit cho UI

Date: 2026-06-13

## Status

Accepted

## Context

PRODUCT_CONTEXT bản đầu ghi Chat UI = Copilot Kit. Nhưng Copilot Kit là React
frontend nói qua giao thức CopilotKit/AG-UI; để nối vào custom LangChain agent
cần dựng CopilotKit runtime + agent adapter (thường phải viết agent dạng
LangGraph). Đây là chỗ tốn thời gian nhất trong 4 ngày. Runtime AgentBase
Custom Agent thì framework-agnostic — chỉ cần container nghe port 8080 và trả
`GET /health` 200 (đã xác nhận trong skill agentbase-deploy/wizard).

## Decision

Dùng **Chainlit** làm UI cho MVP. Chainlit nền FastAPI nên:

- Mount được `/health` trên port 8080 → thỏa runtime contract.
- Tích hợp LangChain native (callback), nối MiniMax M2.5 nhanh.
- Một process/container/replica — khớp single-replica đã chốt.
- Report xem qua lệnh `/report` (kéo report pre-computed từ SQLite), không cần
  trang dashboard riêng.

Copilot Kit chuyển xuống future.

## Alternatives Considered

1. Copilot Kit trên LangGraph + AG-UI. Đẹp/đúng doc nhất nhưng rủi ro thời gian
   cao nhất. Để future.
2. Streamlit/Gradio. Khả thi nhưng tích hợp LangChain + serve /health kém gọn
   hơn Chainlit.
3. Trang dashboard HTML riêng (Jinja2). Bị loại ở MVP: user chọn xem report
   qua lệnh `/report` trong chat cho nhanh.

## Consequences

Positive:

- Rủi ro thời gian thấp, chắc chắn có UI demo.
- 1 container lo cả chat + report + health + scheduler.

Tradeoffs:

- Lệch Copilot Kit trong product context gốc.
- UI kém "sản phẩm" hơn Copilot Kit (chấp nhận cho hackathon).

## Follow-Up

- Nếu nâng cấp lên Copilot Kit sau này, cần refactor agent khối B sang LangGraph.
