---
runbook_version: 1
feature: 001-github-profile-page
status: passed
mode: light
steps_total: 9
step_results: passed,passed,passed,passed,passed,passed,passed,passed,passed
drafted_at: c1aa4d3
drafted_fingerprint: 59d681d4a627835cb8539f39965823b295e5867dd7470ce80bf9d51421ec0d7f
tested_at: 9200ef2
tested_fingerprint: 134efade24021cc1b65d679c8f4f1cf293871393a51eb996c3619b13685710ff
updated: 2026-11-23
---

# Try it: Generated GitHub Profile Page

<!-- runbook-status -->
> **Status:** passed · 9 of 9 steps (9 passed) · Mode: light · Tested at 9200ef2 · 2026-11-23
<!-- /runbook-status -->










## What you're testing

`profilegen` turns the curated `profile.yaml` plus live data (GitHub stars, the ro14nd.de feed, the talks archive) into `README.md` and a fallback snapshot `data/snapshot.json`. The journey goes: tests pass, the data file validates, a live render produces the page, a second render is byte-identical, a broken source falls back to the snapshot, a bad data file is rejected, the keep-alive check answers, the curation scan proposes changes, and a preview leaves the real README alone. Run every step from the repository root of the feature worktree.

## Test environment

No fixtures are needed. Steps 3, 5 and 8 reach github.com and ro14nd.de over the network; `gh` must be logged in for step 8 (higher API limits).

## Steps

### Step 1 of 9: Run the offline test suite (US1)

**Why this step:** Confirms the parsers, rules and renderer behave as specified before touching live data.

**Run:**

```
make test
```

**What you should see:** A dot progress line ending in `558 passed`, with no failures or errors and no network access.

**If you see something else:** A failure names the test file; `uv` errors mean the environment is not synced (`uv sync`).

**Result:**

PASSED (agent). ✔ `558 passed in 46.89s`, no failures, no network.

### Step 2 of 9: Validate the curated data file (US3)

**Why this step:** Every push and every render depends on `profile.yaml` passing the same validation (sentence limits, roles, no duplicates).

**Run:**

```
uv run profilegen validate; echo "exit=$?"
```

**What you should see:** No `ERROR:` lines and `exit=0`.

**If you see something else:** `ERROR: <path>: <message>` lines point to the offending field in `profile.yaml`.

**Result:**

PASSED (agent). ✔ `profile.yaml: valid`, `exit=0`, no `ERROR:` lines.

### Step 3 of 9: Render the page from live data (US1)

**Why this step:** This is the product: the README a visitor sees on github.com/rhuss.

**Run:**

```
uv run profilegen render; echo "exit=$?"; grep -n '^## ' README.md
```

**What you should see:** `exit=0` without warnings, then the section headings in this order: current focus, community, books, talks, writing, more tools (header and stats strip sit above the first heading, the footer below the last). Opening `README.md` shows about 4.3k total stars, Corgi pointing to `tals/corgi`, Knative as "alumni maintainer", 8 recent talks and a Mermaid `xychart-beta` block, and 3 blog posts.

**If you see something else:** `WARNING:` lines name an unreachable source or a data-file entry that is missing or not public.

**Result:**

PASSED (agent). ✔ `exit=0`, no warnings. ✔ Headings in order: Current focus (l.11), Community (30), Books (43), Talks (58), Writing (77), More tools (83). ✔ `⭐ **4.3k** stars · 🎤 **110** talks · 📚 **2** books`; Corgi links `https://github.com/tals/corgi` ⭐ 212; Knative `_alumni maintainer_` ⭐ 6.1k; `xychart-beta` at l.70; footer `Last updated: 2026-11-23`. Observation: `data/snapshot.json` changed one line (`rhuss/cc-slidev` stars 54 to 55, a real new star) while README stayed identical, because More tools entries do not show stars but the snapshot stores them.

### Step 4 of 9: Check that rendering is deterministic (US2)

**Why this step:** The nightly job must not create noise commits; identical inputs have to give byte-identical files, including the footer date.

**Needs:** Step 3.

**Run:**

```
uv run profilegen render --offline && cp README.md /tmp/pg-first.md && uv run profilegen render --offline && cmp README.md /tmp/pg-first.md && echo IDENTICAL
```

**What you should see:** `IDENTICAL`.

**If you see something else:** `cmp` prints the first differing byte; compare the two files to see which value moved.

**Result:**

PASSED (agent). ✔ `IDENTICAL`.

### Step 5 of 9: Break the blog feed and watch the fallback (US2)

**Why this step:** A source outage must keep the last good values instead of publishing an empty section.

**Needs:** Step 3 (snapshot holds the posts).

**Run:**

```
PROFILEGEN_FEED_URL=http://127.0.0.1:9/index.xml uv run profilegen render; echo "exit=$?"; git diff --stat -- README.md data/snapshot.json
```

**What you should see:** One `WARNING:` line about the blog feed, `exit=0`, and no diff for `README.md` or `data/snapshot.json` (the posts come from the snapshot).

