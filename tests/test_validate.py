import copy
from pathlib import Path

import pytest
import yaml

from profilegen.model import (
    Book,
    Link,
    Profile,
    ProfileError,
    Settings,
    load_profile,
    load_yaml,
    profile_from_dict,
)
from profilegen.validate import validate

FIXTURE = Path(__file__).parent / "fixtures" / "profile.yaml"
_BASE = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def base() -> dict:
    return copy.deepcopy(_BASE)


def errors_at(d: dict, path: str) -> list[str]:
    """Errors whose path is exactly ``path``."""
    return [e for e in validate(d) if e.split(": ", 1)[0] == path]


# --- fixture -------------------------------------------------------------


def test_fixture_validates_clean():
    assert validate(base()) == []


def test_fixture_loads_as_profile():
    profile = load_profile(FIXTURE)
    assert isinstance(profile, Profile)
    assert profile.name == "Roland Huß"
    assert [p.repo for p in profile.main_projects] == ["rhuss/cc-spex", "AgentTacho/agenttacho", "rhuss/corgi"]
    assert profile.main_projects[2].name is None
    assert profile.main_projects[1].name == "AgentTacho"
    assert [p.role for p in profile.community] == ["creator", "maintainer"]
    assert [b.cover for b in profile.books] == ["assets/books/kubernetes-patterns.png", None]
    assert isinstance(profile.books[0], Book)
    assert isinstance(profile.links[0], Link)
    assert {b.label for b in profile.badges} >= {"Claude Code", "Spec-Driven"}
    assert profile.badges[2].logo is None and profile.badges[2].logo_color is None
    assert len(profile.more_tools) == 2
    assert profile.settings.talks_shown == 6
    assert profile.settings.demote_after_days == 60


def test_settings_defaults():
    s = Settings()
    assert s.talks_shown == 8
    assert s.posts_shown == 3
    assert s.demote_after_days == 60
    assert s.promote_commits == 10
    assert s.promote_window_days == 30
    assert s.owned_owners == ["rhuss", "AgentTacho", "k8spatterns"]
    assert s.owned_extra_repos == ["jolokia/jolokia", "fabric8io/docker-maven-plugin"]
    assert s.abbreviations == ["e.g.", "i.e.", "vs.", "etc.", "approx."]
    assert s.scan_roots == ["~/Development", "~/Work/projects"]
    assert s.feed_url == "https://ro14nd.de/index.xml"
    assert s.talks_repo == "ro14nd-talks/archive"
    # default_factory: lists are not shared between instances
    s.owned_owners.append("x")
    assert Settings().owned_owners == ["rhuss", "AgentTacho", "k8spatterns"]


def test_profile_without_settings_uses_defaults():
    d = base()
    del d["settings"]
    assert validate(d) == []
    assert profile_from_dict(d).settings == Settings()


# --- top level -----------------------------------------------------------


def test_non_mapping_rejected():
    assert validate([]) != []
    assert validate(None) != []


@pytest.mark.parametrize("key", ["name", "intro", "links", "main_projects", "books"])
def test_required_top_level_fields(key):
    d = base()
    del d[key]
    errs = errors_at(d, key)
    assert errs and "required" in errs[0]


@pytest.mark.parametrize("key", ["badges", "community", "more_tools", "settings"])
def test_optional_top_level_fields(key):
    d = base()
    del d[key]
    assert validate(d) == []


def test_unknown_top_level_key_rejected():
    d = base()
    d["main_project"] = []
    assert errors_at(d, "main_project") == ["main_project: unknown key"]


def test_empty_name_rejected():
    d = base()
    d["name"] = "  "
    assert errors_at(d, "name")


# --- intro ---------------------------------------------------------------


def test_intro_max_160_chars():
    d = base()
    d["intro"] = "x" * 160
    assert validate(d) == []
    d["intro"] = "x" * 161
    assert errors_at(d, "intro") == ["intro: 161 characters, max 160"]


def test_intro_single_line():
    d = base()
    d["intro"] = "line one\nline two"
    errs = errors_at(d, "intro")
    assert errs and "single line" in errs[0]


# --- main projects ---------------------------------------------------------


def test_main_projects_at_least_one():
    d = base()
    d["main_projects"] = []
    errs = errors_at(d, "main_projects")
    assert errs and "1..12" in errs[0]


