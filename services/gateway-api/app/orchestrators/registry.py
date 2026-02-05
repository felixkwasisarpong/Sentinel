from __future__ import annotations

from .base import Orchestrator
from .crewai import CrewAIOrchestrator
from .fsm_hybrid import FSMHybridOrchestrator
from .langgraph import LangGraphOrchestrator


ORCHESTRATORS: dict[str, Orchestrator] = {
    "langgraph": LangGraphOrchestrator(),
    "crewai": CrewAIOrchestrator(),
    "fsm_hybrid": FSMHybridOrchestrator(),
}


def _normalize_orchestrator(name: str | None) -> str:
    n = (name or "").strip().lower()
    if n in ("", "default"):
        return "langgraph"
    if n in ("langgraph", "lg"):
        return "langgraph"
    if n in ("fsm", "hybrid", "fsm_hybrid"):
        return "fsm_hybrid"
    if n in ("crewai", "crew"):
        return "crewai"
    return n


def get_orchestrator(name: str | None) -> Orchestrator:
    key = _normalize_orchestrator(name)
    orchestrator = ORCHESTRATORS.get(key)
    if not orchestrator:
        raise ValueError(f"Unknown orchestrator: {name}")
    return orchestrator
