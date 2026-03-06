# Getting Started with mcp-test

## Installation

```bash
pip install mcp-test
```

For HTTP transport support:
```bash
pip install mcp-test[http]
```

For schema validation:
```bash
pip install mcp-test[schema]
```

Everything:
```bash
pip install mcp-test[all]
```

## Quick Start

### 1. Scaffold your test directory

```bash
mcp-test init
```

This creates a `tests/` directory with an example test and conftest.

### 2. Write your first test

```python
# tests/test_my_server.py
from mcp_test import assert_tool_ok

def test_my_tool(mcp_client):
    result = mcp_client.call_tool("my_tool", param="value")
    assert_tool_ok(result)
    assert "expected" in result.text()
```

### 3. Run tests

```bash
pytest --mcp-command "python my_server.py" -v
```

Or use the CLI wrapper:

```bash
mcp-test run -c "python my_server.py" -v
```

## How It Works

`mcp-test` starts your MCP server as a subprocess, speaks JSON-RPC 2.0 over stdio, and provides a clean Python API for calling tools, listing resources, and validating schemas.

Under the hood:
- A **message pump** thread reads all server output and routes responses by request ID
- **Notifications** are captured without blocking response routing
- **Stderr** is collected for actionable error messages on timeout/crash
- **4-stage shutdown** prevents zombie processes

## Fixtures

The pytest plugin auto-registers these fixtures:

| Fixture | Scope | Use Case |
|---------|-------|----------|
| `mcp_client` | session | One server for all tests (fast) |
| `mcp_client_fresh` | function | Fresh server per test (isolated) |
| `sandboxed_client` | function | Isolated tmp directory (filesystem tests) |
| `snapshot` | function | Snapshot testing for tool outputs |

## Next Steps

- [API Reference](api-reference.md) — Full API documentation
- [CI Integration](ci-integration.md) — GitHub Actions setup
