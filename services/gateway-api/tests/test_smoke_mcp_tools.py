import os

import pytest
import requests


def _is_truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _gql(url: str, query: str, variables: dict | None = None) -> dict:
    resp = requests.post(
        url,
        json={"query": query, "variables": variables or {}},
        timeout=20,
    )
    assert resp.status_code == 200, f"GraphQL HTTP {resp.status_code}: {resp.text}"
    payload = resp.json()
    assert "errors" not in payload, f"GraphQL errors: {payload.get('errors')}"
    data = payload.get("data")
    assert isinstance(data, dict), f"Unexpected GraphQL payload: {payload}"
    return data


@pytest.mark.smoke
def test_mcp_server_has_discoverable_tools():
    if not _is_truthy(os.getenv("RUN_MCP_SMOKE"), default=False):
        pytest.skip("Set RUN_MCP_SMOKE=1 to enable MCP smoke test.")

    graphql_url = os.getenv("SMOKE_GRAPHQL_URL", "http://localhost:8000/graphql")
    server_name = os.getenv("SMOKE_MCP_SERVER_NAME", "gateway")
    should_sync = _is_truthy(os.getenv("SMOKE_SYNC_TOOLS"), default=True)
    expected_tool = (os.getenv("SMOKE_EXPECT_TOOL") or "").strip()

    if should_sync:
        sync_mutation = """
        mutation Sync($server: String!) {
          syncMcpTools(serverName: $server) {
            serverName
            toolCount
          }
        }
        """
        sync_data = _gql(graphql_url, sync_mutation, {"server": server_name})
        tool_count = int(sync_data["syncMcpTools"]["toolCount"])
        assert tool_count > 0, f"syncMcpTools returned 0 tools for server '{server_name}'"

    tools_query = """
    query Tools($server: String!) {
      mcpTools(serverName: $server) {
        name
      }
    }
    """
    data = _gql(graphql_url, tools_query, {"server": server_name})
    tools = data["mcpTools"] or []
    assert tools, f"No tools found for MCP server '{server_name}'"

    if expected_tool:
        names = {t.get("name") for t in tools if isinstance(t, dict)}
        assert expected_tool in names, (
            f"Expected tool '{expected_tool}' not found in server '{server_name}'. "
            f"Found: {sorted([n for n in names if n])}"
        )
