
import pytest
from mcp_test import MCPTestClient, assert_tool_ok


# ── Tools ─────────────────────────────────────────────────────────────────

def test_list_tools(client: MCPTestClient):
    tools = client.list_tools()
    assert len(tools) > 0
    names = tools.names()
    assert "echo" in names or "add" in names


def test_echo_tool(client: MCPTestClient):
    result = client.call_tool("echo", message="hello from mcp-test")
    assert_tool_ok(result)
    assert "hello from mcp-test" in result.text()


def test_add_tool(client: MCPTestClient):
    tools = client.list_tools()
    if not tools.find("add"):
        pytest.skip("add tool not available on this server")
    result = client.call_tool("add", a=2, b=3)
    assert_tool_ok(result)
    assert "5" in result.text()


def test_tool_schemas_valid(client: MCPTestClient):
    client.validate_schemas()


# ── Resources ─────────────────────────────────────────────────────────────

def test_resources_listed(client: MCPTestClient):
    resources = client.list_resources()
    assert len(resources) > 0


def test_resource_readable(client: MCPTestClient):
    resources = client.list_resources()
    if resources:
        content = client.read_resource(resources[0].uri)
        assert content.uri == resources[0].uri


# ── Prompts ───────────────────────────────────────────────────────────────

def test_prompts_listed(client: MCPTestClient):
    prompts = client.list_prompts()
    assert len(prompts) > 0


def test_prompt_renders(client: MCPTestClient):
    prompts = client.list_prompts()
    if prompts:
        name = prompts[0].name
        args = {}
        for arg in prompts[0].arguments:
            if arg.get("required", False):
                args[arg["name"]] = "test-value"
        result = client.get_prompt(name, args)
        assert "result" in result


# ── Sampling ──────────────────────────────────────────────────────────────

def test_sampling_tool(client: MCPTestClient):
    tools = client.list_tools()
    if tools.find("sampleLLM"):
        with client.mock_sampling(response="Mock LLM response") as sampler:
            result = client.call_tool("sampleLLM", prompt="test", maxTokens=10)
            assert result.is_ok()
            assert sampler.called_once()
