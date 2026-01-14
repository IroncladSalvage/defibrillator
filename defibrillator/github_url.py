"""GitHub URL parsing utilities."""

from __future__ import annotations

import re


def parse_owner_repo(url: str) -> tuple[str, str]:
    """Extract owner and repo from a GitHub URL.

    Handles:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/
    - git@github.com:owner/repo.git

    Raises:
        ValueError: If the URL cannot be parsed.
    """
    url = url.strip().rstrip("/")

    if url.endswith(".git"):
        url = url[:-4]

    patterns = [
        r"https?://github\.com/([^/]+)/([^/]+)",
        r"git@github\.com:([^/]+)/([^/]+)",
    ]

    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            return match.group(1), match.group(2)

    raise ValueError(f"Cannot parse GitHub URL: {url}")
