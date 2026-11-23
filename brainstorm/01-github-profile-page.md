# Brainstorm: GitHub Profile Overview Page

**Date:** 2026-11-23
**Status:** active

## Problem Framing

Roland wants a GitHub profile page (the README of a special `rhuss/rhuss` repository, in the style of github.com/steipete) that gives visitors a current, visually appealing overview of his work: main projects, community projects, books, talks, blog posts, and LinkedIn. The page must stay current without manual editing. Curated content changes when Roland runs a skill; live numbers (stars, blog posts, talks) refresh automatically every night.

Success: a visitor sees within seconds what Roland works on right now, backed by a few honest numbers, and the page never goes stale for more than a day on the live parts.

Anti-goals:
- Anything non-public leaking into the README (Red Hat internal or unreleased work under `~/Work/projects`, even as a repo name).
- Inflated numbers (e.g., counting Knative or OpenShell stars as Roland's own).
- Unreviewed AI-written text appearing on the public page.

## Context Found

- `rhuss/rhuss` does not exist yet. steipete's page is the README of `steipete/steipete`, maintained by a workflow.
- Main projects are public: `rhuss/cc-spex` (123 stars), `rhuss/cc-guide`, `rhuss/corgi`, `rhuss/debaser`, `rhuss/aprofile`, `rhuss/cc-review`, `rhuss/cc-prose`. AgentTacho lives in its own org: `AgentTacho/agenttacho` (plus `agenttacho.github.io` site and `homebrew-tap`).
- Talks: `ro14nd-talks/archive` README lists talks by year (2013 to 2026) with title, venue, date, and slide links.
- Blog: `https://ro14nd.de/index.xml` feed is reachable.
- Books: Kubernetes Patterns has `k8spatterns/examples` (1,090 stars) and `k8spatterns/k8spatterns.com`. No public repo/site found yet for Generative AI on Kubernetes.
- LinkedIn: https://www.linkedin.com/in/ro14nd/
- Local checkouts live in `~/Development` (incl. `~/Development/context-engineering`, `~/Development/ai/aprofile`) and `~/Work/projects`.

## Approaches Considered

### A: Curated data file + renderer in `rhuss/rhuss` (chosen)
The profile repo holds a curated data file, a README template, and a small render script. A nightly GitHub Action fetches live data, merges it with the data file, and regenerates the whole README. A local skill edits the data file and pushes it.
- Pros: single source of truth; README fully generated (no drift from hand edits); thin skill; renderer testable offline; the custom star rule and talks chart live in one place.
- Cons: a few hundred lines of renderer code to own.

### B: Skill writes README, off-the-shelf Actions patch marker sections
- Pros: little custom CI code.
- Cons: several third-party actions each own a slice; the star rule and talks chart still need custom code; layout changes require editing README and markers together.

### C: Fully local, no Action
- Pros: simplest.
- Cons: stars and blog posts go stale between runs, defeating the automation goal.

### Dropped: Claude regenerates the page in CI
Needs an API key in the repo, costs tokens nightly, and publishes text nobody reviewed.

## Decision

Approach A. The renderer and nightly workflow live in `rhuss/rhuss`; the local skill lives in `~/Development/context-engineering` (likely inside the `personal-skills` plugin). `~/Work/priv/github-overview` becomes the local clone of `rhuss/rhuss` (proposal, see Open Questions).

## Key Requirements

### Data flow
- **Local skill (run on demand):** scans local checkouts (`~/Development`, `~/Work/projects`) and GitHub, proposes updates to the curated data file (project grouping, blurbs, taglines, roles), shows the diff for review, then commits and pushes it to `rhuss/rhuss`.
- **Nightly GitHub Action (in `rhuss/rhuss`):** reads the data file, fetches live data (stars, latest release/last commit, last 3 blog posts from the feed, recent talks from the archive README), renders the README, commits if changed. No LLM, no API key in CI.
- The archive README in `ro14nd-talks/archive` is the single source of truth for talks. Local talk folders are not read.

### Page content (top to bottom)
1. Header: name, one-line intro (proposal: derived from current GitHub bio), links to blog and LinkedIn, tech badge row.
2. Stats strip: total stars, number of talks, number of books.
3. Current focus: the 8 main projects (cc-spex, AgentTacho, cc-guide, corgi, debaser, aprofile, cc-review, cc-prose), up to 3 sentences each, with live star count.
4. Community: OpenShell, Knative, Jolokia, docker-maven-plugin, JKube; one tagline each, Roland's role (creator/maintainer/contributor, proposal), live stars.
5. Books: Kubernetes Patterns and Generative AI on Kubernetes with covers side by side, one line each, link.
6. Talks: 5 to 10 most recent from the archive, plus a talks-per-year chart.
7. Writing: last 3 blog posts.
8. More tools: smaller public projects, one tagline each.
9. Footer: last refresh timestamp.

### Data rules
- **Public only:** only repos public on GitHub may appear (proposal, agreed). Private or internal repos are never listed, not even by name.
- **Total stars:** sum over repos Roland created or owns: everything under `rhuss`, `AgentTacho`, `k8spatterns`, plus Jolokia and docker-maven-plugin. Knative, JKube, and OpenShell show their stars next to their entries but are excluded from the total.
- **Talks per year:** counted from the year headings of the archive README (2013 onward). Proposal: render as a Mermaid bar chart, which GitHub renders natively (no image generation).
- **Book covers:** static images committed once to `rhuss/rhuss`, not fetched nightly.

### Skill behavior
- Main projects are curated by Roland. The skill suggests promotions/demotions based on activity (e.g., "no commits in 60 days, move down?", "busy repo, promote?") but never moves anything without confirmation (proposal, agreed).
- Blurbs and taglines are written locally (with Roland's review), never in CI.
- Every push to `rhuss/rhuss` is preceded by a diff review.

## Open Questions
- Link target and cover source for Generative AI on Kubernetes (no public repo/site found yet).
- Exact role labels per community project (creator, maintainer, contributor) and which repos represent OpenShell, Knative, and JKube.
- Should `~/Work/priv/github-overview` become the `rhuss/rhuss` clone, or should it stay a separate workspace?
- Activity thresholds for promote/demote suggestions (60 days is a placeholder).
- Renderer language and template engine (plan phase).
- Badge set for the header (which technologies).
- How the skill scopes "smaller public projects": all public `rhuss/*` repos with recent activity, or an explicit list.
