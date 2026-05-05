#!/usr/bin/env python3
"""API-wrapper MCP server demo (stdio).

Wraps a make-believe upstream "weather" API. Demonstrates the security
posture every API-wrapper MCP server should take:

* Required credentials are read from the ``API_KEY`` environment variable.
  When unset, every authenticated tool returns an explicit error rather than
  silently calling upstream anonymously.
* Tool outputs never echo the API key back, even on error paths — common
  failure mode in servers that forward upstream error bodies wholesale.
* No retry loops on user-controlled error paths; one upstream attempt and
  return whatever happened.

Run::

    API_KEY=secret-12345 python server.py
"""

from __future__ import annotations

import json
import os
import sys


WEATHER_DB = {
    "london": {"temp": 12, "condition": "cloudy"},
    "tokyo": {"temp": 22, "condition": "sunny"},
    "new york": {"temp": 18, "condition": "partly cloudy"},
}

TOOLS = [
    {
        "name": "get_current_weather",
        "description": (
            "Get current weather for a city. Requires API_KEY environment "
            "variable to be set on the server."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "ping",
        "description": "Health check that does not require credentials.",
        "inputSchema": {"type": "object", "properties": {}},
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


def handle_initialize(req_id, _params):
    send_response(req_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "api-wrapper-server", "version": "1.0.0"},
    })


def handle_tools_list(req_id, _params):
    send_response(req_id, {"tools": TOOLS})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name == "ping":
        send_response(req_id, {"content": [{"type": "text", "text": "pong"}]})
        return

    if tool_name == "get_current_weather":
        api_key = os.environ.get("API_KEY", "")
        if not api_key:
            # Crucial: do NOT include any partial-key info in this message.
            _tool_error(
                req_id,
                "API key not configured on this server "
                "(set the API_KEY environment variable to enable this tool)",
            )
            return
        city = args.get("city", "").lower()
        weather = WEATHER_DB.get(city)
        if not weather:
            _tool_error(req_id, f"city not found: {city!r}")
            return
        # Note: we never include the API key in the response, even though
        # the upstream "would" return rate-limit info that mentions it.
        text = (
            f"Weather in {city.title()}: "
            f"{weather['temp']}°C, {weather['condition']}"
        )
        send_response(req_id, {"content": [{"type": "text", "text": text}]})
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
