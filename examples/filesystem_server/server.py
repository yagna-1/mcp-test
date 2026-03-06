#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys


TOOLS = [
    {
        "name": "list_files",
        "description": "List files in a directory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
]


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_response(req_id, result: dict) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "result": result})


def send_error(req_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


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
    base_dir = os.environ.get("DATA_DIR", ".")

    if tool_name == "list_files":
        path = os.path.join(base_dir, args.get("path", "."))
        try:
            files = os.listdir(path)
            send_response(req_id, {
                "content": [{"type": "text", "text": "\n".join(sorted(files))}],
            })
        except OSError as e:
            send_response(req_id, {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            })

    elif tool_name == "read_file":
        path = os.path.join(base_dir, args.get("path", ""))
        try:
            with open(path) as f:
                content = f.read()
            send_response(req_id, {
                "content": [{"type": "text", "text": content}],
            })
        except OSError as e:
            send_response(req_id, {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            })

    elif tool_name == "write_file":
        path = os.path.join(base_dir, args.get("path", ""))
        content = args.get("content", "")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
            with open(path, "w") as f:
                f.write(content)
            send_response(req_id, {
                "content": [{"type": "text", "text": f"Wrote {len(content)} bytes to {path}"}],
            })
        except OSError as e:
            send_response(req_id, {
                "content": [{"type": "text", "text": str(e)}],
                "isError": True,
            })
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
        req_id = msg.get("id")
        if req_id is None:
            continue
        handler = HANDLERS.get(msg.get("method"))
        if handler:
            handler(req_id, msg.get("params", {}))
        else:
            send_error(req_id, -32601, f"Method not found: {msg.get('method')}")


if __name__ == "__main__":
    main()
