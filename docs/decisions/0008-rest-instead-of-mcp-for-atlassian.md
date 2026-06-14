# 0008 REST API thay vì MCP cho Jira/Confluence

Date: 2026-06-13

## Status

Accepted

## Context

PRODUCT_CONTEXT bản đầu ghi Jira/Confluence access qua **MCP server**. Với deadline
hackathon (~4 ngày) và mục tiêu "dựng agent nhanh", cần đánh giá lại liệu MCP có
phải là phương tiện nhanh nhất không. Nhu cầu thực tế chia 2:

- Khối A (poll): chỉ chạy vài câu JQL cố định cho 2 project `OS` + `ZPI`.
- Khối B (chat): cần tool động để agent tra cứu ticket/Confluence.

## Decision

Truy cập Jira/Confluence bằng **REST API trực tiếp** (`atlassian-python-api`),
wrap thành LangChain tools (`search_jira`, `get_ticket`, `search_confluence`).
Khối A gọi thẳng các tool đó với JQL cố định; khối B để agent tự gọi qua
tool-calling. Token Atlassian inject qua `--env-file` lúc deploy.

## Alternatives Considered

1. `mcp-atlassian` server chạy stdio trong container + `langchain-mcp-adapters`.
   Cân nhắc kỹ — đúng tinh thần "MCP" và có sẵn tool — nhưng thêm subprocess +
   cấu hình auth MCP. Bị loại vì tốc độ.
2. AgentBase Resource Gateway (managed MCP proxy). Bị loại: nhiều cấu hình
   gateway/policy, over-engineer cho 4 ngày.

## Consequences

Positive:

- Ít mảnh ghép nhất, kiểm soát hoàn toàn payload/JQL, deploy là chạy.
- Một client REST dùng chung cho cả khối A và B.

Tradeoffs:

- Lệch chữ "MCP" trong product context gốc.
- Phải tự viết wrapper thay vì dùng tool MCP có sẵn.

## Follow-Up

- Nếu sau hackathon muốn chuẩn hoá theo MCP, có thể swap layer tool sang
  `mcp-atlassian` mà không đổi agent logic.
