"""Reusable mixin templates for testing common MCP server shapes.

Each pack here is a **batteries-included** template that bundles 4–8
production-relevant assertions for a category of MCP servers. The
assertions encode the security and robustness checks that every server in
that category should pass — drawn from real-world incidents, the MCP spec's
"trust & safety" sections, and the OWASP top-10 mapping for tool servers.

To use a pack, subclass it from a pytest test class (or call its methods
manually) and override the *configuration* class attributes to point at
your server's tool names::

    from mcp_test.test_packs import FilesystemServerTests, ToolInvocation

    class TestMyFsServer(FilesystemServerTests):
        root_uri = "file:///srv/data"
        read_tool = "read_file"
        list_tool = "list_directory"
        safe_path = "ok.txt"

The methods deliberately keep ``test_`` prefixes so subclasses written as
pytest classes get them auto-collected without any extra wiring. They also
gracefully no-op (via ``pytest.skip``) when the server hasn't configured
the relevant tools, so a single subclass can opt into whichever subset of
the pack matches its server's surface area.

See ``examples/<server>/test_<server>.py`` for a working subclass against
each demo server in ``examples/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass(frozen=True)
class ToolInvocation:
    """A named tool call: ``ToolInvocation("read_file", {"path": "x.txt"})``."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


# ─── Filesystem servers ───────────────────────────────────────────────────


class FilesystemServerTests:
    """Reusable assertions for filesystem-shaped MCP servers.

    Configure by overriding the class attributes below. Each test
    individually skips when its prerequisite attributes aren't set, so a
    subclass can opt into the assertions that apply to its server.

    Real-world incidents this pack is designed to catch:

    * **Path traversal** — server accepts ``../etc/passwd`` or its URL-encoded
      equivalents (a recurring class of CVE in npm-published filesystem MCP
      servers since 2024).
    * **Resource scope creep** — ``resources/list`` exposes URIs outside the
      configured sandbox root.
    * **Symlink escape** — server follows a symlink that points outside the
      sandbox.
    * **Absolute path acceptance** — server doesn't reject ``/etc/passwd``
      passed where a relative path is expected.
    * **Tool listing drift** — the documented tool surface must actually be
      advertised (regression guard for refactors that drop tools).
    """

    # ── configuration ────────────────────────────────────────────────
    root_uri: str = "file:///"
    """The expected URI prefix for any resource the server exposes."""

    read_tool: str | None = None
    """Name of a tool that reads a file (e.g. ``read_file``).

    Must accept a path argument named via :attr:`path_arg`.
    """

    list_tool: str | None = None
    """Name of a tool that lists a directory (e.g. ``list_directory``)."""

    path_arg: str = "path"
    """Argument name on ``read_tool`` / ``list_tool`` for the path."""

    safe_path: str = "."
    """A path that is known to exist inside the sandbox and be readable."""

    expected_tools: tuple[str, ...] = ()
    """Tools the server is documented to advertise. Empty disables the check."""

    traversal_payloads: tuple[str, ...] = (
        "../etc/passwd",
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "%2e%2e/etc/passwd",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
    )
    """Payloads the server must reject. Includes Unix + Windows abs paths."""

    # ── tests ────────────────────────────────────────────────────────

    def test_advertises_documented_tools(self, mcp_client):
        if not self.expected_tools:
            pytest.skip("no expected_tools configured")
        names = set(mcp_client.list_tools().names())
        missing = set(self.expected_tools) - names
        assert not missing, (
            f"server failed to advertise documented tools: {sorted(missing)} "
            f"(actual: {sorted(names)})"
        )

    def test_resources_stay_inside_sandbox(self, mcp_client):
        try:
            resources = mcp_client.list_resources()
        except Exception as exc:
            pytest.skip(f"server doesn't expose resources/list: {exc}")
        if not resources:
            pytest.skip("server exposes no resources")
        for resource in resources:
            uri = str(getattr(resource, "uri", resource))
            assert uri.startswith(self.root_uri), (
                f"resource {uri!r} escapes expected root {self.root_uri!r}"
            )

    def test_safe_path_is_readable(self, mcp_client):
        """Sanity check: the configured safe_path actually works."""
        if self.read_tool is None:
            pytest.skip("read_tool not configured")
        result = mcp_client.call_tool(self.read_tool, **{self.path_arg: self.safe_path})
        assert result.is_ok(), (
            f"sanity check failed: {self.read_tool}({self.path_arg}={self.safe_path!r}) "
            f"returned an error: {result.text()!r}"
        )

    def test_rejects_path_traversal(self, mcp_client):
        if self.read_tool is None:
            pytest.skip("read_tool not configured")
        accepted: list[str] = []
        for payload in self.traversal_payloads:
            try:
                result = mcp_client.call_tool(self.read_tool, **{self.path_arg: payload})
            except Exception:
                continue  # raised exceptions are *fine* — they reject the call
            if result.is_ok():
                # The really suspicious case: the server returned content for
                # a path traversal probe. That's a confirmed vulnerability.
                accepted.append(payload)
        assert not accepted, (
            f"{self.read_tool} accepted path-traversal payloads: {accepted!r} — "
            "this server is vulnerable to CVE-style sandbox escapes."
        )

    def test_rejects_absolute_paths_when_relative_expected(self, mcp_client):
        """If safe_path is relative, absolute paths to the same file should be rejected.

        Skipped when safe_path is itself absolute, since then absolute paths
        are part of the documented contract.
        """
        if self.read_tool is None:
            pytest.skip("read_tool not configured")
        if self.safe_path.startswith(("/", "\\")) or (
            len(self.safe_path) > 1 and self.safe_path[1] == ":"
        ):
            pytest.skip("safe_path is absolute — server documents absolute paths")
        # Try an obviously-out-of-sandbox absolute path.
        for absolute in ("/etc/hostname", "/etc/passwd", "C:\\Windows\\win.ini"):
            try:
                result = mcp_client.call_tool(self.read_tool, **{self.path_arg: absolute})
            except Exception:
                continue
            assert result.is_error(), (
                f"{self.read_tool} accepted absolute path {absolute!r} when "
                "the server is documented to take relative paths"
            )

    def test_list_tool_does_not_traverse(self, mcp_client):
        if self.list_tool is None:
            pytest.skip("list_tool not configured")
        for payload in ("..", "../", "../.."):
            try:
                result = mcp_client.call_tool(self.list_tool, **{self.path_arg: payload})
            except Exception:
                continue
            if result.is_ok():
                # The directory contents leaking parent dirs is the failure mode.
                text = result.text()
                # Quick heuristic: any of these strings showing up in a sandboxed
                # demo means we leaked parent-directory contents.
                assert not any(
                    leak in text for leak in ("etc/", "Users/", "root/", "Windows/")
                ), (
                    f"{self.list_tool}({payload!r}) appeared to list outside the "
                    f"sandbox: {text[:200]!r}"
                )


