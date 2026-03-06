import pytest
from mcp_test import MCPTestClient
from mcp_test.annotations import assert_tool_is_destructive, assert_tool_has_annotation

def test_annotated_tool(mcp_client: MCPTestClient):
    assert_tool_has_annotation(mcp_client, "annotated_tool", "read_only_hint", True)
    
    with pytest.raises(AssertionError):
        assert_tool_is_destructive(mcp_client, "annotated_tool")
