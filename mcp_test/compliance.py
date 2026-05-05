from __future__ import annotations

from dataclasses import dataclass

from .conformance import ConformanceReport


@dataclass(frozen=True)
class ComplianceScore:
    passed: int
    total: int
    spec_version: str = ""

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.passed / self.total) * 100, 1)

    def badge_text(self) -> str:
        version = f" for {self.spec_version}" if self.spec_version else ""
        return (
            f"passing {self.passed} / {self.total} conformance scenarios"
            f"{version} ({self.percentage}%)"
        )


def score_conformance(report: ConformanceReport, spec_version: str = "") -> ComplianceScore:
    if not spec_version:
        versions = {scenario.spec_version for scenario in report.scenarios if scenario.spec_version}
        spec_version = sorted(versions)[-1] if versions else ""
    return ComplianceScore(
        passed=report.passed,
        total=report.total,
        spec_version=spec_version,
    )
