#!/usr/bin/env python3
"""Detect archived status of origin repositories via GitHub API."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from defibrillator import GitHubClient, GitHubHTTPError


def parse_owner_repo(url: str) -> tuple[str, str] | None:
    """Parse owner/repo from a GitHub URL."""
    parsed = urlparse(url)

    if parsed.netloc not in ("github.com", "www.github.com"):
        return None

    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    parts = path.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]

    return None


def today_utc() -> str:
    """Return today's date in UTC as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_repo_yamls(repos_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Load all repo YAML files from directory."""
    yaml_files = sorted(list(repos_dir.glob("*.yaml")) + list(repos_dir.glob("*.yml")))
    results = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                results.append((yaml_file, data))
        except (yaml.YAMLError, OSError):
            pass
    return results


def write_repo_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write repo data back to YAML file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect archived status of origin repositories via GitHub API."
    )
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
        return 0

    repos = load_repo_yamls(repos_dir)

    if not repos:
        if args.json_output:
            print("[]")
        else:
            print("No YAML files found in repos/")
        return 0

    results: list[dict[str, Any]] = []

    with GitHubClient(auth="auto") as client:
        for yaml_path, data in repos:
            origin = data.get("origin", {})
            origin_url = origin.get("url", "")

            parsed = parse_owner_repo(origin_url)
            if not parsed:
                print(
                    f"Warning: Skipping {yaml_path.name}: not a GitHub URL ({origin_url})",
                    file=sys.stderr,
                )
                continue

            owner, repo = parsed

            try:
                repo_info = client.get_json(f"/repos/{owner}/{repo}", use_cache=True)
            except GitHubHTTPError as e:
                print(
                    f"Warning: Skipping {yaml_path.name}: API error {e.status_code} for {owner}/{repo}",
                    file=sys.stderr,
                )
                continue

            is_archived = repo_info.get("archived", False)
            current_archived_date = origin.get("archived_date")

            result: dict[str, Any] = {
                "repo": f"{owner}/{repo}",
                "file": yaml_path.name,
                "was_archived": is_archived,
                "archived_date": current_archived_date,
                "updated": False,
            }

            if is_archived and not current_archived_date:
                new_date = today_utc()
                result["archived_date"] = new_date
                result["updated"] = True

                if args.write:
                    if "origin" not in data:
                        data["origin"] = {}
                    data["origin"]["archived_date"] = new_date
                    write_repo_yaml(yaml_path, data)

            results.append(result)

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        updated_count = sum(1 for r in results if r["updated"])
        archived_count = sum(1 for r in results if r["was_archived"])

        for r in results:
            if r["updated"]:
                action = "updated" if args.write else "would update"
                print(
                    f"🔍 {r['file']}: {r['repo']} is archived ({action} archived_date to {r['archived_date']})"
                )
            elif r["was_archived"]:
                print(
                    f"📦 {r['file']}: {r['repo']} is archived (archived_date already set: {r['archived_date']})"
                )

        print()
        print(
            f"Checked {len(results)} repo(s): {archived_count} archived, {updated_count} {'updated' if args.write else 'need update'}"
        )
        if not args.write and updated_count > 0:
            print("Run with --write to update YAML files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
