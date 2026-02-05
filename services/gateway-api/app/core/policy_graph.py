from __future__ import annotations

try:
    from ..policy_graph import lookup_policy_ids
except Exception:
    lookup_policy_ids = None


def get_citations_for_decision(tool_name: str, args: dict | None = None) -> tuple[list[str], list[str], list[str]]:
    if lookup_policy_ids is None:
        return [], [], []
    try:
        return lookup_policy_ids(tool_name)
    except Exception:
        return [], [], []
