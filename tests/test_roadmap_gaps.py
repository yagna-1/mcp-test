from __future__ import annotations

import json
import os
import sys

import pytest

from mcp_test.bench import run_bench
from mcp_test.client import make_client
from mcp_test.compliance import score_conformance
from mcp_test.conformance import parse_conformance_output, run_report_as_pytest
from mcp_test.http_client import HTTPMCPTestClient, TransportMode
from mcp_test.otel import MCPTracer
from mcp_test.replay import WireTraceReplay
from mcp_test.test_packs import (
    APIWrapperTests,
    DatabaseServerTests,
    FilesystemServerTests,
    ShellExecTests,
    ToolInvocation,
)
from mcp_test.timeouts import (
    SMART_TIMEOUT_DEFAULTS,
    TimeoutConfig,
    parse_timeout_overrides,
    smart_timeout_for_method,
)


ECHO_SERVER = os.path.join(os.path.dirname(__file__), "fixtures", "echo_server.py")
SERVER_CMD = f"{sys.executable} {ECHO_SERVER}"


def test_timeout_config_method_override():
    config = TimeoutConfig.from_values(
        10.0,
        {"tools/call": 2.5},
        use_smart_defaults=True,
    )
    assert config.resolve("tools/call") == 2.5
    assert config.resolve("tools/list") == 5.0
    assert config.resolve("sampling/createMessage") == 60.0
    assert smart_timeout_for_method("tasks/get") == 30.0


def test_parse_timeout_overrides():
    assert parse_timeout_overrides(["tools/call=30", "ping=1.5"]) == {
        "tools/call": 30.0,
        "ping": 1.5,
    }


def test_wire_trace_records_jsonl_and_replays(tmp_path):
    trace_path = tmp_path / "trace.jsonl"
    with make_client(SERVER_CMD, timeout=5.0, trace_path=trace_path) as client:
        result = client.call_tool("echo", message="trace me")
        assert result.text() == "trace me"

    lines = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert any(line.get("direction") == "out" and line.get("method") == "tools/call" for line in lines)
    assert any(line.get("direction") == "in" and line.get("message", {}).get("result") for line in lines)

    replay = WireTraceReplay(trace_path)
    response = replay.response_for("tools/call")
    assert response["result"]["content"][0]["text"] == "trace me"


def test_conformance_json_parser_and_score():
    report = parse_conformance_output(
        json.dumps({
            "scenarios": [
                {"name": "initialize", "passed": True, "specVersion": "2025-06-18"},
                {"name": "bad request", "passed": False, "message": "expected 400"},
            ]
        })
    )
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    assert score_conformance(report).badge_text().startswith("passing 1 / 2")
    assert run_report_as_pytest(parse_conformance_output('{"scenarios": [{"name": "ok", "passed": true}]}')) == 0


def test_http_request_includes_session_and_metadata_headers():
    class FakeHTTPX:
        class TimeoutException(Exception):
            pass

        class HTTPStatusError(Exception):
            pass

    class Response:
        def __init__(self, payload, headers=None, status_code=200):
            self._payload = payload
            self.headers = headers or {}
            self.status_code = status_code
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError(self.status_code)

    class FakeClient:
        def __init__(self):
            self.calls = []

        def post(self, url, json, headers, timeout):
            self.calls.append((url, json, headers, timeout))
            if json["method"] == "initialize":
                return Response({"jsonrpc": "2.0", "id": json["id"], "result": {}}, {"mcp-session-id": "sess-1"})
            return Response({"jsonrpc": "2.0", "id": json["id"], "result": {"content": []}})

    fake = FakeClient()
    client = HTTPMCPTestClient("http://example.test/mcp")
    client._client = fake
    client._httpx = FakeHTTPX
    client._resolved_transport = TransportMode.STREAMABLE

    client._request("initialize", {})
    client._request("tools/call", {"name": "search", "arguments": {}})

    headers = fake.calls[-1][2]
    assert headers["Mcp-Session-Id"] == "sess-1"
    assert headers["Mcp-Method"] == "tools/call"
    assert headers["Mcp-Name"] == "search"

    # Sanity: the initialize call must NOT have sent params: {} on the wire,
    # because some servers (FastMCP <2.0 stdio) reject it as -32602.
    init_payload = fake.calls[0][1]
    assert "params" not in init_payload, (
        "Empty params must be omitted from JSON-RPC payload: "
        f"{init_payload}"
    )


