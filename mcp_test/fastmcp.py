from __future__ import annotations

import asyncio
from typing import Any

from .types import ToolList, ToolResult


class FastMCPHarness:
    """In-process test harness for FastMCP apps.

    The adapter intentionally imports FastMCP lazily so pytest-mcp-plugin does
    not require FastMCP for users who only test subprocess servers.
    """

    def __init__(self, app: Any):
        self.app = app
        self._client: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> "FastMCPHarness":
        try:
            from fastmcp import Client
        except ImportError as exc:
            raise RuntimeError("Install fastmcp to use FastMCPHarness") from exc

        self._loop = asyncio.new_event_loop()
        self._client = Client(self.app)
        self._loop.run_until_complete(self._client.__aenter__())
        return self

    def close(self) -> None:
        if self._client is not None and self._loop is not None:
            self._loop.run_until_complete(self._client.__aexit__(None, None, None))
        if self._loop is not None:
            self._loop.close()
        self._client = None
        self._loop = None

    def __enter__(self) -> "FastMCPHarness":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.close()

    def list_tools(self) -> ToolList:
        raw = self._run(self._client.list_tools())
        return ToolList.from_response({"result": {"tools": [_dump(item) for item in raw]}})

    def call_tool(self, name: str, **arguments: Any) -> ToolResult:
        raw = self._run(self._client.call_tool(name, arguments))
        return ToolResult.from_response(_normalize_tool_result(raw))

    def _run(self, awaitable: Any) -> Any:
        if self._loop is None:
            raise RuntimeError("FastMCPHarness is not started")
        return self._loop.run_until_complete(awaitable)


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True, exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _normalize_tool_result(raw: Any) -> dict[str, Any]:
    data = _dump(raw)
    if isinstance(data, dict) and "jsonrpc" in data:
        return data
    if isinstance(data, dict) and "content" in data:
        return {"jsonrpc": "2.0", "id": 0, "result": data}
    if isinstance(data, list):
        return {"jsonrpc": "2.0", "id": 0, "result": {"content": data}}
    return {
        "jsonrpc": "2.0",
        "id": 0,
        "result": {"content": [{"type": "text", "text": str(data)}]},
    }
