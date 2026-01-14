"""Upstream commit checking utilities."""

from __future__ import annotations

from defibrillator.github_api import GitHubClient


def get_upstream_head(client: GitHubClient, owner: str, repo: str) -> tuple[str, str]:
    """Get the default branch and HEAD SHA for a repository.

    Returns:
        Tuple of (default_branch, head_sha).
    """
    repo_data = client.get_json(f"/repos/{owner}/{repo}")
    default_branch = repo_data["default_branch"]

    branch_data = client.get_json(f"/repos/{owner}/{repo}/branches/{default_branch}")
    head_sha = branch_data["commit"]["sha"]

    return default_branch, head_sha


def is_behind_upstream(stored_sha: str, head_sha: str) -> bool:
    """Check if the stored SHA is behind the upstream HEAD.

    Handles prefix matching for abbreviated SHAs.
    """
    if not stored_sha or not head_sha:
        return True

    stored_sha = stored_sha.lower()
    head_sha = head_sha.lower()

    if stored_sha == head_sha:
        return False

    if head_sha.startswith(stored_sha) or stored_sha.startswith(head_sha):
        return False

    return True
