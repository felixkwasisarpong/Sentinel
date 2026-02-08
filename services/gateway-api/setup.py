from setuptools import find_packages, setup


setup(
    name="senteniel",
    version="0.1.0",
    description="Senteniel control plane runtime (FastAPI + GraphQL)",
    packages=find_packages(include=["app", "app.*"]),
    include_package_data=True,
    install_requires=[
        "fastapi",
        "strawberry-graphql",
        "uvicorn",
        "pydantic",
        "email-validator",
        "sqlalchemy",
        "psycopg2-binary",
        "prometheus-client",
        "requests",
        "langgraph",
        "langchain-core",
        "crewai",
        "langchain-ollama",
        "litellm",
        "apscheduler",
        "fastapi-sso",
        "alembic>=1.12",
        "neo4j",
        "autogen-agentchat",
        "autogen-ext[openai]",
    ],
    entry_points={
        "console_scripts": [
            "senteniel=app.cli:main",
        ]
    },
)
