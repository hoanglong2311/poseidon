"""Chat agent (block B): MiniMax M2.5 + Jira/Confluence tools via LangChain.

Answers team questions about tickets — preferring the synced SQLite state for speed,
with live Jira/Confluence lookups when needed.
"""
import json

from langchain.agents import create_agent
from langchain_core.tools import tool

from . import store, jira_client
from .llm import chat_llm, strip_think

_SYSTEM = (
    "Bạn là Poseidon, trợ lý triage ticket Jira cho team hỗ trợ ZaloPay. "
    "Trả lời ngắn gọn, rõ ràng bằng tiếng Việt.\n"
    "Công cụ:\n"
    "- list_team_tickets: danh sách ticket đã sync (nhanh).\n"
    "- get_jira_ticket(key): chi tiết 1 ticket (gồm mô tả).\n"
    "- list_available_runbooks(): TOÀN BỘ runbook có sẵn (id + title + url).\n"
    "- search_confluence_docs(query): tìm thêm theo từ khoá (bổ sung).\n"
    "- read_confluence_page(page_id): ĐỌC nội dung đầy đủ 1 trang runbook.\n\n"
    "Khi user hỏi 'xử lý ticket X thế nào' hoặc cần gợi ý hướng giải quyết, LÀM ĐÚNG THỨ TỰ:\n"
    "1) get_jira_ticket để hiểu vấn đề.\n"
    "2) list_available_runbooks để XEM TRƯỚC toàn bộ runbook đang có và chọn (các) runbook phù hợp nhất theo tiêu đề.\n"
    "3) read_confluence_page (các) runbook đã chọn để ĐỌC các bước (có thể đọc 2-3 cái nếu chưa chắc).\n"
    "4) reason xem runbook nào đúng nhất và TÓM TẮT các bước áp dụng cho ticket này, kèm link.\n"
    "5) Sau khi đưa runbook + các bước, HỎI user: 'Bạn có muốn tôi tạo ticket CICD để nhờ SO/SRE thực hiện không?'.\n"
    "Ưu tiên list_available_runbooks hơn là đoán bằng search. Chỉ dựa trên nội dung tool trả về — không bịa bước.\n\n"
    "TẠO TICKET CICD: CHỈ gọi create_cicd_ticket KHI user đã trả lời đồng ý (có/tạo đi/ok...) ở lượt sau — "
    "TUYỆT ĐỐI không tự tạo khi chưa được xác nhận. Khi tạo: summary ngắn gọn kèm key ticket nguồn "
    "(vd '[CICD][from ZPI-4] Remove wrong IB refund data'); description gồm ticket nguồn, các bước/câu lệnh "
    "cần chạy, và link runbook. **LUÔN truyền source_ticket = key ticket gốc** (vd 'ZPI-4') để link với "
    "ticket nguồn. Sau khi tạo xong, báo lại key + link ticket CICD và xác nhận đã link với ticket gốc."
)


@tool
def list_team_tickets() -> str:
    """Liệt kê các ticket của team đã được sync (key, tiêu đề, trạng thái, assignee, priority, phân loại)."""
    tickets = store.all_tickets()
    if not tickets:
        return "Chưa có ticket nào được sync."
    return json.dumps(
        [
            {
                "key": t["key"], "summary": t.get("summary"), "status": t.get("status"),
                "assignee": t.get("assignee"), "priority": t.get("priority"),
                "complexity": t.get("complexity"), "risk": t.get("risk"),
            }
            for t in tickets
        ],
        ensure_ascii=False,
    )


@tool
def get_jira_ticket(key: str) -> str:
    """Lấy chi tiết một ticket Jira theo key (vd 'OS-123'), gồm cả mô tả."""
    try:
        return json.dumps(jira_client.get_ticket(key), ensure_ascii=False)
    except Exception as e:
        return f"Lỗi khi lấy ticket {key}: {e}"


@tool
def list_available_runbooks() -> str:
    """Liệt kê TOÀN BỘ runbook có sẵn (trang con của trang Runbook index) — {id, title, url}.
    Dùng cái này TRƯỚC để thấy danh sách runbook, rồi chọn cái phù hợp với ticket."""
    try:
        rbs = jira_client.list_runbooks()
        return json.dumps(rbs, ensure_ascii=False) if rbs else "Không lấy được danh sách runbook."
    except Exception as e:
        return f"Lỗi khi liệt kê runbook: {e}"


@tool
def search_confluence_docs(query: str) -> str:
    """Tìm runbook/tài liệu Confluence theo từ khoá (bổ sung cho list_available_runbooks).
    Trả về {id, title, url}. Dùng id với read_confluence_page để đọc nội dung."""
    try:
        docs = jira_client.search_confluence(query)
        return json.dumps(docs, ensure_ascii=False) if docs else "Không tìm thấy tài liệu phù hợp."
    except Exception as e:
        return f"Lỗi khi tìm Confluence: {e}"


@tool
def read_confluence_page(page_id: str) -> str:
    """Đọc NỘI DUNG đầy đủ của một trang runbook Confluence theo page_id (lấy từ search_confluence_docs)."""
    try:
        return json.dumps(jira_client.get_confluence_page(page_id), ensure_ascii=False)
    except Exception as e:
        return f"Lỗi khi đọc trang {page_id}: {e}"


@tool
def create_cicd_ticket(summary: str, description: str, source_ticket: str = "") -> str:
    """Tạo ticket trong project CICD (nhờ SO/SRE thực hiện theo runbook) và LINK với ticket gốc.
    CHỈ gọi khi user ĐÃ XÁC NHẬN muốn tạo.
    - summary: tiêu đề ngắn (nên kèm key ticket nguồn).
    - description: gồm ticket nguồn, các bước/câu lệnh cần chạy, và link runbook.
    - source_ticket: key ticket gốc (vd 'ZPI-4') để link 'relates to' — LUÔN truyền nếu biết."""
    try:
        return json.dumps(
            jira_client.create_jira_ticket(summary, description, link_to=source_ticket or None),
            ensure_ascii=False,
        )
    except Exception as e:
        return f"Lỗi tạo ticket CICD: {e}"


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            chat_llm(),
            tools=[list_team_tickets, get_jira_ticket, list_available_runbooks,
                   search_confluence_docs, read_confluence_page, create_cicd_ticket],
            system_prompt=_SYSTEM,
        )
    return _agent


def ask_sync(messages) -> str:
    """Synchronous agent call. `messages` is the conversation history (list of
    {role, content}) so multi-turn flows (gợi ý → hỏi → xác nhận → tạo ticket) work.
    A plain string is also accepted for a single-turn call.
    Run via asyncio.to_thread from the Chainlit handler so blocking tool HTTP calls
    never stall the event loop."""
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    result = get_agent().invoke({"messages": messages})
    last = result["messages"][-1]
    content = last.content if hasattr(last, "content") else str(last)
    return strip_think(content) or "(không có nội dung trả lời)"
