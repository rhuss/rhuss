"""Tests for the talks archive parser (T010, FR-007, FR-013, research.md R2)."""

from pathlib import Path

import pytest

from profilegen.model import Talk
import profilegen.sources.http as http
from profilegen.sources.talks import (
    ARCHIVE_PAGES,
    _resolve,
    archive_years,
    fetch_archive,
    parse_entry,
    parse_archive,
    per_year,
    recent,
    talks_from_snapshot,
)

FIXTURE = Path(__file__).parent / "fixtures" / "archive-readme.md"
OLDEST_FIRST = Path(__file__).parent / "fixtures" / "archive-readme-oldest-first.md"
PAGES = "https://ro14nd-talks.github.io/archive/"


def video(vid):
    return {"label": "Video", "url": f"https://www.youtube.com/watch?v={vid}"}


# Expected parse result in archive order (file order, newest year first).
# Columns: year, order, title, url, month, venue prefix, extras
EXPECTED = [
    (2026, 0, "Spec-Driven Development in Practice", PAGES + "2026/sdd-codeeurope-2026.pdf", 6, "Code Europe", [video("sddCodeEurope")]),
    (2026, 1, "Agents on Kubernetes", "https://speakerdeck.com/rhuss/agents-on-kubernetes", 3, "KubeCon Europe",
     [video("agentsOnK8s"), {"label": "Demo", "url": "https://github.com/rhuss/agents-demo"}]),
    (2026, 2, "MCP Servers Explained", PAGES + "2026/mcp-jug-darmstadt.pdf", 10, "JUG Darmstadt", [video("mcpExplained")]),
    (2026, 3, "Fireside Chat on Open Source", None, None, "Red Hat Summit Connect", []),
    (2026, 4, "Spec Kit Workshop", PAGES + "2026/speckit-workshop.pdf", 6, "Devoxx Poland", []),
    (2025, 0, "Platform Engineering with AI", "https://slides.com/rhuss/platform-engineering-ai", None, "DevOpsCon Berlin", []),
    (2025, 1, "Kubernetes Operators in Java", None, 4, "Cloud Native Meetup Frankfurt", []),
    (2025, 2, "Knative Functions Deep Dive", PAGES + "2025/knative-functions.pdf", 11, "KubeCon North America",
     [video("knativeFunctions")]),
    (2025, 3, "Some random note without structure", None, None, None, []),
    (2025, 4, "Serverless Java", PAGES + "2025/serverless-java.pdf", 3, "JavaLand", []),
    (2024, 0, "Kubernetes Patterns, 2nd Edition", "https://k8spatterns.com", 10, "Devoxx Belgium", [video("k8sPatterns")]),
    (2024, 1, "WebAssembly on Kubernetes", PAGES + "2024/wasm-k8s.pdf", 7, "WeAreDevelopers", []),
    (2024, 2, "Hallway Track Panel", None, 9, "Container Days", []),
    (2023, 0, "Docker Maven Plugin Revisited", PAGES + "2023/dmp-revisited.pdf", 6, "JCON Europe",
     [video("dmpRevisited"), {"label": "Demo", "url": "https://github.com/fabric8io/docker-maven-plugin"}]),
    (2023, 1, "Jolokia 2.0", "https://jolokia.org", 9, "JavaZone", []),
    (2021, 0, "Tekton Pipelines", PAGES + "2021/tekton-pipelines.pdf", 2, "DevConf.CZ", []),
    (2019, 0, "Knative Serving", PAGES + "2019/knative-serving.pdf", 11, "Devoxx Belgium", []),
    (2019, 1, "Operators 101", "https://example.org/operators-101", 5, "Kubernetes Meetup Munich", [video("operators101")]),
]

