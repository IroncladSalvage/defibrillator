"""Tests for staleness detection."""

from __future__ import annotations

from datetime import date


from defibrillator.dates import days_since, parse_date
from defibrillator.staleness import StalenessResult, compute_staleness, to_json


class TestParseDate:
    def test_valid_date(self):
        assert parse_date("2026-01-01") == date(2026, 1, 1)

    def test_invalid_date(self):
        assert parse_date("not-a-date") is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_wrong_format(self):
        assert parse_date("01-01-2026") is None


class TestDaysSince:
    def test_days_since_valid(self):
        today = date(2026, 1, 14)
        assert days_since("2026-01-01", today) == 13

    def test_days_since_same_day(self):
        today = date(2026, 1, 14)
        assert days_since("2026-01-14", today) == 0

    def test_days_since_invalid_date(self):
        assert days_since("invalid", date(2026, 1, 14)) is None


class TestComputeStaleness:
    def test_ok_status(self):
        repos = [
            {
                "_file": "test-repo.yaml",
                "origin": {"name": "test-repo"},
                "status": {"last_touched": "2026-01-10"},
            }
        ]
        today = date(2026, 1, 14)
        results = compute_staleness(
            repos, warning_days=75, critical_days=90, today=today
        )

        assert len(results) == 1
        assert results[0].severity == "ok"
        assert results[0].days_stale == 4

    def test_warning_status(self):
        repos = [
            {
                "_file": "test-repo.yaml",
                "origin": {"name": "test-repo"},
                "status": {"last_touched": "2025-10-31"},
            }
        ]
        today = date(2026, 1, 14)
        results = compute_staleness(
            repos, warning_days=75, critical_days=90, today=today
        )

        assert len(results) == 1
        assert results[0].severity == "warning"
        assert results[0].days_stale == 75

    def test_critical_status(self):
        repos = [
            {
                "_file": "test-repo.yaml",
                "origin": {"name": "test-repo"},
                "status": {"last_touched": "2025-10-16"},
            }
        ]
        today = date(2026, 1, 14)
        results = compute_staleness(
            repos, warning_days=75, critical_days=90, today=today
        )

        assert len(results) == 1
        assert results[0].severity == "critical"
        assert results[0].days_stale == 90

    def test_missing_last_touched(self):
        repos = [
            {
                "_file": "test-repo.yaml",
                "origin": {"name": "test-repo"},
                "status": {},
            }
        ]
        today = date(2026, 1, 14)
        results = compute_staleness(
            repos, warning_days=75, critical_days=90, today=today
        )

        assert len(results) == 1
        assert results[0].severity == "critical"
        assert results[0].days_stale is None

    def test_configurable_thresholds(self):
        repos = [
            {
                "_file": "test-repo.yaml",
                "origin": {"name": "test-repo"},
                "status": {"last_touched": "2026-01-01"},
            }
        ]
        today = date(2026, 1, 14)

        results_default = compute_staleness(
            repos, warning_days=75, critical_days=90, today=today
        )
        assert results_default[0].severity == "ok"

        results_strict = compute_staleness(
            repos, warning_days=7, critical_days=14, today=today
        )
        assert results_strict[0].severity == "warning"

        results_very_strict = compute_staleness(
            repos, warning_days=5, critical_days=10, today=today
        )
        assert results_very_strict[0].severity == "critical"

    def test_multiple_repos(self):
        repos = [
            {
                "_file": "repo1.yaml",
                "origin": {"name": "repo1"},
                "status": {"last_touched": "2026-01-10"},
            },
            {
                "_file": "repo2.yaml",
                "origin": {"name": "repo2"},
                "status": {"last_touched": "2025-10-31"},
            },
            {
                "_file": "repo3.yaml",
                "origin": {"name": "repo3"},
                "status": {"last_touched": "2025-10-01"},
            },
        ]
        today = date(2026, 1, 14)
        results = compute_staleness(
            repos, warning_days=75, critical_days=90, today=today
        )

        assert len(results) == 3
        severities = {r.repo_name: r.severity for r in results}
        assert severities["repo1"] == "ok"
        assert severities["repo2"] == "warning"
        assert severities["repo3"] == "critical"


class TestToJson:
    def test_serialization(self):
        results = [
            StalenessResult(
                repo_name="test-repo",
                file_stem="test-repo",
                last_touched="2026-01-10",
                days_stale=4,
                severity="ok",
            )
        ]
        json_output = to_json(results)

        assert len(json_output) == 1
        assert json_output[0]["repo_name"] == "test-repo"
        assert json_output[0]["days_stale"] == 4
        assert json_output[0]["severity"] == "ok"
