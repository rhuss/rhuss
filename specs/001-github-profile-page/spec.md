# Feature Specification: Generated GitHub Profile Page

**Feature Branch**: `001-github-profile-page`

**Created**: 2026-11-23

**Status**: Draft

**Input**: Brainstorm `brainstorm/01-github-profile-page.md`: a generated GitHub profile page (README of a new public `rhuss/rhuss` repository, in the style of github.com/steipete) that gives a current overview of Roland Huß's work. Curated content lives in a data file maintained through a local skill; a nightly automated job merges it with live data and regenerates the page.

## Clarifications

### Session 2026-11-23

- Q: Should the footer show when the job last ran or when the content last changed? → A: The date (day precision, UTC) of the last content change, so runs without changes produce byte-identical output and no commit.
- Q: Where do the "last successful values" for an unreachable source come from? → A: A committed live-data snapshot file in the profile repository, updated together with the README whenever a source fetch succeeds.
- Q: How are talks ordered when the archive lists them out of order within a year? → A: Sort by year (from the heading) descending, then by month when parseable from the entry, newest first; entries without a parseable month keep archive order after dated ones in that year.
- Q: How is a single archive bullet that names several talks or venues counted? → A: One bullet equals one talk for counts and the per-year chart.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visitor sees a current overview of Roland's work (Priority: P1)

A visitor opens github.com/rhuss and sees a well-structured page: a header with a short intro and links (blog, LinkedIn), a stats strip (total stars, number of talks, number of books), the eight main projects with short descriptions and star counts, community projects with Roland's role, the two books with covers, recent talks with a talks-per-year chart, the last three blog posts, a list of smaller tools, and a "last refreshed" footer.

**Why this priority**: The page itself is the product. Without a correct, readable page nothing else matters.

**Independent Test**: Given a curated data file and a fixed snapshot of live data (stars, blog feed, talks archive), generating the page produces a README containing every section in the defined order with the expected values.

**Acceptance Scenarios**:

1. **Given** a data file listing the eight main projects with blurbs, **When** the page is generated, **Then** the "Current focus" section lists those eight projects in the curated order, each with its blurb (max three sentences) and its current star count.
2. **Given** live star counts for owned and community repositories, **When** the page is generated, **Then** the total in the stats strip equals the sum over owned repositories only, and community projects (Knative, JKube, OpenShell) show their own counts without being added to the total.
3. **Given** the talks archive README with year sections, **When** the page is generated, **Then** the talks section shows the most recent talks (default 8, within 5 to 10) newest first, and a bar chart shows the number of talks per year.
4. **Given** the blog feed, **When** the page is generated, **Then** the writing section shows the three newest posts with title, link, and date.
5. **Given** the two books in the data file with committed cover images, **When** the page is generated, **Then** both covers appear side by side with a one-line description and link.

---

### User Story 2 - Page refreshes itself every night (Priority: P2)

Without any action from Roland, a scheduled job in the `rhuss/rhuss` repository regenerates the page once per day from the data file plus fresh live data, and commits the result only when the content changed.

**Why this priority**: Freshness of stars, posts, and talks is the main reason for automation; without it the page goes stale.

**Independent Test**: Trigger the job manually; it completes, and either commits an updated README (when live data changed) or makes no commit (when nothing changed).

**Acceptance Scenarios**:

1. **Given** a new blog post was published, **When** the nightly job runs, **Then** the README lists it among the last three posts and a commit is created.
2. **Given** nothing changed in any source except the clock, **When** the nightly job runs, **Then** the output is byte-identical and no commit is created.
3. **Given** one live source is temporarily unreachable, **When** the job runs, **Then** the affected section uses the snapshot values, other sections still update, and the job reports a warning instead of publishing an empty section.
4. **Given** Roland pushes a changed data file, **When** the push lands, **Then** the job runs right away and the README reflects the change within minutes.
5. **Given** no commit for 50 days, **When** the nightly job runs, **Then** it creates an empty keep-alive commit so the schedule stays active.

---

### User Story 3 - Roland curates content with a local skill (Priority: P2)

Roland runs a Claude Code skill on his machine. It scans his local checkouts and GitHub activity, proposes changes to the curated data file (new or changed blurbs and taglines, roles, candidates to promote into or demote out of the main projects, new public smaller tools), applies only the changes he accepts, shows the resulting diff, and on approval commits and pushes the data file to `rhuss/rhuss`.

**Why this priority**: Curated content changes rarely but must stay accurate; the skill makes updates cheap and keeps AI-written text under human review.

**Independent Test**: Run the skill against the local machine; it produces a proposal list, applies only accepted items to the data file, shows a diff, and pushes only after explicit confirmation.

**Acceptance Scenarios**:

