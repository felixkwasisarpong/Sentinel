from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .audit import AuditEmitter, AuditSink
from .models import ToolDecision
from .plugins import Orchestrator, OrchestratorRegistry, ToolBackend, ToolBackendRegistry
from .policy import PrefixPolicyEngine


def _to_result_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


class SentinelEngine:
    """
    Library-only Sentinel runtime:
    - no HTTP server
    - no DB required
    - pluggable tool backends, orchestrators, and audit sinks
    """

    def __init__(
        self,
        *,
        tool_backend: ToolBackend,
        policy_engine: PrefixPolicyEngine | None = None,
        audit_sinks: list[AuditSink] | None = None,
        audit_fail_closed: bool = False,
        allow_unknown_tools: bool = False,
    ) -> None:
        self.tool_backend_registry = ToolBackendRegistry()
        self.orchestrator_registry = OrchestratorRegistry()
        self.tool_backend_registry.register(tool_backend)
        self._active_tool_backend_name = tool_backend.name
        self._policy_engine = policy_engine or PrefixPolicyEngine.from_env()
        self._audit = AuditEmitter(sinks=list(audit_sinks or []), fail_closed=audit_fail_closed)
        self._allow_unknown_tools = allow_unknown_tools
        self._tools: dict[str, ToolContract] = {}

    @property
    def active_tool_backend(self) -> ToolBackend:
        return self.tool_backend_registry.get(self._active_tool_backend_name)

    def set_active_tool_backend(self, name: str) -> None:
        self.tool_backend_registry.get(name)
        self._active_tool_backend_name = name

    def register_tool_backend(self, backend: ToolBackend, *, make_active: bool = False) -> None:
        self.tool_backend_registry.register(backend)
        if make_active:
            self._active_tool_backend_name = backend.name

    def register_orchestrator(self, orchestrator: Orchestrator) -> None:
        self.orchestrator_registry.register(orchestrator)

    def list_registered_tools(self) -> list[ToolContract]:
        return [self._tools[name] for name in sorted(self._tools.keys())]

    def sync_tools(self, *, server_name: str | None = None, namespace: str | None = None) -> list[ToolContract]:
        backend = self.active_tool_backend
        try:
            tools = backend.list_tools(server_name=server_name)
        except TypeError:
            tools = backend.list_tools()  # Backward compatible with simple plugins.

        synced: list[ToolContract] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            raw_name = str(tool.get("name") or "").strip()
            if not raw_name:
                continue
            name = raw_name
            if namespace:
                ns = namespace.rstrip(".")
                name = f"{ns}.{raw_name}" if not raw_name.startswith(f"{ns}.") else raw_name
            contract = ToolContract(
                name=name,
                description=(str(tool.get("description")) if tool.get("description") is not None else None),
                input_schema=tool.get("input_schema") if isinstance(tool.get("input_schema"), dict) else None,
                raw=tool,
            )
            self._tools[name] = contract
            synced.append(contract)

        self._audit.emit(
            "tool.sync",
            {
                "server_name": server_name,
                "namespace": namespace,
                "count": len(synced),
                "backend": backend.name,
            },
        )
        return synced

    def propose_tool_call(self, tool: str, args: dict[str, Any] | None = None) -> ToolDecision:
        call_id = str(uuid.uuid4())
        payload_args = args or {}
        self._audit.emit("tool.proposed", {"tool_call_id": call_id, "tool": tool, "args": payload_args})

        if not self._allow_unknown_tools and tool not in self._tools:
            self._audit.emit("tool.blocked", {"tool_call_id": call_id, "tool": tool, "reason": "Unknown tool"})
            return ToolDecision(
                tool_call_id=call_id,
                decision="BLOCK",
                reason="Unknown tool",
                result=None,
                final_status=None,
                policy_citations=[],
                incident_refs=[],
                control_refs=[],
            )

        policy = self._policy_engine.evaluate(tool, payload_args)
        if policy.decision != "ALLOW":
            final_status = "PENDING" if policy.decision == "APPROVAL_REQUIRED" else None
            event = "tool.pending_approval" if final_status == "PENDING" else "tool.blocked"
            self._audit.emit(
                event,
                {
                    "tool_call_id": call_id,
                    "tool": tool,
                    "reason": policy.reason,
                    "risk_score": policy.risk_score,
                },
            )
            return ToolDecision(
                tool_call_id=call_id,
                decision=policy.decision,
                reason=policy.reason,
                result=None,
                final_status=final_status,
                policy_citations=[],
                incident_refs=[],
                control_refs=[],
            )

        try:
            result = self.active_tool_backend.call_tool(tool, payload_args)
            result_text = _to_result_text(result)
            self._audit.emit(
                "tool.executed",
                {
                    "tool_call_id": call_id,
                    "tool": tool,
                    "risk_score": policy.risk_score,
                },
            )
            return ToolDecision(
                tool_call_id=call_id,
                decision="ALLOW",
                reason=policy.reason,
                result=result_text,
                final_status="EXECUTED",
                policy_citations=[],
                incident_refs=[],
                control_refs=[],
            )
        except Exception as exc:
            reason = f"Tool call failed: {exc}"
            self._audit.emit("tool.failed", {"tool_call_id": call_id, "tool": tool, "reason": reason})
            return ToolDecision(
                tool_call_id=call_id,
                decision="BLOCK",
                reason=reason,
                result=None,
                final_status=None,
                policy_citations=[],
                incident_refs=[],
                control_refs=[],
            )

    def run(self, orchestrator_name: str, prompt: str, **kwargs: Any) -> Any:
        orchestrator = self.orchestrator_registry.get(orchestrator_name)
        self._audit.emit(
            "orchestrator.started",
            {"orchestrator": orchestrator_name, "prompt": prompt},
        )
        result = orchestrator.run(prompt=prompt, engine=self, **kwargs)
        self._audit.emit(
            "orchestrator.finished",
            {"orchestrator": orchestrator_name},
        )
        return result


def make_policy_engine_from_dict(prefix_rules: dict[str, dict]) -> PrefixPolicyEngine:
    return PrefixPolicyEngine(prefix_rules=prefix_rules)


def make_tool_proxy(tool_name: str) -> Callable[[SentinelEngine, dict[str, Any] | None], ToolDecision]:
    def _call(engine: SentinelEngine, args: dict[str, Any] | None = None) -> ToolDecision:
        return engine.propose_tool_call(tool_name, args or {})

    return _call
