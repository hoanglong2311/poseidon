"""Jira/Confluence access via REST (atlassian-python-api) — ADR 0008 (no MCP).

Block A (poll) calls search_jira with team_jql(); block B (chat) exposes these
as tools. Cloud auth = email (username) + API token.
"""
import os

JIRA_URL = os.getenv("JIRA_URL", "")
JIRA_USERNAME = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
# Use `or` (not getenv default) so EMPTY env values fall back to Jira creds —
# Confluence Cloud shares the same Atlassian account + API token.
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL") or JIRA_URL
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME") or JIRA_USERNAME
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN") or JIRA_API_TOKEN

PROJECTS = [p.strip() for p in os.getenv("JIRA_PROJECTS", "OS,ZPI").split(",") if p.strip()]
TEAM_IDS = [a.strip() for a in os.getenv("JIRA_TEAM_ACCOUNT_IDS", "").split(",") if a.strip()]
# Optional issuetype filter — leave empty to include ALL types (test data uses Story/Task,
# not Support). Set e.g. "Support,Production Support" to restrict in production.
ISSUE_TYPES = [t.strip() for t in os.getenv("JIRA_ISSUE_TYPES", "").split(",") if t.strip()]

_FIELDS = "summary,status,assignee,priority,project,issuetype,updated"
_URGENT = ("highest", "critical", "urgent", "blocker", "p1", "sev1", "sev-1")


def is_urgent(priority: str | None) -> bool:
    p = (priority or "").lower()
    return any(u in p for u in _URGENT)


def team_jql() -> str:
    """Scope JQL: the configured projects (OS, ZPI) + team assignees, optionally
    restricted by issuetype."""
    proj = ", ".join(f'"{p}"' for p in PROJECTS)
    jql = f"project in ({proj})"
    if ISSUE_TYPES:
        types = ", ".join(f'"{t}"' for t in ISSUE_TYPES)
        jql += f" AND issuetype in ({types})"
    if TEAM_IDS:
        ids = ", ".join(f'"{a}"' for a in TEAM_IDS)
        jql += f" AND assignee in ({ids})"
    return jql + " ORDER BY priority DESC, updated DESC"


def _jira():
    from atlassian import Jira

    if not (JIRA_URL and JIRA_USERNAME and JIRA_API_TOKEN):
        raise RuntimeError("Jira credentials missing (JIRA_URL/JIRA_USERNAME/JIRA_API_TOKEN).")
    return Jira(url=JIRA_URL, username=JIRA_USERNAME, password=JIRA_API_TOKEN, cloud=True)


def _simplify(issue: dict) -> dict:
    f = issue.get("fields", {}) or {}
    assignee = f.get("assignee") or {}
    return {
        "key": issue.get("key"),
        "project": (f.get("project") or {}).get("key"),
        "summary": f.get("summary"),
        "status": (f.get("status") or {}).get("name"),
        "assignee": assignee.get("displayName"),
        "assignee_id": assignee.get("accountId"),
        "priority": (f.get("priority") or {}).get("name"),
    }


CICD_PROJECT = os.getenv("CICD_PROJECT", "CICD")

import re as _re


_INLINE = _re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|https?://\S+)")


