# Research: Generated GitHub Profile Page

## R1: Implementation language and dependencies

- **Decision**: Python 3.12+, managed with `uv`; runtime deps PyYAML and Jinja2 only; pytest for tests.
- **Rationale**: Available on Actions runners and locally; stdlib covers HTTP, RSS, JSON. Roland's tooling standard is `uv`. Jinja2 keeps the README layout in one readable template.
- **Alternatives**: Go (single binary, but more code for templating and YAML); Node with off-the-shelf actions (rejected in brainstorm approach B); shell + `jq` (too brittle for parsing and rules).

## R2: Talks archive parsing

Observed entry shapes in `ro14nd-talks/archive` README (default branch `gh-pages`):

- `* **[Title](link)** - Venue, MM/YYYY | [Video](url)`
- `* **[Title](link)**, Venue, MM/YYYY | [Video](url) | [Demo](url)`
- `* **[Title](link)** Venue, MM/YYYY | [Video](url)` (no separator)
- `* **Title** - Venue, MM/YYYY`
- `* [Title](link) - Venue, YYYY, extra`
- `* Plain text title - Venue, M/YYYY`

- **Decision**: Parse per `# YYYY` heading; for each `* ` bullet: split off trailing `| ...` extras (collect Video/Demo/Resources links); extract title from the first bold or link construct, else text before ` - `; remaining text (stripped of leading `-`, `,`, whitespace) is venue+date; month from the last `(\d{1,2})/(\d{4})` match. If nothing matches, the raw text is the title (FR-007).
- **Link resolution**: relative links (e.g., `2026/sdd-codeeurope-2026.pdf`) resolve to `https://ro14nd-talks.github.io/archive/<path>`, the published GitHub Pages site of the `gh-pages` branch. Absolute links are kept.
- **Alternatives**: Strict regex per format (fails on the many variants); asking Roland to normalize the archive (out of scope, he owns it).

## R3: Blog feed

- **Decision**: Fetch `https://ro14nd.de/index.xml` (Hugo RSS 2.0); take `channel/item` sorted by `pubDate` (RFC 822, `email.utils.parsedate_to_datetime`) descending; keep title, link, date `YYYY-MM-DD`.
- **Alternatives**: Scraping the HTML (fragile).

## R4: GitHub data and the star total

- **Decision**: Use the REST API with `GITHUB_TOKEN` when present (unauthenticated locally falls back to `gh auth token` if available, else anonymous).
  - Owned listing: `GET /users/rhuss/repos?type=owner&per_page=100` and `GET /users/{AgentTacho,k8spatterns}/repos?type=owner&per_page=100` (the users endpoint also serves organizations) (paginated), plus `GET /repos/jolokia/jolokia` and `GET /repos/fabric8io/docker-maven-plugin`.
  - Total = sum of `stargazers_count` over results where `private == false` and `fork == false` (archived included).
  - Each repo referenced in `profile.yaml` not covered by a listing: `GET /repos/{owner}/{name}`. 404 or `private == true` means omitted with warning; a different `full_name` in the response means renamed (render the new name, warn).
- **Rationale**: About 6 to 15 calls per run; well inside the 1,000 req/h `GITHUB_TOKEN` limit.
- **Alternatives**: GraphQL (one call, but more complex and needs a token locally); `gh` CLI in CI (extra dependency in Python tests).

## R5: Talks-per-year chart

- **Decision**: Mermaid `xychart-beta` bar chart in a ```` ```mermaid ```` block, rendered natively by GitHub in light and dark mode. X axis: every year from first to last archive year; Y: count; zero years included.
- **Alternatives**: Generated SVG (needs commits of binary-ish assets, dark-mode handling); shields.io badges per year (not a chart).

## R6: Footer date and determinism

- **Decision**: Render the page with a fixed placeholder for the footer, compare with the existing README with its footer line normalized to the same placeholder. If equal, reuse the existing footer date; otherwise use today's UTC date. All collections are sorted deterministically; numbers formatted consistently (e.g., `1.2k` above 999 using one fixed rule).
- **Snapshot**: JSON with sorted keys, 2-space indent, trailing newline; contains only rendered values (FR-019).

## R7: Workflow triggers, commits, keep-alive

- **Decision**: `.github/workflows/refresh.yml` with `schedule: cron "17 4 * * *"`, `workflow_dispatch`, and `push` with `paths: [profile.yaml, templates/**, assets/**]` on the default branch. `permissions: contents: write`. Steps: checkout (full history for keep-alive), setup-uv, `uv run profilegen render`, then `git diff --quiet -- README.md data/snapshot.json` decides the commit. Push uses `git pull --rebase` and retries up to 3 times. Keep-alive: `uv run profilegen keepalive --days 50` exits 0 when a keep-alive commit is needed; then `git commit --allow-empty`.
- **Loop safety**: commits made with `GITHUB_TOKEN` do not trigger new workflow runs, so the push trigger cannot loop.
- **Commit identity**: `github-actions[bot]`.

## R8: Skill vs. CLI split

- **Decision**: Deterministic facts come from the CLI (`profilegen scan --json`): local repos with GitHub remotes under `~/Development` and `~/Work/projects` (depth-limited walk, `git log` commit counts in the last M and D days), visibility per repo from GitHub, and computed promote/demote/remove/rename/new-tool candidates. Prose (blurbs, taglines) is drafted by Claude inside the skill and accepted, edited, or rejected by Roland one at a time. The skill edits `profile.yaml`, runs `profilegen validate` and `profilegen render` (preview), shows `git diff`, then `git pull --rebase` and `git push` only after confirmation.
- **Privacy**: `scan` drops any repo that is not public on GitHub before producing output, so private names never reach the skill's proposals (FR-023).
- **Alternatives**: Skill does everything with shell commands (untestable rules); CLI generates prose (violates "no unreviewed AI text").

## R9: Badges and covers

- **Decision**: Header badges are shields.io static badges defined in `profile.yaml` (label, color, logo). Covers are committed under `assets/books/`; Kubernetes Patterns cover taken from the `k8spatterns/k8spatterns.com` repository static assets; GenAI book uses the text-link fallback until a file is added.
