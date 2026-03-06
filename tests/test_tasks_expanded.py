import pytest
import time


def test_task_input_required_state(mcp_client):
    result = mcp_client.call_tool("input_required_job")
    raw = result.raw.get("result", {})
    task_data = raw.get("task", {})
    assert task_data["status"] == "input_required"
    assert "elicitationRequest" in task_data
    assert task_data["elicitationRequest"]["message"] == "What API key should I use?"


def test_task_send_input_completes(mcp_client):
    result = mcp_client.call_tool("input_required_job")
    task_data = result.raw.get("result", {}).get("task", {})
    task_id = task_data["id"]

    task = mcp_client.send_task_input(task_id, {"key": "my-api-key-123"})
    assert task.status == "completed"
    assert task.output is not None
    assert task.output["input_received"]["key"] == "my-api-key-123"


def test_task_cancel(mcp_client):
    task_id = mcp_client.call_tool_async("async_job")

    task = mcp_client.cancel_task(task_id)
    assert task.status == "cancelled"

    task = mcp_client.poll_task(task_id)
    assert task.status == "cancelled"


def test_task_unknown_id_returns_error(mcp_client):
    from mcp_test.types import MCPClientError
    try:
        mcp_client.poll_task("nonexistent-task-id-xyz")
        pytest.fail("Expected MCPClientError for unknown task ID")
    except MCPClientError:
        pass


def test_task_wait_for_completion(mcp_client):
    task_id = mcp_client.call_tool_async("async_job")
    task = mcp_client.wait_for_task(task_id, timeout=10.0, poll_interval=0.3)
    assert task.status == "completed"


def test_task_wait_with_input_handler(mcp_client):
    result = mcp_client.call_tool("input_required_job")
    task_data = result.raw.get("result", {}).get("task", {})
    task_id = task_data["id"]

    def handle_input(elicitation_req):
        return {"key": "auto-provided-key"}

    task = mcp_client.wait_for_task(task_id, timeout=10.0, input_handler=handle_input)
    assert task.status == "completed"
    assert task.output["input_received"]["key"] == "auto-provided-key"


def test_task_is_terminal_property(mcp_client):
    from mcp_test.types import Task
    t = Task(id="t1", status="completed")
    assert t.is_terminal is True
    t = Task(id="t2", status="working")
    assert t.is_terminal is False
    t = Task(id="t3", status="cancelled")
    assert t.is_terminal is True
    t = Task(id="t4", status="failed")
    assert t.is_terminal is True


def test_task_needs_input_property(mcp_client):
    from mcp_test.types import Task
    t = Task(id="t1", status="input_required")
    assert t.needs_input is True
    t = Task(id="t2", status="working")
    assert t.needs_input is False
