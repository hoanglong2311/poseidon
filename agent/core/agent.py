"""Chat agent (block B): MiniMax M2.5 + Jira/Confluence tools via LangChain.

Answers team questions about tickets — preferring the synced SQLite state for speed,
with live Jira/Confluence lookups when needed.
"""
import contextvars
import json
import os

from langchain.agents import create_agent
from langchain_core.tools import tool

from . import store, jira_client
from .llm import chat_llm, strip_think

# URL dashboard tổng hợp FA/OP (read-only) — đưa cho user khi họ hỏi về dashboard.
DASHBOARD_URL = os.getenv(
    "DASHBOARD_URL",
    "https://endpoint-48095726-fd41-4c0a-b174-57656c1f8b2b.agentbase-runtime.aiplatform.vngcloud.vn/dashboard",
)

# Ai đang yêu cầu (đặt bởi ask_sync) — để ghi vào comment ngược + audit.
CURRENT_ACTOR: contextvars.ContextVar[str] = contextvars.ContextVar("actor", default="?")

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
    "1) get_jira_ticket để ĐỌC KỸ vấn đề thực sự của ticket (cả mô tả/description, không chỉ tiêu đề).\n"
    "2) list_available_runbooks: mỗi runbook có {title, summary (Problem/Requirement), sample_tickets}.\n"
    "   CHỌN runbook bằng cách MAP **nội dung vấn đề của ticket** với **summary (Problem) + sample_tickets**\n"
    "   của runbook — KHÔNG chọn chỉ vì tiêu đề trùng từ khoá. Tiêu đề hay gây bẫy: vd ticket nhắc\n"
    "   'IBFT/VPB' không có nghĩa là chọn runbook có 'IBFT/VPB' trong tên nếu Problem không khớp.\n"
    "   • Nếu KEY của ticket đang hỏi nằm trong sample_tickets của 1 runbook → đó gần như chắc chắn\n"
    "     là runbook đúng (runbook đó dùng chính ticket này làm ví dụ).\n"
    "   • Nếu không, chọn runbook có Problem mô tả đúng loại việc của ticket.\n"
    "3) read_confluence_page (các) runbook ứng viên để ĐỌC các bước (đọc 2-3 cái nếu còn phân vân giữa các Problem gần giống).\n"
    "4) reason xem runbook nào Problem khớp nhất với ticket, rồi TÓM TẮT các bước áp dụng cho ticket này, kèm link.\n"
    "5) Sau khi đưa runbook + các bước, HỎI user: 'Bạn có muốn tôi tạo ticket CICD để nhờ SO/SRE thực hiện không?'.\n"
    "Ưu tiên list_available_runbooks hơn là đoán bằng search. Chỉ dựa trên nội dung tool trả về — không bịa bước.\n\n"
    "TẠO TICKET CICD: CHỈ gọi create_cicd_ticket KHI user đã trả lời đồng ý (có/tạo đi/ok...) ở lượt sau — "
    "TUYỆT ĐỐI không tự tạo khi chưa được xác nhận. Khi tạo: summary ngắn gọn kèm key ticket nguồn "
    "(vd '[CICD][from ZPI-4] Remove wrong IB refund data'); description gồm ticket nguồn, các bước/câu lệnh "
    "cần chạy, và link runbook. **LUÔN truyền source_ticket = key ticket gốc** (vd 'ZPI-4') để link với "
    "ticket nguồn. Sau khi tạo xong, báo lại key + link ticket CICD và xác nhận đã link với ticket gốc.\n\n"
    "DASHBOARD TỔNG HỢP FA/OP: khi user hỏi về 'dashboard', 'dashboard tổng hợp', 'bảng tổng hợp "
    "FA/OP', 'xem tổng quan ticket trên web', hay muốn xem giao diện tổng hợp/thống kê ticket — "
    "ĐƯA NGAY đường link dashboard này (read-only, mở trên trình duyệt): " + DASHBOARD_URL
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
    """Liệt kê TOÀN BỘ runbook có sẵn (trang con của trang Runbook index) —
    {id, title, url, summary, sample_tickets}. `summary` = Problem/Requirement của runbook;
    `sample_tickets` = các ticket key đính kèm làm ví dụ. Dùng cái này TRƯỚC, rồi chọn runbook
    bằng cách map NỘI DUNG ticket với summary + sample_tickets (KHÔNG chọn chỉ theo tiêu đề)."""
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
def recall_memory(query: str) -> str:
    """Tra bộ nhớ dài hạn: các rule/quy ước/fact đã lưu (vd quy ước team, cách xử lý quen thuộc).
    Gọi khi câu hỏi có thể liên quan tới rule/kinh nghiệm đã ghi nhớ."""
    try:
        from core import memory
        return memory.recall(query) or "Chưa có ghi nhớ liên quan."
    except Exception as e:
        return f"Lỗi tra bộ nhớ: {e}"


