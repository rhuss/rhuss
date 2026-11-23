# Data Model: Generated GitHub Profile Page

## Profile (root of `profile.yaml`)

| Field | Type | Rules |
|-------|------|-------|
| `name` | string | required |
| `intro` | string | required, single line, max 160 chars |
| `links` | list of Link | required; must include blog and LinkedIn |
| `badges` | list of Badge | optional |
| `main_projects` | list of Project | required, 1..12; description max 3 sentences |
| `community` | list of Project | role required; tagline single line, max 120 chars |
| `books` | list of Book | required |
| `more_tools` | list of Project | tagline single line, max 120 chars |
| `settings` | Settings | optional, defaults below |

Cross-entity rules: a `repo` value appears at most once across `main_projects`, `community`, `more_tools`.

## Link
`label` (string), `url` (https URL), optional `emoji`.

## Badge
`label` (string), `color` (hex without `#` or shields color name), optional `logo` (simple-icons slug), optional `logo_color`.

## Project
| Field | Type | Notes |
|-------|------|-------|
| `repo` | `owner/name` | required; GitHub repository used for stars and visibility |
| `name` | string | display name, defaults to repo name |
| `url` | URL | optional override (e.g., product site); defaults to repo URL |
| `emoji` | string | optional |
| `description` | string | main projects: 1 to 3 sentences |
| `tagline` | string | community/more tools: one line |
| `role` | enum `creator`, `co-creator`, `maintainer`, `alumni-maintainer`, `contributor`, `lead` | community only; `alumni-maintainer` is shown as "alumni maintainer", the others as written |

## Book
`title`, `description` (single line), `url`, optional `cover` (path under `assets/books/`). Missing or nonexistent cover means text-link fallback (FR-006).

## Settings
| Field | Default | Meaning |
|-------|---------|---------|
| `talks_shown` | 8 | 5..10 |
| `posts_shown` | 3 | fixed by spec, kept configurable |
| `demote_after_days` (D) | 60 | no commits in D days means demote proposal |
| `promote_commits` (N) | 10 | min commits for promotion |
| `promote_window_days` (M) | 30 | window for N |
| `owned_owners` | `[rhuss, AgentTacho, k8spatterns]` | accounts whose public non-fork repos count toward total |
| `owned_extra_repos` | `[jolokia/jolokia, fabric8io/docker-maven-plugin]` | extra owned repos |
| `abbreviations` | `[e.g., i.e., vs., etc., approx.]` | ignored by sentence counter |
| `scan_roots` | `[~/Development, ~/Work/projects]` | local scan roots (skill only) |
| `feed_url` | `https://ro14nd.de/index.xml` | blog feed |
| `talks_repo` | `ro14nd-talks/archive` | talks source |

## Talk (parsed, not stored in profile.yaml)
`year` (int), `month` (int or null), `title`, `url` (nullable, resolved), `venue` (string, may be empty), `extras` (list of {label, url}), `order` (index within the year, for stable tie-breaks).

Ordering (FR-013): `year` desc; within a year, dated entries first by `month` desc (ties: later archive position first), then undated entries in archive order.

## BlogPost (parsed)
`title`, `url`, `date` (`YYYY-MM-DD`).

## RepoInfo (from GitHub)
`full_name`, `html_url`, `stars` (int), `private` (bool), `fork` (bool), `archived` (bool).

## Snapshot (`data/snapshot.json`)
```json
{
  "repos": {"rhuss/cc-spex": {"full_name": "rhuss/cc-spex", "stars": "123", "url": "https://github.com/rhuss/cc-spex"}},
  "total_stars": "4.3k",
  "talks": [ { "year": 2026, "month": 9, "title": "...", "url": "...", "venue": "...", "extras": [] } ],
  "talk_years": [2013, 2014, 2015, 2026],
  "posts": [ { "title": "...", "url": "...", "date": "2026-10-21" } ]
}
```
Keys sorted; no timestamps or status. Each top-level key is replaced only when its source fetch succeeded. Star counts are stored as displayed (strings formatted like the README, `1234` becomes `"1.2k"`), so the file only changes when the rendered page changes.

`talk_years` is the sorted, unique list of every year heading in the talks archive, including headings without any talk. The talks-per-year chart spans from the earliest to the latest year in the union of `talk_years` and the talk years, with zero for years without talks (FR-007). `talks` and `talk_years` come from the same fetch and form one source unit: both are replaced on success and both are kept on failure. An archive with year headings but no talks is a successful fetch (`talks` is empty); an archive without any year heading is a source failure.

## State transitions
- Source fetch: `ok` → snapshot key replaced; `failed` → snapshot key kept, one warning for the source; `failed` with no snapshot key → items omitted, one "currently unavailable" note per section of that source.
- Section: source without any value → heading plus "currently unavailable" note; source with values → the items that have values; no item to show (for example an empty feed, or every entry of a project group gone) → section hidden.
- Repo: `public` → rendered; `renamed` → rendered with new name + warning; `private/missing` → omitted + warning (data-file entry only).

## ScanReport (output of `profilegen scan --json`)
```json
{
  "repos": [ {"repo": "tals/corgi", "local_path": "~/Development/context-engineering/corgi", "public": true,
              "commits_window": 14, "days_since_last_commit": 2, "listed_in": "main_projects"} ],
  "proposals": [
    {"kind": "demote", "repo": "rhuss/debaser", "reason": "no commits in 74 days"},
    {"kind": "promote", "repo": "rhuss/cc-blog", "reason": "23 commits in last 30 days"},
    {"kind": "remove", "entry": "more_tools[3]", "reason": "repository not public or missing"},
    {"kind": "rename", "repo": "rhuss/agentmeter", "new_repo": "AgentTacho/agenttacho"},
    {"kind": "new_tool", "repo": "rhuss/cc-cfp", "reason": "public, active in last 12 months, not listed"}
  ]
}
```
Non-public repos never appear in `repos` or `proposals`.
