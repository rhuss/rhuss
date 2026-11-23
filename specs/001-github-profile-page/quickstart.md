# Quickstart: Validate the Profile Page Feature

## Prerequisites
- `uv` installed; `gh` authenticated (optional, for higher API limits locally)
- Repository root of the profile repo (this repo)

## 1. Tests (offline)
```bash
uv run pytest -q
```
Expected: all tests pass, no network access.

## 2. Validate the data file
```bash
uv run profilegen validate
```
Expected: exit 0. Introduce a 4-sentence main-project description and rerun: exit 1 with `ERROR: main_projects[...]`.

## 3. Render with live data
```bash
uv run profilegen render
git diff --stat README.md data/snapshot.json
```
Expected: README has sections in order header, stats, current focus, community, books, talks (+ Mermaid chart), writing, more tools, footer. Total stars excludes Knative, JKube, OpenShell.

## 4. Determinism
```bash
uv run profilegen render --offline && cp README.md /tmp/pg-first.md
uv run profilegen render --offline && cmp README.md /tmp/pg-first.md && echo IDENTICAL
```
Expected: `IDENTICAL`; the footer date did not change.

## 5. Source failure fallback
```bash
PROFILEGEN_FEED_URL=https://invalid.example/index.xml uv run profilegen render
```
Expected: warning about the blog feed; Writing section shows the snapshot's posts; exit 0.

## 6. Scan (skill input)
```bash
uv run profilegen scan --json | jq '.proposals'
```
Expected: proposals only for public repositories.

## 7. Workflow
Push to `rhuss/rhuss`, run the "Refresh profile" workflow manually. Expected: success; a commit only when content changed.

## 8. Skill
Copy `skill/profile-curate/` into the personal-skills plugin (see `skill/profile-curate/README.md`), then run `/profile-curate` in a Claude Code session inside this repo.
