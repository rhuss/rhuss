"""Structural checks for the refresh workflow (T023, FR-016 to FR-019a, R7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "refresh.yml"


@pytest.fixture(scope="module")
def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow(text) -> dict:
    return yaml.safe_load(text)


@pytest.fixture(scope="module")
def triggers(workflow) -> dict:
    # YAML 1.1 (PyYAML) reads the bare key `on` as boolean True.
    return workflow[True] if True in workflow else workflow["on"]


@pytest.fixture(scope="module")
def steps(workflow) -> list[dict]:
    return workflow["jobs"]["refresh"]["steps"]


def _step_index(steps, needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in step.get("run", "") or needle in step.get("uses", ""):
            return i
    raise AssertionError(f"no step contains {needle!r}")


def test_name(workflow):
    assert workflow["name"] == "Refresh profile"


def test_triggers(triggers):
    assert set(triggers) == {"schedule", "workflow_dispatch", "push"}
    assert triggers["schedule"] == [{"cron": "17 4 * * *"}]
    assert triggers["push"]["paths"] == ["profile.yaml", "templates/**", "assets/**"]


def test_push_runs_only_on_default_branch(workflow, triggers):
    branches = triggers["push"].get("branches")
    guard = workflow["jobs"]["refresh"].get("if", "")
    assert branches or "github.event.repository.default_branch" in guard


def test_permissions(workflow):
    assert workflow["permissions"] == {"contents": "write"}
    assert "permissions" not in workflow["jobs"]["refresh"]


def test_concurrency_is_job_level(workflow):
    # Job-level so a skipped run for another branch never replaces a pending
    # default-branch run in the queue.
    assert "concurrency" not in workflow
    assert workflow["jobs"]["refresh"]["concurrency"] == {"group": "refresh", "cancel-in-progress": False}


def test_only_builtin_token_secret(text):
    assert set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)) == {"GITHUB_TOKEN"}


def test_checkout_full_history_of_branch_tip(steps):
    checkout = steps[_step_index(steps, "actions/checkout@")]
    assert checkout["with"]["fetch-depth"] == 0
    # A branch name (not the trigger SHA) so queued runs render the latest tip.
    assert checkout["with"]["ref"] == "${{ github.ref_name }}"
    assert _step_index(steps, "astral-sh/setup-uv@") > 0


def test_actions_pinned_to_commit_shas(steps):
    for step in steps:
        if "uses" in step:
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]


def test_render_step_uses_token_and_locked_env(steps):
    render = steps[_step_index(steps, "profilegen render")]
    assert render["run"].strip() == "uv run --locked profilegen render"
    assert render["env"] == {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}
    assert "continue-on-error" not in render


def test_bot_identity(text):
    assert 'git config user.name "github-actions[bot]"' in text
    assert 'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"' in text


def test_content_commit_only_when_changed(steps):
    run = steps[_step_index(steps, "git diff --cached --quiet")]["run"]
    assert "git add -- README.md data/snapshot.json" in run
    assert "git diff --cached --quiet -- README.md data/snapshot.json" in run


def test_keepalive_step(steps):
    run = steps[_step_index(steps, "profilegen keepalive")]["run"]
    assert "rc=0" in run
    assert "uv run --locked profilegen keepalive --days 50 || rc=$?" in run
    assert 'git commit --allow-empty -m "chore: keep scheduled refresh alive"' in run
    assert re.search(r"^\s*3\)", run, re.M)
    assert re.search(r"^\s*\*\).*exit 1", run, re.M)


def test_push_only_if_ahead_with_retries(steps):
    run = steps[_step_index(steps, "git push")]["run"]
    assert "git rev-list --count '@{u}..HEAD'" in run
    assert "if ! git pull --rebase; then" in run
    assert "git rebase --abort" in run
    assert "for attempt in 0 1 2 3" in run


def test_step_order(steps):
    render = _step_index(steps, "profilegen render")
    commit = _step_index(steps, "git diff --cached --quiet")
    keep = _step_index(steps, "profilegen keepalive")
    push = _step_index(steps, "git push")
    assert render < commit < keep < push


def test_no_em_or_en_dash(text):
    assert chr(0x2014) not in text and chr(0x2013) not in text
