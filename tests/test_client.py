
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

from mcp_test import (
    MCPServerCrash,
    MCPTimeoutError,
    make_client,
    assert_tool_ok,
    assert_tool_error,
    assert_tool_text_contains,
    assert_tool_text_equals,
    assert_tool_content_count,
)

ECHO_SERVER = os.path.join(os.path.dirname(__file__), "fixtures", "echo_server.py")
SERVER_CMD = f"{sys.executable} {ECHO_SERVER}"


@pytest.fixture(scope="module")
def client():
    with make_client(SERVER_CMD, timeout=5.0) as c:
        yield c


@pytest.fixture
def fresh_client():
    with make_client(SERVER_CMD, timeout=5.0) as c:
        yield c


def test_echo_returns_correct_value(client):
    result = client.call_tool("echo", message="hello world")
    assert_tool_ok(result)
    assert_tool_text_equals(result, "hello world")


def test_sequential_calls_return_correct_values(client):
    for i in range(10):
        result = client.call_tool("echo", message=f"msg-{i}")
        assert_tool_ok(result)
        assert_tool_text_equals(result, f"msg-{i}")


def test_concurrent_calls_return_correct_values(client):
    results: dict[int, str] = {}
    errors: list[Exception] = []

    def call_echo(idx: int):
        try:
            result = client.call_tool("echo", message=f"thread-{idx}")
            results[idx] = result.text()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=call_echo, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Thread errors: {errors}"
    for i in range(10):
        assert results[i] == f"thread-{i}", f"Thread {i} got wrong result: {results[i]}"


def test_notification_during_initialize_does_not_block(fresh_client):
    result = fresh_client.call_tool("echo", message="post-init")
    assert_tool_ok(result)
    assert_tool_text_equals(result, "post-init")
    assert len(fresh_client.notifications) > 0, "Should have received at least one notification"


def test_is_error_result_handled(client):
    result = client.call_tool("error_tool", message="bad input")
    assert_tool_error(result)
    assert_tool_text_contains(result, "bad input")


def test_unknown_tool_returns_rpc_error(client):
    result = client.call_tool("nonexistent_tool")
    assert result.is_error()
    assert result.error is not None
    assert result.error.code == -32601


def test_timeout_raises_mcp_timeout_error():
    with make_client(SERVER_CMD, timeout=0.5) as c:
        with pytest.raises(MCPTimeoutError, match="No response for"):
            c.call_tool("slow_echo", message="slow", delay=5)


def test_server_crash_detected():
    with make_client(SERVER_CMD, timeout=5.0) as c:
        with pytest.raises(MCPServerCrash):
            c.call_tool("crash_tool")


def test_list_tools_returns_expected_tools(client):
    tools = client.list_tools()
    names = tools.names()
    assert "echo" in names
    assert "slow_echo" in names
    assert "error_tool" in names
    assert "crash_tool" in names
    assert "multi_content" in names


def test_tool_schema_properties(client):
    tools = client.list_tools()
    echo = tools.find("echo")
    assert echo is not None
    assert echo.required == ["message"]
    assert "message" in echo.properties
    assert echo.properties["message"]["type"] == "string"


def test_multi_content_blocks(client):
    result = client.call_tool("multi_content", count=3)
    assert_tool_ok(result)
    assert_tool_content_count(result, 3)
    assert result.content[0].text == "block-0"
    assert result.content[1].text == "block-1"
    assert result.content[2].text == "block-2"


def test_tool_result_text(client):
    result = client.call_tool("multi_content", count=2)
    assert result.text() == "block-0\nblock-1"


def test_close_stops_server():
    c = make_client(SERVER_CMD, timeout=5.0)
    c.start()
    pid = c._process.pid
    c.close()
    assert c._process is None
    try:
        os.kill(pid, 0)
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            pytest.fail(f"Server process {pid} is still running after close()")
        except OSError:
            pass
    except OSError:
        pass


def test_called_tools_tracking(client):
    assert "echo" in client.called_tools