def test_initialize_handshake_sends_initialized_notification():
    """MCP spec requires notifications/initialized after initialize.

    FastMCP-backed servers reject all later requests with -32602 until they
    receive it, so MCPTestClient must send it as part of start().
    """
    trace_path = None
    with make_client(SERVER_CMD, timeout=5.0) as client:
        recent = client.wire_trace.recent()

    methods_sent = [
        entry.get("method")
        for entry in recent
        if entry.get("direction") == "out"
    ]
    assert "initialize" in methods_sent
    assert "notifications/initialized" in methods_sent, (
        f"client must send notifications/initialized; saw: {methods_sent}"
    )


def test_smart_timeout_defaults_table_matches_resolver():
    """SMART_TIMEOUT_DEFAULTS is the single source of truth — assert agreement."""
    assert smart_timeout_for_method("tools/call") == SMART_TIMEOUT_DEFAULTS["tools/call"]
    assert smart_timeout_for_method("tasks/get") == SMART_TIMEOUT_DEFAULTS["tasks/*"]
    assert smart_timeout_for_method("sampling/createMessage") == (
        SMART_TIMEOUT_DEFAULTS["sampling/createMessage"]
    )
    assert smart_timeout_for_method("tools/list") == SMART_TIMEOUT_DEFAULTS["*/list"]
    assert smart_timeout_for_method("resources/read") == SMART_TIMEOUT_DEFAULTS["*/read"]
    assert smart_timeout_for_method("unknown/method") == SMART_TIMEOUT_DEFAULTS["default"]


def test_otel_tracer_is_no_op_when_disabled_or_missing():
    """MCPTracer must never raise — disabled, or with OTel uninstalled."""
    disabled = MCPTracer(enabled=False)
    with disabled.span("tools/list"):
        pass

    enabled = MCPTracer(enabled=True)
    with enabled.span("tools/call", session_id="abc", protocol_version="2024-11-05"):
        pass


def test_test_packs_classes_are_importable_templates():
    """Test packs are starting templates: subclassable, type-checked attrs."""
    assert APIWrapperTests.__name__ == "APIWrapperTests"
    assert DatabaseServerTests.__name__ == "DatabaseServerTests"
    assert FilesystemServerTests.__name__ == "FilesystemServerTests"
    assert ShellExecTests.__name__ == "ShellExecTests"

    invocation = ToolInvocation("read_file", {"path": "ok.txt"})
    assert invocation.name == "read_file"
    assert invocation.arguments == {"path": "ok.txt"}

    class MyFs(FilesystemServerTests):
        root_uri = "file:///srv"
        read_tool = invocation

    assert MyFs.root_uri == "file:///srv"
    assert MyFs.read_tool == invocation


def test_bench_run_against_demo_server_produces_latency_summary():
    """run_bench drives the demo server and yields a usable BenchResult."""
    result = run_bench(
        SERVER_CMD,
        duration_s=0.4,
        concurrency=1,
        timeout=5.0,
    )
    assert result.concurrency == 1
    assert result.failures == ()
    methods = {item.method for item in result.latencies}
    assert "ping" in methods, f"expected ping latencies, got: {methods}"
    ping = next(item for item in result.latencies if item.method == "ping")
    assert ping.count > 0
    assert ping.p95_ms >= ping.p50_ms


def test_fastmcp_harness_round_trips_when_fastmcp_installed():
    """FastMCPHarness wraps an in-process FastMCP server."""
    fastmcp = pytest.importorskip("fastmcp")
    from mcp_test.fastmcp import FastMCPHarness

    app = fastmcp.FastMCP("harness-test")

    @app.tool()
    def echo(message: str) -> str:
        return message

    with FastMCPHarness(app) as harness:
        tools = harness.list_tools()
        assert tools.find("echo") is not None
        result = harness.call_tool("echo", message="hello")
        assert "hello" in result.text()
