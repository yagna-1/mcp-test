
import json
import pytest

from mcp_test.http_client import (
    HTTPMCPTestClient,
    SSEEvent,
    TransportMode,
    parse_sse_stream,
)


# ── SSE parser unit tests ────────────────────────────────────────────────

class TestSSEParser:
    """Unit tests for the SSE line parser."""

    def test_parse_basic_message(self):
        lines = [
            "data: hello world\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].event == "message"
        assert events[0].data == "hello world"

    def test_parse_named_event(self):
        lines = [
            "event: endpoint\n",
            "data: /api/mcp\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].event == "endpoint"
        assert events[0].data == "/api/mcp"

    def test_parse_event_with_id(self):
        lines = [
            "id: evt-42\n",
            "data: payload\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].id == "evt-42"
        assert events[0].data == "payload"

    def test_parse_multiline_data(self):
        lines = [
            "data: line1\n",
            "data: line2\n",
            "data: line3\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].data == "line1\nline2\nline3"

    def test_parse_multiple_events(self):
        lines = [
            "data: first\n",
            "\n",
            "data: second\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 2
        assert events[0].data == "first"
        assert events[1].data == "second"

    def test_comments_are_ignored(self):
        lines = [
            ": this is a comment\n",
            "data: actual data\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].data == "actual data"

    def test_retry_field(self):
        lines = [
            "retry: 3000\n",
            "data: test\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].retry == 3000

    def test_retry_invalid_value_ignored(self):
        lines = [
            "retry: not-a-number\n",
            "data: test\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].retry is None

    def test_field_with_no_colon(self):
        lines = [
            "data\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].data == ""

    def test_json_data(self):
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        lines = [
            f"data: {json.dumps(payload)}\n",
            "\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].json() == payload

    def test_empty_stream(self):
        events = list(parse_sse_stream(iter([])))
        assert events == []

    def test_stream_ends_without_blank_line(self):
        lines = [
            "data: trailing\n",
        ]
        events = list(parse_sse_stream(iter(lines)))
        assert len(events) == 1
        assert events[0].data == "trailing"


# ── SSEEvent unit tests ──────────────────────────────────────────────────

class TestSSEEvent:
    """Unit tests for the SSEEvent data class."""

    def test_default_event_type(self):
        event = SSEEvent()
        assert event.event == "message"
        assert event.data == ""
        assert event.id == ""
        assert event.retry is None

    def test_json_method(self):
        event = SSEEvent()
        event.data = '{"key": "value"}'
        assert event.json() == {"key": "value"}

    def test_json_invalid_raises(self):
        event = SSEEvent()
        event.data = "not json"
        with pytest.raises(json.JSONDecodeError):
            event.json()


# ── Transport mode tests ─────────────────────────────────────────────────

class TestTransportMode:
    """Tests for transport mode constants."""

    def test_streamable_mode(self):
        assert TransportMode.STREAMABLE == "streamable"

    def test_legacy_sse_mode(self):
        assert TransportMode.LEGACY_SSE == "legacy_sse"

    def test_auto_mode(self):
        assert TransportMode.AUTO == "auto"


# ── HTTPMCPTestClient construction tests ─────────────────────────────────

class TestHTTPClientConstruction:
    """Tests for HTTPMCPTestClient instantiation and configuration."""

    def test_from_url_creates_client(self):
        client = HTTPMCPTestClient.from_url(
            "http://localhost:8080/mcp",
            timeout=5.0,
        )
        assert client._base_url == "http://localhost:8080/mcp"
        assert client._timeout == 5.0
        assert client._transport == TransportMode.AUTO

    def test_explicit_streamable_transport(self):
        client = HTTPMCPTestClient(
            "http://localhost:8080",
            transport=TransportMode.STREAMABLE,
        )
        assert client._transport == TransportMode.STREAMABLE

    def test_explicit_legacy_transport(self):
        client = HTTPMCPTestClient(
            "http://localhost:8080",
            transport=TransportMode.LEGACY_SSE,
        )
        assert client._transport == TransportMode.LEGACY_SSE

    def test_trailing_slash_stripped(self):
        client = HTTPMCPTestClient("http://localhost:8080/")
        assert client._base_url == "http://localhost:8080"

    def test_custom_headers(self):
        client = HTTPMCPTestClient(
            "http://localhost:8080",
            headers={"X-Custom": "value"},
        )
        assert client._headers == {"X-Custom": "value"}

    def test_auth_token_stored(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        client.set_auth_token("test-token-123")
        assert client._auth_token == "test-token-123"

    def test_initial_state(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        assert client.called_tools == set()
        assert client.notifications == []
        assert client.last_event_id == ""
        assert client.session_id == ""
        assert client.transport_mode == ""

    def test_last_event_id_settable(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        client.last_event_id = "evt-99"
        assert client.last_event_id == "evt-99"


# ── SSE response parsing tests ───────────────────────────────────────────

class TestSSEResponseParsing:
    """Tests for _parse_sse_response method."""

    def test_parse_json_rpc_response(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        body = 'event: message\ndata: {"jsonrpc": "2.0", "id": 5, "result": {"tools": []}}\n\n'
        result = client._parse_sse_response(body, 5)
        assert result["id"] == 5
        assert result["result"]["tools"] == []

    def test_parse_collects_notifications(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        body = (
            'event: message\n'
            'data: {"jsonrpc": "2.0", "method": "notifications/progress", '
            '"params": {"progress": 1, "total": 5}}\n\n'
            'event: message\n'
            'data: {"jsonrpc": "2.0", "id": 3, "result": {}}\n\n'
        )
        result = client._parse_sse_response(body, 3)
        assert result["id"] == 3
        assert len(client._notifications) == 1
        assert client._notifications[0][0] == "notifications/progress"

    def test_parse_tracks_event_id(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        body = 'id: evt-42\nevent: message\ndata: {"jsonrpc": "2.0", "id": 1, "result": {}}\n\n'
        client._parse_sse_response(body, 1)
        assert client.last_event_id == "evt-42"

    def test_parse_empty_body_returns_default(self):
        client = HTTPMCPTestClient("http://localhost:8080")
        result = client._parse_sse_response("", 1)
        assert result["id"] == 1
        assert result["result"] == {}


# ── API parity tests ─────────────────────────────────────────────────────

class TestAPIParity:
    """Verify HTTPMCPTestClient has the same API surface as MCPTestClient."""

    def test_has_call_tool(self):
        assert callable(getattr(HTTPMCPTestClient, "call_tool", None))

    def test_has_list_tools(self):
        assert callable(getattr(HTTPMCPTestClient, "list_tools", None))

    def test_has_list_tools_paginated(self):
        assert callable(getattr(HTTPMCPTestClient, "list_tools_paginated", None))

    def test_has_list_resources(self):
        assert callable(getattr(HTTPMCPTestClient, "list_resources", None))

    def test_has_list_resources_paginated(self):
        assert callable(getattr(HTTPMCPTestClient, "list_resources_paginated", None))

    def test_has_read_resource(self):
        assert callable(getattr(HTTPMCPTestClient, "read_resource", None))

    def test_has_list_prompts(self):
        assert callable(getattr(HTTPMCPTestClient, "list_prompts", None))

    def test_has_list_prompts_paginated(self):
        assert callable(getattr(HTTPMCPTestClient, "list_prompts_paginated", None))

    def test_has_get_prompt(self):
        assert callable(getattr(HTTPMCPTestClient, "get_prompt", None))

    def test_has_subscribe_resource(self):
        assert callable(getattr(HTTPMCPTestClient, "subscribe_resource", None))

    def test_has_unsubscribe_resource(self):
        assert callable(getattr(HTTPMCPTestClient, "unsubscribe_resource", None))

    def test_has_completion_complete(self):
        assert callable(getattr(HTTPMCPTestClient, "completion_complete", None))

    def test_has_ping(self):
        assert callable(getattr(HTTPMCPTestClient, "ping", None))

    def test_has_set_logging_level(self):
        assert callable(getattr(HTTPMCPTestClient, "set_logging_level", None))

    def test_has_capture_notifications(self):
        assert callable(getattr(HTTPMCPTestClient, "capture_notifications", None))

    def test_has_cancel_after(self):
        assert callable(getattr(HTTPMCPTestClient, "cancel_after", None))

    def test_has_validate_schemas(self):
        assert callable(getattr(HTTPMCPTestClient, "validate_schemas", None))

    def test_has_assert_schema_compliant(self):
        assert callable(getattr(HTTPMCPTestClient, "assert_schema_compliant", None))

    def test_has_set_auth_token(self):
        assert callable(getattr(HTTPMCPTestClient, "set_auth_token", None))

    def test_has_server_version_property(self):
        assert isinstance(
            getattr(HTTPMCPTestClient, "server_version", None), property
        )

    def test_has_server_capabilities_property(self):
        assert isinstance(
            getattr(HTTPMCPTestClient, "server_capabilities", None), property
        )

    def test_has_notifications_property(self):
        assert isinstance(
            getattr(HTTPMCPTestClient, "notifications", None), property
        )

    def test_has_called_tools_property(self):
        assert isinstance(
            getattr(HTTPMCPTestClient, "called_tools", None), property
        )


    def test_has_reconnect(self):
        assert callable(getattr(HTTPMCPTestClient, "reconnect", None))

    def test_has_request_streaming(self):
        assert callable(getattr(HTTPMCPTestClient, "_request_streaming", None))

    def test_has_transport_mode_property(self):
        assert isinstance(
            getattr(HTTPMCPTestClient, "transport_mode", None), property
        )

    def test_has_last_event_id_property(self):
        assert isinstance(
            getattr(HTTPMCPTestClient, "last_event_id", None), property
        )

    def test_has_call_tool_async(self):
        assert callable(getattr(HTTPMCPTestClient, "call_tool_async", None))

    def test_has_get_task(self):
        assert callable(getattr(HTTPMCPTestClient, "get_task", None))

    def test_has_send_task_input(self):
        assert callable(getattr(HTTPMCPTestClient, "send_task_input", None))

    def test_has_cancel_task(self):
        assert callable(getattr(HTTPMCPTestClient, "cancel_task", None))
