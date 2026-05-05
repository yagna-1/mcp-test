from __future__ import annotations

from contextlib import nullcontext
from typing import Any


class MCPTracer:
    """Small optional OpenTelemetry facade used by clients and tests."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._tracer: Any = None
        if enabled:
            try:
                from opentelemetry import trace

                self._tracer = trace.get_tracer("mcp_test")
            except Exception:
                self._tracer = None

    def span(
        self,
        method: str,
        *,
        session_id: str = "",
        protocol_version: str = "",
    ):
        if self._tracer is None:
            return nullcontext()
        return self._tracer.start_as_current_span(
            f"mcp.{method}",
            attributes={
                "mcp.method": method,
                "mcp.session_id": session_id,
                "mcp.protocol_version": protocol_version,
            },
        )
