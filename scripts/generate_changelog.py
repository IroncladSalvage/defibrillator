#!/usr/bin/env python3
"""Generate changelog from commits between `last_upstream_commit` values."""

import argparse
import sys
from pathlib import Path
from typing import Any

from defibrillator import GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo
from defibrillator.repo_catalog import load_all_repos


def get_commits_since(
    client: GitHubClient,
    owner: str,
    repo: str,
    since_sha: str,
) -> list[dict[str, Any]]:
    """Get commits since a specific SHA.

    Args:
        client: GitHub API client
        owner: Repository owner
        repo: Repository name
        since_sha: Starting commit SHA

    Returns:
        List of commits
    """
    try:
        commits_data = client.get_json(
            f"/repos/{owner}/{repo}/commits",
            params={"sha": since_sha, "per_page": 100},
        )
    except GitHubHTTPError:
        return []

    if not isinstance(commits_data, list):
        return []

    return commits_data


def format_commit(commit: dict[str, Any]) -> str:
    """Format a single commit for the changelog.

    Args:
        commit: Commit data

    Returns:
        Formatted string
    """
    sha = commit.get("sha", "")[:7]
    message = commit.get("commit", {}).get("message", "")
    author = commit.get("commit", {}).get("author", {}).get("name", "Unknown")

    lines = message.split("\n")
    title = lines[0] if lines else message

    return f"- {sha} ({author}): {title}"


def categorize_commits(commits: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Categorize commits by type.

    Args:
        commits: List of commits

    Returns:
        Dictionary of commit types to commit strings
    """
    categories = {
        "features": [],
        "fixes": [],
        "chore": [],
        "docs": [],
        "tests": [],
        "refactor": [],
        "ci": [],
        "other": [],
    }

    for commit in commits:
        message = commit.get("commit", {}).get("message", "").lower()

        if any(prefix in message for prefix in ("feat", "add", "new", "feature")):
            categories["features"].append(format_commit(commit))
        elif any(prefix in message for prefix in ("fix", "bug", "fixes")):
            categories["fixes"].append(format_commit(commit))
        elif any(prefix in message for prefix in ("chore", "update")):
            categories["chore"].append(format_commit(commit))
        elif any(prefix in message for prefix in ("doc", "readme")):
            categories["docs"].append(format_commit(commit))
        elif any(prefix in message for prefix in ("test", "spec")):
            categories["tests"].append(format_commit(commit))
        elif any(prefix in message for prefix in ("refactor", "refactoring", "cleanup")):
            categories["refactor"].append(format_commit(commit))
        elif any(prefix in message for prefix in ("ci", "github", "workflow", "action")):
            categories["ci"].append(format_commit(commit))
        else:
            categories["other"].append(format_commit(commit))

    return categories


def generate_changelog(
    repo_name: str,
    categories: dict[str, list[str]],
    since_commit: str,
) -> str:
    """Generate changelog markdown.

    Args:
        repo_name: Repository name
        categories: Categorized commits
        since_commit: Starting commit SHA

    Returns:
        Markdown string
    """
    lines = [f"# Changelog: {repo_name}", ""]
    lines.append(f"*Since commit `{since_commit[:7]}`*")
    lines.append("")

    section_order = ["features", "fixes", "docs", "tests", "refactor", "ci", "chore", "other"]

    for section in section_order:
        commits = categories.get(section, [])

        if not commits:
            continue

        section_title = section.capitalize()
        lines.append(f"## {section_title}")
        lines.append("")

        for commit in commits:
            lines.append(commit)

        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate changelog from commits.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "outputs" / "changelogs",
        help="Directory to output changelogs",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Specific repo file to process (default: all repos)",
    )

    args = parser.parse_args()

    if not args.repos_dir.exists():
        print(f"Error: repos directory not found: {args.repos_dir}", file=sys.stderr)
        return 2

    repo_data = load_all_repos(args.repos_dir)

    if args.file:
        repo_data = [r for r in repo_data if r.get("_file") == args.file]

    if not repo_data:
        print("No repository files found.")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with GitHubClient() as client:
        for data in repo_data:
            fork = data.get("fork", {})
            origin = data.get("origin", {})
            file_stem = data.get("_file", "unknown")

            fork_url = fork.get("url", "")
            last_upstream = origin.get("last_upstream_commit", "")
            repo_name = fork.get("name", file_stem)

            if not fork_url or not last_upstream:
                continue

            try:
                owner, repo = parse_owner_repo(fork_url)
            except ValueError:
                continue

            try:
                commits = get_commits_since(client, owner, repo, last_upstream)

                if not commits:
                    print(f"Skipping {file_stem}: no commits found since {last_upstream[:7]}")
                    continue

                categories = categorize_commits(commits)
                changelog = generate_changelog(repo_name, categories, last_upstream)

                output_file = args.output_dir / f"{file_stem}.md"
                output_file.write_text(changelog, encoding="utf-8")

                print(f"Generated changelog: {output_file}")
                print(f"  - {len(commits)} commits")

            except (GitHubHTTPError, ValueError):
                continue

    print(f"\nChangelogs written to: {args.output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
