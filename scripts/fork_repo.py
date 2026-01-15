#!/usr/bin/env python3
"""Automate forking repositories and generating YAML configuration."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from defibrillator import GitHubAuthError, GitHubClient, GitHubHTTPError
from defibrillator.github_url import parse_owner_repo

ORGANIZATION = "IroncladSalvage"


def get_repo_metadata(client: GitHubClient, owner: str, repo: str) -> dict[str, Any]:
    """Fetch metadata for a repository.

    Returns:
        Dictionary with license, languages, description, etc.
    """
    repo_data = client.get_json(f"/repos/{owner}/{repo}")

    languages_data = client.get_json(f"/repos/{owner}/{repo}/languages")

    languages = sorted(languages_data.keys(), key=lambda x: languages_data[x], reverse=True)

    license_info = repo_data.get("license", {})
    license_spdx = license_info.get("spdx_id", license_info.get("key", ""))

    metadata = {
        "description": repo_data.get("description", ""),
        "languages": languages,
        "license": license_spdx,
        "default_branch": repo_data.get("default_branch", "master"),
        "is_archived": repo_data.get("archived", False),
        "repo_name": repo_data.get("name", ""),
    }

    return metadata


def fork_repository(client: GitHubClient, owner: str, repo: str) -> dict[str, Any]:
    """Fork a repository to the organization.

    Returns:
        Dictionary with fork information.
    """
    response = client.request("POST", f"/repos/{owner}/{repo}/forks", expected=(202,))
    fork_data = response.json()

    return {
        "fork_name": fork_data.get("name", ""),
        "fork_url": fork_data.get("html_url", ""),
        "full_name": fork_data.get("full_name", ""),
    }


def generate_yaml_from_template(
    upstream_url: str,
    upstream_name: str,
    fork_url: str,
    fork_name: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Generate repository YAML configuration from metadata.

    Args:
        upstream_url: Original repository URL
        upstream_name: Original project name
        fork_url: Fork repository URL
        fork_name: Fork name
        metadata: Repository metadata

    Returns:
        Dictionary representing the YAML configuration.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    yaml_data = {
        "origin": {
            "url": upstream_url,
            "name": upstream_name,
            "last_upstream_commit": "",
            "archived_date": today if metadata["is_archived"] else None,
            "license": metadata["license"],
        },
        "fork": {
            "url": fork_url,
            "name": fork_name,
            "created_at": today,
        },
        "status": {
            "state": "active",
            "last_touched": today,
            "ci_status": "unknown",
            "notes": "Initial fork and CI setup",
        },
        "languages": metadata["languages"],
        "targets": {
            "architectures": ["amd64", "arm64"],
            "runtimes": [],
            "operating_systems": ["linux"],
        },
        "artifacts": {
            "docker": {"enabled": False, "image": ""},
            "packages": {
                "debian": False,
                "alpine": False,
                "pypi": False,
                "npm": False,
            },
        },
        "automation": {
            "dependabot": True,
            "security_scanning": True,
            "auto_release": False,
        },
        "metadata": {
            "description": metadata["description"],
            "tags": [],
            "priority": "normal",
            "upstream_maintainer_contact": "",
        },
    }

    return yaml_data


def write_yaml_file(path: Path, data: dict[str, Any]) -> None:
    """Write YAML data to a file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fork repository and generate YAML configuration.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "url",
        help="Upstream repository URL to fork",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually fork, just show what would happen",
    )

    args = parser.parse_args()

    repos_dir = args.repos_dir
    repos_dir.mkdir(parents=True, exist_ok=True)

    try:
        owner, repo = parse_owner_repo(args.url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"DRY RUN: Would fork {owner}/{repo} to {ORGANIZATION}")
        print(f"DRY RUN: Would generate YAML file in {repos_dir}")
        return 0

    try:
        with GitHubClient(auth="required") as client:
            print(f"Fetching metadata for {owner}/{repo}...")
            metadata = get_repo_metadata(client, owner, repo)

            print(f"Languages: {', '.join(metadata['languages'][:5])}")
            print(f"License: {metadata['license'] or 'None'}")
            print(f"Archived: {metadata['is_archived']}")

            print(f"Forking to {ORGANIZATION}...")
            fork_info = fork_repository(client, owner, repo)

            print(f"Fork created: {fork_info['fork_url']}")

            yaml_data = generate_yaml_from_template(
                upstream_url=args.url,
                upstream_name=metadata["repo_name"],
                fork_url=fork_info["fork_url"],
                fork_name=fork_info["fork_name"],
                metadata=metadata,
            )

            output_path = repos_dir / f"{fork_info['fork_name']}.yaml"
            write_yaml_file(output_path, yaml_data)

            print(f"Generated YAML: {output_path}")
            print(f"  - Origin: {yaml_data['origin']['name']}")
            print(f"  - Fork: {yaml_data['fork']['name']}")
            print(f"  - Languages: {', '.join(yaml_data['languages'])}")

            return 0

    except GitHubAuthError:
        print(
            "Error: GitHub token required for forking repositories. Set GITHUB_TOKEN or GH_TOKEN environment variable.",
            file=sys.stderr,
        )
        return 1
    except GitHubHTTPError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
