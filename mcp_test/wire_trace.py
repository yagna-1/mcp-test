from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


class WireTrace:
    """Thread-safe JSONL recorder for MCP wire events."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_recent: int = 200,
    ) -> None:
        self._path = Path(path) if path else None
        self._recent: deque[dict[str, Any]] = deque(maxlen=max_recent)
        self._lock = threading.Lock()
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text("")

    @property
    def path(self) -> Path | None:
        return self._path

    def record(
        self,
        direction: str,
        *,
        message: dict[str, Any] | None = None,
        method: str | None = None,
        request_id: int | str | None = None,
        transport: str = "stdio",
        event: str = "jsonrpc",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": time.time(),
            "transport": transport,
            "direction": direction,
            "event": event,
        }
        if method:
            entry["method"] = method
        if request_id is not None:
            entry["id"] = request_id
        if message is not None:
            entry["message"] = message
        if metadata:
            entry["metadata"] = metadata

        encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self._recent.append(entry)
            if self._path:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(encoded + "\n")

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent)

    def dump_to(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            lines = [
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in self._recent
            ]
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return target

    def format_recent(self, limit: int = 12) -> str:
        items = self.recent()[-limit:]
        if not items:
            return "(empty)"
        return "\n".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            for item in items
        )
