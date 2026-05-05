#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import time
import threading

PROTOCOL_VERSION = "2024-11-05"

SERVER_INFO = {
    "name": "echo-test-server",
    "version": "2.0.0",
}

_1x1_RED_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
)

_AUDIO_WAV_B64 = "UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA="

_SVG_ICON_DATA = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNiIgaGVpZ2h0PSIxNiI+PGNpcmNsZSBjeD0iOCIgY3k9IjgiIHI9IjgiIGZpbGw9InJlZCIvPjwvc3ZnPg=="

TOOLS = [
    {
        "name": "echo",
        "description": "Echoes the input message back",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "slow_echo",
        "description": "Echoes after a delay (for timeout + progress testing)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "delay": {"type": "number", "description": "Seconds to wait"},
            },
            "required": ["message", "delay"],
        },
    },
    {
        "name": "error_tool",
        "description": "Always returns an error result (isError: true)",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "crash_tool",
        "description": "Crashes the server process immediately",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "multi_content",
        "description": "Returns multiple content blocks",
        "inputSchema": {
            "type": "object",
            "properties": {"count": {"type": "integer", "description": "Number of content blocks"}},
            "required": ["count"],
        },
    },
    {
        "name": "counter",
        "description": "Returns an incrementing counter value (ordering/concurrency test)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "image_tool",
        "description": "Returns a base64-encoded 1x1 red PNG image",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "annotated_tool",
        "title": "Annotated Tool",
        "description": "Tool with full annotations and outputSchema",
        "inputSchema": {"type": "object", "properties": {}},
        "outputSchema": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
        },
        "annotations": {
            "title": "Annotated Tool",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "icons": [{"type": "svg", "data": _SVG_ICON_DATA}],
    },
    {
        "name": "sampling_tool",
        "title": "Sampling Tool",
        "description": "Triggers sampling client feature",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "elicit_tool",
        "title": "Elicit Tool",
        "description": "Triggers elicitation client feature",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "async_job",
        "title": "Async Job",
        "description": "A long-running task (experimental tasks primitive)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "audio_tool",
        "title": "Audio Tool",
        "description": "Returns audio content (WAV)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "resource_result_tool",
        "title": "Resource Result Tool",
        "description": "Returns a resource content type in tool result",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "input_required_job",
        "title": "Input Required Job",
        "description": "Task that enters input_required state",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

RESOURCES = [
    {
        "uri": "test://echo",
        "name": "Echo Resource",
        "title": "Echo Text Resource",
        "description": "A static text resource",
        "mimeType": "text/plain",
        "size": 26,
    },
    {
        "uri": "test://image",
        "name": "Image Resource",
        "title": "Test Image",
        "description": "A 1x1 red PNG binary resource",
        "mimeType": "image/png",
    },
]

RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "test://data/{key}",
        "name": "Data Template",
        "description": "Dynamic key-value resource",
        "mimeType": "application/json",
    },
]

PROMPTS = [
    {
        "name": "echo_prompt",
        "title": "Echo Prompt",
        "description": "Echo prompt",
        "arguments": [
            {"name": "input", "title": "Input Text", "description": "text to echo", "required": True},
        ],
    },
    {
        "name": "code_review",
        "title": "Code Review",
        "description": "Code review prompt",
        "arguments": [
            {"name": "code", "title": "Source Code", "description": "Code to review", "required": True},
            {"name": "language", "title": "Language", "description": "Programming language", "required": False},
            {"name": "style", "title": "Review Style", "description": "Review style", "required": False},
        ],
    },
]

_COMPLETIONS = {
    "code_review": {
        "language": ["python", "javascript", "typescript", "rust", "go", "java"],
        "style": ["brief", "detailed", "security-focused"],
    },
}

_counter = 0
_counter_lock = threading.Lock()
_tasks: dict = {}
_subscriptions: set = set()
_log_level = "debug"
_cancelled_ids: set = set()

_LOG_LEVELS = ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]


_send_lock = threading.Lock()

def send(msg: dict) -> None:
    line = json.dumps(msg)
    with _send_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()



def send_response(req_id: int | str, result: dict) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "result": result})

def send_error(req_id: int | str, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})

_pending_responses: dict = {}
_pending_responses_cond = threading.Condition()

def get_next_id() -> int:
    global _counter
    with _counter_lock:
        _counter += 1
        return _counter

