from __future__ import annotations

from .base import Orchestrator
from .autogen import AutoGenOrchestrator
from .crewai import CrewAIOrchestrator
from .langgraph import LangGraphOrchestrator


ORCHESTRATORS: dict[str, Orchestrator] = {
    "langgraph": LangGraphOrchestrator(),
    "crewai": CrewAIOrchestrator(),
    "autogen": AutoGenOrchestrator(),
}


def _normalize_orchestrator(name: str | None) -> str:
    n = (name or "").strip().lower()
    if n in ("", "default"):
        return "langgraph"
    if n in ("langgraph", "lg"):
        return "langgraph"
    if n in ("crewai", "crew"):
        return "crewai"
    if n in ("autogen", "agentchat", "ag"):
        return "autogen"
    return n


def get_orchestrator(name: str | None) -> Orchestrator:
    key = _normalize_orchestrator(name)
    orchestrator = ORCHESTRATORS.get(key)
    if not orchestrator:
        raise ValueError(f"Unknown orchestrator: {name}")
    return orchestrator
