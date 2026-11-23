"""Tests for profilegen.snapshot (contracts/snapshot-json.md)."""

import json
import re

import pytest

from profilegen import snapshot

OLD = {
    "repos": {
        "rhuss/cc-spex": {"full_name": "rhuss/cc-spex", "stars": 200, "url": "https://github.com/rhuss/cc-spex"}
    },
    "total_stars": 4000,
    "talks": [
        {"year": 2026, "month": 9, "title": "Old talk", "url": None, "venue": "Conf", "extras": []}
    ],
    "talk_years": [2025, 2026],
    "posts": [{"title": "Old post", "url": "https://ro14nd.de/old", "date": "2026-01-02"}],
}

NEW_REPOS = {
    "rhuss/cc-spex": {"full_name": "rhuss/cc-spex", "stars": 214, "url": "https://github.com/rhuss/cc-spex"}
}
NEW_POSTS = [{"title": "Über Specs", "url": "https://ro14nd.de/new", "date": "2026-11-20"}]


# --- load -------------------------------------------------------------------


def test_load_missing_file_is_empty(tmp_path):
    assert snapshot.load(tmp_path / "nope" / "snapshot.json") == {}


def test_load_invalid_json_is_empty(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("{not json", encoding="utf-8")
    assert snapshot.load(path) == {}


def test_load_non_object_json_is_empty(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert snapshot.load(path) == {}


def test_load_undecodable_bytes_is_empty(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_bytes(b"\xff\xfe\x00garbage")
    assert snapshot.load(path) == {}


def test_load_unreadable_path_is_empty(tmp_path):
    # A directory where the file should be cannot be read as a file.
    path = tmp_path / "snapshot.json"
    path.mkdir()
    assert snapshot.load(path) == {}


def test_load_roundtrip(tmp_path):
    path = tmp_path / "snapshot.json"
    snapshot.save(path, OLD)
    assert snapshot.load(path) == OLD


# --- merge ------------------------------------------------------------------


def test_merge_replaces_successful_keys():
    merged = snapshot.merge(
        OLD, {"repos": NEW_REPOS, "total_stars": 4100, "talks": [], "talk_years": [2026], "posts": NEW_POSTS}
    )
    assert merged == {
        "repos": NEW_REPOS, "total_stars": 4100, "talks": [], "talk_years": [2026], "posts": NEW_POSTS
    }


def test_merge_failed_key_keeps_old_value():
    # A failed source contributes no keys to ``fetched``.
    merged = snapshot.merge(OLD, {"talks": OLD["talks"], "posts": NEW_POSTS})
    assert merged["repos"] == OLD["repos"]
    assert merged["total_stars"] == 4000
    assert merged["posts"] == NEW_POSTS


def test_merge_talks_unit_replaced_together():
    merged = snapshot.merge(OLD, {"talks": [], "talk_years": [2013, 2014]})
    assert merged["talks"] == []
    assert merged["talk_years"] == [2013, 2014]


def test_merge_talks_unit_kept_together_on_failure():
    merged = snapshot.merge(OLD, {"posts": NEW_POSTS})
    assert merged["talks"] == OLD["talks"]
    assert merged["talk_years"] == OLD["talk_years"]


def test_merge_failed_key_without_old_value_stays_absent():
    merged = snapshot.merge({}, {"total_stars": 12})
    assert "posts" not in merged
    assert merged == {"total_stars": 12}


def test_merge_key_not_fetched_keeps_old_value():
    merged = snapshot.merge(OLD, {"posts": NEW_POSTS})
    assert merged["talks"] == OLD["talks"]
    assert merged["repos"] == OLD["repos"]


def test_merge_empty_list_is_a_successful_value():
    merged = snapshot.merge(OLD, {"posts": []})
    assert merged["posts"] == []


def test_merge_does_not_mutate_inputs():
    old = json.loads(json.dumps(OLD))
    fetched = {"repos": NEW_REPOS}
    merged = snapshot.merge(old, fetched)
    assert old == OLD
    merged["repos"]["rhuss/cc-spex"]["stars"] = 0
    merged["talks"].append({})
    assert NEW_REPOS["rhuss/cc-spex"]["stars"] == 214
    assert old == OLD


def test_merge_drops_unknown_top_level_keys():
    old = dict(OLD, generated_at="2026-11-23T04:17:00Z", run_id=42)
    merged = snapshot.merge(old, {"posts": NEW_POSTS, "status": {"posts": "ok"}, "fetched_at": "now"})
    assert set(merged) == set(snapshot.KEYS)


# --- dumps / save -----------------------------------------------------------


def test_dumps_format_is_sorted_indented_with_trailing_newline():
    text = snapshot.dumps({"total_stars": 1, "posts": [], "repos": {"b/b": {"stars": 1}, "a/a": {"stars": 2}}})
    assert text == json.dumps(
        {"posts": [], "repos": {"a/a": {"stars": 2}, "b/b": {"stars": 1}}, "total_stars": 1},
        indent=2,
    ) + "\n"
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert text.index('"posts"') < text.index('"repos"') < text.index('"total_stars"')


def test_dumps_is_deterministic():
    assert snapshot.dumps(OLD) == snapshot.dumps(json.loads(snapshot.dumps(OLD)))


def test_non_ascii_survives(tmp_path):
    snap = {"posts": [{"title": "Roland Huß über Kubernetes", "url": "https://ro14nd.de/x", "date": "2026-11-01"}]}
    text = snapshot.dumps(snap)
    assert "Huß über" in text
    assert "\\u" not in text
    path = tmp_path / "snapshot.json"
    snapshot.save(path, snap)
    assert "Huß über" in path.read_text(encoding="utf-8")
    assert snapshot.load(path) == snap


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "data" / "nested" / "snapshot.json"
    snapshot.save(path, OLD)
    assert path.read_text(encoding="utf-8") == snapshot.dumps(OLD)
    assert [p.name for p in path.parent.iterdir()] == ["snapshot.json"]


def test_failed_save_removes_temp_file_and_keeps_old_file(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    path.write_text("old\n", encoding="utf-8")

    def fail(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(snapshot.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        snapshot.save(path, OLD)
    assert [p.name for p in tmp_path.iterdir()] == ["snapshot.json"]
    assert path.read_text(encoding="utf-8") == "old\n"


def test_dumps_refuses_unknown_top_level_keys(tmp_path):
    with pytest.raises(ValueError, match="generated_at"):
        snapshot.dumps(dict(OLD, generated_at="2026-11-23"))
    path = tmp_path / "snapshot.json"
    with pytest.raises(ValueError):
        snapshot.save(path, {"status": "ok"})
    assert not path.exists()


TIMESTAMPISH = re.compile(r"(time|date|stamp|status|run|fetched|updated|generated|ok|error)", re.I)


def test_no_timestamp_or_status_keys_ever_written(tmp_path):
    # Simulate a sequence of runs with mixed success and junk keys supplied
    # by callers; the written file must only ever hold the four data keys.
    path = tmp_path / "data" / "snapshot.json"
    runs = [
        {"repos": NEW_REPOS, "total_stars": 4100, "talks": OLD["talks"], "posts": NEW_POSTS,
         "updated_at": "2026-11-23T04:17:00Z"},
        {"talks": OLD["talks"], "status": {"repos": "failed"}},
        {"repos": NEW_REPOS, "total_stars": 4100, "talks": [], "posts": [], "run_id": 7},
    ]
    for fetched in runs:
        snapshot.save(path, snapshot.merge(snapshot.load(path), fetched))
        written = json.loads(path.read_text(encoding="utf-8"))
        assert set(written) <= set(snapshot.KEYS)
        assert not [k for k in written if TIMESTAMPISH.search(k)]


def test_keys_constant():
    assert snapshot.KEYS == ("repos", "total_stars", "talks", "talk_years", "posts")
