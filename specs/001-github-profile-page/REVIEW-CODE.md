# Code Review: Generated GitHub Profile Page

**Spec:** specs/001-github-profile-page/spec.md
**Date:** 2026-11-23
**Reviewer:** Claude (speckit-spex-gates-review-code, autonomous ship pipeline)
**Branch:** 001-github-profile-page (base `main`)

## Compliance Summary

**Overall Score: 100%** (97.4% before the Stage 1 fix)

- Functional requirements: 29/29 (FR-001 to FR-026 including FR-016a, FR-019a, FR-023a)
- Edge cases: 9/9
- Spec-declared constants: none (the spec has no `## Constants` section)

### Deviations found in Stage 1

| Requirement | Deviation | Resolution |
|-------------|-----------|------------|
| FR-021, US3 AS1 | `scan` dropped every fork before building proposals, including listed main projects. `rhuss/corgi` is a fork, so it could never be proposed for demotion. | Fixed in 446b117: unlisted forks are still dropped, listed forks stay. Test `test_listed_fork_main_project_can_still_be_demoted`. |

Edge-case interpretation (not counted as a deviation): "the blog feed has fewer than three posts: show what exists, without placeholders" now also holds for zero posts and for an archive with year headings but no talks (FINDING-21 in review-findings.md).

## Code Review Guide

Where to look when reviewing this feature:

| Area | Files | What to check |
|------|-------|---------------|
| Page rendering | src/profilegen/render.py, templates/README.md.j2 | Section order (FR-001), footer date logic (FR-010), "currently unavailable" note semantics (FR-019) |
| Live sources | src/profilegen/sources/{github,talks,blog,http}.py | Total-star rule (FR-012), talk ordering (FR-013), error classification (404 vs SourceError), token never leaves the API host |
| Snapshot | src/profilegen/snapshot.py | Only rendered values, per-source fallback, confirmed removals not restored |
| Validation | src/profilegen/validate.py, text.py | FR-024 sentence and tagline rules, URL host checks |
| Nightly job | .github/workflows/refresh.yml, src/profilegen/keepalive.py | Branch-tip checkout, pinned actions, commit-only-on-change, keep-alive, guarded rebase retry |
| Curation | src/profilegen/scan.py, skill/profile-curate/SKILL.md | Privacy (FR-023), proposal rules (FR-021, FR-023a), diff and confirm before push (FR-025) |
| Tests | tests/ (526 tests), tests/test_workflow_scripts.py | Workflow steps run against a local bare remote |

## Deep Review Report

**Gate: PASS** (after fix round 2)

### Review agents

| Agent                   | Found | Fixed | Remaining | Status |
|-------------------------|-------|-------|-----------|--------|
| Correctness             |     7 |     5 |         1 (+1 Notable) | completed |
| Architecture & Idioms   |    15 |     2 |        10 (+3 Notable) | completed |
| Security                |     5 |     2 |         1 (+2 Notable) | completed |
| Production Readiness    |     6 |     3 |         1 (+2 Notable) | completed |
| Test Quality            |    10 |     7 |         3 (+1 Notable) | completed |
| Goal Alignment          |     0 |     0 |         0 | skipped (no PR) |
| Re-review (rounds 1, 2) |     4 |     4 |         0 | completed |
| CodeRabbit (external)   |     6 |     6 |         0 | completed (3 runs: full branch, round 1, round 2) |
| Copilot (external)      |     - |     - |         - | skipped (disabled in config) |
| Codex (external)        |     4 |     3 |         0 (1 dismissed as invalid) | completed |
| Test Suite (regression) |     0 |     0 |         0 | passed in every round |

Counts are per source before deduplication; review-findings.md has the merged list (57 findings: 17 Important, 31 Minor, 9 Notable).

MVP: Architecture & Idioms (15 findings)

### Key fixes applied

1. Workflow checks out the branch tip, pins actions to SHAs, uses job-level concurrency, and handles rebase conflicts with an `::error::` (correctness, production, security)
2. Visibility safety: repository data must state `private`; confirmed removals are not restored on partial GitHub failure; a commits 404 stops the scan (CodeRabbit)
3. The bearer token never follows cross-host pagination links or redirects (Codex, security)
4. `scan` no longer crashes on a 404 owner listing (test quality)
5. Scan proposal noise: commits credited to the origin remote only, one proposal per repo, no profile-repo or org-infra `new_tool` proposals (correctness, confirmed against a real scan)
6. "Currently unavailable" note only on real source failures for talks and posts; project sections keep it when empty (correctness, architecture, re-review)
7. Validation: https URLs need a host, LinkedIn matched by hostname, unparseable URLs are errors not tracebacks (Codex, re-review)
8. SKILL.md: diff against HEAD and commit only `profile.yaml` (CodeRabbit)
9. Workflow step scripts executed in tests, plus tests for NotFound per source, promote boundary, and malformed data (test quality)

