from __future__ import annotations

from typing import Any, Protocol


class Orchestrator(Protocol):
    name: str

    def run(
        self,
        task: str,
        *,
        sentinel_client_or_core: Any = None,
        tool_backend: Any = None,
    ) -> dict:
        ...
