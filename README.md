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
- LangGraph, CrewAI, Hybrid FSM
- Same tools + same policy + same boundary for fair evaluation

**Pluggable tool execution**
- `mcp_http` (default)
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

## Quickstart (Docker)

```bash
docker compose up -d --build
```

Try orchestrators:
```bash
curl -X POST "http://localhost:8000/agent/run?task=list%20files"
curl -X POST "http://localhost:8000/agent/run?orchestrator=crewai&task=list%20files"
curl -X POST "http://localhost:8000/agent/run?orchestrator=fsm&task=list%20files"
```

---

## MCP Registry (GitHub example)

Register MCP server:
```graphql
mutation {
  registerMcpServer(
    name: "github"
    baseUrl: "https://api.githubcopilot.com/mcp/x/all"
    toolPrefix: "gh."
    authHeader: "Authorization"
    authToken: "Bearer <YOUR_GITHUB_TOKEN>"
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
  syncMcpTools(serverName: "github") {
    serverName
    toolCount
  }
}
```

---

## Environment Variables

- `ORCHESTRATOR=langgraph`
- `TOOL_BACKEND=mcp_http`
- `MCP_BASE_URL=http://mcp-sandbox:7001`
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
