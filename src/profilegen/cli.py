"""Command line interface: ``render``, ``validate``, ``scan`` and ``keepalive``.

Exit codes:

* every subcommand: 2 usage error (argparse), 1 data-file validation error
  (nothing written);
* ``render``: 0 success, warnings allowed (FR-019a);
* ``validate``: 0 valid;
* ``scan``: 0 report printed, 1 also when repository visibility cannot be
  verified (no proposals emitted, FR-023);
* ``keepalive``: 0 keep-alive commit needed, 3 not needed, 1 git failed.

``--profile`` is resolved relative to ``--root`` unless it is absolute;
``--output`` is resolved relative to the current directory. Both global
options are accepted before or after the subcommand.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from profilegen import keepalive
from profilegen import render as render_mod
from profilegen import scan as scan_mod
from profilegen import snapshot
from profilegen.model import Profile, ProfileError, load_profile
from profilegen.sources import http

SNAPSHOT_PATH = Path("data") / "snapshot.json"


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}, expected YYYY-MM-DD") from None


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = -1
    if number < 0:
        raise argparse.ArgumentTypeError(f"invalid day count {value!r}, expected a non-negative integer")
    return number


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default=argparse.SUPPRESS, help="profile data file (default: profile.yaml)")
    common.add_argument("--root", default=argparse.SUPPRESS, help="repository root (default: .)")

    parser = argparse.ArgumentParser(
        prog="profilegen",
        description="Render the GitHub profile README from profile.yaml plus live data.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p_render = sub.add_parser("render", parents=[common], help="regenerate README.md and data/snapshot.json")
    p_render.add_argument("--offline", action="store_true", help="do not fetch; render from the snapshot only")
    p_render.add_argument("--today", type=_iso_date, help="date for the footer (YYYY-MM-DD, default: UTC today)")
    p_render.add_argument("--output", help="write the README to PATH instead; the snapshot is not written")

    sub.add_parser("validate", parents=[common], help="validate the profile data file")

    p_scan = sub.add_parser("scan", parents=[common], help="collect facts for the curation skill")
    p_scan.add_argument("--json", action="store_true", help="emit the ScanReport as JSON")
    p_scan.add_argument("--roots", nargs="+", metavar="PATH", help="override settings.scan_roots")

    p_keepalive = sub.add_parser(
        "keepalive", parents=[common], help="exit 0 if the last commit on HEAD is old enough for a keep-alive commit"
    )
    p_keepalive.add_argument(
        "--days", type=_non_negative_int, default=keepalive.DEFAULT_DAYS, help="age threshold in days (default: 50)"
    )
    return parser


def _paths(args: argparse.Namespace) -> tuple[Path, Path]:
    root = Path(getattr(args, "root", "."))
    profile = Path(getattr(args, "profile", "profile.yaml"))
    return root, profile if profile.is_absolute() else root / profile


def _load(path: Path) -> Profile | None:
    """Load and validate the data file; print errors and return None if invalid."""
    try:
        return load_profile(path)
    except ProfileError as e:
        errors = e.errors
    actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for err in errors:
        if actions:
            print(f"::error::{err}")  # shows the cause in the run summary (FR-019a)
        print(f"ERROR: {err}", file=sys.stderr)
    return None


def _warn(messages: list[str]) -> None:
    actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for msg in messages:
        if actions:
            print(f"::warning::{msg}")
        else:
            print(f"WARNING: {msg}", file=sys.stderr)


def _cmd_render(args: argparse.Namespace) -> int:
    root, profile_path = _paths(args)
    profile = _load(profile_path)
    if profile is None:
        return 1
    snapshot_path = root / SNAPSHOT_PATH
    old = snapshot.load(snapshot_path)
    token = None if args.offline else http.resolve_token()
    new, warnings = render_mod.refresh(profile, old, args.offline, token)

    target = Path(args.output) if args.output else root / "README.md"
    existing = target.read_text(encoding="utf-8") if target.is_file() else None
    today = args.today or datetime.now(timezone.utc).date()
    readme = render_mod.render_readme(profile, new, existing, today, root)

    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(readme)
    if not args.output:
        snapshot.save(snapshot_path, new)
    _warn(warnings)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    _, profile_path = _paths(args)
    if _load(profile_path) is None:
        return 1
    print(f"{profile_path}: valid")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    _, profile_path = _paths(args)
    profile = _load(profile_path)
    if profile is None:
        return 1
    roots = args.roots or list(profile.settings.scan_roots)
    try:
        report = scan_mod.build_report(profile, roots, gh=scan_mod.GitHubAccess(http.resolve_token()))
    except (http.SourceError, http.NotFound, scan_mod.ScanError) as e:
        print(f"ERROR: cannot verify repository visibility ({e}); no proposals emitted", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(scan_mod.format_summary(report))
    return 0


def _cmd_keepalive(args: argparse.Namespace) -> int:
    root, _ = _paths(args)
    result = keepalive.check(root, args.days)
    print(result.message, file=sys.stderr if result.exit_code == keepalive.ERROR else sys.stdout)
    return result.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:  # argparse: 2 on usage errors, 0 for --help
        return e.code if isinstance(e.code, int) else 2
    if args.command == "render":
        return _cmd_render(args)
    if args.command == "scan":
        return _cmd_scan(args)
    if args.command == "keepalive":
        return _cmd_keepalive(args)
    return _cmd_validate(args)


if __name__ == "__main__":
    sys.exit(main())
