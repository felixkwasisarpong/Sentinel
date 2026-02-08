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
- `MCP_TOOL_RUNNER_URL` (for `mcp_stdio`, default `http://tool-runner:8100`)
- `MCP_STDIO_CMD` (forwarded to tool-runner, default `docker mcp gateway run`)
- `MCP_STDIO_AUTO_SYNC` (default `true`)
- `MCP_STDIO_SERVER_NAME` (default `gateway`)
- `MCP_STDIO_PLACEHOLDER_URL` (display-only placeholder for stdio mode)
- `MCP_STDIO_SERVER_TOOL_MARKERS` (optional JSON map for per-server filtering)
- `MCP_STDIO_SERVER_PREFIX_OVERRIDES` (optional JSON map for MCP server prefixes)
- `MCP_STDIO_STRIP_PREFIXES` (optional CSV fallback for namespace stripping on call)

## MCP Notes

- `mcp_http` expects Docker-hosted MCP endpoints using Docker service hostnames.
- `mcp_stdio` calls a separate Tool Runner service over HTTP.
- Tool Runner executes `docker mcp gateway run` and talks MCP over stdio.
- `gateway-api` does not need Docker CLI or Docker socket access.
- `tool-runner` installs a native Linux `docker-mcp` CLI plugin at image build
  time and sets `DOCKER_MCP_IN_CONTAINER=1`.
- In stdio mode, tool discovery can auto-sync on first tool call.
- In stdio mode, `tools/list` is aggregated; use `MCP_STDIO_SERVER_TOOL_MARKERS`
  to store tools per logical server when running `syncMcpTools`.
- If no marker is configured for a given server, Senteniel falls back to
  dynamic matching from server name tokens and tool metadata.
- Synced stdio tools are namespaced with the logical server prefix
  (for example: `openbnb.airbnb_search`, `gh.list_issues`).
- During execution, Senteniel strips the known namespace and sends the raw tool
  name to Docker MCP Gateway.

Example:

```bash
export MCP_STDIO_SERVER_TOOL_MARKERS='{
  "openbnb-airbnb":["airbnb_"],
  "github-official":["add_","issue_","list_","search_"]
}'
export MCP_STDIO_SERVER_PREFIX_OVERRIDES='{
  "openbnb-airbnb":"openbnb",
  "github-official":"gh"
}'
```

Then sync each server name:

```graphql
mutation { syncMcpTools(serverName: "openbnb-airbnb") { serverName toolCount } }
mutation { syncMcpTools(serverName: "github-official") { serverName toolCount } }
```

Policy can now target server namespaces directly:

```bash
export POLICY_PREFIX_RULES='{
  "openbnb.":{"decision":"APPROVAL_REQUIRED","risk":0.6,"reason":"Airbnb tools require approval"},
  "gh.list_":{"decision":"ALLOW","risk":0.0,"reason":"GitHub read/list allowed"},
  "gh.issue_write":{"decision":"APPROVAL_REQUIRED","risk":0.7,"reason":"GitHub write requires approval"}
}'
```

## Tool Runner Architecture

With `TOOL_BACKEND=mcp_stdio`, requests flow like this:

1. `gateway-api` evaluates policy and orchestrates.
2. `gateway-api` calls `MCP_TOOL_RUNNER_URL` for `tools/list` and `tools/call`.
3. `tool-runner` executes `docker mcp gateway run` over stdio.
4. Docker MCP Gateway fans out to the MCP servers you enabled in Docker MCP Toolkit.

In Docker Compose, `tool-runner` is the only service that needs Docker socket
access (`/var/run/docker.sock`).

## Verify

```bash
curl -s http://localhost:8000/graphql -H 'content-type: application/json' \
  -d '{"query":"{ ping }"}'
```

## SDK vs Runtime

- `senteniel`: full runtime/control plane (this package)
- `sentinel-sdk`: thin client used by external apps to call the runtime
