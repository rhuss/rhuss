"""Tests for the blog feed source (T011, FR-008, research.md R3)."""

from pathlib import Path

import pytest

import profilegen.sources.blog as blog
from profilegen.model import BlogPost
from profilegen.sources.blog import fetch_posts, parse_feed
from profilegen.sources.http import SourceError

FIXTURE = Path(__file__).parent / "fixtures" / "feed.xml"
FEED_URL = "https://ro14nd.de/index.xml"

# All fixture items, newest first by the full timezone-aware pubDate. The date
# is the calendar date as written in pubDate (publisher's local date, FR-008),
# not converted to UTC.
EXPECTED = [
    ("Running MCP Servers on OpenShift", "https://ro14nd.de/mcp-openshift/", "2026-11-20"),
    # Mon, 02 Nov 2026 00:30:00 +0100: local date 2026-11-02 (2026-11-01 23:30 UTC)
    ("AgentTacho: Budgets for Coding Agents", "https://ro14nd.de/agenttacho/", "2026-11-02"),
    ("Specs First: Spec-Driven Development with Claude Code", "https://ro14nd.de/sdd-claude-code/", "2026-10-14"),
    # Tue, 15 Sep 2026 20:00:00 -0500: local date 2026-09-15 (2026-09-16 01:00 UTC)
    ("Kubernetes Patterns & AI Agents", "https://ro14nd.de/k8s-patterns-ai-agents/", "2026-09-15"),
    ("A Year of Agentic Coding", "https://ro14nd.de/agentic-year/", "2026-01-01"),
]

TWO_ITEMS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>ro14nd</title>
    <item>
      <title>Older Post</title>
      <link>https://ro14nd.de/older/</link>
      <pubDate>Sat, 01 Aug 2026 12:00:00 +0000</pubDate>
      <guid>https://ro14nd.de/older/</guid>
    </item>
    <item>
      <title>Newer Post</title>
      <link>https://ro14nd.de/newer/</link>
      <pubDate>Mon, 03 Aug 2026 12:00:00 +0000</pubDate>
      <guid>https://ro14nd.de/newer/</guid>
    </item>
  </channel>
</rss>
"""

MALFORMED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Broken</title>
      <link>https://ro14nd.de/broken/</link>
  </channel>
</rss>
"""

NO_PUBDATE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Dated Post</title>
      <link>https://ro14nd.de/dated/</link>
      <pubDate>Tue, 21 Jul 2026 08:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Undated Post</title>
      <link>https://ro14nd.de/undated/</link>
    </item>
  </channel>
