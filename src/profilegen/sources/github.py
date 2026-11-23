"""GitHub source: owned-repository listing, star total and per-entry resolution.

Warnings about repositories that are missing or not public name only the
data-file entry path (for example ``more_tools[3]``), never the repository,
so a non-public name cannot leak into a job log (FR-011, FR-019a).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from profilegen.model import PROJECT_SECTIONS, Profile, RepoInfo
from profilegen.sources.http import NotFound, SourceError, api_url, get_json, get_json_list

__all__ = ["Missing", "list_owned", "total_stars", "resolve", "fetch_repos", "commit_times"]


@dataclass
class Missing:
    """A data-file entry whose repository is gone or not public.

    Both cases are reported the same way on purpose, so a warning never tells
    whether a repository still exists privately.
    """

    entry: str


def _repo_info(data: object) -> RepoInfo:
    """Convert a GitHub repository object into a RepoInfo; malformed data is a SourceError."""
    if not isinstance(data, dict):
        raise SourceError("GitHub: unexpected repository data")
    full_name = data.get("full_name")
    stars = data.get("stargazers_count")
    if not isinstance(full_name, str) or "/" not in full_name or not isinstance(stars, int) or isinstance(stars, bool):
        raise SourceError("GitHub: unexpected repository data")
    # Visibility must be stated explicitly: a missing flag must never count as public.
    private = data.get("private")
    if not isinstance(private, bool):
        raise SourceError("GitHub: unexpected repository data")
    html_url = data.get("html_url")
    if not isinstance(html_url, str) or not html_url:
        html_url = f"https://github.com/{full_name}"
    return RepoInfo(
        full_name=full_name,
        html_url=html_url,
        stars=stars,
        private=private,
        fork=bool(data.get("fork", False)),
        archived=bool(data.get("archived", False)),
    )


def list_owned(owners: list[str], extra_repos: list[str], token=None) -> list[RepoInfo]:
    """All repositories of the owned accounts (paginated) plus the extra owned repositories.

    An extra repository that no longer exists (HTTP 404) contributes nothing.
    An owner account that does not exist (HTTP 404) makes the total unknown, so
    it raises SourceError like any other failure.
    """
    base = api_url()
    repos: list[RepoInfo] = []
    for owner in owners:
        try:
            items = get_json_list(f"{base}/users/{owner}/repos?type=owner&per_page=100", token=token)
        except NotFound as e:
            raise SourceError(str(e), url=e.url, status=404) from None
        repos.extend(_repo_info(item) for item in items)
    for repo in extra_repos:
        try:
            data = get_json(f"{base}/repos/{repo}", token=token)
        except NotFound:
            continue
        repos.append(_repo_info(data))
    return repos


def total_stars(repos: list[RepoInfo]) -> int:
    """Sum of stars over public, non-fork repositories (archived included), deduped by full_name."""
    seen: set[str] = set()
    total = 0
    for info in repos:
        key = info.full_name.lower()
        if info.private or info.fork or key in seen:
            continue
        seen.add(key)
        total += info.stars
    return total


def resolve(repo: str, entry: str, token=None, known: dict[str, RepoInfo] | None = None) -> RepoInfo | Missing:
    """Look up one data-file repository.

    ``known`` maps lowercase full_name to RepoInfo (from list_owned) and avoids
    an extra API call. Otherwise ``GET /repos/{repo}`` is used; urllib follows
    the 301 redirect of a renamed repository, so the result carries the new
    full_name. SourceError propagates.
    """
    info = (known or {}).get(repo.lower())
    if info is None:
        try:
            info = _repo_info(get_json(f"{api_url()}/repos/{repo}", token=token))
        except NotFound:
            return Missing(entry)
    if info.private:
        return Missing(entry)
    return info


def fetch_repos(profile: Profile, token=None, missing: set[str] | None = None) -> tuple[dict, int, list[str]]:
    """Return (repos_snapshot, total_stars, warnings) for the profile.

    repos_snapshot is keyed by the data-file repo string of every resolvable
    entry, in data-file order. Any SourceError propagates so the caller keeps
    both snapshot keys unchanged. ``missing``, when given, collects the
    data-file repo strings confirmed gone or not public before any failure, so
    the caller never restores them from an old snapshot.
    """
    settings = profile.settings
    owned = list_owned(list(settings.owned_owners), list(settings.owned_extra_repos), token=token)
    total = total_stars(owned)

    known: dict[str, RepoInfo] = {}
    for info in owned:
        known.setdefault(info.full_name.lower(), info)

    snapshot: dict[str, dict] = {}
    warnings: list[str] = []
    for section in PROJECT_SECTIONS:
        for index, project in enumerate(getattr(profile, section)):
            entry = f"{section}[{index}]"
            result = resolve(project.repo, entry, token=token, known=known)
            if isinstance(result, Missing):
                if missing is not None:
                    missing.add(project.repo)
                warnings.append(f"{result.entry}: repository not found or not public, omitted")
                continue
            if result.full_name.lower() != project.repo.lower():
                warnings.append(f"{entry}: repository was renamed, update profile.yaml")
            snapshot[project.repo] = {"full_name": result.full_name, "stars": result.stars, "url": result.html_url}
    return snapshot, total, warnings


def commit_times(full_name: str, since: datetime, login: str, token=None) -> list[int]:
    """Unix timestamps of the commits by ``login`` in ``full_name`` since ``since``.

    An empty repository (HTTP 409) has none. A 404 means the repository went
    away or turned private after it was confirmed public, so it raises
    SourceError rather than looking like "no activity".
    """
    stamp = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{api_url()}/repos/{full_name}/commits?since={stamp}&author={login}&per_page=100"
    try:
        items = get_json_list(url, token=token)
    except NotFound:
        raise SourceError("GitHub: repository disappeared during the scan") from None
    except SourceError as exc:
        if exc.status == 409:  # empty repository
            return []
        raise
    times: list[int] = []
    for item in items:
        try:
            date = item["commit"]["author"]["date"]
            times.append(int(datetime.fromisoformat(date).timestamp()))
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SourceError("GitHub: unexpected commit data") from None
    return times
