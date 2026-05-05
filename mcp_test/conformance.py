from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .http_client import HTTPMCPTestClient


@dataclass(frozen=True)
class ConformanceScenario:
    name: str
    passed: bool
    message: str = ""
    spec_version: str = ""


@dataclass(frozen=True)
class ConformanceReport:
    scenarios: tuple[ConformanceScenario, ...]
    source: str
    raw: Any = None

    @property
    def total(self) -> int:
        return len(self.scenarios)

    @property
    def passed(self) -> int:
        return sum(1 for scenario in self.scenarios if scenario.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.passed / self.total) * 100, 1)

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "percentage": self.percentage,
            "scenarios": [
                {
                    "name": scenario.name,
                    "passed": scenario.passed,
                    "message": scenario.message,
                    "spec_version": scenario.spec_version,
                }
                for scenario in self.scenarios
            ],
        }


def npx_available() -> bool:
    return shutil.which("npx") is not None


def run_upstream_conformance(
    url: str,
    *,
    npx: str = "npx",
    timeout: float = 300.0,
    extra_args: Iterable[str] = (),
) -> ConformanceReport:
    args = [
        npx,
        "-y",
        "@modelcontextprotocol/conformance",
        "server",
        "--url",
        url,
        "--json",
        *extra_args,
    ]
    completed = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    report = parse_conformance_output(output, source="upstream")
    if completed.returncode and report.failed == 0:
        scenario = ConformanceScenario(
            name="conformance command",
            passed=False,
            message=completed.stderr.strip() or f"Exited with {completed.returncode}",
        )
        return ConformanceReport((scenario,), source="upstream", raw=output)
    return report


def parse_conformance_output(output: str, *, source: str = "upstream") -> ConformanceReport:
    if not output:
        return ConformanceReport((), source=source, raw="")

    parsed: Any
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = _parse_json_lines(output)

    scenarios = tuple(_scenario_from_item(item) for item in _iter_scenario_items(parsed))
    return ConformanceReport(scenarios, source=source, raw=parsed)


def run_offline_smoke_conformance(url: str, *, timeout: float = 10.0) -> ConformanceReport:
    scenarios: list[ConformanceScenario] = []
    try:
        with HTTPMCPTestClient.from_url(url, timeout=timeout) as client:
            scenarios.append(ConformanceScenario("initialize", True))
            try:
                client.ping()
                scenarios.append(ConformanceScenario("ping", True))
            except Exception as exc:
                scenarios.append(ConformanceScenario("ping", False, str(exc)))
            try:
                client.list_tools()
                scenarios.append(ConformanceScenario("tools/list", True))
            except Exception as exc:
                scenarios.append(ConformanceScenario("tools/list", False, str(exc)))
    except Exception as exc:
        scenarios.append(ConformanceScenario("initialize", False, str(exc)))
    return ConformanceReport(tuple(scenarios), source="offline")


def run_report_as_pytest(report: ConformanceReport, *, extra_pytest_args: Iterable[str] = ()) -> int:
    """Re-emit parsed conformance scenarios as real pytest test items."""

    with tempfile.TemporaryDirectory(prefix="mcp-conformance-") as tmp:
        test_file = Path(tmp) / "test_mcp_conformance.py"
        test_file.write_text(_pytest_source(report), encoding="utf-8")
        args = [sys.executable, "-m", "pytest", str(test_file), "-q", *extra_pytest_args]
        return subprocess.run(args, check=False).returncode


def _parse_json_lines(output: str) -> list[Any]:
    items: list[Any] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def _iter_scenario_items(parsed: Any) -> Iterable[dict[str, Any]]:
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                yield from _iter_scenario_items(item)
        return

    if not isinstance(parsed, dict):
        return

    for key in ("scenarios", "tests", "results", "cases"):
        value = parsed.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item
            return

    if any(key in parsed for key in ("name", "title", "status", "passed", "ok")):
        yield parsed


def _scenario_from_item(item: dict[str, Any]) -> ConformanceScenario:
    name = str(
        item.get("name")
        or item.get("title")
        or item.get("id")
        or item.get("scenario")
        or "unnamed scenario"
    )
    status = item.get("status")
    passed = item.get("passed", item.get("ok"))
    if passed is None:
        passed = str(status).lower() in {"pass", "passed", "ok", "success"}
    message = (
        item.get("message")
        or item.get("error")
        or item.get("failure")
        or item.get("details")
        or ""
    )
    if isinstance(message, dict):
        message = json.dumps(message, sort_keys=True)
    return ConformanceScenario(
        name=name,
        passed=bool(passed),
        message=str(message),
        spec_version=str(item.get("specVersion") or item.get("spec_version") or ""),
    )


def _pytest_source(report: ConformanceReport) -> str:
    data = report.to_json()["scenarios"]
    return (
        "import pytest\n\n"
        f"SCENARIOS = {data!r}\n\n"
        "@pytest.mark.parametrize('scenario', SCENARIOS, ids=lambda item: item['name'])\n"
        "def test_mcp_conformance_scenario(scenario):\n"
        "    assert scenario['passed'], scenario.get('message') or scenario['name']\n"
    )