def test_main_projects_at_most_twelve():
    d = base()
    d["community"] = []
    d["more_tools"] = []
    d["main_projects"] = [{"repo": f"rhuss/p{i}", "description": "A project."} for i in range(12)]
    assert validate(d) == []
    d["main_projects"].append({"repo": "rhuss/p12", "description": "One more."})
    errs = errors_at(d, "main_projects")
    assert errs and "13" in errs[0] and "1..12" in errs[0]


def test_main_project_description_max_three_sentences():
    d = base()
    d["main_projects"][0]["description"] = "One. Two. Three."
    assert validate(d) == []
    d["main_projects"][0]["description"] = "One. Two. Three. Four."
    assert errors_at(d, "main_projects[0].description") == ["main_projects[0].description: 4 sentences, max 3"]


def test_main_project_description_required():
    d = base()
    del d["main_projects"][1]["description"]
    errs = errors_at(d, "main_projects[1].description")
    assert errs and "required" in errs[0]


def test_main_project_description_empty_rejected():
    d = base()
    d["main_projects"][1]["description"] = "   "
    assert errors_at(d, "main_projects[1].description")


def test_description_uses_settings_abbreviations():
    d = base()
    d["main_projects"][0]["description"] = "Ask Dr. Who. Then Dr. No. Done."
    assert errors_at(d, "main_projects[0].description") == ["main_projects[0].description: 5 sentences, max 3"]
    d["settings"]["abbreviations"] = ["dr.", "e.g.", "vs."]
    assert validate(d) == []


def test_settings_abbreviations_replace_defaults():
    d = base()
    d["main_projects"][0]["description"] = "Uses e.g. this. And e.g. that. And e.g. more."
    assert validate(d) == []
    d["settings"]["abbreviations"] = ["dr."]
    assert errors_at(d, "main_projects[0].description") == ["main_projects[0].description: 6 sentences, max 3"]


def test_description_default_abbreviations_apply():
    d = base()
    d["main_projects"][0]["description"] = "Tools, e.g. this, i.e. that, vs. others, etc. One. Two. Supports v1.0 and 3.12."
    assert validate(d) == []


def test_project_unknown_key_rejected():
    d = base()
    d["main_projects"][0]["descripton"] = "typo"
    assert errors_at(d, "main_projects[0].descripton") == ["main_projects[0].descripton: unknown key"]


def test_project_url_must_be_https():
    d = base()
    d["main_projects"][1]["url"] = "http://agenttacho.dev"
    assert errors_at(d, "main_projects[1].url")


# --- repo format and uniqueness --------------------------------------------


@pytest.mark.parametrize("repo", ["cc-spex", "rhuss/", "/cc-spex", "rhuss/cc-spex/extra", "rhuss cc-spex", "", 42])
def test_repo_must_match_owner_name(repo):
    d = base()
    d["main_projects"][0]["repo"] = repo
    assert errors_at(d, "main_projects[0].repo")


def test_repo_required():
    d = base()
    del d["more_tools"][0]["repo"]
    errs = errors_at(d, "more_tools[0].repo")
    assert errs and "required" in errs[0]


def test_repo_valid_forms():
    d = base()
    d["more_tools"][0]["repo"] = "fabric8io/docker-maven-plugin"
    d["more_tools"][1]["repo"] = "k8spatterns/k8spatterns.com"
    assert validate(d) == []


def test_repo_duplicate_within_group():
    d = base()
    d["main_projects"][2]["repo"] = "rhuss/cc-spex"
    errs = errors_at(d, "main_projects[2].repo")
    assert errs and "main_projects[0]" in errs[0]


@pytest.mark.parametrize(
    "group, index",
    [("community", 1), ("more_tools", 0)],
)
def test_repo_duplicate_across_groups(group, index):
    d = base()
    d[group][index]["repo"] = "rhuss/cc-spex"
    errs = errors_at(d, f"{group}[{index}].repo")
    assert errs and "main_projects[0]" in errs[0]


def test_repo_duplicate_is_case_insensitive():
    d = base()
    d["more_tools"][0]["repo"] = "RHUSS/CC-SPEX"
    assert errors_at(d, "more_tools[0].repo")


# --- community -------------------------------------------------------------


def test_community_role_required():
    d = base()
    del d["community"][0]["role"]
    errs = errors_at(d, "community[0].role")
    assert errs and "required" in errs[0]


@pytest.mark.parametrize("role", ["creator", "co-creator", "maintainer", "alumni-maintainer", "contributor", "lead"])
def test_community_role_enum_accepts(role):
    d = base()
    d["community"][0]["role"] = role
    assert validate(d) == []


