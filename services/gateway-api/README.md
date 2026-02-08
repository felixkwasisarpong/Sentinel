# Senteniel Runtime

`senteniel` is the control plane runtime package (FastAPI + GraphQL), not the
thin remote client SDK.

## Install

```bash
python -m pip install -U pip setuptools wheel
python -m pip install -e .
```

## Run

```bash
senteniel serve --host 0.0.0.0 --port 8000
```

Equivalent direct run:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Key Endpoints

- GraphQL: `http://localhost:8000/graphql`
- Metrics: `http://localhost:8000/metrics`

## Key Environment Variables

- `DATABASE_URL`
- `GATEWAY_GRAPHQL_URL`
- `ORCHESTRATOR=langgraph|crewai|autogen`
- `TOOL_BACKEND=mcp_http|mcp_stdio|mock`
- `OPENAI_API_BASE`
- `OPENAI_MODEL_NAME`
- `OPENAI_API_KEY`
- `MCP_BASE_URL` / `MCP_URL` (for `mcp_http`)
- `MCP_STDIO_CMD` (for `mcp_stdio`, default `docker mcp gateway run`)
- `MCP_STDIO_AUTO_SYNC` (default `true`)
- `MCP_STDIO_SERVER_NAME` (default `gateway`)
- `MCP_STDIO_PLACEHOLDER_URL` (display-only placeholder for stdio mode)

## MCP Notes

- `mcp_http` expects Docker-hosted MCP endpoints using Docker service hostnames.
- `mcp_stdio` executes `docker mcp gateway run` and talks MCP over stdio.
- In stdio mode, tool discovery can auto-sync on first tool call.

## Verify

```bash
curl -s http://localhost:8000/graphql -H 'content-type: application/json' \
  -d '{"query":"{ ping }"}'
```

## SDK vs Runtime

- `senteniel`: full runtime/control plane (this package)
- `sentinel-sdk`: thin client used by external apps to call the runtime
