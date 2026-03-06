
from __future__ import annotations

import pytest

from .client import MCPTestClient, make_client
from .snapshot import Snapshot, SNAPSHOT_DIR
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


@pytest.fixture(scope="session")
def mcp_client(request):
    command = request.config.getoption("--mcp-command")
    if not command:
        pytest.skip("No --mcp-command provided")
    timeout = request.config.getoption("--mcp-timeout")
    with make_client(command, timeout=timeout) as client:
        yield client


@pytest.fixture
def mcp_client_fresh(request):
    command = request.config.getoption("--mcp-command")
    if not command:
        pytest.skip("No --mcp-command provided")
    timeout = request.config.getoption("--mcp-timeout")
    with make_client(command, timeout=timeout) as client:
        yield client


@pytest.fixture
def sandboxed_client(request, tmp_path):
    command = request.config.getoption("--mcp-command")
    if not command:
        pytest.skip("No --mcp-command provided")
    timeout = request.config.getoption("--mcp-timeout")
    with make_client(
        command,
        timeout=timeout,
        cwd=str(tmp_path),
        env={"DATA_DIR": str(tmp_path)},
    ) as client:
        yield client


@pytest.fixture
def snapshot(request):
    test_file = Path(request.fspath)
    snap_dir = test_file.parent / SNAPSHOT_DIR
    test_name = request.node.name
    update = request.config.getoption("--snapshot-update", default=False)
    return Snapshot(snap_dir, test_name, update=update)
