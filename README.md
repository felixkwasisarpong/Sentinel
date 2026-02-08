# 🛡️ SENTENIEL — SDK + Control Plane for Safe Tool‑Using Agents

![Senteniel Banner](docs/banner.png)

> **Senteniel is a Python SDK with a control‑plane service that enforces safe tool use.**
> It centralizes policy, approvals, and audit logging while keeping orchestration and tool execution pluggable.

---

![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-green)
![GraphQL](https://img.shields.io/badge/GraphQL-Control_Plane-purple)
![MCP](https://img.shields.io/badge/MCP-Tool_Boundary-black)
![Neo4j](https://img.shields.io/badge/Neo4j-Policy_Graph-brightgreen)
![Postgres](https://img.shields.io/badge/Postgres-Audit_DB-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)

---

## Why Senteniel?
LLM agents can read files, open tickets, and modify repos. That is powerful **and risky**.
Senteniel answers: *Should this tool call be allowed — and can we prove why?*

---

## What You Get

**SDK‑first control plane**
- Python SDK for propose/approve/deny
- GraphQL API for UI, runners, and eval
- Centralized policy, approvals, and audit

**Pluggable orchestration**
- LangGraph, CrewAI, AutoGen
- Same tools + same policy + same boundary for fair evaluation

**Pluggable tool execution**
- `mcp_http` (default)
- `mcp_stdio` (Docker MCP Gateway over stdio)
- `mock` (eval/testing)

**Hard boundaries**
- Filesystem tools are **/sandbox only**
- Anything outside `/sandbox` is blocked

**Audit + approvals**
- `PENDING → APPROVED → EXECUTED`
- `PENDING → DENIED`
- All decisions persisted (including BLOCK)

---

## SDK (Python)

```bash
pip install -e sdk
```

```python
from sentinel_sdk import SentinelClient

client = SentinelClient("http://localhost:8000/graphql")

decision = client.propose_tool_call("fs.list_dir", {"path": "/sandbox"})
approved = client.approve_tool_call(decision.tool_call_id, note="ok", approved_by="alice")
```

---

## Runtime Package (Control Plane)

Install and run Senteniel control plane locally:

```bash
cd services/gateway-api
python -m pip install -e . --no-use-pep517
senteniel serve --host 0.0.0.0 --port 8000
```

This package includes the API, policy plane, orchestrators, and MCP backends.
The `sentinel-sdk` package is only the remote client.

---

## Quickstart (Docker)

```bash
docker compose up -d --build
```

Try orchestrators:
```bash
curl -X POST "http://localhost:8000/agent/run?task=list%20files"
curl -X POST "http://localhost:8000/agent/run?orchestrator=crewai&task=list%20files"
curl -X POST "http://localhost:8000/agent/run?orchestrator=autogen&task=list%20files"
```

---

## MCP Registry (Docker example)

Only Docker-hosted MCP servers are supported. Base URLs must use the Docker
service hostname (no dots, no localhost, no IPs).

Register MCP server:
```graphql
mutation {
  registerMcpServer(
    name: "sandbox"
    baseUrl: "http://mcp-sandbox:7001"
    toolPrefix: "fs."
  ) {
    name
    baseUrl
    toolPrefix
  }
}
```

Sync tools:
```graphql
mutation {
  syncMcpTools(serverName: "sandbox") {
    serverName
    toolCount
  }
}
```

---

## Docker MCP Gateway (stdio)

If you want to use Docker MCP Toolkit's gateway (stdio), set:

```
TOOL_BACKEND=mcp_stdio
MCP_STDIO_CMD="docker mcp gateway run"
```

Then enable MCP servers in Docker Desktop (MCP Toolkit). Senteniel will invoke
`docker mcp gateway run` and send MCP JSON-RPC over stdin/stdout.

Note: the `docker mcp` command must be available where `gateway-api` runs
(host process or container with Docker CLI + MCP plugin).

To sync tools into Senteniel while using stdio, call:
```graphql
mutation {
  syncMcpTools(serverName: "gateway") {
    serverName
    toolCount
  }
}
```
If the server does not exist yet, Senteniel will create a placeholder record
named "gateway" using `MCP_DEFAULT_PREFIX` (default `mcp.`) and
`MCP_STDIO_PLACEHOLDER_URL` for display.

---

## Environment Variables

- `ORCHESTRATOR=langgraph`
- `TOOL_BACKEND=mcp_http`
- `MCP_BASE_URL=http://mcp-sandbox:7001` (Docker service hostname only)
- `MCP_STDIO_CMD="docker mcp gateway run"` (when `TOOL_BACKEND=mcp_stdio`)
- `MCP_STDIO_PLACEHOLDER_URL=http://docker-mcp-gateway:7001` (optional display-only)
- `MCP_STDIO_AUTO_SYNC=true` (default; sync tools on first tool call)
- `MCP_STDIO_SERVER_NAME=gateway` (placeholder MCP server name)
- `GATEWAY_GRAPHQL_URL=http://gateway-api:8000/graphql`
- `POLICY_PREFIX_RULES` (JSON map: prefix → decision/risk/reason)
- Optional GitHub defaults:
  - `GITHUB_OWNER=...`
  - `GITHUB_REPO=...`

---

## Tests

```bash
cd services/gateway-api
pytest -q
```

---

## Roadmap (Short)

- Expose richer policy evidence (beyond IDs)
- Expand eval harness + CI safety gate
- More SDKs (TypeScript)

---

## Status

Active development.
