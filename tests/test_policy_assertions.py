from mcp_test.assertions import assert_policy_allows, assert_policy_blocks
from mcp_test.types import MCPError, ToolResult


class _FakeClient:
    def __init__(self, result: ToolResult):
        self._result = result

    def call_tool(self, _tool_name: str, **_arguments):
        return self._result


class _FakeHTTPResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_assert_policy_allows(monkeypatch):
    result = ToolResult(content=[], is_error_result=False, raw={"result": {}}, _error=None)
    client = _FakeClient(result)

    def fake_urlopen(_req, timeout=10):  # noqa: ARG001
        return _FakeHTTPResponse('{"records":[]}')

    monkeypatch.setattr("mcp_test.assertions.urlopen", fake_urlopen)
    out = assert_policy_allows(client, "safe_tool", "http://astragraph:8080", a=1)
    assert out is result


def test_assert_policy_blocks(monkeypatch):
    result = ToolResult(
        content=[],
        is_error_result=True,
        raw={"error": {"message": "POLICY_VIOLATION"}},
        _error=MCPError(code=-32003, message="POLICY_VIOLATION", data=None),
    )
    client = _FakeClient(result)

    def fake_urlopen(_req, timeout=10):  # noqa: ARG001
        return _FakeHTTPResponse('{"violations":[{"rule_id":"rule-export-block"}]}')

    monkeypatch.setattr("mcp_test.assertions.urlopen", fake_urlopen)
    out = assert_policy_blocks(client, "export_data", "http://astragraph:8080", payload="x")
    assert out is result
