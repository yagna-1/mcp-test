"""Smoke test used by the example-action.yml workflow.

Validates that the composite action can install pytest-mcp-plugin and run a real test
suite against the bundled demo server.
"""

from mcp_test import assert_tool_ok, assert_tool_error, assert_tool_text_equals


def test_lists_demo_tools(mcp_client):
    names = {t.name for t in mcp_client.list_tools()}
    assert {"echo", "add", "uppercase", "fail"}.issubset(names)


def test_echo(mcp_client):
    result = mcp_client.call_tool("echo", message="hello")
    assert_tool_ok(result)
    assert_tool_text_equals(result, "hello")


def test_add(mcp_client):
    result = mcp_client.call_tool("add", a=10, b=32)
    assert_tool_text_equals(result, "42")


def test_fail_returns_error(mcp_client):
    result = mcp_client.call_tool("fail")
    assert_tool_error(result)
