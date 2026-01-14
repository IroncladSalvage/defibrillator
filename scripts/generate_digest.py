#!/usr/bin/env python3
"""Generate README tables and individual info pages for repositories."""

import os
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from defibrillator.staleness import compute_staleness, StalenessResult

STATUS_EMOJI = {
    "active": "🟢",
    "life-support": "🟡",
    "archived": "⚫",
    "pending": "🔵",
}

CI_EMOJI = {
    "passing": "✅",
    "failing": "❌",
    "unknown": "❓",
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}

STALE_WARNING_DAYS = int(os.getenv("STALE_WARNING_DAYS", "75"))
STALE_CRITICAL_DAYS = int(os.getenv("STALE_CRITICAL_DAYS", "90"))

STALE_EMOJI = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}


def load_repos(repos_dir: Path) -> list[dict]:
    """Load all repository YAML files."""
    repos = []
    yaml_files = list(repos_dir.glob("*.yaml")) + list(repos_dir.glob("*.yml"))
    
    for yaml_file in yaml_files:
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data:
                    data["_file"] = yaml_file.stem
                    repos.append(data)
        except Exception as e:
            print(f"Warning: Could not load {yaml_file}: {e}")
    
    return repos


def sort_repos(repos: list[dict]) -> list[dict]:
    """Sort repos by priority, then status, then name."""
    def sort_key(repo):
        priority = repo.get("metadata", {}).get("priority", "normal")
        state = repo.get("status", {}).get("state", "pending")
        name = repo.get("fork", {}).get("name", "")
        
        state_order = {"active": 0, "life-support": 1, "pending": 2, "archived": 3}
        
        return (PRIORITY_ORDER.get(priority, 2), state_order.get(state, 2), name.lower())
    
    return sorted(repos, key=sort_key)


def generate_summary_table(repos: list[dict]) -> str:
    """Generate summary table."""
    lines = [
        "| Repository | Status | CI | Languages | Architectures | Details |",
        "|------------|--------|-----|-----------|---------------|---------|",
    ]
    
    for repo in repos:
        name = repo.get("fork", {}).get("name", "Unknown")
        url = repo.get("fork", {}).get("url", "#")
        state = repo.get("status", {}).get("state", "unknown")
        ci = repo.get("status", {}).get("ci_status", "unknown")
        languages = ", ".join(repo.get("languages", []))
        archs = ", ".join(repo.get("targets", {}).get("architectures", []))
        file_stem = repo.get("_file", name)
        
        status_icon = STATUS_EMOJI.get(state, "❓")
        ci_icon = CI_EMOJI.get(ci, "❓")
        
        lines.append(f"| [{name}]({url}) | {status_icon} {state} | {ci_icon} | {languages} | {archs} | [📋](info/{file_stem}.md) |")
    
    return "\n".join(lines)


def generate_repo_detail_page(repo: dict, staleness_result: StalenessResult | None = None) -> str:
    """Generate detailed markdown page for a repository."""
    fork = repo.get("fork", {})
    origin = repo.get("origin", {})
    status = repo.get("status", {})
    targets = repo.get("targets", {})
    artifacts = repo.get("artifacts", {})
    metadata = repo.get("metadata", {})
    automation = repo.get("automation", {})
    
    name = fork.get("name", "Unknown")
    lines = [f"# {name}", ""]
    
    if metadata.get("description"):
        lines.append(f"_{metadata['description']}_")
        lines.append("")
    
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Origin:** [{origin.get('name', 'Unknown')}]({origin.get('url', '#')})")
    lines.append(f"- **Fork:** [{fork.get('name', name)}]({fork.get('url', '#')})")
    lines.append(f"- **License:** {origin.get('license', 'Unknown')}")
    lines.append(f"- **Created:** {fork.get('created_at', 'Unknown')}")
    
    archived_date = origin.get("archived_date")
    if archived_date:
        lines.append(f"- **Upstream Archived:** {archived_date}")
    
    lines.append("")
    lines.append("## Status")
    lines.append("")
    lines.append(f"- **State:** {STATUS_EMOJI.get(status.get('state'), '❓')} {status.get('state', 'unknown')}")
    lines.append(f"- **CI:** {CI_EMOJI.get(status.get('ci_status'), '❓')} {status.get('ci_status', 'unknown')}")
    lines.append(f"- **Last Touched:** {status.get('last_touched', 'Unknown')}")
    lines.append(f"- **Last Upstream Commit:** `{origin.get('last_upstream_commit', 'Unknown')}`")
    
    if staleness_result:
        emoji = STALE_EMOJI.get(staleness_result.severity, "")
        days_str = f"{staleness_result.days_stale} days" if staleness_result.days_stale is not None else "N/A"
        lines.append(f"- **Staleness:** {emoji} {days_str} ({staleness_result.severity})")
    
    if status.get("notes"):
        lines.append(f"- **Notes:** {status['notes']}")
    
    lines.append("")
    lines.append("## Targets")
    lines.append("")
    lines.append(f"- **Languages:** {', '.join(repo.get('languages', ['N/A']))}")
    lines.append(f"- **Architectures:** {', '.join(targets.get('architectures', ['N/A']))}")
    lines.append(f"- **Operating Systems:** {', '.join(targets.get('operating_systems', ['N/A']))}")
    
    runtimes = targets.get("runtimes", [])
    if runtimes:
        lines.append(f"- **Runtimes:** {', '.join(runtimes)}")
    
    # Artifacts section
    docker = artifacts.get("docker", {})
    packages = artifacts.get("packages", {})
    has_artifacts = docker.get("enabled") or any(packages.values())
    
    if has_artifacts:
        lines.append("")
        lines.append("## Artifacts")
        lines.append("")
        
        if docker.get("enabled"):
            lines.append(f"- **Docker:** `{docker.get('image', 'N/A')}`")
        
        enabled_packages = [k for k, v in packages.items() if v]
        if enabled_packages:
            lines.append(f"- **Packages:** {', '.join(enabled_packages)}")
    
    # Automation section
    if automation:
        lines.append("")
        lines.append("## Automation")
        lines.append("")
        lines.append(f"- **Dependabot:** {'✅' if automation.get('dependabot') else '❌'}")
        lines.append(f"- **Security Scanning:** {'✅' if automation.get('security_scanning') else '❌'}")
        lines.append(f"- **Auto Release:** {'✅' if automation.get('auto_release') else '❌'}")
    
    # Metadata
    tags = metadata.get("tags", [])
    priority = metadata.get("priority")
    
    if tags or priority:
        lines.append("")
        lines.append("## Metadata")
        lines.append("")
        if priority:
            lines.append(f"- **Priority:** {priority}")
        if tags:
            lines.append(f"- **Tags:** {', '.join(tags)}")
    
    lines.append("")
    return "\n".join(lines)


