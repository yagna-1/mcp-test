"""Bundled HTTP MCP demo server for `mcp-test` conformance / HTTP tests.

Boots a small FastMCP-backed Streamable-HTTP MCP server on the port given by
``MCP_TEST_DEMO_PORT`` (default 8765). The tools mirror the stdio demo so the
same scenarios can run against either transport.

Run directly::

    python -m mcp_test._demo_server_http
    # or
    MCP_TEST_DEMO_PORT=9000 python -m mcp_test._demo_server_http

Requires the ``fastmcp`` extra::

    pip install 'pytest-mcp-plugin[fastmcp]'
"""

from __future__ import annotations

import os
import sys


def _import_fastmcp():
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        sys.stderr.write(
            "fastmcp is required to run the HTTP demo server. "
            "Install with: pip install 'pytest-mcp-plugin[fastmcp]'\n"
        )
        raise SystemExit(2) from exc
    return FastMCP


def build_app(name: str = "mcptest-demo-http"):
    FastMCP = _import_fastmcp()
    app = FastMCP(name)

    @app.tool()
    def echo(message: str) -> str:
        """Return the given message verbatim."""
        return message

    @app.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @app.tool()
    def uppercase(text: str) -> str:
        """Uppercase the given string."""
        return text.upper()

    @app.tool()
    def fail() -> str:
        """Always raises — useful for testing error handling."""
        raise RuntimeError("intentional failure")

    return app


def main() -> None:
    port = int(os.environ.get("MCP_TEST_DEMO_PORT", "8765"))
    host = os.environ.get("MCP_TEST_DEMO_HOST", "127.0.0.1")
    app = build_app()
    app.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