@pytest.mark.parametrize("role", ["Creator", "owner", "", 1, "alumni maintainer", "alumni"])
def test_community_role_enum_rejects(role):
    d = base()
    d["community"][0]["role"] = role
    assert errors_at(d, "community[0].role")


@pytest.mark.parametrize("group", ["community", "more_tools"])
def test_tagline_required(group):
    d = base()
    del d[group][0]["tagline"]
    errs = errors_at(d, f"{group}[0].tagline")
    assert errs and "required" in errs[0]


@pytest.mark.parametrize("group", ["community", "more_tools"])
def test_tagline_max_120(group):
    d = base()
    d[group][0]["tagline"] = "x" * 120
    assert validate(d) == []
    d[group][0]["tagline"] = "x" * 121
    assert errors_at(d, f"{group}[0].tagline") == [f"{group}[0].tagline: 121 characters, max 120"]


@pytest.mark.parametrize("group", ["community", "more_tools"])
def test_tagline_single_line(group):
    d = base()
    d[group][1]["tagline"] = "first line\nsecond line"
    errs = errors_at(d, f"{group}[1].tagline")
    assert errs and "single line" in errs[0]


# --- books -----------------------------------------------------------------


@pytest.mark.parametrize("field", ["title", "description", "url"])
def test_book_required_fields(field):
    d = base()
    del d["books"][0][field]
    errs = errors_at(d, f"books[0].{field}")
    assert errs and "required" in errs[0]


def test_book_description_single_line():
    d = base()
    d["books"][1]["description"] = "line one\nline two"
    errs = errors_at(d, "books[1].description")
    assert errs and "single line" in errs[0]


@pytest.mark.parametrize(
    "cover",
    [
        "/abs/cover.png",
        "https://example.com/cover.png",
        "../outside.png",
        "~/cover.png",
        "",
        "cover.png",
        "assets/cover.png",
        "assets/books/../../x.png",
    ],
)
def test_book_cover_must_be_relative_path(cover):
    d = base()
    d["books"][0]["cover"] = cover
    assert errors_at(d, "books[0].cover")


def test_book_cover_nonexistent_file_is_fine():
    d = base()
    d["books"][1]["cover"] = "assets/books/does-not-exist.png"
    assert validate(d) == []


# --- links and badges --------------------------------------------------------


def test_links_must_include_blog():
    d = base()
    d["links"] = [lk for lk in d["links"] if "ro14nd.de" not in lk["url"]]
    errs = errors_at(d, "links")
    assert errs and "blog" in errs[0].lower()


def test_blog_link_matched_by_host():
    d = base()
    d["links"][0]["url"] = "https://example.com/ro14nd.de"
    assert errors_at(d, "links")
    d["links"][0]["url"] = "https://ro14nd.de/"
    assert validate(d) == []


def test_links_must_include_linkedin():
    d = base()
    d["links"] = [lk for lk in d["links"] if "linkedin.com" not in lk["url"]]
    errs = errors_at(d, "links")
    assert errs and "linkedin" in errs[0].lower()


@pytest.mark.parametrize("field", ["label", "url"])
def test_link_required_fields(field):
    d = base()
    del d["links"][0][field]
    assert errors_at(d, f"links[0].{field}")


def test_link_url_must_be_https():
    d = base()
    d["links"][1]["url"] = "http://www.linkedin.com/in/ro14nd/"
    assert errors_at(d, "links[1].url")


@pytest.mark.parametrize("field", ["label", "color"])
def test_badge_required_fields(field):
    d = base()
    del d["badges"][0][field]
    assert errors_at(d, f"badges[0].{field}")


def test_badge_unknown_key_rejected():
    d = base()
    d["badges"][0]["logoColor"] = "white"
    assert errors_at(d, "badges[0].logoColor") == ["badges[0].logoColor: unknown key"]


# --- settings --------------------------------------------------------------


@pytest.mark.parametrize("value, ok", [(4, False), (5, True), (8, True), (10, True), (11, False), ("8", False), (True, False)])
def test_talks_shown_range(value, ok):
    d = base()
    d["settings"]["talks_shown"] = value
    assert (errors_at(d, "settings.talks_shown") == []) is ok


@pytest.mark.parametrize("key", ["demote_after_days", "promote_commits", "promote_window_days"])
@pytest.mark.parametrize("value, ok", [(1, True), (60, True), (0, False), (-5, False), (2.5, False), ("10", False), (True, False)])
def test_positive_int_settings(key, value, ok):
    d = base()
    d["settings"][key] = value
    assert (errors_at(d, f"settings.{key}") == []) is ok


