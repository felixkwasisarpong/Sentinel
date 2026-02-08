# Senteniel Runtime

Install the control plane runtime package:

```bash
pip install .
```

Run the API:

```bash
senteniel serve --host 0.0.0.0 --port 8000
```

Environment variables are the same ones used by the Docker deployment
(`DATABASE_URL`, `GATEWAY_GRAPHQL_URL`, `OPENAI_API_BASE`, `OPENAI_MODEL_NAME`,
`MCP_BASE_URL`/`MCP_URL`, etc.).
