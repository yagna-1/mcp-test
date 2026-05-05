# Roadmap

> Where `pytest-mcp-plugin` is going, and how it complements (not competes with)
> Anthropic's official MCP tooling.

This document is intentionally honest about what's already built, what's
missing, what we *won't* build, and where we'd like to contribute upstream.

---

## TL;DR for maintainers / Anthropic

`pytest-mcp-plugin` is the **Python pytest-native execution layer** for testing
MCP servers. It is deliberately complementary to Anthropic's existing tools:

| Tool | Owner | Lane |
|---|---|---|
| [`@modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) | Anthropic | Spec conformance harness, TS/vitest, used by SDK maintainers |
| [`@modelcontextprotocol/inspector`](https://github.com/modelcontextprotocol/inspector) | Anthropic | Interactive React UI for human protocol debugging |
| [`pytest-mcp-plugin`](https://github.com/yagna-1/mcp-test) | community | pytest-native CI runner for individual MCP-server authors, esp. Python |

We want to be the tool a Python MCP-server author drops into their existing
`pytest` setup and CI, with zero new tooling, that *also* runs the upstream
Anthropic conformance suite when available. We are not building a competing
conformance suite, a competing inspector, or a competing certification program.

If parts of this are useful upstream — particularly a Python conformance
runner — we'd like to contribute them to `modelcontextprotocol/conformance`.

---

## What's already in v0.2.0

A snapshot of what shipped, since some downstream proposals duplicate it:

**Transports**
- stdio (subprocess) with 4-stage shutdown to avoid zombies
- HTTP and SSE (Streamable HTTP per [spec PR #206](https://github.com/modelcontextprotocol/specification/pull/206)) with reconnect + Last-Event-ID resumption

**Spec coverage** (versions `2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`)
- Tools, resources, prompts, tasks (sync + async)
- Sampling, elicitation, roots (mocked client capabilities)
- Cancellation (`notifications/cancelled`)
- Pagination (cursor)
- Tool annotations (`read_only_hint`, `destructive_hint`, etc.)
- Icons (spec 2025-11-25)
- Output schemas + structured content

**Auth**
- OAuth 2.1 PKCE (S256) helpers
- Protected Resource Metadata (PRM) and Authorization Server Metadata (ASM) validators
- Bearer token + `MCP-Protocol-Version` header construction
- M2M client_credentials helper

**Validation**
- Tool input-schema validator (basic JSON Schema correctness)
- Contract test generators (valid + invalid input cases for any tool)
- Coverage tracker (tools/prompts/resources/client-features) with Rich-rendered report
- Spec-version pytest markers (`mcp_v2`/`mcp_v3`/`mcp_v4`) auto-skipping older servers

**Test ergonomics**
- pytest plugin auto-loaded via `pytest11` entry point
- Fixtures: `mcp_client` (session), `mcp_client_fresh`, `sandboxed_client`, `snapshot`
- Snapshot testing with key-ignore + array-sort normalization
- Assertions: `assert_tool_ok`/`error`/`error_code`/`text_*`/`content_count`
- Task assertions: `assert_task_completes_within`/`cancelled`/`failed`
- Policy assertions: `assert_policy_allows`/`assert_policy_blocks` (AstraGraph integration)
- Mock client capabilities (`mock_sampling`, `mock_elicitation`, `with_roots`)

**Distribution**
- PyPI (`pip install pytest-mcp-plugin`)
- Composite GitHub Action (`uses: yagna-1/mcp-test@v0.2.0`)
- `mcp-test demo` — bundled in-process MCP server, 5 green tests in 0.14s, zero setup

---

## What's missing — the honest gap list

> **Implementation status as of v0.2.2.** Each item below is tagged in line:
> ✅ shipped, 🟡 partially shipped (works, but limited or undocumented), and
> ⏳ not yet started. The original rationale is preserved underneath because
> the design intent matters even when an item is already done — future
> maintainers (and Anthropic reviewers) need to understand *why*, not just
> *what*. Items still requiring external-repo work (e.g. FastMCP template PRs)
> stay open even when the in-repo adapter exists.

Each item is graded on **value** (1–5) and **effort** (S/M/L). Items the
community has asked for or that block adoption come first.

### P0 — Adoption blockers

#### 1. Bridge to `@modelcontextprotocol/conformance` *(value 5, effort M)* — 🟡 partial (in v0.2.2)

> Shipped: `mcp-test conformance --url ...` subcommand, JSON output parser
> covering `scenarios|tests|results|cases` shapes, `run_report_as_pytest()`
> re-emitter, and an `--offline` mode running `initialize`/`ping`/`tools/list`
> bundled smoke checks via `HTTPMCPTestClient` for environments without
> `npx`. **Not yet shipped:** assertion of the upstream JSON schema (we accept
> any shape that matches the heuristics), and a `SDK_INTEGRATION.md` upstream
> contribution — pending discussion on
> [conformance#258](https://github.com/modelcontextprotocol/conformance/issues/258).


Anthropic ships the canonical conformance suite as a TypeScript/vitest framework.
Python-first MCP authors today have no native way to execute it inside their
existing `pytest` flow.

**Plan**
- Add `mcp-test conformance` subcommand that:
  1. Detects whether `@modelcontextprotocol/conformance` is available (`npx`)
  2. Runs `npx @modelcontextprotocol/conformance server --url ... --json`
  3. Parses the structured output and re-emits each scenario as a pytest test item
- Surface conformance failures with the same UX as a normal pytest failure
- Optional offline mode that runs a vendored snapshot of the spec's positive/negative scenarios when `npx` is not available in CI

**Why this matters to Anthropic.** The conformance repo's `SDK_INTEGRATION.md`
explicitly lists baseline files for known failures — the workflow is currently
designed for SDK maintainers, not server authors. A pytest-native runner makes
the conformance suite usable for the long tail of Python MCP-server authors
(FastMCP, raw SDK, custom). We'd like to upstream this as a Python integration
guide alongside the existing TS-focused one.

#### 2. Streamable HTTP transport conformance audit *(value 5, effort S)* — 🟡 partial (in v0.2.2)

> Shipped: `Mcp-Method`/`Mcp-Name` request headers for richer server-side
> traces, automatic session termination on `close()`, `Last-Event-ID`
> re-attachment on retry. **Not yet shipped:** explicit DNS-rebinding test,
> `MCP-Protocol-Version` header round-trip test against a real Streamable
> HTTP server. The structural plumbing exists; the verification suite does
> not.


The spec replaced HTTP+SSE with Streamable HTTP in PR #206. We need to verify
our `http_client.py` matches the new transport precisely:

- Single endpoint, POST + optional GET upgrade to SSE
- `MCP-Protocol-Version` header negotiation
- `Mcp-Session-Id` lifecycle (create on init, present on subsequent requests, server-side termination via 404)
- DNS rebinding / Origin validation expectations
- Last-Event-ID resumption end-to-end (not just plumbing)

This is a fitness check, not new feature work. Current code mostly does this
but hasn't been compared line-by-line against the latest spec text.

#### 3. Per-operation timeouts *(value 4, effort S)* — ✅ shipped in v0.2.2

> `--mcp-timeout-method METHOD=SECONDS`, `--mcp-smart-timeouts`,
> `[tool.mcp-test.timeouts]` table, `mcp_test.timeouts.SMART_TIMEOUT_DEFAULTS`
> (the canonical map), and `TimeoutConfig.resolve()` plumbed through both
> stdio and HTTP clients. The CLI accepts the same flags via `mcp-test run`.


Today there's a single `--mcp-timeout` for all requests. Real MCP servers have
operations with very different latency profiles (e.g. `tools/list` is fast,
`tools/call` for an LLM-backed tool can be 30s). Add:

- Per-method timeout overrides via `--mcp-timeout-method`
- `[tool.mcp-test.timeouts]` table in `pyproject.toml`
- Smart defaults derived from method type (read-only → 5s, tool-call → 30s, sampling → 60s)

#### 4. Better failure diagnostics *(value 4, effort S)* — ✅ shipped in v0.2.2

> Wire-trace JSONL recorder (`--mcp-trace`), live-stream stderr
> (`--mcp-live-stderr`), automatic dump of recent frames to `mcp-traces/`
> on test failure under CI, and inline `recent` trace excerpts in
> `MCPTimeoutError` messages. Trace records are written *after* the wire
> write succeeds so post-mortem traces don't show phantom-sent messages.


When a test fails today, we surface stderr from the server, but not:
- The last few JSON-RPC frames either way
- Server stderr streamed live (we collect it on crash only)
- A wire-trace dump file on failure

Add `--mcp-trace path/to/file.jsonl` and emit it automatically on test failures
in CI. This is the single most-requested feature in similar pytest plugins.

### P1 — Differentiators

#### 5. FastMCP integration *(value 5, effort S)* — 🟡 in-process adapter shipped (in v0.2.2), upstream PRs ⏳

> Shipped: `from mcp_test import FastMCPHarness`, gated behind the
> `pytest-mcp-plugin[fastmcp]` extra, plus a smoke test that exercises a real
> in-process FastMCP app (`echo` round-trip). **Not yet:** PR upstream into
> FastMCP project templates / cookiecutter so new FastMCP servers ship a
> passing example test on day one. That's external-repo work.


[FastMCP](https://github.com/jlowin/fastmcp) is the dominant Python MCP-server
framework; most Python MCP servers in 2026 are built on it. Two concrete moves:

- Ship a `pytest_mcp.fastmcp` adapter so users with FastMCP servers can write
  `from mcp_test.fastmcp import FastMCPHarness; harness = FastMCPHarness(my_app)`
  and skip the subprocess entirely (in-process testing, 10–100× faster).
- PR upstream into FastMCP's cookiecutter / project templates so new FastMCP
  projects ship with `pytest-mcp-plugin` and a passing example test on day one.

#### 6. Server-type test packs *(value 4, effort M)* — 🟡 starter templates shipped (in v0.2.2)

Reusable parameterized test classes for common MCP server shapes:

- `FilesystemServerTests` — path traversal, symlink escape, read-only on read tools, sandbox bounds
- `DatabaseServerTests` — read-only tools never mutate, prepared-statement use, query injection
- `APIWrapperTests` — auth-required tools 401 without creds, rate-limit handling, retry idempotency
- `ShellExecTests` — command allowlist, argument escaping, non-zero exit handling

> Shipped: importable starter classes in `mcp_test.test_packs`, each with one
> reference assertion (e.g. `test_rejects_path_traversal`). They're
> deliberately minimal — designed for users to subclass and configure with
> their own `ToolInvocation`s. **Not yet shipped:** a matching minimal demo
> server per pack in `examples/` and the broader negative-test suites the
> design calls for. The templates exist as a public extension point; the
> *batteries* still need including.


#### 7. Performance probes *(value 3, effort M)* — ✅ shipped in v0.2.2

> `mcp-test bench --command ... --duration --concurrency` plus
> `compare_to_baseline()` against a previous-run JSON. Latencies are
> p50/p95/p99 per JSON-RPC method. FD-leak tracking is best-effort (Linux
> via `/proc/self/fd`, macOS via `/dev/fd`).


Not full load testing — that's a different product. But a `mcp-test bench`
mode that:

- Runs N concurrent clients for a fixed duration, records p50/p95/p99 latencies per method
- Detects FD/handle leaks across runs (compare `lsof` before/after)
- Compares to a baseline JSON file (`--baseline previous_run.json`) and fails CI on regression

The bar is "catch a regression," not "stress-test production." Three orders of
magnitude simpler than something like Locust.

#### 8. OpenTelemetry export *(value 3, effort S)* — ✅ shipped in v0.2.2

> Optional `[otel]` extra. Pass `otel=True` to `MCPTestClient` /
> `make_client()` and every JSON-RPC request becomes a span with
> `mcp.method`, `mcp.session_id`, `mcp.protocol_version` attributes. With
> OpenTelemetry uninstalled, the tracer degrades to a `nullcontext()` —
> zero overhead, never throws.


Optional `[otel]` extra. When enabled, every JSON-RPC request becomes a span
with `mcp.method`, `mcp.session_id`, `mcp.protocol_version` attributes. Ships
with a Jaeger-compatible local collector recipe in `docs/`. Useful both for
production-style diagnostics and as a debugging aid in tests.

### P2 — Worth doing eventually

#### 9. Wire-trace replay *(value 3, effort M)* — ✅ shipped in v0.2.2

> `mcp_test.WireTraceReplay` reads a JSONL trace and yields the next
> recorded response per method, deterministically. Useful for replacing the
> live server in client-side tests once a recording exists.


Record `--mcp-trace` from a real server run, replay it deterministically as a
fake server in tests. Useful for testing client-side code without needing the
live server every run.

#### 10. Compliance score *(value 2, effort S)* — ✅ shipped in v0.2.2

> `score_conformance(report)` and `ComplianceScore.badge_text()` produce a
> single human-readable line keyed off the conformance report's spec
> version. Suitable as a README badge once the spec-version negotiation
> matures upstream.


When the conformance bridge is in place, surface a single number per spec
version: "passing 412 / 437 conformance scenarios for 2025-06-18 (94.3%)."
Useful for README badges and CI dashboards. Lower priority than just *running*
the conformance suite well.

#### 11. Plain-Python contract tests *(value 2, effort S)*

Generalize the existing `generate_valid_inputs` / `generate_invalid_inputs_*`
into a property-based testing flow. Hypothesis integration if `hypothesis` is
installed.

---

## What we explicitly won't build

Listing this so the scope is unambiguous and so we don't drift into Anthropic's
lane.

| Won't build | Why |
|---|---|
| **A competing conformance suite** | Anthropic owns this; we run theirs |
| **A competing inspector / interactive UI** | `@modelcontextprotocol/inspector` is excellent and the right shape for human debugging |
| **A "MCP certified" program / badge / registry** | Certification authority is reasonably Anthropic's call. We can surface conformance pass/fail in CI, but the badge is theirs to mint |
| **WebSocket transport** | Not a spec transport. TS SDK removed WebSocketClientTransport in March 2026 ([PR #1783](https://github.com/modelcontextprotocol/typescript-sdk/pull/1783)). [SEP-1288](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1288) is still draft. Building it now would actively encourage non-conformant deployments |
| **Per-server quirk middleware** | Quirks should be filed as bugs against the server, not papered over by a test framework. We'll surface known deviations in failure output, not normalize them |
| **AI-based vulnerability review** | [`bryankthompson/inspector-assessment`](https://github.com/bryankthompson/inspector-assessment) was archived after concluding LLM review outperformed automated behavioral tests for MCP-specific vulnerabilities. Where the gain is, the gain is. We focus on deterministic spec/contract/perf testing |
| **A general-purpose pytest replacement** | We're a plugin, not a framework |

---

## Stateless-protocol awareness

The MCP project's [transport future post](https://blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/)
signals movement toward a stateless protocol with explicit session handling at
the data-model layer rather than the transport layer. Concretely:

- Per-request capability info instead of an `initialize` handshake
- Sessions become an application concept, not a transport one

We will avoid building anything that hard-codes the current
`initialize → session-id → subsequent requests` shape into our public API.
Specifically: the `MCPTestClient` constructor will not start treating
`session_id` as a stable identifier in v0.x; users who want it can read
`client.session_id` but should not depend on its persistence.

---

## How we'd like to work with Anthropic

In rough order of cost:

1. **Acknowledgement.** Listing `pytest-mcp-plugin` as a community option in
   the official conformance repo's "see also" or "ecosystem" section, when we
   ship the conformance bridge in §1 above. We are not asking for endorsement
   — just discoverability for Python users.

2. **Issue triage.** When we find genuine spec ambiguity by running tests
   against multiple servers, we will file issues against
   `modelcontextprotocol/specification` with reproductions, not paper over in
   our code.

3. **Upstream contribution.** Submit a `PYTHON_INTEGRATION.md` companion to
   the existing TS-focused `SDK_INTEGRATION.md` in the conformance repo, plus
   a Python runner that wraps the canonical scenarios.

4. **Schema sync.** If/when `modelcontextprotocol/specification` ships
   machine-readable JSON Schemas for Tool / Resource / Prompt definitions, we
   adopt them as the source of truth in `schema_validator.py` rather than our
   handwritten checks.

The test-everywhere problem is too big for any single team. We want to make
the Python slice of it work, and to feed the work back upstream.

---

## Versioning + stability

- `0.x` releases may break public Python API across minor versions; CLI
  invocations are stable.
- `1.0` will lock the public Python API once `mcp-test conformance` is in and
  the spec is comfortably stateless-aware.
- Releases follow tag-driven publishing on PyPI; the GitHub Action is pinned
  by tag (`@v0.2.0`).

---

## Contributing

Issues and PRs welcome at
[github.com/yagna-1/mcp-test](https://github.com/yagna-1/mcp-test). The fastest
path to a merged PR is one of the P0 items above. The code is small enough
(~5k lines, MIT) to read in an afternoon.

If you maintain an MCP server and want it added to the example matrix in
`examples/` (with a passing test pack from §6 above), open an issue with the
server's stdio command — we'll add it.
