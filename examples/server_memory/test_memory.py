
from mcp_test import MCPTestClient, assert_tool_ok


# ── Tools ─────────────────────────────────────────────────────────────────

def test_list_tools(client: MCPTestClient):
    tools = client.list_tools()
    assert len(tools) > 0
    names = tools.names()
    assert any(n in names for n in [
        "create_entities", "create_relations", "add_observations",
        "search_nodes", "open_nodes", "read_graph",
    ])


def test_create_entities(client: MCPTestClient):
    tools = client.list_tools()
    if tools.find("create_entities"):
        result = client.call_tool("create_entities", entities=[
            {"name": "mcp-test", "entityType": "project", "observations": ["A testing framework"]},
        ])
        assert_tool_ok(result)


def test_search_nodes(client: MCPTestClient):
    tools = client.list_tools()
    if tools.find("search_nodes"):
        result = client.call_tool("search_nodes", query="mcp-test")
        assert result.is_ok()


def test_read_graph(client: MCPTestClient):
    tools = client.list_tools()
    if tools.find("read_graph"):
        result = client.call_tool("read_graph")
        assert_tool_ok(result)


# ── Resources ─────────────────────────────────────────────────────────────

def test_resources_reflect_state(client: MCPTestClient):
    tools = client.list_tools()
    if tools.find("create_entities"):
        client.call_tool("create_entities", entities=[
            {"name": "TestEntity", "entityType": "test", "observations": ["Created for testing"]},
        ])

    resources = client.list_resources()
    assert isinstance(resources, list)


# ── Prompts ───────────────────────────────────────────────────────────────

def test_prompts_listed(client: MCPTestClient):
    prompts = client.list_prompts()
    assert isinstance(prompts, list)


# ── Schema Validation ────────────────────────────────────────────────────

def test_tool_schemas_valid(client: MCPTestClient):
    client.validate_schemas()
