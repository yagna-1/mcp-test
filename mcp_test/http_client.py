
from __future__ import annotations

import contextlib
import json
import threading
import time
import warnings
from typing import Any, Iterator

from .timeouts import TimeoutConfig
from .types import (
    MCPAuthRequired,
    MCPClientError,
    MCPForbiddenError,
    MCPTimeoutError,
    SPEC_VERSIONS,
    Task,
    ToolList,
    ToolResult,
    ToolSchema,
    Resource,
    ResourceContent,
    Prompt,
)
from .wire_trace import WireTrace


PROTOCOL_VERSION = "2024-11-05"


def _require_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        raise MCPClientError(
            "httpx is required for HTTP transport. Install with: pip install pytest-mcp-plugin[http]"
        )


def _looks_like_streamable_unsupported(exc: BaseException) -> bool:
    """Heuristic: did the failure look like 'this URL doesn't speak Streamable HTTP'?

    We only flip to legacy SSE when the streamable POST is clearly rejected as
    a transport mismatch. 5xx, 4xx auth, redirects, JSON parse errors etc. are
    real failures the user should see, not signals to silently re-handshake on
    a different transport.
    """
    msg = str(exc)
    # Patterns produced by _request() above.
    return any(token in msg for token in ("HTTP error 404", "HTTP error 405"))


# ── SSE parser ────────────────────────────────────────────────────────────

class SSEEvent:
    """A single Server-Sent Event."""

    __slots__ = ("event", "data", "id", "retry")

    def __init__(self) -> None:
        self.event: str = "message"
        self.data: str = ""
        self.id: str = ""
        self.retry: int | None = None

    def json(self) -> Any:
        return json.loads(self.data)


def parse_sse_stream(lines: Iterator[str]) -> Iterator[SSEEvent]:
    current = SSEEvent()
    data_parts: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")

        if not line:
            if data_parts:
                current.data = "\n".join(data_parts)
                yield current
            current = SSEEvent()
            data_parts = []
            continue

        if line.startswith(":"):
            continue

        if ":" in line:
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
        else:
            field = line
            value = ""

        if field == "event":
            current.event = value
        elif field == "data":
            data_parts.append(value)
        elif field == "id":
            current.id = value
        elif field == "retry":
            try:
                current.retry = int(value)
            except ValueError:
                pass

    if data_parts:
        current.data = "\n".join(data_parts)
        yield current


# ── Transport mode enum ──────────────────────────────────────────────────

class TransportMode:
    STREAMABLE = "streamable"
    LEGACY_SSE = "legacy_sse"
    AUTO = "auto"


# ── HTTP Client ───────────────────────────────────────────────────────────

