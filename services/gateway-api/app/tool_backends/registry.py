from __future__ import annotations

import os

from .base import ToolBackend
from .mcp_http import McpHttpBackend
from .mock import MockBackend


def get_tool_backend() -> ToolBackend:
    backend = (os.getenv("TOOL_BACKEND") or "mcp_http").strip().lower()
    base_url = os.getenv("MCP_BASE_URL") or os.getenv("MCP_URL")

    if backend in ("mcp_http", "mcp", "http"):
        return McpHttpBackend(base_url=base_url)
    if backend in ("mock", "fake", "eval"):
        return MockBackend()

    raise ValueError(f"Unknown TOOL_BACKEND: {backend}")
