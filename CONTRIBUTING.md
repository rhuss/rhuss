# Working on the profile repository

`README.md` in this repository is generated. Do not edit it by hand; the next refresh overwrites it.
Change `profile.yaml` or the template instead and let `profilegen` render the page.

## Layout

| Path | What it holds |
|------|---------------|
| `profile.yaml` | Curated data: intro, links, badges, main projects, community, books, more tools, settings. All prose on the page comes from here. |
| `templates/README.md.j2` | Jinja2 template for the page layout (headings, order of sections, badges, chart). |
| `data/snapshot.json` | Last successfully fetched live values (stars, talks, posts). Written by the generator and used as fallback when a source is down. Never edit by hand. |
| `assets/books/` | Static book covers referenced from `profile.yaml`. Not downloaded during refresh. |
| `src/profilegen/` | The generator: data model, validation, sources (GitHub, blog feed, talks archive), rendering, scan, keep-alive. |
| `tests/` | Offline tests with recorded fixtures. No test touches the network. |
| `.github/workflows/refresh.yml` | Nightly, manual and push-triggered refresh. |
| `skill/profile-curate/` | Claude Code skill for curating `profile.yaml` (see its README for installation). |

## Commands

Everything runs through `uv`:

```bash
make test         # uv run pytest -q
make validate     # uv run profilegen validate
make render       # fetch live data, rewrite README.md and data/snapshot.json
make preview      # render from the snapshot only, write /tmp/profile-preview.md
```

Direct CLI use:

```bash
uv run profilegen validate
uv run profilegen render [--offline] [--today YYYY-MM-DD] [--output PATH]
uv run profilegen scan --json [--roots DIR ...]
uv run profilegen keepalive --days 50
```

`render --output PATH` writes only that file. It does not touch `README.md` or the snapshot and runs no git commands, so it is safe for previews.
Locally the GitHub token comes from `GITHUB_TOKEN` or, if unset, from `gh auth token`.

Exit codes: `0` success (warnings allowed), `1` validation error (nothing is written), `2` usage error.
`keepalive` exits `0` when a keep-alive commit is needed and `3` when it is not.

## How the refresh works

The workflow "Refresh profile" runs every night at 04:17 UTC, on manual dispatch, and on pushes to the default branch that change `profile.yaml`, `templates/` or `assets/`.

1. `profilegen render` validates `profile.yaml`. A validation error fails the job before anything is committed.
2. Each source (GitHub, talks archive, blog feed) is fetched independently. A failed source keeps its values from `data/snapshot.json` and produces a warning annotation; the job still succeeds.
3. The footer date only changes when the rendered page changes, so runs without changes produce identical files and no commit.
4. `README.md` and `data/snapshot.json` are committed only when they differ from the committed version.
5. If the last commit is 50 or more days old, the job adds an empty keep-alive commit so GitHub does not disable the schedule.
6. The push rebases onto the remote and retries up to three times.

Only the built-in `GITHUB_TOKEN` is used.

## Curating content

Run the `profile-curate` skill in Claude Code. It calls `profilegen scan --json` for facts (activity, visibility, rename and removal candidates), walks through the proposals with you, validates, previews, shows the diff, and pushes only after you confirm.
Editing `profile.yaml` by hand works as well; run `make validate` and `make preview` before pushing.

## Manual checks after the first push

These cannot run offline and need the `rhuss/rhuss` repository on GitHub:

1. Run the "Refresh profile" workflow manually. It must succeed, and it must create a commit only when content changed (run it twice; the second run creates no commit).
2. Open github.com/rhuss in light and dark mode. Check that both book covers or links, the badges and the talks chart render without broken images (SC-007).
3. Time a full curation run with the skill (scan, review up to five proposals, push). It should take less than ten minutes (SC-005).
