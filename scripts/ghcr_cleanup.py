#!/usr/bin/env python3
"""Prune old container images from GHCR to stay within free tier limits."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from defibrillator import GitHubAuthError, GitHubClient, GitHubHTTPError
from defibrillator.repo_catalog import load_all_repos


def get_container_images(client: GitHubClient, owner: str, repo: str) -> list[dict[str, Any]]:
    """Get list of container image versions for a repository.

    Args:
        client: GitHub API client
        owner: Repository owner
        repo: Repository name

    Returns:
        List of image versions with metadata
    """
    try:
        packages = client.get_json(
            f"/orgs/{owner}/packages",
            params={"package_type": "container", "package_name": repo},
        )
    except GitHubHTTPError:
        return []

    if not packages:
        return []

    try:
        versions_data = client.get_json(
            f"/orgs/{owner}/packages/container/{repo}/versions",
            params={"per_page": 100},
        )
    except GitHubHTTPError:
        return []

    if not isinstance(versions_data, list):
        return []

    versions = []

    for version in versions_data:
        created_at = datetime.fromisoformat(version["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(version["updated_at"].replace("Z", "+00:00"))
        metadata = version.get("metadata", {})

        versions.append(
            {
                "id": version["id"],
                "name": metadata.get("container", {}).get("tags", ["untagged"])[0],
                "created_at": created_at,
                "updated_at": updated_at,
                "size_bytes": metadata.get("package_type", "").count("container") * 0,
            }
        )

    return versions


def should_delete(
    version: dict[str, Any],
    keep_days: int,
    keep_count: int,
    all_versions: list[dict[str, Any]],
) -> bool:
    """Determine if an image version should be deleted.

    Args:
        version: Image version metadata
        keep_days: Minimum age in days before considering deletion
        keep_count: Minimum number of versions to keep
        all_versions: All versions for sorting

    Returns:
        True if the version should be deleted
    """
    created_at = version["created_at"]
    age_days = (datetime.now(UTC) - created_at).days

    if age_days < keep_days:
        return False

    sorted_versions = sorted(all_versions, key=lambda v: v["created_at"], reverse=True)
    version_index = next((i for i, v in enumerate(sorted_versions) if v["id"] == version["id"]), -1)

    if version_index < keep_count:
        return False

    return True


def delete_image_version(
    client: GitHubClient,
    org: str,
    repo: str,
    version_id: int,
    dry_run: bool = False,
) -> bool:
    """Delete a container image version.

    Args:
        client: GitHub API client
        org: Organization name
        repo: Repository name
        version_id: Image version ID
        dry_run: If True, don't actually delete

    Returns:
        True if deleted or dry run
    """
    if dry_run:
        return True

    try:
        client.request(
            "DELETE",
            f"/orgs/{org}/packages/container/{repo}/versions/{version_id}",
            auth="required",
            expected=(204,),
        )
        return True
    except (GitHubHTTPError, GitHubAuthError):
        return False


def format_table(results: list[dict[str, Any]], dry_run: bool) -> str:
    """Format results as a human-readable table.

    Args:
        results: Cleanup results
        dry_run: Whether this was a dry run

    Returns:
        Formatted table string
    """
    if not results:
        return "No images to clean up."

    action = "would delete" if dry_run else "deleted"

    lines = [
        "| Repository | Image | Age (days) | Action |",
        "|------------|--------|-----------|--------|",
    ]

    for r in results:
        repo = r["repo"]
        image = r.get("image", "untagged")
        age = r.get("age_days", 0)
        lines.append(f"| {repo} | {image} | {age} | {action} |")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prune old container images from GHCR.",
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
        help="Organization name for container registry",
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=30,
        help="Minimum age in days before considering deletion",
    )
    parser.add_argument(
        "--keep-count",
        type=int,
        default=3,
        help="Minimum number of versions to keep",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
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
        print("No repository files found.")
        return 0

    if args.dry_run:
        print(f"DRY RUN: Would delete images older than {args.keep_days} days (keeping {args.keep_count} versions)")
        print("")

    results = []

    with GitHubClient(auth="required") as client:
        for data in repo_data:
            fork = data.get("fork", {})
            artifacts = data.get("artifacts", {})
            docker = artifacts.get("docker", {})

            if not docker.get("enabled"):
                continue

            file_stem = data.get("_file", "unknown")
            repo_name = fork.get("name", file_stem)

            try:
                versions = get_container_images(client, args.org, repo_name)
            except (GitHubHTTPError, GitHubAuthError):
                continue

            to_delete = [v for v in versions if should_delete(v, args.keep_days, args.keep_count, versions)]

            for version in to_delete:
                age_days = (datetime.now(UTC) - version["created_at"]).days

                result = {
                    "repo": repo_name,
                    "image": version.get("name", "untagged"),
                    "version_id": version["id"],
                    "age_days": age_days,
                    "deleted": False,
                }

                deleted = delete_image_version(client, args.org, repo_name, version["id"], args.dry_run)

                if deleted:
                    result["deleted"] = True
                    results.append(result)
                    print(f"Deleted {repo_name} image {version.get('name', 'untagged')} ({age_days} days old)")

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        if results:
            print("")
            print(format_table(results, args.dry_run))

        print(f"\nCleaned up {len(results)} image(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
