"""LLM clients pointing at GreenNode MaaS (OpenAI-compatible endpoint).

Chat (khối B) = MiniMax M2.5 (tool-calling verified). Classify (khối A) = Qwen 3.5 27B.
MiniMax embeds reasoning in <think>...</think> — strip before display.
"""
import os
import re

CHAT_MODEL = os.getenv("LLM_MODEL_CHAT", "minimax/minimax-m2.5")
CLASSIFY_MODEL = os.getenv("LLM_MODEL_CLASSIFY", "qwen/qwen3-5-27b")
BASE_URL = os.getenv("LLM_BASE_URL", "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1")
# Accept any of the MaaS key conventions: skill (LLM_API_KEY / AIP_API_KEY)
# and BTC sample (AI_PLATFORM_API_KEY).
API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("AI_PLATFORM_API_KEY")
    or os.getenv("AIP_API_KEY")
    or ""
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove MiniMax <think>...</think> reasoning blocks before showing to user."""
    return _THINK_RE.sub("", text or "").strip()


def chat_llm(**kwargs):
    """Chat model for the LangChain agent. Lazy import so the skeleton imports
    even before deps are installed."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=CHAT_MODEL, base_url=BASE_URL, api_key=API_KEY, **kwargs)


def classify_llm(**kwargs):
    """Deterministic model for classification/report (temperature 0).

    Qwen3 has 'thinking mode' ON by default → ~1600 tokens of reasoning → ~35s/call.
    Disable it (enable_thinking=False) → ~1s/call. Cap max_tokens as a safety net.
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=CLASSIFY_MODEL,
        base_url=BASE_URL,
        api_key=API_KEY,
        temperature=0,
        max_tokens=512,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        **kwargs,
    )
