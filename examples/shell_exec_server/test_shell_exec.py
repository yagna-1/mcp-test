"""End-to-end tests for the allowlist-based shell-exec demo server.

Verifies the documented surface and opts into the bundled
``ShellExecTests`` pack to gain command-injection coverage automatically.
"""

from __future__ import annotations

import os
import sys

import pytest
from mcp_test import make_client, assert_tool_ok, assert_tool_error
from mcp_test.test_packs import ShellExecTests


SERVER = os.path.join(os.path.dirname(__file__), "server.py")
CMD = f"{sys.executable} {SERVER}"


@pytest.fixture
def client():
    with make_client(CMD, timeout=5.0) as c:
        yield c


# ─── Documented-surface tests ────────────────────────────────────────────


def test_list_allowed(client):
    result = client.call_tool("list_allowed")
    assert_tool_ok(result)
    assert "echo" in result.text()


def test_echo_runs(client):
    result = client.call_tool("run_command", command="echo hello-world")
    assert_tool_ok(result)
    assert "hello-world" in result.text()


def test_disallowed_command_rejected(client):
    result = client.call_tool("run_command", command="cat /etc/passwd")
    assert_tool_error(result)
    assert "not allowed" in result.text()


# ─── Reference: opt into the bundled ShellExecTests pack ─────────────────


CANARY_PATH = "/tmp/mcptest-shell-injection-canary"


class TestShellExecPack(ShellExecTests):
    """Run the bundled shell-exec security pack against this demo server."""

    exec_tool = "run_command"
    command_arg = "command"
    successful_command = "echo ok"
    failing_command = "false"

    # The probe: 'echo' is allowed; if the server uses shell=True the
    # `;touch ...` segment will run and create the canary file. With
    # execvp() (correct), the entire string is just arguments to echo.
    injection_probe_command = f"echo ok; touch {CANARY_PATH}"
    injection_canary_path = CANARY_PATH

    @pytest.fixture
    def mcp_client(self, client):
        return client