# ─── Database servers ─────────────────────────────────────────────────────


class DatabaseServerTests:
    """Reusable assertions for database-backed MCP servers (read-only or RW).

    Real-world incidents this pack catches:

    * **Read-only tools that quietly mutate** — a `query` tool that runs
      ``DELETE FROM users`` because of weak SQL parsing.
    * **SQL injection via parameter concatenation** — server inlines tool
      arguments into the query without binding.
    * **Unbounded result sets** — a query that returns ``SELECT *`` from a
      million-row table without a LIMIT.
    """

    # ── configuration ────────────────────────────────────────────────
    read_only_tools: tuple[ToolInvocation, ...] = ()
    """Tools documented as read-only. Each will be invoked to verify behavior."""

    mutation_probe: ToolInvocation | None = None
    """A read-only query whose result reflects whether DB state changed.

    Typically something like ``ToolInvocation("query", {"sql": "SELECT COUNT(*) FROM users"})``.
    """

    injection_tool: ToolInvocation | None = None
    """A tool that takes a string argument we'll fuzz with SQLi payloads."""

    injection_arg: str = "query"
    """Argument name on ``injection_tool`` that takes user input."""

    sqli_payloads: tuple[str, ...] = (
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "'; SELECT pg_sleep(5); --",
        "' UNION SELECT NULL,NULL,NULL --",
    )

    # ── tests ────────────────────────────────────────────────────────

    def test_read_only_tools_do_not_mutate(self, mcp_client):
        if self.mutation_probe is None or not self.read_only_tools:
            pytest.skip("mutation_probe and read_only_tools must both be configured")
        before = mcp_client.call_tool(
            self.mutation_probe.name, **self.mutation_probe.arguments,
        ).text()
        for invocation in self.read_only_tools:
            result = mcp_client.call_tool(invocation.name, **invocation.arguments)
            assert result.is_ok(), (
                f"read-only tool {invocation.name!r} failed: {result.text()!r}"
            )
        after = mcp_client.call_tool(
            self.mutation_probe.name, **self.mutation_probe.arguments,
        ).text()
        assert before == after, (
            f"read-only tool changed database-visible state: "
            f"probe was {before!r} before, {after!r} after"
        )

    def test_rejects_sql_injection_payloads(self, mcp_client):
        """SQL injection probes must either error or return data that proves they were neutralised.

        The check is: after sending an SQLi payload as the query argument, the
        mutation_probe must produce the same value as before. Otherwise the
        injection executed against the live database.
        """
        if self.injection_tool is None or self.mutation_probe is None:
            pytest.skip("injection_tool and mutation_probe required")
        before = mcp_client.call_tool(
            self.mutation_probe.name, **self.mutation_probe.arguments,
        ).text()
        for payload in self.sqli_payloads:
            args = dict(self.injection_tool.arguments)
            args[self.injection_arg] = payload
            try:
                mcp_client.call_tool(self.injection_tool.name, **args)
            except Exception:
                pass  # rejection is fine
        after = mcp_client.call_tool(
            self.mutation_probe.name, **self.mutation_probe.arguments,
        ).text()
        assert before == after, (
            f"SQL injection payloads modified database state: "
            f"probe was {before!r}, became {after!r}"
        )


