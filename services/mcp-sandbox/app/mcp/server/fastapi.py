from fastapi import FastAPI, HTTPException
from typing import Callable, Dict, Any

class MCPServer:
    def __init__(self, name: str, description: str | None = None):
        self.name = name
        self.description = description or "MCP Server"
        self._tools: Dict[str, Callable[..., Any]] = {}
        self.app = FastAPI(title=self.name, description=self.description)

        @self.app.post("/tools")
        async def run_tool(payload: dict):
            tool = payload.get("tool")
            args = payload.get("args", {})

            if not tool:
                raise HTTPException(status_code=400, detail="Missing 'tool' in request")

            handler = self._tools.get(tool)
            if handler is None:
                raise HTTPException(status_code=404, detail=f"Unknown tool: {tool}")

            # Call handler synchronously; handlers in this project are simple functions
            try:
                if isinstance(args, dict):
                    return {"result": handler(**args)}
                return {"result": handler(args)}
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    def add_tool(self, name: str, description: str, handler: Callable[..., Any]):
        self._tools[name] = handler
