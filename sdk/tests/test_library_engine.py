from __future__ import annotations

import json

from sentinel_sdk import (
    ExplicitToolCallOrchestrator,
    InMemoryAuditSink,
    JsonlAuditSink,
    SentinelEngine,
    StaticToolBackend,
    make_policy_engine_from_dict,
)


def _engine_with_allow_rule() -> tuple[SentinelEngine, InMemoryAuditSink]:
    backend = StaticToolBackend(
        {
            "openbnb_airbnb.airbnb_search": lambda args: {"location": args.get("location")},
        }
    )
    policy = make_policy_engine_from_dict(
        {
            "openbnb_airbnb.": {
                "decision": "ALLOW",
                "risk": 0.0,
                "reason": "allowed",
            }
        }
    )
    audit = InMemoryAuditSink()
    engine = SentinelEngine(tool_backend=backend, policy_engine=policy, audit_sinks=[audit])
    engine.sync_tools()
    return engine, audit


def test_local_engine_executes_known_tool() -> None:
    engine, audit = _engine_with_allow_rule()
    decision = engine.propose_tool_call("openbnb_airbnb.airbnb_search", {"location": "Accra"})
    assert decision.decision == "ALLOW"
    assert decision.final_status == "EXECUTED"
    assert '"location": "Accra"' in (decision.result or "")
    assert any(evt.get("type") == "tool.executed" for evt in audit.events)


def test_unknown_tool_is_blocked() -> None:
    engine, _ = _engine_with_allow_rule()
    decision = engine.propose_tool_call("openbnb_airbnb.nope", {})
    assert decision.decision == "BLOCK"
    assert decision.reason == "Unknown tool"


def test_jsonl_audit_sink_writes_lines(tmp_path) -> None:
    path = tmp_path / "audit" / "events.jsonl"
    sink = JsonlAuditSink(str(path))
    sink.write({"type": "tool.proposed", "tool": "demo"})
    sink.write({"type": "tool.executed", "tool": "demo"})

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "tool.proposed"
    assert json.loads(lines[1])["type"] == "tool.executed"


def test_explicit_orchestrator_calls_engine() -> None:
    engine, _ = _engine_with_allow_rule()
    engine.register_orchestrator(ExplicitToolCallOrchestrator())
    decision = engine.run("explicit", 'openbnb_airbnb.airbnb_search {"location":"Kumasi"}')
    assert decision.decision == "ALLOW"
    assert '"Kumasi"' in (decision.result or "")
