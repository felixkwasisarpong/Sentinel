from __future__ import annotations

from ..agents.fsm_runner import HybridFSM


class FSMHybridOrchestrator:
    name = "fsm_hybrid"

    def run(
        self,
        task: str,
        *,
        sentinel_client_or_core=None,
        tool_backend=None,
    ) -> dict:
        fsm = HybridFSM(task)
        return fsm.run()
