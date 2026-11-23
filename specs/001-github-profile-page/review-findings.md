# Deep Review Findings

**Date:** 2026-11-23
**Branch:** 001-github-profile-page
**Rounds:** 2 fix rounds (plus one pre-review spec compliance fix)
**Gate Outcome:** PASS
**Invocation:** quality-gate (ship pipeline, autonomous)

## Summary

| Severity | Found | Fixed | Remaining |
|----------|-------|-------|-----------|
| Critical | 0 | 0 | 0 |
| Important | 17 | 16 | 0 (1 dismissed as invalid) |
| Minor | 31 | 31 | 0 (18 resolved in the user-approved follow-up) |
| Notable | 9 | 1 | 8 (NOTABLE-7 resolved in the follow-up) |
| **Total** | **57** | **48** | **8** |

Counts are after deduplication. Codex P2 findings are counted as Important.

**Agents completed:** 5/5 internal (Goal Alignment skipped: no PR exists) + 2 external tools (CodeRabbit, Codex). Copilot: disabled in config.
**Agents failed:** none

Stage 1 spec compliance was 97.4% (37/38) before review; the one deviation (FR-021, a forked main project could never be proposed for demotion) was fixed in commit 446b117, giving 100%.

## Findings

### Important (all resolved)

#### FINDING-1: Workflow renders from a stale commit; a rebase conflict kills the push step silently
- **Severity:** Important
- **Confidence:** 80
- **File:** .github/workflows/refresh.yml:32-35, 75-93
- **Category:** correctness / production-readiness
- **Source:** correctness-agent (also reported by: production-readiness-agent)
- **Round found:** 1
- **Resolution:** fixed (round 1, commit 1c49421)

**What is wrong:** `actions/checkout` without `ref` pins the run to the trigger SHA, so a run queued behind another one renders from an outdated tree. Its generated commit then conflicts with the previous run's commit on `git pull --rebase`, and under `bash -e` the step dies on the first failed rebase without the `::error::` annotation.

**Why this matters:** Two quick data-file pushes (or a push during the nightly run) leave the README stale until the next night and a red run with no clear cause (FR-016, FR-017, US2 AS4).

**How it was resolved:** Checkout now uses `ref: ${{ github.ref_name }}` (branch tip, valid for schedule, dispatch and push events). A failing `git pull --rebase` aborts the rebase and fails with `::error::rebase onto the remote conflicted ...`. Concurrency moved to job level (see FINDING-27). A new test file executes the commit, keep-alive and push steps against a local bare remote, including the rejected-push and conflict paths.

#### FINDING-2: Actions pinned to mutable tags in a job with a write token
- **Severity:** Important
- **Confidence:** 75
- **File:** .github/workflows/refresh.yml:18-19, 32-38
- **Category:** security
- **Source:** security-agent
- **Round found:** 1
- **Resolution:** fixed (round 1, commit 1c49421)

**What is wrong:** `actions/checkout@v4` and `astral-sh/setup-uv@v6` were referenced by tag in a job with `contents: write`.

**Why this matters:** A retagged or compromised action could push to the public profile repository.

**How it was resolved:** Both are pinned to commit SHAs (`checkout` v4.4.0, `setup-uv` v6.8.0, verified with `gh api`), and a test asserts every `uses:` is a 40-character SHA.

#### FINDING-3: `profilegen scan` crashes with a traceback on a 404 owner listing
- **Severity:** Important
- **Confidence:** 90
- **File:** src/profilegen/sources/github.py:57-59, src/profilegen/cli.py:148-152
- **Category:** test-quality (code bug confirmed by probe)
- **Source:** test-quality-agent
- **Round found:** 1
- **Resolution:** fixed (round 1, commit 0cb2631)

**What is wrong:** `NotFound` is deliberately not a `SourceError`; `list_owned` did not convert it for owner listings, and the CLI caught only `SourceError`.

