#!/usr/bin/env python3
"""Track GitHub Actions artifact usage and alert when approaching limits."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from defibrillator import GitHubAuthError, GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo
from defibrillator.repo_catalog import load_all_repos

ARTIFACT_LIMITS = {
    "free": {
        "storage_bytes": 2 * 1024 * 1024 * 1024,
        "retention_days": 90,
    },
}


def format_bytes(bytes: int) -> str:
    """Format bytes as human readable string.

    Args:
        bytes: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    value = float(bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def get_artifacts(client: GitHubClient, owner: str, repo: str) -> list[dict[str, Any]]:
    """Get list of artifacts for a repository.

    Args:
        client: GitHub API client
        owner: Repository owner
        repo: Repository name

    Returns:
        List of artifacts with metadata
    """
    try:
        artifacts_data = client.get_json(
            f"/repos/{owner}/{repo}/actions/artifacts",
            params={"per_page": 100},
        )
    except GitHubHTTPError:
        return []

    if not isinstance(artifacts_data, dict):
        return []

    artifacts = artifacts_data.get("artifacts", [])

    result = []

    for artifact in artifacts:
        created_at = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
        expires_at = (
            datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
            if artifact.get("expires_at")
            else None
        )

        result.append(
            {
                "id": artifact["id"],
                "name": artifact["name"],
                "size_bytes": artifact["size_in_bytes"],
                "created_at": created_at,
                "expires_at": expires_at,
                "expired": expires_at is not None and expires_at < datetime.now(UTC),
            }
        )

    return result


def calculate_repo_usage(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate storage usage for a repository.

    Args:
        artifacts: List of artifacts

    Returns:
        Dictionary with usage statistics
    """
    total_size = sum(a["size_bytes"] for a in artifacts if not a["expired"])
    expired_size = sum(a["size_bytes"] for a in artifacts if a["expired"])
    expired_count = sum(1 for a in artifacts if a["expired"])
    active_count = sum(1 for a in artifacts if not a["expired"])

    return {
        "total_size_bytes": total_size,
        "total_size_formatted": format_bytes(total_size),
        "expired_size_bytes": expired_size,
        "expired_size_formatted": format_bytes(expired_size),
        "expired_count": expired_count,
        "active_count": active_count,
    }


def format_table(results: list[dict[str, Any]], limits: dict[str, Any]) -> str:
    """Format results as a human-readable table.

    Args:
        results: Artifact usage results
        limits: Usage limits

    Returns:
        Formatted table string
    """
    if not results:
        return "No artifacts found."

    lines = [
        "| Repository | Active Artifacts | Expired Artifacts | Storage Used | % of Limit |",
        "|------------|-----------------|-------------------|--------------|-------------|",
    ]

    limit_bytes = limits["free"]["storage_bytes"]
    limit_formatted = format_bytes(limit_bytes)

    for r in results:
        repo = r["repo"]
        active = r["usage"]["active_count"]
        expired = r["usage"]["expired_count"]
        used = r["usage"]["total_size_formatted"]
        used_bytes = r["usage"]["total_size_bytes"]
        percent = (used_bytes / limit_bytes * 100) if limit_bytes > 0 else 0

        warning = " 🚨" if percent > 80 else " ⚠️" if percent > 50 else ""

        lines.append(f"| {repo} | {active} | {expired} | {used} | {percent:.1f}%{warning} |")

    lines.append("")
    lines.append(f"**Free Tier Limit:** {limit_formatted}")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Track GitHub Actions artifact usage.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--org",
        type=str,
        default="IroncladSalvage",
        help="Organization name for repository lookup",
    )
    parser.add_argument(
        "--warning-percent",
        type=int,
        default=50,
        help="Warning threshold percentage of limit",
    )
    parser.add_argument(
        "--critical-percent",
        type=int,
        default=80,
        help="Critical threshold percentage of limit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output in JSON format",
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

    limits = ARTIFACT_LIMITS
    results = []

    with GitHubClient(auth="auto") as client:
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

            try:
                artifacts = get_artifacts(client, owner, repo)
                usage = calculate_repo_usage(artifacts)

                results.append(
                    {
                        "repo": repo_name,
                        "file": file_stem,
                        "usage": usage,
                    }
                )
            except (GitHubHTTPError, GitHubAuthError):
                continue

    results.sort(key=lambda r: r["usage"]["total_size_bytes"], reverse=True)

    limit_bytes = limits["free"]["storage_bytes"]
    total_used = sum(r["usage"]["total_size_bytes"] for r in results)
    total_percent = (total_used / limit_bytes * 100) if limit_bytes > 0 else 0

    if args.json_output:
        print(json.dumps({"results": results, "limits": limits, "total_percent": total_percent}, indent=2))
    else:
        print("## Artifact Storage Usage")
        print("")
        print(f"**Total Used:** {format_bytes(total_used)} / {format_bytes(limit_bytes)} ({total_percent:.1f}%)")
        print("")
        print(format_table(results, limits))

    if total_percent >= args.critical_percent:
        return 2
    if total_percent >= args.warning_percent:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
