import pytest

from profilegen.text import DEFAULT_ABBREVIATIONS, check_tagline, count_sentences


def test_default_abbreviations():
    assert DEFAULT_ABBREVIATIONS == ["e.g.", "i.e.", "vs.", "etc.", "approx."]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", 0),
        ("   ", 0),
        ("One sentence.", 1),
        ("One sentence", 1),
        ("First. Second.", 2),
        ("First! Second? Third.", 3),
        ("First.\nSecond.", 2),
        ("First. Second. Third. Fourth.", 4),
        ("First sentence. Trailing text without punctuation", 2),
        ("Really?! Yes.", 2),
        ("Wait... then more.", 2),
        ('He said "hi." Then left.', 2),
        ("A tool (really useful.) Next one.", 2),
        ("No space.after the dot", 1),
    ],
)
def test_basic_sentence_counting(text, expected):
    assert count_sentences(text) == expected


@pytest.mark.parametrize("abbr", ["e.g.", "i.e.", "vs.", "etc.", "approx."])
def test_abbreviations_do_not_end_sentence(abbr):
    assert count_sentences(f"Works with things {abbr} other things here.") == 1


def test_abbreviations_case_insensitive_and_in_parentheses():
    assert count_sentences("E.g. this one. And (e.g. that) too.") == 2


def test_abbreviation_at_end_counts_as_one_sentence():
    assert count_sentences("Apples, pears, etc.") == 1


def test_multiple_abbreviations():
    text = "Agents, e.g. Claude Code vs. Codex, run approx. 10 tasks, i.e. many, etc. All tracked."
    assert count_sentences(text) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Supports v1.0 and later.",
        "Requires Python 3.12 or newer.",
        "Tested with release 1.2.3 today.",
        "Upgrade from v2.10.1 to v3.0 is easy.",
    ],
)
def test_version_numbers_do_not_end_sentence(text):
    assert count_sentences(text) == 1


def test_version_number_at_end_of_sentence():
    assert count_sentences("Released v1.0. Next comes 3.12.") == 2


def test_custom_abbreviations():
    assert count_sentences("See approx. two. Done.") == 2
    assert count_sentences("See approx. two. Done.", abbreviations=[]) == 3
    assert count_sentences("Ask Dr. Who. Done.", abbreviations=["dr."]) == 2
    assert count_sentences("Ask Dr. Who. Done.") == 3


def test_tagline_ok():
    assert check_tagline("Draft conference proposals with a simulated program committee") is None


def test_tagline_exactly_max_length_ok():
    assert check_tagline("x" * 120) is None


def test_tagline_too_long():
    msg = check_tagline("x" * 121)
    assert msg is not None
    assert "121" in msg and "120" in msg


def test_tagline_custom_max_len():
    assert check_tagline("abcdef", max_len=5) is not None
    assert check_tagline("abcde", max_len=5) is None


@pytest.mark.parametrize("text", ["two\nlines", "two\r\nlines", "line one\n\nline two"])
def test_tagline_multiline_rejected(text):
    msg = check_tagline(text)
    assert msg is not None
    assert "single line" in msg


def test_tagline_trailing_newline_tolerated():
    # YAML literal block scalars add a trailing newline; content is still one line.
    assert check_tagline("one line\n") is None


def test_tagline_empty_rejected():
    assert check_tagline("") is not None
    assert check_tagline("   ") is not None
