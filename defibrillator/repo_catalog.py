"""YAML repo file operations."""

from __future__ import annotations

from pathlib import Path

import yaml


def iter_repo_files(repos_dir: Path) -> list[Path]:
    """Find all YAML files in the repos directory."""
    return sorted(repos_dir.glob("*.yaml"))


def load_repo(path: Path) -> dict:
    """Load a single YAML repo file, adding _file and _path metadata."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["_file"] = path.name
    data["_path"] = str(path)
    return data


def load_all_repos(repos_dir: Path) -> list[dict]:
    """Load all repo YAML files from a directory."""
    return [load_repo(path) for path in iter_repo_files(repos_dir)]


def write_repo(path: Path, data: dict) -> None:
    """Save YAML repo file, preserving key order."""
    clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(clean_data, f, sort_keys=False, allow_unicode=True)
