"""Tests for ``profilegen scan`` (T024, FR-020 to FR-023a, R8).

Git runs for real against throwaway repositories built under a temporary
directory (with controlled commit dates and author emails, and with global and
system git configuration disabled). GitHub is stubbed at the JSON level: the
fake replaces ``get_json``/``get_json_list`` and fails the test on any URL it
does not know, so no test touches the network or the real ``~/Development``.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from profilegen import cli
from profilegen import scan as scan_mod
from profilegen.model import load_profile
from profilegen.sources import github, http
from profilegen.sources.http import NotFound, SourceError

FIXTURES = Path(__file__).parent / "fixtures" / "scan"
API = "https://api.example.test"
NOW = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
SINCE = "2025-11-23T12:00:00Z"  # NOW minus 365 days
ME = "roland@example.com"
OTHER = "other@example.com"

# Names that must never show up in any output (FR-023, SC-003).
PRIVATE_NAMES = ["secret-sauce", "local-only", "forked", "hidden-tool", "gone-tool", "too-deep"]


# --- git world ------------------------------------------------------------------------


def _git_env(home: Path, empty_config: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=str(empty_config), GIT_CONFIG_NOSYSTEM="1", HOME=str(home))
    return env


def _git(path: Path, env: dict, *args: str) -> None:
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env=env)


def make_repo(
    path: Path,
    env: dict,
    remotes: dict[str, str] | None = None,
    commits: list[tuple[int, str]] = (),
    user_email: str | None = ME,
) -> Path:
    """Create a git repository with the given remotes and (days_ago, author_email) commits."""
    path.mkdir(parents=True)
    _git(path, env, "init", "-q", "-b", "main")
    if user_email:
        _git(path, env, "config", "user.email", user_email)
    for name, url in (remotes or {}).items():
        _git(path, env, "remote", "add", name, url)
    if commits:
        # One fast-import stream instead of one `git commit` per commit (same
        # result: author and committer email and date are set per commit).
        stream = []
        for i, (days_ago, email) in enumerate(commits):
            ts = int((NOW - timedelta(days=days_ago)).timestamp())
            msg = f"commit {i}\n"
            stream.append(
                f"commit refs/heads/main\n"
                f"author Someone <{email}> {ts} +0000\n"
                f"committer Someone <{email}> {ts} +0000\n"
                f"data {len(msg)}\n{msg}\n"
            )
        subprocess.run(
            ["git", "-C", str(path), "fast-import", "--quiet"],
            input="".join(stream).encode(),
            check=True,
            capture_output=True,
            env=env,
        )
    return path


def mine(*days: int) -> list[tuple[int, str]]:
    return [(d, ME) for d in days]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    base = tmp_path_factory.mktemp("world")
    home = base / "home"
    work = base / "work"
    dev = home / "Development"
    empty_config = base / "empty-gitconfig"
    empty_config.write_text("", encoding="utf-8")
    env = _git_env(home, empty_config)

    make_repo(
        dev / "context-engineering" / "corgi",
        env,
        {"origin": "git@github.com:rhuss/corgi.git"},
        mine(2, 3, 4) + [(1, OTHER)] * 20,
    )
    make_repo(dev / "cc-blog", env, {"origin": "https://github.com/rhuss/cc-blog"}, mine(*range(1, 13)))
    make_repo(dev / "a" / "b" / "deep-ok", env, {"origin": "ssh://git@github.com/otherorg/deep-ok.git"}, mine(5))
    make_repo(dev / "a" / "b" / "c" / "too-deep", env, {"origin": "git@github.com:rhuss/too-deep.git"}, mine(1))
    # No user.email in this checkout: counts come from the GitHub API instead.
    make_repo(dev / "cc-cfp", env, {"origin": "https://github.com/rhuss/cc-cfp.git"}, mine(1, 2, 3), user_email=None)

    make_repo(
        work / "debaser",
        env,
        {"origin": "git@github.com:rhuss/debaser.git", "upstream": "https://github.com/rhuss/debaser.git"},
        mine(74, 100) + [(1, OTHER)],
    )
    make_repo(work / "secret-sauce", env, {"origin": "git@github.com:rhuss/secret-sauce.git"}, mine(*range(1, 16)))
    make_repo(work / "local-only", env, {"origin": "https://github.com/rhuss/local-only.git"}, mine(*range(1, 13)))
    make_repo(work / "forked", env, {"origin": "git@github.com:rhuss/forked.git"}, mine(*range(1, 13)))
    make_repo(work / "old-tool", env, {"origin": "git@github.com:rhuss/old-tool.git"}, mine(400))
    make_repo(work / "archived-thing", env, {"origin": "git@github.com:rhuss/archived-thing.git"}, mine(*range(1, 12)))
    make_repo(work / "no-remote", env, None, mine(1))
    make_repo(work / "gitlab-thing", env, {"origin": "git@gitlab.com:rhuss/gitlab-thing.git"}, mine(1))

    return {"base": base, "home": home, "work": work, "empty_config": empty_config}


@pytest.fixture
def env(world, monkeypatch):
    """Point HOME at the fake home and keep the user's git configuration out."""
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("HOME", str(world["home"]))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(world["empty_config"]))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return world


