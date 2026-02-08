from __future__ import annotations

from ..agents.autogen_runner import run_autogen


class AutoGenOrchestrator:
    name = "autogen"

    def run(
        self,
        task: str,
        *,
        sentinel_client_or_core=None,
        tool_backend=None,
    ) -> dict:
        return run_autogen(task)
