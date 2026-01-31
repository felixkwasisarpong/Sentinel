from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter
from prometheus_client import make_asgi_app
from .graphql_schema import schema
from .db.base import Base
from .db.session import engine

app = FastAPI(title="Senteniel Gateway")

Base.metadata.create_all(bind=engine)

app.mount("/metrics", make_asgi_app())


graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

app.mount("/metrics", make_asgi_app())