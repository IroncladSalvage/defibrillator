#!/usr/bin/env python3
"""Check runtime compatibility and flag EOL runtimes."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from defibrillator.repo_catalog import load_all_repos

EOL_Runtimes = {
    "python": {
        "2.7": "2020-01-01",
        "3.6": "2021-12-23",
        "3.7": "2023-06-27",
        "3.8": "2024-10-07",
        "3.9": "2025-10-05",
        "3.10": "2026-10-04",
    },
    "node": {
        "12": "2022-04-30",
        "14": "2023-04-30",
        "16": "2023-09-11",
        "17": "2024-04-30",
        "18": "2025-04-30",
        "19": "2026-04-01",
    },
    "java": {
        "8": "2030-12-31",
        "11": "2026-09-30",
        "17": "2029-09-30",
    },
    "go": {
        "1.16": "2022-03-15",
        "1.17": "2022-08-10",
        "1.18": "2023-08-01",
        "1.19": "2024-01-09",
        "1.20": "2024-02-01",
    },
}


LATEST_VERSIONS = {
    "python": "3.13",
    "node": "22",
    "java": "21",
    "go": "1.23",
}


def parse_runtime_spec(runtime: str) -> tuple[str, str] | None:
    """Parse runtime specification.

    Args:
        runtime: Runtime string (e.g., "python3.11+", "node20+")

    Returns:
        Tuple of (runtime_type, version) or None
    """
    match = re.match(r"(python|node|java|go)[\s-]*(\d+(?:\.\d+)*[+]?)", runtime.lower())
    if not match:
        return None

    runtime_type = match.group(1)
    version = match.group(2).rstrip("+")

    return runtime_type, version


def is_eol(runtime_type: str, version: str) -> tuple[bool, str | None]:
    """Check if a runtime version is EOL.

    Args:
        runtime_type: Type of runtime (python, node, java, go)
        version: Version string

    Returns:
        Tuple of (is_eol, eol_date)
    """
    eol_dates = EOL_Runtimes.get(runtime_type, {})

    for eol_version, eol_date in eol_dates.items():
        if version.startswith(eol_version):
            return True, eol_date

    return False, None


def get_suggested_version(runtime_type: str) -> str:
    """Get suggested latest version for a runtime.

    Args:
        runtime_type: Type of runtime

    Returns:
        Suggested version
    """
    return LATEST_VERSIONS.get(runtime_type, "")


def check_runtime_compatibility(data: dict) -> dict[str, Any]:
    """Check runtime compatibility for a repository.

    Args:
        data: Repository YAML data

    Returns:
        Dictionary with compatibility information
    """
    runtimes = data.get("targets", {}).get("runtimes", [])
    file_stem = data.get("_file", "unknown")
    fork = data.get("fork", {})

    repo_name = fork.get("name", file_stem)

    issues = []
    suggestions = []

    for runtime in runtimes:
        parsed = parse_runtime_spec(runtime)
        if not parsed:
            continue

        runtime_type, version = parsed
        is_eol_value, eol_date = is_eol(runtime_type, version)

        if is_eol_value:
            issues.append(
                {
                    "runtime": runtime,
                    "runtime_type": runtime_type,
                    "version": version,
                    "eol_date": eol_date,
                    "severity": "eol",
                }
            )
        else:
            suggested = get_suggested_version(runtime_type)
            if suggested and not version.startswith(suggested):
                suggestions.append(
                    {
                        "runtime": runtime,
                        "runtime_type": runtime_type,
                        "version": version,
                        "suggested": suggested,
                        "severity": "outdated",
                    }
                )

    return {
        "repo": repo_name,
        "file": file_stem,
        "runtimes": runtimes,
        "issues": issues,
        "suggestions": suggestions,
        "status": "critical" if issues else "warning" if suggestions else "ok",
    }


def format_table(results: list[dict[str, Any]]) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No runtime issues found."

    lines = [
        "| Repository | Status | Runtime | Issue | Details |",
        "|------------|--------|----------|--------|---------|",
    ]

    for r in results:
        repo = r["repo"]

        for issue in r.get("issues", []):
            runtime = issue["runtime"]
            severity = issue["severity"]
            details = f"EOL since {issue['eol_date']}"
            status_icon = "🚨" if severity == "eol" else "⚠️"
            lines.append(f"| {repo} | {status_icon} {severity} | {runtime} | {issue['version']} | {details} |")

        for suggestion in r.get("suggestions", []):
            runtime = suggestion["runtime"]
            severity = suggestion["severity"]
            details = f"Latest: {suggestion['suggested']}"
            status_icon = "⚠️" if severity == "outdated" else "✅"
            lines.append(f"| {repo} | {status_icon} {severity} | {runtime} | {suggestion['version']} | {details} |")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check runtime compatibility and flag EOL runtimes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
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
        return 2

    repo_data = load_all_repos(args.repos_dir)

    if not repo_data:
        if args.json_output:
            print(json.dumps([]))
        else:
            print("No repository files found.")
        return 0

    results = []

    for data in repo_data:
        result = check_runtime_compatibility(data)
        results.append(result)

    if not args.show_all:
        results = [r for r in results if r["status"] in ("warning", "critical")]

    results.sort(key=lambda r: r["status"])

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_table(results))

    has_critical = any(r["status"] == "critical" for r in results)
    has_warning = any(r["status"] == "warning" for r in results)

    if has_critical:
        return 2
    if has_warning:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