# --- GitHub fake ----------------------------------------------------------------------


def repo_json(full_name: str, private=False, fork=False, archived=False) -> dict:
    return {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "stargazers_count": 1,
        "private": private,
        "fork": fork,
        "archived": archived,
    }


def commits_json(*days: int) -> list:
    out = []
    for i, d in enumerate(days):
        stamp = (NOW - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"sha": f"{i:040x}", "commit": {"author": {"date": stamp}, "committer": {"date": stamp}}})
    return out


def listing_url(owner: str) -> str:
    return f"{API}/users/{owner}/repos?type=owner&per_page=100"


def commits_url(full_name: str, login: str = "rhuss") -> str:
    return f"{API}/repos/{full_name}/commits?since={SINCE}&author={login}&per_page=100"


def base_routes() -> dict:
    return {
        listing_url("rhuss"): [
            repo_json("rhuss/cc-spex"),
            repo_json("rhuss/corgi"),
            repo_json("rhuss/debaser"),
            repo_json("rhuss/cc-blog"),
            repo_json("rhuss/cc-cfp"),
            repo_json("rhuss/forked", fork=True),
            repo_json("rhuss/secret-sauce", private=True),
            repo_json("rhuss/old-tool"),
            repo_json("rhuss/archived-thing", archived=True),
            repo_json("rhuss/api-tool"),
            repo_json("rhuss/empty-repo"),
        ],
        listing_url("AgentTacho"): [repo_json("AgentTacho/agenttacho")],
        f"{API}/repos/rhuss/agentmeter": repo_json("AgentTacho/agenttacho"),
        f"{API}/repos/knative/serving": repo_json("knative/serving"),
        f"{API}/repos/rhuss/gone-tool": NotFound("api.example.test: HTTP 404 Not Found"),
        f"{API}/repos/rhuss/hidden-tool": repo_json("rhuss/hidden-tool", private=True),
        f"{API}/repos/otherorg/deep-ok": repo_json("otherorg/deep-ok"),
        f"{API}/repos/rhuss/local-only": NotFound("api.example.test: HTTP 404 Not Found"),
        commits_url("rhuss/cc-spex"): commits_json(3, 10),
        commits_url("AgentTacho/agenttacho"): commits_json(1),
        commits_url("knative/serving"): [],
        commits_url("rhuss/cc-cfp"): [],
        commits_url("rhuss/api-tool"): commits_json(20, 50, 100),
        commits_url("rhuss/empty-repo"): SourceError("api.example.test: HTTP 409", status=409),
        # Only used when the work root is not scanned:
        commits_url("rhuss/debaser"): [],
        commits_url("rhuss/old-tool"): [],
        commits_url("rhuss/archived-thing"): [],
    }


