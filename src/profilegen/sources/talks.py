"""Talks archive source: the README of ``ro14nd-talks/archive`` (FR-007, FR-013).

The README is split into ``# YYYY`` year
sections (in any order, newest or oldest first); every ``* `` bullet inside a
year section is one talk. For each bullet:

* the title comes from the leading ``**[Title](url)**``, ``[Title](url)`` or
  ``**Title**`` construct, else from the text before the first `` - ``;
  entries that match none of these keep their raw text as the title;
* every markdown link after the title construct is an extra
  (``{"label": text, "url": url}``, in source order) and is removed from the
  venue together with its separator (``|``, `` - ``, ``,``, wrapping ``()``);
* the month comes from the last ``M/YYYY`` or ``MM/YYYY`` token; that token
  (or, without one, the last bare year that is a comma-separated field of
  its own) is stripped from the venue.

Relative links (with or without a leading ``/``) resolve under the
published archive site :data:`ARCHIVE_PAGES`; absolute links are kept.

:func:`archive_years` lists every year heading, including headings without
any bullet, so the chart can span the full archive range (FR-007).
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urljoin, urlsplit

from profilegen.model import Talk
from profilegen.sources import http

__all__ = [
    "ARCHIVE_PAGES",
    "parse_archive",
    "archive_years",
    "recent",
    "per_year",
    "fetch_archive",
    "talks_from_snapshot",
]

ARCHIVE_PAGES = "https://ro14nd-talks.github.io/archive/"

_YEAR_HEADING = re.compile(r"^#{1,6}\s+(\d{4})\s*#*\s*$")
_BULLET = re.compile(r"^[*-]\s+(.*\S)\s*$")  # top-level bullets only
_LINK = re.compile(r"\[([^\]]+)\]\(\s*([^)\s]+)\s*\)")
_BOLD_LINK = re.compile(r"^\*\*\[([^\]]+)\]\(\s*([^)\s]+)\s*\)\*\*(.*)$")
_LINK_BOLD = re.compile(r"^\[\*\*([^\]]+?)\*\*\]\(\s*([^)\s]+)\s*\)(.*)$")
_PLAIN_LINK = re.compile(r"^\[([^\]]+)\]\(\s*([^)\s]+)\s*\)(.*)$")
_BOLD = re.compile(r"^\*\*([^*]+)\*\*(.*)$")

# Placeholder for a removed extra link while the venue is cleaned up.
_MARK = "\x00"
# Parentheses that wrap nothing but extra links, e.g. "([Demo code](url))".
_WRAPPED_MARKS = re.compile(r"\(\s*" + _MARK + r"(?:[\s,;|-]*" + _MARK + r")*\s*\)")
# An extra link together with the separator in front of it.
_MARK_WITH_SEP = re.compile(r"\s*(?:\||,|;|-)?\s*" + _MARK)

_MONTH_DATE = re.compile(r"(?<!\d)(\d{1,2})/(\d{4})(?!\d)")
# A bare year that is a comma-separated field of its own ("Conf, 2013, Munich").
_YEAR_FIELD = re.compile(r"(?:^|(?<=,))\s*(?P<year>(?:19|20)\d{2})\s*(?=,|$)")


def _resolve(url: str) -> str:
    """Relative archive links point to the published GitHub Pages site.

    ``2026/x.pdf`` and ``/2026/x.pdf`` both resolve under ``ARCHIVE_PAGES``
    (the archive is published below ``/archive/``, so a root-relative link
    means the archive root, not the host root). Absolute links are kept.
    """
    url = url.strip()
    try:
        scheme = urlsplit(url).scheme
    except ValueError:  # for example "https://[x": keep the text, never crash the run
        return url
    if scheme:
        return url
    if url.startswith("//"):
        return "https:" + url
    return urljoin(ARCHIVE_PAGES, url.lstrip("/"))


def _split_title(text: str) -> tuple[str, str | None, str]:
    """Return (title, url, rest) for one bullet's text."""
    for pattern in (_BOLD_LINK, _LINK_BOLD, _PLAIN_LINK):
        m = pattern.match(text)
        if m:
            return m.group(1).strip(), _resolve(m.group(2)), m.group(3)
    m = _BOLD.match(text)
    if m:
        return m.group(1).strip(), None, m.group(2)
    if " - " in text:
        title, rest = text.split(" - ", 1)
        return title.strip(), None, rest
    # Unparseable entry: the raw text is the title (FR-007).
    return text, None, ""