@tool
def remember(note: str) -> str:
    """Lưu 1 rule/ghi chú vào bộ nhớ dài hạn để dùng lại sau. CHỈ gọi khi user yêu cầu
    ghi nhớ (vd 'nhớ giúp...', 'ghi nhớ rule...')."""
    try:
        from core import memory
        ok = memory.remember(note)
        store.audit_add("remember", CURRENT_ACTOR.get(), (note or "")[:140])
        return "✅ Đã ghi nhớ." if ok else "Không lưu được (bộ nhớ chưa cấu hình)."
    except Exception as e:
        return f"Lỗi khi ghi nhớ: {e}"


@tool
def create_cicd_ticket(summary: str, description: str, source_ticket: str = "") -> str:
    """Tạo ticket trong project CICD (nhờ SO/SRE thực hiện theo runbook) và LINK với ticket gốc.
    CHỈ gọi khi user ĐÃ XÁC NHẬN muốn tạo.
    - summary: tiêu đề ngắn (nên kèm key ticket nguồn).
    - description: gồm ticket nguồn, các bước/câu lệnh cần chạy, và link runbook.
    - source_ticket: key ticket gốc (vd 'ZPI-4') để link 'relates to' — LUÔN truyền nếu biết."""
    try:
        actor = CURRENT_ACTOR.get()
        res = jira_client.create_jira_ticket(summary, description, link_to=source_ticket or None)
        # Ghi ngược comment vào ticket gốc (kèm key/url mới) — audit trail trên Jira.
        if res.get("key") and source_ticket:
            res["commented"] = jira_client.add_comment(
                source_ticket,
                f"🤖 **Poseidon**: đã tạo ticket xử lý **{res['key']}** ({res.get('url')}) "
                f"cho ticket này theo runbook — yêu cầu bởi {actor}.")
        if res.get("key"):
            store.track_cicd(res["key"], source_ticket or "", "")  # theo dõi vòng đời
        store.audit_add("create_cicd_ticket", actor,
                        f"{res.get('key')} <- {source_ticket or '?'}")
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return f"Lỗi tạo ticket CICD: {e}"


_READONLY_NOTE = (
    "\n\nLƯU Ý KÊNH NÀY (Zalo, read-only):\n"
    "- KHÔNG tạo được ticket CICD ở đây. Nếu user muốn tạo, hướng dẫn mở web UI.\n"
    "- KHÔNG dùng bảng markdown (Zalo không hiển thị bảng). Trình bày dạng **danh sách "
    "gạch đầu dòng** ngắn gọn — mỗi ticket 1 dòng: `KEY — tiêu đề — trạng thái — assignee`."
)

_READ_TOOLS = [list_team_tickets, get_jira_ticket, list_available_runbooks,
               search_confluence_docs, read_confluence_page, recall_memory]

_MEMORY_NOTE = (
    "\n\nBỘ NHỚ DÀI HẠN: bạn có thể nhớ rule/quy ước/fact của team. Dùng recall_memory "
    "để tra lại khi câu hỏi liên quan (vd cách xử lý quen thuộc, quy ước nội bộ)."
)

_agents: dict[bool, object] = {}


def get_agent(allow_write: bool = True):
    if allow_write not in _agents:
        if allow_write:
            _agents[allow_write] = create_agent(
                chat_llm(), tools=_READ_TOOLS + [create_cicd_ticket, remember],
                system_prompt=_SYSTEM + _MEMORY_NOTE
                + "\nKhi user yêu cầu ghi nhớ một rule/lưu ý, dùng remember để lưu.")
        else:
            _agents[allow_write] = create_agent(
                chat_llm(), tools=_READ_TOOLS,
                system_prompt=_SYSTEM + _READONLY_NOTE + _MEMORY_NOTE)
    return _agents[allow_write]


def ask_sync(messages, allow_write: bool = True, actor: str = "?") -> str:
    """Synchronous agent call. `messages` = conversation history. `actor` = ai đang
    yêu cầu (web: email OAuth; Zalo: tên/chat_id) → ghi vào comment ngược + audit.
    allow_write=False dùng cho Zalo (read-only). Run via asyncio.to_thread."""
    CURRENT_ACTOR.set(actor or "?")
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    result = get_agent(allow_write).invoke({"messages": messages})
    last = result["messages"][-1]
    content = last.content if hasattr(last, "content") else str(last)
    return strip_think(content) or "(không có nội dung trả lời)"
