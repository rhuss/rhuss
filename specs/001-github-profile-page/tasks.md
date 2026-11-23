# Tasks: Generated GitHub Profile Page

**Input**: Design documents from `specs/001-github-profile-page/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. plan.md mandates test-first for parsers and rules, with all tests offline using fixtures in `tests/fixtures/`.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Create `pyproject.toml` (uv project, Python >=3.12, package `profilegen` under `src/`, deps `pyyaml`, `jinja2`, dev dep `pytest`, console script `profilegen = profilegen.cli:main`), run `uv lock` and commit `uv.lock`, create `src/profilegen/__init__.py`, `src/profilegen/sources/__init__.py`, and `.gitignore` (`.venv/`, `__pycache__/`, `.pytest_cache/`, `.mcp.json`)
- [X] T002 [P] Create `Makefile` with targets `test` (`uv run pytest -q`), `validate`, `render`, `preview` (`render --offline --output /tmp/profile-preview.md`)
- [X] T003 [P] Record offline fixtures in `tests/fixtures/`: `archive-readme.md` (copy of current `ro14nd-talks/archive` README, plus synthetic edge entries: empty year, unparseable line, entry without link), `feed.xml` (copy of `https://ro14nd.de/index.xml` trimmed to 5 items), `github/` JSON samples for `users/rhuss/repos`, `orgs/AgentTacho/repos`, `orgs/k8spatterns/repos`, single repos (public, private, fork, archived, renamed via differing `full_name`), and a 404 marker; plus `tests/fixtures/profile.yaml` (small valid profile covering every section, one book without cover, one badge label with a space and one with a `-`)

---

## Phase 2: Foundational

- [X] T004 [P] Write tests in `tests/test_text.py` for sentence counting (abbreviations `e.g.`, `i.e.`, `vs.`, `etc.`, `approx.` and version numbers like `v1.0`/`3.12` do not end sentences; `.`, `!`, `?` followed by whitespace or end do; trailing text without final punctuation counts as one sentence) and tagline checks ("single line with at most 120 characters")
- [X] T005 Implement `src/profilegen/text.py`: `count_sentences(text, abbreviations)`, `check_tagline(text, max_len=120)`
- [X] T006 [P] Write tests in `tests/test_validate.py` for profile validation: required fields; unknown top-level keys rejected; `intro` "single line, max 160 chars"; `main_projects` "1..12", description "1 to 3 sentences"; community `role` required and in enum `creator`, `co-creator`, `maintainer`, `contributor`, `lead`; taglines "one line" max 120; `repo` matches `owner/name`; a `repo` "appears at most once across `main_projects`, `community`, `more_tools`"; `settings.talks_shown` in "5..10"; `settings.demote_after_days`, `promote_commits`, `promote_window_days` positive integers; unknown `settings` keys rejected; book `description` single line; links include blog and LinkedIn; YAML syntax error reported with line number
- [X] T007 Implement `src/profilegen/model.py` (dataclasses Profile, Link, Badge, Project, Book, Settings with defaults from data-model.md; parsed-data dataclasses Talk, BlogPost, RepoInfo; `load_profile(path)` raising `ProfileError` with line number on YAML syntax errors) and `src/profilegen/validate.py` (`validate(profile_dict) -> list[str]` returning `<path>: <message>` errors)
- [X] T008 [P] Implement `src/profilegen/sources/http.py`: `get_json(url, token)` and `get_text(url)` via `urllib.request` with 20 s timeout, `Authorization: Bearer` when token set, `User-Agent: profilegen`, raising `SourceError` on network/HTTP errors, timeouts, and rate limits (403 with `X-RateLimit-Remaining: 0`, 429), and `NotFound` (subclass of nothing, distinct) only for 404; base URLs overridable via `PROFILEGEN_API_URL`, `PROFILEGEN_FEED_URL`; token from `GITHUB_TOKEN`, else `gh auth token` if available, else none. Tests in `tests/test_http.py` (stubbed `urlopen`) for 404, 403 rate limit, 429, timeout, and token precedence
- [X] T009 [P] Write tests in `tests/test_snapshot.py` and implement `src/profilegen/snapshot.py`: load (missing/unreadable file means empty), `merge(old, fetched: dict[str, object | SourceError])` replaces only keys whose fetch fully succeeded (a `SourceError` value keeps the old key), `dump` with `sort_keys=True, indent=2, ensure_ascii=False` plus trailing newline; assert no timestamp/status keys are ever written

