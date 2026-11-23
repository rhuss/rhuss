"""Collect facts for the curation skill: ``profilegen scan`` (FR-020 to FR-023a).

Candidates come from the GitHub owner listings (``settings.owned_owners`` and
``settings.owned_extra_repos``), the repositories listed in profile.yaml, and
local checkouts with GitHub remotes found under the scan roots (at most
``MAX_DEPTH`` directory levels below a root).

Privacy (FR-023, SC-003): visibility is always checked on GitHub, and every
repository that is private, a fork or unknown to GitHub is dropped before any
output is built. Data-file entries that are gone or not public are reported
by entry path only (for example ``more_tools[3]``). Any SourceError while
checking visibility or activity propagates, so the caller refuses to emit a
partial report.

Commit activity counts only commits authored by the checkout's git
``user.email``. A checkout's commits are credited to its primary remote
(``origin``) and to any of its remotes that is a listed main project, so a
main project listed by its upstream repository is matched through the
``upstream`` remote of a fork checkout. Repositories without such a checkout
fall back to the GitHub commits API (``author=<login>``, the first entry of
``owned_owners``), looking back ``LOOKBACK_DAYS`` days.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from profilegen import clock
from profilegen.clock import SECONDS_PER_DAY
from profilegen.model import PROJECT_SECTIONS, Profile, RepoInfo
from profilegen.sources import github

__all__ = [
    "GitHubAccess",
    "ScanError",
    "build_report",
    "find_checkouts",
    "format_summary",
    "parse_remote",
    "sort_proposals",
]

MAX_DEPTH = 3
LOOKBACK_DAYS = 365  # "active in the last 12 months" for new_tool proposals
KIND_ORDER = ("demote", "promote", "remove", "rename", "new_tool")
REMOVE_REASON = "repository not public or missing"
NEW_TOOL_REASON = "public, active in last 12 months, not listed"

_REMOTE = re.compile(
    r"""^(?:
        (?:https?|git|ssh)://(?:[^@/]+@)?github\.com(?::\d+)?/   # URL forms
        | [^@/:]+@github\.com:                                      # scp-like ssh
    )
    (?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+?)(?:\.git)?/?$""",
    re.VERBOSE | re.IGNORECASE,
)
_ENTRY = re.compile(r"^(?P<section>[a-z_]+)\[(?P<index>\d+)\]$")


class ScanError(Exception):
    """Local scanning failed (for example git is not installed)."""


# --- GitHub access --------------------------------------------------------------------


class GitHubAccess:
    """The GitHub source bound to one token; tests stub the JSON layer underneath."""

    def __init__(self, token: str | None = None):
        self.token = token

    def list_owned(self, owners: list[str], extra_repos: list[str]) -> list[RepoInfo]:
        return github.list_owned(owners, extra_repos, token=self.token)

    def resolve(self, repo: str, entry: str, known: dict[str, RepoInfo]) -> RepoInfo | github.Missing:
        return github.resolve(repo, entry, token=self.token, known=known)

    def commit_times(self, full_name: str, since: datetime, login: str) -> list[int]:
        return github.commit_times(full_name, since, login, token=self.token)


# --- local checkouts ------------------------------------------------------------------


def parse_remote(url: str) -> str | None:
    """Map a GitHub remote URL to ``owner/name``; None for anything else."""
    match = _REMOTE.match((url or "").strip())
    if not match:
        return None
    return f"{match['owner']}/{match['name']}"


def _expand(root: str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(root)))


def find_checkouts(roots: list[str], max_depth: int = MAX_DEPTH) -> list[Path]:
    """Git checkouts at most ``max_depth`` levels below each root (``~`` expanded).

    Hidden directories are skipped and checkouts are not descended into.
    Missing roots are ignored. Sorted, deduplicated by real path.
    """
    found: dict[str, Path] = {}

    def walk(directory: Path, depth: int) -> None:
        if (directory / ".git").exists():
            found.setdefault(os.path.realpath(directory), directory)
            return
        if depth >= max_depth:
            return
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            if is_dir:
                walk(Path(entry.path), depth + 1)

    for root in roots:
        path = _expand(root)
        if path.is_dir():
            walk(path, 0)
    return sorted(found.values())


def _git(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise ScanError("git is not installed") from None
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


@dataclass
class Checkout:
    remotes: list[str]  # owner/name, origin first
    email: str | None
    commits: dict[str, int] = field(default_factory=dict)  # sha -> author timestamp
    primary: str | None = None  # the remote the local commits are credited to


def _config(path: Path) -> tuple[list[str], str | None, str | None]:
    """(GitHub remotes as owner/name with origin first, user.email, primary remote) from one git call.

    The primary remote is ``origin``, or the only GitHub remote when there is
    no ``origin``. Local commits are credited to it alone: ``git log --all``
    also holds fork-only branches, which an upstream remote never received.
    """
    out = _git(path, "config", "--get-regexp", r"^(remote\..*\.url|user\.email)$") or ""
    pairs = []
    email = None
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        if key == "user.email":
            email = value.strip() or None
            continue
        name = key[len("remote.") : -len(".url")]
        repo = parse_remote(value)
        if repo:
            pairs.append((name != "origin", name, repo))
    seen: set[str] = set()
    repos = []
    for _, _, repo in sorted(pairs):
        if repo.lower() not in seen:
            seen.add(repo.lower())
            repos.append(repo)
    origin = next((repo for _, name, repo in pairs if name == "origin"), None)
    primary = origin or (repos[0] if len(repos) == 1 else None)
    return repos, email, primary


def _read_checkout(path: Path) -> Checkout | None:
    remotes, email, primary = _config(path)
    if not remotes:
        return None
    commits: dict[str, int] = {}
    if email:
        log = _git(path, "log", "--all", "--format=%H%x09%ae%x09%at") or ""
        for line in log.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[1].lower() == email.lower() and parts[2].isdigit():
                commits[parts[0]] = int(parts[2])
    return Checkout(remotes=remotes, email=email, commits=commits, primary=primary)


def _display(path: Path) -> str:
    home = Path(os.path.expanduser("~"))
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


# --- report ---------------------------------------------------------------------------


@dataclass
class _Candidate:
    info: RepoInfo
    local_paths: list[Path] = field(default_factory=list)
    local_commits: dict[str, int] = field(default_factory=dict)
    has_local_counts: bool = False


def _entry_key(entry: str) -> tuple:
    match = _ENTRY.match(entry)
    if not match:
        return (len(PROJECT_SECTIONS), entry, 0)
    section = match["section"]
    order = PROJECT_SECTIONS.index(section) if section in PROJECT_SECTIONS else len(PROJECT_SECTIONS)
    return (order, section, int(match["index"]))


def sort_proposals(proposals: list[dict]) -> list[dict]:
    """Kind order demote, promote, remove, rename, new_tool; then repo (case-insensitive) or entry."""

    def key(p: dict) -> tuple:
        kind = KIND_ORDER.index(p["kind"]) if p["kind"] in KIND_ORDER else len(KIND_ORDER)
        if "entry" in p and "repo" not in p:
            return (kind, _entry_key(p["entry"]), "")
        return (kind, (), p.get("repo", "").lower())

    return sorted(proposals, key=key)


def build_report(
    profile: Profile,
    roots: list[str],
    now: datetime | None = None,
    gh: GitHubAccess | None = None,
) -> dict:
    """Build the ScanReport (``{"repos": [...], "proposals": [...]}``).

    SourceError propagates: when visibility is unknown, no report is built.
    """
    now = now or clock.now()
    gh = gh or GitHubAccess()
    settings = profile.settings
    now_ts = now.timestamp()
    owners = list(settings.owned_owners)
    login = owners[0] if owners else "rhuss"

    owned = gh.list_owned(owners, list(settings.owned_extra_repos))
    known: dict[str, RepoInfo] = {}
    for info in owned:
        known.setdefault(info.full_name.lower(), info)

    candidates: dict[str, _Candidate] = {}
    alias: dict[str, str | None] = {}  # lowercase requested name -> canonical key, None if dropped
    proposals: list[dict] = []
    listed_in: dict[str, str] = {}
    main_entries: list[tuple[str, str]] = []  # (canonical key, data-file repo)

    def add(info: RepoInfo) -> str:
        key = info.full_name.lower()
        candidates.setdefault(key, _Candidate(info))
        return key

    # Data-file entries: remove (by entry path only) and rename proposals.
    for section in PROJECT_SECTIONS:
        for index, project in enumerate(getattr(profile, section)):
            entry = f"{section}[{index}]"
            result = gh.resolve(project.repo, entry, known)
            if isinstance(result, github.Missing):
                alias[project.repo.lower()] = None
                proposals.append({"kind": "remove", "entry": entry, "reason": REMOVE_REASON})
                continue
            key = add(result)
            alias[project.repo.lower()] = key
            listed_in.setdefault(key, section)
            if key != project.repo.lower():
                proposals.append({"kind": "rename", "repo": project.repo, "new_repo": result.full_name})
            if section == "main_projects":
                main_entries.append((key, project.repo))
    listed_keys = set(listed_in)
    main_keys = {key for key, _ in main_entries}

    for info in owned:
        alias.setdefault(info.full_name.lower(), add(info))

    # Local checkouts: every GitHub remote is a candidate once GitHub confirms it.
    for path in find_checkouts(roots):
        checkout = _read_checkout(path)
        if checkout is None:
            continue
        for remote in checkout.remotes:
            lower = remote.lower()
            if lower not in alias:
                result = gh.resolve(remote, "local", known)
                alias[lower] = None if isinstance(result, github.Missing) else add(result)
            key = alias[lower]
            if key is None:
                continue
            cand = candidates[key]
            if path not in cand.local_paths:
                cand.local_paths.append(path)
            # Local commits count for the primary remote, and for any remote that
            # is a listed main project: a main project listed by its upstream
            # (worked on through a fork checkout) is assessed from the checkout.
            # Other remotes (for example an unlisted upstream of a fork) fall back
            # to the GitHub commits API, which only sees commits they contain.
            primary = checkout.primary is not None and lower == checkout.primary.lower()
            if checkout.email and (primary or key in main_keys):
                cand.has_local_counts = True
                cand.local_commits.update(checkout.commits)

    # Drop everything that is not public before building output. Unlisted forks
    # are dropped too; a listed fork (for example a main project that is a fork)
    # stays, so it can still be proposed for demotion (FR-021).
    visible = {
        k: c
        for k, c in candidates.items()
        if not c.info.private and (not c.info.fork or k in listed_keys)
    }

    since = now - timedelta(days=max(LOOKBACK_DAYS, settings.demote_after_days, settings.promote_window_days))
    times: dict[str, list[int]] = {}
    for key in sorted(visible):
        cand = visible[key]
        if cand.has_local_counts:
            times[key] = list(cand.local_commits.values())
        else:
            times[key] = list(gh.commit_times(cand.info.full_name, since, login))

    def count_within(key: str, days: int) -> int:
        cutoff = now_ts - days * SECONDS_PER_DAY
        return sum(1 for t in times[key] if t >= cutoff)

    def days_since(key: str) -> int | None:
        if not times[key]:
            return None
        return max(0, int((now_ts - max(times[key])) // SECONDS_PER_DAY))

    window = settings.promote_window_days
    repos = []
    for key in sorted(visible):
        cand = visible[key]
        repos.append(
            {
                "repo": cand.info.full_name,
                "local_path": _display(min(cand.local_paths)) if cand.local_paths else None,
                "public": True,
                "commits_window": count_within(key, window),
                "days_since_last_commit": days_since(key),
                "listed_in": listed_in.get(key),
            }
        )

    for key, repo in main_entries:
        if key in visible and count_within(key, settings.demote_after_days) == 0:
            days = days_since(key)
            reason = f"no commits in {days} days" if days is not None else (
                f"no commits in the last {settings.demote_after_days} days"
            )
            proposals.append({"kind": "demote", "repo": repo, "reason": reason})

    # New tools are seeded from the user's own repositories only (not the
    # organizations or the extra owned repos), and never the profile repo itself.
    profile_repo = f"{login}/{login}".lower()
    for key, cand in visible.items():
        if cand.info.archived or key == profile_repo:
            continue  # the profile repository is never a project candidate
        n = count_within(key, window)
        if key not in main_keys and n >= settings.promote_commits:
            proposals.append(
                {"kind": "promote", "repo": cand.info.full_name, "reason": f"{n} commits in last {window} days"}
            )
            continue  # one proposal per repository: promote wins over new_tool
        own_repo = key.split("/")[0] == login.lower()
        if own_repo and key not in listed_keys and count_within(key, LOOKBACK_DAYS) > 0:
            proposals.append({"kind": "new_tool", "repo": cand.info.full_name, "reason": NEW_TOOL_REASON})

    return {"repos": repos, "proposals": sort_proposals(proposals)}


def format_summary(report: dict) -> str:
    """Short human-readable summary of the proposals."""
    proposals = report["proposals"]
    lines = [f"{len(report['repos'])} public repositories scanned, {len(proposals)} proposals:"]
    if not proposals:
        lines[0] = f"{len(report['repos'])} public repositories scanned, no proposals"
    for p in proposals:
        if p["kind"] == "rename":
            text = f"{p['repo']} -> {p['new_repo']}"
        else:
            text = f"{p.get('repo') or p.get('entry')}: {p['reason']}"
        lines.append(f"  {p['kind']:<9} {text}")
    return "\n".join(lines)
