
import json
import os
import sys

import pytest
from mcp_test import make_client, assert_tool_ok, assert_tool_error, assert_tool_text_contains

SERVER = os.path.join(os.path.dirname(__file__), "server.py")
CMD = f"{sys.executable} {SERVER}"


@pytest.fixture
def client():
    with make_client(CMD, timeout=5.0) as c:
        yield c


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
    result = client.call_tool("query", table="users", filter_field="name", filter_value="Alice")
    assert_tool_ok(result)
    users = json.loads(result.text())
    assert len(users) == 1
    assert users[0]["name"] == "Alice"


def test_query_nonexistent_table(client):
    result = client.call_tool("query", table="nonexistent")
    assert_tool_error(result)
    assert_tool_text_contains(result, "Table not found")


def test_insert_record(client):
    result = client.call_tool(
        "insert",
        table="users",
        record={"id": 3, "name": "Charlie", "email": "charlie@example.com"},
    )
    assert_tool_ok(result)
    assert_tool_text_contains(result, "Inserted")


def test_schema_validation(client):
    tools = client.list_tools()
    query = tools.find("query")
    assert query is not None
    assert "table" in query.required
