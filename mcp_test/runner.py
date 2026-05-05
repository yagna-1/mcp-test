
from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

try:
    import tomllib  # py>=3.11
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


def _load_mcp_test_config(project_dir: str | None) -> dict[str, Any]:
    """Read [tool.mcp-test] from the project's pyproject.toml.

    Returns an empty dict if the file does not exist, tomllib is unavailable,
    or the TOML is malformed (with a warning so users notice typos).
    """

    root = Path(project_dir) if project_dir else Path.cwd()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists() or tomllib is None:
        return {}

    try:
        with open(pyproject, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:  # type: ignore[attr-defined]
        warnings.warn(
            f"pytest-mcp-plugin: could not read {pyproject}: {exc}",
            stacklevel=3,
        )
        return {}

    section = data.get("tool", {}).get("mcp-test", {})
    return section if isinstance(section, dict) else {}


def discover_command(project_dir: str | None = None) -> str | None:
    config = _load_mcp_test_config(project_dir)
    command = config.get("command")
    return command if isinstance(command, str) else None


def discover_timeout(project_dir: str | None = None) -> float:
    config = _load_mcp_test_config(project_dir)
    try:
        return float(config.get("timeout", 10.0))
    except (TypeError, ValueError):
        return 10.0


def discover_method_timeouts(project_dir: str | None = None) -> dict[str, float]:
    config = _load_mcp_test_config(project_dir)
    raw = config.get("timeouts", {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for method, timeout in raw.items():
        try:
            value = float(timeout)
        except (TypeError, ValueError):
            continue
        if value > 0:
            result[str(method)] = value
    return result


def run_tests(
    command: str | None = None,
    timeout: float | None = None,
    test_dir: str = "tests",
    verbose: bool = False,
    extra_args: list[str] | None = None,
    watch: bool = False,
    method_timeouts: dict[str, float] | None = None,
    trace_path: str | None = None,
) -> int:
    if command is None:
        command = discover_command()
    if command is None:
        print("Error: No --mcp-command provided and no [tool.mcp-test] command in pyproject.toml")
        return 1

    if timeout is None:
        timeout = discover_timeout()
    if method_timeouts is None:
        method_timeouts = discover_method_timeouts()

    args = [
        sys.executable, "-m", "pytest",
        test_dir,
        f"--mcp-command={command}",
        f"--mcp-timeout={timeout}",
    ]
    for method, method_timeout in method_timeouts.items():
        args.append(f"--mcp-timeout-method={method}={method_timeout}")
    if trace_path:
        args.append(f"--mcp-trace={trace_path}")
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
