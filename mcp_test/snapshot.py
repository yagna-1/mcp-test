
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from .types import ToolResult


SNAPSHOT_DIR = ".mcp_snapshots"


def _normalize(data: Any, ignore_keys: list[str] | None = None, sort_arrays: bool = False) -> Any:
    if isinstance(data, dict):
        result = {}
        for k, v in sorted(data.items()):
            if ignore_keys and k in ignore_keys:
                result[k] = "<IGNORED>"
            else:
                result[k] = _normalize(v, ignore_keys=ignore_keys, sort_arrays=sort_arrays)
        return result
    elif isinstance(data, list):
        normalized = [_normalize(item, ignore_keys=ignore_keys, sort_arrays=sort_arrays) for item in data]
        if sort_arrays:
            try:
                normalized = sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True, default=str))
            except TypeError:
                pass
        return normalized
    else:
        return data


def _to_serializable(result: ToolResult) -> dict:
    return {
        "content": [
            {
                "type": c.type,
                "text": c.text,
                "data": c.data,
                "mime_type": c.mime_type,
                "uri": c.uri,
            }
            for c in result.content
        ],
        "is_error": result.is_error_result,
    }


class SnapshotMismatch(AssertionError):
    """Raised when a snapshot doesn't match the current output."""

    def __init__(self, snapshot_path: str, expected: Any, actual: Any):
        self.snapshot_path = snapshot_path
        self.expected = expected
        self.actual = actual

        expected_str = json.dumps(expected, indent=2, default=str)
        actual_str = json.dumps(actual, indent=2, default=str)
        super().__init__(
            f"Snapshot mismatch in {snapshot_path}\n\n"
            f"Expected (saved):\n{expected_str}\n\n"
            f"Actual (current):\n{actual_str}\n\n"
            f"To update, run: mcp-test snapshot --update"
        )


class Snapshot:
    """Snapshot testing context for a single test."""

    def __init__(self, snapshot_dir: Path, test_name: str, update: bool = False):
        self._dir = snapshot_dir
        self._test_name = test_name
        self._update = update
        self._counter = 0

    def _snapshot_path(self) -> Path:
        name = self._test_name
        if self._counter > 0:
            name = f"{name}_{self._counter}"
        self._counter += 1
        return self._dir / f"{name}.json"

    def assert_match(
        self,
        result: ToolResult | dict | Any,
        *,
        ignore_keys: list[str] | None = None,
        sort_arrays: bool = False,
    ) -> None:
        if isinstance(result, ToolResult):
            data = _to_serializable(result)
        elif isinstance(result, dict):
            data = result
        else:
            data = {"value": result}

        normalized = _normalize(data, ignore_keys=ignore_keys, sort_arrays=sort_arrays)
        path = self._snapshot_path()

        if self._update or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(normalized, indent=2, default=str) + "\n")
            return

        saved = json.loads(path.read_text())
        if saved != normalized:
            raise SnapshotMismatch(str(path), saved, normalized)


@pytest.fixture
def snapshot(request, tmp_path):
    test_file = Path(request.fspath)
    snap_dir = test_file.parent / SNAPSHOT_DIR

    test_name = request.node.name

    update = request.config.getoption("--snapshot-update", default=False)

    return Snapshot(snap_dir, test_name, update=update)


def pytest_addoption(parser):
    try:
        parser.addoption(
            "--snapshot-update",
            action="store_true",
            default=False,
            help="Update MCP test snapshots instead of comparing",
        )
    except ValueError:
        pass
