from __future__ import annotations

import os

import requests

_DEFAULT_CMD = "docker mcp gateway run"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_TOOL_RUNNER_URL = "http://tool-runner:8100"
_DEFAULT_TOOL_RUNNER_TIMEOUT = 20.0


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _known_stdio_prefixes() -> set[str]:
    """
    Prefixes for stdio logical servers (without trailing dot), used to map
    namespaced tool ids (e.g., github.list_issues) back to raw names.
    """
    prefixes = set(_split_csv(os.getenv("MCP_STDIO_STRIP_PREFIXES")))
    placeholder_base = (os.getenv("MCP_STDIO_PLACEHOLDER_URL", "http://docker-mcp-gateway:7001") or "").rstrip("/")
    try:
        from ..db.models import MCPServer
        from ..db.session import SessionLocal

        db = SessionLocal()
        try:
            servers = db.query(MCPServer).all()
            for server in servers:
                base = (getattr(server, "base_url", "") or "").rstrip("/")
                if base != placeholder_base:
                    continue
                prefix = (getattr(server, "tool_prefix", "") or "").strip().rstrip(".")
                if prefix:
                    prefixes.add(prefix)
        finally:
            db.close()
    except Exception:
        # DB may not be available in isolated tests; env prefixes still work.
        pass
    return prefixes


def _normalize_tool_name_for_stdio_call(tool_name: str) -> str:
    if not isinstance(tool_name, str) or "." not in tool_name:
        return tool_name
    first, rest = tool_name.split(".", 1)
    if not rest:
        return tool_name
    if first in _known_stdio_prefixes():
        return rest
    return tool_name


def _extract_error_detail(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except Exception:
        return (resp.text or "").strip() or f"HTTP {resp.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if detail:
        return str(detail)
    return str(payload)


class McpStdioBackend:
    name = "mcp_stdio"

    def __init__(
        self,
        command: str | None = None,
        timeout: float | None = None,
        tool_runner_url: str | None = None,
        request_timeout: float | None = None,
    ) -> None:
        cmd = command or os.getenv("MCP_STDIO_CMD") or os.getenv("MCP_GATEWAY_CMD") or _DEFAULT_CMD
        self.command = cmd
        self.timeout = float(timeout or os.getenv("MCP_STDIO_TIMEOUT", _DEFAULT_TIMEOUT))
        self.tool_runner_url = (
            tool_runner_url or os.getenv("MCP_TOOL_RUNNER_URL") or _DEFAULT_TOOL_RUNNER_URL
        ).rstrip("/")
        self.request_timeout = float(
            request_timeout or os.getenv("MCP_TOOL_RUNNER_TIMEOUT", _DEFAULT_TOOL_RUNNER_TIMEOUT)
        )

    def call_tool(self, tool_name: str, args: dict) -> dict | str | None:
        raw_tool_name = _normalize_tool_name_for_stdio_call(tool_name)
        endpoint = f"{self.tool_runner_url}/v1/mcp/call-tool"
        payload = {
            "tool_name": raw_tool_name,
            "args": args or {},
            "command": self.command,
            "timeout": self.timeout,
        }
        try:
            resp = requests.post(endpoint, json=payload, timeout=self.request_timeout)
        except requests.RequestException as exc:
            raise requests.RequestException(
                f"Failed to reach MCP tool-runner at {endpoint}: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise requests.RequestException(_extract_error_detail(resp))

        data = resp.json()
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    def list_tools(self) -> list[dict]:
        endpoint = f"{self.tool_runner_url}/v1/mcp/list-tools"
        payload = {
            "command": self.command,
            "timeout": self.timeout,
            "max_pages": int(os.getenv("MCP_STDIO_LIST_MAX_PAGES", "100")),
        }
        try:
            resp = requests.post(endpoint, json=payload, timeout=self.request_timeout)
        except requests.RequestException as exc:
            raise requests.RequestException(
                f"Failed to reach MCP tool-runner at {endpoint}: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise requests.RequestException(_extract_error_detail(resp))

        data = resp.json()
        if isinstance(data, dict):
            tools = data.get("tools")
            if isinstance(tools, list):
                return [t for t in tools if isinstance(t, dict)]
            result = data.get("result")
            if isinstance(result, dict) and isinstance(result.get("tools"), list):
                return [t for t in result["tools"] if isinstance(t, dict)]
            if isinstance(result, list):
                return [t for t in result if isinstance(t, dict)]
        return []
