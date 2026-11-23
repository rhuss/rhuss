"""Tests for profilegen.sources.github.

The HTTP layer is stubbed at ``profilegen.sources.http.urlopen`` so the real
``get_json``/``get_json_list`` code (including Link pagination and error
classification) runs against fixture files. No test touches the network.
"""

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
import yaml

from profilegen.model import RepoInfo, profile_from_dict
from profilegen.sources import github, http
from profilegen.sources.http import SourceError

FIXTURES = Path(__file__).parent / "fixtures"
GH = FIXTURES / "github"
API = "https://api.example.test"

OWNERS = ["rhuss", "AgentTacho", "k8spatterns"]
EXTRAS = ["jolokia/jolokia", "fabric8io/docker-maven-plugin"]

# Expected owned total from the fixtures:
#   rhuss:        214 + 37 + 12 + 21 + 9 + 15 + 18 + 26 + 58 (archived jmx4perl) = 410   (fork kubernetes 3 excluded)
#   AgentTacho:   142 + 2 = 144
#   k8spatterns:  1234 + 6 = 1240                                                         (fork kubernetes 4 excluded)
#   extras:       834 (jolokia) + 1882 (docker-maven-plugin) = 2716
EXPECTED_TOTAL = 410 + 144 + 1240 + 2716


def _listing(owner: str) -> str:
    return f"{API}/users/{owner}/repos?type=owner&per_page=100"


def _repo(full_name: str) -> str:
    return f"{API}/repos/{full_name}"


def _load(name: str):
    return json.loads((GH / name).read_text(encoding="utf-8"))


def _headers(values: dict | None = None) -> Message:
    msg = Message()
    for key, value in (values or {}).items():
        msg[key] = value
    return msg


class FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = _headers({"Content-Type": "application/json; charset=utf-8", **(headers or {})})

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(url: str, status: int, headers: dict | None = None, body: bytes = b"{}") -> HTTPError:
    import io

    return HTTPError(url, status, "error", _headers(headers), io.BytesIO(body))


def rate_limited(url: str) -> HTTPError:
    return _http_error(url, 403, {"X-RateLimit-Remaining": "0"}, b'{"message": "API rate limit exceeded"}')


def network_down(url: str) -> URLError:
    return URLError(ConnectionRefusedError("connection refused"))


class FakeGitHub:
    """Maps request URLs to fixture data; unknown URLs answer with HTTP 404."""

    def __init__(self):
        page2 = f"{_listing('rhuss')}&page=2"
        self.routes: dict[str, object] = {
            _listing("rhuss"): ("users-rhuss-repos-page1.json", {"Link": f'<{page2}>; rel="next"'}),
            page2: ("users-rhuss-repos-page2.json", {}),
            _listing("AgentTacho"): ("orgs-AgentTacho-repos.json", {}),
            _listing("k8spatterns"): ("orgs-k8spatterns-repos.json", {}),
            _repo("jolokia/jolokia"): ("repos-jolokia-jolokia.json", {}),
            _repo("fabric8io/docker-maven-plugin"): ("repos-fabric8io-docker-maven-plugin.json", {}),
            _repo("knative/serving"): ("repos-knative-serving.json", {}),
            _repo("eclipse-jkube/jkube"): ("repos-eclipse-jkube-jkube.json", {}),
            _repo("NVIDIA/OpenShell"): ("repos-NVIDIA-OpenShell.json", {}),
            _repo("rhuss/agentmeter"): ("repos-rhuss-agentmeter.json", {}),
            _repo("rhuss/secret-thing"): ("repos-rhuss-secret-thing.json", {}),
        }
        self.calls: list[str] = []

    def fail(self, url: str, error_factory) -> None:
        self.routes[url] = error_factory

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.calls.append(url)
        route = self.routes.get(url)
        if route is None:
            raise _http_error(url, 404, body=(GH / "not-found.json").read_bytes())
        if callable(route):
            raise route(url)
        data, headers = route
        body = (GH / data).read_bytes() if isinstance(data, str) else json.dumps(data).encode("utf-8")
        return FakeResponse(body, headers)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("PROFILEGEN_API_URL", API)
    stub = FakeGitHub()
    monkeypatch.setattr(http, "urlopen", stub)
    return stub


def _profile_dict() -> dict:
    return yaml.safe_load((FIXTURES / "profile.yaml").read_text(encoding="utf-8"))


