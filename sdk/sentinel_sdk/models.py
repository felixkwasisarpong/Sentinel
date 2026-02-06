from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDecision:
    tool_call_id: str
    decision: str
    reason: str
    result: str | None
    final_status: str | None
    policy_citations: list[str]
    incident_refs: list[str]
    control_refs: list[str]

    @classmethod
    def from_graphql(cls, payload: dict[str, Any]) -> "ToolDecision":
        return cls(
            tool_call_id=str(payload.get("toolCallId", "")),
            decision=str(payload.get("decision", "")),
            reason=str(payload.get("reason", "")),
            result=payload.get("result"),
            final_status=payload.get("finalStatus"),
            policy_citations=list(payload.get("policyCitations") or []),
            incident_refs=list(payload.get("incidentRefs") or []),
            control_refs=list(payload.get("controlRefs") or []),
        )
