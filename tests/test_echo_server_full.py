
import json
import pytest
from mcp_test import MCPTestClient


# ── Counter Tool ──────────────────────────────────────────────────────────

def test_counter_increments(mcp_client: MCPTestClient):
    r1 = mcp_client.call_tool("counter")
    r2 = mcp_client.call_tool("counter")
    r3 = mcp_client.call_tool("counter")
    assert int(r1.text()) < int(r2.text()) < int(r3.text())


def test_counter_concurrent(mcp_client: MCPTestClient):
    import concurrent.futures

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(mcp_client.call_tool, "counter") for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    values = sorted(int(r.text()) for r in results)
    assert len(set(values)) == 5


# ── Image Tool ────────────────────────────────────────────────────────────

def test_image_tool_returns_base64(mcp_client: MCPTestClient):
    result = mcp_client.call_tool("image_tool")
    assert result.is_ok()
    content = result.content[0]
    assert content.type == "image"
    assert content.mime_type == "image/png"
    assert len(content.data) > 0


# ── Binary Resource ───────────────────────────────────────────────────────

def test_binary_resource_blob(mcp_client: MCPTestClient):
    resources = mcp_client.list_resources()
    image_uris = [r.uri for r in resources if "image" in r.uri]
    assert len(image_uris) > 0, "Should have a test://image resource"

    content = mcp_client.read_resource("test://image")
    assert content.uri == "test://image"
    contents = content.raw.get("result", {}).get("contents", [{}])
    assert contents[0].get("blob") is not None


# ── URI Template Resource ─────────────────────────────────────────────────

def test_uri_template_resource(mcp_client: MCPTestClient):
    content = mcp_client.read_resource("test://data/mykey")
    data = json.loads(content.text)
    assert data["key"] == "mykey"
    assert data["value"] == "data-for-mykey"


def test_resource_templates_list(mcp_client: MCPTestClient):
    result = mcp_client._request("resources/templates/list", {})
    templates = result.get("result", {}).get("resourceTemplates", [])
    assert len(templates) >= 1
    assert any("data/{key}" in t.get("uriTemplate", "") for t in templates)


# ── Resource Subscriptions ────────────────────────────────────────────────

def test_resource_subscribe_unsubscribe(mcp_client: MCPTestClient):
    mcp_client.subscribe_resource("test://echo")
    mcp_client.unsubscribe_resource("test://echo")


# ── Code Review Prompt ────────────────────────────────────────────────────

def test_code_review_prompt_listed(mcp_client: MCPTestClient):
    prompts = mcp_client.list_prompts()
    names = [p.name for p in prompts]
    assert "code_review" in names
    assert "echo_prompt" in names


def test_code_review_prompt_renders(mcp_client: MCPTestClient):
    result = mcp_client.get_prompt("code_review", {
        "code": "def hello(): pass",
        "language": "python",
        "style": "brief",
    })
    messages = result.get("result", {}).get("messages", [])
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "python" in messages[0]["content"]["text"]
    assert "brief" in messages[1]["content"]["text"]


def test_code_review_prompt_defaults(mcp_client: MCPTestClient):
    result = mcp_client.get_prompt("code_review", {"code": "x = 1"})
    messages = result.get("result", {}).get("messages", [])
    assert len(messages) == 2


# ── Pagination ────────────────────────────────────────────────────────────

def test_tools_pagination(mcp_client: MCPTestClient):
    result = mcp_client._request("tools/list", {})
    page1_tools = result.get("result", {}).get("tools", [])
    cursor = result.get("result", {}).get("nextCursor")

    assert cursor is not None
    assert len(page1_tools) == 5

    result2 = mcp_client._request("tools/list", {"cursor": cursor})
    page2_tools = result2.get("result", {}).get("tools", [])
    cursor2 = result2.get("result", {}).get("nextCursor")

    assert len(page2_tools) == 5
    assert cursor2 is not None

    result3 = mcp_client._request("tools/list", {"cursor": cursor2})
    page3_tools = result3.get("result", {}).get("tools", [])
    cursor3 = result3.get("result", {}).get("nextCursor")

    assert len(page3_tools) == 4
    assert cursor3 is None

    all_names = [t["name"] for t in page1_tools + page2_tools + page3_tools]
    assert len(set(all_names)) == 14


# ── Completion/Complete ───────────────────────────────────────────────────

def test_completion_complete(mcp_client: MCPTestClient):
    result = mcp_client._request("completion/complete", {
        "ref": {"type": "ref/prompt", "name": "code_review"},
        "argument": {"name": "language", "value": "py"},
    })
    values = result.get("result", {}).get("completion", {}).get("values", [])
    assert "python" in values


def test_completion_no_match(mcp_client: MCPTestClient):
    result = mcp_client._request("completion/complete", {
        "ref": {"type": "ref/prompt", "name": "code_review"},
        "argument": {"name": "language", "value": "zzz"},
    })
    values = result.get("result", {}).get("completion", {}).get("values", [])
    assert len(values) == 0


# ── Logging ───────────────────────────────────────────────────────────────

def test_logging_set_level(mcp_client: MCPTestClient):
    result = mcp_client._request("logging/setLevel", {"level": "warning"})
    assert "error" not in result


# ── Multiple Resources ────────────────────────────────────────────────────

def test_resources_list_has_two(mcp_client: MCPTestClient):
    resources = mcp_client.list_resources()
    uris = [r.uri for r in resources]
    assert "test://echo" in uris
    assert "test://image" in uris
