# Changelog

All notable changes to `pytest-mcp-plugin` are documented here.

## [0.2.3] — 2026-05-05

### Fixed

- **Send `notifications/initialized` after the handshake** (MCP spec requires
  it; FastMCP-backed servers reject all subsequent requests with
  `-32602 Invalid request parameters` until they receive it). Caught while
  testing v0.2.2 against `excel-mcp-server`. Affects both stdio and HTTP
  clients.

## [0.2.2] — 2026-05-05

### Fixed

- **Compatibility with strict MCP servers** (e.g. FastMCP 1.10 stdio): the
  client no longer sends `params: {}` for parameterless JSON-RPC requests.
  FastMCP rejected those with `-32602 Invalid request parameters`, causing
  `tools/list` to return zero tools against real-world Python MCP servers.
  Empty params are now omitted from the wire payload, matching every other
  well-behaved MCP client. Affects both stdio and HTTP transports.
- **Wire trace accuracy**: `WireTrace.record("out", ...)` calls now run
  *after* a successful `write()`+`flush()` instead of before, so
  post-mortem traces never show phantom-sent messages when the server has
  closed the pipe.

### Added

- `mcp-test conformance --url ... [--offline] [--pytest-items]` subcommand
  that bridges to `npx @modelcontextprotocol/conformance`, parses results,
  and can re-emit each scenario as a real pytest test item. Bundled
  `--offline` mode runs `initialize`/`ping`/`tools/list` smoke checks
  through `HTTPMCPTestClient` for environments without `npx`.
- Per-method timeouts: `--mcp-timeout-method METHOD=SECONDS` (repeatable),
  `--mcp-smart-timeouts` flag, `[tool.mcp-test.timeouts]` table in
  `pyproject.toml`. `mcp_test.timeouts.SMART_TIMEOUT_DEFAULTS` is the
  single source of truth.
- Wire trace recorder: `--mcp-trace path.jsonl` (or `trace_path=` kwarg),
  optional `--mcp-live-stderr`. `MCPTimeoutError` now embeds the most
  recent frames inline. On CI failures, the plugin auto-dumps a
  per-test-id trace under `mcp-traces/`.
- `MCPTracer` (opt-in OpenTelemetry spans) — `pip install
  'pytest-mcp-plugin[otel]'`, then pass `otel=True` to `make_client()`.
- `FastMCPHarness` — in-process testing for FastMCP apps without spawning
  a subprocess. `pip install 'pytest-mcp-plugin[fastmcp]'`.
- `WireTraceReplay` — deterministic replay of recorded traces.
- `mcp-test bench --command ... --duration --concurrency` — p50/p95/p99
  per-method latencies, FD-leak detection, baseline comparison via
  `compare_to_baseline()`.
- Server-type test pack starters: `FilesystemServerTests`,
  `DatabaseServerTests`, `APIWrapperTests`, `ShellExecTests` in
  `mcp_test.test_packs`.
- `[hypothesis]` extra: `hypothesis_strategy_for_tool()` returns a
  Hypothesis strategy from a tool's input schema, for property-based
  contract tests.
- HTTP client: `Mcp-Method` and `Mcp-Name` request headers, automatic
  session termination on `close()`.

### Changed

- Consolidated three `pyproject.toml` readers in `runner.py` behind a
  single `_load_mcp_test_config()` helper that warns (instead of silently
  swallowing) on malformed TOML.
- Removed redundant `[tool.mcp-test.timeouts]` block from this repo's own
  `pyproject.toml`; the values were exact duplicates of
  `SMART_TIMEOUT_DEFAULTS`. Use `--smart-timeouts` to opt in.
- The pytest plugin's session-scoped client attribute is now
  `_pytest_mcp_plugin_client` (was `_mcp_client_instance`) so it never
  collides with other plugins on `pytest.Config`.

## [0.2.1] — 2026-05-05

### Added

- Per-method timeout overrides via pytest/CLI and `[tool.mcp-test.timeouts]`.
- JSONL wire tracing, recent-frame failure dumps in CI, and trace replay helpers.
- `mcp-test conformance`, compliance scoring, `mcp-test bench`, FastMCP harness,
  reusable test packs, optional OpenTelemetry facade, and Hypothesis schema strategies.

### Changed

- Lowered minimum Python from `>=3.11` to `>=3.10`. The codebase already had a
  `tomllib` → `tomli` fallback for 3.10 in `runner.py`; this release makes that
  fallback an explicit conditional dependency and unblocks adoption in projects
  that target 3.10 (e.g. `qdrant/mcp-server-qdrant`).
- Tightened Streamable HTTP session handling, resumability headers, DELETE
  termination, and draft request metadata headers.

## [0.2.0] — 2026-05-05

### Renamed

- **PyPI distribution renamed from `mcp-test` to `pytest-mcp-plugin`.** The `mcp-test`
  name on PyPI is held by Anthropic for their official MCP SDK
  ([modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)),
  and PyPI's name-similarity rules block close variants like `mcptest`.
  - The CLI binary is still `mcp-test` (and also available as `mcptest` and `pytest-mcp-plugin`).
  - The Python module is still `mcp_test`.
  - Old install command `pip install mcp-test` no longer installs this package.

### Added

- `mcp-test demo` — runs the bundled demo MCP server + a real pytest suite
  against it in 5 seconds, with zero setup.
- `mcp_test._demo_server` — a tiny zero-dependency stdio MCP server with
  `echo`, `add`, `uppercase`, and `fail` tools, used by the demo command and
  example workflow.
- Composite GitHub Action at `action.yml`. Drop into any repo:
  ```yaml
  - uses: yagna-1/mcp-test@v0.2.0
    with:
      command: "python my_server.py"
  ```
- `.github/workflows/example-action.yml` — dogfooded example users can copy.
- `tests/action_demo/` — smoke tests run by the example action workflow.

### Fixed

- `mcp-test` CLI was non-functional in `0.1.0` (empty `main()` body, undefined
  `CONFTEST` variable, malformed `EXAMPLE_TEST` string). All commands now work.
- `mcp-test init` now writes a valid `conftest.py`.

### Changed

- Project metadata: added `[project.urls]`, expanded classifiers (now lists
  Python 3.13), bumped maturity to "4 - Beta", populated authors/maintainers.
- Added `[tool.hatch.build.targets.{wheel,sdist}]` so builds are reproducible
  whether or not hatch's auto-detection picks the right package.

## [0.1.0] — 2026-03-06

- Initial release: `mcp-test` package, pytest plugin, stdio + HTTP/SSE clients,
  schema validator, snapshot testing, coverage, auth helpers.
