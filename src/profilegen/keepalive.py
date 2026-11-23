"""Keep-alive check for the scheduled refresh (FR-016a).

GitHub disables scheduled workflows after 60 days without repository
activity. The refresh job asks ``profilegen keepalive --days 50`` whether the
last commit on HEAD is old enough to warrant an empty keep-alive commit.

Exit codes: ``NEEDED`` (0) keep-alive commit needed, ``NOT_NEEDED`` (3) the
last commit is recent enough, ``ERROR`` (1) git failed (not a repository, no
commits, git missing).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from profilegen import clock
from profilegen.clock import SECONDS_PER_DAY

NEEDED = 0
NOT_NEEDED = 3
ERROR = 1

DEFAULT_DAYS = 50


class KeepaliveError(Exception):
    """Raised when the last commit time cannot be determined."""


@dataclass(frozen=True)
class Result:
    exit_code: int
    message: str


def last_commit_epoch(repo: Path) -> int:
    """Return the committer timestamp (Unix seconds) of HEAD in ``repo``."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:  # git not installed or repo directory missing
        raise KeepaliveError(f"cannot run git: {e}") from None
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()
        raise KeepaliveError(detail[-1] if detail else f"git log failed with exit code {proc.returncode}")
    value = proc.stdout.strip()
    if not value.isdigit():
        raise KeepaliveError("no commits on HEAD")
    return int(value)


def check(repo: Path, days: int = DEFAULT_DAYS, now: datetime | None = None) -> Result:
    """Decide whether a keep-alive commit is needed.

    Needed when HEAD's committer date is at least ``days`` full days before
    ``now`` (default: current UTC time).
    """
    try:
        committed = last_commit_epoch(repo)
    except KeepaliveError as e:
        return Result(ERROR, f"ERROR: keepalive: {e}")
    current = int((now or clock.now()).timestamp())
    age = current - committed
    age_days = age / SECONDS_PER_DAY
    if age >= days * SECONDS_PER_DAY:
        return Result(NEEDED, f"last commit {age_days:.1f} days ago (threshold {days}): keep-alive commit needed")
    return Result(NOT_NEEDED, f"last commit {age_days:.1f} days ago (threshold {days}): no keep-alive commit needed")