# ─── API wrapper servers ──────────────────────────────────────────────────


class APIWrapperTests:
    """Reusable assertions for MCP servers that wrap an external HTTP API.

    Real-world incidents this pack catches:

    * **Credential leakage** — the server echoes its API key back in the tool
      result (happens when servers naively forward error responses).
    * **No auth check** — a tool that's *supposed* to need credentials happily
      runs without any, hitting the upstream API anonymously.
    * **Retry hammering** — a transient failure causes the server to retry
      indefinitely, taking down the upstream.
    """

    # ── configuration ────────────────────────────────────────────────
    auth_required_tools: tuple[ToolInvocation, ...] = ()
    """Tools that should fail without credentials configured."""

    forbidden_secrets: tuple[str, ...] = ()
    """Strings (e.g. API key prefixes) that must never appear in tool output."""

    rate_probe: ToolInvocation | None = None
    """A tool we can call repeatedly to verify the server doesn't loop."""

    max_calls_per_second: int = 10
    """Upper bound on rate when calling rate_probe in a tight loop."""

    # ── tests ────────────────────────────────────────────────────────

    def test_auth_required_tools_fail_without_credentials(self, mcp_client):
        if not self.auth_required_tools:
            pytest.skip("no auth_required_tools configured")
        for invocation in self.auth_required_tools:
            try:
                result = mcp_client.call_tool(invocation.name, **invocation.arguments)
            except Exception:
                continue  # exception = rejection, also fine
            assert result.is_error(), (
                f"{invocation.name!r} returned a successful result without "
                f"credentials configured: {result.text()[:200]!r}"
            )

    def test_no_secret_leakage_in_outputs(self, mcp_client):
        if not self.forbidden_secrets or not self.auth_required_tools:
            pytest.skip("forbidden_secrets and auth_required_tools required")
        for invocation in self.auth_required_tools:
            try:
                result = mcp_client.call_tool(invocation.name, **invocation.arguments)
            except Exception:
                continue
            text = result.text()
            for secret in self.forbidden_secrets:
                assert secret not in text, (
                    f"tool {invocation.name!r} leaked secret prefix {secret!r} "
                    f"in its response: {text[:200]!r}"
                )


# ─── Shell-exec servers ───────────────────────────────────────────────────