def send_request(method: str, params: dict) -> dict:
    req_id = get_next_id()
    send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    with _pending_responses_cond:
        if _pending_responses_cond.wait_for(lambda: req_id in _pending_responses, timeout=5.0):
            msg = _pending_responses.pop(req_id)
            if "error" in msg:
                return {}
            return msg.get("result", {})
    return {}


def send_notification(method: str, params: dict | None = None) -> None:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    send(msg)


def _level_index(level: str) -> int:
    try:
        return _LOG_LEVELS.index(level)
    except ValueError:
        return 0


def send_log(level: str, message: str, logger: str = "echo-server") -> None:
    if _level_index(level) >= _level_index(_log_level):
        send_notification("notifications/message", {
            "level": level,
            "logger": logger,
            "data": message,
        })


# ── Handlers ──────────────────────────────────────────────────────────────

def handle_initialize(req_id: int | str, _params: dict) -> None:
    send_notification("notifications/initialized", {"status": "starting"})

    send_response(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": True, "listChanged": False},
            "prompts": {"listChanged": False},
            "logging": {},
        },
        "serverInfo": SERVER_INFO,
    })


def handle_ping(req_id: int | str, _params: dict) -> None:
    send_response(req_id, {})


# ── Tools ─────────────────────────────────────────────────────────────────

TOOLS_PAGE_SIZE = 5


def handle_tools_list(req_id: int | str, params: dict) -> None:
    cursor = params.get("cursor")
    if cursor is not None:
        try:
            start = int(cursor)
        except (ValueError, TypeError):
            start = 0
    else:
        start = 0

    end = start + TOOLS_PAGE_SIZE
    page = TOOLS[start:end]
    result: dict = {"tools": page}

    if end < len(TOOLS):
        result["nextCursor"] = str(end)

    send_response(req_id, result)