**Why this matters:** A renamed account or typo in `owned_owners` printed a traceback instead of the contract's clean "no proposals emitted" exit 1.

**How it was resolved:** Owner-listing 404 is now a `SourceError` (status 404); the CLI also catches `NotFound`. Parametrized CLI test covers listing 404 and commits 404.

#### FINDING-4: Refresh `NotFound` handling untested for GitHub and blog
- **Severity:** Important
- **Confidence:** 85
- **File:** tests/test_render.py
- **Category:** test-quality
- **Source:** test-quality-agent
- **Round found:** 1
- **Resolution:** fixed (round 1)

**What is wrong:** Mutating `except (SourceError, NotFound)` to `except SourceError` for two sources survived the suite.

**Why this matters:** A regression would fail the nightly job instead of warning (FR-019a).

**How it was resolved:** A test parametrized over all three sources times `SourceError`/`NotFound` asserts kept snapshot keys and the exact warning.

#### FINDING-5: Promote threshold boundary untested
- **Severity:** Important
- **Confidence:** 85
- **File:** tests/test_scan.py
- **Category:** test-quality
- **Source:** test-quality-agent
- **Round found:** 1
- **Resolution:** fixed (round 1)

**What is wrong:** `>=` to `>` on the promote check survived.

**Why this matters:** US3 AS5 says "at least 10 commits".

**How it was resolved:** `test_promote_threshold_is_inclusive` checks exactly-N promotes and N+1 does not.

#### FINDING-6: Workflow shell logic only checked as strings
- **Severity:** Important
- **Confidence:** 75
- **File:** tests/test_workflow.py
- **Category:** test-quality
- **Source:** test-quality-agent
- **Round found:** 1
- **Resolution:** fixed (round 1, tests/test_workflow_scripts.py)

**What is wrong:** US2 AS1, AS2, AS5 and FR-017 were verified by grepping `refresh.yml`.

**How it was resolved:** The `run:` blocks are extracted and executed with `bash -eo pipefail` in a clone of a local bare remote (stubbed `uv` and `sleep`): unchanged output, changed README, snapshot-only change, untracked snapshot on a first run, keep-alive needed, keep-alive error, rejected push with rebase, rebase conflict.

#### FINDING-7: Malformed source data paths untested
- **Severity:** Important
- **Confidence:** 80
- **File:** tests/test_blog.py, tests/test_github.py, tests/test_http.py, tests/test_scan.py
- **Category:** test-quality
- **Source:** test-quality-agent
- **Round found:** 1
- **Resolution:** fixed (round 1)

**What is wrong:** Seven guards (blog title/link, bad pubDate, repo data validation, `html_url` fallback, commit data, connection errors, `MAX_PAGES`) could be removed without a test failing.

**How it was resolved:** Focused tests for each path.

#### FINDING-8: SKILL.md commit could include unrelated staged files
- **Severity:** Important (CodeRabbit major)
- **Confidence:** 75
- **File:** skill/profile-curate/SKILL.md:117
- **Category:** external
- **Source:** coderabbit
- **Round found:** 1
- **Resolution:** fixed (round 1)

**How it was resolved:** `git commit -m ... -- profile.yaml`, with a rule never to drop the pathspec.

**External tool analysis (CodeRabbit):**
> Step 1 permits the user to continue with a dirty checkout. If another file is already staged, `git commit` includes it and `git push` publishes it, despite the instruction to stage only `profile.yaml`.

#### FINDING-9: SKILL.md review diff omitted staged changes
- **Severity:** Important (CodeRabbit major)
- **Confidence:** 75
- **File:** skill/profile-curate/SKILL.md:92
- **Category:** external
- **Source:** coderabbit
- **Round found:** 1
- **Resolution:** fixed (round 1): `git diff HEAD -- profile.yaml`

**External tool analysis (CodeRabbit):**
> If `profile.yaml` already has staged changes, `git diff profile.yaml` omits them. A later accepted edit makes this diff nonempty, and `git add` commits both sets of changes.

