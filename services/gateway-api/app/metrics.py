from prometheus_client import Counter, Histogram

tool_calls = Counter(
    "senteniel_tool_calls_total",
    "Total tool calls",
    ["tool", "decision"]
)

decision_latency = Histogram(
    "senteniel_decision_latency_ms",
    "Decision latency in ms"
)