def handle_tools_call(req_id: int | str, params: dict) -> None:
    global _counter

    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name == "echo":
        if "message" not in arguments:
            send_error(req_id, -32602, "Missing required argument 'message'")
            return
        if not isinstance(arguments["message"], str):
            send_error(req_id, -32602, "Invalid argument: 'message' must be a string")
            return
        message = arguments["message"]
        send_response(req_id, {
            "content": [{"type": "text", "text": message}],
        })

    elif tool_name == "slow_echo":
        message = arguments.get("message", "")
        delay = arguments.get("delay", 1)
        steps = max(1, int(delay * 2))
        progress_token = params.get("_meta", {}).get("progressToken")

        for i in range(steps):
            if req_id in _cancelled_ids:
                _cancelled_ids.discard(req_id)
                send_error(req_id, -32800, "Request cancelled")
                return
            if progress_token:
                send_notification("notifications/progress", {
                    "progressToken": progress_token,
                    "progress": i + 1,
                    "total": steps,
                    "message": f"Step {i + 1}/{steps}",
                })
            time.sleep(delay / steps)

        send_response(req_id, {
            "content": [{"type": "text", "text": message}],
        })

    elif tool_name == "error_tool":
        message = arguments.get("message", "something went wrong")
        send_response(req_id, {
            "content": [{"type": "text", "text": message}],
            "isError": True,
        })

    elif tool_name == "crash_tool":
        sys.stderr.write("CRASH: crash_tool invoked\n")
        sys.stderr.flush()
        import os
        os._exit(1)

    elif tool_name == "multi_content":
        count = arguments.get("count", 2)
        content = [{"type": "text", "text": f"block-{i}"} for i in range(count)]
        send_response(req_id, {"content": content})

    elif tool_name == "counter":
        with _counter_lock:
            _counter += 1
            val = _counter
        send_response(req_id, {
            "content": [{"type": "text", "text": str(val)}],
        })

    elif tool_name == "image_tool":
        send_response(req_id, {
            "content": [{
                "type": "image",
                "data": _1x1_RED_PNG,
                "mimeType": "image/png",
            }],
        })

    elif tool_name == "annotated_tool":
        send_response(req_id, {
            "content": [{"type": "text", "text": '{"status": "ok"}'}],
        })

    elif tool_name == "sampling_tool":
        prompt = arguments.get("prompt", "hello")
        resp = send_request("sampling/createMessage", {
            "messages": [{"role": "user", "content": {"type": "text", "text": prompt}}],
            "maxTokens": 100,
        })
        llm_text = resp.get("content", {}).get("text", "mock")
        send_response(req_id, {"content": [{"type": "text", "text": f"LLM said: {llm_text}"}]})

    elif tool_name == "elicit_tool":
        resp = send_request("elicitation/create", {
            "message": "Need user data",
            "requestedSchema": {
                "type": "object",
                "properties": {"email": {"type": "string", "format": "email"}},
                "required": ["email"],
            },
        })
        elicit_data = resp.get("data", "mock-data")
        send_response(req_id, {"content": [{"type": "text", "text": f"Got: {elicit_data}"}]})

    elif tool_name == "async_job":
        task_id = f"task-{req_id}"
        _tasks[task_id] = {"status": "working", "start": time.time()}
        send_response(req_id, {"task": {"id": task_id, "status": "working"}})

    elif tool_name == "audio_tool":
        send_response(req_id, {
            "content": [{
                "type": "audio",
                "data": _AUDIO_WAV_B64,
                "mimeType": "audio/wav",
            }],
        })

    elif tool_name == "resource_result_tool":
        send_response(req_id, {
            "content": [{
                "type": "resource",
                "resource": {
                    "uri": "test://echo",
                    "text": "Embedded resource content",
                    "mimeType": "text/plain",
                },
            }],
        })

    elif tool_name == "input_required_job":
        task_id = f"input-task-{req_id}"
        _tasks[task_id] = {
            "status": "input_required",
            "start": time.time(),
            "elicitationRequest": {
                "message": "What API key should I use?",
                "requestedSchema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            },
        }
        send_response(req_id, {
            "task": {
                "id": task_id,
                "status": "input_required",
                "elicitationRequest": _tasks[task_id]["elicitationRequest"],
            }
        })

    else:
        send_error(req_id, -32601, f"Unknown tool: {tool_name}")


# ── Tasks ─────────────────────────────────────────────────────────────────

def handle_tasks_get(req_id: int | str, params: dict) -> None:
    task_id = params.get("id")
    task = _tasks.get(task_id)
    if not task:
        send_error(req_id, -32602, "Task not found")
        return
    if task["status"] == "working" and time.time() - task.get("start", 0) > 1.0:
        task["status"] = "completed"
        task["output"] = {"result": "done"}
    response: dict = {"task": {"id": task_id, "status": task["status"]}}
    if task.get("elicitationRequest"):
        response["task"]["elicitationRequest"] = task["elicitationRequest"]
    if task.get("output"):
        response["task"]["output"] = task["output"]
    if task.get("error"):
        response["task"]["error"] = task["error"]
    send_response(req_id, response)


def handle_tasks_send_input(req_id: int | str, params: dict) -> None:
    task_id = params.get("id")
    task = _tasks.get(task_id)
    if not task:
        send_error(req_id, -32602, "Task not found")
        return
    if task["status"] != "input_required":
        send_error(req_id, -32602, "Task is not waiting for input")
        return
    input_data = params.get("input", {})
    task["status"] = "completed"
    task["output"] = {"result": "completed_with_input", "input_received": input_data}
    task.pop("elicitationRequest", None)
    send_response(req_id, {"task": {"id": task_id, "status": "completed", "output": task["output"]}})


def handle_tasks_cancel(req_id: int | str, params: dict) -> None:
    task_id = params.get("id")
    task = _tasks.get(task_id)
    if not task:
        send_error(req_id, -32602, "Task not found")
        return
    task["status"] = "cancelled"
    send_response(req_id, {"task": {"id": task_id, "status": "cancelled"}})


# ── Resources ─────────────────────────────────────────────────────────────

def handle_resources_list(req_id: int | str, _params: dict) -> None:
    send_response(req_id, {"resources": RESOURCES})


def handle_resources_read(req_id: int | str, params: dict) -> None:
    uri = params.get("uri", "")

    if uri == "test://echo":
        send_response(req_id, {
            "contents": [{
                "uri": uri,
                "mimeType": "text/plain",
                "text": "echo resource content",
            }],
        })
    elif uri == "test://image":
        send_response(req_id, {
            "contents": [{
                "uri": uri,
                "mimeType": "image/png",
                "blob": _1x1_RED_PNG,
            }],
        })
    elif uri.startswith("test://data/"):
        key = uri.replace("test://data/", "")
        send_response(req_id, {
            "contents": [{
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps({"key": key, "value": f"data-for-{key}"}),
            }],
        })
    else:
        send_error(req_id, -32602, f"Resource not found: {uri}")


def handle_resources_templates_list(req_id: int | str, _params: dict) -> None:
    send_response(req_id, {"resourceTemplates": RESOURCE_TEMPLATES})


def handle_resources_subscribe(req_id: int | str, params: dict) -> None:
    uri = params.get("uri", "")
    _subscriptions.add(uri)
    send_response(req_id, {})
    send_log("info", f"Subscribed to {uri}")


def handle_resources_unsubscribe(req_id: int | str, params: dict) -> None:
    uri = params.get("uri", "")
    _subscriptions.discard(uri)
    send_response(req_id, {})
    send_log("info", f"Unsubscribed from {uri}")


# ── Prompts ───────────────────────────────────────────────────────────────

def handle_prompts_list(req_id: int | str, _params: dict) -> None:
    send_response(req_id, {"prompts": PROMPTS})


def handle_prompts_get(req_id: int | str, params: dict) -> None:
    name = params.get("name")
    args = params.get("arguments", {})

    if name == "echo_prompt":
        send_response(req_id, {
            "description": "Echo prompt",
            "messages": [{
                "role": "user",
                "content": {"type": "text", "text": args.get("input", "")},
            }],
        })
    elif name == "code_review":
        code = args.get("code", "")
        language = args.get("language", "unknown")
        style = args.get("style", "detailed")
        send_response(req_id, {
            "description": f"Code review ({style})",
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": f"Review this {language} code:\n{code}"},
                },
                {
                    "role": "assistant",
                    "content": {"type": "text", "text": f"Code review ({style}) for {language}: looks good."},
                },
            ],
        })
    else:
        send_error(req_id, -32602, f"Prompt not found: {name}")