#### FINDING-10: Missing `private` flag treated as public
- **Severity:** Important (CodeRabbit major)
- **Confidence:** 75
- **File:** src/profilegen/sources/github.py:43
- **Category:** external / security
- **Source:** coderabbit
- **Round found:** 1
- **Resolution:** fixed (round 1): `private` must be a bool, else `SourceError`; tests added.

**External tool analysis (CodeRabbit):**
> A response such as `{"full_name":"owner/hidden","stargazers_count":1}` passes the existing checks. This default marks the repository public even though the response did not establish its visibility.

#### FINDING-11: Partial GitHub failure restored repositories already confirmed non-public
- **Severity:** Important (CodeRabbit major)
- **Confidence:** 75
- **File:** src/profilegen/render.py:65-73
- **Category:** external / security
- **Source:** coderabbit (related: security-agent NOTABLE on FR-019 vs FR-011)
- **Round found:** 1
- **Resolution:** fixed (round 1)

**How it was resolved:** `fetch_repos` reports entries confirmed missing before a failure via a `missing` set; refresh drops them from the fallback snapshot. Tests in test_github.py and test_render.py.

**External tool analysis (CodeRabbit):**
> If A is now private, `fetch_repos` omits A. If resolving B then raises `SourceError`, this assignment discards that omission. `snapshot.merge` restores cached A, and `_project_view` renders A again.

#### FINDING-12: Scan treated a commits 404 as "no activity" for a repo already reported public
- **Severity:** Important (CodeRabbit major)
- **Confidence:** 75
- **File:** src/profilegen/scan.py:92-93
- **Category:** external / security
- **Source:** coderabbit
- **Round found:** 1
- **Resolution:** fixed (round 1): raises `SourceError`, so the CLI refuses to emit a report; 409 (empty repo) unchanged.

#### FINDING-13: `posts_shown` not validated (Codex P2)
- **Severity:** Important (Codex P2)
- **File:** src/profilegen/validate.py:38-39
- **Source:** codex
- **Resolution:** dismissed: `posts_shown` is already in `POSITIVE_INT_SETTINGS` (validate.py:38). A negative test was added anyway (`test_more_invalid_settings`).

#### FINDING-14: https URLs without a host accepted (Codex P2)
- **Severity:** Important (Codex P2)
- **File:** src/profilegen/validate.py:84-86
- **Source:** codex
- **Resolution:** fixed (round 1; hardened in round 2 against unparseable URLs, FINDING-17).

#### FINDING-15: LinkedIn link matched by substring (Codex P2)
- **Severity:** Important (Codex P2)
- **File:** src/profilegen/validate.py:159
- **Source:** codex
- **Resolution:** fixed (round 1): matched by hostname; test added.

#### FINDING-16: Bearer token could follow cross-host pagination links or redirects
- **Severity:** Important (Codex P2; security-agent rated Minor)
- **File:** src/profilegen/sources/http.py:116-128, 204
- **Category:** security
- **Source:** codex (also reported by: security-agent)
- **Round found:** 1
- **Resolution:** fixed (round 1)

**How it was resolved:** Pagination links to another scheme or host raise `SourceError`. A redirect handler drops `Authorization` when a redirect leaves the host or downgrades to http (same-host 301s for renamed repositories keep the token). Tests added.

#### FINDING-17: Empty project section published without the "currently unavailable" note after a partial failure
- **Severity:** Important
- **Confidence:** 72
- **File:** src/profilegen/render.py:193-198, templates/README.md.j2
- **Category:** correctness (regression from round 1)
- **Source:** round-2 re-review agent
- **Round found:** 2
- **Resolution:** fixed (round 2, commit e6f28d0)

**What is wrong:** Round 1 gated the note on `"repos" not in snap`. GitHub values fall back per entry, so a section whose entries all lack values could render empty.

