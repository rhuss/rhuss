"""Tests for the profilegen CLI (T019, contracts/cli.md).

Every test uses ``tmp_path`` as ``--root``. The root holds only profile.yaml,
data/snapshot.json and (where needed) a book cover; the template is found in
this checkout's ``templates/`` because the root has none (see profilegen.render).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from profilegen import cli, snapshot

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    shutil.copy(FIXTURES / "profile.yaml", tmp_path / "profile.yaml")
    (tmp_path / "data").mkdir()
    shutil.copy(FIXTURES / "snapshot.json", tmp_path / "data" / "snapshot.json")
    cover = tmp_path / "assets" / "books" / "kubernetes-patterns.png"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


@pytest.fixture
def no_token(monkeypatch):
    def fail():
        raise AssertionError("token must not be resolved")

    monkeypatch.setattr(cli.http, "resolve_token", fail)


def run(root, *args):
    return cli.main(["--root", str(root), *args])


def fixture_snapshot():
    return json.loads((FIXTURES / "snapshot.json").read_text(encoding="utf-8"))


# --- render ---------------------------------------------------------------------------


def test_render_offline_writes_readme_and_snapshot(root, no_token, no_git, capsys):
    # US4 AS1: a local render has no git side effects either.
    assert run(root, "render", "--offline", "--today", "2026-11-23") == 0
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert readme == (FIXTURES / "expected-README.md").read_text(encoding="utf-8")
    snap_text = (root / "data" / "snapshot.json").read_text(encoding="utf-8")
    assert snap_text == snapshot.dumps(fixture_snapshot())
    captured = capsys.readouterr()
    assert captured.err == ""


def test_render_twice_is_byte_identical_and_keeps_footer_date(root, no_token):
    assert run(root, "render", "--offline", "--today", "2026-11-23") == 0
    first = (root / "README.md").read_bytes()
    first_snap = (root / "data" / "snapshot.json").read_bytes()
    assert run(root, "render", "--offline", "--today", "2026-12-24") == 0
    assert (root / "README.md").read_bytes() == first
    assert (root / "data" / "snapshot.json").read_bytes() == first_snap


def test_global_options_after_subcommand(root, no_token):
    assert cli.main(["render", "--root", str(root), "--offline", "--today", "2026-11-23"]) == 0
    assert (root / "README.md").is_file()


def test_profile_option_relative_to_root(root, no_token):
    (root / "profile.yaml").rename(root / "other.yaml")
    assert run(root, "--profile", "other.yaml", "render", "--offline", "--today", "2026-11-23") == 0


def test_render_online_resolves_token_and_writes_refreshed_snapshot(root, monkeypatch):
    seen = {}

    def refresh(profile, snap, offline, token=None):
        seen["offline"], seen["token"] = offline, token
        new = dict(snap, total_stars=9999)
        return new, []

    monkeypatch.setattr(cli.http, "resolve_token", lambda: "tok")
    monkeypatch.setattr(cli.render_mod, "refresh", refresh)
    assert run(root, "render", "--today", "2026-11-23") == 0
    assert seen == {"offline": False, "token": "tok"}
    assert json.loads((root / "data" / "snapshot.json").read_text(encoding="utf-8"))["total_stars"] == 9999
    assert "10.0k" in (root / "README.md").read_text(encoding="utf-8")


def _stub_sources(monkeypatch, agenttacho_stars: int, total: int) -> None:
    """Live sources from the fixtures; only the star counts vary."""
    from profilegen import render
    from profilegen.model import BlogPost

    repos = fixture_snapshot()["repos"]
    raw = {"AgentTacho/agenttacho": agenttacho_stars, "jolokia/jolokia": 845, "knative/serving": 5821,
           "rhuss/cc-cfp": 7, "rhuss/cc-guide": 41, "rhuss/cc-spex": 312, "rhuss/corgi": 0}
    live = {k: dict(v, stars=raw[k]) for k, v in repos.items()}
    posts = [BlogPost(**p) for p in fixture_snapshot()["posts"]]
    archive = (FIXTURES / "archive-readme.md").read_text(encoding="utf-8")
    monkeypatch.setattr(cli.http, "resolve_token", lambda: None)
    monkeypatch.setattr(render.github, "fetch_repos", lambda p, token=None, missing=None: (live, total, []))
    monkeypatch.setattr(render.talks, "fetch_archive", lambda repo, token=None: archive)
    monkeypatch.setattr(render.blog, "fetch_posts", lambda url, n=3: posts[:n])


def test_star_change_below_display_precision_leaves_outputs_byte_identical(root, monkeypatch):
    # The snapshot stores only displayed values (FR-019, SC-006): one more star
    # on a repository shown as "1.2k" and on a total shown as "2.5k" changes nothing.
    _stub_sources(monkeypatch, agenttacho_stars=1234, total=2468)
    assert run(root, "render", "--today", "2026-11-23") == 0
    readme = (root / "README.md").read_bytes()
    snap = (root / "data" / "snapshot.json").read_bytes()

    _stub_sources(monkeypatch, agenttacho_stars=1235, total=2469)
    assert run(root, "render", "--today", "2026-11-24") == 0
    assert (root / "README.md").read_bytes() == readme
    assert (root / "data" / "snapshot.json").read_bytes() == snap

    # A change that is visible on the page does change both files.
    _stub_sources(monkeypatch, agenttacho_stars=1290, total=2551)
    assert run(root, "render", "--today", "2026-11-25") == 0
    assert (root / "README.md").read_bytes() != readme
    stored = json.loads((root / "data" / "snapshot.json").read_text(encoding="utf-8"))
    assert stored["total_stars"] == "2.6k"
    assert stored["repos"]["AgentTacho/agenttacho"]["stars"] == "1.3k"


def _tree(path: Path) -> dict[str, bytes | None]:
    """Every entry below ``path`` with file contents (None for directories)."""
    return {
        str(p.relative_to(path)): (p.read_bytes() if p.is_file() else None) for p in sorted(path.rglob("*"))
    }


@pytest.fixture
def no_git(monkeypatch):
    """Fail the test if anything starts a git process (FR-026: preview has no git side effects)."""
    real_popen = subprocess.Popen

    def guarded_popen(args, *a, **kw):
        argv = str(args).split() if isinstance(args, (str, bytes, Path)) else [str(a) for a in args]
        if argv and Path(argv[0]).name == "git":
            raise AssertionError(f"unexpected git invocation: {args!r}")
        return real_popen(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)


def test_render_output_does_not_touch_readme_or_snapshot(root, tmp_path_factory, monkeypatch, no_git):
    """T028: --output writes only PATH; root unchanged and no git process started."""
    monkeypatch.setattr(cli.http, "resolve_token", lambda: None)
    monkeypatch.setattr(cli.render_mod, "refresh", lambda p, s, offline, token=None: (dict(s, total_stars=1), []))
    out = tmp_path_factory.mktemp("preview") / "sub" / "preview.md"
    before_snap = (root / "data" / "snapshot.json").read_bytes()
    before_tree = _tree(root)
    assert run(root, "render", "--today", "2026-11-23", "--output", str(out)) == 0
    assert out.is_file()
    assert "⭐ **1** stars" in out.read_text(encoding="utf-8")
    assert not (root / "README.md").exists()
    assert (root / "data" / "snapshot.json").read_bytes() == before_snap
    assert _tree(root) == before_tree
    assert _tree(out.parent.parent) == {"sub": None, "sub/preview.md": out.read_bytes()}


def test_render_output_with_existing_readme_leaves_it_unchanged(root, tmp_path_factory, no_token, no_git):
    """T028: an existing README.md in the root stays byte-identical when previewing."""
    (root / "README.md").write_text("existing\n", encoding="utf-8")
    before_tree = _tree(root)
    out = tmp_path_factory.mktemp("preview") / "preview.md"
    assert run(root, "render", "--offline", "--today", "2026-11-23", "--output", str(out)) == 0
    assert out.read_text(encoding="utf-8") == (FIXTURES / "expected-README.md").read_text(encoding="utf-8")
    assert _tree(root) == before_tree


def test_no_git_guard_rejects_git(no_git):
    with pytest.raises(AssertionError, match="unexpected git invocation"):
        subprocess.run(["git", "status"], capture_output=True, check=False)
    with pytest.raises(AssertionError, match="unexpected git invocation"):
        subprocess.run("git status", shell=True, capture_output=True, check=False)


def test_render_without_snapshot_file(root, no_token):
    (root / "data" / "snapshot.json").unlink()
    assert run(root, "render", "--offline", "--today", "2026-11-23") == 0
    assert "_Currently unavailable._" in (root / "README.md").read_text(encoding="utf-8")
    assert json.loads((root / "data" / "snapshot.json").read_text(encoding="utf-8")) == {}


# --- warnings ---------------------------------------------------------------------------


@pytest.fixture
def warn_refresh(monkeypatch):
    monkeypatch.setattr(cli.http, "resolve_token", lambda: None)
    monkeypatch.setattr(
        cli.render_mod,
        "refresh",
        lambda p, s, offline, token=None: (s, ["blog feed unavailable, using last known values (timeout)",
                                              "main_projects[2]: repository not found or not public, omitted"]),
    )


def test_warnings_on_stderr_locally(root, warn_refresh, capsys):
    assert run(root, "render", "--today", "2026-11-23") == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        "WARNING: blog feed unavailable, using last known values (timeout)",
        "WARNING: main_projects[2]: repository not found or not public, omitted",
    ]


def test_warnings_as_annotations_in_github_actions(root, warn_refresh, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert run(root, "render", "--today", "2026-11-23") == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "::warning::blog feed unavailable, using last known values (timeout)",
        "::warning::main_projects[2]: repository not found or not public, omitted",
    ]


# --- validation errors -------------------------------------------------------------------


def _break_profile(root, old, new):
    path = root / "profile.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def _assert_nothing_written(root):
    assert not (root / "README.md").exists()
    assert (root / "data" / "snapshot.json").read_bytes() == (FIXTURES / "snapshot.json").read_bytes()


def test_render_invalid_profile_exit_1_nothing_written(root, no_token, capsys):
    _break_profile(root, "role: creator", "role: boss")
    assert run(root, "render", "--offline", "--today", "2026-11-23") == 1
    _assert_nothing_written(root)
    err = capsys.readouterr().err
    assert err.startswith("ERROR: community[0].role: must be one of")


def test_render_yaml_syntax_error_exit_1(root, no_token, capsys):
    (root / "profile.yaml").write_text("name: x\nlinks: [unclosed\n", encoding="utf-8")
    assert run(root, "render", "--offline") == 1
    _assert_nothing_written(root)
    assert "ERROR: profile.yaml: YAML syntax error at line" in capsys.readouterr().err


def test_render_missing_profile_exit_1(root, no_token, capsys):
    (root / "profile.yaml").unlink()
    assert run(root, "render", "--offline") == 1
    _assert_nothing_written(root)
    assert capsys.readouterr().err.startswith("ERROR: profile.yaml: cannot read file")


# --- validate -----------------------------------------------------------------------------


def test_validate_valid(root, capsys):
    assert run(root, "validate") == 0
    assert "valid" in capsys.readouterr().out


def test_validate_invalid(root, capsys):
    _break_profile(root, "description: Voice relay for meetings", "description: One. Two. Three. Four.")
    assert run(root, "validate") == 1
    assert capsys.readouterr().err.splitlines() == ["ERROR: main_projects[2].description: 4 sentences, max 3"]


def test_validate_yaml_syntax_error(root, capsys):
    (root / "profile.yaml").write_text("name: [x\n", encoding="utf-8")
    assert run(root, "validate") == 1
    assert capsys.readouterr().err.startswith("ERROR: profile.yaml: YAML syntax error at line")


# --- usage errors ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["frobnicate"],
        ["render", "--bogus"],
        ["render", "--today", "23.11.2026"],
        ["validate", "extra"],
    ],
    ids=["no-command", "unknown-command", "unknown-option", "bad-date", "extra-arg"],
)
def test_usage_errors_exit_2(argv, capsys):
    assert cli.main(argv) == 2
    assert "usage:" in capsys.readouterr().err


def test_help_exit_0(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "render" in out and "validate" in out


def test_module_help_runs_as_program():
    result = subprocess.run(
        [sys.executable, "-m", "profilegen.cli", "render", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "--offline" in result.stdout and "--output" in result.stdout and "--today" in result.stdout


def test_validation_errors_become_error_annotations_in_actions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    (tmp_path / "profile.yaml").write_text("name: x\n", encoding="utf-8")
    assert cli.main(["--root", str(tmp_path), "validate"]) == 1
    out, err = capsys.readouterr()
    assert out.startswith("::error::")
    assert "ERROR: " in err