class HTTPMCPTestClient:
    """Client for testing MCP servers over HTTP SSE transport."""

    PROTOCOL_VERSION = PROTOCOL_VERSION

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        transport: str = TransportMode.AUTO,
        method_timeouts: dict[str, float] | None = None,
        use_smart_timeouts: bool = False,
        trace_path: str | None = None,
        trace: WireTrace | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._timeouts = TimeoutConfig.from_values(
            timeout,
            method_timeouts,
            use_smart_defaults=use_smart_timeouts,
        )
        self._headers = headers or {}
        self._trace = trace or WireTrace(trace_path)
        self._httpx: Any = None
        self._client: Any = None
        self._id_counter = 0
        self._called_tools: set[str] = set()
        self._notifications: list[tuple[str, dict]] = []
        self._auth_token: str = ""
        self._session_id: str = ""
        self._last_event_id: str = ""
        self._transport: str = transport
        self._resolved_transport: str = ""

        self._legacy_endpoint: str = ""
        self._sse_thread: threading.Thread | None = None
        self._sse_stop_event = threading.Event()

        self._cancel_after_seconds: float | None = None

        self._server_version: str = ""
        self._server_capabilities: dict = {}
        self._server_info: dict = {}
        self._server_instructions: str = ""

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        transport: str = TransportMode.AUTO,
        method_timeouts: dict[str, float] | None = None,
        use_smart_timeouts: bool = False,
        trace_path: str | None = None,
    ) -> HTTPMCPTestClient:
        return cls(
            url,
            timeout=timeout,
            headers=headers,
            transport=transport,
            method_timeouts=method_timeouts,
            use_smart_timeouts=use_smart_timeouts,
            trace_path=trace_path,
        )

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter


    def start(self) -> HTTPMCPTestClient:
        self._httpx = _require_httpx()
        merged_headers = dict(self._headers)
        merged_headers["Accept"] = "application/json, text/event-stream"
        merged_headers["MCP-Protocol-Version"] = self.PROTOCOL_VERSION
        if self._auth_token:
            merged_headers["Authorization"] = f"Bearer {self._auth_token}"

        self._client = self._httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=merged_headers,
            # Many real-world MCP servers (FastMCP, Starlette w/ trailing-slash
            # redirects, reverse proxies) issue 301/307 to canonicalise the
            # endpoint URL. Following redirects keeps the client robust without
            # forcing every caller to know the canonical form.
            follow_redirects=True,
        )

        if self._transport == TransportMode.AUTO:
            try:
                self._resolved_transport = TransportMode.STREAMABLE
                self._do_initialize()
            except MCPAuthRequired:
                # Auth failures are real auth failures, not "wrong transport".
                raise
            except (MCPClientError, MCPTimeoutError) as exc:
                # Only fall back to legacy SSE when the streamable path is
                # clearly unsupported (404/405 on POST, or no JSON response).
                # A 307 redirect, a 5xx, or an auth failure should never
                # silently switch transports.
                if not _looks_like_streamable_unsupported(exc):
                    raise
                self._resolved_transport = TransportMode.LEGACY_SSE
                self._start_legacy_sse()
                self._do_initialize()
        elif self._transport == TransportMode.LEGACY_SSE:
            self._resolved_transport = TransportMode.LEGACY_SSE
            self._start_legacy_sse()
            self._do_initialize()
        else:
            self._resolved_transport = TransportMode.STREAMABLE
            self._do_initialize()

        return self

    def _do_initialize(self) -> None:
        response = self._request("initialize", {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {
                "sampling": {},
                "roots": {"listChanged": True},
            },
            "clientInfo": {"name": "mcp-test", "version": "0.3.0"},
        })

        result = response.get("result", {})
        self._server_version = result.get("protocolVersion", "")
        self._server_capabilities = result.get("capabilities", {})
        self._server_info = result.get("serverInfo", {})
        self._server_instructions = result.get("instructions", "")

        if self._server_version and self._server_version != self.PROTOCOL_VERSION:
            warnings.warn(
                f"Server speaks MCP {self._server_version}, client expects {self.PROTOCOL_VERSION}. "
                "Some features may not work.",
                stacklevel=2,
            )

        # Per MCP spec, send `notifications/initialized` immediately after
        # the initialize handshake — FastMCP-backed servers reject all later
        # requests until they receive it.
        self._send_notification("notifications/initialized", {})

    def _send_notification(self, method: str, params: dict) -> None:
        if self._client is None:
            return
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        headers: dict[str, str] = {"Mcp-Method": method}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            self._client.post("/", json=payload, headers=headers, timeout=self._timeout)
            self._trace.record(
                "out",
                transport="http",
                message=payload,
                method=method,
                metadata={"headers": headers},
            )
        except Exception:  # notifications are fire-and-forget
            pass

    def _start_legacy_sse(self) -> None:
        self._sse_stop_event.clear()
        self._sse_thread = threading.Thread(
            target=self._legacy_sse_loop,
            daemon=True,
        )
        self._sse_thread.start()

        deadline = time.monotonic() + self._timeout
        while not self._legacy_endpoint:
            if time.monotonic() > deadline:
                raise MCPTimeoutError(
                    "Timed out waiting for legacy SSE endpoint event"
                )
            time.sleep(0.05)

    def _legacy_sse_loop(self) -> None:
        headers: dict[str, str] = {}
        if self._last_event_id:
            headers["Last-Event-ID"] = self._last_event_id

        while not self._sse_stop_event.is_set():
            try:
                with self._client.stream(
                    "GET", "/sse", headers=headers, timeout=None,
                ) as resp:
                    resp.raise_for_status()
                    for event in parse_sse_stream(resp.iter_lines()):
                        if self._sse_stop_event.is_set():
                            return

                        if event.id:
                            self._last_event_id = event.id

                        if event.event == "endpoint":
                            self._legacy_endpoint = event.data
                        elif event.event == "message":
                            try:
                                msg = event.json()
                                method = msg.get("method")
                                if method and "id" not in msg:
                                    self._notifications.append(
                                        (method, msg.get("params", {}))
                                    )
                            except (json.JSONDecodeError, Exception):
                                pass
            except Exception:
                if self._sse_stop_event.is_set():
                    return
                if self._last_event_id:
                    headers["Last-Event-ID"] = self._last_event_id
                time.sleep(0.5)

    def close(self) -> None:
        self._sse_stop_event.set()
        if self._sse_thread and self._sse_thread.is_alive():
            self._sse_thread.join(timeout=2.0)

        if self._client:
            self.terminate_session()
            self._client.close()
            self._client = None

    def __enter__(self) -> HTTPMCPTestClient:
        return self.start()

    def __exit__(self, *_):
        self.close()


    def _request(
        self,
        method: str,
        params: dict,
        timeout: float | None = None,
        *,
        _retry_on_missing_session: bool = True,
    ) -> dict:
        if self._client is None:
            raise MCPClientError("Client is not started. Call start() first.")

        timeout = self._timeouts.resolve(method, timeout)
        req_id = self._next_id()

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        post_url = "/"
        if self._resolved_transport == TransportMode.LEGACY_SSE and self._legacy_endpoint:
            post_url = self._legacy_endpoint

        request_headers: dict[str, str] = {}
        request_headers["Mcp-Method"] = method
        if method in {"tools/call", "prompts/get"} and "name" in params:
            request_headers["Mcp-Name"] = str(params["name"])
        elif method == "resources/read" and "uri" in params:
            request_headers["Mcp-Name"] = str(params["uri"])
        if self._session_id and method != "initialize":
            request_headers["Mcp-Session-Id"] = self._session_id
        if self._last_event_id:
            request_headers["Last-Event-ID"] = self._last_event_id

        try:
            resp = self._client.post(
                post_url,
                json=payload,
                headers=request_headers,
                timeout=timeout,
            )
            self._trace.record(
                "out",
                transport="http",
                message=payload,
                method=method,
                request_id=req_id,
                metadata={"url": post_url, "headers": request_headers},
            )
            self._trace.record(
                "in",
                transport="http",
                method=method,
                request_id=req_id,
                event="http",
                metadata={
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                },
            )
            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "")
                raise MCPAuthRequired(
                    status_code=401,
                    www_authenticate=www_auth,
                    message=f"Server requires authentication: {www_auth}",
                )
            if resp.status_code == 403:
                raise MCPForbiddenError(
                    message=f"Forbidden: {resp.text}",
                )
            if (
                resp.status_code == 404
                and self._session_id
                and method != "initialize"
                and _retry_on_missing_session
            ):
                self._session_id = ""
                self._do_initialize()
                return self._request(
                    method,
                    params,
                    timeout=timeout,
                    _retry_on_missing_session=False,
                )

            session_id = resp.headers.get("mcp-session-id")
            if session_id:
                self._session_id = session_id

            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                return self._parse_sse_response(resp.text, req_id)

            data = resp.json()
            self._trace.record(
                "in",
                transport="http",
                message=data,
                method=data.get("method", method),
                request_id=data.get("id", req_id),
            )
            return data
        except (MCPAuthRequired, MCPForbiddenError):
            raise
        except self._httpx.TimeoutException as e:
            raise MCPTimeoutError(
                f"No response for '{method}' after {timeout}s: {e}"
            ) from e
        except self._httpx.HTTPStatusError as e:
            raise MCPClientError(
                f"HTTP error {e.response.status_code} for '{method}': {e.response.text}"
            ) from e
        except Exception as e:
            if isinstance(e, (MCPClientError, MCPTimeoutError)):
                raise
            raise MCPClientError(f"HTTP request failed for '{method}': {e}") from e

    def _request_streaming(
        self, method: str, params: dict, timeout: float | None = None,
    ) -> Iterator[SSEEvent]:
        if self._client is None:
            raise MCPClientError("Client is not started. Call start() first.")

        timeout = self._timeouts.resolve(method, timeout)
        req_id = self._next_id()

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        post_url = "/"
        if self._resolved_transport == TransportMode.LEGACY_SSE and self._legacy_endpoint:
            post_url = self._legacy_endpoint

        headers = {"Accept": "text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._last_event_id:
            headers["Last-Event-ID"] = self._last_event_id

        with self._client.stream(
            "POST", post_url, json=payload, headers=headers, timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            self._trace.record(
                "out",
                transport="http",
                message=payload,
                method=method,
                request_id=req_id,
                metadata={"url": post_url, "headers": headers, "stream": True},
            )
            for event in parse_sse_stream(resp.iter_lines()):
                if event.id:
                    self._last_event_id = event.id
                self._trace.record(
                    "in",
                    transport="http",
                    event="sse",
                    method=method,
                    request_id=req_id,
                    metadata={"event": event.event, "id": event.id},
                )
                yield event

    def _parse_sse_response(self, body: str, req_id: int) -> dict:
        for event in parse_sse_stream(iter(body.splitlines(keepends=True))):
            if event.id:
                self._last_event_id = event.id

            if event.event == "message":
                try:
                    msg = event.json()
                except (json.JSONDecodeError, Exception):
                    continue

                if "method" in msg and "id" not in msg:
                    self._notifications.append(
                        (msg["method"], msg.get("params", {}))
                    )
                    continue

                if msg.get("id") == req_id:
                    self._trace.record(
                        "in",
                        transport="http",
                        message=msg,
                        method=msg.get("method"),
                        request_id=msg.get("id"),
                    )
                    return msg

        return {"jsonrpc": "2.0", "id": req_id, "result": {}}


    def reconnect(self) -> None:
        if self._resolved_transport == TransportMode.LEGACY_SSE:
            self._sse_stop_event.set()
            if self._sse_thread and self._sse_thread.is_alive():
                self._sse_thread.join(timeout=2.0)

            self._legacy_endpoint = ""
            self._start_legacy_sse()

    def stream_events(self, timeout: float | None = None) -> Iterator[SSEEvent]:
        """Open a Streamable HTTP GET stream, resuming with Last-Event-ID."""

        if self._client is None:
            raise MCPClientError("Client is not started. Call start() first.")
        headers = {"Accept": "text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._last_event_id:
            headers["Last-Event-ID"] = self._last_event_id

        with self._client.stream(
            "GET",
            "/",
            headers=headers,
            timeout=timeout or self._timeout,
        ) as resp:
            if resp.status_code == 404 and self._session_id:
                self._session_id = ""
                self._do_initialize()
                return
            resp.raise_for_status()
            for event in parse_sse_stream(resp.iter_lines()):
                if event.id:
                    self._last_event_id = event.id
                self._trace.record(
                    "in",
                    transport="http",
                    event="sse",
                    metadata={"event": event.event, "id": event.id},
                )
                yield event

    def terminate_session(self) -> None:
        """Best-effort Streamable HTTP session termination."""

        if not self._client or not self._session_id:
            return
        try:
            self._client.delete(
                "/",
                headers={"Mcp-Session-Id": self._session_id},
                timeout=min(self._timeout, 5.0),
            )
        except Exception:
            pass
        finally:
            self._session_id = ""

    @property
    def last_event_id(self) -> str:
        return self._last_event_id

    @last_event_id.setter
    def last_event_id(self, value: str) -> None:
        self._last_event_id = value

    @property
    def transport_mode(self) -> str:
        return self._resolved_transport


    def call_tool(self, name: str, _meta: dict | None = None, **arguments: Any) -> ToolResult:
        self._called_tools.add(name)
        params: dict[str, Any] = {"name": name, "arguments": arguments}
        if _meta:
            params["_meta"] = _meta
        response = self._request("tools/call", params)
        return ToolResult.from_response(response)

    def list_tools(self) -> ToolList:
        all_tools: list[dict] = []
        params: dict = {}
        while True:
            response = self._request("tools/list", params)
            result = response.get("result", {})
            all_tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
            params = {"cursor": cursor}

        synthetic = {"jsonrpc": "2.0", "id": 0, "result": {"tools": all_tools}}
        return ToolList.from_response(synthetic)

    def list_tools_paginated(self) -> Iterator[ToolSchema]:
        params: dict = {}
        while True:
            response = self._request("tools/list", params)
            result = response.get("result", {})
            for tool in result.get("tools", []):
                yield ToolSchema.from_dict(tool)
            cursor = result.get("nextCursor")
            if not cursor:
                break
            params = {"cursor": cursor}

    def list_resources(self) -> list[Resource]:
        return list(self.list_resources_paginated())

    def list_resources_paginated(self) -> Iterator[Resource]:
        params: dict = {}
        while True:
            response = self._request("resources/list", params)
            result = response.get("result", {})
            for resource in result.get("resources", []):
                yield Resource.from_dict(resource)
            cursor = result.get("nextCursor")
            if not cursor:
                break
            params = {"cursor": cursor}

    def read_resource(self, uri: str) -> ResourceContent:
        response = self._request("resources/read", {"uri": uri})
        return ResourceContent.from_response(response)

    def list_prompts(self) -> list[Prompt]:
        return list(self.list_prompts_paginated())

    def list_prompts_paginated(self) -> Iterator[Prompt]:
        params: dict = {}
        while True:
            response = self._request("prompts/list", params)
            result = response.get("result", {})
            for prompt in result.get("prompts", []):
                yield Prompt.from_dict(prompt)
            cursor = result.get("nextCursor")
            if not cursor:
                break
            params = {"cursor": cursor}

    def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        params: dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return self._request("prompts/get", params)

    def subscribe_resource(self, uri: str) -> dict:
        return self._request("resources/subscribe", {"uri": uri})

    def unsubscribe_resource(self, uri: str) -> dict:
        return self._request("resources/unsubscribe", {"uri": uri})

    def completion_complete(self, ref: dict, argument: dict, context: dict | None = None) -> dict:
        params: dict[str, Any] = {"ref": ref, "argument": argument}
        if context:
            params["context"] = context
        return self._request("completion/complete", params)

    def ping(self) -> dict:
        return self._request("ping", {})

    def set_logging_level(self, level: str) -> dict:
        return self._request("logging/setLevel", {"level": level})

    @contextlib.contextmanager
    def capture_notifications(self, method: str):
        class _Capture:
            collected: list[dict]
            def __init__(self):
                self.collected = []
        capture = _Capture()
        original_idx = len(self._notifications)
        try:
            yield capture
        finally:
            all_notes: list[tuple[str, dict]] = list(self._notifications)
            capture.collected = [
                params for m, params in all_notes[original_idx:]
                if m == method
            ]

    @contextlib.contextmanager
    def cancel_after(self, seconds: float):
        self._cancel_after_seconds = seconds
        try:
            yield
        finally:
            self._cancel_after_seconds = None

    def validate_schemas(self) -> list:
        from .schema_validator import validate_schemas as _validate
        tools = self.list_tools()
        return _validate(tools)

    def assert_schema_compliant(self, tool_name: str) -> None:
        from .schema_validator import (
            generate_valid_inputs,
            generate_invalid_inputs_missing_required,
            generate_invalid_inputs_wrong_types
        )
        tools = self.list_tools()
        tool = tools.find(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name!r} not found on server")

        valid_args = generate_valid_inputs(tool)
        result = self.call_tool(tool_name, **valid_args)
        assert result.is_ok(), f"Schema contract failed: valid input was rejected (args: {valid_args})"

        for args in generate_invalid_inputs_missing_required(tool):
            result = self.call_tool(tool_name, **args)
            assert result.is_error(), f"Schema contract failed: missing required field accepted (args: {args})"

        for args in generate_invalid_inputs_wrong_types(tool):
            result = self.call_tool(tool_name, **args)
            assert result.is_error(), f"Schema contract failed: wrong type accepted (args: {args})"


    def call_tool_async(self, name: str, **arguments: Any) -> str:
        self._called_tools.add(name)
        response = self._request("tools/call", {"name": name, "arguments": arguments})
        result = response.get("result", {})
        task = result.get("task", {})
        return task.get("id", "")

    def get_task(self, task_id: str) -> Task:
        response = self._request("tasks/get", {"id": task_id})
        return Task.from_response(response)

    def send_task_input(self, task_id: str, data: dict) -> Task:
        response = self._request("tasks/sendInput", {"id": task_id, "data": data})
        return Task.from_response(response)

    def cancel_task(self, task_id: str) -> Task:
        response = self._request("tasks/cancel", {"id": task_id})
        return Task.from_response(response)


    @property
    def server_version(self) -> str:
        return self._server_version

    @property
    def server_version_num(self) -> int:
        return SPEC_VERSIONS.get(self._server_version, 0)

    @property
    def server_capabilities(self) -> dict:
        return self._server_capabilities

    @property
    def server_info(self) -> dict:
        return self._server_info

    @property
    def server_instructions(self) -> str:
        return self._server_instructions

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def wire_trace(self) -> WireTrace:
        return self._trace


    def set_auth_token(self, token: str) -> None:
        self._auth_token = token
        if self._client:
            self._client.headers["Authorization"] = f"Bearer {token}"

    @property
    def notifications(self) -> list[tuple[str, dict]]:
        return list(self._notifications)

    @property
    def called_tools(self) -> set[str]:
        return self._called_tools.copy()
