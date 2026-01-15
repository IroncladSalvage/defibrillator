#!/usr/bin/env python3
"""Generate upstream divergence report showing how far behind each fork is."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from defibrillator import GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo
from defibrillator.repo_catalog import load_all_repos
from defibrillator.upstream import get_upstream_head


def get_commit_count(client: GitHubClient, owner: str, repo: str, base_sha: str) -> tuple[int, str]:
    """Get the number of commits since base_sha and the date of the last commit.

    Returns:
        Tuple of (commit_count, last_commit_date).
    """
    try:
        _, head_sha = get_upstream_head(client, owner, repo)
    except GitHubHTTPError:
        return 0, ""

    if not head_sha or not base_sha:
        return 0, ""

    try:
        compare_data = client.get_json(f"/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}")
    except GitHubHTTPError:
        return 0, ""

    commits_ahead = compare_data.get("ahead_by", 0)

    commits = compare_data.get("commits", [])
    last_commit_date = commits[0]["commit"]["committer"]["date"][:10] if commits else ""

    return commits_ahead, last_commit_date


def get_divergence_significance(commits_behind: int, warning_threshold: int = 50, critical_threshold: int = 100) -> str:
    """Determine the significance of divergence.

    Returns:
        One of "ok", "warning", or "critical".
    """
    if commits_behind >= critical_threshold:
        return "critical"
    elif commits_behind >= warning_threshold:
        return "warning"
    return "ok"


def format_table(results: list[dict[str, Any]], show_all: bool = False) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No repositories found."

    lines = [
        "| Repository | Behind | Last Commit | Significance |",
        "|------------|---------|-------------|---------------|",
    ]

    severity_icons = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}

    for r in results:
        if not show_all and r["significance"] == "ok":
            continue

        behind = r["commits_behind"]
        last_commit = r["last_commit_date"] if r["last_commit_date"] else "N/A"
        icon = severity_icons.get(r["significance"], "")
        lines.append(f"| {r['repo_name']} | {behind} | {last_commit} | {icon} {r['significance']} |")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate upstream divergence report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--warning-commits",
        type=int,
        default=50,
        help="Commits behind threshold for warning severity",
    )
    parser.add_argument(
        "--critical-commits",
        type=int,
        default=100,
        help="Commits behind threshold for critical severity",
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
            origin = data.get("origin", {})
            origin_url = origin.get("url", "")
            base_sha = origin.get("last_upstream_commit", "")
            file_stem = data.get("_file", "")
            repo_name = origin.get("name", file_stem)

            if not origin_url or not base_sha:
                results.append(
                    {
                        "repo_name": repo_name,
                        "file_stem": file_stem,
                        "commits_behind": 0,
                        "last_commit_date": None,
                        "significance": "critical",
                        "upstream_url": origin_url,
                    }
                )
                continue

            try:
                owner, repo = parse_owner_repo(origin_url)
            except ValueError:
                results.append(
                    {
                        "repo_name": repo_name,
                        "file_stem": file_stem,
                        "commits_behind": 0,
                        "last_commit_date": None,
                        "significance": "critical",
                        "upstream_url": origin_url,
                    }
                )
                continue

            try:
                commits_behind, last_commit_date = get_commit_count(client, owner, repo, base_sha)
            except GitHubHTTPError:
                results.append(
                    {
                        "repo_name": repo_name,
                        "file_stem": file_stem,
                        "commits_behind": 0,
                        "last_commit_date": None,
                        "significance": "critical",
                        "upstream_url": origin_url,
                    }
                )
                continue

            significance = get_divergence_significance(
                commits_behind,
                args.warning_commits,
                args.critical_commits,
            )

            results.append(
                {
                    "repo_name": repo_name,
                    "file_stem": file_stem,
                    "commits_behind": commits_behind,
                    "last_commit_date": last_commit_date,
                    "significance": significance,
                    "upstream_url": origin_url,
                }
            )

    results.sort(key=lambda r: r["commits_behind"], reverse=True)

    if not args.show_all:
        results = [r for r in results if r["significance"] in ("warning", "critical")]

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_table(results, args.show_all))

    has_critical = any(r["significance"] == "critical" for r in results)
    has_warning = any(r["significance"] == "warning" for r in results)

    if has_critical:
        return 2
    if has_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
