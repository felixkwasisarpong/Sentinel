from __future__ import annotations

from sentinel_sdk.audit import HttpAuditSink


class _Resp:
    def __init__(self, ok: bool, status_code: int = 200, text: str = "") -> None:
        self.ok = ok
        self.status_code = status_code
        self.text = text


class _Session:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[dict] = []

    def post(self, url, json, headers, timeout):  # noqa: A002
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if self.ok:
            return _Resp(True)
        return _Resp(False, 500, "boom")


def test_http_audit_sink_posts_event() -> None:
    sess = _Session(ok=True)
    sink = HttpAuditSink("http://audit.local/events", session=sess, headers={"x-api-key": "k"})
    sink.write({"type": "tool.executed"})
    assert len(sess.calls) == 1
    assert sess.calls[0]["url"] == "http://audit.local/events"
    assert sess.calls[0]["json"]["type"] == "tool.executed"


def test_http_audit_sink_raises_on_error() -> None:
    sess = _Session(ok=False)
    sink = HttpAuditSink("http://audit.local/events", session=sess)
    try:
        sink.write({"type": "tool.executed"})
        assert False, "expected error"
    except RuntimeError as exc:
        assert "HTTP audit sink failed" in str(exc)
