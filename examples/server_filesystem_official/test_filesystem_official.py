
from mcp_test import MCPTestClient, assert_tool_ok, assert_tool_error


# ── Tool Discovery ────────────────────────────────────────────────────────

def test_list_tools(client):
    c, _ = client
    tools = c.list_tools()
    names = tools.names()
    assert any(n in names for n in ["read_file", "list_directory", "get_file_info"])


# ── Resources ─────────────────────────────────────────────────────────────

def test_list_resources(client):
    c, tmp = client
    (tmp / "readme.txt").write_text("Hello from mcp-test")
    resources = c.list_resources()
    assert isinstance(resources, list)


def test_read_file_resource(client):
    c, tmp = client
    (tmp / "test.txt").write_text("resource content here")
    tools = c.list_tools()
    if tools.find("read_file"):
        result = c.call_tool("read_file", path=str(tmp / "test.txt"))
        assert_tool_ok(result)
        assert "resource content here" in result.text()


# ── Write Operations ─────────────────────────────────────────────────────

def test_write_file(client):
    c, tmp = client
    tools = c.list_tools()
    if tools.find("write_file"):
        result = c.call_tool("write_file", path=str(tmp / "output.txt"), content="written by test")
        assert_tool_ok(result)
        assert (tmp / "output.txt").read_text() == "written by test"


# ── List Directory ────────────────────────────────────────────────────────

def test_list_directory(client):
    c, tmp = client
    (tmp / "a.txt").write_text("a")
    (tmp / "b.txt").write_text("b")

    tools = c.list_tools()
    if tools.find("list_directory"):
        result = c.call_tool("list_directory", path=str(tmp))
        assert_tool_ok(result)
        text = result.text()
        assert "a.txt" in text
        assert "b.txt" in text


# ── Roots Boundary Enforcement ────────────────────────────────────────────

def test_read_outside_roots_is_rejected(client):
    c, _ = client
    tools = c.list_tools()
    if tools.find("read_file"):
        result = c.call_tool("read_file", path="/etc/passwd")
        assert result.is_error()


# ── Schema Validation ────────────────────────────────────────────────────

def test_tool_schemas_valid(client):
    c, _ = client
    c.validate_schemas()