class FakeGitHub:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url, token=None, accept=None):
        self.calls.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected GitHub request: {url}")
        result = self.routes[url]
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)


@pytest.fixture
def fake(monkeypatch):
    gh = FakeGitHub(base_routes())
    monkeypatch.setenv("PROFILEGEN_API_URL", API)
    monkeypatch.setattr(github, "get_json", gh)
    monkeypatch.setattr(github, "get_json_list", gh)
    monkeypatch.setattr(http, "get_json_list", gh)
    monkeypatch.setattr(http, "get_json", gh)
    monkeypatch.setattr(http, "resolve_token", lambda: None)
    monkeypatch.setattr(scan_mod.clock, "now", lambda: NOW)
    return gh


@pytest.fixture
def profile():
    return load_profile(FIXTURES / "profile.yaml")


def roots(world) -> list[str]:
    return ["~/Development", str(world["work"])]


def report_for(profile, world, gh=None) -> dict:
    return scan_mod.build_report(profile, roots(world), now=NOW, gh=gh or scan_mod.GitHubAccess(token=None))


def expected_repos(world) -> list[dict]:
    work = world["work"]

    def r(repo, local_path, commits, days, listed):
        return {
            "repo": repo,
            "local_path": local_path,
            "public": True,
            "commits_window": commits,
            "days_since_last_commit": days,
            "listed_in": listed,
        }

    return [
        r("AgentTacho/agenttacho", None, 1, 1, "main_projects"),
        r("knative/serving", None, 0, None, "community"),
        r("otherorg/deep-ok", "~/Development/a/b/deep-ok", 1, 5, None),
        r("rhuss/api-tool", None, 1, 20, None),
        r("rhuss/archived-thing", str(work / "archived-thing"), 11, 1, None),
        r("rhuss/cc-blog", "~/Development/cc-blog", 12, 1, None),
        r("rhuss/cc-cfp", "~/Development/cc-cfp", 0, None, "more_tools"),
        r("rhuss/cc-spex", None, 2, 3, "main_projects"),
        r("rhuss/corgi", "~/Development/context-engineering/corgi", 3, 2, "main_projects"),
        r("rhuss/debaser", str(work / "debaser"), 0, 74, "main_projects"),
        r("rhuss/empty-repo", None, 0, None, None),
        r("rhuss/old-tool", str(work / "old-tool"), 0, 400, None),
    ]


EXPECTED_PROPOSALS = [
    {"kind": "demote", "repo": "rhuss/debaser", "reason": "no commits in 74 days"},
    {"kind": "promote", "repo": "rhuss/cc-blog", "reason": "12 commits in last 30 days"},
    {"kind": "remove", "entry": "more_tools[1]", "reason": "repository not public or missing"},
    {"kind": "remove", "entry": "more_tools[2]", "reason": "repository not public or missing"},
    {"kind": "rename", "repo": "rhuss/agentmeter", "new_repo": "AgentTacho/agenttacho"},
    {"kind": "new_tool", "repo": "rhuss/api-tool", "reason": "public, active in last 12 months, not listed"},
    # rhuss/cc-blog is not also a new_tool: one proposal per repository, promote wins.
]


# --- remote mapping -------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:rhuss/foo.git", "rhuss/foo"),
        ("git@github.com:rhuss/foo", "rhuss/foo"),
        ("https://github.com/rhuss/bar", "rhuss/bar"),
        ("https://github.com/rhuss/bar.git", "rhuss/bar"),
        ("https://github.com/rhuss/bar/", "rhuss/bar"),
        ("https://token@github.com/AgentTacho/agenttacho.git", "AgentTacho/agenttacho"),
        ("ssh://git@github.com/rhuss/baz.git", "rhuss/baz"),
        ("ssh://git@github.com:22/rhuss/baz", "rhuss/baz"),
        ("git://github.com/rhuss/qux.git", "rhuss/qux"),
        ("https://GitHub.com/rhuss/my.repo.git", "rhuss/my.repo"),
        ("git@gitlab.com:rhuss/foo.git", None),
        ("https://github.com/rhuss", None),
        ("https://github.com/rhuss/foo/tree/main", None),
        ("/some/local/path", None),
        ("", None),
    ],
)
def test_parse_remote(url, expected):
    assert scan_mod.parse_remote(url) == expected


