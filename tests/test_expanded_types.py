import pytest


def test_audio_tool_returns_audio_content(mcp_client):
    result = mcp_client.call_tool("audio_tool")
    assert result.is_ok()
    assert len(result.content) == 1
    c = result.content[0]
    assert c.type == "audio"
    assert c.mime_type == "audio/wav"
    assert len(c.data) > 0


def test_resource_result_tool_returns_resource_content(mcp_client):
    result = mcp_client.call_tool("resource_result_tool")
    assert result.is_ok()
    assert len(result.content) == 1
    c = result.content[0]
    assert c.type == "resource"
    assert c.resource["uri"] == "test://echo"
    assert c.resource["text"] == "Embedded resource content"


def test_tool_has_title(mcp_client):
    tools = mcp_client.list_tools()
    annotated = tools.find("annotated_tool")
    assert annotated is not None
    assert annotated.title == "Annotated Tool"


def test_tool_has_icons(mcp_client):
    tools = mcp_client.list_tools()
    annotated = tools.find("annotated_tool")
    assert annotated is not None
    assert len(annotated.icons) == 1
    icon = annotated.icons[0]
    assert icon.type == "svg"
    assert len(icon.data) > 0
    assert icon.is_valid()


def test_resource_has_title(mcp_client):
    resources = mcp_client.list_resources()
    echo_res = next((r for r in resources if r.uri == "test://echo"), None)
    assert echo_res is not None
    assert echo_res.title == "Echo Text Resource"


def test_resource_has_size(mcp_client):
    resources = mcp_client.list_resources()
    echo_res = next((r for r in resources if r.uri == "test://echo"), None)
    assert echo_res is not None
    assert echo_res.size == 26


def test_prompt_has_title(mcp_client):
    prompts = mcp_client.list_prompts()
    echo_prompt = next((p for p in prompts if p.name == "echo_prompt"), None)
    assert echo_prompt is not None
    assert echo_prompt.title == "Echo Prompt"


def test_prompt_argument_has_title(mcp_client):
    prompts = mcp_client.list_prompts()
    code_review = next((p for p in prompts if p.name == "code_review"), None)
    assert code_review is not None
    assert code_review.arguments[0]["title"] == "Source Code"


def test_tool_name_format(mcp_client):
    tools = mcp_client.list_tools()
    for tool in tools:
        assert tool.has_valid_name(), f"Tool name {tool.name!r} does not follow SEP-986"


def test_unknown_method_returns_32601(mcp_client):
    from mcp_test.types import JSONRPCErrors
    response = mcp_client._request("nonexistent/method", {})
    assert "error" in response
    assert response["error"]["code"] == JSONRPCErrors.METHOD_NOT_FOUND


def test_unknown_tool_returns_32601(mcp_client):
    result = mcp_client.call_tool("nonexistent_tool_xyz")
    assert result.is_error()
    assert result.error is not None
    assert result.error.code == -32601


def test_server_info_available(mcp_client):
    assert mcp_client.server_version != ""
    assert mcp_client.server_info.get("name") != ""


def test_completion_with_context(mcp_client):
    response = mcp_client.completion_complete(
        ref={"type": "ref/prompt", "name": "code_review"},
        argument={"name": "language", "value": "p"},
        context={"code": "print('hello')"},
    )
    result = response.get("result", {})
    values = result.get("completion", {}).get("values", [])
    assert any("(ctx)" in v for v in values)


def test_completion_ref_resource(mcp_client):
    response = mcp_client.completion_complete(
        ref={"type": "ref/resource", "uri": "test://data/{key}"},
        argument={"name": "key", "value": "u"},
    )
    result = response.get("result", {})
    values = result.get("completion", {}).get("values", [])
    assert "users" in values


def test_meta_in_tool_call(mcp_client):
    result = mcp_client.call_tool("echo", _meta={"progressToken": "test-token"}, message="hello")
    assert result.is_ok()
    assert result.text() == "hello"
