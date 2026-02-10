from __future__ import annotations

from sentinel_core import SentinelEngine, StaticToolBackend, make_policy_engine_from_dict


def test_sentinel_core_alias_import_works() -> None:
    backend = StaticToolBackend({"demo.echo": lambda args: args})
    policy = make_policy_engine_from_dict(
        {"demo.": {"decision": "ALLOW", "risk": 0.0, "reason": "ok"}}
    )
    engine = SentinelEngine(tool_backend=backend, policy_engine=policy)
    engine.sync_tools()
    decision = engine.propose_tool_call("demo.echo", {"x": 1})
    assert decision.decision == "ALLOW"
