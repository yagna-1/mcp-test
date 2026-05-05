
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import threading
import warnings
from typing import Any, Callable, Iterator

from .types import (
    MCPCancelledError,
    MCPClientError,
    MCPServerCrash,
    MCPTimeoutError,
    SPEC_VERSIONS,
    ToolList,
    ToolResult,
    ToolSchema,
    Resource,
    ResourceContent,
    Prompt,
    Task,
)
import contextlib


PROTOCOL_VERSION = "2024-11-05"


class _StderrCollector:
    """Drains stderr from the server process in a background thread."""

    def __init__(self, stderr):
        self._lines: list[str] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, args=(stderr,), daemon=True)
        self._thread.start()

    def _run(self, stderr):
        try:
            for line in stderr:
                with self._lock:
                    self._lines.append(line)
        except (ValueError, OSError):
            pass

    def get(self) -> str:
        with self._lock:
            return "".join(self._lines)


class _MessagePump:
    """Background thread that owns stdout and routes messages by shape."""

    def __init__(self, stdout, on_notification=None, on_request=None, send_response=None):
        self._stdout = stdout
        self._on_notification = on_notification
        self._on_request = on_request
        self._send_response = send_response
        self._pending: dict[int, threading.Event] = {}
        self._results: dict[int, dict] = {}
        self._pending_lock = threading.Lock()
        self._eof = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def register(self, request_id: int) -> threading.Event:
        ev = threading.Event()
        with self._pending_lock:
            self._pending[request_id] = ev
        return ev

    def get_result(self, request_id: int) -> dict:
        with self._pending_lock:
            return self._results.pop(request_id, {})

    def _run(self):
        try:
            while True:
                line = self._stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._dispatch(msg)
        finally:
            self._eof.set()
            with self._pending_lock:
                for ev in self._pending.values():
                    ev.set()

    def _dispatch(self, msg: dict):
        msg_id = msg.get("id")
        method = msg.get("method")

        if msg_id is not None and method is None:
            with self._pending_lock:
                ev = self._pending.pop(msg_id, None)
                if ev:
                    self._results[msg_id] = msg
                    ev.set()
        elif method is not None and msg_id is None:
            if self._on_notification:
                try:
                    self._on_notification(method, msg.get("params", {}))
                except Exception:
                    pass
        elif method is not None and msg_id is not None:
            if self._on_request:
                try:
                    result = self._on_request(method, msg.get("params", {}))
                    if self._send_response:
                        self._send_response({"jsonrpc": "2.0", "id": msg_id, "result": result})
                except Exception as e:
                    if self._send_response:
                        self._send_response({
                            "jsonrpc": "2.0", 
                            "id": msg_id, 
                            "error": {"code": -32603, "message": str(e)}
                        })

    @property
    def is_eof(self) -> bool:
        return self._eof.is_set()


