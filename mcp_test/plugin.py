
from __future__ import annotations

import os
import re

import pytest

from .client import make_client
from .runner import discover_method_timeouts
from .snapshot import Snapshot, SNAPSHOT_DIR
from .timeouts import parse_timeout_overrides
from .types import SPEC_VERSIONS

from pathlib import Path

_VERSION_MARKERS = {
    "mcp_v2": 2,
    "mcp_v3": 3,
    "mcp_v4": 4,
}


def pytest_addoption(parser):
    group = parser.getgroup("mcp-test", "MCP server testing")
    group.addoption(
        "--mcp-command",
        action="store",
        default=None,
        help="Command to start the MCP server (e.g. 'python my_server.py')",
    )
    group.addoption(
        "--mcp-timeout",
        action="store",
        type=float,
        default=10.0,
        help="Default timeout for MCP requests in seconds (default: 10)",
    )
    group.addoption(
        "--mcp-timeout-method",
        action="append",
        default=[],
        metavar="METHOD=SECONDS",
        help="Override timeout for a JSON-RPC method; may be passed multiple times",
    )
    group.addoption(
        "--mcp-smart-timeouts",
        action="store_true",
        default=False,
        help="Use built-in method-family timeouts when no explicit timeout exists",
    )
    group.addoption(
        "--mcp-trace",
        action="store",
        default=None,
        help="Write MCP wire trace JSONL to this path",
    )
    group.addoption(
        "--mcp-live-stderr",
        action="store_true",
        default=False,
        help="Stream MCP server stderr live while tests run",
    )
    group.addoption(
        "--snapshot-update",
        action="store_true",
        default=False,
        help="Update MCP test snapshots instead of comparing",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "mcp_v2: test requires spec >= 2025-03-26")
    config.addinivalue_line("markers", "mcp_v3: test requires spec >= 2025-06-18")
    config.addinivalue_line("markers", "mcp_v4: test requires spec >= 2025-11-25")


def pytest_runtest_setup(item):
    for marker_name, min_version in _VERSION_MARKERS.items():
        marker = item.get_closest_marker(marker_name)
        if marker is not None:
            client = item.session.config._mcp_client_instance if hasattr(item.session.config, "_mcp_client_instance") else None
            if client is not None:
                server_num = client.server_version_num
                if server_num > 0 and server_num < min_version:
                    version_names = {v: k for k, v in SPEC_VERSIONS.items()}
                    min_name = version_names.get(min_version, "unknown")
                    pytest.skip(f"Test requires spec >= {min_name}, server is {client.server_version}")


def _client_options(config) -> dict:
    method_timeouts = discover_method_timeouts()
    method_timeouts.update(
        parse_timeout_overrides(config.getoption("--mcp-timeout-method") or [])
    )
    return {
        "timeout": config.getoption("--mcp-timeout"),
        "method_timeouts": method_timeouts,
        "use_smart_timeouts": config.getoption("--mcp-smart-timeouts"),
        "trace_path": config.getoption("--mcp-trace"),
        "live_stderr": config.getoption("--mcp-live-stderr"),
    }


def _safe_nodeid(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_") or "mcp-test"


# Namespaced session attribute so we never collide with another plugin or
# user-defined config attribute on `session.config`.
_CLIENT_ATTR = "_pytest_mcp_plugin_client"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    client = getattr(item.session.config, _CLIENT_ATTR, None)
    if client is None or not hasattr(client, "wire_trace"):
        return

    # If the user already specified --mcp-trace, the trace is being written
    # there directly; don't double-dump. Outside CI we skip the auto-dump so
    # local runs don't litter the working tree.
    if item.config.getoption("--mcp-trace") or not os.getenv("CI"):
        return

    target_dir = Path("mcp-traces")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        dumped = client.wire_trace.dump_to(target_dir / f"{_safe_nodeid(item.nodeid)}.jsonl")
        report.sections.append(("mcp-wire-trace", f"Recent MCP frames dumped to {dumped}"))
    except OSError as exc:
        # Read-only working tree, etc — surface in the report rather than
        # crashing the test runner.
        report.sections.append(("mcp-wire-trace", f"Could not dump wire trace: {exc}"))


@pytest.fixture(scope="session")
def mcp_client(request):
    command = request.config.getoption("--mcp-command")
    if not command:
        pytest.skip("No --mcp-command provided")
    options = _client_options(request.config)
    with make_client(command, **options) as client:
        setattr(request.config, _CLIENT_ATTR, client)
        try:
            yield client
        finally:
            if getattr(request.config, _CLIENT_ATTR, None) is client:
                setattr(request.config, _CLIENT_ATTR, None)


@pytest.fixture
def mcp_client_fresh(request):
    command = request.config.getoption("--mcp-command")
    if not command:
        pytest.skip("No --mcp-command provided")
    options = _client_options(request.config)
    previous = getattr(request.config, _CLIENT_ATTR, None)
    with make_client(command, **options) as client:
        setattr(request.config, _CLIENT_ATTR, client)
        try:
            yield client
        finally:
            setattr(request.config, _CLIENT_ATTR, previous)


@pytest.fixture
def sandboxed_client(request, tmp_path):
    command = request.config.getoption("--mcp-command")
    if not command:
        pytest.skip("No --mcp-command provided")
    options = _client_options(request.config)
    previous = getattr(request.config, _CLIENT_ATTR, None)
    with make_client(
        command,
        **options,
        cwd=str(tmp_path),
        env={"DATA_DIR": str(tmp_path)},
    ) as client:
        setattr(request.config, _CLIENT_ATTR, client)
        try:
            yield client
        finally:
            setattr(request.config, _CLIENT_ATTR, previous)


@pytest.fixture
def snapshot(request):
    test_file = Path(request.fspath)
    snap_dir = test_file.parent / SNAPSHOT_DIR
    test_name = request.node.name
    update = request.config.getoption("--snapshot-update", default=False)
    return Snapshot(snap_dir, test_name, update=update)
