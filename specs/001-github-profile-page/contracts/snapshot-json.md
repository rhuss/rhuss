# Contract: `data/snapshot.json`

Machine-written, committed. Shape in [data-model.md](../data-model.md#snapshot-datasnapshotjson).

- Serialization: `json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"`.
- Top-level keys: `repos`, `total_stars`, `talks`, `talk_years`, `posts`. A key is rewritten only when its source fetch fully succeeded.
- Only displayed values are stored. Star counts (`repos.*.stars` and `total_stars`) are strings in the rounded form the README shows (`"312"`, `"1.2k"`), so a star change that does not change the page leaves the file byte-identical. A renderer reading an older snapshot with integer star counts formats them the same way.
- `talk_years` is the sorted list (ints, unique) of all year headings of the talks archive, empty headings included. It is fetched and merged together with `talks`: both are replaced on success, both are kept on failure.
- Must never contain timestamps, run ids, fetch status, or non-public repository names.
- A missing or unreadable file is treated as an empty snapshot (first run).