**Checkpoint**: validation, text rules, HTTP, snapshot ready.

---

## Phase 3: User Story 1 - Visitor sees a current overview (P1) 🎯 MVP

**Goal**: `profilegen render` produces the full README from `profile.yaml` plus live data or snapshot.
**Independent Test**: With fixtures, rendering yields all sections in order with expected values (spec US1 scenarios 1 to 5).

### Tests (write first, must fail)

- [X] T010 [P] [US1] Tests in `tests/test_talks.py`: parse all entry shapes from research.md R2 (` - Venue, MM/YYYY`, `, Venue, MM/YYYY`, no separator, bold-only title, plain text, `| [Video](...)` extras); relative links resolve to `https://ro14nd-talks.github.io/archive/<path>`; one bullet counts as one talk; per-year counts cover every year first..last with zeros; ordering year desc, dated by month desc (ties: later archive position first), undated after dated in archive order; unparseable entry renders raw text as title; a README without any year heading yields an empty talk list and no chart (never an invalid chart)
- [X] T011 [P] [US1] Tests in `tests/test_blog.py`: RSS parsing returns newest 3 posts sorted by `pubDate` desc, date formatted `YYYY-MM-DD`; fewer than 3 items returns what exists; malformed XML or an item without `pubDate` raises `SourceError` (no crash)
- [X] T012 [P] [US1] Tests in `tests/test_github.py` (HTTP layer stubbed with fixtures): star total over public non-fork repos of `rhuss`, `AgentTacho`, `k8spatterns` plus `jolokia/jolokia` and `fabric8io/docker-maven-plugin`, archived included, forks and private excluded, Knative/JKube/OpenShell excluded; listed repo 404 or private is omitted with warning that names only the data-file entry path; renamed repo (different `full_name`) renders the new link and warns (display name: explicit `name` if set, else the new repo name); pagination followed via `Link` header; a rate-limit or network error on any single call makes the whole `repos`/`total_stars` fetch a `SourceError` so the snapshot keeps both keys unchanged
- [X] T013 [P] [US1] Tests in `tests/test_render.py` (structural assertions first; the golden file `tests/fixtures/expected-README.md` is generated and reviewed in T018, then asserted): render from `tests/fixtures/profile.yaml` with `today=2026-11-23`; section order header, stats, current focus, community, books, talks + `mermaid` `xychart-beta`, writing, more tools, footer; footer date kept when body unchanged and set to today when changed; two renders byte-identical; book without cover renders title as text link; failed source uses snapshot values; failed source without snapshot omits items and shows "currently unavailable"; validation error or YAML syntax error leaves README and snapshot untouched (exit 1); badge URLs escape spaces (`%20`) and dashes (`--`) in labels and omit unset `logo`/`logoColor` parameters; no prose in the output that is not from the profile (FR-015)

### Implementation