1. **Given** a main project had no commits in the last 60 days, **When** the skill runs, **Then** it proposes demoting it, and nothing changes unless Roland accepts.
2. **Given** a repository exists locally but is not public on GitHub, **When** the skill runs, **Then** it never proposes it and never writes its name into the data file.
3. **Given** accepted changes, **When** the skill finishes, **Then** it shows the full diff of the data file and waits for explicit confirmation before committing and pushing.
4. **Given** Roland declines the push, **When** the skill ends, **Then** the remote repository is unchanged.
5. **Given** a public repository outside the main projects had at least 10 commits in the last 30 days, **When** the skill runs, **Then** it proposes promoting it, and nothing changes unless Roland accepts.

---

### User Story 4 - Roland previews the page locally (Priority: P3)

Roland generates the page on his machine from the current data file to check layout and content before pushing.

**Why this priority**: Useful for iterating on blurbs and layout, but the nightly job also produces the page.

**Independent Test**: Run the generation locally; it writes the README without committing or pushing anything.

**Acceptance Scenarios**:

1. **Given** a local checkout of the profile repository, **When** Roland runs the generation, **Then** README.md is rewritten locally and no commit or push happens.

---

### Edge Cases

- A repository listed in the data file is renamed: the page follows the redirect and renders the new name and link; the job warns so the next skill run updates the data file.
- A repository listed in the data file is deleted or made private: it is dropped from the page (never rendered with a broken link) and the job warns, referring to it only by its data-file entry.
- A live source fails on the very first run (no snapshot yet): affected items are omitted, and the job warns.
- A blurb exceeds three sentences or a tagline exceeds one line: generation fails validation with a clear message instead of publishing it.
- The talks archive has a year heading with no entries, or entries without links: the year counts zero talks; entries without a link render as plain text.
- The blog feed has fewer than three posts: show what exists, without placeholders. A feed or archive that is fetched successfully but has no entries hides its section.
- GitHub API rate limit is hit: treated as an unreachable source (keep previous values, warn).
- The data file is malformed: generation fails with a message pointing to the problem; the existing README is left untouched.
- The same repository appears in two groups of the data file: validation error.

## Requirements *(mandatory)*

### Functional Requirements

**Page content and layout**

- **FR-001**: The page MUST contain, in this order: header, stats strip, current focus, community, books, talks, writing, more tools, footer.
- **FR-002**: The header MUST show Roland's name, a one-line intro, links to the blog (https://ro14nd.de) and LinkedIn (https://www.linkedin.com/in/ro14nd/), and a row of technology badges defined in the data file.
- **FR-003**: The stats strip MUST show total stars, total number of talks (counted from the talks archive), and number of books.
- **FR-004**: The current-focus section MUST list the main projects from the data file (initially eight: rhuss/cc-spex, AgentTacho/agenttacho, rhuss/cc-guide, tals/corgi (upstream, worked on through the fork rhuss/corgi), rhuss/debaser, rhuss/aprofile, rhuss/cc-review, rhuss/cc-prose) in curated order, each with a link, a description of at most three sentences, and its live star count.
- **FR-005**: The community section MUST list the community projects (OpenShell, Knative, Jolokia, docker-maven-plugin, JKube) with a one-line tagline, Roland's role (for example creator, maintainer, contributor), a link, and the live star count of the designated repository.
- **FR-006**: The books section MUST show both books (Kubernetes Patterns, Generative AI on Kubernetes) with cover images side by side, a one-line description, and a link. A book without a cover image file renders its title as a text link in place of the image.
- **FR-007**: The talks section MUST list the N most recent talks from the archive (N configurable, 5 to 10, default 8), newest first, with title, venue, date (`Mon YYYY` when a month is known, otherwise `YYYY`), and link when available, followed by a talks-per-year bar chart that renders natively on GitHub. The chart covers every year from the first archive year through the latest archive year, with zero for years without talks. Entries that do not match the `title - venue, date` pattern render their raw text as the title.
- **FR-008**: The writing section MUST list the three most recent blog posts from the blog feed with title, link, and publication date (`YYYY-MM-DD`).
- **FR-009**: The more-tools section MUST list smaller public projects from the data file with a single-line tagline each.
- **FR-010**: The footer MUST state the date (UTC, day precision) of the last content change. The footer date is set to the current UTC date only if the rendered page, excluding the footer, differs from the existing README; otherwise the existing footer date is kept. Generating twice from identical inputs MUST produce byte-identical output.

**Data rules**

