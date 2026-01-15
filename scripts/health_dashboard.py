#!/usr/bin/env python3
"""Generate health dashboard showing CI status, staleness, and upstream divergence."""

import argparse
import json
import sys
from pathlib import Path

from defibrillator.repo_catalog import load_all_repos
from defibrillator.staleness import compute_staleness, today_utc


def get_divergence_info(repo: dict, divergence_data: dict) -> dict:
    """Get divergence info from divergence data.

    Args:
        repo: Repository data
        divergence_data: Dictionary mapping file_stem to divergence data

    Returns:
        Dictionary with commits_behind, significance, last_commit_date
    """
    file_stem = repo.get("_file", "")
    return divergence_data.get(
        file_stem,
        {"commits_behind": None, "significance": "unknown", "last_commit_date": None},
    )


def generate_health_dashboard(
    repos: list[dict],
    staleness_results: list,
    divergence_data: dict,
) -> str:
    """Generate health dashboard markdown."""

    today = today_utc()

    lines = [
        "# Repository Health Dashboard",
        "",
        f"**Generated:** {today}",
        "",
        "# Overview",
        "",
    ]

    total = len(repos)
    active = sum(1 for r in repos if r.get("status", {}).get("state") == "active")
    passing = sum(1 for r in repos if r.get("status", {}).get("ci_status") == "passing")
    failing = sum(1 for r in repos if r.get("status", {}).get("ci_status") == "failing")

    staleness_map = {r.file_stem: r for r in staleness_results}
    critical_stale = sum(1 for r in staleness_results if r.severity == "critical")
    warning_stale = sum(1 for r in staleness_results if r.severity == "warning")

    critical_divergence = sum(1 for d in divergence_data.values() if d.get("significance") == "critical")
    warning_divergence = sum(1 for d in divergence_data.values() if d.get("significance") == "warning")

    lines.extend(
        [
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total Repositories | {total} |",
            f"| Active | {active} |",
            f"| CI Passing | {passing} |",
            f"| CI Failing | {failing} |",
            f"| 🚨 Critical Stale | {critical_stale} |",
            f"| ⚠️ Warning Stale | {warning_stale} |",
            f"| 🚨 Critical Divergence | {critical_divergence} |",
            f"| ⚠️ Warning Divergence | {warning_divergence} |",
            "",
        ]
    )

    lines.extend(
        [
            "# Repository Details",
            "",
            "| Repository | Status | CI | Staleness | Divergence |",
            "|------------|--------|-----|-----------|-------------|",
        ]
    )

    for repo in repos:
        file_stem = repo.get("_file", "")
        fork = repo.get("fork", {})
        status = repo.get("status", {})

        name = fork.get("name", file_stem)
        url = fork.get("url", "#")
        state = status.get("state", "unknown")
        ci_status = status.get("ci_status", "unknown")

        staleness_result = staleness_map.get(file_stem)
        if staleness_result:
            days_stale = staleness_result.days_stale
            s_severity = staleness_result.severity
            if days_stale is not None:
                staleness_display = f"{s_severity} ({days_stale}d)"
            else:
                staleness_display = f"{s_severity}"
        else:
            staleness_display = "unknown"

        divergence = get_divergence_info(repo, divergence_data)
        commits_behind = divergence.get("commits_behind")
        d_severity = divergence.get("significance", "unknown")

        if commits_behind is not None:
            divergence_display = f"{d_severity} ({commits_behind})"
        else:
            divergence_display = f"{d_severity}"

        status_icons = {"active": "🟢", "life-support": "🟡", "archived": "⚫", "pending": "🔵", "unknown": "❓"}
        ci_icons = {"passing": "✅", "failing": "❌", "unknown": "❓"}

        status_icon = status_icons.get(state, "❓")
        ci_icon = ci_icons.get(ci_status, "❓")

        table_row = (
            f"| [{name}]({url}) | {status_icon} {state} | {ci_icon} {ci_status} | "
            f"{staleness_display} | {divergence_display} |"
        )
        lines.append(table_row)

    return "\n".join(lines)


def load_divergence_data(repos: list[dict]) -> dict:
    """Load divergence data for repositories.

    This is a simplified version that loads from a file if it exists,
    otherwise returns empty data.
    """
    base_dir = Path(__file__).parent.parent
    divergence_file = base_dir / "data" / "divergence.json"

    if not divergence_file.exists():
        return {}

    try:
        with open(divergence_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate health dashboard.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "HEALTH.md",
        help="Output file for health dashboard",
    )
    parser.add_argument(
        "--warning-days",
        type=int,
        default=75,
        help="Days threshold for warning severity",
    )
    parser.add_argument(
        "--critical-days",
        type=int,
        default=90,
        help="Days threshold for critical severity",
    )

    args = parser.parse_args()

    if not args.repos_dir.exists():
        print(f"Error: repos directory not found: {args.repos_dir}", file=sys.stderr)
        return 2

    repos = load_all_repos(args.repos_dir)

    if not repos:
        print("No repository files found.")
        return 0

    staleness_results = compute_staleness(
        repos,
        warning_days=args.warning_days,
        critical_days=args.critical_days,
    )

    divergence_data = load_divergence_data(repos)

    dashboard = generate_health_dashboard(repos, staleness_results, divergence_data)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dashboard, encoding="utf-8")

    print(f"Generated health dashboard: {args.output}")
    print(f"  - {len(repos)} repositories")

    return 0


if __name__ == "__main__":
    sys.exit(main())
