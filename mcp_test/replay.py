from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class WireTraceReplay:
    """Deterministic fake-response lookup keyed off a recorded wire trace.

    Use this to replay a captured live session in a hermetic test:

        replay = WireTraceReplay("traces/run.jsonl")
        response = replay.response_for("tools/call")  # next recorded response

    Each call consumes one response so iteration order matches the recording.
    """

    def __init__(self, trace_path: str | Path):
        self.trace_path = Path(trace_path)
        self._responses = self._load_responses()

    def response_for(self, method: str) -> dict[str, Any]:
        responses = self._responses.get(method) or []
        if not responses:
            raise KeyError(f"No recorded response for {method!r}")
        return responses.pop(0)

    def _load_responses(self) -> dict[str, list[dict[str, Any]]]:
        pending: dict[Any, str] = {}
        responses: dict[str, list[dict[str, Any]]] = {}
        for line in self.trace_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines rather than aborting replay; live traces
                # can include partial writes when a process is killed.
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            if entry.get("direction") == "out" and "method" in message and "id" in message:
                pending[message["id"]] = message["method"]
            elif entry.get("direction") == "in" and "id" in message:
                method = pending.get(message["id"])
                if method:
                    responses.setdefault(method, []).append(message)
        return responses
