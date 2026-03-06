# API Reference

## MCPTestClient

The core client for testing MCP servers over stdio transport.

### Construction

```python
from mcp_test import MCPTestClient, make_client

# Using context manager (recommended)
with make_client("python my_server.py") as client:
    result = client.call_tool("echo", message="hi")

# With options
with make_client(
    "python my_server.py",
    timeout=15.0,
    startup_timeout=30.0,
    env={"API_KEY": "test-key"},
    cwd="/path/to/server",
) as client:
    ...

# Factory method
with MCPTestClient.from_command("python my_server.py") as client:
    ...
```

### Methods

#### `call_tool(name: str, **arguments) -> ToolResult`
Call an MCP tool by name with keyword arguments.

```python
result = client.call_tool("search", query="hello", limit=10)
```

#### `list_tools() -> ToolList`
List all available tools on the server.

```python
tools = client.list_tools()
print(tools.names())       # ["search", "get_doc", ...]
tool = tools.find("search")
print(tool.required)        # ["query"]
print(tool.properties)      # {"query": {"type": "string"}, ...}
```

#### `list_resources() -> list[Resource]`
List all available resources.

#### `read_resource(uri: str) -> ResourceContent`
Read a resource by URI.

#### `list_prompts() -> list[Prompt]`
List all available prompts.

#### `get_prompt(name: str, arguments: dict | None) -> dict`
Get a rendered prompt by name.

### Properties

- `notifications` — List of `(method, params)` tuples received from server
- `called_tools` — Set of tool names called during this session

---

## ToolResult

Returned by `call_tool()`.

```python
result = client.call_tool("echo", message="hi")

result.is_ok()        # True if tool succeeded
result.is_error()     # True if tool failed
result.text()         # Joined text from all text content blocks
result.content        # list[Content] — all content blocks
result.error          # MCPError | None — error details if failed
result.raw            # dict — raw JSON-RPC response
```

---

## ToolSchema / ToolList

```python
tools = client.list_tools()  # ToolList
len(tools)                     # number of tools
tools.names()                  # list of tool names
tool = tools.find("search")   # ToolSchema | None

tool.name            # "search"
tool.description     # "Search for documents"
tool.required        # ["query"]
tool.properties      # {"query": {"type": "string"}}
tool.input_schema    # full JSON Schema dict
```

---

## Assertion Helpers

```python
from mcp_test import (
    assert_tool_ok,             # assert result.is_ok()
    assert_tool_error,          # assert result.is_error()
    assert_tool_text_contains,  # assert substring in result.text()
    assert_tool_text_equals,    # assert result.text() == expected
    assert_tool_error_code,     # assert result.error.code == code
    assert_tool_content_count,  # assert len(result.content) == n
)
```

---

## Schema Validation

```python
from mcp_test import validate_schemas, validate_tool_schema

tools = client.list_tools()
errors = validate_schemas(tools)
for err in errors:
    print(f"[{err.severity}] {err.tool_name}: {err.message}")
```

---

## Snapshot Testing

```python
def test_output_snapshot(mcp_client, snapshot):
    result = mcp_client.call_tool("search", query="python")
    snapshot.assert_match(result)

    # With normalization
    snapshot.assert_match(result, ignore_keys=["timestamp", "id"])
    snapshot.assert_match(result, sort_arrays=True)
```

Update snapshots: `pytest --snapshot-update`

---

## Coverage Tracking

```python
from mcp_test import CoverageTracker

tracker = CoverageTracker()
tracker.register_tools(client.list_tools().names())
tracker.record_call("search", test_name="test_search")
report = tracker.report()
print(report.overall_percentage)
```

CLI: `mcp-test coverage -c "python my_server.py"`

---

## HTTP Transport

```python
from mcp_test.http_client import HTTPMCPTestClient

with HTTPMCPTestClient.from_url("http://localhost:8080") as client:
    result = client.call_tool("search", query="hello")
```

Requires: `pip install mcp-test[http]`

---

## Exceptions

| Exception | When |
|-----------|------|
| `MCPClientError` | Base class for all client errors |
| `MCPServerCrash` | Server process exited unexpectedly |
| `MCPTimeoutError` | Request timed out waiting for response |
