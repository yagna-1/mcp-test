"""Reusable mixin templates for testing common MCP server shapes.

These are **starting templates**, not finished tests — subclass and override
class attributes (or methods) to point at your server's tool names and
arguments. They live as plain classes (not pytest classes with ``test_*``
prefixes auto-collected) so importing this module doesn't accidentally
register tests in the consumer's suite::

    class MyFsTests(FilesystemServerTests):
        root_uri = "file:///srv/data"
        read_tool = ToolInvocation("read_file", {"path": "ok.txt"})

    def test_my_filesystem_server(mcp_client):
        MyFsTests().test_rejects_path_traversal(mcp_client)

The methods deliberately keep ``test_`` prefixes so subclasses written as
pytest classes get them auto-collected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolInvocation:
    name: str
    arguments: dict[str, Any]


class FilesystemServerTests:
    """Reusable assertions for filesystem-shaped MCP servers."""

    root_uri: str = "file:///"
    read_tool: ToolInvocation | None = None
    traversal_payloads: tuple[str, ...] = ("../secret.txt", "..%2Fsecret.txt")

    def test_rejects_path_traversal(self, mcp_client):
        if self.read_tool is None:
            return
        for payload in self.traversal_payloads:
            args = dict(self.read_tool.arguments)
            args[next(iter(args))] = payload
            result = mcp_client.call_tool(self.read_tool.name, **args)
            assert result.is_error(), f"{self.read_tool.name} accepted traversal payload {payload!r}"

    def test_resources_stay_inside_sandbox(self, mcp_client):
        for resource in mcp_client.list_resources():
            assert str(resource.uri).startswith(self.root_uri), (
                f"Resource {resource.uri!r} escaped expected root {self.root_uri!r}"
            )


class DatabaseServerTests:
    """Reusable assertions for database-backed MCP servers."""

    read_only_tools: tuple[ToolInvocation, ...] = ()
    mutation_probe: ToolInvocation | None = None

    def test_read_only_tools_do_not_mutate(self, mcp_client):
        if self.mutation_probe is None:
            return
        before = mcp_client.call_tool(self.mutation_probe.name, **self.mutation_probe.arguments).text()
        for invocation in self.read_only_tools:
            result = mcp_client.call_tool(invocation.name, **invocation.arguments)
            assert result.is_ok(), f"{invocation.name} failed before mutation check"
        after = mcp_client.call_tool(self.mutation_probe.name, **self.mutation_probe.arguments).text()
        assert before == after, "Read-only tool changed database-visible state"


class APIWrapperTests:
    """Reusable assertions for API wrapper MCP servers."""

    auth_required_tools: tuple[ToolInvocation, ...] = ()

    def test_auth_required_tools_fail_without_credentials(self, mcp_client):
        for invocation in self.auth_required_tools:
            result = mcp_client.call_tool(invocation.name, **invocation.arguments)
            assert result.is_error(), f"{invocation.name} succeeded without credentials"


class ShellExecTests:
    """Reusable assertions for shell-exec MCP servers."""

    exec_tool: str = "run_command"
    blocked_commands: tuple[str, ...] = ("sh -c 'echo unsafe'", "rm -rf /")

    def test_blocks_disallowed_commands(self, mcp_client):
        for command in self.blocked_commands:
            result = mcp_client.call_tool(self.exec_tool, command=command)
            assert result.is_error(), f"{self.exec_tool} accepted disallowed command {command!r}"
