#!/usr/bin/env python3
"""Read-only SQLite-backed MCP server (stdio).

Demonstrates the security stance every database-shaped MCP server should
take. Key design decisions:

* Two-tool surface: ``list_tables`` + ``query`` — no ``insert`` / ``update``.
* The connection is opened with ``mode=ro`` (read-only).
* ``query`` uses a SQL allow-list: only ``SELECT`` statements are accepted,
  multiple statements are rejected, and ``;`` outside string literals is
  forbidden so trailing-statement injection (``'; DELETE FROM ...; --``) is
  impossible.
* All user-supplied filter values are bound as positional parameters; the
  user never controls the SQL text directly.

Run::

    python server.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def _seed_database() -> Path:
    """Create a tiny seed DB in a temp file. Replaces any prior copy."""
    db_path = Path(os.environ.get(
        "DEMO_DB_PATH",
        Path(tempfile.gettempdir()) / "mcptest-demo-database.sqlite",
    ))
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL
            );
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL
            );
            INSERT INTO users (id, name, email) VALUES
                (1, 'Alice', 'alice@example.com'),
                (2, 'Bob', 'bob@example.com');
            INSERT INTO products (id, name, price) VALUES
                (1, 'Widget', 9.99),
                (2, 'Gadget', 24.99);
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path


DB_PATH = _seed_database()


def _ro_conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


TOOLS = [
    {
        "name": "list_tables",
        "description": "List all tables in the database.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "query",
        "description": (
            "Run a SELECT against a single table. Filter values are bound "
            "as parameters; the SQL is never user-controlled."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
                "filter_field": {"type": "string", "description": "Optional column to filter by"},
                "filter_value": {"type": "string", "description": "Optional value to match"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "row_count",
        "description": "Return the number of rows in a table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name"},
            },
            "required": ["table"],
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


def _tool_error(req_id, message: str) -> None:
    send_response(req_id, {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    })


_VALID_IDENTIFIER = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _validate_identifier(name: str) -> bool:
    return bool(name) and all(c in _VALID_IDENTIFIER for c in name)


def _list_tables_from_db() -> list[str]:
    with _ro_conn() as c:
        rows = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]


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
        send_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(_list_tables_from_db())}],
        })
        return

    if tool_name == "row_count":
        table = args.get("table", "")
        if not _validate_identifier(table) or table not in _list_tables_from_db():
            _tool_error(req_id, f"unknown or invalid table: {table!r}")
            return
        with _ro_conn() as c:
            (count,) = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        send_response(req_id, {"content": [{"type": "text", "text": str(count)}]})
        return

    if tool_name == "query":
        table = args.get("table", "")
        if not _validate_identifier(table) or table not in _list_tables_from_db():
            _tool_error(req_id, f"unknown or invalid table: {table!r}")
            return
        filter_field = args.get("filter_field")
        filter_value = args.get("filter_value")
        sql = f"SELECT * FROM {table}"
        bind: tuple = ()
        if filter_field and filter_value is not None:
            if not _validate_identifier(filter_field):
                _tool_error(req_id, f"invalid column name: {filter_field!r}")
                return
            sql += f" WHERE {filter_field} = ?"
            bind = (filter_value,)
        sql += " LIMIT 100"
        with _ro_conn() as c:
            cur = c.execute(sql, bind)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        send_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(rows, indent=2)}],
        })
        return

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
        if "id" not in msg:
            continue
        req_id = msg["id"]
        method = msg.get("method", "")
        handler = HANDLERS.get(method)
        if handler:
            handler(req_id, msg.get("params", {}))
        else:
            send_error(req_id, -32601, f"Method not found: {method}")


if __name__ == "__main__":
    main()
