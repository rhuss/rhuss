"""Tests for profilegen.sources.http. urlopen is always stubbed: no network."""

import io
import json
import socket
import subprocess
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from profilegen.sources import http

FIXTURES = Path(__file__).parent / "fixtures" / "github"


def _headers(values: dict | None = None) -> Message:
    msg = Message()
    for key, value in (values or {}).items():
        msg[key] = value
    return msg


class FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = _headers(headers)

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """Stand-in for urlopen: maps URL to a response or an exception."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        outcome = self.routes[request.full_url]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _http_error(url: str, code: int, headers: dict | None = None) -> HTTPError:
    return HTTPError(url, code, "error", _headers(headers), io.BytesIO(b'{"message": "x"}'))


@pytest.fixture
def stub(monkeypatch):
    def install(routes: dict) -> Recorder:
        recorder = Recorder(routes)
        monkeypatch.setattr(http, "urlopen", recorder)
        return recorder

    return install


URL = "https://api.github.com/repos/rhuss/cc-spex"


# --- status classification -------------------------------------------------


def test_success_returns_parsed_json(stub):
    body = (FIXTURES / "repos-jolokia-jolokia.json").read_bytes()
    stub({URL: FakeResponse(body)})
    data = http.get_json(URL)
    assert data["full_name"] == "jolokia/jolokia"


def test_404_raises_not_found(stub):
    stub({URL: _http_error(URL, 404)})
    with pytest.raises(http.NotFound):
        http.get_json(URL)


def test_not_found_is_not_a_source_error():
    assert not issubclass(http.NotFound, http.SourceError)
    assert not issubclass(http.SourceError, http.NotFound)


def test_403_rate_limit_raises_source_error(stub):
    stub({URL: _http_error(URL, 403, {"X-RateLimit-Remaining": "0"})})
    with pytest.raises(http.SourceError, match="rate limit"):
        http.get_json(URL)


def test_other_403_raises_source_error(stub):
    stub({URL: _http_error(URL, 403, {"X-RateLimit-Remaining": "42"})})
    with pytest.raises(http.SourceError) as info:
        http.get_json(URL)
    assert info.value.status == 403
    assert "rate limit" not in str(info.value)


def test_429_raises_source_error(stub):
    stub({URL: _http_error(URL, 429)})
    with pytest.raises(http.SourceError, match="rate limit"):
        http.get_json(URL)


def test_500_raises_source_error(stub):
    stub({URL: _http_error(URL, 500)})
    with pytest.raises(http.SourceError) as info:
        http.get_text(URL)
    assert info.value.status == 500


@pytest.mark.parametrize(
    "exc",
    [
        socket.timeout("timed out"),
        TimeoutError("timed out"),
        URLError(socket.timeout("timed out")),
        URLError(TimeoutError("timed out")),
    ],
)
def test_timeouts_raise_source_error(stub, exc):
    stub({URL: exc})
    with pytest.raises(http.SourceError, match="timed out"):
        http.get_json(URL)


def test_connection_refused_raises_source_error(stub):
    stub({URL: URLError(ConnectionRefusedError("refused"))})
    with pytest.raises(http.SourceError):
        http.get_text(URL)


def test_invalid_json_raises_source_error(stub):
    stub({URL: FakeResponse(b"<html>not json</html>")})
    with pytest.raises(http.SourceError, match="JSON"):
        http.get_json(URL)


def test_error_message_names_host_not_path(stub):
    secret = "https://api.github.com/repos/rhuss/secret-thing"
    stub({secret: _http_error(secret, 500)})
    with pytest.raises(http.SourceError) as info:
        http.get_json(secret)
    assert "secret-thing" not in str(info.value)
    assert "api.github.com" in str(info.value)
    assert info.value.url == secret


def test_uses_20_second_timeout(stub):
    recorder = stub({URL: FakeResponse(b"{}")})
    http.get_json(URL)
    assert http.TIMEOUT == 20
    assert recorder.timeouts == [20]


# --- request headers --------------------------------------------------------


def test_authorization_header_only_with_token(stub):
    recorder = stub({URL: FakeResponse(b"{}")})
    http.get_json(URL, token="t0ken")
    http.get_json(URL)
    with_token, without_token = recorder.requests
    assert with_token.get_header("Authorization") == "Bearer t0ken"
    assert without_token.get_header("Authorization") is None


def test_user_agent_and_accept_headers(stub):
    recorder = stub({URL: FakeResponse(b"{}")})
    http.get_json(URL)
    http.get_text(URL, accept="application/vnd.github.raw")
    http.get_text(URL)
    json_req, raw_req, plain_req = recorder.requests
    for req in recorder.requests:
        assert req.get_header("User-agent") == "profilegen"
    assert json_req.get_header("Accept") == "application/vnd.github+json"
    assert raw_req.get_header("Accept") == "application/vnd.github.raw"
    assert plain_req.get_header("Accept") is None


def test_get_text_decodes_utf8(stub):
    stub({URL: FakeResponse("Roland Huß".encode("utf-8"))})
    assert http.get_text(URL) == "Roland Huß"


# --- pagination -------------------------------------------------------------


def test_get_json_list_follows_link_header(stub):
    page1_url = "https://api.github.com/users/rhuss/repos?type=owner&per_page=100"
    page2_url = "https://api.github.com/users/rhuss/repos?type=owner&per_page=100&page=2"
    last = "https://api.github.com/users/rhuss/repos?type=owner&per_page=100&page=2"
    page1 = (FIXTURES / "users-rhuss-repos-page1.json").read_bytes()
    page2 = (FIXTURES / "users-rhuss-repos-page2.json").read_bytes()
    recorder = stub(
        {
            page1_url: FakeResponse(
                page1, {"Link": f'<{page2_url}>; rel="next", <{last}>; rel="last"'}
            ),
            page2_url: FakeResponse(
                page2, {"Link": f'<{page1_url}&page=1>; rel="prev", <{page1_url}&page=1>; rel="first"'}
            ),
        }
    )
    repos = http.get_json_list(page1_url, token="abc")
    expected = json.loads(page1) + json.loads(page2)
    assert repos == expected
    assert [r.full_url for r in recorder.requests] == [page1_url, page2_url]
    assert all(r.get_header("Authorization") == "Bearer abc" for r in recorder.requests)


def test_get_json_list_single_page_without_link(stub):
    url = "https://api.github.com/orgs/k8spatterns/repos?type=public&per_page=100"
    body = (FIXTURES / "orgs-k8spatterns-repos.json").read_bytes()
    stub({url: FakeResponse(body)})
    assert [r["full_name"] for r in http.get_json_list(url)][0] == "k8spatterns/examples"


def test_get_json_list_error_on_later_page_fails_whole_call(stub):
    page1_url = "https://api.github.com/users/rhuss/repos?page=1"
    page2_url = "https://api.github.com/users/rhuss/repos?page=2"
    stub(
        {
            page1_url: FakeResponse(b"[]", {"Link": f'<{page2_url}>; rel="next"'}),
            page2_url: _http_error(page2_url, 403, {"X-RateLimit-Remaining": "0"}),
        }
    )
    with pytest.raises(http.SourceError):
        http.get_json_list(page1_url)


def test_get_json_list_rejects_non_array(stub):
    stub({URL: FakeResponse(b'{"message": "Bad credentials"}')})
    with pytest.raises(http.SourceError, match="array"):
        http.get_json_list(URL)


def test_get_json_list_stops_on_link_loop(stub):
    stub({URL: FakeResponse(b"[]", {"Link": f'<{URL}>; rel="next"'})})
    with pytest.raises(http.SourceError):
        http.get_json_list(URL)


# --- token resolution -------------------------------------------------------


def _fake_gh(monkeypatch, *, which="/usr/bin/gh", stdout="gh-token\n", returncode=0, exc=None):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if exc is not None:
            raise exc
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(http.shutil, "which", lambda name: which if name == "gh" else None)
    monkeypatch.setattr(http.subprocess, "run", fake_run)
    return calls


def test_token_prefers_github_token_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    calls = _fake_gh(monkeypatch)
    assert http.resolve_token() == "env-token"
    assert calls == []


def test_token_falls_back_to_gh_auth_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    calls = _fake_gh(monkeypatch)
    assert http.resolve_token() == "gh-token"
    assert calls == [["gh", "auth", "token"]]


def test_empty_github_token_env_falls_back_to_gh(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "")
    _fake_gh(monkeypatch)
    assert http.resolve_token() == "gh-token"


def test_token_none_without_gh(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    calls = _fake_gh(monkeypatch, which=None)
    assert http.resolve_token() is None
    assert calls == []


def test_token_none_when_gh_fails(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _fake_gh(monkeypatch, stdout="", returncode=1)
    assert http.resolve_token() is None


def test_token_none_when_gh_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _fake_gh(monkeypatch, exc=subprocess.TimeoutExpired(["gh"], 10))
    assert http.resolve_token() is None


# --- endpoint overrides -----------------------------------------------------


def test_api_url_default_and_override(monkeypatch):
    monkeypatch.delenv("PROFILEGEN_API_URL", raising=False)
    assert http.api_url() == "https://api.github.com"
    monkeypatch.setenv("PROFILEGEN_API_URL", "http://127.0.0.1:9/")
    assert http.api_url() == "http://127.0.0.1:9"


def test_feed_url_default_and_override(monkeypatch):
    monkeypatch.delenv("PROFILEGEN_FEED_URL", raising=False)
    assert http.feed_url("https://ro14nd.de/index.xml") == "https://ro14nd.de/index.xml"
    monkeypatch.setenv("PROFILEGEN_FEED_URL", "http://127.0.0.1:9/feed.xml")
    assert http.feed_url("https://ro14nd.de/index.xml") == "http://127.0.0.1:9/feed.xml"


# --- token never leaves the API host (review fixes) ----------------------------


def test_pagination_link_to_another_host_is_refused(stub):
    page1_url = "https://api.github.com/users/rhuss/repos?type=owner&per_page=100"
    evil = "https://evil.example/collect?page=2"
    recorder = stub({page1_url: FakeResponse(b"[]", {"Link": f'<{evil}>; rel="next"'})})
    with pytest.raises(http.SourceError) as exc:
        http.get_json_list(page1_url, token="abc")
    assert "leaves the API host" in str(exc.value)
    assert [r.full_url for r in recorder.requests] == [page1_url]


def test_pagination_bounded_by_max_pages(stub, monkeypatch):
    monkeypatch.setattr(http, "MAX_PAGES", 3)
    base = "https://api.github.com/users/rhuss/repos?page="
    stub({f"{base}{i}": FakeResponse(b"[]", {"Link": f'<{base}{i + 1}>; rel="next"'}) for i in range(1, 10)})
    with pytest.raises(http.SourceError) as exc:
        http.get_json_list(f"{base}1")
    assert "does not terminate" in str(exc.value)


def _redirected(old_url: str, new_url: str):
    handler = http._TokenSafeRedirectHandler()
    req = http.Request(old_url, headers={"Authorization": "Bearer abc", "User-Agent": "profilegen"})
    return handler.redirect_request(req, io.BytesIO(b""), 301, "Moved", _headers({"Location": new_url}), new_url)


def test_redirect_on_same_host_keeps_token():
    new = _redirected("https://api.github.com/repos/rhuss/old", "https://api.github.com/repositories/1")
    assert new.get_header("Authorization") == "Bearer abc"


@pytest.mark.parametrize("target", ["https://other.example/x", "http://api.github.com/repositories/1"])
def test_redirect_to_other_host_or_http_drops_token(target):
    new = _redirected("https://api.github.com/repos/rhuss/old", target)
    assert new.get_header("Authorization") is None
    assert new.get_header("User-agent") == "profilegen"


def test_connection_reset_raises_source_error(stub):
    from http.client import RemoteDisconnected

    stub({URL: RemoteDisconnected("closed")})
    with pytest.raises(http.SourceError):
        http.get_json(URL)
