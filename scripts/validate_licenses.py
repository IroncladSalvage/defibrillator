#!/usr/bin/env python3
"""Validate repository license files against YAML declarations."""

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from defibrillator import GitHubClient, GitHubHTTPError

LICENSE_SIGNATURES = {
    "MIT": [
        "permission is hereby granted, free of charge, to any person obtaining a copy",
    ],
    "Apache-2.0": [
        "licensed under the apache license, version 2.0",
        "http://www.apache.org/licenses/license",
    ],
    "GPL-3.0": [
        "gnu general public license version 3",
        "gnu general public license, version 3",
    ],
    "GPL-2.0": [
        "gnu general public license version 2",
        "gnu general public license, version 2",
    ],
    "BSD-3-Clause": [
        "redistribution and use in source and binary forms",
        "neither the name of",
    ],
    "BSD-2-Clause": [
        "redistribution and use in source and binary forms",
    ],
    "Unlicense": [
        "this is free and unencumbered software released into the public domain",
    ],
    "ISC": [
        "permission to use, copy, modify, and/or distribute this software",
    ],
    "MPL-2.0": [
        "mozilla public license version 2.0",
    ],
    "LGPL-3.0": [
        "gnu lesser general public license version 3",
    ],
}


def normalize_text(text: str) -> str:
    """Normalize license text for comparison."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_license_from_text(text: str) -> tuple[str | None, str]:
    """Detect license from text content using heuristics."""
    normalized = normalize_text(text)

    matches = []
    for spdx_id, signatures in LICENSE_SIGNATURES.items():
        if all(sig in normalized for sig in signatures):
            matches.append(spdx_id)

    if len(matches) == 1:
        return matches[0], "high"
    elif len(matches) > 1:
        if "BSD-3-Clause" in matches and "BSD-2-Clause" in matches:
            if "neither the name of" in normalized:
                return "BSD-3-Clause", "high"
            else:
                return "BSD-2-Clause", "medium"
        return matches[0], "low"

    return None, "none"


def parse_github_url(url: str) -> tuple[str, str] | None:
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


def fetch_license_spdx(client: GitHubClient, owner: str, repo: str) -> tuple[str | None, str, str]:
    """Fetch license SPDX ID from GitHub API.

    Returns: (spdx_id, source, details)
    """
    try:
        data = client.get_json(f"/repos/{owner}/{repo}/license", use_cache=True)
        license_info = data.get("license", {})
        spdx_id = license_info.get("spdx_id")

        if spdx_id and spdx_id not in ("NOASSERTION", "OTHER"):
            return spdx_id, "github_api", ""

        content_b64 = data.get("content", "")
        if content_b64:
            try:
                license_text = base64.b64decode(content_b64).decode("utf-8")
                detected, confidence = detect_license_from_text(license_text)
                if detected and confidence in ("high", "medium"):
                    return detected, "heuristic", f"confidence={confidence}"
            except Exception:
                pass

        return spdx_id or "UNKNOWN", "github_api", "could not detect"

    except GitHubHTTPError as e:
        if e.status_code == 404:
            return None, "missing", "no LICENSE file found"
        raise


def validate_license(yaml_path: Path, client: GitHubClient, verbose: bool = False) -> dict[str, Any]:
    """Validate a single repository's license."""
    result: dict[str, Any] = {
        "file": yaml_path.name,
        "status": "error",
        "origin_license": None,
        "detected": None,
        "source": None,
        "details": "",
    }

    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        result["details"] = f"YAML parse error: {e}"
        return result

    if not isinstance(data, dict):
        result["details"] = "YAML root must be a dictionary"
        return result

    fork_url = data.get("fork", {}).get("url", "")
    origin_license = data.get("origin", {}).get("license", "")

    result["origin_license"] = origin_license

    if not fork_url:
        result["details"] = "fork.url is missing"
        return result

    if not origin_license:
        result["details"] = "origin.license is missing"
        return result

    parsed = parse_github_url(fork_url)
    if not parsed:
        result["details"] = f"could not parse GitHub URL: {fork_url}"
        return result

    owner, repo = parsed

    try:
        detected, source, details = fetch_license_spdx(client, owner, repo)
        result["detected"] = detected
        result["source"] = source
        result["details"] = details

        if detected is None:
            result["status"] = "missing_license"
        elif detected in ("NOASSERTION", "OTHER", "UNKNOWN"):
            result["status"] = "unknown"
        elif detected.upper() == origin_license.upper():
            result["status"] = "ok"
        else:
            result["status"] = "mismatch"

    except GitHubHTTPError as e:
        result["details"] = f"API error: {e.status_code}"
        result["status"] = "error"

    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate repository license files against YAML declarations.")
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=None,
        help="Directory containing repo YAML files (default: repos/)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat unknown/missing licenses as errors",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Validate only this specific YAML file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )

    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    repos_dir = args.repos_dir or (base_dir / "repos")

    if not repos_dir.exists():
        print(f"Error: repos directory not found: {repos_dir}", file=sys.stderr)
        return 2

    if args.only:
        yaml_files = [repos_dir / args.only]
        if not yaml_files[0].exists():
            print(f"Error: file not found: {yaml_files[0]}", file=sys.stderr)
            return 2
    else:
        yaml_files = sorted(list(repos_dir.glob("*.yaml")) + list(repos_dir.glob("*.yml")))

    if not yaml_files:
        if args.format == "json":
            print("[]")
        else:
            print("No YAML files found in repos/")
        return 0

    results = []
    has_mismatch = False
    has_warning = False

    with GitHubClient(auth="auto") as client:
        for yaml_file in yaml_files:
            result = validate_license(yaml_file, client, args.verbose)
            results.append(result)

            if result["status"] == "mismatch":
                has_mismatch = True
            elif result["status"] in ("unknown", "missing_license", "error"):
                has_warning = True

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            status = r["status"]
            file_name = r["file"]
            origin = r["origin_license"] or "N/A"
            detected = r["detected"] or "N/A"
            source = r["source"] or ""
            details = r["details"]

            if status == "ok":
                print(f"✅ {file_name}: {origin} ({source})")
            elif status == "mismatch":
                print(f"❌ {file_name}: expected {origin}, detected {detected} ({source})")
            elif status == "missing_license":
                print(f"⚠️  {file_name}: expected {origin}, no LICENSE file found")
            elif status == "unknown":
                print(f"⚠️  {file_name}: expected {origin}, detected {detected} ({source})")
            else:
                print(f"❌ {file_name}: error - {details}")

        print()
        ok_count = sum(1 for r in results if r["status"] == "ok")
        print(f"Validated {len(results)} file(s): {ok_count} OK")

    if has_mismatch:
        return 1
    if args.strict and has_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
