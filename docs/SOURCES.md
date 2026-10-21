# Source investigation — 2026-10-20

## poe.ninja / poe2.ninja intended market source

Primary documentation inspected: https://poe.ninja/docs/api

The publisher documents public PoE2 economy endpoints under `/poe2/api/economy/`, including league discovery and currency exchange overviews. Forge's saved-response normalizer uses the documented exchange shape: `core.primary`, `lines[].id`, `lines[].primaryValue`. It does not infer a unit from an old PoE1 API convention. The URL's league and category must match normalization context.

The documentation directs clients to cache, use conditional requests, identify their app/contact, and keep traffic modest. It also recommends a backend proxy for desktop clients. Builds/profile endpoints are outside the permitted integration surface. A future production fetcher should implement those requirements before any automatic refresh.

A first read through the research tool failed. A subsequent live integration using Forge's Python client succeeded after network permission was granted. The league endpoint returned six league IDs. The PoE2 Currency overview for the discovered first league, Forbidden Rites, returned 51 currency quotes, all with values. Exact raw bytes, response headers, ETag, receipt times and normalized data are stored under `market-data/`. The source observation is dated 2026-10-20; see `market-data/coverage.json` for timestamp and digest. Game version remains UNKNOWN and observations retain INFERRED evidence and UNKNOWN price confidence.

This failed read is a tool-access limitation, not a publisher prohibition. The publisher explicitly permits its documented economy endpoints and points developers to the browser Network tab for observing requests.

## PoE2DB

Primary pages inspected:

- https://poe2db.tw/us/Modifiers
- https://poe2db.tw/robots.txt

The modifier page exposes item-category links and modifier tables. The inspected robots response disallows language-prefixed `/marked` and `/markdown_history` paths. This inspection does not establish a supported bulk API or permission for arbitrary harvesting.

No reliably documented complete modifier export/API was established in this session. Forge therefore implements a reviewed normalized-JSON import boundary rather than a guessed HTML parser. No tables were copied into the solver; no live modifier, weight or tier was treated as verified.

Next source work: obtain a permitted structured PoE2DB export or verify one narrow item-class extraction against its original source. Preserve raw snapshots, source-specific IDs, version, per-field unknowns, spawn-weight semantics and a reviewed completeness certificate. If extraction cannot establish complete relevant pools, probability stays blocked.

## Verified real coverage

- Real bases: 0.
- Real modifiers: 0.
- Verified real mechanics: 0.
- Real market snapshots: 1 currency overview, plus 1 league catalog. Currency observations: 51/51 quoted, priced in the API's `divine` primary unit. None is represented as verified market certainty or verified crafting mechanics.

Research observations are documentation findings, not crafting-data ingestion.
