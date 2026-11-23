# Idea Inbox

Ideas captured from code reviews for future brainstorming.

### merge-local-and-api-activity

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: A checkout with user.email is the only activity source for its repo, so a stale clone can produce false demote proposals.

> Merging local and API commit timestamps (dedup by SHA) would make FR-021 activity robust across machines.

### explicit-github-login-setting

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: The GitHub login used for the commits API is owned_owners[0], so reordering a star-accounting setting changes scan behavior.

> An explicit settings.github_login (or GET /user) decouples identity from star accounting.

### package-template-as-data

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: The README template fallback only works for editable installs; a built wheel would not contain templates/.

> Ship the template as package data if the generator is ever installed as a wheel.

### http-test-seam-exports

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: http.__all__ re-exports urlopen and Request only as a test seam.

> Misleading public API surface; a private indirection would be cleaner.

### skill-readme-injection-hardening

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: The curation skill drafts prose from third-party READMEs guarded only by a one-line data-not-instructions rule.

> Delimiting, size limits and no URLs from READMEs in drafts would reduce prompt-injection exposure.

### fallback-vs-public-precedence

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: The FR-019 snapshot fallback can keep showing a repo that turned private while GitHub is unreachable.

> The spec should state whether the FR-019 fallback or FR-011 wins for already published entries.

### snapshot-rendered-star-values

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: The snapshot stores raw star counts while the page shows rounded values, so one star on any owned repo creates a snapshot-only commit almost nightly.

> Storing rendered values, or committing on README change only, would remove near-daily noise commits (SC-006 intent).

### bounded-retry-for-transient-errors

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: No HTTP request is retried, so one transient 5xx drops a whole night's GitHub refresh.

> One bounded retry for 5xx and timeouts would improve SC-002 freshness.

### end-to-end-refresh-cli-test

- **Source**: deep-review
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page
- **Summary**: No CLI test drives the real refresh and sources with one failing source.

> Integration seams (token passing, snapshot write, warning output) are only verified piecewise.

### snapshot-hidden-stars

- **Source**: walkthrough
- **Date**: 2026-11-23
- **Reference**: 001-github-profile-page, RUNBOOK.md step 3
- **Summary**: data/snapshot.json stores star counts for More tools entries although the page shows no stars for them, so a new star there (cc-slidev 54 to 55) causes a snapshot-only commit; this contradicts the approved "store only displayed values" decision and SC-006.

> Fix: store stars only for entries whose section renders a star count (main projects, community); keep full_name and url for More tools so rename and visibility fallbacks still work. Add a test that a star change on a More tools repo leaves README and snapshot byte-identical.