**How it was resolved:** Project sections show the note whenever they would be empty again; talks and posts (all-or-nothing sources) keep the source-level check. Regression test added.

### Minor, resolved

| ID | File | Finding | Source | Round |
|----|------|---------|--------|-------|
| FINDING-18 | src/profilegen/scan.py:204-215, 314-327 | Local `git log --all` commits credited to every remote, so upstream repos (for example `ai-openshell/sdk-go`, confirmed by a real scan) got promote proposals | correctness | 1 |
| FINDING-19 | src/profilegen/scan.py:380-392 | `new_tool` noise: org infra repos, profile repo | correctness | 1 |
| FINDING-20 | src/profilegen/scan.py:382-392 | Same repo proposed as both promote and new_tool | correctness | 1 |
| FINDING-21 | templates/README.md.j2, render.py | "Currently unavailable" shown for a successful but empty talks archive or feed (edge case "show what exists, without placeholders") | correctness, architecture | 1 |
| FINDING-22 | src/profilegen/model.py:74 | Abbreviation default duplicated in model and text | architecture | 1 |
| FINDING-23 | src/profilegen/cli.py:96-97 | Validation errors not surfaced as `::error::` annotations in Actions | production-readiness | 1 |
| FINDING-24 | src/profilegen/sources/blog.py:37-38 | Well-formed non-RSS document returned an empty post list | coderabbit | 1 |
| FINDING-25 | tests/test_validate.py | Missing negative tests for several settings | test-quality | 1 |
| FINDING-26 | tests/test_render.py | `posts_shown` cap untested (render side fixed; refresh `n` pass-through still untested) | test-quality | 1 |
| FINDING-27 | .github/workflows/refresh.yml:12-28 | Workflow-level concurrency let a skipped other-branch run replace a pending default-branch run | production-readiness | 1 |
| FINDING-28 | src/profilegen/scan.py:392-406 | Profile repo still eligible for promote | round-2 re-review | 2 |
| FINDING-29 | src/profilegen/validate.py:84-86 | `urlparse` ValueError on `https://[x` crashed validation | round-2 re-review | 2 |
| FINDING-30 | src/profilegen/sources/talks.py:63-75 | Unparseable link target in the live archive (`https://[x`) raised `ValueError` and aborted the job instead of the FR-019 fallback | round-2 re-review | 2 (fixed after gate) |

### Minor, resolved in the user-approved follow-up

These were open after the gate. Roland decided the ambiguous ones (FINDING-32, FINDING-47, FINDING-48) and asked for all of them to be fixed. Details are in REVIEW-CODE.md, section "Follow-up Fixes (user-approved)".

