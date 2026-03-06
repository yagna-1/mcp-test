import pytest
from mcp_test import MCPTestClient

def test_mock_sampling(mcp_client: MCPTestClient):
    with mcp_client.mock_sampling("Fake LLM") as sampler:
        result = mcp_client.call_tool("sampling_tool", prompt="hello world")
        assert result.is_ok()
        assert "Fake LLM" in result.text()
        
    assert sampler.called_once()
    req = sampler.last_request()
    assert req["messages"][0]["content"]["text"] == "hello world"

def test_mock_elicitation(mcp_client: MCPTestClient):
    with mcp_client.mock_elicitation({"city": "Seattle"}) as elicitor:
        result = mcp_client.call_tool("elicit_tool")
        assert result.is_ok()
        assert "Seattle" in result.text()
        
    assert elicitor.called_once()
    assert elicitor.last_schema()["type"] == "object"
