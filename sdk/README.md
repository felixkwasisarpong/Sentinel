# Sentinel SDK (Python)

Thin client for the Sentinel GraphQL API.

## Install (editable)
```bash
pip install -e sdk
```

## Usage
```python
from sentinel_sdk import SentinelClient

client = SentinelClient("http://localhost:8000/graphql")

# Propose a tool call
result = client.propose_tool_call("fs.list_dir", {"path": "/sandbox"})
print(result)

# Approve a pending tool call
approved = client.approve_tool_call(result.tool_call_id, note="ok", approved_by="alice")

# Deny a pending tool call
# denied = client.deny_tool_call(result.tool_call_id, note="no", approved_by="alice")
```
