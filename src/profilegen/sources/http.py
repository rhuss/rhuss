"""Small HTTP layer for all live sources (stdlib only).

Error classification:

* HTTP 404 raises :class:`NotFound`, which is deliberately not a
  :class:`SourceError`, so callers can treat "repository is gone or not
  visible" differently from "source is unreachable".
* Everything else that prevents a complete, well-formed answer raises
  :class:`SourceError`: other 4xx/5xx statuses, rate limits (403 with
  ``X-RateLimit-Remaining: 0`` and 429), timeouts, connection problems and
  malformed bodies.

Exception messages name only the host, never the URL path, so a warning built
from ``str(exc)`` cannot leak a non-public repository name (FR-011). The full
URL is kept on the ``url`` attribute for debugging.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

__all__ = [
    "SourceError",
    "NotFound",
    "TIMEOUT",
    "api_url",
    "feed_url",
    "resolve_token",
    "get_text",
    "get_json",
    "get_json_list",
    "urlopen",
    "Request",
]

TIMEOUT = 20
DEFAULT_API_URL = "https://api.github.com"
USER_AGENT = "profilegen"
GITHUB_JSON = "application/vnd.github+json"
MAX_PAGES = 100

_NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')


class _TokenSafeRedirectHandler(HTTPRedirectHandler):
    """Follow redirects, but drop the Authorization header when a redirect
    leaves the original host or downgrades from https. urllib copies all
    request headers into the redirected request by default."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            old, target = urlsplit(req.full_url), urlsplit(new.full_url)
            if target.scheme != "https" or target.netloc.lower() != old.netloc.lower():
                new.remove_header("Authorization")
        return new


# Module-level so tests can replace it; same call signature as urllib's urlopen.
urlopen = build_opener(_TokenSafeRedirectHandler).open


class SourceError(Exception):
    """A live source could not deliver complete, well-formed data."""

    def __init__(self, message: str, url: str | None = None, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


class NotFound(Exception):
    """HTTP 404. Deliberately not a subclass of SourceError."""

    def __init__(self, message: str, url: str | None = None):
        super().__init__(message)
        self.url = url
        self.status = 404


def api_url() -> str:
    """GitHub API base URL, overridable via PROFILEGEN_API_URL (no trailing slash)."""
    return (os.environ.get("PROFILEGEN_API_URL") or DEFAULT_API_URL).rstrip("/")


def feed_url(default: str) -> str:
    """Blog feed URL, overridable via PROFILEGEN_FEED_URL."""
    return os.environ.get("PROFILEGEN_FEED_URL") or default


def resolve_token() -> str | None:
    """GITHUB_TOKEN, else the output of `gh auth token` if gh works, else None."""
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if token:
        return token
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    token = (result.stdout or "").strip()
    return token or None


def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc or url
    except ValueError:
        return "<invalid url>"


def _is_timeout(reason: object) -> bool:
    return isinstance(reason, (TimeoutError, socket.timeout))


def _fetch(url: str, token: str | None, accept: str | None) -> tuple[bytes, object]:
    """GET url and return (body, headers); classify every failure."""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    if token:
        headers["Authorization"] = f"Bearer {token}"
    host = _host(url)
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
            return body, response.headers
    except HTTPError as exc:
        status = exc.code
        exc_headers = exc.headers
        exc.close()
        if status == 404:
            raise NotFound(f"{host}: HTTP 404 Not Found", url=url) from None
        remaining = exc_headers.get("X-RateLimit-Remaining") if exc_headers is not None else None
        if status == 429 or (status == 403 and str(remaining).strip() == "0"):
            raise SourceError(f"{host}: rate limit exceeded (HTTP {status})", url=url, status=status) from None
        raise SourceError(f"{host}: HTTP {status}", url=url, status=status) from None
    except URLError as exc:
        if _is_timeout(exc.reason):
            raise SourceError(f"{host}: timed out after {TIMEOUT}s", url=url) from None
        raise SourceError(f"{host}: connection failed ({exc.reason})", url=url) from None
    except (TimeoutError, socket.timeout):
        raise SourceError(f"{host}: timed out after {TIMEOUT}s", url=url) from None
    except (OSError, HTTPException) as exc:
        raise SourceError(f"{host}: connection failed ({type(exc).__name__})", url=url) from None
    except ValueError as exc:
        raise SourceError(f"{host}: invalid URL ({exc})", url=url) from None


def _charset(headers: object) -> str:
    getter = getattr(headers, "get_content_charset", None)
    if callable(getter):
        charset = getter()
        if charset:
            return charset
    return "utf-8"


def _decode(body: bytes, headers: object, url: str) -> str:
    try:
        return body.decode(_charset(headers))
    except (UnicodeDecodeError, LookupError):
        raise SourceError(f"{_host(url)}: response is not valid text", url=url) from None


def _parse_json(text: str, url: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        raise SourceError(f"{_host(url)}: response is not valid JSON", url=url) from None


def get_text(url: str, token: str | None = None, accept: str | None = None) -> str:
    """GET url and return the decoded body."""
    body, headers = _fetch(url, token, accept)
    return _decode(body, headers, url)


def get_json(url: str, token: str | None = None, accept: str | None = GITHUB_JSON) -> object:
    """GET url and return the parsed JSON body."""
    body, headers = _fetch(url, token, accept)
    return _parse_json(_decode(body, headers, url), url)


def _next_link(headers: object) -> str | None:
    getter = getattr(headers, "get", None)
    link = getter("Link") if callable(getter) else None
    if not link:
        return None
    match = _NEXT_LINK.search(link)
    return match.group(1) if match else None


def get_json_list(url: str, token: str | None = None) -> list:
    """GET a paginated JSON array, following `Link: <...>; rel="next"`."""
    items: list = []
    seen: set[str] = set()
    origin = urlsplit(url)
    next_url: str | None = url
    while next_url:
        if next_url in seen or len(seen) >= MAX_PAGES:
            raise SourceError(f"{_host(url)}: pagination does not terminate", url=url)
        target = urlsplit(next_url)
        if (target.scheme, target.netloc.lower()) != (origin.scheme, origin.netloc.lower()):
            # Never send the token to a host named by a response header.
            raise SourceError(f"{_host(url)}: pagination link leaves the API host", url=url)
        seen.add(next_url)
        body, headers = _fetch(next_url, token, GITHUB_JSON)
        page = _parse_json(_decode(body, headers, next_url), next_url)
        if not isinstance(page, list):
            raise SourceError(f"{_host(next_url)}: expected a JSON array", url=next_url)
        items.extend(page)
        next_url = _next_link(headers)
    return items
