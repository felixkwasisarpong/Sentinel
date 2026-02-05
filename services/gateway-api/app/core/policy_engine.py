from __future__ import annotations

from dataclasses import dataclass
from ..policy import evaluate_policy
from .policy_graph import get_citations_for_decision


@dataclass
class ToolDecisionResult:
    decision: str
    reason: str
    risk_score: float | None
    policy_citations: list[str]
    incident_refs: list[str]
    control_refs: list[str]


def evaluate_tool_call(tool_name: str, args: dict, context: dict | None = None) -> ToolDecisionResult:
    decision, reason, risk_score = evaluate_policy(tool_name, args or {})
    policies, incidents, controls = get_citations_for_decision(tool_name, args or {})
    return ToolDecisionResult(
        decision=decision,
        reason=reason,
        risk_score=risk_score,
        policy_citations=policies,
        incident_refs=incidents,
        control_refs=controls,
    )