def _cut(text: str, start: int, end: int) -> str:
    """Remove text[start:end] together with its separating comma/whitespace."""
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    # Keep the separator that followed the removed token: "A, 2025, b" -> "A, b".
    comma = after.startswith(",")
    before = before.rstrip(", ")
    after = after.lstrip(", ")
    if before and after:
        return before + (", " if comma else " ") + after
    return before or after


def _clean(text: str) -> str:
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s*\|\s*", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)
    # A leading ":" separates a bold title from its venue ("**Title**: Venue").
    return text.strip().lstrip(":-,;| \t").rstrip("-,;| \t").strip()


def _venue_and_month(rest: str) -> tuple[str, int | None, list[dict]]:
    extras = [{"label": label.strip(), "url": _resolve(url)} for label, url in _LINK.findall(rest)]
    venue = _LINK.sub(_MARK, rest)
    venue = _WRAPPED_MARKS.sub(_MARK, venue)
    venue = _MARK_WITH_SEP.sub("", venue)
    venue = _clean(venue)

    month = None
    span = None
    dates = list(_MONTH_DATE.finditer(venue))
    if dates:
        span = dates[-1].span()
        if 1 <= int(dates[-1].group(1)) <= 12:
            month = int(dates[-1].group(1))
    else:
        # A year inside a venue name ("JayDay 2013, Munich") stays part of the name.
        years = list(_YEAR_FIELD.finditer(venue))
        if years:
            span = years[-1].span("year")
    if span is not None:
        venue = _clean(_cut(venue, *span))
    return venue, month, extras


def parse_entry(text: str, year: int, order: int) -> Talk:
    """Parse the text of one bullet (without the bullet marker)."""
    title, url, rest = _split_title(text.strip())
    if not rest.strip():
        return Talk(year=year, month=None, title=title, url=url, venue="", extras=[], order=order)
    venue, month, extras = _venue_and_month(rest)
    return Talk(year=year, month=month, title=title, url=url, venue=venue, extras=extras, order=order)


def parse_archive(markdown: str) -> list[Talk]:
    """All talks in archive (file) order; ``order`` is the index within its year section.

    Bullets before the first year heading are ignored, so a README without
    any year heading yields no talks.
    """
    talks: list[Talk] = []
    year: int | None = None
    index: Counter[int] = Counter()
    for line in markdown.splitlines():
        heading = _YEAR_HEADING.match(line)
        if heading:
            year = int(heading.group(1))
            continue
        if line.startswith("# "):
            # Another top-level heading ends the current year section.
            year = None
            continue
        if year is None:
            continue
        bullet = _BULLET.match(line)
        if not bullet:
            continue
        talks.append(parse_entry(bullet.group(1), year, index[year]))
        index[year] += 1
    return talks


def archive_years(markdown: str) -> list[int]:
    """Every year heading of the archive, sorted ascending and unique.

    Headings without any bullet are included, so empty years at the start or
    end of the archive still count for the chart range (FR-007).
    """
    return sorted({int(m.group(1)) for m in map(_YEAR_HEADING.match, markdown.splitlines()) if m})


def _recent_key(talk: Talk) -> tuple:
    if talk.month is None:
        # Undated entries follow the dated ones of the same year, in archive order.
        return (-talk.year, 1, 0, talk.order)
    # Same month: the later archive position comes first.
    return (-talk.year, 0, -talk.month, -talk.order)


def recent(talks: list[Talk], n: int) -> list[Talk]:
    """The n most recent talks (FR-013 ordering), independent of list order."""
    return sorted(talks, key=_recent_key)[:n]


def per_year(talks: list[Talk], years: list[int] | None = None) -> list[tuple[int, int]]:
    """(year, count) for every year from the first to the last year, zeros included.

    The range spans the union of the talk years and ``years`` (the archive
    year headings from :func:`archive_years`), so empty headings at either
    end of the archive are part of the chart.
    """
    counts = Counter(t.year for t in talks)
    span = set(counts) | set(years or [])
    if not span:
        return []
    return [(y, counts.get(y, 0)) for y in range(min(span), max(span) + 1)]


def talks_from_snapshot(items: list[dict]) -> list[Talk]:
    """Rebuild talks from snapshot dicts (archive order), restoring ``order`` per year."""
    index: Counter[int] = Counter()
    talks = []
    for item in items:
        talk = Talk.from_dict(item, order=index[item["year"]])
        index[item["year"]] += 1
        talks.append(talk)
    return talks


def fetch_archive(repo: str, token: str | None = None) -> str:
    """Raw markdown of the archive repository's README."""
    return http.get_text(
        f"{http.api_url()}/repos/{repo}/readme", token, accept="application/vnd.github.raw"
    )
