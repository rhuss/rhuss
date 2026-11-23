"""Shared clock: the current UTC time and the length of a day.

Tests replace ``now`` to pin the time for the scan and the keep-alive check.
"""

from __future__ import annotations

from datetime import datetime, timezone

SECONDS_PER_DAY = 86400


def now() -> datetime:
    """The current time in UTC."""
    return datetime.now(timezone.utc)