- **FR-011**: Only repositories that are public on GitHub at generation time MAY appear on the page. Non-public or missing repositories MUST be omitted and reported as warnings.
- **FR-012**: Total stars MUST be the sum of stars over owned repositories: all public repositories under `rhuss`, `AgentTacho`, and `k8spatterns`, plus `jolokia/jolokia` and `fabric8io/docker-maven-plugin`. Stars of other community repositories MUST NOT be added. Forks under the owned accounts MUST be excluded from the total; archived repositories are included.
- **FR-013**: The talks archive README (`ro14nd-talks/archive`) MUST be the only source for talks; talks per year are counted from its year sections, one bullet entry counting as one talk. Recent talks MUST be ordered by year descending, then by parseable month descending; undated entries follow dated ones of the same year in archive order.
- **FR-014**: Book covers MUST be static images stored in the profile repository; they are not downloaded during the nightly refresh.
- **FR-015**: All descriptive text (intro, blurbs, taglines, roles) MUST come from the curated data file; the nightly job MUST NOT generate or alter prose.

**Nightly refresh**

- **FR-016**: The profile repository MUST contain a scheduled job that runs at least once per day, can also be triggered manually, and runs immediately on every push that changes the data file.
- **FR-016a**: To prevent GitHub from disabling the schedule after 60 days of repository inactivity, the job MUST create an empty keep-alive commit when the last commit on the default branch is 50 or more days old.
- **FR-017**: The job MUST regenerate the whole README from the data file plus live data and commit only when the README or the live-data snapshot differs from the committed version. If the remote moved meanwhile, the job MUST rebase and retry the push.
- **FR-018**: The job MUST NOT require any secret beyond the repository's built-in automation token.
- **FR-019**: When a live source fails, the job MUST use that source's values from the committed live-data snapshot, still update other sections, and surface a warning in the job log. The snapshot MUST be updated for every source that was fetched successfully. The snapshot MUST contain only rendered data values (no fetch timestamps, per-run status, or other values that change on every run). If a source fails and the snapshot has no value for an item, that item is omitted, with one warning per source that lists the omitted data-file entries. The "currently unavailable" note is per source, not per entry: a section shows one note when its source has no value at all (failed with nothing in the snapshot). Otherwise the section shows the items that have values, and a section with no item to show is hidden entirely (no empty heading).
- **FR-019a**: Warnings (unreachable source, missing or non-public repository) MUST NOT fail the job; the job succeeds with warning annotations. Data-file validation errors MUST fail the job and leave the README untouched. Warnings about a repository MUST identify it only by its data-file entry.
- **FR-019b**: Text from the blog feed and the talks archive (titles, venues, link labels) MUST be rendered as literal text, with Markdown special characters escaped. Links from these sources MUST only be rendered for absolute http or https URLs; any other link target renders the text without a link.

**Local curation skill**

- **FR-020**: The skill MUST scan local checkouts (`~/Development`, `~/Work/projects`) and the GitHub accounts/organizations above to build proposals for the data file.
- **FR-021**: The skill MUST propose (never silently apply) promotions and demotions of main projects based on commit activity: demotion for a main project with no commits in the last D days (default 60), promotion for a public repository not in the main projects with at least N commits in the last M days (defaults N=10, M=30). D, N, and M are configurable in the data file.
- **FR-022**: The skill MUST draft blurbs and taglines for new or changed projects and present each for acceptance, editing, or rejection.
- **FR-023**: The skill MUST only consider repositories that are public on GitHub; local-only or private repositories MUST NOT appear in proposals or in the data file.
- **FR-023a**: The skill MUST propose removing data-file entries whose repositories are no longer public or no longer exist, and propose updating entries for renamed repositories.
- **FR-024**: The skill MUST validate the data file before offering to push, and the generator MUST apply the same validation: required fields present, no repository listed twice, descriptions of at most three sentences, taglines of a single line with at most 120 characters. A sentence is text ending in `.`, `!`, or `?` followed by whitespace or end of text; tokens on a configurable abbreviation list (default includes `e.g.`, `i.e.`, `vs.`, `etc.`) and version numbers do not end a sentence.
- **FR-025**: The skill MUST show the full diff of the data file and require explicit confirmation before committing and pushing to `rhuss/rhuss`. Before pushing, the skill MUST rebase onto the remote default branch.
- **FR-026**: The page generation MUST be runnable locally without committing or pushing, for preview.

### Key Entities

