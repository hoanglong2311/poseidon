# 0013 Dùng AgentBase Memory cho fact/rule dài hạn (recall + remember)

Date: 2026-06-15

## Status

Accepted

## Context

Agent cần nhớ **rule/quy ước/fact của team** xuyên phiên (vd "ticket refund luôn cần PIC
xác nhận", "backup trước khi xóa"). Trước đó chỉ có history trong phiên (web SQLite / Zalo
in-memory), không có tri thức dài hạn. AgentBase có dịch vụ **Memory** (events + long-term
memory records + strategy SEMANTIC/USER_PREFERENCE/CUSTOM).

## Decision

- Tạo memory `poseidon-mem` + strategy `semantic-facts` (SEMANTIC, auto-generate).
- **Phạm vi (đã grill): chỉ recall fact + lưu rule** — HOÃN checkpointer-history (overlap +
  rủi ro thêm dep `greennode-agent-bridge`).
- Dùng **shared actor `team`** → tri thức/rule chung cho cả đội (không phân theo từng user).
- `core/memory.py` gọi **raw REST** (httpx) thay vì SDK: SDK `greennode-agentbase` 1.0.3 cài
  được nhưng `MemoryClient` thiếu các method như doc mô tả (doc mismatch) → REST đáng tin hơn
  và không thêm dep nặng. Token lấy từ `GREENNODE_CLIENT_ID/SECRET` (runtime auto-inject).
- Tools: `recall_memory` (cả web + Zalo) để tra rule/fact; `remember` (chỉ web/write) để lưu
  — Zalo read-only không lưu được, nhất quán với ADR 0012.

## Alternatives Considered

1. Rule tĩnh trong system prompt / trang Confluence. Vẫn hợp cho rule cố định; nhưng Memory
   cho phép tích lũy + recall theo ngữ cảnh, mở rộng tốt hơn khi nhiều rule/fact.
2. Dùng SDK MemoryClient. Bị loại: SDK 1.0.3 không expose method search/insert như doc.
3. Làm cả checkpointer-history. Hoãn: overlap history hiện có + rủi ro dep với langchain 1.3.9.
4. Per-user actor. Bị loại: tri thức team nên dùng chung 1 actor.

## Consequences

Positive:

- Agent nhớ rule/quy ước/fact xuyên phiên, recall theo semantic — cả khi hỏi runbook.
- Không thêm dep nặng (raw REST + httpx có sẵn).

Tradeoffs:

- Records dùng chung actor `team` → không cô lập theo người (chấp nhận cho tri thức đội).
- Chưa có history bền qua Memory (vẫn dùng SQLite/in-memory như trước).
- `remember` chỉ ở web; Zalo chỉ recall.

## Follow-Up

- Có thể bật checkpointer-history sau (dep `greennode-agent-bridge`) nếu cần history bền.
- Có thể thêm CUSTOM strategy nếu muốn định hướng trích fact (vd chỉ trích "quyết định vận hành").
- Dọn các record test đã chèn lúc verify nếu không muốn giữ.
