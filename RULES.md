# RULES.md - mcp-test

## Enforced rules (AstraGraph policy: mcp-test-default)

- Tests must assert both success and error paths.
- Restricted tools require paired allow/block policy assertions.
- MCP request/response schema validation is mandatory.
- Test evidence must be captured in machine-readable output.

## Human review required (PR, not direct commit)

- Any removal of policy-block assertions.
- Changes to core fixtures affecting MCP contract semantics.
- Broad skips/xfails applied to compliance suites.

## Auto-blocked (AstraGraph fail-closed)

- Test runs that omit required policy block checks.
- Contract suites with schema validation disabled.
- Fixtures that bypass restricted tool checks.
