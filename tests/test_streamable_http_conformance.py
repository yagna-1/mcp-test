"""Streamable-HTTP transport conformance tests.

Boots the bundled FastMCP-backed HTTP demo server (`mcp_test._demo_server_http`)
in a subprocess and exercises the parts of the MCP Streamable-HTTP spec that
the structural plumbing in `http_client.py` already supports — but which were
never end-to-end-verified before this file existed.

Skipped when:
* `fastmcp` is not installed (HTTP demo server requires it),
* `httpx` is not installed (HTTP client requires it).

Each test boots its own server on an OS-chosen free port so they can run in
parallel under pytest-xdist without colliding.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("fastmcp", reason="fastmcp required for HTTP demo server")
pytest.importorskip("httpx", reason="httpx required for the HTTP client")

from mcp_test.http_client import HTTPMCPTestClient  # noqa: E402


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(host: str, port: int, *, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return
            except OSError:
                time.sleep(0.1)
    raise RuntimeError(f"HTTP demo server did not start on {host}:{port} within {timeout}s")


@pytest.fixture()
def http_demo_server():
    """Spawn a fresh HTTP demo server on a free port, tear it down after."""
    port = _free_port()
    env = {
        **os.environ,
        "MCP_TEST_DEMO_PORT": str(port),
        "MCP_TEST_DEMO_HOST": "127.0.0.1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_test._demo_server_http"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_port("127.0.0.1", port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def test_initialize_handshake_over_streamable_http(http_demo_server):
    """The server completes the MCP initialize handshake over Streamable HTTP."""
    with HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0) as client:
        assert client.server_info.get("name"), "server must advertise serverInfo.name"
        assert client.server_version, "server must advertise protocolVersion"
        assert "tools" in client.server_capabilities, "server must advertise tools capability"


def test_session_id_is_assigned_and_reused(http_demo_server):
    """Per spec: server returns Mcp-Session-Id on init; clients echo it on later requests."""
    with HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0) as client:
        session = client._session_id  # populated by the wrapped initialize call
        assert session, (
            "server must return Mcp-Session-Id on initialize "
            "(Streamable-HTTP spec, 'Session management')"
        )

        # A subsequent tools/list must reuse the session id.
        client.list_tools()
        # Find the OUTBOUND tools/list entry in the wire trace.
        out_tools_list = [
            entry for entry in client._trace.recent()
            if entry.get("direction") == "out" and entry.get("method") == "tools/list"
        ]
        assert out_tools_list, "expected an outbound tools/list entry in the trace"
        sent_headers = out_tools_list[-1].get("metadata", {}).get("headers", {})
        assert sent_headers.get("Mcp-Session-Id") == session, (
            "client must echo Mcp-Session-Id on subsequent requests; "
            f"actual headers: {sent_headers}"
        )


def test_initialize_does_not_send_session_id_header(http_demo_server):
    """Per spec: the FIRST request (initialize) must not include Mcp-Session-Id."""
    with HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0) as client:
        traces = [
            entry for entry in client._trace.recent()
            if entry.get("direction") == "out"
            and entry.get("method") == "initialize"
        ]
        assert traces, "expected an outbound initialize entry in the wire trace"
        init_headers = traces[0].get("metadata", {}).get("headers", {})
        assert "Mcp-Session-Id" not in init_headers, (
            "initialize must not carry an Mcp-Session-Id header; "
            f"actual headers: {init_headers}"
        )


def test_tools_list_returns_advertised_tools(http_demo_server):
    """tools/list returns the tools the demo server registered."""
    with HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0) as client:
        tools = client.list_tools()
        names = set(tools.names())
        # The HTTP demo server advertises echo, add, uppercase, fail.
        assert {"echo", "add", "uppercase"}.issubset(names), (
            f"expected echo/add/uppercase tools, got: {names}"
        )


def test_tool_call_round_trips_over_http(http_demo_server):
    """A tools/call round-trip succeeds and returns content over HTTP."""
    with HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0) as client:
        result = client.call_tool("echo", message="hello-streamable-http")
        assert result.is_ok(), f"echo failed: {result}"
        assert "hello-streamable-http" in result.text()


def test_close_terminates_session(http_demo_server):
    """HTTPMCPTestClient.close() sends DELETE / to drop the server-side session."""
    client = HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0)
    client.start()
    session = client._session_id
    assert session

    client.close()

    # After close, a subsequent request with the *same* session id must be
    # rejected by the server. We talk raw httpx here so we don't accidentally
    # auto-re-initialize through the client.
    import httpx

    with httpx.Client() as raw:
        resp = raw.post(
            http_demo_server,
            json={
                "jsonrpc": "2.0",
                "id": 999,
                "method": "tools/list",
            },
            headers={
                "Mcp-Session-Id": session,
                "Mcp-Method": "tools/list",
                "Accept": "application/json,text/event-stream",
            },
            timeout=5.0,
        )
    # The server is allowed to return either 404 (session terminated) or
    # 400 (session not found); both signal a successful tear-down.
    assert resp.status_code in {400, 404}, (
        f"expected 400/404 after session termination, got {resp.status_code}: {resp.text}"
    )


def test_protocol_version_is_advertised(http_demo_server):
    """The server's initialize result advertises a known MCP protocol version."""
    with HTTPMCPTestClient.from_url(http_demo_server, timeout=10.0) as client:
        # Known versions through Q2 2026.
        known = {"2024-11-05", "2025-06-18", "2025-11-25"}
        assert client.server_version in known or client.server_version.startswith("DRAFT-"), (
            f"server advertised unexpected protocol version: {client.server_version!r}"
        )
