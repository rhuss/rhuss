"""Execute the commit, keep-alive and push steps of refresh.yml (FR-016a, FR-017, SC-006).

The ``run:`` blocks are taken from the workflow file and executed with the
shell GitHub uses (``bash -eo pipefail``) in a clone of a local bare remote.
``uv`` and ``sleep`` are stubbed on PATH: the keep-alive check returns the exit
code from ``KEEPALIVE_RC``, and the retry back-off does not wait.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "refresh.yml"


def _steps() -> dict[str, str]:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["refresh"]["steps"]
    return {s["name"]: s["run"] for s in steps if "run" in s}


STEPS = _steps()
IDENTITY = STEPS["Configure git identity"]
COMMIT = STEPS["Commit README and snapshot if changed"]
KEEPALIVE = STEPS["Keep the schedule alive"]
PUSH = STEPS["Push if ahead"]


@pytest.fixture
def env(tmp_path, monkeypatch) -> dict:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "uv").write_text('#!/bin/sh\nexit "${KEEPALIVE_RC:-3}"\n')
    (stubs / "sleep").write_text("#!/bin/sh\nexit 0\n")
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    e.update(
        PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}",
        GIT_CONFIG_GLOBAL=str(empty),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="Roland",
        GIT_AUTHOR_EMAIL="roland@example.test",
        GIT_COMMITTER_NAME="Roland",
        GIT_COMMITTER_EMAIL="roland@example.test",
    )
    return e


def git(cwd: Path, env: dict, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def run_step(script: str, cwd: Path, env: dict, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=cwd,
        env={**env, **extra},
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path, env) -> dict:
    """A bare remote with one commit (README, snapshot, profile) and a tracking clone."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], env=env, check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(remote), str(seed)], env=env, check=True)
    (seed / "data").mkdir()
    (seed / "README.md").write_text("# Profile\n\nold\n")
    (seed / "data" / "snapshot.json").write_text("{}\n")
    (seed / "profile.yaml").write_text("name: x\n")
    git(seed, env, "add", ".")
    git(seed, env, "commit", "-q", "-m", "seed")
    git(seed, env, "push", "-q", "origin", "main")
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], env=env, check=True)
    assert run_step(IDENTITY, work, env).returncode == 0
    return {"remote": remote, "seed": seed, "work": work}


def remote_count(repo, env) -> int:
    return int(git(repo["remote"], env, "rev-list", "--count", "main"))


def run_pipeline(repo, env, keepalive_rc: int = 3) -> list[subprocess.CompletedProcess]:
    results = []
    for script in (COMMIT, KEEPALIVE, PUSH):
        result = run_step(script, repo["work"], env, KEEPALIVE_RC=str(keepalive_rc))
        results.append(result)
        if result.returncode != 0:
            break
    return results


def test_unchanged_output_creates_no_commit(repo, env):
    results = run_pipeline(repo, env)
    assert all(r.returncode == 0 for r in results)
    assert "nothing to commit" in results[0].stdout
    assert "Nothing to push" in results[2].stdout
    assert remote_count(repo, env) == 1


def test_changed_readme_is_committed_and_pushed(repo, env):
    (repo["work"] / "README.md").write_text("# Profile\n\nnew\n")
    assert all(r.returncode == 0 for r in run_pipeline(repo, env))
    assert remote_count(repo, env) == 2
    assert git(repo["remote"], env, "log", "-1", "--format=%s", "main") == "chore: refresh profile README"
    assert git(repo["remote"], env, "show", "main:README.md").endswith("new")


def test_snapshot_only_change_is_committed(repo, env):
    (repo["work"] / "data" / "snapshot.json").write_text('{"posts": []}\n')
    assert all(r.returncode == 0 for r in run_pipeline(repo, env))
    assert remote_count(repo, env) == 2


def test_untracked_snapshot_on_first_run_is_committed(repo, env):
    git(repo["work"], env, "rm", "-q", "data/snapshot.json")
    git(repo["work"], env, "commit", "-q", "-m", "drop snapshot")
    git(repo["work"], env, "push", "-q")
    (repo["work"] / "data").mkdir(exist_ok=True)
    (repo["work"] / "data" / "snapshot.json").write_text("{}\n")
    assert all(r.returncode == 0 for r in run_pipeline(repo, env))
    assert git(repo["remote"], env, "show", "main:data/snapshot.json") == "{}"


def test_keepalive_needed_adds_one_empty_commit(repo, env):
    assert all(r.returncode == 0 for r in run_pipeline(repo, env, keepalive_rc=0))
    assert remote_count(repo, env) == 2
    assert git(repo["remote"], env, "log", "-1", "--format=%s", "main") == "chore: keep scheduled refresh alive"
    assert git(repo["remote"], env, "diff", "--name-only", "main~1", "main") == ""


def test_keepalive_error_fails_the_job(repo, env):
    results = run_pipeline(repo, env, keepalive_rc=1)
    assert results[1].returncode == 1
    assert "::error::profilegen keepalive failed with exit code 1" in results[1].stdout
    assert remote_count(repo, env) == 1


def test_rejected_push_rebases_and_retries(repo, env):
    # The remote moved meanwhile (Roland pushed a data-file change).
    (repo["seed"] / "profile.yaml").write_text("name: y\n")
    git(repo["seed"], env, "commit", "-q", "-am", "profile change")
    git(repo["seed"], env, "push", "-q")
    (repo["work"] / "README.md").write_text("# Profile\n\nnew\n")
    results = run_pipeline(repo, env)
    assert all(r.returncode == 0 for r in results), results[-1].stdout + results[-1].stderr
    assert "rebasing onto the remote (retry 1 of 3)" in results[2].stdout
    assert remote_count(repo, env) == 3
    assert git(repo["remote"], env, "log", "--format=%s", "main").splitlines()[:2] == [
        "chore: refresh profile README",
        "profile change",
    ]


def test_rebase_conflict_fails_with_error_and_aborts(repo, env):
    (repo["seed"] / "README.md").write_text("# Profile\n\nremote\n")
    git(repo["seed"], env, "commit", "-q", "-am", "remote readme")
    git(repo["seed"], env, "push", "-q")
    (repo["work"] / "README.md").write_text("# Profile\n\nlocal\n")
    results = run_pipeline(repo, env)
    assert results[2].returncode == 1
    assert "::error::rebase onto the remote conflicted" in results[2].stdout
    git_dir = repo["work"] / ".git"
    assert not (git_dir / "rebase-merge").exists() and not (git_dir / "rebase-apply").exists()
    assert remote_count(repo, env) == 2