def _inline_nodes(text: str) -> list:
    """Parse inline markdown in a line → ADF text nodes with marks
    (**bold**, `code`, [label](url), bare URL)."""
    out = []
    for tok in _INLINE.split(text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            out.append({"type": "text", "text": tok[2:-2], "marks": [{"type": "strong"}]})
        elif tok.startswith("`") and tok.endswith("`") and len(tok) > 2:
            out.append({"type": "text", "text": tok[1:-1], "marks": [{"type": "code"}]})
        elif tok.startswith("[") and "](" in tok and tok.endswith(")"):
            label = tok[1:tok.index("]")]
            url = tok[tok.index("](") + 2:-1]
            out.append({"type": "text", "text": label or url,
                        "marks": [{"type": "link", "attrs": {"href": url}}]})
        elif tok.startswith("http://") or tok.startswith("https://"):
            out.append({"type": "text", "text": tok, "marks": [{"type": "link", "attrs": {"href": tok}}]})
        else:
            out.append({"type": "text", "text": tok})
    return out


def _md_to_adf(text: str) -> dict:
    """Lightweight Markdown → Atlassian Document Format. Handles ``` code fences ```
    (→ codeBlock), blank-line paragraphs (single \\n → hardBreak), and inline marks
    (**bold**, `code`, links). Jira Cloud renders ADF, not raw markdown."""
    content = []
    parts = _re.split(r"```[a-zA-Z0-9]*\n?(.*?)```", text or "", flags=_re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2 == 1:  # inside a code fence
            code = part.rstrip("\n")
            if code:
                content.append({"type": "codeBlock", "content": [{"type": "text", "text": code}]})
        else:
            for para in (p.strip() for p in part.split("\n\n")):
                if not para:
                    continue
                nodes = []
                for j, ln in enumerate(para.split("\n")):
                    if j > 0:
                        nodes.append({"type": "hardBreak"})
                    nodes.extend(_inline_nodes(ln))
                if nodes:
                    content.append({"type": "paragraph", "content": nodes})
    if not content:
        content = [{"type": "paragraph", "content": [{"type": "text", "text": text or " "}]}]
    return {"type": "doc", "version": 1, "content": content}


def create_jira_ticket(summary: str, description: str, project: str | None = None,
                       issuetype: str = "Task", link_to: str | None = None,
                       link_type: str = "Relates") -> dict:
    """Create a Jira issue (default project CICD, type Task) with an ADF description.
    If link_to is given (a source ticket key), link the new ticket to it. Returns
    {key, url, linked_to}."""
    project = project or CICD_PROJECT
    j = _jira()
    payload = {
        "fields": {
            "project": {"key": project},
            "summary": summary[:250],
            "description": _md_to_adf(description),
            "issuetype": {"name": issuetype},
        }
    }
    res = j.post("rest/api/3/issue", json=payload)
    key = res.get("key") if isinstance(res, dict) else None
    site = JIRA_URL.rstrip("/")
    out = {"key": key, "url": f"{site}/browse/{key}" if key else None, "linked_to": None}

    if key and link_to:
        try:
            j.post("rest/api/3/issueLink", json={
                "type": {"name": link_type},
                "inwardIssue": {"key": link_to},      # source ticket
                "outwardIssue": {"key": key},          # new CICD ticket
            })
            out["linked_to"] = link_to
        except Exception as e:
            out["link_error"] = str(e)[:120]
    return out


def search_jira(jql: str, limit: int = 50) -> list[dict]:
    """Run a JQL query and return simplified ticket dicts."""
    res = _jira().jql(jql, limit=limit, fields=_FIELDS)
    return [_simplify(i) for i in (res or {}).get("issues", [])]


def get_ticket(key: str) -> dict:
    """Fetch a single issue (incl. description) by key."""
    issue = _jira().issue(key, fields=_FIELDS + ",description")
    out = _simplify(issue)
    out["description"] = (issue.get("fields", {}) or {}).get("description")
    return out


def search_confluence(text: str, limit: int = 5) -> list[dict]:
    """Search Confluence for similar cases. Returns title + link."""
    from atlassian import Confluence

    if not (CONFLUENCE_URL and CONFLUENCE_API_TOKEN):
        return []
    conf = Confluence(
        url=CONFLUENCE_URL,
        username=CONFLUENCE_USERNAME,
        password=CONFLUENCE_API_TOKEN,
        cloud=True,
    )
    safe = text.replace('"', " ").strip()[:200]
    # `text ~` searches page body (works on this instance); `siteSearch` returned nothing.
    results = conf.cql(f'text ~ "{safe}"', limit=limit) or {}
    # Phrase match can miss multi-word queries — fall back to OR of meaningful words.
    if not results.get("results"):
        words = [w for w in safe.split() if len(w) > 2]
        if words:
            cql = " OR ".join(f'text ~ "{w}"' for w in words[:6])
            results = conf.cql(cql, limit=limit) or {}
    out = []
    site = CONFLUENCE_URL.rstrip("/").removesuffix("/wiki")  # site root, no /wiki
    for r in results.get("results", []):
        content = r.get("content", {}) or {}
        webui = ((content.get("_links") or {}).get("webui")) or r.get("url") or ""
        out.append({
            "id": content.get("id"),
            "title": content.get("title") or r.get("title"),
            "url": f"{site}/wiki{webui}" if webui.startswith("/") else webui,
        })
    return out


def _confluence():
    from atlassian import Confluence

    return Confluence(
        url=CONFLUENCE_URL,
        username=CONFLUENCE_USERNAME,
        password=CONFLUENCE_API_TOKEN,
        cloud=True,
    )


RUNBOOK_PAGE_ID = os.getenv("CONFLUENCE_RUNBOOK_PAGE_ID", "360449")  # [OPF-RC] Runbook index


def list_runbooks() -> list[dict]:
    """List the runbooks available under the Runbook index page (its child pages).
    Lets the agent see the full catalog and reason which one fits, instead of guessing
    via keyword search. The index page body itself is empty — content is in the children.
    """
    if not (CONFLUENCE_URL and CONFLUENCE_API_TOKEN and RUNBOOK_PAGE_ID):
        return []
    conf = _confluence()
    site = CONFLUENCE_URL.rstrip("/").removesuffix("/wiki")
    try:
        kids = list(conf.get_page_child_by_type(RUNBOOK_PAGE_ID, type="page", start=0, limit=100))
    except Exception:
        return []
    out = []
    for k in kids:
        webui = ((k.get("_links") or {}).get("webui")) or ""
        out.append({
            "id": k.get("id"),
            "title": k.get("title"),
            "url": f"{site}/wiki{webui}" if webui.startswith("/") else f"{site}/wiki/pages/viewpage.action?pageId={k.get('id')}",
        })
    return out


def get_confluence_page(page_id: str) -> dict:
    """Fetch a Confluence page's full body as plain text (for the agent to reason over)."""
    from bs4 import BeautifulSoup

    if not (CONFLUENCE_URL and CONFLUENCE_API_TOKEN):
        return {"error": "Confluence credentials missing."}
    conf = _confluence()
    page = conf.get_page_by_id(page_id, expand="body.storage")
    body = (((page.get("body") or {}).get("storage") or {}).get("value")) or ""
    if not body:  # some pages render only via view
        page = conf.get_page_by_id(page_id, expand="body.view")
        body = (((page.get("body") or {}).get("view") or {}).get("value")) or ""
    text = BeautifulSoup(body, "html.parser").get_text("\n", strip=True)
    site = CONFLUENCE_URL.rstrip("/").removesuffix("/wiki")
    webui = ((page.get("_links") or {}).get("webui")) or ""
    return {
        "id": page_id,
        "title": page.get("title"),
        "url": f"{site}/wiki{webui}" if webui.startswith("/") else "",
        "body": text[:6000],
    }

