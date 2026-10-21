# Local source recall

Forge's persistent source library lives at `local-data/sources/` in this project. It is user data, not a temporary browser cache. Do not delete it during cache cleanup. It contains `sources.sqlite3`, immutable SHA-256-addressed `blobs/`, and a coverage receipt. Runtime data stays outside Git; adapters, tests and these recall instructions are source controlled. Back up the whole directory together, not the SQLite index alone.

## Use the saved data first

From the Forge project directory:

```python
from forge.source_store import SourceStore
sources = SourceStore('local-data/sources')
print(sources.coverage())
print(sources.search('maximum Life', source='poe2db', limit=10))
print(sources.search('exalted', source='poe.ninja'))
```

These methods do not fetch or open any website. They work offline, survive Python/session restarts, and return exact source fields alongside URLs, timestamps, hashes and evidence status. Search is literal, case-insensitive substring matching. Use a distinctive stat phrase or affix name. `raw(snapshot_sha256)` returns the original saved PoE2DB bytes, checking their integrity. `snapshots(url)` lists preserved revisions. Search uses the latest explicitly imported revision per URL.

The JSON CLI provides `data-status`, `data-search` and `data-import`. For example:

```json
{"directory":"local-data/sources","query":"maximum Life","source":"poe2db","limit":10}
```

Pass that request to `python -m forge data-search --input request.json`. A new empty directory is not evidence of source completeness; inspect counts before relying on results.

## Acquisition and refresh

```text
python tools/sync_sources.py --market-file market-data/currency.json
```

The synchronizer follows category links actually present in PoE2DB's Modifiers index, parses the category's literal embedded `ModsView` JSON without executing JavaScript, and preserves the HTML response. Existing sources are reused without network requests. Missing sources are downloaded sequentially with an interval, a response-size cap, no redirects, and no persistence of `no-store` responses. A changed robots contract or modifier schema blocks acquisition; individual category failures are reported without removing good saved records.

`--refresh` explicitly reacquires PoE2DB pages. This does not refresh market prices. For a new market observation, run the existing `refresh-currency` command with an actual discovered league and then import its JSON result with `--market-file`. The original API cache still preserves the exact market response bytes; the source library additionally indexes its canonical JSON fields. No alternative currency provider or manual price override is accepted.

## Evidence limits

- Saved rows are source observations with INFERRED status. Version and league remain UNKNOWN when the source does not establish them.
- `DropChance`, generation IDs, families and other values are retained exactly as reported. Their presence is not proof of weight semantics, action interactions, tier numbering or pool completeness. No solver dataset is automatically fabricated from them.
- Snapshot age never resets merely because a local record is queried or reimported. Market observation time stays attached to every quote. Historical prices remain historical.
- PoE2DB's data schema includes empty generic category keys. Their presence does not establish that a mechanic exists in PoE2.
- Source counts are distinct from verified engine coverage. The current store deliberately reports zero automatically verified solver records.

Tests exercise offline recall, process-style reopening, immutable revision history, raw corruption, schema changes, source restrictions, preserved API prices/times, and CLI dispatch. They use labeled test data; real observations are stored separately.

## Acquisition checkpoint

The initial acquisition saved all **63 category URLs discovered in the live Modifiers index**, comprising **23,753 modifier rows** across those categories, plus **51 historical API currency observations**. Rows can repeat across item classes; this is not a count of unique verified modifiers or a claim of all PoE2DB coverage. `local-data/sources/coverage.json` contains the actual local inventory and zero acquisition failures. Every raw blob was hash-checked, and live local modifier/currency lookup succeeded in a new process with HTTP access disabled.

Final verification: **113 tests, zero failures/errors**, including 14 source-recall regressions. The existing six-mod synthetic simulation still agrees with exact EV 23. Independent review identified a changed-index false-success path and legacy market-time relabeling; both were reproduced by failing tests and fixed before completion.
