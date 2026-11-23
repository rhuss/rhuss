"""Tests for the keep-alive check (T022, FR-016a, contracts/cli.md).

Each test builds a real git repository in ``tmp_path`` with commits dated via
``GIT_COMMITTER_DATE``/``GIT_AUTHOR_DATE``. No network access is needed.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from profilegen import cli, keepalive

NOW = datetime(2026, 11, 23, 4, 17, 0, tzinfo=timezone.utc)


@pytest.fixture
def git_env(tmp_path, monkeypatch):
    """Isolate git from the user's configuration and from enclosing repositories."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env={**os.environ, **(env or {})})


def make_repo(path: Path, *commit_times: datetime) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    for when in commit_times:
        stamp = f"@{int(when.timestamp())} +0000"
        env = {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
        }
        _git(path, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "c", env=env)
    return path


@pytest.fixture
def repo_aged(tmp_path, git_env):
    count = 0

    def build(age: timedelta) -> Path:
        nonlocal count
        count += 1
        return make_repo(tmp_path / f"repo{count}", NOW - age)

    return build


# --- keepalive.check -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(days=50), keepalive.NEEDED),
        (timedelta(days=50, seconds=1), keepalive.NEEDED),
        (timedelta(days=120), keepalive.NEEDED),
        (timedelta(days=49, hours=23), keepalive.NOT_NEEDED),
        (timedelta(days=50) - timedelta(seconds=1), keepalive.NOT_NEEDED),
        (timedelta(0), keepalive.NOT_NEEDED),
    ],
    ids=["exactly-50d", "50d-plus-1s", "120d", "49d-23h", "50d-minus-1s", "just-now"],
)
def test_check_threshold(repo_aged, age, expected):
    result = keepalive.check(repo_aged(age), 50, now=NOW)
    assert result.exit_code == expected


def test_check_uses_latest_commit(tmp_path, git_env):
    repo = make_repo(tmp_path / "repo", NOW - timedelta(days=200), NOW - timedelta(days=3))
    assert keepalive.check(repo, 50, now=NOW).exit_code == keepalive.NOT_NEEDED


def test_check_uses_committer_date_not_author_date(tmp_path, git_env):
    repo = make_repo(tmp_path / "repo", NOW - timedelta(days=1))
    old = f"@{int((NOW - timedelta(days=90)).timestamp())} +0000"
    recent = f"@{int((NOW - timedelta(days=60)).timestamp())} +0000"
    _git(
        repo,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "rebased",
        env={
            "GIT_AUTHOR_NAME": "T",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_AUTHOR_DATE": old,
            "GIT_COMMITTER_DATE": recent,
        },
    )
    assert keepalive.check(repo, 70, now=NOW).exit_code == keepalive.NOT_NEEDED
    assert keepalive.check(repo, 60, now=NOW).exit_code == keepalive.NEEDED


def test_check_honours_custom_days(repo_aged):
    repo = repo_aged(timedelta(days=10))
    assert keepalive.check(repo, 10, now=NOW).exit_code == keepalive.NEEDED
    assert keepalive.check(repo, 11, now=NOW).exit_code == keepalive.NOT_NEEDED


def test_check_timezone_offset_of_now_does_not_matter(repo_aged):
    repo = repo_aged(timedelta(days=50))
    cet = NOW.astimezone(timezone(timedelta(hours=1)))
    assert keepalive.check(repo, 50, now=cet).exit_code == keepalive.NEEDED


def test_check_defaults_to_current_time(repo_aged, monkeypatch):
    repo = repo_aged(timedelta(days=50))
    monkeypatch.setattr(keepalive.clock, "now", lambda: NOW)
    assert keepalive.check(repo).exit_code == keepalive.NEEDED
    monkeypatch.setattr(keepalive.clock, "now", lambda: NOW - timedelta(hours=1))
    assert keepalive.check(repo).exit_code == keepalive.NOT_NEEDED


def test_check_not_a_repository(tmp_path, git_env):
    plain = tmp_path / "plain"
    plain.mkdir()
    result = keepalive.check(plain, 50, now=NOW)
    assert result.exit_code == keepalive.ERROR
    assert result.message.startswith("ERROR: keepalive:")


def test_check_repository_without_commits(tmp_path, git_env):
    repo = make_repo(tmp_path / "empty")
    assert keepalive.check(repo, 50, now=NOW).exit_code == keepalive.ERROR


def test_check_missing_directory(tmp_path, git_env):
    assert keepalive.check(tmp_path / "missing", 50, now=NOW).exit_code == keepalive.ERROR


def test_check_git_not_installed(repo_aged, monkeypatch):
    repo = repo_aged(timedelta(days=1))
    monkeypatch.setenv("PATH", "")
    assert keepalive.check(repo, 50, now=NOW).exit_code == keepalive.ERROR


# --- CLI -------------------------------------------------------------------------------


@pytest.fixture
def fixed_now(monkeypatch):
    monkeypatch.setattr(keepalive.clock, "now", lambda: NOW)


def test_cli_needed_exit_0(repo_aged, fixed_now, capsys):
    repo = repo_aged(timedelta(days=50))
    assert cli.main(["--root", str(repo), "keepalive", "--days", "50"]) == 0
    assert "keep-alive commit needed" in capsys.readouterr().out


def test_cli_not_needed_exit_3(repo_aged, fixed_now, capsys):
    repo = repo_aged(timedelta(days=49, hours=23))
    assert cli.main(["--root", str(repo), "keepalive", "--days", "50"]) == 3
    assert "no keep-alive commit needed" in capsys.readouterr().out


def test_cli_default_days_is_50(repo_aged, fixed_now):
    assert cli.main(["--root", str(repo_aged(timedelta(days=50))), "keepalive"]) == 0
    assert cli.main(["--root", str(repo_aged(timedelta(days=49, hours=23))), "keepalive"]) == 3


def test_cli_root_after_subcommand(repo_aged, fixed_now):
    repo = repo_aged(timedelta(days=60))
    assert cli.main(["keepalive", "--root", str(repo), "--days", "50"]) == 0


def test_cli_defaults_to_current_directory(repo_aged, fixed_now, monkeypatch):
    repo = repo_aged(timedelta(days=60))
    monkeypatch.chdir(repo)
    assert cli.main(["keepalive"]) == 0


def test_cli_git_error_exit_1(tmp_path, git_env, fixed_now, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert cli.main(["--root", str(plain), "keepalive"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR: keepalive:")


@pytest.mark.parametrize("days", ["-1", "abc", "1.5"])
def test_cli_invalid_days_exit_2(days, capsys):
    assert cli.main(["keepalive", "--days", days]) == 2
    assert "usage:" in capsys.readouterr().err