def _profile(extra_main=(), extra_community=(), extra_tools=()):
    d = _profile_dict()
    d["main_projects"] += [{"repo": r, "description": "Something useful."} for r in extra_main]
    d["community"] += [{"repo": r, "tagline": "Something useful", "role": "contributor"} for r in extra_community]
    d["more_tools"] += [{"repo": r, "tagline": "Something useful"} for r in extra_tools]
    return profile_from_dict(d)


def _info(full_name, stars, private=False, fork=False, archived=False):
    return RepoInfo(
        full_name=full_name,
        html_url=f"https://github.com/{full_name}",
        stars=stars,
        private=private,
        fork=fork,
        archived=archived,
    )


# --- list_owned / total_stars --------------------------------------------------------------------


def test_list_owned_follows_pagination_and_includes_extras(fake):
    repos = github.list_owned(OWNERS, EXTRAS)
    names = {r.full_name for r in repos}
    # page 2 of the rhuss listing is only reachable through the Link header
    assert "rhuss/cc-guide" in names and "rhuss/cc-prose" in names
    assert f"{_listing('rhuss')}&page=2" in fake.calls
    assert {"AgentTacho/agenttacho", "k8spatterns/examples", "jolokia/jolokia", "fabric8io/docker-maven-plugin"} <= names
    assert all(isinstance(r, RepoInfo) for r in repos)
    jmx = next(r for r in repos if r.full_name == "rhuss/jmx4perl")
    assert jmx.archived and jmx.stars == 58 and jmx.html_url.startswith("https://github.com/")


def test_total_over_owned_accounts_and_extras(fake):
    assert github.total_stars(github.list_owned(OWNERS, EXTRAS)) == EXPECTED_TOTAL


def test_total_excludes_community_repos_not_owned(fake):
    repos = github.list_owned(OWNERS, EXTRAS)
    names = {r.full_name for r in repos}
    assert not names & {"knative/serving", "eclipse-jkube/jkube", "NVIDIA/OpenShell"}
    assert all(not c.startswith(_repo("knative")) for c in fake.calls)


def test_total_includes_archived_excludes_forks_and_private():
    repos = [
        _info("rhuss/a", 10),
        _info("rhuss/archived", 5, archived=True),
        _info("rhuss/fork", 100, fork=True),
        _info("rhuss/private", 1000, private=True),
    ]
    assert github.total_stars(repos) == 15


def test_total_excludes_private_repo_in_listing(fake):
    page2 = _load("users-rhuss-repos-page2.json")
    secret = dict(page2[0], full_name="rhuss/secret-thing", name="secret-thing", private=True, stargazers_count=999)
    key = f"{_listing('rhuss')}&page=2"
    fake.routes[key] = (page2 + [secret], {})
    assert github.total_stars(github.list_owned(OWNERS, EXTRAS)) == EXPECTED_TOTAL


def test_total_dedupes_repo_in_listing_and_extras(fake):
    cc_spex = _load("users-rhuss-repos-page1.json")[0]
    assert cc_spex["full_name"] == "rhuss/cc-spex"
    fake.routes[_repo("rhuss/cc-spex")] = (cc_spex, {})
    repos = github.list_owned(OWNERS, EXTRAS + ["rhuss/cc-spex"])
    assert sum(1 for r in repos if r.full_name == "rhuss/cc-spex") == 2
    assert github.total_stars(repos) == EXPECTED_TOTAL


def test_list_owned_skips_deleted_extra_repo(fake):
    repos = github.list_owned(OWNERS, EXTRAS + ["rhuss/vanished-repo"])
    assert github.total_stars(repos) == EXPECTED_TOTAL


def test_total_dedupe_is_case_insensitive():
    repos = [_info("rhuss/cc-spex", 214), _info("RHUSS/CC-Spex", 214), _info("jolokia/jolokia", 834)]
    assert github.total_stars(repos) == 214 + 834


# --- resolve -------------------------------------------------------------------------------------


def test_resolve_uses_known_listing_case_insensitively(fake):
    known = {r.full_name.lower(): r for r in github.list_owned(OWNERS, EXTRAS)}
    fake.calls.clear()
    info = github.resolve("RHUSS/CC-Spex", "main_projects[0]", known=known)
    assert isinstance(info, RepoInfo)
    assert info.full_name == "rhuss/cc-spex" and info.stars == 214
    assert fake.calls == []


