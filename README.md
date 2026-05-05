# pytest-mcp-plugin

> **pytest for MCP servers** — the testing framework for the Model Context Protocol.

[![PyPI](https://img.shields.io/pypi/v/pytest-mcp-plugin.svg)](https://pypi.org/project/pytest-mcp-plugin/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-mcp-plugin.svg)](https://pypi.org/project/pytest-mcp-plugin/)
[![CI](https://github.com/yagna-1/mcp-test/actions/workflows/ci.yml/badge.svg)](https://github.com/yagna-1/mcp-test/actions/workflows/ci.yml)
[![Conformance](https://img.shields.io/badge/MCP%20conformance-baseline%20locked-brightgreen)](./conformance-baseline.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```bash
pip install pytest-mcp-plugin
mcp-test demo       # runs a bundled MCP server + tests in 5 seconds
```

> **About the name.** This package is `pytest-mcp-plugin` on PyPI. The
> `mcp-test` name is reserved by Anthropic for their official MCP SDK, and
> PyPI's name-similarity policy blocks close variants. The CLI binary is still
> `mcp-test`, the Python module is still `mcp_test`.

---

## Why this exists

MCP servers turn LLM output into real-world side-effects: file reads, SQL
queries, HTTP calls, shell commands. Most of them ship with zero automated
tests. `pytest-mcp-plugin` is the missing test harness:

* **Real protocol coverage** — runs against Anthropic's own
  [`@modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance)
  suite in CI on every PR. Our bundled demo server passes the suite modulo
  features it intentionally doesn't implement (locked in
  [`conformance-baseline.yml`](./conformance-baseline.yml)).
* **Batteries-included security packs** — opt-in mixin classes that test
  path traversal, SQL injection, credential leakage, and shell-metacharacter
  injection against your server with one subclass declaration.
* **stdio + Streamable-HTTP** — same fixtures, same assertions, both
  transports. Includes an in-process FastMCP harness for sub-second tests.
* **Built for CI** — pytest-native, JUnit XML output, automatic wire-trace
  dumps on CI failure, `mcp-test` GitHub Action for one-line integration.

---

## 60-second tour

```bash
pip install pytest-mcp-plugin
mcp-test demo
```

That spins up a bundled stdio MCP server and runs a real test suite against it
— no setup, no API keys, no servers to write first.

```text
test_demo.py::test_lists_tools         PASSED
test_demo.py::test_echo                PASSED
test_demo.py::test_add                 PASSED
test_demo.py::test_uppercase           PASSED
test_demo.py::test_fail_returns_error  PASSED

✅ Demo passed. Now write tests for your own MCP server:
   mcp-test init
```

For HTTP / FastMCP servers:

```bash
pip install 'pytest-mcp-plugin[fastmcp]'
python -m mcp_test._demo_server_http &     # boots on :8765
mcp-test conformance --url http://127.0.0.1:8765/mcp
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
```

…then just run:

```bash
mcp-test run
```

For per-method timeouts, prefer the built-in smart defaults:

```bash
mcp-test run --smart-timeouts
# or list explicit overrides:
pytest --mcp-timeout-method "tools/call=30" --mcp-timeout-method "sampling/createMessage=120"
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

---

## Batteries-included security test packs

If your server fits one of these shapes, you get 4–8 production-grade
security assertions for free by subclassing one mixin:

| Pack | Catches |
|---|---|
| [`FilesystemServerTests`](./examples/filesystem_server/) | path traversal, absolute-path acceptance, sandbox escape via symlinks, resource scope creep |
| [`DatabaseServerTests`](./examples/database_server/) | read-only tools that quietly mutate, SQL injection via parameter concatenation |
| [`APIWrapperTests`](./examples/api_wrapper_server/) | tools that call upstream anonymously without configured creds, API-key leakage in tool output |
| [`ShellExecTests`](./examples/shell_exec_server/) | `shell=True` injection (canary-probed), allowlist bypass, hidden non-zero exits |

Each pack ships with a worked-example demo server that passes the pack —
look in `examples/<server>/` for the reference implementation and the
test file that opts in. Copy-paste-modify is the intended workflow.

```python
from mcp_test.test_packs import FilesystemServerTests

class TestMyFsServer(FilesystemServerTests):
    expected_tools = ("read_file", "list_directory")
    read_tool = "read_file"
    list_tool = "list_directory"
    safe_path = "data/known-good.txt"
    # That's it — you now have 5 security tests.
```

---

## MCP spec conformance

`pytest-mcp-plugin` runs Anthropic's official
[`@modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance)
suite against the bundled demo server on every PR. The current
expected-failures baseline (features the minimal demo doesn't implement) is
locked in [`conformance-baseline.yml`](./conformance-baseline.yml); any
unexpected failure in CI fails the build.

To run the suite against *your* server:

```bash
mcp-test conformance --url http://127.0.0.1:8765/mcp
# or for a stdio server through the bridge:
mcp-test conformance --command "python my_server.py"
```

Add `--offline` to skip the `npx` round-trip and run our local smoke
scenarios only.

---

## Use as a library

```python
from mcp_test import MCPTestClient

with MCPTestClient.from_command("python my_server.py") as client:
    tools = client.list_tools()
    print(tools.names())

    result = client.call_tool("echo", message="hello")
    print(result.text())
```

For HTTP / Streamable-HTTP:

```python
from mcp_test.http_client import HTTPMCPTestClient

with HTTPMCPTestClient.from_url("http://127.0.0.1:8765/mcp") as client:
    print(client.list_tools().names())
```

For FastMCP apps, skip the subprocess entirely:

```python
from fastmcp import FastMCP
from mcp_test.fastmcp import FastMCPHarness

app = FastMCP("my-server")

@app.tool()
def echo(msg: str) -> str: return msg

with FastMCPHarness(app) as client:
    assert client.call_tool("echo", msg="hi").text() == "hi"
```

---

## Run on every PR (GitHub Action)

Drop this into any repo:

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
      - uses: yagna-1/mcp-test@v0.3.0
        with:
          command: "python my_server.py"
          test-dir: "tests"
```

The action installs `pytest-mcp-plugin`, runs your suite against your MCP
server, and uploads a JUnit XML report. On failures, it also uploads any
wire-trace dumps from `mcp-traces/`.

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
| `mcp-test conformance --url "..."` | Run Anthropic's conformance suite via `npx` (or `--offline`) |
| `mcp-test bench -c "..."` | Run lightweight p50/p95/p99 regression probes |

All commands accept `--help` for full options.

---

## Fixtures

The pytest plugin auto-registers four fixtures:

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

`--mcp-timeout-method METHOD=SECONDS` may be passed multiple times. On CI,
failing tests automatically dump recent JSONL wire frames to `mcp-traces/`.

---

## Spec-version markers

Mark tests by required MCP spec version; the plugin auto-skips them against
older servers.

```python
import pytest

@pytest.mark.mcp_v3  # requires spec >= 2025-06-18
def test_uses_recent_feature(mcp_client):
    ...
```

Available markers: `mcp_v2` (≥ 2025-03-26), `mcp_v3` (≥ 2025-06-18),
`mcp_v4` (≥ 2025-11-25).

---

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

`pytest-mcp-plugin` runs your MCP server as a subprocess (stdio) or speaks
Streamable-HTTP to a running endpoint, all over JSON-RPC 2.0. A background
message pump handles response routing, notification dispatching, and
concurrent request support.

```
mcp_test/
  client.py              # stdio JSON-RPC client
  http_client.py         # Streamable-HTTP + legacy-SSE client
  plugin.py              # pytest plugin (fixtures, options, markers)
  cli.py                 # mcp-test CLI
  assertions.py          # assert_tool_*, assert_policy_*, assert_task_*
  schema_validator.py    # JSON Schema validation for tool inputs
  coverage.py            # tools/prompts/resources coverage tracker
  snapshot.py            # snapshot testing
  auth.py                # OAuth / PKCE / RFC 9728 helpers
  bench.py               # lightweight regression benchmark probes
  conformance.py         # bridge to @modelcontextprotocol/conformance
  compliance.py          # conformance score helpers
  fastmcp.py             # in-process FastMCP harness adapter
  otel.py                # optional OpenTelemetry tracing facade
  replay.py              # deterministic wire-trace replay
  pagination.py          # cursor pagination helpers
  test_packs.py          # batteries-included security test packs
  timeouts.py            # per-method timeout policy
  wire_trace.py          # JSONL wire trace recorder
  types.py               # ToolResult, ToolSchema, MCPError, ...
  _demo_server.py        # bundled stdio demo server
  _demo_server_http.py   # bundled FastMCP HTTP demo server
```

---

## Status

`pytest-mcp-plugin` is **beta**. The CLI surface, plugin API, and test-pack
class attributes are stable; minor internals (snapshot format, schema
validator details) may still change before 1.0.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for what's next and how we plan to complement
— not compete with — Anthropic's official conformance + inspector tools.

## Contributing

Bug reports, feature requests, and PRs welcome at
[github.com/yagna-1/mcp-test](https://github.com/yagna-1/mcp-test).

## License

MIT
