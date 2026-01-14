#!/usr/bin/env python3
"""Monitor upstream repositories for new commits."""

import argparse
import json
import sys
from pathlib import Path

from defibrillator import GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo
from defibrillator.repo_catalog import load_all_repos
from defibrillator.upstream import get_upstream_head, is_behind_upstream


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Monitor upstream repositories for new commits."
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=None,
        help="Directory containing repo YAML files (default: repos/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    parser.add_argument(
        "--fail-on-updates",
        action="store_true",
        help="Exit 1 if any repo has upstream commits",
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    repos_dir = args.repos_dir or (base_dir / "repos")

    if not repos_dir.exists():
        print(f"Error: repos directory not found: {repos_dir}", file=sys.stderr)
        return 2

    repo_data = load_all_repos(repos_dir)

    if not repo_data:
        if args.json_output:
            print("[]")
        else:
            print("No YAML files found in repos/")
        return 0

    results = []
    has_updates = False

    with GitHubClient() as client:
        for data in repo_data:
            origin = data.get("origin", {})
            origin_url = origin.get("url", "")
            stored_sha = origin.get("last_upstream_commit", "")
            repo_name = origin.get("name", data.get("_file", "unknown"))
            yaml_file = data.get("_file", "unknown")

            try:
                owner, repo = parse_owner_repo(origin_url)
            except ValueError:
                print(
                    f"Warning: skipping {yaml_file} - not a GitHub URL: {origin_url}",
                    file=sys.stderr,
                )
                continue

            try:
                _, upstream_sha = get_upstream_head(client, owner, repo)
            except GitHubHTTPError as e:
                print(
                    f"Warning: could not fetch upstream HEAD for {owner}/{repo}: {e}",
                    file=sys.stderr,
                )
                continue

            repo_has_updates = is_behind_upstream(stored_sha, upstream_sha)
            if repo_has_updates:
                has_updates = True

            results.append({
                "repo": repo_name,
                "file": yaml_file,
                "stored_sha": stored_sha,
                "upstream_sha": upstream_sha,
                "has_updates": repo_has_updates,
                "origin_url": origin_url,
            })

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No repositories to check.")
            return 0

        name_width = max(len(r["repo"]) for r in results)
        print(f"{'REPO':<{name_width}}  STORED       UPSTREAM     STATUS")
        print("-" * (name_width + 42))

        for r in results:
            stored_short = r["stored_sha"][:12] if r["stored_sha"] else "N/A"
            upstream_short = r["upstream_sha"][:12] if r["upstream_sha"] else "N/A"
            status = "UPDATES" if r["has_updates"] else "current"
            print(f"{r['repo']:<{name_width}}  {stored_short:<12} {upstream_short:<12} {status}")

        print()
        updates_count = sum(1 for r in results if r["has_updates"])
        if updates_count:
            print(f"{updates_count} repo(s) have upstream updates available.")
        else:
            print("All repos are up to date.")

    if args.fail_on_updates and has_updates:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
