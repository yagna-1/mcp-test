"""Bundled demo MCP server for `mcp-test demo`.

A zero-dependency stdio MCP server with a handful of tools so users can
try `pytest-mcp-plugin` end-to-end in seconds without writing their own server first.
Speaks JSON-RPC 2.0 over stdio per the MCP spec.

Run directly:

    python -m mcp_test._demo_server
"""

from __future__ import annotations

import json
import sys
from typing import Any

SERVER_NAME = "mcptest-demo"
SERVER_VERSION = "0.3.0"
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "echo",
        "description": "Return the given message verbatim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Text to echo"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "add",
        "description": "Add two integers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "uppercase",
        "description": "Uppercase the given string.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "fail",
        "description": "Always returns an error result. Useful for testing assert_tool_error.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(req_id: Any, result: dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: Any, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _text_result(text: str, is_error: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        out["isError"] = True
    return out


def _handle_initialize(req_id: Any, _params: dict[str, Any]) -> None:
    _ok(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def _handle_tools_list(req_id: Any, _params: dict[str, Any]) -> None:
    _ok(req_id, {"tools": TOOLS})


def _handle_tools_call(req_id: Any, params: dict[str, Any]) -> None:
    name = params.get("name", "")
    args = params.get("arguments") or {}

    if name == "echo":
        _ok(req_id, _text_result(str(args.get("message", ""))))
        return

    if name == "add":
        try:
            total = int(args["a"]) + int(args["b"])
        except (KeyError, TypeError, ValueError):
            _ok(req_id, _text_result("add requires integer 'a' and 'b'", is_error=True))
            return
        _ok(req_id, _text_result(str(total)))
        return

    if name == "uppercase":
        text = args.get("text")
        if not isinstance(text, str):
            _ok(req_id, _text_result("uppercase requires string 'text'", is_error=True))
            return
        _ok(req_id, _text_result(text.upper()))
        return

    if name == "fail":
        _ok(req_id, _text_result("intentional failure", is_error=True))
        return

    _err(req_id, -32601, f"Unknown tool: {name}")


_HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        req_id = msg.get("id")

        if req_id is None:
            continue

        handler = _HANDLERS.get(method)
        if handler is None:
            _err(req_id, -32601, f"Method not found: {method}")
            continue

        handler(req_id, msg.get("params") or {})


if __name__ == "__main__":
    main()
