"""End-to-end tests for the API-wrapper demo server.

Two clients are spun up: one with no credentials (the "unauthenticated"
client used by the security pack) and one with a fake API key (used to
verify the happy path). The split lets us test exactly what the
``APIWrapperTests`` pack is designed to catch — credential leakage and
silent anonymous calls.
"""

from __future__ import annotations

import os
import sys

import pytest
from mcp_test import make_client, assert_tool_ok, assert_tool_error
from mcp_test.test_packs import APIWrapperTests, ToolInvocation


SERVER = os.path.join(os.path.dirname(__file__), "server.py")
CMD = f"{sys.executable} {SERVER}"
SECRET_KEY = "sk-very-secret-do-not-leak-12345"


@pytest.fixture
def unauthenticated_client():
    """Server with NO API_KEY set — auth-required tools should fail."""
    with make_client(CMD, timeout=5.0, env={"PATH": os.environ.get("PATH", "")}) as c:
        yield c


@pytest.fixture
def authenticated_client():
    """Server with a fake API key — happy path."""
    env = {"PATH": os.environ.get("PATH", ""), "API_KEY": SECRET_KEY}
    with make_client(CMD, timeout=5.0, env=env) as c:
        yield c


# ─── Documented-surface tests ────────────────────────────────────────────


def test_ping_works_without_credentials(unauthenticated_client):
    result = unauthenticated_client.call_tool("ping")
    assert_tool_ok(result)
    assert "pong" in result.text()


def test_authenticated_call_succeeds(authenticated_client):
    result = authenticated_client.call_tool("get_current_weather", city="london")
    assert_tool_ok(result)
    assert "London" in result.text()


def test_unauthenticated_call_fails_explicitly(unauthenticated_client):
    result = unauthenticated_client.call_tool("get_current_weather", city="london")
    assert_tool_error(result)


# ─── Reference: opt into the bundled APIWrapperTests pack ────────────────


class TestApiWrapperPack(APIWrapperTests):
    """Run the bundled API-wrapper pack against the unauthenticated server."""

    auth_required_tools = (
        ToolInvocation("get_current_weather", {"city": "london"}),
    )
    forbidden_secrets = (SECRET_KEY, SECRET_KEY[:8])

    @pytest.fixture
    def mcp_client(self, unauthenticated_client):
        return unauthenticated_client


class TestApiWrapperLeakWithKey(APIWrapperTests):
    """Run the leak-detection check while creds ARE configured.

    The server must still not echo its key back even when it has one — that's
    the more dangerous failure mode (server has a key and leaks it on error).
    """

    auth_required_tools = (
        ToolInvocation("get_current_weather", {"city": "london"}),
        ToolInvocation("get_current_weather", {"city": "atlantis"}),  # error path
    )
    forbidden_secrets = (SECRET_KEY, SECRET_KEY[:8])

    @pytest.fixture
    def mcp_client(self, authenticated_client):
        return authenticated_client

    def test_auth_required_tools_fail_without_credentials(self, mcp_client):
        pytest.skip("creds are intentionally configured for this class")