def test_unknown_settings_key_rejected():
    d = base()
    d["settings"]["talk_shown"] = 8
    assert errors_at(d, "settings.talk_shown") == ["settings.talk_shown: unknown key"]


def test_settings_must_be_mapping():
    d = base()
    d["settings"] = [1, 2]
    assert errors_at(d, "settings")


def test_abbreviations_must_be_list_of_strings():
    d = base()
    d["settings"]["abbreviations"] = "e.g."
    assert errors_at(d, "settings.abbreviations")


def test_all_known_settings_accepted():
    d = base()
    d["settings"] = {
        "talks_shown": 8,
        "posts_shown": 3,
        "demote_after_days": 60,
        "promote_commits": 10,
        "promote_window_days": 30,
        "owned_owners": ["rhuss"],
        "owned_extra_repos": ["jolokia/jolokia"],
        "abbreviations": ["e.g."],
        "scan_roots": ["~/Development"],
        "feed_url": "https://ro14nd.de/index.xml",
        "talks_repo": "ro14nd-talks/archive",
    }
    assert validate(d) == []
    s = profile_from_dict(d).settings
    assert s.owned_owners == ["rhuss"] and s.abbreviations == ["e.g."]


# --- loading -----------------------------------------------------------------


def test_yaml_syntax_error_reports_line_number(tmp_path):
    p = tmp_path / "profile.yaml"
    p.write_text("name: Roland\nintro: hello\nlinks: [\n  {label: Blog\nbooks: []\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_yaml(p)
    assert len(exc.value.errors) == 1
    msg = exc.value.errors[0]
    assert msg.startswith("profile.yaml: YAML syntax error at line ")
    line = int(msg.removeprefix("profile.yaml: YAML syntax error at line ").split(":", 1)[0])
    assert 3 <= line <= 5
    assert str(exc.value) == msg


def test_yaml_syntax_error_via_load_profile(tmp_path):
    p = tmp_path / "profile.yaml"
    p.write_text("name: Roland\n  intro: bad indent\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profile(p)
    assert "YAML syntax error at line 2" in str(exc.value)


def test_unreadable_file_raises_profile_error(tmp_path):
    with pytest.raises(ProfileError):
        load_yaml(tmp_path / "missing.yaml")


def test_load_profile_raises_with_all_validation_errors(tmp_path):
    d = base()
    d["intro"] = "x" * 200
    d["settings"]["talks_shown"] = 42
    p = tmp_path / "profile.yaml"
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profile(p)
    paths = {e.split(": ", 1)[0] for e in exc.value.errors}
    assert paths == {"intro", "settings.talks_shown"}
    assert "intro: 200 characters, max 160" in str(exc.value)


def test_linkedin_link_matched_by_host():
    d = base()
    d["links"][1]["url"] = "https://example.com/?next=linkedin.com"
    assert errors_at(d, "links")


@pytest.mark.parametrize("path,value", [("links", "https://"), ("settings.feed_url", "https://")])
def test_https_url_needs_a_host(path, value):
    d = base()
    if path == "links":
        d["links"][0]["url"] = value
        assert errors_at(d, "links[0].url")
    else:
        d.setdefault("settings", {})["feed_url"] = value
        assert errors_at(d, path)


@pytest.mark.parametrize(
    "key,value",
    [
        ("posts_shown", 0),
        ("posts_shown", "3"),
        ("owned_extra_repos", ["bad"]),
        ("feed_url", "http://ro14nd.de/index.xml"),
        ("talks_repo", "nope"),
        ("scan_roots", "x"),
    ],
)
def test_more_invalid_settings(key, value):
    d = base()
    d.setdefault("settings", {})[key] = value
    assert any(e.startswith(f"settings.{key}") for e in validate(d)), validate(d)


def test_numeric_badge_color_rejected():
    d = base()
    d["badges"][0]["color"] = 326
    assert errors_at(d, "badges[0].color")


@pytest.mark.parametrize("field", ["links", "book", "feed"])
def test_unparseable_url_is_a_validation_error_not_a_crash(field):
    d = base()
    bad = "https://[x"
    if field == "links":
        d["links"][0]["url"] = bad
        assert errors_at(d, "links[0].url")
    elif field == "book":
        d["books"][0]["url"] = bad
        assert errors_at(d, "books[0].url")
    else:
        d.setdefault("settings", {})["feed_url"] = bad
        assert errors_at(d, "settings.feed_url")
