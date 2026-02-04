# eval/run_eval.py
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "eval" / "tasks.jsonl"
RESULTS_PATH = ROOT / "eval" / "results.json"

import os
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

ORCHESTRATORS = [
    {"name": "langgraph", "url": f"{BASE_URL}/agent/run"},
    {"name": "crewai", "url": f"{BASE_URL}/agent/crew/run"},
    {"name": "fsm_hybrid", "url": f"{BASE_URL}/agent/fsm/run"},
]

def load_tasks():
    tasks = []
    with TASKS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks

def call_orchestrator(url: str, task: str) -> dict:
    t0 = time.perf_counter()
    r = requests.post(url, params={"task": task}, timeout=30)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    r.raise_for_status()
    body = r.json()
    return body, latency_ms

def extract_tool_decision(resp: dict) -> dict | None:
    if not isinstance(resp, dict):
        return None
    # New contract: ToolDecision returned at top level
    if "decision" in resp and "tool_call_id" in resp:
        return resp
    # Legacy contract: nested tool_decision
    td = resp.get("tool_decision")
    if isinstance(td, dict):
        return td
    return None

def main():
    tasks = load_tasks()
    results = []

    for tc in tasks:
        for orch in ORCHESTRATORS:
            try:
                resp, latency_ms = call_orchestrator(orch["url"], tc["task"])
                td = extract_tool_decision(resp) or {}
                decision = td.get("decision", "UNKNOWN")
                tool_call_id = td.get("tool_call_id", "n/a")
                final_status = td.get("final_status")

                results.append({
                    "task_id": tc["id"],
                    "task": tc["task"],
                    "expected_decision": tc["expected_decision"],
                    "orchestrator": orch["name"],
                    "latency_ms": round(latency_ms, 2),
                    "decision": decision,
                    "tool_call_id": tool_call_id,
                    "reason": td.get("reason"),
                    "final_status": final_status,
                    "policy_citations": td.get("policy_citations") or [],
                    "incident_refs": td.get("incident_refs") or [],
                    "control_refs": td.get("control_refs") or [],
                    "ok_http": True,
                })
            except Exception as e:
                results.append({
                    "task_id": tc["id"],
                    "task": tc["task"],
                    "expected_decision": tc["expected_decision"],
                    "orchestrator": orch["name"],
                    "latency_ms": None,
                    "decision": "ERROR",
                    "tool_call_id": "n/a",
                    "reason": str(e),
                    "policy_citations": [],
                    "incident_refs": [],
                    "control_refs": [],
                    "ok_http": False,
                })

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {len(results)} rows -> {RESULTS_PATH}")

if __name__ == "__main__":
    main()