# FR-013 ordering of all fixture talks: year desc, dated by month desc
# (ties: later archive position first), undated after dated in archive order.
EXPECTED_RECENT_TITLES = [
    "MCP Servers Explained",  # 2026, 10
    "Spec Kit Workshop",  # 2026, 6, order 4 (tie, later position first)
    "Spec-Driven Development in Practice",  # 2026, 6, order 0
    "Agents on Kubernetes",  # 2026, 3
    "Fireside Chat on Open Source",  # 2026, undated
    "Knative Functions Deep Dive",  # 2025, 11
    "Kubernetes Operators in Java",  # 2025, 4
    "Serverless Java",  # 2025, 3
    "Platform Engineering with AI",  # 2025, undated, order 0
    "Some random note without structure",  # 2025, undated, order 3
    "Kubernetes Patterns, 2nd Edition",  # 2024, 10
    "Hallway Track Panel",  # 2024, 9
    "WebAssembly on Kubernetes",  # 2024, 7
    "Jolokia 2.0",  # 2023, 9
    "Docker Maven Plugin Revisited",  # 2023, 6
    "Tekton Pipelines",  # 2021, 2
    "Knative Serving",  # 2019, 11
    "Operators 101",  # 2019, 5
]


@pytest.fixture(scope="module")
def talks():
    return parse_archive(FIXTURE.read_text(encoding="utf-8"))


def by_title(talks, title):
    matches = [t for t in talks if t.title == title]
    assert len(matches) == 1, f"expected exactly one talk titled {title!r}, got {matches!r}"
    return matches[0]


def test_archive_pages_constant():
    assert ARCHIVE_PAGES == PAGES


def test_parse_returns_talk_objects(talks):
    assert talks
    assert all(isinstance(t, Talk) for t in talks)


def test_one_bullet_is_one_talk(talks):
    assert len(talks) == 18
    counts = {}
    for t in talks:
        counts[t.year] = counts.get(t.year, 0) + 1
    assert counts == {2026: 5, 2025: 5, 2024: 3, 2023: 2, 2021: 1, 2019: 2}


def test_archive_order_and_order_index(talks):
    assert [(t.year, t.order, t.title) for t in talks] == [(y, o, title) for (y, o, title, *_rest) in EXPECTED]


@pytest.mark.parametrize(
    "year,order,title,url,month,venue,extras", EXPECTED, ids=[e[2] for e in EXPECTED]
)
def test_entry_fields(talks, year, order, title, url, month, venue, extras):
    t = by_title(talks, title)
    assert t.year == year
    assert t.order == order
    assert t.url == url
    assert t.month == month
    assert t.extras == extras
    if venue is not None:
        assert t.venue.startswith(venue), t.venue


def test_separator_dash(talks):
    t = by_title(talks, "Spec-Driven Development in Practice")
    assert t.venue.startswith("Code Europe, Krakow")
    assert t.month == 6


def test_separator_comma(talks):
    t = by_title(talks, "Agents on Kubernetes")
    assert t.venue.startswith("KubeCon Europe, London")
    assert t.month == 3


def test_no_separator(talks):
    t = by_title(talks, "MCP Servers Explained")
    assert t.venue.startswith("JUG Darmstadt")
    assert t.month == 10


def test_bold_only_title_without_link(talks):
    t = by_title(talks, "Fireside Chat on Open Source")
    assert t.url is None
    assert t.month is None
    assert t.venue.startswith("Red Hat Summit Connect")


def test_link_without_bold_year_only_with_extra_text(talks):
    t = by_title(talks, "Platform Engineering with AI")
    assert t.url == "https://slides.com/rhuss/platform-engineering-ai"
    assert t.month is None
    assert t.venue.startswith("DevOpsCon Berlin")


def test_plain_text_title_single_digit_month(talks):
    t = by_title(talks, "Kubernetes Operators in Java")
    assert t.url is None
    assert t.month == 4
    assert t.venue.startswith("Cloud Native Meetup Frankfurt")


def test_title_with_comma_inside_link(talks):
    t = by_title(talks, "Kubernetes Patterns, 2nd Edition")
    assert t.url == "https://k8spatterns.com"
    assert t.venue.startswith("Devoxx Belgium")


def test_unparseable_entry_renders_raw_text(talks):
    t = by_title(talks, "Some random note without structure")
    assert t.year == 2025
    assert t.url is None
    assert t.month is None
    assert t.extras == []


def test_relative_links_resolve_to_pages(talks):
    t = by_title(talks, "Spec-Driven Development in Practice")
    assert t.url == "https://ro14nd-talks.github.io/archive/2026/sdd-codeeurope-2026.pdf"


@pytest.mark.parametrize("link", ["2026/x.pdf", "/2026/x.pdf", " /2026/x.pdf "])
def test_relative_and_root_relative_links_resolve_under_archive(link):
    assert _resolve(link) == "https://ro14nd-talks.github.io/archive/2026/x.pdf"


