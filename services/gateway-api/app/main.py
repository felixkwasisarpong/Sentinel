import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter
from prometheus_client import make_asgi_app
from .graphql_schema import schema
from .db.base import Base
from .db.session import engine, SessionLocal
from .db.models import MCPServer
from .agents.langgraph_runner import build_langgraph
from .agents.state import AgentState
from .agents.fsm_runner import HybridFSM


from .agents.crewai_runner import run_crewai



langgraph = build_langgraph()



app = FastAPI(title="Senteniel Gateway")

# Allow browser-based UI calls to GraphQL/REST.
allowed_origins = [
    o.strip()
    for o in (os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","))
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)


def _normalize_mcp_base(url: str) -> str:
    url = (url or "").rstrip("/")
    if url.endswith("/tools"):
        url = url[: -len("/tools")]
    return url


def ensure_default_mcp_server() -> None:
    base_url = _normalize_mcp_base(os.getenv("MCP_URL", "http://mcp-sandbox:7001"))
    name = os.getenv("MCP_DEFAULT_NAME", "sandbox")
    prefix = os.getenv("MCP_DEFAULT_PREFIX", "fs.")

    db = SessionLocal()
    try:
        existing = (
            db.query(MCPServer)
            .filter((MCPServer.name == name) | (MCPServer.tool_prefix == prefix))
            .first()
        )
        if existing:
            existing.base_url = base_url
            existing.name = name
            existing.tool_prefix = prefix
            db.add(existing)
            db.commit()
            return

        server = MCPServer(
            name=name,
            base_url=base_url,
            tool_prefix=prefix,
        )
        db.add(server)
        db.commit()
    finally:
        try:
            db.close()
        except Exception:
            pass


ensure_default_mcp_server()




graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

app.mount("/metrics", make_asgi_app())



def _tool_decision_or_default(result: dict | None) -> dict:
    if isinstance(result, dict):
        tool_decision = result.get("tool_decision")
        if tool_decision:
            return tool_decision
        if "final_answer" in result:
            final_answer = result.get("final_answer")
        else:
            final_answer = result.get("result")
    else:
        final_answer = None

    return {
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": final_answer,
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }


@app.api_route("/agent/run", methods=["GET", "POST"])
def run_agent(task: str, orchestrator: str = "langgraph"):
    orchestrator = (orchestrator or "langgraph").strip().lower()
    if orchestrator in ("langgraph", "lg", "default"):
        initial_state: AgentState = {
            "user_task": task,
            "plan": None,
            "tool_result": None,
            "final_answer": None,
            "tool_decision": None,
        }
        result = langgraph.invoke(initial_state)
        return _tool_decision_or_default(result)

    if orchestrator in ("fsm", "hybrid", "fsm_hybrid"):
        fsm = HybridFSM(task)
        result = fsm.run()
        return _tool_decision_or_default(result)

    if orchestrator in ("crewai", "crew"):
        result = run_crewai(task)
        return _tool_decision_or_default(result)

    raise HTTPException(
        status_code=400,
        detail="Unknown orchestrator. Use langgraph, fsm, or crewai.",
    )

@app.api_route("/agent/fsm/run", methods=["GET", "POST"])
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

@app.api_route("/agent/crew/run", methods=["GET", "POST"])
def run_crew(task: str):
    return run_crewai(task)
