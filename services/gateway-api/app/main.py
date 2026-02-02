from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from prometheus_client import make_asgi_app
from .graphql_schema import schema
from .db.base import Base
from .db.session import engine
from .agents.langgraph_runner import build_langgraph
from .agents.state import AgentState
from .agents.fsm_runner import HybridFSM


from .agents.crewai_runner import run_crewai



langgraph = build_langgraph()



app = FastAPI(title="Senteniel Gateway")

Base.metadata.create_all(bind=engine)




graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

app.mount("/metrics", make_asgi_app())



@app.post("/agent/run")
def run_agent(task: str):
    initial_state: AgentState = {
        "user_task": task,
        "plan": None,
        "tool_result": None,
        "final_answer": None,
        "tool_decision": None,
    }

    result = langgraph.invoke(initial_state)
    if isinstance(result, dict) and result.get("tool_decision"):
        return result["tool_decision"]
    return {
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": result.get("final_answer") if isinstance(result, dict) else None,
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }

@app.post("/agent/fsm/run")
def run_fsm(task: str):
    fsm = HybridFSM(task)
    ctx = fsm.run()
    if isinstance(ctx, dict) and ctx.get("tool_decision"):
        return ctx["tool_decision"]
    return {
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": None,
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }

@app.post("/agent/crew/run")
def run_crew(task: str):
    return run_crewai(task)
