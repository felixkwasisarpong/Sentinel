from __future__ import annotations

from ..agents.crewai_runner import run_crewai


class CrewAIOrchestrator:
    name = "crewai"

    def run(
        self,
        task: str,
        *,
        sentinel_client_or_core=None,
        tool_backend=None,
    ) -> dict:
        return run_crewai(task)
