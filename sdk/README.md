# sentinel-core (Python)

`sentinel-core` is the library-first Sentinel package:
- no required port
- no required HTTP server
- pluggable MCP/tool backends
- pluggable orchestrators
- pluggable audit sinks

The existing `SentinelClient` (GraphQL remote client) is still available.
Both imports are supported:
- `from sentinel_core import ...` (preferred)
- `from sentinel_sdk import ...` (backward compatible)

## Install (editable)

```bash
pip install -e sdk
```

Published package name: `sentinel-core`.

## Local Library Usage (No Server)

```python
from sentinel_core import (
    SentinelEngine,
    StaticToolBackend,
    InMemoryAuditSink,
    make_policy_engine_from_dict,
)

backend = StaticToolBackend(
    {
        "openbnb_airbnb.airbnb_search": lambda args: {"ok": True, "args": args},
    }
)

policy = make_policy_engine_from_dict(
    {
        "openbnb_airbnb.": {
            "decision": "ALLOW",
            "risk": 0.0,
            "reason": "Airbnb read tools allowed",
        }
    }
)

audit = InMemoryAuditSink()
engine = SentinelEngine(tool_backend=backend, policy_engine=policy, audit_sinks=[audit])
engine.sync_tools()

decision = engine.propose_tool_call(
    "openbnb_airbnb.airbnb_search",
    {"location": "Accra"},
)
print(decision)
print(audit.events[-1])
```

## Audit Sinks

- `InMemoryAuditSink`: captures events in memory (`events` list).
- `JsonlAuditSink`: appends one JSON event per line to a file.
- `HttpAuditSink`: sends events to an external endpoint.

## Orchestrator Plugin Example

```python
from sentinel_core import SentinelEngine, ExplicitToolCallOrchestrator, StaticToolBackend

backend = StaticToolBackend({"demo.echo": lambda args: args})
engine = SentinelEngine(tool_backend=backend, allow_unknown_tools=True)
engine.register_orchestrator(ExplicitToolCallOrchestrator())
engine.sync_tools()

result = engine.run("explicit", 'demo.echo {"msg":"hello"}')
print(result)
```

## Remote GraphQL Client (Optional)

```python
from sentinel_core import SentinelClient

client = SentinelClient("http://localhost:8000/graphql")
result = client.propose_tool_call("fs.list_dir", {"path": "/sandbox"})
print(result)
```
