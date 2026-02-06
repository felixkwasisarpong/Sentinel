from __future__ import annotations

import os
from typing import Any

import requests

from .models import ToolDecision


class SentinelError(RuntimeError):
    pass


class SentinelClient:
    def __init__(
        self,
        graphql_url: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.graphql_url = graphql_url or os.getenv("SENTINEL_GRAPHQL_URL", "http://localhost:8000/graphql")
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout = timeout
        self._session = session or requests.Session()

    def propose_tool_call(self, tool: str, args: dict[str, Any]) -> ToolDecision:
        query = """
        mutation Propose($tool: String!, $args: JSON!) {
          proposeToolCall(tool: $tool, args: $args) {
            toolCallId
            decision
            reason
            result
            finalStatus
            policyCitations
            incidentRefs
            controlRefs
          }
        }
        """
        data = self._request(query, {"tool": tool, "args": args})
        return ToolDecision.from_graphql(data["proposeToolCall"])

    def approve_tool_call(
        self,
        tool_call_id: str,
        *,
        note: str | None = None,
        approved_by: str | None = None,
    ) -> ToolDecision:
        query = """
        mutation Approve($id: String!, $note: String, $approvedBy: String) {
          approveToolCall(toolCallId: $id, note: $note, approvedBy: $approvedBy) {
            toolCallId
            decision
            reason
            result
            finalStatus
            policyCitations
            incidentRefs
            controlRefs
          }
        }
        """
        variables = {"id": tool_call_id, "note": note, "approvedBy": approved_by}
        data = self._request(query, variables)
        return ToolDecision.from_graphql(data["approveToolCall"])

    def deny_tool_call(
        self,
        tool_call_id: str,
        *,
        note: str | None = None,
        approved_by: str | None = None,
    ) -> ToolDecision:
        query = """
        mutation Deny($id: String!, $note: String, $approvedBy: String) {
          denyToolCall(toolCallId: $id, note: $note, approvedBy: $approvedBy) {
            toolCallId
            decision
            reason
            result
            finalStatus
            policyCitations
            incidentRefs
            controlRefs
          }
        }
        """
        variables = {"id": tool_call_id, "note": note, "approvedBy": approved_by}
        data = self._request(query, variables)
        return ToolDecision.from_graphql(data["denyToolCall"])

    def _request(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        resp = self._session.post(
            self.graphql_url,
            json={"query": query, "variables": variables},
            headers=self.headers,
            timeout=self.timeout,
        )
        if not resp.ok:
            raise SentinelError(f"GraphQL request failed: {resp.status_code} {resp.text}")
        payload = resp.json()
        if payload.get("errors"):
            message = payload["errors"][0].get("message", "GraphQL error")
            raise SentinelError(message)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise SentinelError("GraphQL error: empty response")
        return data
