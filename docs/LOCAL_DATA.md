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

The synchronizer follows relative and absolute links actually present in PoE2DB's Modifiers index. With `--all-items`, it also follows the Items index and auxiliary modifier categories. It parses literal `ModsView` JSON without executing JavaScript and preserves HTML tables and base cards. Existing sources are reused offline. Downloads are sequential, bounded and do not follow redirects. Automatic HTTP caching honors `no-store`; `--archive-public-pages` explicitly archives public unauthenticated source documents as user-requested research data. This flag does not change the poe.ninja client's HTTP cache rules. A changed robots contract or modifier schema blocks acquisition; failures preserve good saved records.

`--refresh` explicitly reacquires PoE2DB pages. This does not refresh market prices. For a new market observation, run the existing `refresh-currency` command with an actual discovered league and then import its JSON result with `--market-file`. The original API cache still preserves the exact market response bytes; the source library additionally indexes its canonical JSON fields. No alternative currency provider or manual price override is accepted.

## Evidence limits

- Saved rows are source observations with INFERRED status. Version and league remain UNKNOWN when the source does not establish them.
- `DropChance`, generation IDs, families and other values are retained exactly as reported. Their presence is not proof of weight semantics, action interactions, tier numbering or pool completeness. No solver dataset is automatically fabricated from them.
- Snapshot age never resets merely because a local record is queried or reimported. Market observation time stays attached to every quote. Historical prices remain historical.
- PoE2DB's data schema includes empty generic category keys. Their presence does not establish that a mechanic exists in PoE2.
- Source counts are distinct from verified engine coverage. The current store deliberately reports zero automatically verified solver records.

Tests exercise offline recall, process-style reopening, immutable revision history, raw corruption, schema changes, source restrictions, preserved API prices/times, and CLI dispatch. They use labeled test data; real observations are stored separately.

## Initial acquisition checkpoint (superseded)

The initial acquisition saved all **63 category URLs discovered in the live Modifiers index**, comprising **23,753 modifier rows** across those categories, plus **51 historical API currency observations**. Rows can repeat across item classes; this is not a count of unique verified modifiers or a claim of all PoE2DB coverage. `local-data/sources/coverage.json` contains the actual local inventory and zero acquisition failures. Every raw blob was hash-checked, and live local modifier/currency lookup succeeded in a new process with HTTP access disabled.

Final verification: **113 tests, zero failures/errors**, including 14 source-recall regressions. The existing six-mod synthetic simulation still agrees with exact EV 23. Independent review identified a changed-index false-success path and legacy market-time relabeling; both were reproduced by failing tests and fixed before completion.

## Source catalog and current recall

Latest continuation: `SOURCE_ACTIONS_REPORT.md`, 158 passing tests and 33,069 matched captured rows. `catalog-action` accepts `{"record_id":"Chaos_Orb"}` for a complete-description canonical proposal and missing proof fields. It is offline and leaves evidence INFERRED. `build-craft` lists supported source variants, including exact-name Omen relationships, without player hints. Canonical `unresolved_rules` remain blocking. Currency/other display styles and reward references are now included; affirmative conflicting properties still block even when a reference lacks a description.

```text
python tools/sync_sources.py --all-items --catalog --archive-public-pages --market-file market-data/currency.json
python -m forge catalog-build
python -m forge catalog-audit
```

The JSON requests for `catalog-query` and `catalog-rule` are:

```json
{"filters":{"kind":"modifier","item_class":"Wands","pool":"normal","min_ilvl":1,"max_ilvl":80,"text":"maximum Life","limit":20}}
```

```json
{"filters":{"kind":"base","record_id":"Rusted_Cuirass"}}
```

```json
{"record_id":"Serles_Triumph"}
```

Queries expose exact reported levels, scalar weights or ordered conditional weight entries, source IDs, family/filter metadata, base stats, equip requirements and raw source references. Query/build/audit use the local library without HTTP. Static rows with missing descriptions/weights are retained explicitly. Conditional weights remain conditional; no scalar value or condition match is invented. See `SOURCE_FIELD_CONTRACT.md` for the presentation-field mapping and its limits.

The audit counts raw JSON/table/card structures separately from projection and checks every projected payload plus the indexed columns driving queries. A projection count gap, missing row, changed indexed field or checksum failure prevents a clean audit. Its denominator is the **captured source inventory**, not hidden game data or a claim that every site page has been discovered. `inventory.json` records discovered/saved URLs and SOURCE_UNAVAILABLE versus INGESTION_FAILURE. Counts are source occurrences across page/class/pool scopes, not unique verified game modifiers.

`build-craft` without a supplied reviewed dataset resolves the starting base and exact target IDs through this library, checks available level requirements, and returns specific missing-source/interpretation/rule diagnostics. It produces no Golden 6 until the actual craft is provable. This preflight is not the finished real-game solver.