def test_resolve_fetches_unknown_repo(fake):
    info = github.resolve("knative/serving", "community[1]")
    assert isinstance(info, RepoInfo)
    assert info.full_name == "knative/serving" and info.stars == 5712
    assert fake.calls == [_repo("knative/serving")]


def test_resolve_not_found(fake):
    assert github.resolve("rhuss/vanished-repo", "more_tools[2]") == github.Missing("more_tools[2]")


def test_resolve_private(fake):
    assert github.resolve("rhuss/secret-thing", "more_tools[2]") == github.Missing("more_tools[2]")


def test_resolve_renamed_returns_new_full_name(fake):
    info = github.resolve("rhuss/agentmeter", "main_projects[3]")
    assert isinstance(info, RepoInfo)
    assert info.full_name == "AgentTacho/agenttacho"
    assert info.html_url == "https://github.com/AgentTacho/agenttacho"


def test_resolve_propagates_source_error(fake):
    fake.fail(_repo("knative/serving"), rate_limited)
    with pytest.raises(SourceError):
        github.resolve("knative/serving", "community[1]")


# --- fetch_repos ---------------------------------------------------------------------------------


def test_fetch_repos_snapshot_and_total(fake):
    profile = _profile(extra_community=["eclipse-jkube/jkube", "NVIDIA/OpenShell", "fabric8io/docker-maven-plugin"])
    repos, total, warnings = github.fetch_repos(profile)

    assert total == EXPECTED_TOTAL
    assert warnings == []
    assert isinstance(repos, dict)
    assert list(repos) == [
        "rhuss/cc-spex",
        "AgentTacho/agenttacho",
        "rhuss/corgi",
        "jolokia/jolokia",
        "knative/serving",
        "eclipse-jkube/jkube",
        "NVIDIA/OpenShell",
        "fabric8io/docker-maven-plugin",
        "rhuss/cc-cfp",
        "rhuss/cc-guide",
    ]
    assert repos["rhuss/cc-spex"] == {"full_name": "rhuss/cc-spex", "stars": 214, "url": "https://github.com/rhuss/cc-spex"}
    # community repos outside the owned set carry their own stars but do not count toward the total
    assert repos["knative/serving"]["stars"] == 5712
    assert repos["eclipse-jkube/jkube"]["stars"] == 812
    assert repos["NVIDIA/OpenShell"] == {
        "full_name": "NVIDIA/OpenShell",
        "stars": 2450,
        "url": "https://github.com/NVIDIA/OpenShell",
    }
    assert repos["jolokia/jolokia"]["stars"] == 834


def test_fetch_repos_no_extra_call_for_repos_in_listing(fake):
    github.fetch_repos(_profile())
    per_repo = [c for c in fake.calls if c.startswith(f"{API}/repos/")]
    # only the owned extras and the non-owned community repo need /repos/ calls
    assert sorted(per_repo) == sorted([_repo(r) for r in EXTRAS] + [_repo("knative/serving")])


def test_fetch_repos_case_insensitive_listing_lookup(fake):
    d = _profile_dict()
    d["main_projects"][0]["repo"] = "rhuss/CC-Spex"
    repos, _, warnings = github.fetch_repos(profile_from_dict(d))
    assert repos["rhuss/CC-Spex"]["full_name"] == "rhuss/cc-spex"
    assert repos["rhuss/CC-Spex"]["stars"] == 214
    assert _repo("rhuss/CC-Spex") not in fake.calls
    assert warnings == []


def test_fetch_repos_omits_missing_and_private_with_entry_only_warning(fake):
    profile = _profile(extra_tools=["rhuss/secret-thing", "rhuss/vanished-repo"])
    repos, total, warnings = github.fetch_repos(profile)

    assert "rhuss/secret-thing" not in repos
    assert "rhuss/vanished-repo" not in repos
    assert warnings == [
        "more_tools[2]: repository not found or not public, omitted",
        "more_tools[3]: repository not found or not public, omitted",
    ]
    for w in warnings:
        assert "secret-thing" not in w
        assert "vanished-repo" not in w
        assert "rhuss/" not in w
    assert total == EXPECTED_TOTAL


