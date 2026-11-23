"""Validation of the profile.yaml mapping (FR-024).

``validate`` returns a list of ``"<path>: <message>"`` strings; an empty list
means the profile is valid.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

from profilegen.model import PROJECT_SECTIONS, ROLES, SETTINGS_KEYS
from profilegen.text import DEFAULT_ABBREVIATIONS, TAGLINE_MAX, check_tagline, count_sentences

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

TOP_LEVEL_REQUIRED = ("name", "intro", "links", "main_projects", "books")
TOP_LEVEL_OPTIONAL = ("badges", "community", "more_tools", "settings")

INTRO_MAX = 160
MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
MAIN_PROJECTS_MIN, MAIN_PROJECTS_MAX = 1, 12
DESCRIPTION_MAX_SENTENCES = 3
TALKS_SHOWN_MIN, TALKS_SHOWN_MAX = 5, 10

LINK_KEYS = ("label", "url", "emoji")
BADGE_KEYS = ("label", "color", "logo", "logo_color")
BOOK_KEYS = ("title", "description", "url", "cover")
PROJECT_BASE_KEYS = ("repo", "name", "url", "emoji")
MAIN, COMMUNITY, MORE_TOOLS = PROJECT_SECTIONS
GROUP_KEYS = {
    MAIN: PROJECT_BASE_KEYS + ("description",),
    COMMUNITY: PROJECT_BASE_KEYS + ("tagline", "role"),
    MORE_TOOLS: PROJECT_BASE_KEYS + ("tagline",),
}

POSITIVE_INT_SETTINGS = ("posts_shown", "demote_after_days", "promote_commits", "promote_window_days")
STRING_LIST_SETTINGS = ("owned_owners", "owned_extra_repos", "abbreviations", "scan_roots")


def _hostname(url: str) -> str | None:
    """Lowercase host of ``url``; None when there is none or the URL cannot be parsed."""
    try:
        host = urlparse(url).hostname
    except ValueError:  # for example "https://[x"
        return None
    return host.lower() if host else None


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


class _Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def err(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    def unknown_keys(self, d: dict, allowed, prefix: str) -> None:
        for k in d:
            if k not in allowed:
                self.err(f"{prefix}{k}", "unknown key")

    def required_str(self, d: dict, key: str, path: str) -> str | None:
        if key not in d or d[key] is None:
            self.err(path, "required")
            return None
        v = d[key]
        if not isinstance(v, str):
            self.err(path, "must be a string")
            return None
        if not v.strip():
            self.err(path, "must not be empty")
            return None
        return v

    def optional_str(self, d: dict, key: str, path: str) -> str | None:
        if key not in d or d[key] is None:
            return None
        v = d[key]
        if not _is_nonempty_str(v):
            self.err(path, "must be a non-empty string")
            return None
        return v

    def https_url(self, value: str | None, path: str) -> None:
        if value is not None and (not value.startswith("https://") or not _hostname(value)):
            self.err(path, "must be an https:// URL with a host")

    def one_line(self, value: str | None, path: str, max_len: int | None) -> None:
        if value is None:
            return
        msg = check_tagline(value, max_len)
        if msg:
            self.err(path, msg)

    def list_of_mappings(self, d: dict, key: str, required: bool) -> list[dict] | None:
        if key not in d or d[key] is None:
            if required:
                self.err(key, "required")
            return None
        v = d[key]
        if not isinstance(v, list):
            self.err(key, "must be a list")
            return None
        ok = True
        for i, item in enumerate(v):
            if not isinstance(item, dict):
                self.err(f"{key}[{i}]", "must be a mapping")
                ok = False
        return v if ok else [x for x in v if isinstance(x, dict)]


def _abbreviations(d: dict) -> list[str]:
    settings = d.get("settings")
    if isinstance(settings, dict):
        abbr = settings.get("abbreviations")
        if isinstance(abbr, list) and all(isinstance(a, str) for a in abbr):
            return abbr
    return DEFAULT_ABBREVIATIONS


def validate(profile_dict: dict) -> list[str]:
    c = _Checker()
    d = profile_dict
    if not isinstance(d, dict):
        c.err("profile", "top level must be a mapping")
        return c.errors

    allowed = set(TOP_LEVEL_REQUIRED) | set(TOP_LEVEL_OPTIONAL)
    c.unknown_keys(d, allowed, "")

    c.required_str(d, "name", "name")
    intro = c.required_str(d, "intro", "intro")
    if intro is not None:
        # The intro may contain Markdown links; limits apply to the visible text, link targets must be https.
        for target in MD_LINK.findall(intro):
            if urlparse(target[1]).scheme != "https" or not urlparse(target[1]).netloc:
                c.err("intro", f"link target must be an https URL: {target[1]}")
        c.one_line(MD_LINK.sub(lambda m: m.group(1), intro), "intro", INTRO_MAX)

    _validate_links(c, d)
    _validate_badges(c, d)
    _validate_projects(c, d, _abbreviations(d))
    _validate_books(c, d)
    _validate_settings(c, d)
    return c.errors


def _validate_links(c: _Checker, d: dict) -> None:
    links = c.list_of_mappings(d, "links", required=True)
    if links is None:
        return
    has_blog = has_linkedin = False
    for i, link in enumerate(links):
        p = f"links[{i}]"
        c.unknown_keys(link, LINK_KEYS, f"{p}.")
        c.required_str(link, "label", f"{p}.label")
        url = c.required_str(link, "url", f"{p}.url")
        c.https_url(url, f"{p}.url")
        c.optional_str(link, "emoji", f"{p}.emoji")
        if url:
            host = _hostname(url) or ""
            if host in ("ro14nd.de", "www.ro14nd.de"):
                has_blog = True
            if host == "linkedin.com" or host.endswith(".linkedin.com"):
                has_linkedin = True
    if not has_blog:
        c.err("links", "missing blog link (https://ro14nd.de)")
    if not has_linkedin:
        c.err("links", "missing LinkedIn link (linkedin.com)")


def _validate_badges(c: _Checker, d: dict) -> None:
    badges = c.list_of_mappings(d, "badges", required=False)
    for i, badge in enumerate(badges or []):
        p = f"badges[{i}]"
        c.unknown_keys(badge, BADGE_KEYS, f"{p}.")
        c.required_str(badge, "label", f"{p}.label")
        if isinstance(badge.get("color"), (int, float)) and not isinstance(badge.get("color"), bool):
            c.err(f"{p}.color", "must be a string (quote hex colors)")
        else:
            c.required_str(badge, "color", f"{p}.color")
        c.optional_str(badge, "logo", f"{p}.logo")
        c.optional_str(badge, "logo_color", f"{p}.logo_color")


def _validate_projects(c: _Checker, d: dict, abbreviations: list[str]) -> None:
    seen: dict[str, str] = {}
    for group in PROJECT_SECTIONS:
        required = group == MAIN
        entries = c.list_of_mappings(d, group, required=required)
        if entries is None:
            continue
        if group == MAIN:
            raw = d[group]
            if not MAIN_PROJECTS_MIN <= len(raw) <= MAIN_PROJECTS_MAX:
                c.err(group, f"{len(raw)} entries, must be {MAIN_PROJECTS_MIN}..{MAIN_PROJECTS_MAX}")
        for i, entry in enumerate(entries):
            p = f"{group}[{i}]"
            c.unknown_keys(entry, GROUP_KEYS[group], f"{p}.")
            _validate_repo(c, entry, p, seen)
            c.optional_str(entry, "name", f"{p}.name")
            c.https_url(c.optional_str(entry, "url", f"{p}.url"), f"{p}.url")
            c.optional_str(entry, "emoji", f"{p}.emoji")
            if group == MAIN:
                desc = c.required_str(entry, "description", f"{p}.description")
                if desc is not None:
                    n = count_sentences(desc, abbreviations)
                    if n > DESCRIPTION_MAX_SENTENCES:
                        c.err(f"{p}.description", f"{n} sentences, max {DESCRIPTION_MAX_SENTENCES}")
            else:
                tagline = c.required_str(entry, "tagline", f"{p}.tagline")
                c.one_line(tagline, f"{p}.tagline", TAGLINE_MAX)
            if group == COMMUNITY:
                if "role" not in entry or entry["role"] is None:
                    c.err(f"{p}.role", f"required, one of {', '.join(ROLES)}")
                elif entry["role"] not in ROLES:
                    c.err(f"{p}.role", f"must be one of {', '.join(ROLES)}")


def _validate_repo(c: _Checker, entry: dict, p: str, seen: dict[str, str]) -> None:
    path = f"{p}.repo"
    if "repo" not in entry or entry["repo"] is None:
        c.err(path, "required")
        return
    repo = entry["repo"]
    if not isinstance(repo, str) or not REPO_RE.match(repo):
        c.err(path, "must have the form owner/name")
        return
    key = repo.lower()
    if key in seen:
        c.err(path, f"{repo} already listed at {seen[key]}")
    else:
        seen[key] = p


def _validate_books(c: _Checker, d: dict) -> None:
    books = c.list_of_mappings(d, "books", required=True)
    for i, book in enumerate(books or []):
        p = f"books[{i}]"
        c.unknown_keys(book, BOOK_KEYS, f"{p}.")
        c.required_str(book, "title", f"{p}.title")
        desc = c.required_str(book, "description", f"{p}.description")
        c.one_line(desc, f"{p}.description", None)
        c.https_url(c.required_str(book, "url", f"{p}.url"), f"{p}.url")
        if "cover" in book and book["cover"] is not None:
            _validate_cover(c, book["cover"], f"{p}.cover")


def _validate_cover(c: _Checker, cover, path: str) -> None:
    if not _is_nonempty_str(cover):
        c.err(path, "must be a non-empty relative path")
        return
    pp = PurePosixPath(cover)
    if "://" in cover or cover.startswith(("/", "~", "\\")) or pp.is_absolute() or ".." in pp.parts:
        c.err(path, "must be a relative path inside the repository")
    elif len(pp.parts) < 3 or pp.parts[:2] != ("assets", "books"):
        c.err(path, "must be a path under assets/books/")


def _validate_settings(c: _Checker, d: dict) -> None:
    if "settings" not in d or d["settings"] is None:
        return
    s = d["settings"]
    if not isinstance(s, dict):
        c.err("settings", "must be a mapping")
        return
    c.unknown_keys(s, SETTINGS_KEYS, "settings.")

    if "talks_shown" in s:
        v = s["talks_shown"]
        if not _is_int(v) or not TALKS_SHOWN_MIN <= v <= TALKS_SHOWN_MAX:
            c.err("settings.talks_shown", f"must be an integer in {TALKS_SHOWN_MIN}..{TALKS_SHOWN_MAX}")

    for key in POSITIVE_INT_SETTINGS:
        if key in s:
            v = s[key]
            if not _is_int(v) or v < 1:
                c.err(f"settings.{key}", "must be a positive integer")

    for key in STRING_LIST_SETTINGS:
        if key in s:
            v = s[key]
            if not isinstance(v, list) or not all(_is_nonempty_str(x) for x in v):
                c.err(f"settings.{key}", "must be a list of non-empty strings")
            elif key == "owned_extra_repos":
                for j, repo in enumerate(v):
                    if not REPO_RE.match(repo):
                        c.err(f"settings.{key}[{j}]", "must have the form owner/name")

    if "feed_url" in s:
        v = s["feed_url"]
        if not _is_nonempty_str(v) or not v.startswith("https://") or not _hostname(v):
            c.err("settings.feed_url", "must be an https:// URL with a host")

    if "talks_repo" in s:
        v = s["talks_repo"]
        if not isinstance(v, str) or not REPO_RE.match(v):
            c.err("settings.talks_repo", "must have the form owner/name")
