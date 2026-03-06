
from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel

from .types import ToolList, Prompt, Resource


@dataclass
class PrimitiveCoverage:
    """Coverage data for a single primitive (tool, prompt, resource)."""

    name: str
    call_count: int = 0
    test_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_covered(self) -> bool:
        return self.call_count > 0

    @property
    def percentage(self) -> float:
        return 100.0 if self.is_covered else 0.0


@dataclass
class CoverageReport:
    """Full coverage report across all primitives."""

    tools: list[PrimitiveCoverage]
    prompts: list[PrimitiveCoverage]
    resources: list[PrimitiveCoverage]
    client_features: list[PrimitiveCoverage]

    @property
    def total_tools(self) -> int:
        return len(self.tools)

    @property
    def covered_tools(self) -> int:
        return sum(1 for t in self.tools if t.is_covered)

    @property
    def uncovered_tools(self) -> list[str]:
        return [t.name for t in self.tools if not t.is_covered]

    @property
    def total_prompts(self) -> int:
        return len(self.prompts)

    @property
    def covered_prompts(self) -> int:
        return sum(1 for p in self.prompts if p.is_covered)

    @property
    def total_resources(self) -> int:
        return len(self.resources)

    @property
    def covered_resources(self) -> int:
        return sum(1 for r in self.resources if r.is_covered)

    @property
    def total_client_features(self) -> int:
        return len(self.client_features)

    @property
    def covered_client_features(self) -> int:
        return sum(1 for f in self.client_features if f.is_covered)

    @property
    def overall_percentage(self) -> float:
        total = self.total_tools + self.total_prompts + self.total_resources + self.total_client_features
        if total == 0:
            return 100.0
        covered = self.covered_tools + self.covered_prompts + self.covered_resources + self.covered_client_features
        return (covered / total) * 100


class CoverageTracker:
    """Tracks tool coverage during a test session."""

    def __init__(self):
        self._call_counts: dict[str, dict[str, int]] = {
            "tools": {},
            "prompts": {},
            "resources": {},
            "client_features": {},
        }
        self._tests: dict[str, dict[str, list[str]]] = {
            "tools": {},
            "prompts": {},
            "resources": {},
            "client_features": {},
        }
        self._all_items: dict[str, set[str]] = {
            "tools": set(),
            "prompts": set(),
            "resources": set(),
            "client_features": {"sampling", "elicitation", "roots"},
        }
        self._warnings: dict[str, list[str]] = {}

    def register_schemas(self, tools: ToolList, prompts: list[Prompt], resources: list[Resource]) -> None:
        for t in tools:
            self._all_items["tools"].add(t.name)
            # Check for warnings
            warnings = []
            if not getattr(t.annotations, "destructive_hint", False) and not getattr(t.annotations, "read_only_hint", False):
                warnings.append("Missing read_only_hint or destructive_hint annotation")
            if t.output_schema is None:
                warnings.append("Missing output_schema definition")
            if warnings:
                self._warnings[t.name] = warnings

        for p in prompts:
            self._all_items["prompts"].add(p.name)

        for r in resources:
            self._all_items["resources"].add(r.name)

    def record_call(self, category: str, name: str, test_name: str = "") -> None:
        if category not in self._call_counts:
            self._call_counts[category] = {}
            self._tests[category] = {}
            self._all_items[category] = set()

        self._call_counts[category][name] = self._call_counts[category].get(name, 0) + 1
        self._all_items[category].add(name)

        if test_name:
            if name not in self._tests[category]:
                self._tests[category][name] = []
            self._tests[category][name].append(test_name)

    def report(self) -> CoverageReport:
        def _build_cov(category: str) -> list[PrimitiveCoverage]:
            cov = []
            for name in sorted(self._all_items[category]):
                cov.append(PrimitiveCoverage(
                    name=name,
                    call_count=self._call_counts[category].get(name, 0),
                    test_names=self._tests[category].get(name, []),
                    warnings=self._warnings.get(name, []) if category == "tools" else []
                ))
            return cov

        return CoverageReport(
            tools=_build_cov("tools"),
            prompts=_build_cov("prompts"),
            resources=_build_cov("resources"),
            client_features=_build_cov("client_features"),
        )


def print_coverage_report(report: CoverageReport) -> None:
    console = Console()

    def _render_table(title: str, items: list[PrimitiveCoverage]) -> Table | None:
        if not items:
            return None
        table = Table(title=title, show_lines=True)
        table.add_column("Item", style="cyan", no_wrap=True)
        table.add_column("Coverage", justify="center")
        table.add_column("Calls", justify="right", style="white")
        table.add_column("Status / Warnings", justify="left")

        for item in items:
            if item.is_covered:
                bar = "█" * 12
                bar_style = "green"
                status = "✅"
            else:
                bar = "░" * 12
                bar_style = "red"
                status = "⚠️  never tested"

            if item.warnings:
                status += f"\n[yellow]Warnings:[/] {', '.join(item.warnings)}"

            bar_text = Text(f"{bar} {item.percentage:.0f}%", style=bar_style)
            table.add_row(
                item.name,
                bar_text,
                str(item.call_count),
                status,
            )
        return table

    for table in [
        _render_table("Tools", report.tools),
        _render_table("Prompts", report.prompts),
        _render_table("Resources", report.resources),
        _render_table("Client Features Mocked", report.client_features),
    ]:
        if table:
            console.print(table)
            console.print()

    overall_style = "green" if report.overall_percentage == 100 else "yellow"
    if report.overall_percentage < 50:
        overall_style = "red"

    summary = Text(
        f"Overall: "
        f"{report.covered_tools}/{report.total_tools} tools, "
        f"{report.covered_prompts}/{report.total_prompts} prompts, "
        f"{report.covered_resources}/{report.total_resources} resources, "
        f"{report.covered_client_features}/{report.total_client_features} features used. "
        f"({report.overall_percentage:.0f}% total)",
        style=f"bold {overall_style}",
    )
    console.print(Panel(summary, border_style=overall_style))

    if report.uncovered_tools:
        console.print()
        console.print(Text("Untested items:", style="bold red"))
        for name in report.uncovered_tools:
            console.print(f"  • Tool: {name}", style="red")
        for p in report.prompts:
            if not p.is_covered:
                console.print(f"  • Prompt: {p.name}", style="red")
        for r in report.resources:
            if not r.is_covered:
                console.print(f"  • Resource: {r.name}", style="red")