@pytest.mark.parametrize(
    "link", ["https://example.org/a/b.pdf", "http://example.org/x", "https://ro14nd-talks.github.io/other/x.pdf"]
)
def test_resolve_keeps_absolute_links(link):
    assert _resolve(link) == link


def test_root_relative_link_in_entry():
    [t] = parse_archive("# 2026\n\n* **[T](/2026/t.pdf)** - ConfX, 06/2026 | [Slides](/2026/s.pdf)\n")
    assert t.url == PAGES + "2026/t.pdf"
    assert t.extras == [{"label": "Slides", "url": PAGES + "2026/s.pdf"}]


def test_leading_colon_stripped_from_venue():
    t = parse_entry("**Title**: Venue, 03/2025", 2025, 0)
    assert t.title == "Title"
    assert t.venue == "Venue"
    assert t.month == 3


def test_absolute_links_kept(talks):
    assert by_title(talks, "Jolokia 2.0").url == "https://jolokia.org"
    assert by_title(talks, "Operators 101").url == "https://example.org/operators-101"


def test_extras_collected(talks):
    t = by_title(talks, "Docker Maven Plugin Revisited")
    assert t.extras == [
        {"label": "Video", "url": "https://www.youtube.com/watch?v=dmpRevisited"},
        {"label": "Demo", "url": "https://github.com/fabric8io/docker-maven-plugin"},
    ]


def test_titles_and_venues_are_clean(talks):
    for t in talks:
        for marker in ("**", "](", "|"):
            assert marker not in t.title, t
            assert marker not in t.venue, t
        assert not t.title.startswith(("* ", "[")), t
        assert t.title == t.title.strip(), t
        assert not t.venue.startswith(("-", ",", " ")), t
        assert "Video" not in t.venue and "Demo" not in t.venue, t


def test_per_year_covers_every_year_with_zeros(talks):
    assert per_year(talks) == [
        (2019, 2),
        (2020, 0),  # heading without entries
        (2021, 1),
        (2022, 0),  # no heading at all
        (2023, 2),
        (2024, 3),
        (2025, 5),
        (2026, 5),
    ]


def test_per_year_independent_of_input_order(talks):
    assert per_year(list(reversed(talks))) == per_year(talks)


def test_archive_years_lists_every_heading_sorted_unique():
    markdown = "# 2026\n\n* a - b, 2026\n\n# 2024\n\n# Other\n\n# 2019\n\n## 2024\n"
    assert archive_years(markdown) == [2019, 2024, 2026]
    assert archive_years(FIXTURE.read_text(encoding="utf-8")) == [2019, 2020, 2021, 2023, 2024, 2025, 2026]
    assert archive_years("# Talks\n\n* orphan - x, 2020\n") == []


def test_per_year_spans_empty_edge_year_headings(talks):
    # Empty headings for 2017 (before the first talk) and 2027 (after the last) widen the range.
    result = per_year(talks, [2017, 2019, 2027])
    assert result[0] == (2017, 0)
    assert result[1] == (2018, 0)
    assert result[-1] == (2027, 0)
    assert result[2:-1] == per_year(talks)


def test_per_year_years_without_talks():
    assert per_year([], [2024, 2026]) == [(2024, 0), (2025, 0), (2026, 0)]
    assert per_year([], []) == []
    assert per_year([], None) == []


def test_empty_edge_year_headings_in_markdown():
    markdown = "# 2027\n\n# 2026\n\n* **[T](t.pdf)** - ConfX, 06/2026\n\n# 2024\n"
    assert per_year(parse_archive(markdown), archive_years(markdown)) == [(2024, 0), (2025, 0), (2026, 1), (2027, 0)]


def test_per_year_single_talk():
    t = Talk(year=2024, month=None, title="Solo", url=None, venue="", extras=[], order=0)
    assert per_year([t]) == [(2024, 1)]


def test_recent_full_ordering(talks):
    assert [t.title for t in recent(talks, 100)] == EXPECTED_RECENT_TITLES


def test_recent_limits_to_n(talks):
    assert [t.title for t in recent(talks, 8)] == EXPECTED_RECENT_TITLES[:8]
    assert [t.title for t in recent(talks, 5)] == EXPECTED_RECENT_TITLES[:5]