### Remaining findings

No Critical or Important findings remain. 18 Minor and 9 Notable items are listed in review-findings.md; the Minors are mostly architecture cleanups (duplicated helpers, dead fields, docstrings citing plan.md/research.md) and a few test gaps.

### Post-fix spec coverage

29/29 functional requirements verified after the fix loop (table in review-findings.md). README.md re-renders byte-identically from the committed snapshot.

## Next Steps

Code review complete. To close out this feature:

1. `/speckit-spex-walkthrough` (try the feature with a runbook)
2. `/clear` (free context for the final gate)
3. `/speckit-spex-finish` (verify and merge or PR, all-in-one)

## Follow-up Fixes (user-approved)

After the review, Roland approved the open design decisions and asked for every remaining unambiguous Minor finding to be fixed. All 18 remaining Minor findings and NOTABLE-7 are resolved; review-findings.md marks each one.

### Design decisions

1. **Snapshot noise (NOTABLE-7):** `data/snapshot.json` stores star counts per repository and in total in the rounded form the README shows (`"1.2k"`). A star change that does not change the page leaves README and snapshot byte-identical (CLI test). Older snapshots with integer counts render the same. contracts/snapshot-json.md and data-model.md updated. Commit dd69f33.
2. **External text (FINDING-32, new FR-019b):** feed and archive titles, venues and link labels are Markdown-escaped (inline characters escaped, leading block markers neutralized, whitespace collapsed). Links from these sources render only for absolute http(s) URLs with a host; parentheses, angle brackets and whitespace are percent-encoded. Any other target renders as plain text. Commit aa1497a.
3. **Empty sections (FINDING-47):** a section whose source succeeded with nothing to show is hidden entirely: empty feed, archive without talks (heading and chart), and project groups without any entry that has a value. Commit aa1497a.
4. **"Currently unavailable" note (FINDING-48):** one note per section, only when the section's source has no value at all. FR-019 now says so, and data-model.md describes the section states. This replaces the round-2 FINDING-17 behavior: a project section without any value is now hidden instead of showing the note. Commit aa1497a.

### Remaining Minor findings

- FINDING-31: a bare venue year is stripped only when it is its own comma-separated field ("JayDay 2013, Munich" is kept). Commit 3a76008.
- FINDING-33: a failed GitHub fetch gives one warning that lists the omitted entries by data-file path. Commit dd69f33.
- FINDING-34 to FINDING-37: `cli._load` calls `load_profile`; `Project.display_name`, `Missing.reason` and `Checkout.path` removed; `PROJECT_SECTIONS` defined once in model.py. Commit 827570c.
- FINDING-38: refresh passes only successful values to `snapshot.merge`, with one helper for the NotFound conversion. Commit dd69f33.
- FINDING-39 to FINDING-43: docstrings cite spec requirement IDs only; `commit_times` moved to sources/github.py; `TAGLINE_MAX` defined once with `max_len: int | None`; new `profilegen.clock` module; the CLI docstring lists every exit code. Commit 827570c.
- FINDING-44 to FINDING-46: tests added for the demote reason without any commit, hidden directories, a non-year heading ending a year section, temp-file cleanup, no git on the local render, and `posts_shown` reaching the feed. Commit 827570c.

### Content changes (user decisions)

- Corgi points to the upstream `tals/corgi` (212 stars). The new description says Roland contributes to Corgi and helps support it, and the fork comment is removed. `tals` is not an owned account, so the stars are shown but not counted (FR-012; a new GitHub-source test covers this). Commit 2badf18.
- `scan` credits a checkout's own commits to its origin remote and also to any remote that is a listed main project. Roland's checkout (origin `rhuss/corgi`, upstream `tals/corgi`) therefore supplies the activity for the Corgi main project. Unlisted upstreams still fall back to the commits API. Test added; the local checkout's remotes were checked offline. Commit 60a8697.
- New community role `alumni-maintainer`, shown as "alumni maintainer"; Knative uses it. Validation and render tests added; data-model.md and contracts/profile-yaml.md updated. Commit 2300073.

### Verification

- `uv run pytest -q`: 558 passed (526 before the follow-up). No test touches the network.
- `uv run profilegen render` (live): exit 0, no warnings, total stars 4.3k, Corgi shown with 212 stars. Commit 6b9d957.
- `uv run profilegen render --offline` twice: README.md and data/snapshot.json byte-identical.
