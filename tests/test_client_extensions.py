from mcp_test import MCPTestClient
from mcp_test.assertions import assert_task_completes_within

def test_ping(mcp_client: MCPTestClient):
    result = mcp_client.ping()
    assert "result" in result
    assert result["result"] == {}

def test_resources(mcp_client: MCPTestClient):
    resources = mcp_client.list_resources()
    assert len(resources) >= 1
    uris = [r.uri for r in resources]
    assert "test://echo" in uris
    
    content = mcp_client.read_resource("test://echo")
    assert content.uri == "test://echo"
    assert "echo resource content" in content.text
    
    mcp_client.subscribe_resource("test://echo")
    mcp_client.unsubscribe_resource("test://echo")

def test_prompts(mcp_client: MCPTestClient):
    prompts = mcp_client.list_prompts()
    assert len(prompts) >= 1
    names = [p.name for p in prompts]
    assert "echo_prompt" in names
    
    p = mcp_client.get_prompt("echo_prompt", {"input": "test msg"})
    assert p["result"]["description"] == "Echo prompt"
    assert p["result"]["messages"][0]["content"]["text"] == "test msg"

def test_tasks(mcp_client: MCPTestClient):
    task_id = mcp_client.call_tool_async("async_job")
    assert task_id.startswith("task-")
    
    task = assert_task_completes_within(mcp_client, task_id, timeout=2.0)
    assert task.status == "completed"

def test_cancellation(mcp_client: MCPTestClient):
    with mcp_client.cancel_after(seconds=0.1):
        res = mcp_client.call_tool("slow_echo", message="test", delay=1)
        assert res.is_error()
        assert res.error.code == -32800

