#!/usr/bin/env python3
"""Check for Docker base image updates."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

from defibrillator.repo_catalog import load_all_repos


def parse_base_image_from_dockerfile(dockerfile_path: Path) -> str | None:
    """Extract base image FROM a Dockerfile.

    Args:
        dockerfile_path: Path to Dockerfile

    Returns:
        Base image name (e.g., "python:3.11") or None
    """
    if not dockerfile_path.exists():
        return None

    with open(dockerfile_path, encoding="utf-8") as f:
        for line in f:
            match = re.match(r"^\s*FROM\s+([^\s#]+)", line)
            if match:
                return match.group(1)

    return None


def get_latest_tag(image_name: str, timeout: float = 10.0) -> str | None:
    """Get latest tag for a Docker image from Docker Hub API.

    Args:
        image_name: Image name (e.g., "python" or "alpine")
        timeout: Request timeout in seconds

    Returns:
        Latest tag or None if unavailable
    """
    try:
        url = f"https://hub.docker.com/v2/repositories/{image_name}/tags"
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        tags = data.get("results", [])

        if not tags:
            return None

        return tags[0].get("name")
    except (requests.RequestException, KeyError):
        return None


def parse_image_name(image_ref: str) -> tuple[str, str | None]:
    """Parse Docker image reference into name and tag.

    Args:
        image_ref: Image reference (e.g., "python:3.11", "alpine:latest")

    Returns:
        Tuple of (image_name, tag)
    """
    parts = image_ref.split(":")
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], None


def check_base_image(base_image: str) -> dict[str, Any]:
    """Check if a base image has updates available.

    Args:
        base_image: Base image reference

    Returns:
        Dictionary with current_tag, latest_tag, and update_available
    """
    image_name, current_tag = parse_image_name(base_image)

    if not current_tag or current_tag == "latest":
        return {
            "image": base_image,
            "current_tag": current_tag,
            "latest_tag": None,
            "update_available": False,
            "message": "No version specified or using latest",
        }

    latest_tag = get_latest_tag(image_name)

    if not latest_tag:
        return {
            "image": base_image,
            "current_tag": current_tag,
            "latest_tag": None,
            "update_available": False,
            "message": "Could not fetch latest tag",
        }

    update_available = current_tag != latest_tag

    return {
        "image": base_image,
        "current_tag": current_tag,
        "latest_tag": latest_tag,
        "update_available": update_available,
        "message": "" if update_available else "Up to date",
    }


def get_base_image_from_yaml(data: dict) -> str | None:
    """Get base image from YAML data (docker.image field).

    Args:
        data: Repository YAML data

    Returns:
        Base image name or None
    """
    docker = data.get("artifacts", {}).get("docker", {})
    image = docker.get("image", "")

    if not image:
        return None

    parts = image.rsplit("/", 1)
    if len(parts) == 2:
        return parts[1]
    return image


def format_table(results: list[dict[str, Any]]) -> str:
    """Format results as a human-readable table."""
    if not results:
        return "No Docker base images found."

    lines = [
        "| Repository | Base Image | Current | Latest | Update Available |",
        "|------------|-------------|---------|---------|------------------|",
    ]

    for r in results:
        repo = r["repo"]
        image = r.get("image", "N/A")
        current = r.get("current_tag", "N/A")
        latest = r.get("latest_tag", "N/A")
        available = "Yes" if r.get("update_available") else "No"

        lines.append(f"| {repo} | {image} | {current} | {latest} | {available} |")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check for Docker base image updates.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--dockerfile-dir",
        type=Path,
        default=None,
        help="Directory containing Dockerfiles (for Dockerfile-based repos)",
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
        help="Show all repos including up to date",
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
        file_stem = data.get("_file", "unknown")
        fork = data.get("fork", {})
        artifacts = data.get("artifacts", {})
        docker = artifacts.get("docker", {})

        if not docker.get("enabled"):
            continue

        repo_name = fork.get("name", file_stem)

        base_image = get_base_image_from_yaml(data)
        dockerfile_dir = args.dockerfile_dir

        if dockerfile_dir:
            dockerfile_path = dockerfile_dir / file_stem / "Dockerfile"
            dockerfile_image = parse_base_image_from_dockerfile(dockerfile_path)
            if dockerfile_image:
                base_image = dockerfile_image

        if not base_image:
            continue

        check_result = check_base_image(base_image)
        check_result["repo"] = repo_name
        check_result["file"] = file_stem

        results.append(check_result)

    if not args.show_all:
        results = [r for r in results if r.get("update_available")]

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        print(format_table(results))

        has_updates = any(r.get("update_available") for r in results)
        if has_updates:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