def test_recent_uses_order_field_not_list_position(talks):
    assert [t.title for t in recent(list(reversed(talks)), 100)] == EXPECTED_RECENT_TITLES


def test_recent_same_month_tie_later_archive_position_first(talks):
    titles = [t.title for t in recent(talks, 100)]
    assert titles.index("Spec Kit Workshop") < titles.index("Spec-Driven Development in Practice")


def test_recent_undated_after_dated_in_archive_order(talks):
    in_2025 = [t.title for t in recent(talks, 100) if t.year == 2025]
    assert in_2025 == [
        "Knative Functions Deep Dive",
        "Kubernetes Operators in Java",
        "Serverless Java",
        "Platform Engineering with AI",
        "Some random note without structure",
    ]


def test_readme_without_year_heading_yields_no_talks():
    markdown = (
        "# Talks by Roland Huß\n\n"
        "Some intro text.\n\n"
        "* **[Orphan Talk](orphan.pdf)** - Nowhere Conf, 01/2026\n"
    )
    assert parse_archive(markdown) == []
    assert parse_archive("") == []


def test_per_year_of_no_talks_is_empty():
    assert per_year([]) == []
    assert recent([], 8) == []


# --- Real archive layout: no title heading, years oldest first, mixed extra-link forms ---

# Columns: year, order, title, url, month, exact venue, extras
EXPECTED_OLDEST_FIRST = [
    (2013, 0, "Jolokia: JMX on Capsaicin", PAGES + "2013/jolokia-jax.pdf", 4, "JAX, Mainz",
     [{"label": "Video", "url": "https://www.youtube.com/watch?v=jolokiaJax"}]),
    (2013, 1, "Docker for Java Developers", PAGES + "2013/docker-java.pdf", 11, "W-JAX, Munich",
     [{"label": "Video (GER)", "url": "https://www.youtube.com/watch?v=dockerJavaGer"}]),
    (2014, 0, "Docker Maven Plugin", PAGES + "2014/dmp-javaone.pdf", 9, "JavaOne, San Francisco",
     [{"label": "Demo code", "url": "https://github.com/rhuss/docker-maven-sample"}]),
    (2014, 1, "Microservices with Docker", "https://speakerdeck.com/rhuss/microservices-docker", 11,
     "Devoxx Belgium, Antwerp",
     [{"label": "Slides", "url": PAGES + "2014/microservices-docker.pdf"},
      {"label": "Docker Image", "url": "https://hub.docker.com/r/rhuss/microservices-demo"}]),
    (2014, 2, "Jolokia Hackergarten", None, None, "JUG Saxony, Dresden", []),
    (2016, 0, "Kubernetes for Java Developers", PAGES + "2016/k8s-java.pdf", 3, "JavaLand, Bruehl",
     [{"label": "Video", "url": "https://www.youtube.com/watch?v=k8sJavaLand"},
      {"label": "Demo", "url": PAGES + "demos/k8s-java/"}]),
    (2026, 0, "Agentic Coding with Specs", PAGES + "2026/agentic-specs.pdf", 3, "KubeCon Europe, Amsterdam",
     [{"label": "Video", "url": "https://www.youtube.com/watch?v=agenticSpecs"}]),
    (2026, 1, "Coding Agents on a Budget", PAGES + "2026/agents-budget.pdf", 10, "JUG Darmstadt",
     [{"label": "Video (GER)", "url": "https://www.youtube.com/watch?v=agentsBudget"}]),
]


@pytest.fixture(scope="module")
def oldest_first():
    return parse_archive(OLDEST_FIRST.read_text(encoding="utf-8"))


def test_oldest_first_archive_order(oldest_first):
    assert [(t.year, t.order, t.title) for t in oldest_first] == [
        (y, o, title) for (y, o, title, *_rest) in EXPECTED_OLDEST_FIRST
    ]


@pytest.mark.parametrize(
    "year,order,title,url,month,venue,extras",
    EXPECTED_OLDEST_FIRST,
    ids=[e[2] for e in EXPECTED_OLDEST_FIRST],
)
def test_oldest_first_entry_fields(oldest_first, year, order, title, url, month, venue, extras):
    t = by_title(oldest_first, title)
    assert (t.year, t.order, t.url, t.month) == (year, order, url, month)
    assert t.venue == venue
    assert t.extras == extras


