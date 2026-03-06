
from .client import MCPTestClient
from .types import TOOL_NAME_PATTERN, Icon


def assert_tool_has_annotation(client: MCPTestClient, tool_name: str, annotation: str, expected_value: bool = True) -> None:
    tool = client.list_tools().find(tool_name)
    assert tool is not None, f"Tool {tool_name!r} not found"
    
    val = getattr(tool.annotations, annotation, None)
    assert val == expected_value, f"Expected {tool_name} annotation {annotation} to be {expected_value}, got {val}"


def assert_tool_is_read_only(client: MCPTestClient, tool_name: str) -> None:
    assert_tool_has_annotation(client, tool_name, "read_only_hint", True)


def assert_tool_is_destructive(client: MCPTestClient, tool_name: str) -> None:
    assert_tool_has_annotation(client, tool_name, "destructive_hint", True)


def assert_tool_is_idempotent(client: MCPTestClient, tool_name: str) -> None:
    assert_tool_has_annotation(client, tool_name, "idempotent_hint", True)


def assert_tool_is_open_world(client: MCPTestClient, tool_name: str) -> None:
    assert_tool_has_annotation(client, tool_name, "open_world_hint", True)


def assert_tool_name_valid(client: MCPTestClient, tool_name: str) -> None:
    tool = client.list_tools().find(tool_name)
    assert tool is not None, f"Tool {tool_name!r} not found"
    assert TOOL_NAME_PATTERN.match(tool.name), (
        f"Tool name {tool.name!r} does not follow SEP-986 format "
        "(must be lowercase, start with letter, contain only [a-z0-9_-])"
    )


def assert_tool_names_valid(client: MCPTestClient) -> list[str]:
    tools = client.list_tools()
    invalid = [t.name for t in tools if not TOOL_NAME_PATTERN.match(t.name)]
    assert len(invalid) == 0, f"Invalid tool names (SEP-986): {invalid}"
    return invalid


def assert_valid_icons(icons: list[Icon]) -> None:
    for i, icon in enumerate(icons):
        assert icon.type in ("svg", "png"), (
            f"Icon[{i}] type must be 'svg' or 'png', got {icon.type!r}"
        )
        assert len(icon.data) > 0, f"Icon[{i}] data must be non-empty base64"


def assert_tool_icons_valid(client: MCPTestClient, tool_name: str) -> None:
    tool = client.list_tools().find(tool_name)
    assert tool is not None, f"Tool {tool_name!r} not found"
    if tool.icons:
        assert_valid_icons(tool.icons)


def assert_resource_size_matches(client: MCPTestClient, resource_uri: str) -> None:
    resources = client.list_resources()
    res = next((r for r in resources if r.uri == resource_uri), None)
    assert res is not None, f"Resource {resource_uri!r} not found"
    if res.size is not None:
        content = client.read_resource(resource_uri)
        actual_len = len(content.text.encode("utf-8")) if content.text else len(content.blob)
        assert actual_len == res.size, (
            f"Resource {resource_uri!r} declared size={res.size} but actual content is {actual_len} bytes"
        )


def assert_tool_has_title(client: MCPTestClient, tool_name: str) -> None:
    tool = client.list_tools().find(tool_name)
    assert tool is not None, f"Tool {tool_name!r} not found"
    assert tool.title, f"Tool {tool_name!r} has no title (required since spec 2025-06-18)"
