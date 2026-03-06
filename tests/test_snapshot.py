
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from mcp_test import make_client, ToolResult, Content
from mcp_test.snapshot import Snapshot, SnapshotMismatch, _normalize

ECHO_SERVER = os.path.join(os.path.dirname(__file__), "fixtures", "echo_server.py")
SERVER_CMD = f"{sys.executable} {ECHO_SERVER}"


def test_normalize_sorts_dict_keys():
    data = {"z": 1, "a": 2, "m": 3}
    result = _normalize(data)
    assert list(result.keys()) == ["a", "m", "z"]


def test_normalize_ignores_keys():
    data = {"name": "test", "timestamp": "2026-01-01", "id": "abc123"}
    result = _normalize(data, ignore_keys=["timestamp", "id"])
    assert result["timestamp"] == "<IGNORED>"
    assert result["id"] == "<IGNORED>"
    assert result["name"] == "test"


def test_normalize_sorts_arrays():
    data = [{"name": "c"}, {"name": "a"}, {"name": "b"}]
    result = _normalize(data, sort_arrays=True)
    assert result[0]["name"] == "a"
    assert result[1]["name"] == "b"
    assert result[2]["name"] == "c"


def test_normalize_nested():
    data = {
        "outer": {
            "inner": {"ts": "2026-01-01", "value": 42},
            "list": [3, 1, 2],
        }
    }
    result = _normalize(data, ignore_keys=["ts"], sort_arrays=True)
    assert result["outer"]["inner"]["ts"] == "<IGNORED>"
    assert result["outer"]["inner"]["value"] == 42
    assert result["outer"]["list"] == [1, 2, 3]


def test_snapshot_first_run_saves(tmp_path):
    snap = Snapshot(tmp_path / "snaps", "test_first_run")
    result = ToolResult(
        content=[Content(type="text", text="hello")],
        is_error_result=False,
        raw={},
    )
    snap.assert_match(result)
    snap_file = tmp_path / "snaps" / "test_first_run.json"
    assert snap_file.exists()
    saved = json.loads(snap_file.read_text())
    assert saved["content"][0]["text"] == "hello"


def test_snapshot_match_passes(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap1 = Snapshot(snap_dir, "test_match")
    result = ToolResult(
        content=[Content(type="text", text="hello")],
        is_error_result=False,
        raw={},
    )
    snap1.assert_match(result)

    snap2 = Snapshot(snap_dir, "test_match")
    snap2.assert_match(result)


def test_snapshot_mismatch_raises(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap1 = Snapshot(snap_dir, "test_mismatch")
    result1 = ToolResult(
        content=[Content(type="text", text="hello")],
        is_error_result=False,
        raw={},
    )
    snap1.assert_match(result1)

    result2 = ToolResult(
        content=[Content(type="text", text="changed!")],
        is_error_result=False,
        raw={},
    )
    snap2 = Snapshot(snap_dir, "test_mismatch")
    with pytest.raises(SnapshotMismatch, match="Snapshot mismatch"):
        snap2.assert_match(result2)


def test_snapshot_update_overwrites(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap1 = Snapshot(snap_dir, "test_update")
    result1 = ToolResult(
        content=[Content(type="text", text="old")],
        is_error_result=False,
        raw={},
    )
    snap1.assert_match(result1)

    result2 = ToolResult(
        content=[Content(type="text", text="new")],
        is_error_result=False,
        raw={},
    )
    snap2 = Snapshot(snap_dir, "test_update", update=True)
    snap2.assert_match(result2)

    saved = json.loads((snap_dir / "test_update.json").read_text())
    assert saved["content"][0]["text"] == "new"


def test_snapshot_with_ignore_keys(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap1 = Snapshot(snap_dir, "test_ignore")
    data1 = {"name": "test", "timestamp": "2026-01-01"}
    snap1.assert_match(data1, ignore_keys=["timestamp"])

    snap2 = Snapshot(snap_dir, "test_ignore")
    data2 = {"name": "test", "timestamp": "2026-12-31"}
    snap2.assert_match(data2, ignore_keys=["timestamp"])


def test_snapshot_with_real_server(tmp_path):
    with make_client(SERVER_CMD, timeout=5.0) as client:
        result = client.call_tool("echo", message="snapshot_test")
        snap = Snapshot(tmp_path / "snaps", "test_real")
        snap.assert_match(result)

        result2 = client.call_tool("echo", message="snapshot_test")
        snap2 = Snapshot(tmp_path / "snaps", "test_real")
        snap2.assert_match(result2)
