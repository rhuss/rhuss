# Contract: `profilegen` CLI

Invoked as `uv run profilegen <command>` from the repository root. Global options: `--profile PATH` (default `profile.yaml`), `--root PATH` (default `.`).

Environment: `GITHUB_TOKEN` (API auth, optional locally), `PROFILEGEN_FEED_URL` and `PROFILEGEN_API_URL` (override source endpoints, used for failure tests), `GITHUB_ACTIONS` (switches warning format).

## `render`
Regenerate `README.md` and `data/snapshot.json`.

| Option | Meaning |
|--------|---------|
| `--offline` | Do not fetch; render from snapshot only |
| `--today YYYY-MM-DD` | Override the date used for the footer (tests) |
| `--output PATH` | Write README elsewhere (preview) |

Exit codes: `0` success (warnings allowed, printed as `::warning::` lines when `GITHUB_ACTIONS=true`, otherwise `WARNING:` on stderr); `1` data-file validation error (README and snapshot untouched); `2` usage error.

## `validate`
Validate `profile.yaml` (FR-024). Prints each problem as `ERROR: <path>: <message>` (e.g., `ERROR: main_projects[2].description: 4 sentences, max 3`). Exit `0` valid, `1` invalid.

## `scan`
Collect facts for the curation skill (FR-020 to FR-023a).

| Option | Meaning |
|--------|---------|
| `--json` | Emit ScanReport JSON (see data-model.md) on stdout |
| `--roots PATH...` | Override `settings.scan_roots` |

Never emits non-public repositories. Exit `0` on success, `1` on fatal errors (e.g., no network to check visibility: then it refuses to emit proposals rather than risk leaking).

## `keepalive`
`profilegen keepalive --days 50`: exit `0` if the last commit on HEAD is at least N days old (keep-alive needed), `3` if not needed, `1` on error.
