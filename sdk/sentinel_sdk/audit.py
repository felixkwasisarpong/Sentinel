from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import requests


class AuditSink(Protocol):
    def write(self, event: dict[str, Any]) -> None:
        ...


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


class JsonlAuditSink:
    def __init__(self, path: str, *, create_parent: bool = True) -> None:
        self.path = Path(path)
        self.create_parent = create_parent

    def write(self, event: dict[str, Any]) -> None:
        if self.create_parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True, default=str))
            f.write("\n")


class HttpAuditSink:
    def __init__(
        self,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
        session: requests.Session | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.headers = headers or {}
        self.timeout = timeout
        self._session = session or requests.Session()

    def write(self, event: dict[str, Any]) -> None:
        resp = self._session.post(
            self.endpoint,
            json=event,
            headers=self.headers,
            timeout=self.timeout,
        )
        if not resp.ok:
            raise RuntimeError(f"HTTP audit sink failed: {resp.status_code} {resp.text}")


@dataclass
class AuditEmitter:
    sinks: list[AuditSink] = field(default_factory=list)
    fail_closed: bool = False

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        errors: list[str] = []
        for sink in self.sinks:
            try:
                sink.write(event)
            except Exception as exc:
                errors.append(str(exc))

        if errors and self.fail_closed:
            raise RuntimeError(f"Audit emission failed: {' | '.join(errors)}")
