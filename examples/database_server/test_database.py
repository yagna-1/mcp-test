"""End-to-end tests for the read-only SQLite demo server.

The first block exercises the documented surface; the second opts into the
``DatabaseServerTests`` test pack from ``mcp_test.test_packs`` so we get
regression coverage for read-only-ness and SQL-injection neutralisation
for free.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from mcp_test import (
    make_client,
    assert_tool_ok,
    assert_tool_error,
    assert_tool_text_contains,
)
from mcp_test.test_packs import DatabaseServerTests, ToolInvocation


SERVER = os.path.join(os.path.dirname(__file__), "server.py")
CMD = f"{sys.executable} {SERVER}"


@pytest.fixture
def client():
    with make_client(CMD, timeout=5.0) as c:
        yield c


# ─── Documented-surface smoke tests ──────────────────────────────────────


def test_list_tables(client):
    result = client.call_tool("list_tables")
    assert_tool_ok(result)
    tables = json.loads(result.text())
    assert "users" in tables
    assert "products" in tables


def test_query_users(client):
    result = client.call_tool("query", table="users")
    assert_tool_ok(result)
    users = json.loads(result.text())
    assert len(users) >= 2
    assert any(u["name"] == "Alice" for u in users)


def test_query_with_filter(client):
    result = client.call_tool(
        "query", table="users", filter_field="name", filter_value="Alice",
    )
    assert_tool_ok(result)
    users = json.loads(result.text())
    assert len(users) == 1
    assert users[0]["name"] == "Alice"


def test_query_invalid_table_is_rejected(client):
    """Invalid identifiers (with quotes / spaces / SQL fragments) are rejected up front."""
    for table in ("nonexistent", "users; DROP TABLE users", "users--"):
        result = client.call_tool("query", table=table)
        assert_tool_error(result), f"server accepted invalid table {table!r}"


def test_row_count(client):
    result = client.call_tool("row_count", table="users")
    assert_tool_ok(result)
    assert int(result.text()) == 2


# ─── Reference: opt into the bundled DatabaseServerTests pack ────────────


class TestDatabasePack(DatabaseServerTests):
    """Run the bundled database test pack against this demo server."""

    mutation_probe = ToolInvocation("row_count", {"table": "users"})

    read_only_tools = (
        ToolInvocation("query", {"table": "users"}),
        ToolInvocation("query", {"table": "products"}),
        ToolInvocation("list_tables", {}),
    )

    injection_tool = ToolInvocation("query", {"table": "users"})
    injection_arg = "filter_value"

    @pytest.fixture
    def mcp_client(self, client):
        return client
