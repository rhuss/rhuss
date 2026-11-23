"""Load, merge and save ``data/snapshot.json`` (FR-019).

The snapshot holds the last successfully fetched values per live source and
nothing else. It works on plain dicts so it does not depend on the model.

Unknown top-level keys: ``merge`` drops every key outside :data:`KEYS` (from
both the old snapshot and the fetched values), and ``dumps``/``save`` refuse
to serialize a snapshot with keys outside :data:`KEYS` by raising
``ValueError``. Together this guarantees that timestamps, run ids or fetch
status flags can never be written to the file.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

__all__ = ["KEYS", "load", "merge", "dumps", "save"]

KEYS = ("repos", "total_stars", "talks", "talk_years", "posts")


def load(path: str | os.PathLike) -> dict:
    """Read the snapshot; a missing, unreadable or invalid file yields {}."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def merge(old: dict, fetched: dict) -> dict:
    """Return a new snapshot: fetched values replace old ones per key.

    ``fetched`` holds only the keys of sources that succeeded. Every other
    key keeps its old value, or stays absent if it had none. Keys outside
    KEYS are dropped.
    """
    result: dict = {}
    for key in KEYS:
        if key in fetched:
            result[key] = copy.deepcopy(fetched[key])
        elif key in old:
            result[key] = copy.deepcopy(old[key])
    return result


def dumps(snap: dict) -> str:
    """Deterministic serialization; refuses keys outside KEYS."""
    unknown = sorted(str(k) for k in snap if k not in KEYS)
    if unknown:
        raise ValueError(f"snapshot has unknown top-level keys: {', '.join(unknown)}")
    return json.dumps(snap, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def save(path: str | os.PathLike, snap: dict) -> None:
    """Write dumps(snap) to path (atomically), creating the parent directory."""
    text = dumps(snap)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