# ── Completion ────────────────────────────────────────────────────────────

def handle_completion_complete(req_id: int | str, params: dict) -> None:
    ref = params.get("ref", {})
    argument = params.get("argument", {})
    context = params.get("context", {})
    arg_name = argument.get("name", "")
    arg_value = argument.get("value", "")

    completions = []
    if ref.get("type") == "ref/prompt":
        prompt_name = ref.get("name", "")
        candidates = _COMPLETIONS.get(prompt_name, {}).get(arg_name, [])
        completions = [c for c in candidates if c.startswith(arg_value)]
        if context:
            completions = [f"{c} (ctx)" for c in completions]
    elif ref.get("type") == "ref/resource":
        completions = ["users", "products", "orders"]
        completions = [c for c in completions if c.startswith(arg_value)]

    send_response(req_id, {
        "completion": {
            "values": completions[:10],
            "hasMore": len(completions) > 10,
        },
    })


# ── Logging ───────────────────────────────────────────────────────────────

def handle_logging_set_level(req_id: int | str, params: dict) -> None:
    global _log_level
    _log_level = params.get("level", "debug")
    send_response(req_id, {})
    send_log("info", f"Log level set to {_log_level}")


# ── Notification handling (from client) ───────────────────────────────────

def handle_notification(method: str, params: dict) -> None:
    if method == "notifications/cancelled":
        request_id = params.get("requestId")
        if request_id is not None:
            _cancelled_ids.add(request_id)
    elif method == "notifications/initialized":
        pass


# ── Dispatch table ────────────────────────────────────────────────────────

HANDLERS = {
    "initialize": handle_initialize,
    "ping": handle_ping,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "tasks/get": handle_tasks_get,
    "tasks/sendInput": handle_tasks_send_input,
    "tasks/cancel": handle_tasks_cancel,
    "resources/list": handle_resources_list,
    "resources/read": handle_resources_read,
    "resources/templates/list": handle_resources_templates_list,
    "resources/subscribe": handle_resources_subscribe,
    "resources/unsubscribe": handle_resources_unsubscribe,
    "prompts/list": handle_prompts_list,
    "prompts/get": handle_prompts_get,
    "completion/complete": handle_completion_complete,
    "logging/setLevel": handle_logging_set_level,
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue

        if isinstance(msg, list):
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Batch requests not supported (spec 2025-06-18)"}})
            continue

        method = msg.get("method")
        req_id = msg.get("id")

        if req_id is not None and ("result" in msg or "error" in msg):
            with _pending_responses_cond:
                _pending_responses[req_id] = msg
                _pending_responses_cond.notify_all()
            continue

        if req_id is None:
            if method:
                handle_notification(method, msg.get("params", {}))
            continue

        handler = HANDLERS.get(method)
        if handler:
            threading.Thread(target=handler, args=(req_id, msg.get("params", {})), daemon=True).start()
        else:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
