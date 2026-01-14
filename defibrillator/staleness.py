"""Staleness calculation for repository tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from defibrillator.dates import days_since, today_utc

Severity = Literal["ok", "warning", "critical"]


@dataclass
class StalenessResult:
    """Result of staleness calculation for a repository."""

    repo_name: str
    file_stem: str
    last_touched: str | None
    days_stale: int | None
    severity: Severity


def compute_staleness(
    repos: list[dict],
    warning_days: int = 75,
    critical_days: int = 90,
    today: date | None = None,
) -> list[StalenessResult]:
    """Compute staleness for a list of repositories."""
    if today is None:
        today = today_utc()

    results: list[StalenessResult] = []

    for repo in repos:
        file_stem = repo.get("_file", "")
        if not file_stem:
            file_path = repo.get("_path", "")
            file_stem = Path(file_path).stem if file_path else ""

        status = repo.get("status", {})
        last_touched = status.get("last_touched")

        origin = repo.get("origin", {})
        repo_name = origin.get("name", file_stem)

        if not last_touched:
            results.append(
                StalenessResult(
                    repo_name=repo_name,
                    file_stem=file_stem,
                    last_touched=None,
                    days_stale=None,
                    severity="critical",
                )
            )
            continue

        days = days_since(last_touched, today)
        if days is None:
            severity: Severity = "critical"
        elif days >= critical_days:
            severity = "critical"
        elif days >= warning_days:
            severity = "warning"
        else:
            severity = "ok"

        results.append(
            StalenessResult(
                repo_name=repo_name,
                file_stem=file_stem,
                last_touched=last_touched,
                days_stale=days,
                severity=severity,
            )
        )

    return results


def to_json(results: list[StalenessResult]) -> list[dict]:
    """Convert staleness results to JSON-serializable dictionaries."""
    return [
        {
            "repo_name": r.repo_name,
            "file_stem": r.file_stem,
            "last_touched": r.last_touched,
            "days_stale": r.days_stale,
            "severity": r.severity,
        }
        for r in results
    ]
