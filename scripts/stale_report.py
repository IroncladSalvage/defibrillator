#!/usr/bin/env python3
"""Generate stale repository report.

Flags repos where last_touched exceeds configurable thresholds.
"""

import argparse
import json
import sys
from pathlib import Path

from defibrillator.repo_catalog import load_all_repos
from defibrillator.staleness import StalenessResult, compute_staleness, to_json


def format_table(results: list[StalenessResult]) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No stale repositories found."

    lines = [
        "| Repository | Last Touched | Days Stale | Severity |",
        "|------------|--------------|------------|----------|",
    ]

    severity_icons = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}

    for r in results:
        last_touched = r.last_touched if r.last_touched else "N/A"
        days = r.days_stale if r.days_stale is not None else "N/A"
        icon = severity_icons.get(r.severity, "")
        lines.append(f"| {r.repo_name} | {last_touched} | {days} | {icon} {r.severity} |")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate stale repository report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
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
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="Show all repos including ok status",
    )

    args = parser.parse_args()

    if not args.repos_dir.exists():
        print(f"Error: repos directory not found: {args.repos_dir}", file=sys.stderr)
        return 1

    repos = load_all_repos(args.repos_dir)

    if not repos:
        if args.json_output:
            print(json.dumps([]))
        else:
            print("No repository files found.")
        return 0

    results = compute_staleness(
        repos,
        warning_days=args.warning_days,
        critical_days=args.critical_days,
    )

    if not args.show_all:
        results = [r for r in results if r.severity in ("warning", "critical")]

    results.sort(key=lambda r: r.days_stale if r.days_stale is not None else -1, reverse=True)

    if args.json_output:
        print(json.dumps(to_json(results), indent=2))
    else:
        print(format_table(results))

    has_critical = any(r.severity == "critical" for r in results)
    has_warning = any(r.severity == "warning" for r in results)

    if has_critical:
        return 2
    if has_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