**If you see something else:** A diff in the Writing section means the fallback did not use the snapshot; a non-zero exit means a source failure was treated as fatal.

**Result:**

PASSED (agent). ✔ `WARNING: blog feed unavailable, using last known values (127.0.0.1:9: connection failed ...)`, ✔ `exit=0`, ✔ no README diff. The only snapshot diff is the cc-slidev line carried over from step 3 (not caused by this step).

### Step 6 of 9: Feed the generator a bad data file (US1)

**Why this step:** A malformed data file must fail loudly and leave the README untouched.

**Run:**

```
printf 'name: Test\nbogus_key: 1\n' > /tmp/pg-bad.yaml; uv run profilegen --profile /tmp/pg-bad.yaml render; echo "exit=$?"; git diff --stat -- README.md
```

**What you should see:** `ERROR:` lines (unknown key `bogus_key`, missing required fields), `exit=1`, and no diff for `README.md`.

**If you see something else:** `exit=0` or a README diff means validation runs too late or not at all.

**Result:**

PASSED (agent). ✔ `ERROR: bogus_key: unknown key`, `ERROR: intro: required`, `ERROR: links: required`, `ERROR: main_projects: required`, `ERROR: books: required`; ✔ `exit=1`; ✔ no README diff.

### Step 7 of 9: Ask the keep-alive check (US2)

**Why this step:** The workflow uses this exit code to decide whether an empty commit is needed to keep GitHub's schedule alive.

**Run:**

```
uv run profilegen keepalive --days 50; echo "exit=$?"
```

**What you should see:** `exit=3` (the branch has fresh commits, so no keep-alive is needed).

**If you see something else:** `exit=0` would mean the last commit looks older than 50 days; `exit=1` is a git error.

**Result:**

PASSED (agent). ✔ `last commit 0.0 days ago (threshold 50): no keep-alive commit needed`, `exit=3`.

### Step 8 of 9: Run the curation scan (US3)

**Why this step:** This is the fact base the `profile-curate` skill turns into proposals; it must only ever mention public repositories.

**Run:**

```
uv run profilegen scan --json | jq '{repos: (.repos | length), proposals: .proposals}'
```

**What you should see:** A repo count above zero and a list of proposals with `kind` values among `demote`, `promote`, `remove`, `rename`, `new_tool`, each naming only public repositories you recognize. Corgi is not proposed for demotion.

**If you see something else:** An error exit means visibility could not be checked (network or `gh` login); any private repo name in the output is a bug.

**Result:**

PASSED (agent). ✔ `exit=0`, 329 repos, 18 proposals (6 `promote`, 12 `new_tool`), all public; no demotion of Corgi. Output saved to `.walkthrough/step-8.json`. Observations: the scan took over 2 minutes, and the list is long and includes sites and repro repos (`rhuss.github.io`, `zellij-*-repro`, `homebrew-tap`), so the skill's one-at-a-time review will need a quick reject path.

### Step 9 of 9: Preview without touching the README (US4)

**Why this step:** Local previews must never change the committed page.

**Run:**

```
make preview && git status --short -- README.md data/snapshot.json && head -5 /tmp/profile-preview.md
```

**What you should see:** `Preview written to /tmp/profile-preview.md`, no `git status` lines for README or snapshot, then the first lines of the preview starting with the name header.

**If you see something else:** A modified README or snapshot means `--output` leaks into the real files.

**Result:**

PASSED (agent). ✔ `Preview written to /tmp/profile-preview.md`; ✔ preview starts with `# Roland Huß`; ✔ README unchanged. The ` M data/snapshot.json` shown was already present before this step (from step 3).

## Not covered here

- The nightly GitHub Actions run, the push trigger and keep-alive commits: `rhuss/rhuss` does not exist yet. Try them after the first push with a manual "Refresh profile" dispatch (see `CONTRIBUTING.md`).
- Light and dark rendering on github.com (SC-007): needs the pushed repository.
- The interactive `profile-curate` skill session (accept, edit, reject, diff, confirmed push): it pushes to the remote, which does not exist yet. Step 8 covers its fact base.

## Coverage

- US1 (visitor sees the overview): steps 1, 3, 6.
- US2 (nightly refresh): steps 4, 5, 7 locally; the scheduled run itself is not covered (no remote yet).
- US3 (curation skill): steps 2 and 8; the interactive session is not covered (pushes to a remote that does not exist yet).
- US4 (local preview): step 9.

## Results

9 steps: 9 passed, 0 failed, 0 skipped (agent-run, 2026-11-23). The generator renders the full page from live data with the agreed star rule, falls back to the snapshot when a source fails, rejects bad data files without touching the README, renders deterministically, and the scan yields public-only proposals. Two follow-ups: stars of More tools entries are stored in the snapshot although the page does not show them, so a new star there causes a snapshot-only commit (SC-006 noise); and the scan is slow and noisy (329 repos, 18 proposals).