- **Profile data file**: the curated source of truth. Holds identity (name, intro, links, badges), groups (main projects, community, books, more tools), and settings (number of talks shown, inactivity threshold).
- **Project entry**: repository reference (owner/name), display name, link, group, description (up to 3 sentences for main projects, one line otherwise), optional role, optional emoji.
- **Book entry**: title, one-line description, link, cover image path.
- **Talk**: title, venue, date (month/year as given), optional slides/video link, year. Parsed from the archive README.
- **Blog post**: title, link, publication date. Parsed from the blog feed.
- **Live snapshot**: the last successfully fetched rendered values per source (stars per repository, resolved repository names, talks, posts); used as fallback when a source fails. Contains no timestamps or per-run status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time visitor can identify Roland's eight current main projects, both books, and the latest talk within 30 seconds of opening the profile.
- **SC-002**: Star counts, blog posts, and talks on the page are never more than 24 hours behind their sources, except while a source is unreachable.
- **SC-003**: Zero non-public repository names appear on the rendered page at any time, and zero appear in the data file at the time of each skill push.
- **SC-004**: The total-stars figure exactly matches the sum over owned public, non-fork repositories at the time of the last refresh.
- **SC-005**: A curation run with the skill (scan, review proposals, push) takes Roland under 10 minutes when there are no more than 5 proposals.
- **SC-006**: Nightly runs where both the README and the live-data snapshot are unchanged create no commits (no daily noise commits in the repository history).
- **SC-007**: The page renders correctly (no broken images, no broken charts) on GitHub's web view in light and dark mode.

## Assumptions

- This repository (`~/Work/priv/github-overview`) is the local working copy of the future `rhuss/rhuss` repository. Creating the GitHub repository and the first push are manual steps outside this feature.
- The curation skill is developed in this repository (so it is reviewed and tested with the renderer) and is packaged so it can be installed into the `personal-skills` plugin in `~/Development/context-engineering`. Copying it into that repository is a follow-up step.
- The talks archive README keeps its current structure: `# <year>` headings followed by bullet entries `title - venue, date` with optional links. Roland keeps it up to date.
- The blog at https://ro14nd.de publishes a standard feed at `/index.xml`.
- The talks-per-year chart is rendered as a chart description that GitHub renders natively (no generated image files).
- The cover for Generative AI on Kubernetes is supplied by Roland as an image file; until then the text-link fallback from FR-006 is shown. Its link target defaults to the publisher page and can be changed in the data file.
- Community canonical repositories: OpenShell `ai-openshell/openshell` (the former `NVIDIA/OpenShell` redirects there), Knative `knative/serving`, Jolokia `jolokia/jolokia`, docker-maven-plugin `fabric8io/docker-maven-plugin`, JKube `eclipse-jkube/jkube`. Roles: creator for Jolokia and docker-maven-plugin, co-creator for JKube, alumni maintainer for Knative, contributor for OpenShell; all editable in the data file.
- Corgi is listed as a main project through its upstream `tals/corgi`, to which Roland contributes; its stars are shown but not counted toward the total (not owned).
- The "more tools" list is seeded from public `rhuss/*` repositories with activity in the last 12 months that are not already listed elsewhere; the skill proposes additions and removals.
- Only GitHub's built-in automation token is available in CI. A nightly run needs roughly a few dozen API calls (paginated repository listings for `rhuss`, `AgentTacho`, `k8spatterns`, plus individual community repositories and the archive README), well within the token's hourly limit.

## Implementation Refinements

Details settled during implementation and review that refine the requirements above without changing their intent:

- **Talk links**: relative and protocol-relative links in the archive README resolve to `https://ro14nd-talks.github.io/archive/<path>` (the published `gh-pages` site) before the http/https check of FR-019b applies. Talks in the same month keep the later archive position first (FR-013).
- **Commit activity (FR-021)**: only Roland's own commits count (git `user.email` for local checkouts, the GitHub login, the first entry of `owned_owners`, for API counts). A listed main project is matched through any remote of a local checkout (origin or upstream). Archived repositories, unlisted forks, and the profile repository itself are never proposed for promotion or as new tools.
- **Settings**: besides the thresholds, `profile.yaml` settings hold `posts_shown` (default 3), `owned_owners`, `owned_extra_repos`, `abbreviations`, `scan_roots`, `feed_url`, and `talks_repo`.
- **Validation (FR-024)** also enforces: intro single line, max 160 characters; 1 to 12 main projects; https URLs; covers under `assets/books/`; unknown keys rejected; community `role` required and one of `creator`, `co-creator`, `maintainer`, `alumni-maintainer`, `contributor`, `lead`.
- **Workflow (FR-016)** also runs on pushes that change `templates/**` or `assets/**`, only on the default branch, serialized by a concurrency group.
- **Source failures (FR-019)**: an archive without any year heading, a non-RSS feed, or a feed item without a date count as a failed fetch (snapshot fallback), not as a successful empty result.
- **Renames**: a curated `name` in the data file wins over the new repository name; the link always follows the rename.
- **Numbers**: star counts above 999 display as one-decimal `k` values (for example `4.3k`); the snapshot stores the displayed values so that changes invisible on the page cause no commit (SC-006). A stat without a value is omitted from the stats strip.
- **Overrides**: `PROFILEGEN_API_URL` and `PROFILEGEN_FEED_URL` override the source endpoints (testing); locally, without `GITHUB_TOKEN`, the token from `gh auth token` is used when available.
