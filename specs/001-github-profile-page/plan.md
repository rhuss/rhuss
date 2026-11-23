# Implementation Plan: Generated GitHub Profile Page

**Branch**: `001-github-profile-page` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-github-profile-page/spec.md`

## Summary

Build a small Python package, `profilegen`, that turns a curated YAML data file (`profile.yaml`) plus live data (GitHub repository metadata, the ro14nd.de RSS feed, the `ro14nd-talks/archive` README) into the profile `README.md`. Live values are cached in a committed JSON snapshot (`data/snapshot.json`) that doubles as the fallback when a source fails. A GitHub Actions workflow runs the generator nightly, on manual dispatch, and on pushes that change `profile.yaml`, commits only on real changes, and creates a keep-alive commit after 50 quiet days. A Claude Code skill (`skill/profile-curate/`) drives local curation: it calls `profilegen scan` to collect activity and visibility facts, drafts proposals, applies only accepted ones to `profile.yaml`, validates, shows the diff, rebases, and pushes on confirmation.

## Technical Context

**Language/Version**: Python 3.12+ (runs on GitHub's `ubuntu-latest` and locally via `uv`)

**Primary Dependencies**: PyYAML (data file), Jinja2 (README template). Standard library for HTTP (`urllib.request`), RSS (`xml.etree.ElementTree`), JSON, dates. No GitHub SDK.

**Storage**: Files in the repository: `profile.yaml` (curated), `data/snapshot.json` (live cache), `assets/books/*` (covers), `README.md` (output).

**Testing**: pytest with recorded fixtures (archive README, RSS feed, GitHub API JSON); all generator tests run offline.

**Target Platform**: GitHub Actions `ubuntu-latest` for the nightly job; macOS for local preview and the skill.

**Project Type**: CLI tool + scheduled workflow + Claude Code skill.

**Performance Goals**: A full refresh finishes in under 1 minute; roughly 10 to 40 GitHub API calls per run.

**Constraints**: No secrets beyond `GITHUB_TOKEN`; deterministic, byte-identical output for identical inputs; output must render on GitHub (Markdown, inline HTML subset, Mermaid).

**Scale/Scope**: About 30 to 60 repositories, about 100 talks, 3 posts, 2 books.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is still the unfilled template, so there are no project-specific gates. Applied defaults: keep it simple (single package, two runtime dependencies), test-first for parsers and rules (star total, sentence counting, talk ordering, footer date), no network in tests. **Result: PASS** (pre- and post-design).

## Global Constraints

- Only `GITHUB_TOKEN` in CI (FR-018); no other secrets.
- Identical inputs produce byte-identical README and snapshot (FR-010, SC-006).
- No non-public repository name in output, snapshot, warnings, or scan results (FR-011, FR-023, SC-003).
- No prose generated outside `profile.yaml` (FR-015).
- Tests never touch the network.

## Review Focus

- HTTP error classification: rate limits and timeouts are `SourceError`, only 404 is `NotFound`.
- Partial-failure fallback: a source either fully succeeds or keeps its snapshot key.
- Malformed inputs (YAML syntax, feed XML, archive without years) never crash or publish broken output.
- Sentence counter edge cases (abbreviations, versions, missing final punctuation).
- Workflow exit-code handling for `keepalive` and commit-on-change scoping.

## Project Structure

### Documentation (this feature)

```text
specs/001-github-profile-page/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── cli.md
│   ├── profile-yaml.md
│   └── snapshot-json.md
└── tasks.md
```

### Source Code (repository root)

```text
profile.yaml                    # curated data file (source of truth for prose)
data/snapshot.json              # committed live-data snapshot (fallback cache)
assets/books/                   # static book covers
templates/README.md.j2          # README template
README.md                       # generated output

src/profilegen/
├── __init__.py
├── cli.py                      # argparse entry point: render, validate, scan, keepalive
├── model.py                    # dataclasses + loading of profile.yaml
├── validate.py                 # data-file validation (FR-024)
├── text.py                     # sentence counting, tagline checks
├── sources/
│   ├── http.py                 # tiny urllib wrapper (token, timeout, errors)
│   ├── github.py               # repo metadata, owner listings, star total (FR-011, FR-012)
│   ├── blog.py                 # RSS parsing (FR-008)
│   └── talks.py                # archive README parsing, ordering, per-year counts (FR-007, FR-013)
├── snapshot.py                 # load/merge/save snapshot, fallback logic (FR-019)
├── keepalive.py                # last-commit age check (FR-016a)
├── render.py                   # build view model, Jinja render, footer date (FR-001..FR-010)
└── scan.py                     # local + GitHub activity scan for the skill (FR-020..FR-023a)

tests/
├── fixtures/                   # archive README, RSS, GitHub API JSON samples
├── test_text.py
├── test_validate.py
├── test_talks.py
├── test_blog.py
├── test_github.py
├── test_snapshot.py
├── test_render.py
├── test_scan.py
└── test_cli.py

.github/workflows/refresh.yml   # nightly + dispatch + push(profile.yaml); keep-alive; commit-on-change

skill/profile-curate/
├── SKILL.md                    # curation workflow for Claude Code
└── README.md                   # how to install into personal-skills

pyproject.toml                  # uv-managed project, console script `profilegen`
Makefile                        # test, render, preview targets
```

**Structure Decision**: Single Python package under `src/` with a thin CLI. The workflow and the skill both call the same CLI, so validation and rendering rules live in one place. The skill lives in this repository for review and testing; installing it into `~/Development/context-engineering/personal-skills` is a documented copy step.

## Phase Notes

- **Phase 0** decisions are in [research.md](research.md): language, archive parsing tolerance, link resolution, star-total algorithm, Mermaid chart, footer date algorithm, workflow triggers and keep-alive, skill/CLI split.
- **Phase 1** artifacts: [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md).

## Complexity Tracking

No constitution violations to justify.