# --- discovery ------------------------------------------------------------------------


def test_find_checkouts_depth_limit_and_tilde(env):
    found = scan_mod.find_checkouts(roots(env))
    home = env["home"]
    rel = sorted(str(p.relative_to(home)) if p.is_relative_to(home) else p.name for p in found)
    assert "Development/a/b/deep-ok" in rel
    assert "Development/context-engineering/corgi" in rel
    assert not any("too-deep" in p for p in rel)
    assert "no-remote" in rel  # still a checkout; it simply has no GitHub remote


def test_find_checkouts_skips_hidden_directories(env, tmp_path):
    git_env = _git_env(env["home"], env["empty_config"])
    make_repo(tmp_path / "scan" / ".cache" / "hidden-clone", git_env, {"origin": "git@github.com:rhuss/x.git"})
    make_repo(tmp_path / "scan" / "visible", git_env, {"origin": "git@github.com:rhuss/y.git"})
    assert [p.name for p in scan_mod.find_checkouts([str(tmp_path / "scan")])] == ["visible"]


def test_find_checkouts_ignores_missing_roots(env, tmp_path):
    assert scan_mod.find_checkouts([str(tmp_path / "does-not-exist")]) == []


# --- full report ----------------------------------------------------------------------


def test_report_shape_and_content(env, fake, profile):
    report = report_for(profile, env)
    assert list(report) == ["repos", "proposals"]
    assert report["repos"] == expected_repos(env)
    assert report["proposals"] == EXPECTED_PROPOSALS


def test_private_fork_and_missing_names_never_appear(env, fake, profile):
    text = json.dumps(report_for(profile, env))
    for name in PRIVATE_NAMES:
        assert name not in text


def test_deeper_repos_are_not_even_looked_up(env, fake, profile):
    report_for(profile, env)
    assert not any("too-deep" in url for url in fake.calls)


def test_commit_counts_only_include_the_checkout_user(env, fake, profile):
    repos = {r["repo"]: r for r in report_for(profile, env)["repos"]}
    # corgi has 3 commits by Roland and 20 more recent ones by someone else.
    assert repos["rhuss/corgi"]["commits_window"] == 3
    assert repos["rhuss/corgi"]["days_since_last_commit"] == 2
    # debaser's newest commit (1 day ago) is by someone else.
    assert repos["rhuss/debaser"]["days_since_last_commit"] == 74


def test_api_fallback_for_repos_without_local_counts(env, fake, profile):
    report_for(profile, env)
    # No checkout at all, and a checkout without user.email:
    assert commits_url("rhuss/cc-spex") in fake.calls
    assert commits_url("rhuss/cc-cfp") in fake.calls
    # Checkouts with user.email are counted locally:
    for repo in ("rhuss/corgi", "rhuss/debaser", "rhuss/cc-blog", "rhuss/archived-thing"):
        assert commits_url(repo) not in fake.calls
    # Never asked for repos that are dropped:
    for name in PRIVATE_NAMES:
        assert not any(f"/repos/rhuss/{name}/commits" in url for url in fake.calls)


def test_login_is_first_owned_owner(env, fake, profile):
    profile.settings.owned_owners = ["AgentTacho", "rhuss"]
    fake.routes[commits_url("rhuss/cc-spex", login="AgentTacho")] = []
    for key in list(fake.routes):
        if "&author=rhuss&" in key:
            fake.routes[key.replace("&author=rhuss&", "&author=AgentTacho&")] = fake.routes[key]
    report_for(profile, env)
    assert commits_url("rhuss/cc-spex", login="AgentTacho") in fake.calls