class MCPTestClient:
    """Client for testing MCP servers over stdio transport."""

    PROTOCOL_VERSION = PROTOCOL_VERSION

    def __init__(
        self,
        command: str | list[str],
        *,
        timeout: float = 10.0,
        startup_timeout: float = 15.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ):
        self._command = command
        self._default_timeout = timeout
        self._startup_timeout = startup_timeout
        self._env = env
        self._cwd = cwd
        self._process: subprocess.Popen | None = None
        self._pump: _MessagePump | None = None
        self._stderr_collector: _StderrCollector | None = None
        self._id_counter = 0
        self._id_lock = threading.Lock()
        self._notifications: list[tuple[str, dict]] = []
        self._called_tools: set[str] = set()
        self._cancel_after_seconds: float | None = None
        
        self._server_version: str = ""
        self._server_capabilities: dict = {}
        self._server_info: dict = {}
        self._server_instructions: str = ""
        
        self._mock_responders: dict[str, Any] = {}
        self._server_requests: list[tuple[str, dict]] = []

    @classmethod
    def from_command(
        cls,
        command: str,
        *,
        timeout: float = 10.0,
        startup_timeout: float = 15.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> MCPTestClient:
        return cls(command, timeout=timeout, startup_timeout=startup_timeout, env=env, cwd=cwd)

    def _next_id(self) -> int:
        with self._id_lock:
            self._id_counter += 1
            return self._id_counter

    def _build_env(self) -> dict[str, str]:
        merged = os.environ.copy()
        if self._env:
            merged.update(self._env)
        return merged

    def _on_notification(self, method: str, params: dict):
        self._notifications.append((method, params))

    def _on_server_request(self, method: str, params: dict) -> dict:
        self._server_requests.append((method, params))
        responder = self._mock_responders.get(method)
        if responder:
            if hasattr(responder, "handle"):
                return responder.handle(params)
            elif callable(responder):
                return responder(params)
            return responder
        raise MCPClientError(f"No mock responder registered for server request: {method}")

    def _send_response(self, msg: dict) -> None:
        if self._process and self._process.stdin and not self._process.stdin.closed:
            try:
                self._process.stdin.write(json.dumps(msg) + "\n")
                self._process.stdin.flush()
            except Exception:
                pass
                
    def register_mock_responder(self, method: str, responder: Any) -> None:
        self._mock_responders[method] = responder
        
    def unregister_mock_responder(self, method: str) -> None:
        self._mock_responders.pop(method, None)


    def start(self) -> MCPTestClient:
        if isinstance(self._command, str):
            args = shlex.split(self._command)
        else:
            args = list(self._command)

        self._process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._build_env(),
            cwd=self._cwd,
            start_new_session=True,
        )

        self._stderr_collector = _StderrCollector(self._process.stderr)
        self._pump = _MessagePump(
            self._process.stdout, 
            on_notification=self._on_notification,
            on_request=self._on_server_request,
            send_response=self._send_response
        )

        response = self._request(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {
                    "sampling": {},
                    "roots": {"listChanged": True},
                },
                "clientInfo": {"name": "mcp-test", "version": "0.2.0"},
            },
            timeout=self._startup_timeout,
        )

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

        return self

    def close(self) -> None:
        if self._process is None:
            return

        try:
            if self._process.stdin and not self._process.stdin.closed:
                try:
                    self._process.stdin.close()
                except OSError:
                    pass

            try:
                self._process.wait(timeout=self._default_timeout)
                return
            except subprocess.TimeoutExpired:
                pass

            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

            try:
                self._process.wait(timeout=1)
                return
            except subprocess.TimeoutExpired:
                pass

            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass

            self._process.wait(timeout=1)
        except Exception:
            pass
        finally:
            self._process = None

    def __enter__(self) -> MCPTestClient:
        return self.start()

    def __exit__(self, *_):
        self.close()


    def _assert_running(self) -> None:
        if self._process is None:
            raise MCPClientError("Client is not started. Call start() first.")
        returncode = self._process.poll()
        if returncode is not None:
            stderr = self._stderr_collector.get() if self._stderr_collector else ""
            raise MCPServerCrash(returncode, stderr)

    def _request(self, method: str, params: dict, timeout: float | None = None) -> dict:
        self._assert_running()
        timeout = timeout or self._default_timeout
        req_id = self._next_id()

        event = self._pump.register(req_id)

        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        
        cancel_timer: threading.Timer | None = None
        if getattr(self, "_cancel_after_seconds", None) is not None:
            def _send_cancel():
                cancel_msg = {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": req_id}
                }
                try:
                    if self._process and self._process.stdin and not self._process.stdin.closed:
                        self._process.stdin.write(json.dumps(cancel_msg) + "\n")
                        self._process.stdin.flush()
                except Exception:
                    pass
            cancel_timer = threading.Timer(self._cancel_after_seconds, _send_cancel)
            cancel_timer.start()

        try:
            self._process.stdin.write(json.dumps(msg) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            stderr = self._stderr_collector.get() if self._stderr_collector else ""
            returncode = self._process.poll()
            if returncode is not None:
                raise MCPServerCrash(returncode, stderr) from e
            raise MCPClientError(f"Failed to write to server stdin: {e}") from e

        signaled = event.wait(timeout=timeout)
        if not signaled:
            returncode = self._process.poll()
            if returncode is not None:
                stderr = self._stderr_collector.get() if self._stderr_collector else ""
                raise MCPServerCrash(returncode, stderr)
            stderr = self._stderr_collector.get() if self._stderr_collector else ""
            raise MCPTimeoutError(
                f"No response for '{method}' after {timeout}s. "
                f"Server stderr:\n{stderr or '(empty)'}"
            )

        if cancel_timer:
            cancel_timer.cancel()

        result = self._pump.get_result(req_id)
        if not result:
            returncode = self._process.poll()
            stderr = self._stderr_collector.get() if self._stderr_collector else ""
            if returncode is not None:
                raise MCPServerCrash(returncode, stderr)
            raise MCPClientError(f"Empty result for request {req_id}")

        return result


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
        all_resources: list[Resource] = []
        for r in self.list_resources_paginated():
            all_resources.append(r)
        return all_resources

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
        all_prompts: list[Prompt] = []
        for p in self.list_prompts_paginated():
            all_prompts.append(p)
        return all_prompts

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
        self._cancel_after_seconds = seconds  # type: ignore
        try:
            yield
        finally:
            self._cancel_after_seconds = None  # type: ignore


    @contextlib.contextmanager
    def mock_sampling(self, response: str):
        from .mock_client import MockSampler
        sampler = MockSampler(response)
        self.register_mock_responder("sampling/createMessage", sampler)
        try:
            yield sampler
        finally:
            self.unregister_mock_responder("sampling/createMessage")

    @contextlib.contextmanager
    def mock_elicitation(self, data: dict):
        from .mock_client import MockElicitor
        elicitor = MockElicitor(data)
        self.register_mock_responder("elicitation/create", elicitor)
        try:
            yield elicitor
        finally:
            self.unregister_mock_responder("elicitation/create")

    @contextlib.contextmanager
    def with_roots(self, roots: list[dict]):
        self.register_mock_responder("roots/list", lambda params: {"roots": roots})
        try:
            yield
        finally:
            self.unregister_mock_responder("roots/list")


    def call_tool_async(self, name: str, _meta: dict | None = None, **arguments: Any) -> str:
        self._called_tools.add(name)
        params: dict[str, Any] = {"name": name, "arguments": arguments}
        if _meta:
            params["_meta"] = _meta
        response = self._request("tools/call", params)
        task = Task.from_response(response)
        if not task:
            raise MCPClientError(f"Tool {name} did not return a task handle.")
        return task.id

    def poll_task(self, task_id: str) -> Task:
        response = self._request("tasks/get", {"id": task_id})
        task = Task.from_response(response)
        if not task:
            raise MCPClientError(f"Task get did not return a task handle for {task_id}.")
        return task

    def send_task_input(self, task_id: str, input_data: dict) -> Task:
        response = self._request("tasks/sendInput", {"id": task_id, "input": input_data})
        task = Task.from_response(response)
        if not task:
            raise MCPClientError(f"tasks/sendInput did not return a task for {task_id}.")
        return task

    def cancel_task(self, task_id: str) -> Task:
        response = self._request("tasks/cancel", {"id": task_id})
        task = Task.from_response(response)
        if not task:
            raise MCPClientError(f"tasks/cancel did not return a task for {task_id}.")
        return task

    def wait_for_task(
        self,
        task_id: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
        input_handler: Any = None,
    ) -> Task:
        import time
        deadline = time.monotonic() + timeout
        interval = poll_interval

        while time.monotonic() < deadline:
            task = self.poll_task(task_id)

            if task.status == "completed":
                return task
            elif task.status == "failed":
                raise MCPClientError(
                    f"Task {task_id} failed: {task.error or 'unknown error'}"
                )
            elif task.status == "cancelled":
                raise MCPCancelledError(f"Task {task_id} was cancelled")
            elif task.status == "input_required":
                if input_handler and task.elicitation_request:
                    input_data = input_handler(task.elicitation_request)
                    task = self.send_task_input(task_id, input_data)
                    continue
                else:
                    raise MCPClientError(
                        f"Task {task_id} requires input but no handler provided"
                    )

            time.sleep(interval)
            interval = min(interval * 2, 5.0)

        raise MCPTimeoutError(f"Task {task_id} did not complete within {timeout}s")

    @property
    def notifications(self) -> list[tuple[str, dict]]:
        return list(self._notifications)

    @property
    def called_tools(self) -> set[str]:
        return self._called_tools.copy()


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


def make_client(
    command: str,
    *,
    timeout: float = 10.0,
    startup_timeout: float = 15.0,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> MCPTestClient:
    return MCPTestClient(command, timeout=timeout, startup_timeout=startup_timeout, env=env, cwd=cwd)
