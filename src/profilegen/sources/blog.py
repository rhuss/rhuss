"""Blog feed source: the Hugo RSS 2.0 feed of ro14nd.de (FR-008)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from profilegen.model import BlogPost
from profilegen.sources.http import SourceError, get_text

__all__ = ["parse_feed", "fetch_posts"]


def _pub_datetime(value: str) -> datetime:
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError) as exc:
        raise SourceError(f"blog feed: invalid pubDate {value!r}") from exc
    if dt.tzinfo is None:
        # RFC 2822 "-0000" means UTC without a known local offset.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_feed(xml: str) -> list[BlogPost]:
    """All feed items, newest first by pubDate.

    Raises SourceError on malformed XML or an item without pubDate, title
    or link.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise SourceError(f"blog feed: malformed XML ({exc})") from exc
    if root.tag != "rss" or root.find("channel") is None:
        # For example an HTML maintenance page that happens to be well-formed:
        # it must not replace the cached posts with an empty list.
        raise SourceError("blog feed: not an RSS document")

    dated: list[tuple[datetime, BlogPost]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if not pub:
            raise SourceError("blog feed: item without pubDate")
        if not title or not link:
            raise SourceError("blog feed: item without title or link")
        dt = _pub_datetime(pub)
        # FR-008: the publication date as written (publisher's local date), not converted to UTC.
        dated.append((dt, BlogPost(title=title, url=link, date=dt.strftime("%Y-%m-%d"))))

    # Stable sort on the full timezone-aware datetime; equal times keep feed order.
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [post for _, post in dated]


def fetch_posts(url: str, n: int = 3) -> list[BlogPost]:
    """The n newest posts of the feed at url."""
    return parse_feed(get_text(url))[:n]
