from __future__ import annotations

from .base import ToolBackend


class MockBackend:
    name = "mock"

    def call_tool(self, tool_name: str, args: dict) -> dict | str | None:
        if tool_name == "fs.list_dir":
            return {"result": ["example.txt"]}
        if tool_name == "fs.read_file":
            path = ""
            if isinstance(args, dict):
                path = args.get("path") or args.get("file") or ""
            if isinstance(path, str) and path.endswith("hello.txt"):
                return {"result": "Hello from mock backend."}
            if isinstance(path, str) and path.endswith("example.txt"):
                return {"result": "Example content."}
            return {"result": ""}
        if tool_name == "fs.write_file":
            return {"result": "OK"}
        return {"result": f"[MOCK] {tool_name}"}
