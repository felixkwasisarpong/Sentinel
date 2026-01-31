from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from prometheus_client import make_asgi_app
from .graphql_schema import schema
from .db.base import Base
from .db.session import engine
from .agents.langgraph_runner import build_langgraph
from .agents.state import AgentState
from .agents.fsm_runner import FSMRunner



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
    }

    result = langgraph.invoke(initial_state)
    return result

@app.post("/agent/fsm/run")
def run_fsm(task: str):
    fsm = FSMRunner(task)
    ctx = fsm.run()
    return {
        "final_state": ctx,
    }