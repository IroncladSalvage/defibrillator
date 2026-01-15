#!/usr/bin/env python3
"""Generate Dependabot configuration files based on repository languages."""

import argparse
import sys
from pathlib import Path

from defibrillator.repo_catalog import load_all_repos

LANGUAGE_TO_ECOSYSTEM = {
    "Python": ["pip", "pip-compile"],
    "JavaScript": ["npm", "yarn"],
    "TypeScript": ["npm", "yarn"],
    "Ruby": ["bundler", "rubygems"],
    "Go": ["gomod"],
    "Java": ["maven", "gradle"],
    "Kotlin": ["maven", "gradle"],
    "Rust": ["cargo"],
    "PHP": ["composer"],
    "C#": ["nuget"],
    "Swift": ["swift"],
    "Docker": ["docker"],
    "Helm": ["helm"],
}


def get_ecosystems(languages: list[str]) -> list[str]:
    """Get package ecosystems for the given languages.

    Args:
        languages: List of language names from repo YAML

    Returns:
        Deduplicated list of ecosystems
    """
    ecosystems = set()
    for language in languages:
        if language in LANGUAGE_TO_ECOSYSTEM:
            ecosystems.update(LANGUAGE_TO_ECOSYSTEM[language])

    return sorted(ecosystems)


def generate_dependabot_config(ecosystems: list[str]) -> str:
    """Generate Dependabot configuration YAML.

    Args:
        ecosystems: List of package ecosystems

    Returns:
        YAML configuration string
    """
    if not ecosystems:
        return ""

    lines = [
        "version: 2",
        "updates:",
    ]

    for ecosystem in ecosystems:
        lines.append(f'  - package-ecosystem: "{ecosystem}"')
        lines.append('    directory: "/"')
        lines.append("    schedule:")
        lines.append('      interval: "weekly"')
        lines.append("    open-pull-requests-limit: 10")
        lines.append("")

    return "\n".join(lines).strip()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Dependabot configuration files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "outputs" / "dependabot",
        help="Directory to output Dependabot configs",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Specific repo file to process (default: all repos)",
    )

    args = parser.parse_args()

    if not args.repos_dir.exists():
        print(f"Error: repos directory not found: {args.repos_dir}", file=sys.stderr)
        return 2

    repo_data = load_all_repos(args.repos_dir)

    if args.file:
        repo_data = [r for r in repo_data if r.get("_file") == args.file]

    if not repo_data:
        print("No repository files found.")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for data in repo_data:
        file_stem = data.get("_file", "unknown")
        languages = data.get("languages", [])

        ecosystems = get_ecosystems(languages)

        if not ecosystems:
            print(f"Skipping {file_stem}: no supported languages found")
            continue

        config = generate_dependabot_config(ecosystems)

        output_file = args.output_dir / f"{file_stem}.dependabot.yml"
        output_file.write_text(config, encoding="utf-8")

        print(f"Generated: {output_file}")
        print(f"  Ecosystems: {', '.join(ecosystems)}")

    print(f"\nProcessed {len(repo_data)} repository file(s).")
    print(f"Configs written to: {args.output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
