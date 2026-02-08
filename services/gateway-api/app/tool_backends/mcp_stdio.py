from __future__ import annotations

import json
import os
import select
import shlex
import subprocess
import time
from typing import Any

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


def _read_jsonrpc_response(proc: subprocess.Popen, request_id: Any, timeout: float) -> dict | None:
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

    def _write_payload(self, proc: subprocess.Popen, payload: dict) -> None:
        if proc.stdin is None:
            raise requests.RequestException("MCP stdio gateway stdin unavailable")
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()

    def _initialize_session(self, proc: subprocess.Popen) -> None:
        protocol_version = os.getenv("MCP_STDIO_PROTOCOL_VERSION", "2024-11-05")
        init_id = "initialize"
        init_payload = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "senteniel", "version": "0.1.0"},
            },
        }
        self._write_payload(proc, init_payload)
        init_data = _read_jsonrpc_response(proc, init_id, self.timeout)
        if init_data is None:
            raise requests.RequestException("No response to MCP initialize request")
        init_err = _jsonrpc_error_message(init_data)
        if init_err:
            raise requests.RequestException(f"MCP initialize error: {init_err}")

        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        self._write_payload(proc, initialized_notification)

    def _start_process(self) -> subprocess.Popen:
        cmd = shlex.split(self.command)
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            program = cmd[0] if cmd else "command"
            raise requests.RequestException(
                f"MCP stdio gateway command not found: {program}. "
                "Ensure Docker CLI is installed where gateway-api runs."
            ) from exc
        self._initialize_session(proc)
        return proc

    def _request_with_proc(self, proc: subprocess.Popen, payload: dict) -> dict:
        self._write_payload(proc, payload)
        data = _read_jsonrpc_response(proc, payload.get("id", ""), self.timeout)
        if data is None:
            # Avoid blocking forever on stderr.read() while process is still alive.
            _terminate_process(proc)
            err_text = ""
            try:
                _, stderr_out = proc.communicate(timeout=1)
                err_text = (stderr_out or "").strip()
            except Exception:
                err_text = ""
            if err_text:
                raise requests.RequestException(f"MCP stdio gateway error: {err_text}")
            raise requests.RequestException("No response from MCP stdio gateway")
        return data

    def _request(self, payload: dict) -> dict:
        proc = self._start_process()
        try:
            return self._request_with_proc(proc, payload)
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
        tools: list[dict] = []
        seen_names: set[str] = set()
        cursor = None
        max_pages = int(os.getenv("MCP_STDIO_LIST_MAX_PAGES", "100"))

        proc = self._start_process()
        try:
            for i in range(max_pages):
                params = {"cursor": cursor} if cursor else {}
                payload = {
                    "jsonrpc": "2.0",
                    "id": f"tools-list-{i}",
                    "method": "tools/list",
                    "params": params,
                }
                data = self._request_with_proc(proc, payload)
                err = _jsonrpc_error_message(data)
                if err:
                    raise requests.RequestException(f"MCP error: {err}")
                result = data.get("result")

                batch: list[dict] = []
                next_cursor = None
                if isinstance(result, dict):
                    if isinstance(result.get("tools"), list):
                        batch = [t for t in result["tools"] if isinstance(t, dict)]
                    next_cursor = (
                        result.get("nextCursor")
                        or result.get("next_cursor")
                        or result.get("cursor")
                    )
                elif isinstance(result, list):
                    batch = [t for t in result if isinstance(t, dict)]

                for t in batch:
                    name = t.get("name")
                    key = str(name) if name is not None else json.dumps(t, sort_keys=True)
                    if key in seen_names:
                        continue
                    seen_names.add(key)
                    tools.append(t)

                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
        finally:
            _terminate_process(proc)

        return tools