def generate_overview_table(repos: list[dict]) -> str:
    """Generate overview stats table."""
    total = len(repos)
    active = sum(1 for r in repos if r.get("status", {}).get("state") == "active")
    life_support = sum(1 for r in repos if r.get("status", {}).get("state") == "life-support")
    archived = sum(1 for r in repos if r.get("status", {}).get("state") == "archived")
    
    return f"""| Total | 🟢 Active | 🟡 Life Support | ⚫ Archived |
|-------|-----------|-----------------|-------------|
| {total} | {active} | {life_support} | {archived} |"""


def update_readme(readme_path: Path, overview_table: str, repos_table: str) -> None:
    """Update README.md with generated tables."""
    content = readme_path.read_text(encoding="utf-8")
    
    # Find and replace or append the auto-generated section
    marker_start = "<!-- AUTO-GENERATED-START -->"
    marker_end = "<!-- AUTO-GENERATED-END -->"
    
    generated_section = f"""{marker_start}

## Overview

{overview_table}

## Repositories

{repos_table}

{marker_end}"""
    
    if marker_start in content:
        # Replace existing section
        import re
        pattern = f"{re.escape(marker_start)}.*?{re.escape(marker_end)}"
        content = re.sub(pattern, generated_section, content, flags=re.DOTALL)
    else:
        # Append to end
        content = content.rstrip() + "\n\n" + generated_section + "\n"
    
    readme_path.write_text(content, encoding="utf-8")
    print(f"Updated: {readme_path}")


def generate_info_pages(repos: list[dict], info_dir: Path, staleness_map: dict[str, StalenessResult]) -> None:
    """Generate individual info pages for each repository."""
    if info_dir.exists():
        shutil.rmtree(info_dir)
    info_dir.mkdir(parents=True)
    
    for repo in repos:
        file_stem = repo.get("_file", repo.get("fork", {}).get("name", "unknown"))
        staleness_result = staleness_map.get(file_stem)
        page_path = info_dir / f"{file_stem}.md"
        page_content = generate_repo_detail_page(repo, staleness_result)
        page_path.write_text(page_content, encoding="utf-8")
        print(f"Generated: {page_path}")


def main() -> None:
    """Main entry point."""
    base_dir = Path(__file__).parent.parent
    repos_dir = base_dir / "repos"
    readme_path = base_dir / "README.md"
    info_dir = base_dir / "info"
    
    repos = load_repos(repos_dir)
    repos = sort_repos(repos)
    
    staleness_results = compute_staleness(
        repos, warning_days=STALE_WARNING_DAYS, critical_days=STALE_CRITICAL_DAYS
    )
    staleness_map = {r.file_stem: r for r in staleness_results}
    
    overview_table = generate_overview_table(repos)
    repos_table = generate_summary_table(repos)
    
    update_readme(readme_path, overview_table, repos_table)
    generate_info_pages(repos, info_dir, staleness_map)
    
    print(f"\nProcessed {len(repos)} repository file(s).")


if __name__ == "__main__":
    main()
