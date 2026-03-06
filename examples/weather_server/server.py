#!/usr/bin/env python3

from __future__ import annotations

import json
import sys

WEATHER_DB = {
    "london": {"temp": 12, "condition": "cloudy", "humidity": 78},
    "tokyo": {"temp": 22, "condition": "sunny", "humidity": 55},
    "new york": {"temp": 18, "condition": "partly cloudy", "humidity": 62},
    "paris": {"temp": 15, "condition": "rainy", "humidity": 85},
}

TOOLS = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_forecast",
        "description": "Get multi-day weather forecast",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
                "days": {"type": "integer", "description": "Number of forecast days (1-7)"},
            },
            "required": ["city", "days"],
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
        "serverInfo": {"name": "weather-server", "version": "1.0.0"},
    })


def handle_tools_list(req_id, _params):
    send_response(req_id, {"tools": TOOLS})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name == "get_weather":
        city = args.get("city", "").lower()
        weather = WEATHER_DB.get(city)
        if not weather:
            send_response(req_id, {
                "content": [{"type": "text", "text": f"City not found: {city}"}],
                "isError": True,
            })
            return
        text = f"Weather in {city.title()}: {weather['temp']}°C, {weather['condition']}, humidity {weather['humidity']}%"
        send_response(req_id, {"content": [{"type": "text", "text": text}]})

    elif tool_name == "get_forecast":
        city = args.get("city", "").lower()
        days = args.get("days", 3)
        weather = WEATHER_DB.get(city)
        if not weather:
            send_response(req_id, {
                "content": [{"type": "text", "text": f"City not found: {city}"}],
                "isError": True,
            })
            return
        if days < 1 or days > 7:
            send_response(req_id, {
                "content": [{"type": "text", "text": "Days must be between 1 and 7"}],
                "isError": True,
            })
            return
        lines = [f"Forecast for {city.title()} ({days} days):"]
        for i in range(days):
            temp_offset = (i * 2 - days) % 5
            lines.append(f"  Day {i+1}: {weather['temp'] + temp_offset}°C, {weather['condition']}")
        send_response(req_id, {"content": [{"type": "text", "text": "\n".join(lines)}]})

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
