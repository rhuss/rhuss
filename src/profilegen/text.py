"""Text rules for curated prose: sentence counting and tagline checks (FR-024)."""

from __future__ import annotations

DEFAULT_ABBREVIATIONS = ["e.g.", "i.e.", "vs.", "etc.", "approx."]
TAGLINE_MAX = 120

_TERMINATORS = ".!?"
# Characters that may close a sentence after its terminator, e.g. `"hi."` or `(see this.)`.
_CLOSERS = "\"')]}”’"
# Characters that may open a token, e.g. `(e.g.`.
_OPENERS = "\"'([{“‘"


def count_sentences(text: str, abbreviations: list[str] = DEFAULT_ABBREVIATIONS) -> int:
    """Count sentences in ``text``.

    A sentence ends with ``.``, ``!`` or ``?`` followed by whitespace or the end of
    the text (optionally with closing quotes or brackets in between). Tokens on the
    abbreviation list (case-insensitive) do not end a sentence. Version numbers such
    as ``v1.0`` or ``3.12`` do not end a sentence because their dots are followed by
    a digit, not whitespace. Trailing text without final punctuation counts as one
    sentence.
    """
    abbrevs = {a.lower() for a in abbreviations}
    count = 0
    open_sentence = False
    for token in text.split():
        open_sentence = True
        core = token.rstrip(_CLOSERS)
        if not core or core[-1] not in _TERMINATORS:
            continue
        if core.lstrip(_OPENERS).lower() in abbrevs:
            continue
        count += 1
        open_sentence = False
    if open_sentence:
        count += 1
    return count


def check_tagline(text: str, max_len: int | None = TAGLINE_MAX) -> str | None:
    """Return ``None`` if ``text`` is a non-empty single line of at most ``max_len``
    characters (no length limit when ``max_len`` is None), otherwise an error message."""
    stripped = text.strip()
    if not stripped:
        return "must not be empty"
    if "\n" in stripped or "\r" in stripped:
        return "must be a single line"
    if max_len is not None and len(stripped) > max_len:
        return f"{len(stripped)} characters, max {max_len}"
    return None
