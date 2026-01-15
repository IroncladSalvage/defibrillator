"""Date utilities."""

from __future__ import annotations

from datetime import UTC, date, datetime


def parse_date(s: str) -> date | None:
    """Parse a YYYY-MM-DD date string, returning None on failure."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def today_utc() -> date:
    """Return today's date in UTC."""
    return datetime.now(UTC).date()


def days_since(date_str: str, today: date | None = None) -> int | None:
    """Return the number of days since the given date string."""
    parsed = parse_date(date_str)
    if parsed is None:
        return None
    if today is None:
        today = today_utc()
    return (today - parsed).days
