# profile-curate

A Claude Code skill for curating `profile.yaml`, the data file behind the `rhuss/rhuss` GitHub profile README.

It runs `profilegen scan` to collect facts about local checkouts and public GitHub repositories, then walks through the resulting proposals (promote, demote, remove, rename, new tool) one at a time.
For each accepted proposal it drafts a blurb or tagline from the repository README, which you accept, edit or reject.
It applies the accepted edits to `profile.yaml`, validates the file, renders an offline preview, shows the full diff, and commits and pushes only after you say yes.
Repositories that are not public on GitHub never show up in proposals or in the data file.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (runs the `profilegen` CLI from the profile repo)
- [`gh`](https://cli.github.com/), authenticated (`gh auth status`), for README fetches and visibility checks
- A checkout of the profile repository with push access to `rhuss/rhuss`

## Installation

The skill lives in the `personal-skills` plugin under `~/Development/context-engineering/personal-skills`.
Copy this directory into the plugin's `skills/` directory:

```bash
cp -R skill/profile-curate ~/Development/context-engineering/personal-skills/personal-skills/skills/
```

Restart Claude Code (or reload plugins) so the skill is picked up.
After changes to `SKILL.md` in this repository, copy it again.

## Configuration

The skill looks for the profile repo checkout in this order:

1. A path you name in the request ("curate the profile in ~/src/rhuss")
2. The `PROFILE_REPO` environment variable
3. `~/Work/priv/github-overview`

The thresholds for proposals are set in `profile.yaml` under `settings`:

| Setting | Default | Meaning |
|---------|---------|---------|
| `demote_after_days` (D) | 60 | propose demoting a main project with no commits in D days |
| `promote_commits` (N) | 10 | commits needed for a promotion proposal |
| `promote_window_days` (M) | 30 | window in days for N |
| `scan_roots` | `~/Development`, `~/Work/projects` | local directories that `scan` walks |

## Usage

```
> update my GitHub profile

Scan found 3 proposals: 1 promote, 1 demote, 1 new_tool.

Proposal 1 of 3: promote rhuss/cc-blog (23 commits in last 30 days)
Move it from more_tools to main_projects with this description:
  "..."
Accept, edit, or reject?
```

After the last proposal the skill runs `profilegen validate`, writes a preview to `/tmp/profile-preview.md`, pastes the `git diff profile.yaml` and the commit message, and asks "Commit and push this to rhuss/rhuss?".
Answering no leaves the remote unchanged.

You can also invoke it as `/profile-curate`, or ask to "refresh profile blurbs" to re-draft text for entries already listed.
