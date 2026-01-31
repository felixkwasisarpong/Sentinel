import requests

MCP_URL = "http://mcp-sandbox:7001/tools"

def call_tool(tool: str, args: dict):
    resp = requests.post(
        MCP_URL,
        json={"tool": tool, "args": args},
        timeout=5
    )
    resp.raise_for_status()
    return resp.json()