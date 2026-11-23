"""Data model for profile.yaml and parsed live data, plus loading of profile.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from profilegen.text import DEFAULT_ABBREVIATIONS

# The data-file groups that list GitHub repositories, in page and data-file order.
PROJECT_SECTIONS = ("main_projects", "community", "more_tools")

# Community roles (data-file values) and how the README shows them; a role
# without a label is shown as written.
ROLES = ("creator", "co-creator", "maintainer", "alumni-maintainer", "contributor", "lead")
ROLE_LABELS = {"alumni-maintainer": "alumni maintainer"}


class ProfileError(Exception):
    """Raised when profile.yaml cannot be loaded or fails validation.

    ``errors`` holds one ``"<path>: <message>"`` string per problem.
    """

    def __init__(self, errors: list[str] | str):
        self.errors: list[str] = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("\n".join(self.errors))

    def __str__(self) -> str:
        return "\n".join(self.errors)


@dataclass
class Link:
    label: str
    url: str
    emoji: str | None = None


@dataclass
class Badge:
    label: str
    color: str
    logo: str | None = None
    logo_color: str | None = None


@dataclass
class Project:
    repo: str
    name: str | None = None
    url: str | None = None
    emoji: str | None = None
    description: str | None = None
    tagline: str | None = None
    role: str | None = None


@dataclass
class Book:
    title: str
    description: str
    url: str
    cover: str | None = None


@dataclass
class Settings:
    talks_shown: int = 8
    posts_shown: int = 3
    demote_after_days: int = 60
    promote_commits: int = 10
    promote_window_days: int = 30
    owned_owners: list[str] = field(default_factory=lambda: ["rhuss", "AgentTacho", "k8spatterns"])
    owned_extra_repos: list[str] = field(
        default_factory=lambda: ["jolokia/jolokia", "fabric8io/docker-maven-plugin"]
    )
    abbreviations: list[str] = field(default_factory=lambda: list(DEFAULT_ABBREVIATIONS))
    scan_roots: list[str] = field(default_factory=lambda: ["~/Development", "~/Work/projects"])
    feed_url: str = "https://ro14nd.de/index.xml"
    talks_repo: str = "ro14nd-talks/archive"


SETTINGS_KEYS = tuple(f.name for f in fields(Settings))


@dataclass
class Profile:
    name: str
    intro: str
    links: list[Link]
    badges: list[Badge]
    main_projects: list[Project]
    community: list[Project]
    books: list[Book]
    more_tools: list[Project]
    settings: Settings


@dataclass
class Talk:
    year: int
    month: int | None
    title: str
    url: str | None
    venue: str
    extras: list[dict] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "month": self.month,
            "title": self.title,
            "url": self.url,
            "venue": self.venue,
            "extras": [dict(e) for e in self.extras],
        }

    @classmethod
    def from_dict(cls, d: dict, order: int = 0) -> Talk:
        return cls(
            year=d["year"],
            month=d.get("month"),
            title=d["title"],
            url=d.get("url"),
            venue=d.get("venue", ""),
            extras=[dict(e) for e in d.get("extras", [])],
            order=order,
        )


@dataclass
class BlogPost:
    title: str
    url: str
    date: str  # YYYY-MM-DD

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "date": self.date}


@dataclass
class RepoInfo:
    full_name: str
    html_url: str
    stars: int
    private: bool
    fork: bool
    archived: bool


def load_yaml(path) -> dict:
    """Read and parse a YAML file. Raises ``ProfileError`` on unreadable files or
    YAML syntax errors (with the 1-based line number of the problem)."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ProfileError(f"{p.name}: cannot read file: {e}") from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
        problem = getattr(e, "problem", None) or str(e)
        if mark is not None:
            raise ProfileError(f"{p.name}: YAML syntax error at line {mark.line + 1}: {problem}") from e
        raise ProfileError(f"{p.name}: YAML syntax error: {problem}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ProfileError(f"{p.name}: top level must be a mapping")
    return data


def _project(d: dict) -> Project:
    return Project(
        repo=d["repo"],
        name=d.get("name"),
        url=d.get("url"),
        emoji=d.get("emoji"),
        description=d.get("description"),
        tagline=d.get("tagline"),
        role=d.get("role"),
    )


def profile_from_dict(d: dict) -> Profile:
    """Build a ``Profile`` from an already validated mapping."""
    settings_d = d.get("settings") or {}
    settings = Settings(**{k: v for k, v in settings_d.items() if k in SETTINGS_KEYS})
    return Profile(
        name=d["name"],
        intro=d["intro"],
        links=[Link(label=x["label"], url=x["url"], emoji=x.get("emoji")) for x in d.get("links") or []],
        badges=[
            Badge(label=x["label"], color=str(x["color"]), logo=x.get("logo"), logo_color=x.get("logo_color"))
            for x in d.get("badges") or []
        ],
        main_projects=[_project(x) for x in d.get("main_projects") or []],
        community=[_project(x) for x in d.get("community") or []],
        books=[
            Book(title=x["title"], description=x["description"], url=x["url"], cover=x.get("cover"))
            for x in d.get("books") or []
        ],
        more_tools=[_project(x) for x in d.get("more_tools") or []],
        settings=settings,
    )


def load_profile(path) -> Profile:
    """Load, validate and convert profile.yaml. Raises ``ProfileError`` with all
    problems found."""
    from profilegen.validate import validate

    data = load_yaml(path)
    errors = validate(data)
    if errors:
        raise ProfileError(errors)
    return profile_from_dict(data)