| ID | File:line (at review time) | Finding | Resolution |
|----|-----------|---------|------------|
| FINDING-31 | src/profilegen/sources/talks.py:128-132 | Bare year inside a venue name stripped ("JayDay 2013, Munich" rendered "JayDay, Munich"). | resolved (3a76008): only a year that is its own comma-separated field is stripped. |
| FINDING-32 | src/profilegen/render.py:155-161, 199; talks.py:63-75 | External text unescaped, any URL scheme kept. | resolved (aa1497a): Markdown escaping and an http/https allowlist; non-http targets render as plain text (new FR-019b). |
| FINDING-33 | src/profilegen/render.py:96-103 | One warning per entry on a first-run GitHub failure. | resolved (dd69f33): one warning per source listing the omitted entry paths. |
| FINDING-34 | src/profilegen/cli.py:86-98 vs model.py:211-220 | `cli._load` duplicated `load_profile`. | resolved (827570c): `_load` calls `load_profile`. |
| FINDING-35 | src/profilegen/model.py:50-52 | `Project.display_name` unused. | resolved (827570c): removed. |
| FINDING-36 | src/profilegen/sources/github.py:17 (+ scan, render, validate) | Group names defined in the GitHub source and repeated in validate. | resolved (827570c): `PROJECT_SECTIONS` in model.py, imported everywhere. |
| FINDING-37 | src/profilegen/sources/github.py:20-25; scan.py:176 | `Missing.entry/reason` and `Checkout.path` never read. | resolved (827570c): `Missing.entry` used in the warning; `reason` and `Checkout.path` removed (the warning deliberately does not say whether a repository is private or gone). |
| FINDING-38 | src/profilegen/render.py:69-93; snapshot.py:40-43 | Exceptions stored as dict values, triplicated NotFound conversion, redundant `_failed`. | resolved (dd69f33): `fetched` holds only successful values; one `_attempt` helper; `_failed` removed. |
| FINDING-39 | src/profilegen/sources/http.py:3 and other module docstrings, refresh.yml:2 | Docstrings cited plan.md/research.md. | resolved (827570c): spec requirement IDs only. |
| FINDING-40 | src/profilegen/scan.py:74-105 | `commit_times` was a second GitHub client. | resolved (827570c): moved to sources/github.py; `GitHubAccess` delegates. |
| FINDING-41 | src/profilegen/validate.py:88-93; text.py:41 | 120 duplicated; "no limit" emulated. | resolved (827570c): `TAGLINE_MAX` in text.py, `max_len: int | None`. |
| FINDING-42 | src/profilegen/scan.py:46, 67; keepalive.py:24, 37 | `_now()` and seconds per day duplicated. | resolved (827570c): `profilegen.clock`. |
| FINDING-43 | src/profilegen/cli.py:1-9 | Exit codes incomplete in the docstring. | resolved (827570c): codes per subcommand. |
| FINDING-44 | tests/test_scan.py, test_talks.py, test_snapshot.py | Four uncovered branches. | resolved (827570c): four focused tests. |
| FINDING-45 | tests/test_cli.py:54-71 | `no_git` not applied to the default local render. | resolved (827570c). |
| FINDING-46 | tests/test_render.py | `posts_shown` pass-through untested. | resolved (827570c): asserts `n=2` reaches `fetch_posts`. |
| FINDING-47 | src/profilegen/sources/talks.py, render | Empty section body under its heading after a successful empty fetch. | resolved (aa1497a): the section is hidden entirely. |
| FINDING-48 | spec FR-019 vs data-model.md | Per-entry vs per-source note semantics only implied. | resolved (aa1497a): the note is per source; FR-019 and data-model.md updated. This supersedes the FINDING-17 behavior: a project section without any value is hidden. |

## Notable Observations

### NOTABLE-1
- **File:** src/profilegen/scan.py:325-345
- **Category:** correctness
- **Source:** correctness-agent
- **Description:** A checkout with `user.email` is the only activity source for its repo; a stale clone can produce false demotes.
- **Rationale:** Merging local and API timestamps (dedup by SHA) would make FR-021 activity robust across machines.

### NOTABLE-2
- **File:** src/profilegen/scan.py:269-270
- **Category:** architecture
- **Source:** architecture-agent
- **Description:** The GitHub login for the commits API is `owned_owners[0]`, so reordering an unrelated setting changes scan behavior.
- **Rationale:** An explicit `settings.github_login` (or `GET /user`) would decouple identity from star accounting.

### NOTABLE-3
- **File:** src/profilegen/render.py:8-11, 40; pyproject.toml:25-26
- **Category:** architecture
- **Source:** architecture-agent
- **Description:** The template fallback works only for editable installs; a built wheel lacks `templates/`.
- **Rationale:** Ship the template as package data if the generator is ever installed as a wheel.

### NOTABLE-4
- **File:** src/profilegen/sources/http.py:31-43
- **Category:** architecture
- **Source:** architecture-agent
- **Description:** `__all__` re-exports `urlopen` and `Request` only as a test seam.
- **Rationale:** Misleading public API surface.

