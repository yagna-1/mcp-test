# pytest-mcp-plugin

> **pytest for MCP servers** — the testing framework for the Model Context Protocol.

[![PyPI](https://img.shields.io/pypi/v/pytest-mcp-plugin.svg)](https://pypi.org/project/pytest-mcp-plugin/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-mcp-plugin.svg)](https://pypi.org/project/pytest-mcp-plugin/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```bash
pip install pytest-mcp-plugin
mcp-test demo            # runs a bundled MCP server + tests in 5 seconds
```

> **Note on the name.** This package is published on PyPI as `pytest-mcp-plugin`.
> The `mcp-test` name on PyPI is reserved by Anthropic for their official MCP
> SDK, and PyPI's name-similarity policy blocks close variants like `mcptest`.
> The CLI binary is still `mcp-test`, and the Python module is still `mcp_test`.

---

## Why

MCP (Model Context Protocol) is the standard interface every AI agent now uses
to talk to tools, files, databases, and APIs. Thousands of teams are shipping
MCP servers in 2026. **Almost none of them are tested.**

`pytest-mcp-plugin` fixes that. Write tests for your MCP tools, resources, and prompts
with the same developer experience you expect from `pytest`.

- `pytest` plugin with auto-registered fixtures
- stdio and HTTP/SSE transports
- Schema validation, snapshot testing, coverage reports
- Auth + policy assertions
- Drop-in GitHub Action

---

## 60-second tour

```bash
pip install pytest-mcp-plugin
mcp-test demo
```

That spins up a bundled MCP server and runs a real test suite against it —
no setup, no API keys, no servers to write first.

```text
🚀 mcp-test demo
   server  : python -m mcp_test._demo_server
   workdir : /tmp/mcptest-demo-xxxx

test_demo.py::test_lists_tools         PASSED
test_demo.py::test_echo                PASSED
test_demo.py::test_add                 PASSED
test_demo.py::test_uppercase           PASSED
test_demo.py::test_fail_returns_error  PASSED

✅ Demo passed. Now write tests for your own MCP server:
   mcp-test init
```

---

## Test your own server

```bash
cd my-mcp-server/
mcp-test init
pytest --mcp-command "python my_server.py" -v
```

Or pin the command in your `pyproject.toml`:

```toml
[tool.mcp-test]
command = "python my_server.py"
timeout = 10

[tool.mcp-test.timeouts]
"tools/list" = 5
"tools/call" = 30
"sampling/createMessage" = 60
```

…and just run:

```bash
mcp-test run
```

---

## Write tests

```python
# tests/test_my_server.py
from mcp_test import assert_tool_ok, assert_tool_error, assert_tool_text_contains


def test_search_returns_results(mcp_client):
    result = mcp_client.call_tool("search", query="machine learning")
    assert_tool_ok(result)
    assert len(result.content) > 0


def test_search_handles_empty_query(mcp_client):
    result = mcp_client.call_tool("search", query="")
    assert_tool_error(result)


def test_search_schema(mcp_client):
    tools = mcp_client.list_tools()
    search = tools.find("search")
    assert search.required == ["query"]
    assert search.properties["query"]["type"] == "string"
```

## Use as a library

```python
from mcp_test import MCPTestClient

with MCPTestClient.from_command("python my_server.py") as client:
    tools = client.list_tools()
    print(tools.names())

    result = client.call_tool("echo", message="hello")
    print(result.text())
```

---

## Run on every PR (GitHub Action)

`pytest-mcp-plugin` ships as a composite action you can drop into any repo:

```yaml
# .github/workflows/mcp-tests.yml
name: MCP Tests

on:
  pull_request:
  push:
    branches: [main]

jobs:
  mcp-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: yagna-1/mcp-test@v0.2.0
        with:
          command: "python my_server.py"
          test-dir: "tests"
```

That's it. The action installs `pytest-mcp-plugin`, runs your suite against your MCP
server, and posts a JUnit XML report.

---

## CLI reference

| Command | Description |
|---|---|
| `mcp-test demo` | Run the bundled demo server + tests (zero setup) |
| `mcp-test init` | Scaffold `tests/` with example MCP tests |
| `mcp-test run -c "python server.py"` | Run pytest against your server |
| `mcp-test snapshot -c "..."` | Run snapshot tests (`--update` to refresh) |
| `mcp-test coverage -c "..."` | Print coverage report (tools/prompts/resources) |
| `mcp-test validate -c "..."` | Validate tool input schemas |
| `mcp-test conformance --url "..."` | Run the upstream MCP conformance suite through `npx` |
| `mcp-test bench -c "..."` | Run lightweight p50/p95/p99 regression probes |

All commands accept `--help` for full options.

---

## Fixtures

The pytest plugin auto-registers three fixtures:

| Fixture | Scope | Use for |
|---|---|---|
| `mcp_client` | session | Fast — one server process for the whole test run |
| `mcp_client_fresh` | function | Clean state per test |
| `sandboxed_client` | function | Fresh server with `cwd=tmp_path` and `DATA_DIR=tmp_path` |
| `snapshot` | function | Snapshot testing helper |

```bash
pytest --mcp-command "python my_server.py" --mcp-timeout 15 \
  --mcp-timeout-method tools/call=30 \
  --mcp-trace .mcp-test/trace.jsonl
```

`--mcp-timeout-method METHOD=SECONDS` may be passed multiple times, and the
same values can live in `[tool.mcp-test.timeouts]`. `--mcp-trace` records JSONL
wire frames; in CI, failing tests also dump recent frames to `mcp-traces/`.

Use `mcp-test conformance --url ... --pytest-items` when you want each parsed
upstream scenario re-emitted as a normal pytest test item.

## Spec-version markers

Mark tests by required MCP spec version; the plugin auto-skips tests against
older servers.

```python
import pytest

@pytest.mark.mcp_v3  # requires spec >= 2025-06-18
def test_uses_recent_feature(mcp_client):
    ...
```

Available markers: `mcp_v2`, `mcp_v3`, `mcp_v4`.

## Assertion helpers

```python
from mcp_test import (
    assert_tool_ok,
    assert_tool_error,
    assert_tool_error_code,
    assert_tool_text_contains,
    assert_tool_text_equals,
    assert_tool_content_count,
    assert_policy_allows,
    assert_policy_blocks,
    assert_task_completes_within,
    assert_task_cancelled,
    assert_task_failed,
)
```

---

## Architecture

`pytest-mcp-plugin` runs your MCP server as a subprocess and speaks JSON-RPC 2.0 over
stdio (or HTTP/SSE for the HTTP transport). A background message pump handles
response routing, notification dispatching, and concurrent request support —
so your tests just work.

Source modules:

```
mcp_test/
  client.py            # stdio JSON-RPC client
  http_client.py       # HTTP + SSE client
  plugin.py            # pytest plugin (fixtures, options, markers)
  cli.py               # mcp-test CLI
  assertions.py        # assert_tool_*, assert_policy_*, assert_task_*
  schema_validator.py  # JSON Schema validation for tool inputs
  coverage.py          # tools/prompts/resources coverage tracker
  snapshot.py          # snapshot testing
  auth.py              # OAuth / PKCE / RFC 9728 helpers
  bench.py             # lightweight regression benchmark probes
  conformance.py       # bridge to @modelcontextprotocol/conformance
  compliance.py        # conformance score helpers
  fastmcp.py           # in-process FastMCP harness adapter
  replay.py            # deterministic wire-trace replay lookup
  pagination.py        # cursor pagination helpers
  test_packs.py        # reusable server-shape test packs
  timeouts.py          # per-method timeout policy
  wire_trace.py        # JSONL wire trace recorder
  types.py             # ToolResult, ToolSchema, MCPError, ...
  _demo_server.py      # bundled demo server (used by `mcp-test demo`)
```

## Status

`pytest-mcp-plugin` is **beta**. The CLI surface and plugin API are stable; minor
internals (schema validator details, snapshot format) may still change.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for what's next, what we explicitly won't build,
and how we plan to complement (not compete with) Anthropic's official
[`@modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance)
and [`@modelcontextprotocol/inspector`](https://github.com/modelcontextprotocol/inspector).

## Contributing

Bug reports, feature requests, and PRs welcome at
[github.com/yagna-1/mcp-test](https://github.com/yagna-1/mcp-test).

## License

MIT
