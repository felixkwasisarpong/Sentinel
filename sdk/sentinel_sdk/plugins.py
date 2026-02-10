from __future__ import annotations

from typing import Any, Protocol


class ToolBackend(Protocol):
    name: str

    def list_tools(self, *, server_name: str | None = None) -> list[dict[str, Any]]:
        ...

    def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        ...


class Orchestrator(Protocol):
    name: str

    def run(self, prompt: str, engine: Any, **kwargs: Any) -> Any:
        ...


class ToolBackendRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ToolBackend] = {}

    def register(self, backend: ToolBackend) -> None:
        self._items[str(backend.name)] = backend

    def get(self, name: str) -> ToolBackend:
        item = self._items.get(name)
        if item is None:
            raise KeyError(f"Unknown tool backend: {name}")
        return item

    def names(self) -> list[str]:
        return sorted(self._items.keys())


class OrchestratorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Orchestrator] = {}

    def register(self, orchestrator: Orchestrator) -> None:
        self._items[str(orchestrator.name)] = orchestrator

    def get(self, name: str) -> Orchestrator:
        item = self._items.get(name)
        if item is None:
            raise KeyError(f"Unknown orchestrator: {name}")
        return item

    def names(self) -> list[str]:
        return sorted(self._items.keys())