def test_listed_fork_main_project_can_still_be_demoted(env, fake, profile):
    # rhuss/corgi in the real profile is a fork; a listed fork must not be dropped
    # from the report, or it could never be proposed for demotion (FR-021).
    listing = fake.routes[listing_url("rhuss")]
    for item in listing:
        if item["full_name"] == "rhuss/debaser":
            item["fork"] = True
    report = report_for(profile, env)
    assert "rhuss/debaser" in {r["repo"] for r in report["repos"]}
    assert {"kind": "demote", "repo": "rhuss/debaser", "reason": "no commits in 74 days"} in report["proposals"]
    # Unlisted forks stay out of the report.
    assert "forked" not in json.dumps(report)


def test_local_commits_count_only_for_the_origin_remote(env, fake, profile, tmp_path):
    # A fork checkout with an upstream remote: fork-only branches must not be
    # credited to the upstream repository (it falls back to the commits API).
    make_repo(
        tmp_path / "extra" / "sdk",
        _git_env(env["home"], env["empty_config"]),
        {"origin": "git@github.com:rhuss/sdk-fork.git", "upstream": "https://github.com/upstreamorg/sdk.git"},
        mine(*range(1, 16)),
    )
    fake.routes[f"{API}/repos/rhuss/sdk-fork"] = repo_json("rhuss/sdk-fork")
    fake.routes[f"{API}/repos/upstreamorg/sdk"] = repo_json("upstreamorg/sdk")
    fake.routes[commits_url("upstreamorg/sdk")] = commits_json(40)
    report = scan_mod.build_report(
        profile, roots(env) + [str(tmp_path / "extra")], now=NOW, gh=scan_mod.GitHubAccess(token=None)
    )
    repos = {r["repo"]: r for r in report["repos"]}
    assert repos["rhuss/sdk-fork"]["commits_window"] == 15
    assert repos["upstreamorg/sdk"]["commits_window"] == 0
    assert commits_url("upstreamorg/sdk") in fake.calls
    promoted = [p["repo"] for p in report["proposals"] if p["kind"] == "promote"]
    assert "rhuss/sdk-fork" in promoted and "upstreamorg/sdk" not in promoted


def test_main_project_matched_through_upstream_remote_of_a_fork_checkout(env, fake, profile, tmp_path):
    # The real profile lists tals/corgi; Roland's checkout has origin rhuss/corgi
    # (his fork) and upstream tals/corgi. The main project's activity comes from
    # that checkout, counting only Roland's own commits.
    profile.main_projects[2].repo = "tals/corgi"
    make_repo(
        tmp_path / "extra" / "corgi-fork",
        _git_env(env["home"], env["empty_config"]),
        {"origin": "git@github.com:rhuss/corgi-fork.git", "upstream": "https://github.com/tals/corgi.git"},
        mine(2, 5) + [(1, OTHER)] * 30,
    )
    fake.routes[f"{API}/repos/tals/corgi"] = repo_json("tals/corgi")
    fake.routes[f"{API}/repos/rhuss/corgi-fork"] = repo_json("rhuss/corgi-fork", fork=True)
    report = scan_mod.build_report(
        profile, roots(env) + [str(tmp_path / "extra")], now=NOW, gh=scan_mod.GitHubAccess(token=None)
    )
    repos = {r["repo"]: r for r in report["repos"]}
    corgi = repos["tals/corgi"]
    assert corgi["listed_in"] == "main_projects"
    assert corgi["local_path"] == str(tmp_path / "extra" / "corgi-fork")
    assert corgi["commits_window"] == 2 and corgi["days_since_last_commit"] == 2
    assert commits_url("tals/corgi") not in fake.calls  # counted locally, not via the API
    assert not any(p.get("repo") == "tals/corgi" for p in report["proposals"])
    assert "rhuss/corgi-fork" not in repos  # an unlisted fork stays out

    # Without recent own commits the upstream-matched main project is proposed for demotion.
    profile.settings.demote_after_days = 1
    report = scan_mod.build_report(
        profile, roots(env) + [str(tmp_path / "extra")], now=NOW, gh=scan_mod.GitHubAccess(token=None)
    )
    assert {"kind": "demote", "repo": "tals/corgi", "reason": "no commits in 2 days"} in report["proposals"]


