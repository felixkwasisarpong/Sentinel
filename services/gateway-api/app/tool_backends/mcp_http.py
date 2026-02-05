from __future__ import annotations

from .base import ToolBackend
from ..mcp_client import call_tool as mcp_call_tool


class McpHttpBackend:
    name = "mcp_http"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url

    def call_tool(self, tool_name: str, args: dict) -> dict | str | None:
        return mcp_call_tool(tool_name, args, base_url=self.base_url)
