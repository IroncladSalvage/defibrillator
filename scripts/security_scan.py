#!/usr/bin/env python3
"""Integrate with GitHub security scanning and report findings."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from defibrillator import GitHubAuthError, GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo
from defibrillator.repo_catalog import load_all_repos


def get_security_summary(client: GitHubClient, owner: str, repo: str) -> dict[str, Any]:
    """Get security summary for a repository.

    Args:
        client: GitHub API client
        owner: Repository owner
        repo: Repository name

    Returns:
        Dictionary with vulnerability counts and details
    """
    summary = {
        "dependabot_alerts": [],
        "dependabot_count": 0,
        "code_scanning_alerts": [],
        "code_scanning_count": 0,
    }

    try:
        alerts_data = client.get_json(f"/repos/{owner}/{repo}/dependabot/alerts", auth="auto")
        alerts = alerts_data if isinstance(alerts_data, list) else []
        summary["dependabot_alerts"] = [
            {
                "id": a.get("id"),
                "severity": a.get("security_advisory", {}).get("severity", "unknown"),
                "package": a.get("dependency", {}).get("package", {}).get("name", "unknown"),
                "state": a.get("state", "unknown"),
            }
            for a in alerts
            if a.get("state") != "dismissed"
        ]
        summary["dependabot_count"] = len(summary["dependabot_alerts"])
    except (GitHubHTTPError, GitHubAuthError):
        pass

    try:
        scanning_data = client.get_json(
            f"/repos/{owner}/{repo}/code-scanning/alerts",
            params={"per_page": 100},
            auth="auto",
        )
        alerts = scanning_data if isinstance(scanning_data, list) else []
        summary["code_scanning_alerts"] = [
            {
                "id": a.get("id"),
                "severity": a.get("rule", {}).get("severity", "unknown"),
                "name": a.get("rule", {}).get("name", "unknown"),
                "state": a.get("state", "unknown"),
            }
            for a in alerts
            if a.get("state") in ("open", "fixed")
        ]
        summary["code_scanning_count"] = len(summary["code_scanning_alerts"])
    except (GitHubHTTPError, GitHubAuthError):
        pass

    return summary


def calculate_security_status(summary: dict[str, Any]) -> str:
    """Calculate overall security status.

    Args:
        summary: Security summary

    Returns:
        One of "critical", "warning", "ok"
    """
    critical_vulns = sum(1 for a in summary["dependabot_alerts"] if a["severity"] in ("critical", "high"))

    if critical_vulns > 0:
        return "critical"

    total_issues = summary["dependabot_count"] + summary["code_scanning_count"]
    if total_issues > 0:
        return "warning"

    return "ok"


def format_table(results: list[dict[str, Any]]) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No security issues found."

    lines = [
        "| Repository | Status | Dependabot Alerts | Code Scanning | Total Issues |",
        "|------------|--------|-------------------|---------------|--------------|",
    ]

    for r in results:
        repo = r["repo"]
        status = r["status"]
        dependabot = r["dependabot_count"]
        code_scanning = r["code_scanning_count"]
        total = dependabot + code_scanning

        status_icons = {"critical": "🚨", "warning": "⚠️", "ok": "✅"}

        lines.append(f"| {repo} | {status_icons.get(status, '')} {status} | {dependabot} | {code_scanning} | {total} |")

    return "\n".join(lines)


def format_details(results: list[dict[str, Any]]) -> str:
    """Format detailed findings.

    Args:
        results: Security scan results

    Returns:
        Markdown string with detailed findings
    """
    lines = ["# Security Scan Details", ""]

    for r in results:
        if r["status"] == "ok":
            continue

        lines.append(f"## {r['repo']}")
        lines.append("")

        if r["dependabot_alerts"]:
            lines.append("### Dependabot Alerts")
            lines.append("")
            for alert in r["dependabot_alerts"]:
                pkg = alert["package"]
                sev = alert["severity"]
                state = alert["state"]
                lines.append(f"- **{pkg}**: {sev} severity ({state})")
            lines.append("")

        if r["code_scanning_alerts"]:
            lines.append("### Code Scanning Alerts")
            lines.append("")
            for alert in r["code_scanning_alerts"][:5]:
                name = alert["name"]
                sev = alert["severity"]
                state = alert["state"]
                lines.append(f"- **{name}**: {sev} severity ({state})")
            if len(r["code_scanning_alerts"]) > 5:
                lines.append(f"- ... and {len(r['code_scanning_alerts']) - 5} more")
            lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Integrate with GitHub security scanning and report findings.",
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
        default=None,
        help="Output file for detailed report",
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

    with GitHubClient() as client:
        for data in repo_data:
            fork = data.get("fork", {})
            fork_url = fork.get("url", "")
            file_stem = data.get("_file", "unknown")
            repo_name = fork.get("name", file_stem)

            if not fork_url:
                continue

            try:
                owner, repo = parse_owner_repo(fork_url)
            except ValueError:
                continue

            summary = get_security_summary(client, owner, repo)
            status = calculate_security_status(summary)

            results.append(
                {
                    "repo": repo_name,
                    "file": file_stem,
                    "status": status,
                    **summary,
                }
            )

    if not args.show_all:
        results = [r for r in results if r["status"] in ("warning", "critical")]

    results.sort(key=lambda r: r["status"])

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_table(results))

        if args.output:
            details = format_details(results)
            args.output.write_text(details, encoding="utf-8")
            print(f"\nDetailed report written to: {args.output}")

    has_critical = any(r["status"] == "critical" for r in results)
    has_warning = any(r["status"] == "warning" for r in results)

    if has_critical:
        return 2
    if has_warning:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
