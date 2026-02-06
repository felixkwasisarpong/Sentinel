from __future__ import annotations

import json
import os
import select
import shlex
import subprocess
import time

import requests

_DEFAULT_CMD = "docker mcp gateway run"
_DEFAULT_TIMEOUT = 10.0


def _normalize_jsonrpc_result(result):
    # Normalize to match MCP /tools shape used elsewhere.
    if isinstance(result, dict) and "content" in result:
        content = result.get("content")
        if isinstance(content, list) and content:
            item = content[0]
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str) and text.strip().startswith(("{", "[")):
                    try:
                        return {"result": json.loads(text)}
                    except Exception:
                        pass
                return {"result": text}
    return {"result": result}


def _read_jsonrpc_response(proc: subprocess.Popen, request_id: str, timeout: float) -> dict | None:
    if proc.stdout is None:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rlist, _, _ = select.select([proc.stdout], [], [], 0.2)
        if not rlist:
            if proc.poll() is not None:
                break
            continue
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id") == request_id:
            return data
    return None


def _terminate_process(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=1)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _jsonrpc_error_message(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    err = data.get("error")
    if not err:
        return None
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error") or "Unknown MCP error"
        details = err.get("data")
        if details:
            return f"{msg} ({details})"
        return msg
    return str(err)


class McpStdioBackend:
    name = "mcp_stdio"

    def __init__(self, command: str | None = None, timeout: float | None = None) -> None:
        cmd = command or os.getenv("MCP_STDIO_CMD") or os.getenv("MCP_GATEWAY_CMD") or _DEFAULT_CMD
        self.command = cmd
        self.timeout = float(timeout or os.getenv("MCP_STDIO_TIMEOUT", _DEFAULT_TIMEOUT))

    def _request(self, payload: dict) -> dict:
        cmd = shlex.split(self.command)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        try:
            if proc.stdin is None:
                raise requests.RequestException("MCP stdio gateway stdin unavailable")
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            data = _read_jsonrpc_response(proc, payload.get("id", ""), self.timeout)
            if data is None:
                err_text = ""
                if proc.stderr is not None:
                    try:
                        err_text = proc.stderr.read().strip()
                    except Exception:
                        err_text = ""
                if err_text:
                    raise requests.RequestException(f"MCP stdio gateway error: {err_text}")
                raise requests.RequestException("No response from MCP stdio gateway")
            return data
        finally:
            _terminate_process(proc)

    def call_tool(self, tool_name: str, args: dict) -> dict | str | None:
        payload = {
            "jsonrpc": "2.0",
            "id": "tools-call",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }
        data = self._request(payload)
        err = _jsonrpc_error_message(data)
        if err:
            raise requests.RequestException(f"MCP error: {err}")
        result = data.get("result")
        return _normalize_jsonrpc_result(result)

    def list_tools(self) -> list[dict]:
        payload = {
            "jsonrpc": "2.0",
            "id": "tools-list",
            "method": "tools/list",
            "params": {},
        }
        data = self._request(payload)
        err = _jsonrpc_error_message(data)
        if err:
            raise requests.RequestException(f"MCP error: {err}")
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            return result["tools"]
        if isinstance(result, list):
            return result
        return []
