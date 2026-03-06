
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from .client import MCPTestClient, make_client


def fixture(func=None, *, scope="session", timeout=10.0):
    def decorator(fn):
        @pytest.fixture(scope=scope)
        def wrapper():
            client = fn()
            if isinstance(client, MCPTestClient):
                client.start()
                yield client
                client.close()
            else:
                yield client
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def make_sandboxed_client(
    command: str,
    tmp_path: Path,
    *,
    timeout: float = 10.0,
    env: dict[str, str] | None = None,
) -> MCPTestClient:
    merged_env = {"DATA_DIR": str(tmp_path)}
    if env:
        merged_env.update(env)
    return make_client(command, timeout=timeout, cwd=str(tmp_path), env=merged_env)


def seed_fixture_data(tmp_path: Path, files: dict[str, str]) -> None:
    for file_path, content in files.items():
        full_path = tmp_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
