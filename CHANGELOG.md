# Changelog

All notable changes to `pytest-mcp-plugin` are documented here.

## [0.2.1] — 2026-05-05

### Changed

- Lowered minimum Python from `>=3.11` to `>=3.10`. The codebase already had a
  `tomllib` → `tomli` fallback for 3.10 in `runner.py`; this release makes that
  fallback an explicit conditional dependency and unblocks adoption in projects
  that target 3.10 (e.g. `qdrant/mcp-server-qdrant`).

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
