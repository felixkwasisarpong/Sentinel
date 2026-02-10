from __future__ import annotations

import json
from typing import Any, Callable


class StaticToolBackend:
    """
    Simple local backend for tests and demos.
    Register tools with callables; list_tools returns metadata only.
    """

    name = "static"

    def __init__(self, tools: dict[str, Callable[[dict[str, Any]], Any]] | None = None) -> None:
        self._tools = dict(tools or {})

    def register(self, name: str, fn: Callable[[dict[str, Any]], Any]) -> None:
        self._tools[name] = fn

    def list_tools(self, *, server_name: str | None = None) -> list[dict[str, Any]]:
        _ = server_name
        return [{"name": name, "description": "static tool"} for name in sorted(self._tools.keys())]

    def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        fn = self._tools.get(tool_name)
        if fn is None and "." in tool_name:
            # Convenience for namespaced local registrations.
            fn = self._tools.get(tool_name.split(".", 1)[1])
        if fn is None:
            raise KeyError(f"Unknown tool: {tool_name}")
        return fn(args)


class ExplicitToolCallOrchestrator:
    """
    Parses:
    - "<tool> {json args}"
    - "<tool> key=value key2=value2"
    """

    name = "explicit"

    def run(self, prompt: str, engine: Any, **kwargs: Any) -> Any:
        _ = kwargs
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Prompt is empty")

        tool, _, rest = prompt.partition(" ")
        args_text = rest.strip()
        if not args_text:
            parsed_args: dict[str, Any] = {}
        elif args_text.startswith("{"):
            parsed_args = json.loads(args_text)
        else:
            parsed_args = {}
            for token in args_text.split():
                if "=" not in token:
                    continue
                k, v = token.split("=", 1)
                parsed_args[k] = v

        return engine.propose_tool_call(tool, parsed_args)
