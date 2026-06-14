# Notes: Deploy vllm-wiki Agent trên GreenNode AgentBase

> **Mục đích file:** Context tham chiếu cho các phiên làm việc khác. Tóm tắt + rút pattern
> từ tutorial chính thức của GreenNode, vì Poseidon deploy trên **cùng nền tảng GreenNode
> AgentBase — Custom Agent runtime**. Các kỹ thuật ở đây (handler, gọi MaaS, né timeout 60s,
> deploy vCR, wrap LangChain tool) áp dụng trực tiếp cho Poseidon.
>
> **Nguồn:** https://greennode.ai/tutorial/trien-khai-vllm-wiki-agent-tren-greennode-agentbase
> — tác giả Nguyễn Ngọc Long, đăng 02/06/2026. Đọc & note ngày 13/06/2026.

---

## 1. Tóm tắt agent là gì

**vllm-wiki Agent v1.0** — agent chạy 24/7 trên GreenNode AgentBase, tự đọc docs/URL/file →
trích xuất concepts → tạo & bảo trì wiki page interconnected (citation `[[slug]]`), lưu vào
AgentBase Memory (persistent, searchable). Dùng `google/gemma-4-31b-it` qua GreenNode AI Platform.

Triết lý gốc (Karpathy's LLM Wiki): **humans curate, LLMs maintain** — người chọn nguồn & đặt
câu hỏi; LLM lo phần "chán": cross-reference, update summary, đánh dấu mâu thuẫn.

**3 mode chính** (mỗi mode 1 function độc lập để test riêng):

- `ingest` — đưa knowledge vào (URL/file/text → 3–10 wiki page/nguồn).
- `query` — truy vấn ngôn ngữ tự nhiên → answer + citation `[[slug]]`.
- `lint` — phát hiện stale / orphan / mâu thuẫn (v1.0 chỉ chạy manual qua `mode: lint`; lint
  tự động là roadmap v1.1).

---

## 2. Tech stack (quan trọng cho Poseidon)

| Thành phần | Công nghệ |
|---|---|
| SDK runtime | `greennode-agentbase` (`GreenNodeAgentBaseApp`, `@app.entrypoint`, `RequestContext`) |
| Orchestration | LangChain |
| LLM client | `langchain_openai.ChatOpenAI` — GreenNode AI Platform là **OpenAI-compatible**, chỉ đổi `base_url` |
| Model | `google/gemma-4-31b-it` (128K context, free tier) |
| Scrape | Firecrawl (`/v1/map` + `/v1/scrape`), fallback `httpx` |
| Storage | AgentBase Memory (namespace `pages`, `manifests`) |
| Registry | vCR (`vcr.vngcloud.vn`) hoặc Docker Hub |
| Runtime | GreenNode AgentBase — managed, không tự quản K8s/scaling |

**Chuẩn bị tài khoản:**

- IAM Service Account trên `iam.console.vngcloud.vn` → `CLIENT_ID` + `CLIENT_SECRET` (gọi Memory/Identity API).
- GreenNode AI Platform API key (`aiplatform.console.vngcloud.vn`).
- Docker + Python 3.10+; vCR/Docker Hub để push image.
- (Optional) Firecrawl self-hosted/cloud.

---

## 3. Cấu trúc project tối thiểu

```
vllm-wiki-agent/
├── main.py          # entrypoint — GreenNodeAgentBaseApp handler
├── webui.py         # local UI server (stdlib, không cần Node)
├── requirements.txt
├── Dockerfile
└── .env.example
```

> `.dockerignore` **bắt buộc** có `.env`, `.greennode.json`, `venv/` — tránh leak secrets vào image.

**Env vars:**

```dotenv
GREENNODE_CLIENT_ID=        # runtime tự inject khi deploy — KHÔNG hardcode cho production
GREENNODE_CLIENT_SECRET=
LLM_API_KEY=vn-xxx          # từ aiplatform.console.vngcloud.vn
LLM_BASE_URL=https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1
LLM_MODEL=google/gemma-4-31b-it
MEMORY_ID=memory-xxxxxxxx   # tạo qua AgentBase console
FIRECRAWL_API_KEY=fc-xxx    # optional, content sạch hơn nhiều
FIRECRAWL_URL=http://firecrawl.your-cluster/
```

---

## 4. Handler pattern (áp dụng được cho Poseidon)

```python
from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext
from langchain_openai import ChatOpenAI

app = GreenNodeAgentBaseApp()
llm = ChatOpenAI(
    model=os.environ["LLM_MODEL"],
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    temperature=0.2, max_tokens=5000, timeout=55,   # timeout < 60s gateway
)

@app.entrypoint
def handler(payload: dict, ctx: RequestContext) -> dict:
    mode = payload.get("mode", "query")
    if mode == "ingest":
        text = _fetch_url(payload["url"]) if payload.get("url") else payload["text"]
        return _ingest(text, source_label=payload.get("url"))
    if mode == "query":
        return _query(payload["question"])
    if mode == "lint":
        return _lint(payload.get("topic"))
```

**Ingest flow (5 bước tuần tự):**

1. Search semantic top-5 page liên quan trong namespace `pages` (context cho LLM).
2. Gọi LLM: system prompt = schema, user prompt = source + related pages.
3. LLM trả JSON `{summary, pages: [{slug, markdown}], notes}`.
4. Insert từng page vào Memory namespace `pages`.
5. Insert manifest `{label, timestamp, summary, pages}` vào `manifests` (cho Sources tab).

---

## 5. ⭐ 3 pattern kỹ thuật quan trọng nhất

### 5.1. Né hard timeout 60s của AgentBase gateway (2-phase)

Gateway có **hard timeout 60s**. Crawl 20 URL × ~20s/page = 400s → không fit. Giải pháp tách:

- **Discover phase (~2s):** `mode: "discover"` → backend hit `/v1/map` → trả list URL ngay.
- **Ingest phase (N call song song):** UI loop N URL với **concurrency = 4**, mỗi call 15–25s (< 60s).

```js
async function worker() {
  while (cursor < urls.length) {
    const i = cursor++;
    const r = await api({ mode: 'ingest', url: urls[i] });
    results[i] = r; done++;
  }
}
await Promise.all(Array.from({ length: 4 }, worker));
```

Kết quả: crawl 20 URL từ 7 phút (serial) → ~1.5 phút (throughput 4×).
→ **Áp dụng Poseidon:** bất kỳ tác vụ batch nào (poll nhiều ticket, gọi LLM nhiều lần) phải chia
nhỏ mỗi invocation < 60s, song song hóa thay vì 1 call dài.

### 5.2. Dùng `/v1/map` thay vì `/v1/crawl` cho site có sidebar

- `/v1/crawl` → **0 URL** (bị `onlyMainContent` strip mất sidebar navigation).
- `/v1/map` → 50 URL trong 1.87s (sitemap-based).
→ Dùng `/v1/map` để discover sitemap, `/v1/scrape` để lấy content.

### 5.3. Chất lượng = schema/prompt, KHÔNG phải model size

Pin chặt schema + để Firecrawl clean content (`onlyMainContent=true`: input 480KB → 4KB) thì
Gemma 4-31B đủ tốt (đôi khi ổn định hơn GPT-4o vì output ngắn gọn, không "diễn").

**Page schema (ép trong system prompt):**

```markdown
## [[slug]]
**TL;DR:** 1–2 câu tóm tắt core idea
### Overview
### Key details
### How it works
### Use cases
### Related
- [[related-slug-1]]
### Sources
- https://nguon.url
```

> Prompt cũ "produce pages" → LLM merge nhiều source thành 1 page. Fix: nhấn mạnh "nếu source
> chứa `=== Page: URL ===` blocks thì produce ít nhất 1 page per block" → 5 URL ra 8–12 page.

---

## 6. Deploy lên AgentBase (2 cách, cùng trỏ image trên vCR)

**Cách A — Portal UI:** `aiplatform.console.vngcloud.vn/runtime` → Create Runtime → chọn vCR image
→ flavor `2x4-general` → nhập env vars → Create. Endpoint public sinh tự động; IAM credentials
được Portal inject sẵn.

**Cách B — CLI (reproducible, hợp CI/CD):**

```bash
# Login vCR
echo $VCR_PASSWORD | docker login vcr.vngcloud.vn -u $VCR_USER --password-stdin
# Build & push (LƯU Ý: --platform linux/amd64)
docker build --platform linux/amd64 -t vcr.vngcloud.vn/$REPO/vllm-wiki:latest .
docker push vcr.vngcloud.vn/$REPO/vllm-wiki:latest
# Deploy runtime
bash runtime.sh create \
  --name vllm-wiki --image vcr.vngcloud.vn/$REPO/vllm-wiki:latest \
  --flavor 2x4-general --env-file .env \
  --min-replicas 1 --max-replicas 2 --cpu-scale 50 --mem-scale 50
# Endpoint: https://invocation-agentbase.api.vngcloud.vn/runtime/endpoint-xxx
```

**Update:** rebuild + push cùng tag `:latest` → bấm Update trên Portal (hoặc `runtime.sh update`)
→ rolling restart (UPDATING → ACTIVE ~60s, zero downtime). Logs/metrics/scaling quản trong Portal.

**Gọi agent:** `POST https://<endpoint>/invocations` với body `{"mode": "...", ...}`.

---

## 7. Biến agent thành LangChain tool (agent-to-agent)

Vì agent có HTTP endpoint công khai → wrap thành 1 LangChain `@tool` cho agent khác gọi:

```python
from langchain_core.tools import tool
import httpx

VLLM_WIKI = "https://invocation-agentbase.api.vngcloud.vn/runtime/endpoint-xxx"

@tool
def vllm_wiki_lookup(question: str) -> str:
    """Look up VNG Cloud / vLLM / VKS / AI Platform docs. Use for infra & runbook questions."""
    r = httpx.post(f"{VLLM_WIKI}/invocations",
                   json={"mode": "query", "question": question}, timeout=60.0).json()
    return r.get("answer", r.get("error", "lookup failed"))

agent = create_agent(llm, tools=[*existing_tools, vllm_wiki_lookup])
```

Use case thực: sre-agent nhận alert CrashLoopBackOff lúc 3h sáng → tự gọi `vllm_wiki_lookup` lấy
runbook → xử lý + report vào Teams, không cần đánh thức người. → Wiki là "trí nhớ chung" cho cả
hệ agent.
→ **Áp dụng Poseidon:** chính là pattern bridge — agent này gọi agent/tool khác qua HTTP endpoint.

---

## 8. Smoke-test & lỗi thường gặp

```bash
# ingest
curl -X POST https://<endpoint>/invocations -H 'Content-Type: application/json' \
  -d '{"mode":"ingest","url":"https://docs.vngcloud.vn/vks"}'
# query
curl -X POST https://<endpoint>/invocations -H 'Content-Type: application/json' \
  -d '{"mode":"query","question":"VKS multi-AZ vs private cluster?"}'
# logs
bash runtime.sh logs $RUNTIME_ID --limit 100 --order desc
```

| Triệu chứng | Nguyên nhân | Fix |
|---|---|---|
| `UnicodeDecodeError` tiếng Việt | Content-Type thiếu `charset=utf-8` | Thêm `charset=utf-8` vào header (hay gặp khi curl từ Windows Git Bash) |
| Gateway 504 timeout | Crawl synchronous vượt 60s | Tách `discover` + `ingest`, mỗi call < 60s |
| Page mỏng, self-cite lặp | Source HTML nhiều noise | Re-ingest qua Firecrawl `onlyMainContent=true` + strengthen prompt |
| 400 khi runtime create | Description dùng en-dash (–) | Dùng hyphen (-) thay en-dash (Helm encoding issue) |
| Memory record reject 500 | Page > 10KB | Truncate `text[:8000] + "[truncated]"` |
| `/v1/crawl` → 0 URL | `onlyMainContent` strip sidebar | Dùng `/v1/map` |
| `insert_memory_records_directly()` TypeError | Nhận `{"memoryRecords": [text]}` chứ không phải `[text]` | Truyền đúng dict + check version SDK |

---

## 9. Kết quả đo được (tham khảo)

| Metric | Trước | Sau v1.0 |
|---|---|---|
| Time-to-info | ~15 phút | ~30 giây |
| Mở lại docs cũ | mỗi session | gần 0 |
| Incident response có dẫn nguồn | không ổn định | 100% có `[[slug]]` |
| Hallucination khi thiếu runbook | cao | gần 0 |
| Maintain wiki sau update docs | 30–60 phút/lần | tự động re-ingest |

**Roadmap tác giả nêu:** lint mode tự động (Slack DM page stale), Slack ingest bot, Memex export
(Obsidian vault), custom embeddings tiếng Việt (multilingual-e5 thay BGE-M3 mặc định).

---

## 10. Liên hệ với dự án Poseidon

- **Cùng nền tảng:** Poseidon target GreenNode AgentBase Custom Agent runtime (xem
  `docs/product/PRODUCT_CONTEXT.md`). Toàn bộ pattern deploy/handler/MaaS ở trên dùng lại được.
- **Né timeout 60s:** Poseidon poll Jira + gọi LLM nhiều lần → áp dụng 2-phase + concurrency.
- **Agent-as-tool:** pattern `@tool` + HTTP endpoint giống bridge cho Report Engine / Zalo bot
  (xem `docs/integrations/ZALO_BOT_INTEGRATION.md`).
- **MaaS OpenAI-compatible:** chọn model GreenNode MaaS chỉ cần đổi `base_url` cho `ChatOpenAI`
  — giải quyết mục "Model (chưa xác định)" trong PRODUCT_CONTEXT.
