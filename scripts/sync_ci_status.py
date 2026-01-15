#!/usr/bin/env python3
"""Sync CI status from GitHub Actions to repository YAML files."""

import argparse
import json
import sys
from pathlib import Path

from defibrillator import GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo
from defibrillator.repo_catalog import load_all_repos, write_repo


def get_ci_status(client: GitHubClient, owner: str, repo: str) -> str:
    """Get the CI status from GitHub Actions workflow runs.

    Returns:
        One of "passing", "failing", or "unknown".
    """
    try:
        runs = client.get_json(f"/repos/{owner}/{repo}/actions/runs", params={"per_page": 1})
    except GitHubHTTPError:
        return "unknown"

    if not runs.get("workflow_runs"):
        return "unknown"

    latest_run = runs["workflow_runs"][0]
    conclusion = latest_run.get("conclusion", "")

    if conclusion == "success":
        return "passing"
    elif conclusion in ("failure", "cancelled", "timed_out", "action_required"):
        return "failing"
    else:
        status = latest_run.get("status", "")
        if status == "completed":
            return "passing"
        return "unknown"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync CI status from GitHub Actions.")
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=None,
        help="Directory containing repo YAML files (default: repos/)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually update YAML files (default: dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output JSON format",
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

    with GitHubClient() as client:
        for data in repo_data:
            fork = data.get("fork", {})
            fork_url = fork.get("url", "")
            file_path = data.get("_path")
            file_name = data.get("_file", "unknown")
            repo_name = fork.get("name", file_name)

            if not fork_url:
                results.append(
                    {
                        "repo": repo_name,
                        "file": file_name,
                        "fork_url": "",
                        "ci_status": "unknown",
                        "previous_status": "",
                        "updated": False,
                    }
                )
                continue

            try:
                owner, repo = parse_owner_repo(fork_url)
            except ValueError:
                print(
                    f"Warning: skipping {file_name} - not a GitHub URL: {fork_url}",
                    file=sys.stderr,
                )
                continue

            ci_status = get_ci_status(client, owner, repo)
            previous_status = data.get("status", {}).get("ci_status", "")

            result = {
                "repo": repo_name,
                "file": file_name,
                "fork_url": fork_url,
                "ci_status": ci_status,
                "previous_status": previous_status,
                "updated": False,
            }

            if ci_status != previous_status:
                result["updated"] = True

                if args.write and file_path:
                    if "status" not in data:
                        data["status"] = {}
                    data["status"]["ci_status"] = ci_status
                    write_repo(Path(file_path), data)

            results.append(result)

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No repositories to check.")
            return 0

        updated_count = sum(1 for r in results if r["updated"])
        passing_count = sum(1 for r in results if r["ci_status"] == "passing")
        failing_count = sum(1 for r in results if r["ci_status"] == "failing")
        unknown_count = sum(1 for r in results if r["ci_status"] == "unknown")

        for r in results:
            if r["updated"]:
                action = "updated" if args.write else "would update"
                print(f"🔄 {r['file']}: {r['repo']} {action} ci_status {r['previous_status']} -> {r['ci_status']}")

        print()
        print(f"Checked {len(results)} repo(s):")
        print(f"  ✅ Passing: {passing_count}")
        print(f"  ❌ Failing: {failing_count}")
        print(f"  ❓ Unknown: {unknown_count}")
        print(f"  🔄 Updated: {updated_count}")

        if not args.write and updated_count > 0:
            print()
            print("Run with --write to update YAML files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
