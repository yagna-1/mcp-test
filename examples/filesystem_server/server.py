#!/usr/bin/env python3
"""Sandbox-safe filesystem MCP server (stdio).

This is a reference implementation that demonstrates the security checks
required to pass `mcp_test.test_packs.FilesystemServerTests`. The sandbox
root is taken from the `DATA_DIR` environment variable (default: cwd) and
all paths are resolved + checked to ensure they don't escape it.

Run::

    DATA_DIR=/tmp/sandbox python server.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


TOOLS = [
    {
        "name": "list_files",
        "description": "List files in a directory inside the sandbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path, relative to DATA_DIR"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file inside the sandbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, relative to DATA_DIR"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a file inside the sandbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path, relative to DATA_DIR"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
]


def _sandbox_root() -> Path:
    return Path(os.environ.get("DATA_DIR", ".")).resolve()


def _resolve_inside_sandbox(path: str) -> Path:
    """Resolve `path` relative to the sandbox; raise on escape attempts.

    Rejects:
      * absolute paths (Unix `/foo`, Windows `C:\\`)
      * any path that resolves outside the sandbox root after symlink resolution
    """
    if not path:
        raise PermissionError("empty path")
    p_str = str(path)
    if p_str.startswith(("/", "\\")) or (len(p_str) > 1 and p_str[1] == ":"):
        raise PermissionError(f"absolute paths are not permitted: {p_str!r}")

    root = _sandbox_root()
    candidate = (root / p_str).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"path escapes sandbox: {p_str!r}") from exc
    return candidate


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_response(req_id, result: dict) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def send_error(req_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _tool_error(req_id, message: str) -> None:
    send_response(req_id, {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    })


def handle_initialize(req_id, _params):
    send_response(req_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "filesystem-server", "version": "1.0.0"},
    })


def handle_tools_list(req_id, _params):
    send_response(req_id, {"tools": TOOLS})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name == "list_files":
        try:
            target = _resolve_inside_sandbox(args.get("path", "."))
        except PermissionError as e:
            _tool_error(req_id, f"sandbox violation: {e}")
            return
        try:
            files = sorted(os.listdir(target))
            send_response(req_id, {
                "content": [{"type": "text", "text": "\n".join(files)}],
            })
        except OSError as e:
            _tool_error(req_id, str(e))

    elif tool_name == "read_file":
        try:
            target = _resolve_inside_sandbox(args.get("path", ""))
        except PermissionError as e:
            _tool_error(req_id, f"sandbox violation: {e}")
            return
        try:
            content = target.read_text()
            send_response(req_id, {
                "content": [{"type": "text", "text": content}],
            })
        except OSError as e:
            _tool_error(req_id, str(e))

    elif tool_name == "write_file":
        try:
            target = _resolve_inside_sandbox(args.get("path", ""))
        except PermissionError as e:
            _tool_error(req_id, f"sandbox violation: {e}")
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(args.get("content", ""))
            send_response(req_id, {
                "content": [{
                    "type": "text",
                    "text": f"Wrote {len(args.get('content', ''))} bytes to {target.name}",
                }],
            })
        except OSError as e:
            _tool_error(req_id, str(e))

    else:
        send_error(req_id, -32601, f"Unknown tool: {tool_name}")


HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method", "")
        # Notifications (no id) — ignore but don't crash.
        if "id" not in msg:
            continue
        req_id = msg["id"]
        handler = HANDLERS.get(method)
        if handler:
            handler(req_id, msg.get("params", {}))
        else:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