def test_fetch_repos_renamed_repo(fake):
    d = _profile_dict()
    # replace the AgentTacho entry by its old name
    d["main_projects"][1]["repo"] = "rhuss/agentmeter"
    repos, _, warnings = github.fetch_repos(profile_from_dict(d))

    assert "AgentTacho/agenttacho" not in repos
    assert repos["rhuss/agentmeter"] == {
        "full_name": "AgentTacho/agenttacho",
        "stars": 142,
        "url": "https://github.com/AgentTacho/agenttacho",
    }
    assert warnings == ["main_projects[1]: repository was renamed, update profile.yaml"]
    # FR-019a: neither the old nor the new repository name appears in the warning.
    assert "agentmeter" not in warnings[0].lower()
    assert "agenttacho" not in warnings[0].lower()


@pytest.mark.parametrize("failure", [rate_limited, network_down], ids=["rate-limit", "network"])
@pytest.mark.parametrize(
    "url",
    [
        _listing("rhuss"),
        f"{_listing('rhuss')}&page=2",
        _listing("k8spatterns"),
        _repo("fabric8io/docker-maven-plugin"),
        _repo("knative/serving"),
    ],
    ids=["listing-page1", "listing-page2", "org-listing", "extra-repo", "resolve-entry"],
)
def test_fetch_repos_any_failed_call_raises(fake, url, failure):
    fake.fail(url, failure)
    with pytest.raises(SourceError):
        github.fetch_repos(_profile())


def test_fetch_repos_passes_token(fake, monkeypatch):
    seen = []
    original = fake.__call__

    def recording(request, timeout=None):
        seen.append(request.get_header("Authorization"))
        return original(request, timeout)

    monkeypatch.setattr(http, "urlopen", recording)
    github.fetch_repos(_profile(), token="t0k")
    assert seen and all(h == "Bearer t0k" for h in seen)


# --- malformed data and owner 404 (review fixes) -----------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        {"full_name": "rhuss/x", "html_url": "https://github.com/rhuss/x", "fork": False},  # no stars, no private
        {"full_name": "rhuss/x", "stargazers_count": 1, "fork": False},  # visibility not stated
        {"full_name": "rhuss/x", "stargazers_count": 1, "private": "no"},  # visibility not a bool
        {"full_name": "x", "stargazers_count": 1, "private": False},  # not owner/name
        ["not", "an", "object"],
    ],
)
def test_malformed_repository_data_is_a_source_error(fake, data):
    fake.routes[_repo("knative/serving")] = (data, {})
    with pytest.raises(SourceError):
        github.resolve("knative/serving", "community[1]")


def test_missing_html_url_falls_back_to_github_url(fake):
    fake.routes[_repo("knative/serving")] = ({"full_name": "knative/serving", "stargazers_count": 3, "private": False}, {})
    info = github.resolve("knative/serving", "community[1]")
    assert info.html_url == "https://github.com/knative/serving"


def test_owner_listing_not_found_is_a_source_error(fake):
    del fake.routes[_listing("k8spatterns")]  # unknown URLs answer 404
    with pytest.raises(SourceError) as exc:
        github.list_owned(OWNERS, EXTRAS)
    assert exc.value.status == 404


def test_fetch_repos_reports_confirmed_missing_before_a_failure(fake):
    profile = _profile(extra_tools=["rhuss/vanished-repo", "otherorg/late-repo"])
    fake.fail(_repo("otherorg/late-repo"), rate_limited)
    missing: set[str] = set()
    with pytest.raises(SourceError):
        github.fetch_repos(profile, missing=missing)
    assert "rhuss/vanished-repo" in missing


def test_main_project_outside_owned_accounts_does_not_count_toward_total(fake):
    # FR-012: a main project hosted upstream (for example tals/corgi) shows its
    # own stars, but only owned repositories count toward the total.
    fake.routes[_repo("tals/corgi")] = (
        {"full_name": "tals/corgi", "html_url": "https://github.com/tals/corgi", "stargazers_count": 212,
         "private": False, "fork": False, "archived": False},
        {},
    )
    repos, total, warnings = github.fetch_repos(_profile(extra_main=["tals/corgi"]))
    assert total == EXPECTED_TOTAL
    assert repos["tals/corgi"] == {"full_name": "tals/corgi", "stars": 212, "url": "https://github.com/tals/corgi"}
    assert warnings == []