def test_new_tool_skips_profile_repo_and_organization_repos(env, fake, profile):
    fake.routes[listing_url("rhuss")].append(repo_json("rhuss/rhuss"))
    fake.routes[listing_url("AgentTacho")].append(repo_json("AgentTacho/homebrew-tap"))
    # Enough commits to cross the promote threshold: still never proposed.
    fake.routes[commits_url("rhuss/rhuss")] = commits_json(*range(1, 13))
    fake.routes[commits_url("AgentTacho/homebrew-tap")] = commits_json(3)
    report = report_for(profile, env)
    new_tools = [p["repo"] for p in report["proposals"] if p["kind"] == "new_tool"]
    assert new_tools == ["rhuss/api-tool"]
    assert not any(p.get("repo") == "rhuss/rhuss" for p in report["proposals"])
    # Both are still reported as public repositories.
    assert {"rhuss/rhuss", "AgentTacho/homebrew-tap"} <= {r["repo"] for r in report["repos"]}


def test_settings_drive_thresholds(env, fake, profile):
    s = profile.settings
    s.demote_after_days, s.promote_commits, s.promote_window_days = 2, 3, 5
    report = report_for(profile, env)
    repos = {r["repo"]: r for r in report["repos"]}
    assert repos["rhuss/corgi"]["commits_window"] == 3
    assert repos["rhuss/cc-blog"]["commits_window"] == 5
    kinds = [(p["kind"], p.get("repo")) for p in report["proposals"] if p["kind"] in ("demote", "promote")]
    assert kinds == [
        ("demote", "rhuss/cc-spex"),
        ("demote", "rhuss/debaser"),
        ("promote", "rhuss/cc-blog"),
    ]
    assert report["proposals"][0]["reason"] == "no commits in 3 days"
    assert report["proposals"][2]["reason"] == "5 commits in last 5 days"


def test_demote_reason_without_any_commit(env, fake, profile):
    # cc-spex has no checkout and the commits API knows no commit by the user at all.
    fake.routes[commits_url("rhuss/cc-spex")] = []
    demotes = [p for p in report_for(profile, env)["proposals"] if p["kind"] == "demote"]
    assert {"kind": "demote", "repo": "rhuss/cc-spex", "reason": "no commits in the last 60 days"} in demotes


def test_promote_threshold_is_inclusive(env, fake, profile):
    # cc-blog has exactly 12 own commits in the last 30 days (FR-021: "at least N").
    profile.settings.promote_commits = 12
    kinds = [(p["kind"], p.get("repo")) for p in report_for(profile, env)["proposals"]]
    assert ("promote", "rhuss/cc-blog") in kinds
    profile.settings.promote_commits = 13
    kinds = [(p["kind"], p.get("repo")) for p in report_for(profile, env)["proposals"]]
    assert ("promote", "rhuss/cc-blog") not in kinds


def test_lenient_settings_produce_no_demote_or_promote(env, fake, profile):
    s = profile.settings
    s.demote_after_days, s.promote_commits = 80, 13
    kinds = {p["kind"] for p in report_for(profile, env)["proposals"]}
    assert "demote" not in kinds and "promote" not in kinds


def test_report_is_deterministic(env, fake, profile):
    first = json.dumps(report_for(profile, env))
    second = json.dumps(report_for(profile, env))
    assert first == second


