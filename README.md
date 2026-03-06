# mcp-test

> **pytest for MCP servers** — the testing framework for the Model Context Protocol

---

## Why

MCP (Model Context Protocol) became the Linux Foundation standard in early 2026. Thousands of developers are building MCP servers. **Nobody is testing them.**

`mcp-test` fixes that. Write tests for your MCP tools, resources, and prompts with the same developer experience you expect from pytest.

## Install

```bash
pip install mcp-test
```

## Quick Start

```bash
# Scaffold a test directory
mcp-test init

# Run tests against your MCP server
pytest --mcp-command "python my_server.py" -v
```

## Write Tests

```python
# tests/test_my_server.py
from mcp_test import assert_tool_ok, assert_tool_text_contains

def test_search_returns_results(mcp_client):
    result = mcp_client.call_tool("search", query="machine learning")
    assert_tool_ok(result)
    assert len(result.content) > 0

def test_search_handles_empty_query(mcp_client):
    result = mcp_client.call_tool("search", query="")
    assert result.is_error()

def test_search_schema(mcp_client):
    tools = mcp_client.list_tools()
    search = tools.find("search")
    assert search.required == ["query"]
    assert search.properties["query"]["type"] == "string"
```

## Use in Code

```python
from mcp_test import MCPTestClient

with MCPTestClient.from_command("python my_server.py") as client:
    tools = client.list_tools()
    print(tools.names())

    result = client.call_tool("echo", message="hello")
    print(result.text())
```

## CLI

| Command | Description |
|---------|-------------|
| `mcp-test init` | Scaffold test directory with example tests |
| `mcp-test run -c "python server.py"` | Run tests via pytest |

## Fixtures

The pytest plugin provides two fixtures:

- **`mcp_client`** — Session-scoped. One server process for all tests. Fast.
- **`mcp_client_fresh`** — Function-scoped. Fresh server per test. Use for isolation.

```bash
# Pass your server command via CLI
pytest --mcp-command "python my_server.py" --mcp-timeout 15
```

## Assertion Helpers

```python
from mcp_test import (
    assert_tool_ok,
    assert_tool_error,
    assert_tool_text_contains,
    assert_tool_text_equals,
    assert_tool_error_code,
    assert_tool_content_count,
)
```

## Architecture

Under the hood, `mcp-test` runs your MCP server as a subprocess and speaks JSON-RPC 2.0 over stdio. A background message pump handles response routing, notification dispatching, and concurrent request support — so your tests just work.

## License

MIT