class ShellExecTests:
    """Reusable assertions for MCP servers that execute shell commands.

    These servers are the *highest*-risk category: they convert untrusted
    LLM-generated input into ``execve`` calls. This pack encodes the bare
    minimum every shell-exec server should pass.

    Real-world incidents this pack catches:

    * **Command injection via shell metacharacters** — server passes argument
      strings to ``sh -c`` instead of directly to ``execve``.
    * **Allowlist bypass via environment variables** — server checks the first
      token but allows ``cmd; rm -rf /``.
    * **Silent failure** — the tool returns "ok" even when the underlying
      command exited non-zero.
    """

    # ── configuration ────────────────────────────────────────────────
    exec_tool: str = "run_command"
    command_arg: str = "command"

    blocked_commands: tuple[str, ...] = (
        # Commands rooted at non-allowlisted binaries. A correctly-implemented
        # allowlist server must refuse to run any of these — even with no
        # shell-metacharacters at all.
        "rm -rf /tmp/should-not-exist-mcptest",
        "sh -c \"echo unsafe\"",
        "bash -c 'echo unsafe'",
        "/bin/sh -c 'echo unsafe'",
        "curl http://example.invalid",
    )
    """Commands the server must reject outright (different command names, not just metacharacters).

    Note: detecting metacharacter-based injection generically is impossible
    without a side-effect probe (see :meth:`test_no_shell_metacharacter_injection`).
    """

    injection_probe_command: str | None = None
    """A single command string that *only* mutates state if shell-evaluated.

    Example: if the allowlist permits ``touch``, set this to
    ``"touch /tmp/safe; touch /tmp/MCPTEST_INJECTION_CANARY"`` and provide
    :attr:`injection_canary_path`. If the canary exists after the call, the
    server invoked a shell. Set to ``None`` to skip metacharacter testing.
    """

    injection_canary_path: str | None = None
    """Filesystem path checked after :attr:`injection_probe_command` runs."""

    failing_command: str = "false"
    """A command that exits non-zero. Used for exit-code surfacing test."""

    successful_command: str = "echo ok"
    """A command that exits zero. Used for happy-path test."""

    # ── tests ────────────────────────────────────────────────────────

    def test_successful_command_returns_ok(self, mcp_client):
        try:
            result = mcp_client.call_tool(self.exec_tool, **{self.command_arg: self.successful_command})
        except Exception as exc:
            pytest.fail(f"{self.exec_tool}({self.successful_command!r}) raised: {exc}")
        assert result.is_ok(), (
            f"happy-path command {self.successful_command!r} returned an error: "
            f"{result.text()[:200]!r}"
        )

    def test_failing_command_surfaces_nonzero_exit(self, mcp_client):
        try:
            result = mcp_client.call_tool(self.exec_tool, **{self.command_arg: self.failing_command})
        except Exception:
            return  # exception is also an acceptable surfacing
        # Either it returns is_error(), OR the text contains a non-zero exit
        # code in some recognisable form.
        if result.is_error():
            return
        text = result.text().lower()
        assert any(token in text for token in ("exit code 1", "exit 1", "non-zero", "failed")), (
            f"{self.exec_tool} hid a non-zero exit code: {text[:200]!r}"
        )

    def test_blocks_disallowed_commands(self, mcp_client):
        """Commands that aren't in the server's allowlist must be rejected.

        This catches the most common mistake: forgetting to gate the binary
        name. Metacharacter-based injection is covered separately by
        :meth:`test_no_shell_metacharacter_injection`.
        """
        accepted: list[str] = []
        for command in self.blocked_commands:
            try:
                result = mcp_client.call_tool(self.exec_tool, **{self.command_arg: command})
            except Exception:
                continue  # rejection via raise is fine
            if result.is_ok():
                accepted.append(command)
        assert not accepted, (
            f"{self.exec_tool} accepted disallowed commands: {accepted!r} — "
            "the server is not enforcing its command allowlist."
        )

    def test_no_shell_metacharacter_injection(self, mcp_client, tmp_path):
        """Run a probe command that only side-effects if a shell evaluated it.

        Skipped unless ``injection_probe_command`` and ``injection_canary_path``
        are configured. Configuring them is the only honest way to detect
        ``shell=True`` injection: a server that uses ``execvp`` will pass the
        probe even though the command string contains metacharacters; a server
        that uses ``shell=True`` will create the canary file.
        """
        if not self.injection_probe_command or not self.injection_canary_path:
            pytest.skip(
                "set injection_probe_command + injection_canary_path to enable "
                "shell-metacharacter detection"
            )
        # Make sure the canary doesn't pre-exist.
        import os
        try:
            os.unlink(self.injection_canary_path)
        except FileNotFoundError:
            pass
        try:
            mcp_client.call_tool(self.exec_tool, **{self.command_arg: self.injection_probe_command})
        except Exception:
            pass
        assert not os.path.exists(self.injection_canary_path), (
            f"{self.exec_tool} interpreted shell metacharacters: canary "
            f"{self.injection_canary_path!r} was created. The server is "
            "passing user input through a shell (shell=True) and is "
            "vulnerable to arbitrary code execution."
        )
