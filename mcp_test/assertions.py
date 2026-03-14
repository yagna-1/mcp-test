
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .client import MCPTestClient
from .types import ToolResult, Task


def assert_tool_ok(result: ToolResult, msg: str = "") -> None:
    detail = msg or f"Expected tool result to be OK, got error: {result._error or result.raw}"
    assert result.is_ok(), detail


def assert_tool_error(result: ToolResult, msg: str = "") -> None:
    detail = msg or f"Expected tool result to be an error, but it was OK: {result.raw}"
    assert result.is_error(), detail


def assert_tool_text_contains(result: ToolResult, substring: str, msg: str = "") -> None:
    text = result.text()
    detail = msg or f"Expected tool result text to contain {substring!r}, got: {text!r}"
    assert substring in text, detail


def assert_tool_text_equals(result: ToolResult, expected: str, msg: str = "") -> None:
    text = result.text()
    detail = msg or f"Expected tool result text to equal {expected!r}, got: {text!r}"
    assert text == expected, detail


def assert_tool_error_code(result: ToolResult, code: int, msg: str = "") -> None:
    assert result.is_error(), f"Expected an error result, but got OK: {result.raw}"
    assert result.error is not None, "Result is marked as error but has no error object"
    detail = msg or f"Expected error code {code}, got {result.error.code}"
    assert result.error.code == code, detail


def assert_tool_content_count(result: ToolResult, count: int) -> None:
    assert len(result.content) == count, f"Expected {count} content blocks, got {len(result.content)}"


def assert_task_completes_within(
    client: MCPTestClient, task_id: str, timeout: float = 5.0,
    input_handler: Any = None,
) -> Task:
    start = time.time()
    while time.time() - start < timeout:
        task = client.poll_task(task_id)
        if task.status == "completed":
            return task
        if task.status == "failed":
            assert False, f"Task {task_id} failed: {task.error or 'unknown error'}"
        if task.status == "cancelled":
            assert False, f"Task {task_id} was cancelled"
        if task.status == "input_required":
            if input_handler and task.elicitation_request:
                input_data = input_handler(task.elicitation_request)
                client.send_task_input(task_id, input_data)
                continue
            else:
                assert False, f"Task {task_id} requires input but no handler provided"
        time.sleep(0.1)
    raise AssertionError(f"Task {task_id} did not complete within {timeout} seconds")


def assert_task_cancelled(client: MCPTestClient, task_id: str) -> None:
    task = client.poll_task(task_id)
    assert task.status == "cancelled", f"Expected task {task_id} to be cancelled, got {task.status}"


def assert_task_failed(client: MCPTestClient, task_id: str) -> None:
    task = client.poll_task(task_id)
    assert task.status == "failed", f"Expected task {task_id} to be failed, got {task.status}"


def assert_policy_allows(client: MCPTestClient, tool_name: str, astragraph_url: str, **arguments: Any) -> ToolResult:
    """Assert a tool call is allowed by AstraGraph policy."""
    result = client.call_tool(tool_name, **arguments)
    assert result.is_ok(), f"Expected allow, got: {result}"

    violations = _fetch_violations(astragraph_url, tool_name)
    assert len(violations) == 0, f"Expected no policy violations for {tool_name}, got: {violations}"
    return result


def assert_policy_blocks(client: MCPTestClient, tool_name: str, astragraph_url: str, **arguments: Any) -> ToolResult:
    """Assert a tool call is blocked by AstraGraph policy."""
    result = client.call_tool(tool_name, **arguments)
    assert result.is_error(), f"Expected block, got: {result}"
    error_text = ""
    if result.error is not None:
        error_text = result.error.message or ""
    if not error_text:
        error_text = json.dumps(result.raw)
    assert "POLICY_VIOLATION" in error_text, f"Expected POLICY_VIOLATION, got: {error_text}"

    violations = _fetch_violations(astragraph_url, tool_name)
    assert len(violations) > 0, f"Expected at least one violation for {tool_name}, got none"
    return result


def _fetch_violations(astragraph_url: str, tool_name: str) -> list[dict[str, Any]]:
    token = os.environ.get("ASTRAGRAPH_TOKEN", "")
    query = urlencode({"tool_name": tool_name})
    url = f"{astragraph_url.rstrip('/')}/audit/violations?{query}"
    req = Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "violations", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []
