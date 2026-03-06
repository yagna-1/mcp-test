
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


def discover_command(project_dir: str | None = None) -> str | None:
    root = Path(project_dir) if project_dir else Path.cwd()
    pyproject = root / "pyproject.toml"

    if not pyproject.exists():
        return None
    if tomllib is None:
        return None

    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None

    mcp_test_config = data.get("tool", {}).get("mcp-test", {})
    return mcp_test_config.get("command")


def discover_timeout(project_dir: str | None = None) -> float:
    root = Path(project_dir) if project_dir else Path.cwd()
    pyproject = root / "pyproject.toml"

    if not pyproject.exists() or tomllib is None:
        return 10.0

    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return 10.0

    mcp_test_config = data.get("tool", {}).get("mcp-test", {})
    return float(mcp_test_config.get("timeout", 10.0))


def run_tests(
    command: str | None = None,
    timeout: float | None = None,
    test_dir: str = "tests",
    verbose: bool = False,
    extra_args: list[str] | None = None,
    watch: bool = False,
) -> int:
    if command is None:
        command = discover_command()
    if command is None:
        print("Error: No --mcp-command provided and no [tool.mcp-test] command in pyproject.toml")
        return 1

    if timeout is None:
        timeout = discover_timeout()

    args = [
        sys.executable, "-m", "pytest",
        test_dir,
        f"--mcp-command={command}",
        f"--mcp-timeout={timeout}",
    ]
    if verbose:
        args.append("-v")
    if extra_args:
        args.extend(extra_args)

    if watch:
        return _run_watch_mode(args)

    result = subprocess.run(args, cwd=os.getcwd())
    return result.returncode


def _run_watch_mode(base_args: list[str]) -> int:
    import time

    test_dir = "tests"
    for arg in base_args:
        if not arg.startswith("-") and not arg.startswith("--") and arg != sys.executable and arg != "-m" and arg != "pytest":
            if not "=" in arg:
                test_dir = arg
                break

    print(f"👀 Watching for changes... (Ctrl+C to stop)")
    print()

    last_mtimes: dict[str, float] = {}
    first_run = True

    try:
        while True:
            current_mtimes: dict[str, float] = {}
            watch_dirs = [test_dir, "."]
            for watch_dir in watch_dirs:
                watch_path = Path(watch_dir)
                if watch_path.exists():
                    for py_file in watch_path.rglob("*.py"):
                        try:
                            current_mtimes[str(py_file)] = py_file.stat().st_mtime
                        except OSError:
                            pass

            changed = first_run or current_mtimes != last_mtimes

            if changed:
                if not first_run:
                    print("\n🔄 File change detected, re-running tests...\n")

                subprocess.run(base_args, cwd=os.getcwd())
                last_mtimes = current_mtimes
                first_run = False

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Watch mode stopped.")
        return 0
