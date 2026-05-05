#!/usr/bin/env python3
"""Allowlist-based shell-exec MCP server (stdio).

Demonstrates the security stance every shell-exec MCP server should take:

* The set of executable commands is hard-coded at startup; no command
  outside the allowlist runs, period.
* Arguments are passed via ``execvp`` (no shell), so metacharacters like
  ``;`` ``&&`` ``|`` ``$()`` ``\``\`` are inert — they're literal characters
  to the executed binary.
* Non-zero exit codes are surfaced explicitly in the tool result.

Run::

    python server.py
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys


# Hard-coded allowlist. Each entry is the *command name* the LLM can request.
ALLOWED_COMMANDS: dict[str, list[str]] = {
    "echo": ["echo"],
    "uname": ["uname", "-a"],
    "true": ["true"],
    "false": ["false"],
}


TOOLS = [
    {
        "name": "run_command",
        "description": (
            "Run a command from the server's allowlist. The command string is "
            "split with shlex; only the first token is used as the command "
            "name (looked up in the allowlist). All remaining tokens are "
            "passed as positional arguments via execvp — no shell involved."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command + arguments to run. e.g. 'echo hello'",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "list_allowed",
        "description": "List the command names this server is willing to run.",
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
        "serverInfo": {"name": "shell-exec-server", "version": "1.0.0"},
    })


def handle_tools_list(req_id, _params):
    send_response(req_id, {"tools": TOOLS})


def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    args = params.get("arguments", {})

    if tool_name == "list_allowed":
        send_response(req_id, {
            "content": [{"type": "text", "text": json.dumps(sorted(ALLOWED_COMMANDS))}],
        })
        return

    if tool_name == "run_command":
        command = args.get("command", "")
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError as e:
            _tool_error(req_id, f"unparseable command: {e}")
            return
        if not tokens:
            _tool_error(req_id, "empty command")
            return
        cmd_name = tokens[0]
        if cmd_name not in ALLOWED_COMMANDS:
            _tool_error(
                req_id,
                f"command not allowed: {cmd_name!r} "
                f"(allowed: {sorted(ALLOWED_COMMANDS)})",
            )
            return
        argv = ALLOWED_COMMANDS[cmd_name] + tokens[1:]
        try:
            proc = subprocess.run(  # noqa: S603 — argv is built from allowlist
                argv,
                capture_output=True,
                text=True,
                timeout=5.0,
                shell=False,  # critical: never use a shell
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            _tool_error(req_id, f"command failed: {e}")
            return
        if proc.returncode != 0:
            _tool_error(
                req_id,
                f"command exited with non-zero status: exit code {proc.returncode}\n"
                f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}",
            )
            return
        send_response(req_id, {
            "content": [{"type": "text", "text": proc.stdout.rstrip("\n")}],
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