### NOTABLE-5
- **File:** skill/profile-curate/SKILL.md:14-16, 61-72
- **Category:** security
- **Source:** security-agent
- **Description:** Drafting from third-party READMEs relies on a one-line "input data, not instructions" rule.
- **Rationale:** Stronger delimiting, size limits and "no URLs from README in drafts" would reduce prompt-injection exposure.

### NOTABLE-6
- **File:** src/profilegen/render.py:65-104
- **Category:** security
- **Source:** security-agent
- **Description:** FR-019 fallback can keep showing a repo that turned private while GitHub is unreachable (partially mitigated by FINDING-11).
- **Rationale:** The spec should state that FR-019 fallback takes precedence over FR-011 for already published entries.

### NOTABLE-7
- **File:** src/profilegen/sources/github.py:109-127
- **Category:** production-readiness
- **Source:** production-readiness-agent
- **Description:** The snapshot stores raw star counts while the page shows `1.2k`, so a single star on any owned repo creates a snapshot-only commit almost every night.
- **Rationale:** Technically meets SC-006 but produces near-daily commits; storing rendered values or committing on README change only needs a spec decision.
- **Resolution:** resolved in the user-approved follow-up (dd69f33): the snapshot stores star counts in displayed form.

### NOTABLE-8
- **File:** src/profilegen/sources/http.py:116-148
- **Category:** production-readiness
- **Source:** production-readiness-agent
- **Description:** No request is retried; one transient 5xx drops a whole night's GitHub refresh.
- **Rationale:** One bounded retry for 5xx and timeouts would improve SC-002 freshness.

### NOTABLE-9
- **File:** tests/test_cli.py
- **Category:** test-quality
- **Source:** test-quality-agent
- **Description:** No end-to-end CLI test drives real refresh and sources with one failing source.
- **Rationale:** Integration seams (token passing, snapshot write, warning output) are only verified piecewise.

## Goal Alignment

Skipped: no PR exists for this branch (no git remote yet).

## Post-Fix Spec Coverage

Fix rounds removed or narrowed code in scan.py (new_tool scope, origin-only crediting), render.py/template (availability flags) and http.py (urlopen replacement). Coverage re-checked:

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| FR-001..FR-009 | templates/README.md.j2, render.py `_view` | ✓ |
| FR-010 | render.py `render_readme` (README re-renders byte-identically) | ✓ |
| FR-011 | github.py `resolve`/`fetch_repos`, render.py confirmed-missing filter | ✓ |
| FR-012 | github.py `total_stars` | ✓ |
| FR-013 | talks.py `parse_archive`, `recent`, `per_year` | ✓ |
| FR-014 | validate.py `_validate_cover`, render.py cover check | ✓ |
| FR-015 | render.py (prose only from profile) | ✓ |
| FR-016, FR-016a, FR-017, FR-018 | refresh.yml, keepalive.py | ✓ |
| FR-019, FR-019a | render.py `refresh`, snapshot.py `merge`, cli.py `_warn`/`_load` | ✓ |
| FR-020..FR-023a | scan.py `build_report` (demote, promote, remove, rename, new_tool) | ✓ |
| FR-024 | validate.py, text.py | ✓ |
| FR-025 | skill/profile-curate/SKILL.md steps 6-8 | ✓ |
| FR-026 | cli.py `render --output` / local render | ✓ |

All spec requirements verified after the fix loop.

## Test Suite Results

| Round | Test Command | Exit Code | Failures | Status |
|-------|-------------|-----------|----------|--------|
| pre-review | uv run pytest -q | 0 | 0 | passed (465) |
| 1 | uv run pytest -q | 0 | 0 | passed (521) |
| 2 | uv run pytest -q | 0 | 0 | passed (525) |
| post-gate Minor fix | uv run pytest -q | 0 | 0 | passed (526) |
| user-approved follow-up | uv run pytest -q | 0 | 0 | passed (558) |

Test suite passed in all fix rounds.
