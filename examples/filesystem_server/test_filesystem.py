
import os
import sys

import pytest
from mcp_test import make_client, assert_tool_ok, assert_tool_error, assert_tool_text_contains

SERVER = os.path.join(os.path.dirname(__file__), "server.py")
CMD = f"{sys.executable} {SERVER}"


@pytest.fixture
def client(tmp_path):
    with make_client(CMD, timeout=5.0, cwd=str(tmp_path), env={"DATA_DIR": str(tmp_path)}) as c:
        yield c, tmp_path


def test_list_tools(client):
    c, _ = client
    tools = c.list_tools()
    assert "list_files" in tools.names()
    assert "read_file" in tools.names()
    assert "write_file" in tools.names()


def test_write_and_read_file(client):
    c, tmp = client
    result = c.call_tool("write_file", path="hello.txt", content="Hello, World!")
    assert_tool_ok(result)

    result = c.call_tool("read_file", path="hello.txt")
    assert_tool_ok(result)
    assert_tool_text_contains(result, "Hello, World!")


def test_list_files(client):
    c, tmp = client
    (tmp / "file_a.txt").write_text("a")
    (tmp / "file_b.txt").write_text("b")

    result = c.call_tool("list_files", path=".")
    assert_tool_ok(result)
    assert_tool_text_contains(result, "file_a.txt")
    assert_tool_text_contains(result, "file_b.txt")


def test_read_nonexistent(client):
    c, _ = client
    result = c.call_tool("read_file", path="nonexistent.txt")
    assert_tool_error(result)
