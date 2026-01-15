"""Defibrillator - Repository manager for IroncladSalvage."""

from defibrillator.github_api import (
    GitHubClient,
    GitHubError,
    GitHubAuthError,
    GitHubHTTPError,
)
from defibrillator.repo_catalog import load_all_repos
from defibrillator.staleness import StalenessResult, compute_staleness, to_json

__all__ = [
    "GitHubClient",
    "GitHubError",
    "GitHubAuthError",
    "GitHubHTTPError",
    "load_all_repos",
    "StalenessResult",
    "compute_staleness",
    "to_json",
]
