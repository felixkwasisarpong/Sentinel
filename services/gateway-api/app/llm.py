# services/gateway-api/app/llm.py
import os
from functools import lru_cache

from crewai import LLM
from langchain_ollama import ChatOllama


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v else default


@lru_cache(maxsize=1)
def get_crewai_llm() -> LLM:
    """
    CrewAI LLM configured to talk to Ollama via Ollama's OpenAI-compatible endpoint (/v1).
    This avoids OpenAI subscriptions; OPENAI_API_KEY is a dummy value to satisfy CrewAI's checks.
    """
    # Prefer explicit OpenAI-compatible envs (best for CrewAI)
    api_base = _env("OPENAI_API_BASE", "")

    # Fallback: derive OpenAI-compatible base from OLLAMA_BASE_URL
    if not api_base:
        ollama_base = _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        api_base = f"{ollama_base}/v1"

    model = _env("OPENAI_MODEL_NAME", _env("OLLAMA_MODEL", "llama3.1:8b"))
    api_key = _env("OPENAI_API_KEY", "ollama")  # dummy, used only to satisfy validation

    return LLM(
        model=f"openai/{model}",
        base_url=api_base,
        api_key=api_key,
        temperature=0.0,
    )

@lru_cache(maxsize=1)
def get_langchain_chat_llm() -> ChatOllama:
    """
    LangChain Chat model configured for Ollama.
    """
    base_url = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    model = _env("OLLAMA_MODEL", "llama3.1:8b")

    # LangChain Ollama chat uses ChatOllama from the langchain-ollama package  [oai_citation:3‡docs.langchain.com](https://docs.langchain.com/oss/python/integrations/chat/ollama)
    # base_url is supported as an init arg in langchain_ollama.  [oai_citation:4‡reference.langchain.com](https://reference.langchain.com/python/integrations/langchain_ollama/)
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0,
    )