</rss>
"""


def as_tuples(posts):
    return [(p.title, p.url, p.date) for p in posts]


@pytest.fixture
def feed_xml():
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_feed_returns_all_items_newest_first(feed_xml):
    posts = parse_feed(feed_xml)
    assert all(isinstance(p, BlogPost) for p in posts)
    assert as_tuples(posts) == EXPECTED


def test_parse_feed_dates_are_local_publication_dates(feed_xml):
    # The date as written in pubDate, even where the UTC date differs.
    dates = {p.title: p.date for p in parse_feed(feed_xml)}
    assert dates["AgentTacho: Budgets for Coding Agents"] == "2026-11-02"
    assert dates["Kubernetes Patterns & AI Agents"] == "2026-09-15"


def test_parse_feed_sorts_by_full_datetime_not_local_date():
    # Same local date, but "Late" (00:30 +1400) is 2026-03-04 10:30 UTC and
    # "Early" (23:00 -1000) is 2026-03-05 09:00 UTC, so "Early" is newer.
    xml = """<rss version="2.0"><channel>
      <item><title>Late</title><link>https://ro14nd.de/late/</link>
        <pubDate>Thu, 05 Mar 2026 00:30:00 +1400</pubDate></item>
      <item><title>Early</title><link>https://ro14nd.de/early/</link>
        <pubDate>Wed, 04 Mar 2026 23:00:00 -1000</pubDate></item>
    </channel></rss>"""
    assert as_tuples(parse_feed(xml)) == [
        ("Early", "https://ro14nd.de/early/", "2026-03-04"),
        ("Late", "https://ro14nd.de/late/", "2026-03-05"),
    ]


def test_parse_feed_with_two_items():
    assert as_tuples(parse_feed(TWO_ITEMS)) == [
        ("Newer Post", "https://ro14nd.de/newer/", "2026-08-03"),
        ("Older Post", "https://ro14nd.de/older/", "2026-08-01"),
    ]


def test_parse_feed_malformed_xml_raises_source_error():
    with pytest.raises(SourceError):
        parse_feed(MALFORMED)
    with pytest.raises(SourceError):
        parse_feed("this is not xml at all")


def test_parse_feed_item_without_pubdate_raises_source_error():
    with pytest.raises(SourceError):
        parse_feed(NO_PUBDATE)


def fake_get_text(content, calls):
    def _get_text(url, *args, **kwargs):
        calls.append(url)
        return content

    return _get_text


def test_fetch_posts_returns_three_newest(monkeypatch, feed_xml):
    calls = []
    monkeypatch.setattr(blog, "get_text", fake_get_text(feed_xml, calls))
    posts = fetch_posts(FEED_URL, n=3)
    assert calls == [FEED_URL]
    assert as_tuples(posts) == EXPECTED[:3]


def test_fetch_posts_defaults_to_three(monkeypatch, feed_xml):
    monkeypatch.setattr(blog, "get_text", fake_get_text(feed_xml, []))
    assert as_tuples(fetch_posts(FEED_URL)) == EXPECTED[:3]


def test_fetch_posts_fewer_items_returns_what_exists(monkeypatch):
    monkeypatch.setattr(blog, "get_text", fake_get_text(TWO_ITEMS, []))
    posts = fetch_posts(FEED_URL, n=3)
    assert [p.title for p in posts] == ["Newer Post", "Older Post"]


def test_fetch_posts_propagates_source_error(monkeypatch):
    def failing(url, *args, **kwargs):
        raise SourceError("network down")

    monkeypatch.setattr(blog, "get_text", failing)
    with pytest.raises(SourceError):
        fetch_posts(FEED_URL, n=3)


def test_fetch_posts_malformed_feed_raises_source_error(monkeypatch):
    monkeypatch.setattr(blog, "get_text", fake_get_text(MALFORMED, []))
    with pytest.raises(SourceError):
        fetch_posts(FEED_URL, n=3)


# --- malformed feeds (review fixes) ---------------------------------------------


def _rss(items: str) -> str:
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>'


@pytest.mark.parametrize(
    "item",
    [
        "<item><title></title><link>https://ro14nd.de/a/</link><pubDate>Mon, 02 Nov 2026 10:00:00 +0100</pubDate></item>",
        "<item><title>A</title><link></link><pubDate>Mon, 02 Nov 2026 10:00:00 +0100</pubDate></item>",
        "<item><title>A</title><link>https://ro14nd.de/a/</link><pubDate>garbage</pubDate></item>",
        "<item><title>A</title><link>https://ro14nd.de/a/</link></item>",
    ],
    ids=["no-title", "no-link", "bad-date", "no-date"],
)
def test_malformed_item_is_a_source_error(item):
    with pytest.raises(SourceError):
        parse_feed(_rss(item))


@pytest.mark.parametrize(
    "doc",
    ["<html><body><p>Maintenance</p></body></html>", '<rss version="2.0"></rss>'],
    ids=["html-page", "rss-without-channel"],
)
def test_non_rss_document_is_a_source_error(doc):
    with pytest.raises(SourceError):
        parse_feed(doc)


def test_rss_channel_without_items_is_an_empty_list():
    assert parse_feed(_rss("")) == []
