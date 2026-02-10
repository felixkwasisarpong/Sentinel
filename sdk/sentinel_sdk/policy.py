from __future__ import annotations

import json
import os
from dataclasses import dataclass


VALID_DECISIONS = {"ALLOW", "BLOCK", "APPROVAL_REQUIRED"}


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    reason: str
    risk_score: float


class PrefixPolicyEngine:
    def __init__(self, prefix_rules: dict[str, dict] | None = None) -> None:
        raw_rules = prefix_rules or {}
        rules: list[tuple[str, dict]] = []
        for prefix, rule in raw_rules.items():
            if isinstance(prefix, str) and isinstance(rule, dict):
                rules.append((prefix, rule))
        self._rules = sorted(rules, key=lambda x: len(x[0]), reverse=True)

    @classmethod
    def from_env(cls, var_name: str = "POLICY_PREFIX_RULES") -> "PrefixPolicyEngine":
        raw = (os.getenv(var_name) or "").strip()
        if not raw:
            return cls({})
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        return cls(parsed)

    def evaluate(self, tool_name: str, args: dict | None = None) -> PolicyDecision:
        _ = args
        for prefix, rule in self._rules:
            if not tool_name.startswith(prefix):
                continue
            decision = str(rule.get("decision", "BLOCK")).upper()
            if decision not in VALID_DECISIONS:
                decision = "BLOCK"
            reason = str(rule.get("reason") or "Policy prefix match")
            try:
                risk = float(rule.get("risk", 0.5))
            except Exception:
                risk = 0.5
            return PolicyDecision(decision=decision, reason=reason, risk_score=risk)
        return PolicyDecision(decision="BLOCK", reason="Unknown tool", risk_score=1.0)
