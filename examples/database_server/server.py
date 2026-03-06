#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from typing import Any


DB: dict[str, list[dict[str, Any]]] = {
    "users": [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ],
    "products": [
        {"id": 1, "name": "Widget", "price": 9.99},
        {"id": 2, "name": "Gadget", "price": 24.99},
    ],
}

TOOLS = [
    {
        "name": "list_tables",
        "description": "List all available tables",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "query",
        "description": "Query records from a table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "filter_field": {"type": "string", "description": "Field to filter by (optional)"},
                "filter_value": {"type": "string", "description": "Value to filter for (optional)"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "insert",
        "description": "Insert a record into a table",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "record": {"type": "object", "description": "Record to insert"},
            },
            "required": ["table", "record"],
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
        "serverInfo": {"name": "database-server", "version": "1.0.0"},
    })


def handle_tools_list(req_id, _params):
    send_response(req_id, {"tools": TOOLS})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name == "list_tables":
        tables = list(DB.keys())
        send_response(req_id, {"content": [{"type": "text", "text": json.dumps(tables)}]})

    elif tool_name == "query":
        table = args.get("table", "")
        if table not in DB:
            send_response(req_id, {
                "content": [{"type": "text", "text": f"Table not found: {table}"}],
                "isError": True,
            })
            return
        records = DB[table]
        filter_field = args.get("filter_field")
        filter_value = args.get("filter_value")
        if filter_field and filter_value:
            records = [r for r in records if str(r.get(filter_field)) == str(filter_value)]
        send_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(records, indent=2)}],
        })

    elif tool_name == "insert":
        table = args.get("table", "")
        record = args.get("record", {})
        if table not in DB:
            send_response(req_id, {
                "content": [{"type": "text", "text": f"Table not found: {table}"}],
                "isError": True,
            })
            return
        DB[table].append(record)
        send_response(req_id, {
            "content": [{"type": "text", "text": f"Inserted record into {table}. Total: {len(DB[table])}"}],
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