- [X] T014 [P] [US1] Implement `src/profilegen/sources/talks.py`: `parse_archive(markdown) -> list[Talk]`, `recent(talks, n)`, `per_year(talks) -> list[(year, count)]`, `fetch_archive(repo)` via `GET /repos/{repo}/readme` (raw media type)
- [X] T015 [P] [US1] Implement `src/profilegen/sources/blog.py`: `parse_feed(xml) -> list[BlogPost]`, `fetch_posts(url, n=3)`
- [X] T016 [P] [US1] Implement `src/profilegen/sources/github.py`: `list_owned(owners, extra_repos)` with pagination, `total_stars(repos)`, `resolve(repo) -> RepoInfo | Missing` handling 404/private/rename
- [X] T017 [US1] Create `templates/README.md.j2` per FR-001..FR-010: header (name, intro, links with emoji, shields.io badges `https://img.shields.io/badge/-<label>-<color>?style=flat-square&logo=<logo>&logoColor=<logo_color>`), stats strip (⭐ total, 🎤 talks, 📚 books), Current focus list (emoji, bold link, ⭐ count, description), Community (name, role, tagline, ⭐), Books (HTML table with two cover cells side by side, width 140), Talks (title link, venue, `Mon YYYY`/`YYYY`, extras) + Mermaid `xychart-beta` bar chart, Writing (3 posts with date), More tools (one line each), footer line `<sub>Last updated: YYYY-MM-DD · generated by profilegen</sub>`; star numbers above 999 formatted with one decimal and `k`
- [X] T018 [US1] Implement `src/profilegen/render.py` with interfaces `refresh(profile, snapshot, offline: bool) -> tuple[dict, list[str]]` (fetch each source, map `SourceError` to fallback via `snapshot.merge`, collect warnings) and `render_readme(profile, snapshot, existing_readme: str | None, today: date) -> str`; build view model from Profile + snapshot; render with Jinja2 (`keep_trailing_newline=True`, autoescape off, deterministic ordering); footer-date algorithm from research.md R6 (compare against existing README with footer normalized); write README and snapshot only after validation passes; generate `tests/fixtures/expected-README.md`, review it, and enable the golden assertion in `tests/test_render.py`
- [X] T019 [US1] Implement `src/profilegen/cli.py` with `render` (`--offline`, `--today`, `--output`) and `validate` per `contracts/cli.md`; exit codes 0/1/2; warnings as `::warning::` when `GITHUB_ACTIONS=true`, else `WARNING:` on stderr; plus `tests/test_cli.py` covering exit codes
- [X] T020 [US1] Create initial `profile.yaml` with real content: name, intro from GitHub bio, links (Blog https://ro14nd.de, LinkedIn https://www.linkedin.com/in/ro14nd/), badges (Kubernetes, Go, Java, Python, Claude Code, OpenShift), the eight main projects (`rhuss/cc-spex`, `AgentTacho/agenttacho` with url https://agenttacho.dev, `rhuss/cc-guide`, `rhuss/corgi`, `rhuss/debaser`, `rhuss/aprofile`, `rhuss/cc-review`, `rhuss/cc-prose`) with 1 to 3 sentence descriptions drawn from each repo's README, community (`NVIDIA/OpenShell` contributor, `knative/serving` maintainer, `jolokia/jolokia` creator, `fabric8io/docker-maven-plugin` creator, `eclipse-jkube/jkube` co-creator), books (Kubernetes Patterns https://k8spatterns.com with cover; Generative AI on Kubernetes with the publisher page link if one can be found on oreilly.com, otherwise `https://www.oreilly.com/search/?q=Generative%20AI%20on%20Kubernetes` with a `# TODO: replace with publisher page` comment, no cover), more tools (other public `cc-*` repos active in the last 12 months, one tagline each); mark in a top comment that all prose is a draft for Roland's review
- [X] T021 [US1] Add `assets/books/kubernetes-patterns.png` from the `k8spatterns/k8spatterns.com` repository static images (pick the cover image; if none is found, leave `cover` unset so the text-link fallback applies) and run `uv run profilegen render` to produce the first `README.md` and `data/snapshot.json`

**Checkpoint**: MVP: full README generated locally.

---

## Phase 4: User Story 2 - Nightly refresh (P2)

**Goal**: Scheduled workflow regenerates and commits only on change; keep-alive; push-triggered.
**Independent Test**: `workflow_dispatch` run succeeds; no commit when unchanged.

- [X] T022 [US2] Tests in `tests/test_keepalive.py`, logic in `src/profilegen/keepalive.py`, and the `keepalive` subcommand wired in `src/profilegen/cli.py`: exit 0 when last HEAD commit is at least `--days` (default 50) old, exit 3 otherwise, exit 1 on git error
- [X] T023 [US2] Create `.github/workflows/refresh.yml` named "Refresh profile": triggers `schedule` (`17 4 * * *`), `workflow_dispatch`, `push` on default branch with `paths: [profile.yaml, templates/**, assets/**]`; `permissions: contents: write`; `concurrency: {group: refresh, cancel-in-progress: false}`; steps: `actions/checkout@v4` (`fetch-depth: 0`), `astral-sh/setup-uv@v6`, `uv run --locked profilegen render` with `GITHUB_TOKEN`; commit `README.md data/snapshot.json` as `github-actions[bot]` only if `git diff --quiet -- README.md data/snapshot.json` fails; then (after the content commit step) `rc=0; uv run --locked profilegen keepalive --days 50 || rc=$?`, where 0 creates `git commit --allow-empty -m "chore: keep scheduled refresh alive"`, 3 skips, anything else fails the step; finally push only if local is ahead, with `git pull --rebase` and up to 3 retries

**Checkpoint**: automation ready (verifiable after pushing to `rhuss/rhuss`).

---

## Phase 5: User Story 3 - Local curation skill (P2)

**Goal**: `profilegen scan` provides facts; the skill turns them into reviewed edits and a confirmed push.
**Independent Test**: `scan --json` on fixtures yields expected proposals without non-public repos; skill instructions enforce accept/diff/confirm.

- [X] T024 [P] [US3] Tests in `tests/test_scan.py` (git and GitHub stubbed): candidates come from the GitHub owner listings (`settings.owned_owners`) plus local repos under roots (max depth 3) with GitHub remotes; maps remotes to `owner/name`; drops non-public and fork repos before output; commit counts include only commits authored by Roland (git `user.email` of the checkout, falling back to GitHub API commit counts for repos without a local checkout); proposals `demote` (main project, no commits in D=60 days), `promote` (not in main, at least N=10 commits in M=30 days), `remove` (listed entry not public or missing), `rename` (listed repo resolves to new `full_name`), `new_tool` (public, active in last 12 months, not listed); output matches ScanReport shape in data-model.md
- [X] T025 [US3] Implement `src/profilegen/scan.py` and the `scan` subcommand (`--json`, `--roots`) in `src/profilegen/cli.py`; refuse to emit proposals (exit 1) when visibility cannot be verified
- [X] T026 [US3] Write `skill/profile-curate/SKILL.md` (frontmatter `name: profile-curate`, description with trigger phrases): steps 1) locate the profile repo checkout (default `~/Work/priv/github-overview`, configurable), `git pull --rebase`; 2) `uv run profilegen scan --json`; 3) present proposals one at a time (accept/edit/reject), and on request offer to re-draft the text of any listed entry (FR-022 "changed" projects), drafting blurbs (max 3 sentences) and taglines (one line, max 120 chars) from each repo's README, never listing non-public repos; 4) apply accepted edits to `profile.yaml`; 5) `uv run profilegen validate` and `uv run profilegen render --offline --output` preview; 6) show full `git diff profile.yaml` in the reply; 7) re-run `uv run profilegen scan --json` and refuse to push while any listed repo is not public (SC-003); ask for explicit confirmation in plain text; 8) on yes: commit (`Assisted-By: 🤖 Claude Code`), `git pull --rebase`, `git push`; on no: leave remote unchanged. Writing rules: no em/en dashes, no "So I built" pivots
- [X] T027 [P] [US3] Write `skill/profile-curate/README.md`: how to install into `~/Development/context-engineering/personal-skills` (copy directory to the plugin's `skills/` dir), prerequisites (`uv`, `gh`), configuration of the profile repo path

**Checkpoint**: curation loop available.

---

## Phase 6: User Story 4 - Local preview (P3)

- [X] T028 [US4] Verify `profilegen render --output PATH` writes only to PATH (no README/snapshot change, no git operations) with a test in `tests/test_cli.py` (documentation of `make preview` happens in T029)

---

## Phase 7: Polish & Cross-Cutting

- [X] T029 [P] Write `CONTRIBUTING.md` describing the layout (`profile.yaml`, `templates/`, `data/snapshot.json`, `assets/`), commands (including `make preview`), and the workflow; keep `README.md` generated-only
- [X] T030 Run quickstart.md steps 1 to 6 locally (`uv run pytest -q`, `validate`, `render`, determinism check, source-failure fallback, `scan --json`) and fix any failures; list in `CONTRIBUTING.md` the manual post-push checks: workflow dispatch run (step 7), light/dark rendering on github.com (SC-007), timed curation run (SC-005)

---

## Dependencies & Execution Order

- Setup (T001 to T003) → Foundational (T004 to T009) → US1 (T010 to T021) → US2 (T022, T023) and US3 (T024 to T027) in either order → US4 (T028) → Polish (T029, T030).
- Within US1: tests T010 to T013 first; T014 to T016 parallel; T017 then T018, T019; T020 and T021 last.
- US2 and US3 depend only on Foundational + US1 CLI skeleton (T019).

## Parallel Examples

- Foundational: T004, T006, T008, T009 in parallel (different files).
- US1 tests: T010, T011, T012, T013 in parallel; then T014, T015, T016 in parallel.
- US3: T024 alongside T027.

## Implementation Strategy

MVP = Phases 1 to 3 (local render of the full page). Then the nightly workflow (US2), the curation skill (US3), preview polish (US4).
