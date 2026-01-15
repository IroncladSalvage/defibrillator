#!/usr/bin/env python3
"""Generate RSS/Atom feed of repository status changes."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from defibrillator.repo_catalog import load_all_repos


class FeedEntry:
    """Represents a feed entry."""

    def __init__(
        self,
        title: str,
        content: str,
        updated: datetime,
        link: str,
        author: str | None = None,
    ):
        self.title = title
        self.content = content
        self.updated = updated
        self.link = link
        self.author = author


class AtomFeed:
    """Represents an Atom feed."""

    def __init__(self, title: str, id: str, link: str):
        self.title = title
        self.id = id
        self.link = link
        self.entries: list[FeedEntry] = []

    def add_entry(self, entry: FeedEntry) -> None:
        """Add an entry to the feed."""
        self.entries.append(entry)

    def to_xml(self) -> str:
        """Generate Atom XML feed."""
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        xml_lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"  <title>{self.title}</title>",
            f'  <link href="{self.link}" rel="self"/>',
            f'  <link href="{self.link}"/>',
            f"  <id>{self.id}</id>",
            f"  <updated>{now}</updated>",
        ]

        for entry in sorted(self.entries, key=lambda e: e.updated, reverse=True):
            updated = entry.updated.strftime("%Y-%m-%dT%H:%M:%SZ")
            xml_lines.extend(
                [
                    "  <entry>",
                    f"    <title>{entry.title}</title>",
                    f'    <link href="{entry.link}"/>',
                    f"    <id>{entry.link}</id>",
                    f"    <updated>{updated}</updated>",
                    f'    <content type="text">{entry.content}</content>',
                ]
            )

            if entry.author:
                xml_lines.append(f"    <author><name>{entry.author}</name></author>")

            xml_lines.extend(["  </entry>", ""])

        xml_lines.append("</feed>")

        return "\n".join(xml_lines)


def generate_feed_entries(repos: list[dict]) -> list[FeedEntry]:
    """Generate feed entries from repository data.

    Args:
        repos: List of repository data

    Returns:
        List of FeedEntry objects
    """
    entries = []

    for repo in repos:
        file_stem = repo.get("_file", "unknown")
        fork = repo.get("fork", {})
        status = repo.get("status", {})

        repo_name = fork.get("name", file_stem)
        repo_url = fork.get("url", "#")
        last_touched = status.get("last_touched", "")
        state = status.get("state", "unknown")
        ci_status = status.get("ci_status", "unknown")
        notes = status.get("notes", "")

        if not last_touched:
            continue

        try:
            updated = datetime.strptime(last_touched, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue

        status_icons = {"active": "🟢", "life-support": "🟡", "archived": "⚫", "pending": "🔵", "unknown": "❓"}
        ci_icons = {"passing": "✅", "failing": "❌", "unknown": "❓"}

        status_icon = status_icons.get(state, "❓")
        ci_icon = ci_icons.get(ci_status, "❓")

        title = f"{repo_name}: {state}"
        content = f"""
Repository: {repo_name}
Status: {status_icon} {state}
CI Status: {ci_icon} {ci_status}
Last Touched: {last_touched}
{"Notes: " + notes if notes else ""}
        """.strip()

        entry = FeedEntry(
            title=title,
            content=content,
            updated=updated,
            link=repo_url,
        )

        entries.append(entry)

    return entries


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate RSS/Atom feed of repository status changes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=Path(__file__).parent.parent / "repos",
        help="Directory containing repository YAML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "feed.xml",
        help="Output feed file",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="IroncladSalvage Repository Status",
        help="Feed title",
    )
    parser.add_argument(
        "--id",
        type=str,
        default="urn:uuid:ironcladsalvage-repos",
        help="Feed ID",
    )
    parser.add_argument(
        "--link",
        type=str,
        default="https://github.com/IroncladSalvage",
        help="Feed link",
    )

    args = parser.parse_args()

    if not args.repos_dir.exists():
        print(f"Error: repos directory not found: {args.repos_dir}", file=sys.stderr)
        return 2

    repo_data = load_all_repos(args.repos_dir)

    if not repo_data:
        print("No repository files found.")
        return 0

    entries = generate_feed_entries(repo_data)

    if not entries:
        print("No recent status changes found.")
        return 0

    feed = AtomFeed(title=args.title, id=args.id, link=args.link)

    for entry in entries:
        feed.add_entry(entry)

    xml = feed.to_xml()

    args.output.write_text(xml, encoding="utf-8")
    print(f"Generated feed: {args.output}")
    print(f"  - {len(entries)} entries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