def test_proposal_sort_uses_entry_index_numerically():
    props = [
        {"kind": "new_tool", "repo": "rhuss/b"},
        {"kind": "remove", "entry": "more_tools[10]"},
        {"kind": "remove", "entry": "more_tools[2]"},
        {"kind": "remove", "entry": "community[3]"},
        {"kind": "new_tool", "repo": "rhuss/A"},
        {"kind": "demote", "repo": "rhuss/z"},
    ]
    ordered = [p.get("repo") or p.get("entry") for p in scan_mod.sort_proposals(props)]
    assert ordered == ["rhuss/z", "community[3]", "more_tools[2]", "more_tools[10]", "rhuss/A", "rhuss/b"]


def test_visibility_failure_raises(env, fake, profile):
    fake.routes[listing_url("rhuss")] = SourceError("api.example.test: rate limit exceeded (HTTP 403)")
    with pytest.raises(SourceError):
        report_for(profile, env)


# --- CLI ------------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path):
    shutil.copy(FIXTURES / "profile.yaml", tmp_path / "profile.yaml")
    return tmp_path


def run_cli(root, *args):
    return cli.main(["--root", str(root), "scan", *args])


def test_cli_json(env, fake, root, capsys):
    assert run_cli(root, "--json", "--roots", *roots(env)) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data == {"repos": expected_repos(env), "proposals": EXPECTED_PROPOSALS}
    for name in PRIVATE_NAMES:
        assert name not in out and name not in err


def test_cli_defaults_to_settings_scan_roots(env, fake, root, capsys):
    assert run_cli(root, "--json") == 0
    repos = {r["repo"]: r for r in json.loads(capsys.readouterr().out)["repos"]}
    assert repos["rhuss/corgi"]["local_path"] == "~/Development/context-engineering/corgi"
    assert repos["rhuss/debaser"]["local_path"] is None
    assert commits_url("rhuss/debaser") in fake.calls


def test_cli_human_summary(env, fake, root, capsys):
    assert run_cli(root, "--roots", *roots(env)) == 0
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[0] == "12 public repositories scanned, 6 proposals:"
    assert "  demote    rhuss/debaser: no commits in 74 days" in lines
    assert "  remove    more_tools[1]: repository not public or missing" in lines
    assert "  rename    rhuss/agentmeter -> AgentTacho/agenttacho" in lines
    assert "  new_tool  rhuss/api-tool: public, active in last 12 months, not listed" in lines
    for name in PRIVATE_NAMES:
        assert name not in out and name not in err


@pytest.mark.parametrize(
    "url,error",
    [
        (listing_url("rhuss"), SourceError("api.example.test: HTTP 502")),  # owner listing
        (listing_url("rhuss"), NotFound("api.example.test: HTTP 404 Not Found")),  # owner account gone
        (f"{API}/repos/rhuss/hidden-tool", SourceError("api.example.test: HTTP 502")),  # a listed entry
        (f"{API}/repos/rhuss/local-only", SourceError("api.example.test: HTTP 502")),  # a local repo not listed
        # A visible repo that turns private mid-scan: its commits answer 404.
        (commits_url("rhuss/cc-spex"), NotFound("api.example.test: HTTP 404 Not Found")),
    ],
    ids=["listing-502", "listing-404", "entry-502", "local-502", "commits-404"],
)
def test_cli_refuses_when_visibility_cannot_be_verified(env, fake, root, capsys, url, error):
    fake.routes[url] = error
    assert run_cli(root, "--json", "--roots", *roots(env)) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("ERROR: ")
    assert "no proposals emitted" in err
    for name in PRIVATE_NAMES:
        assert name not in err


def test_cli_invalid_profile(env, fake, tmp_path, capsys):
    (tmp_path / "profile.yaml").write_text("name: x\n", encoding="utf-8")
    assert run_cli(tmp_path, "--json") == 1
    assert capsys.readouterr().out == ""


def test_malformed_commit_data_is_a_source_error(env, fake, profile):
    fake.routes[commits_url("rhuss/cc-spex")] = [{"sha": "0" * 40}]
    with pytest.raises(SourceError):
        report_for(profile, env)