def test_oldest_first_venues_are_clean(oldest_first):
    for t in oldest_first:
        for marker in ("](", "|", "[", "]", "(", ")", "**"):
            assert marker not in t.venue, t
            assert marker not in t.title, t
        assert not t.venue.endswith(("-", ",", " ")), t
        assert not t.venue.startswith(("-", ",", " ")), t
        for label in ("Video", "Demo", "Slides", "Docker Image"):
            assert label not in t.venue, t


def test_oldest_first_per_year_with_zero_years(oldest_first):
    assert per_year(oldest_first) == (
        [(2013, 2), (2014, 3), (2015, 0), (2016, 1)]
        + [(y, 0) for y in range(2017, 2026)]
        + [(2026, 2)]
    )


def test_oldest_first_recent_is_newest_first(oldest_first):
    assert [t.title for t in recent(oldest_first, 100)] == [
        "Coding Agents on a Budget",  # 2026, 10
        "Agentic Coding with Specs",  # 2026, 3
        "Kubernetes for Java Developers",  # 2016, 3
        "Microservices with Docker",  # 2014, 11
        "Docker Maven Plugin",  # 2014, 9
        "Jolokia Hackergarten",  # 2014, undated
        "Docker for Java Developers",  # 2013, 11
        "Jolokia: JMX on Capsaicin",  # 2013, 4
    ]
    assert [t.title for t in recent(oldest_first, 2)] == [
        "Coding Agents on a Budget",
        "Agentic Coding with Specs",
    ]


def test_venue_drops_date_token():
    [t] = parse_archive("# 2025\n\n* **[T](t.pdf)** - ConfX, 2025, keynote\n")
    assert t.venue == "ConfX, keynote"
    assert t.month is None
    [t] = parse_archive("# 2026\n\n* **[T](t.pdf)** - ConfX, 06/2026\n")
    assert t.venue == "ConfX"
    assert t.month == 6


def test_talks_from_snapshot_restores_order_per_year(talks):
    restored = talks_from_snapshot([t.to_dict() for t in talks])
    assert restored == talks
    assert [t.title for t in recent(restored, 100)] == EXPECTED_RECENT_TITLES


def test_fetch_archive_reads_raw_readme(monkeypatch):
    calls = []

    def fake_get_text(url, token=None, accept=None):
        calls.append((url, token, accept))
        return "# 2026\n"

    monkeypatch.setenv("PROFILEGEN_API_URL", "http://127.0.0.1:9/api")
    monkeypatch.setattr(http, "get_text", fake_get_text)
    assert fetch_archive("ro14nd-talks/archive", "tok") == "# 2026\n"
    assert calls == [
        ("http://127.0.0.1:9/api/repos/ro14nd-talks/archive/readme", "tok", "application/vnd.github.raw")
    ]


def test_unparseable_link_does_not_crash_the_parser():
    # A typo in the live archive must not abort the nightly job (FR-019).
    talks_ = parse_archive("# 2025\n\n* [Talk](https://[x) - Venue, 3/2025\n")
    assert len(talks_) == 1 and talks_[0].title == "Talk" and talks_[0].month == 3


def test_non_year_heading_ends_the_year_section():
    markdown = "# 2025\n\n* **Talk A** - Conf, 3/2025\n\n# Notes\n\n* not a talk\n\n# 2024\n\n* **Talk B** - Meetup\n"
    assert [(t.year, t.title) for t in parse_archive(markdown)] == [(2025, "Talk A"), (2024, "Talk B")]


@pytest.mark.parametrize(
    "text,venue",
    [
        # A year inside the venue name is part of the name (FINDING-31).
        ("**Docker Patterns** - JayDay 2013, Munich", "JayDay 2013, Munich"),
        ("**Docker Patterns** - Devoxx, Antwerp 2013", "Devoxx, Antwerp 2013"),
        # A year that is its own comma-separated field is the date and is stripped.
        ("**Docker Patterns** - JayDay, 2013, Munich", "JayDay, Munich"),
        ("**Docker Patterns** - JayDay, Munich, 2013", "JayDay, Munich"),
        ("**Docker Patterns** - 2013", ""),
    ],
)
def test_bare_year_stripped_only_as_its_own_field(text, venue):
    talk = parse_entry(text, 2013, 0)
    assert talk.venue == venue
    assert talk.month is None
