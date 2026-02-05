from __future__ import annotations

from typing import Protocol


class ToolBackend(Protocol):
    name: str

    def call_tool(self, tool_name: str, args: dict) -> dict | str | None:
        ...
