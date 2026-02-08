import os
import shlex
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tool_backends.mcp_stdio import McpStdioBackend


def _is_truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@pytest.mark.smoke
def test_stdio_tools_list_discovers_tools_from_gateway():
    if not _is_truthy(os.getenv("RUN_STDIO_TOOLS_LIST_SMOKE"), default=False):
        pytest.skip("Set RUN_STDIO_TOOLS_LIST_SMOKE=1 to enable stdio tools/list smoke test.")

    cmd = os.getenv("MCP_STDIO_CMD", "docker mcp gateway run")
    cmd_argv = shlex.split(cmd)
    if not cmd_argv:
        pytest.skip("MCP_STDIO_CMD is empty.")
    if shutil.which(cmd_argv[0]) is None:
        pytest.skip(
            f"'{cmd_argv[0]}' not found in PATH. "
            "Run this smoke test where Docker CLI is available."
        )

    min_tools = int(os.getenv("SMOKE_MIN_TOOLS", "1"))
    max_print = int(os.getenv("SMOKE_PRINT_MAX", "200"))
    include_prefixes = _split_csv(os.getenv("SMOKE_INCLUDE_TOOL_PREFIXES"))
    exclude_prefixes = _split_csv(os.getenv("SMOKE_EXCLUDE_TOOL_PREFIXES", "mcp-"))
    expected_markers_raw = os.getenv("SMOKE_EXPECT_TOOL_MARKERS", "")
    expected_markers = [m.strip() for m in expected_markers_raw.split(",") if m.strip()]

    backend = McpStdioBackend(command=cmd)
    tools = backend.list_tools()
    assert len(tools) >= min_tools, (
        f"Expected at least {min_tools} tools from stdio gateway, got {len(tools)}"
    )

    names = sorted({str(t.get("name", "")) for t in tools if isinstance(t, dict) and t.get("name")})
    assert names, "tools/list returned tools without names"

    filtered_names = names
    if include_prefixes:
        filtered_names = [n for n in filtered_names if any(n.startswith(p) for p in include_prefixes)]
    if exclude_prefixes:
        filtered_names = [n for n in filtered_names if not any(n.startswith(p) for p in exclude_prefixes)]

    assert len(filtered_names) >= min_tools, (
        f"Expected at least {min_tools} filtered tools, got {len(filtered_names)}. "
        f"include={include_prefixes or '[]'} exclude={exclude_prefixes or '[]'}"
    )

    if expected_markers:
        missing = [m for m in expected_markers if not any(m in n for n in filtered_names)]
        assert not missing, (
            f"Missing expected marker(s) {missing} in tool names. "
            f"First 30 filtered tool names: {sorted([n for n in filtered_names if n])[:30]}"
        )

    print(f"[SMOKE] stdio tools/list returned {len(names)} tools ({len(filtered_names)} after filters)")
    print(f"[SMOKE] include_prefixes={include_prefixes or []} exclude_prefixes={exclude_prefixes or []}")
    for name in filtered_names[:max_print]:
        print(f"[SMOKE][TOOL] {name}")
