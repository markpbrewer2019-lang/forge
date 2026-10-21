# Forge development session — 2026-10-20

Implemented a working, standard-library Python toolchain in a previously empty workspace. Crafting correctness is proven in a synthetic universe; real currency API ingestion is now integrated. **No real PoE2 recipe is currently authoritative.**

## TOOLS BUILT

- Provenance and version/league/domain gates; exact immutable serializable item state and inspector.
- Certified eligible pools with exclusions, exact weighted probability, declarative action transitions and legality checks.
- Transition explanations, structural future-conflict warnings, target inspection.
- Branch-complete route replay/validation with actual-state propagation, expected-state assertions and precise originating-node diagnostics.
- Failure graph, explicit settle/failure terminals, recovery search and repair-versus-restart comparison.
- Replaceable timestamped price books; exact absorbing-chain route cost, expected resource use, rung contributions and completion probabilities. Includes initial bases and explicitly declared replacement bases.
- Independent bounded finite-policy generation and full-route comparison; hard limits prevent partial-optimum claims.
- Seeded sequential Monte Carlo using the shared transition graph; cost quantiles, budget exceedance, censoring and analytical discrepancy checks.
- Reviewed normalized-JSON ingestion with structural validation, source snapshots, content hashes and local refresh; coverage auditing; saved poe.ninja exchange-response normalizer.
- Append-only JSON regression store/runner, adversarial tests, JSON CLI/API, plan JSON Schema and gated Golden 6 developer grouping.
- Live PoE2 economy client: league discovery, documented exchange categories, exact raw snapshots, conditional refresh, shared cache, retry limits, source enforcement, quote lookup and market coverage. Composite category price books reject conflicting prices and mismatched units.
- Exact cost distributions and budget-completion comparison, including zero-cost retry cycles, with bounded computation.
- Safe-settle analysis using explicit build requirements and a validated continuation from the actual item.
- Automatic adversarial mutation generator with regression-ready cases.

Golden 6 remains a developer grouping/gating tool, not a finished player-facing presentation generator. The live market client is implemented and has retrieved actual API responses. Price confidence and crafting evidence remain separate gates.

## TESTS

Executed `python -m unittest discover -v` with the bundled Python executable documented in README.

**78 tests passed; 0 failures or errors. Latest run: 9.992 seconds.** Earlier runs passed 34, 40, 48, 56 and 73 tests during development.

All real currency market data comes exclusively from the poe.ninja PoE2 economy API. Verification requires an allowed endpoint and exact league, a preserved response and content hash, and matching quotes/units. Alternate providers, PoE1 URLs, manual overrides and missing snapshots are rejected. Live ingestion succeeded after network access was granted; no research-tool limitation is treated as a source prohibition.

New tests exercise HTTP cache directives, ETags, retries, malformed-response throttling, category merging, source preservation, exact budget tails, zero-cost cycles, stopping decisions and automated adversarial mutations. Additional callable-tool smoke checks passed for budget distributions, adversarial testing and settle analysis. Their request examples and JSON results are saved alongside the code.

Tests include a 20,000-trial seeded recovery-loop simulation, repeatable seeds, analytical cost/completion comparison, finite search, invalid recoveries, failed and settled branches, replacement-base accounting, source/domain mismatches, missing data and actual CLI subprocess exit behavior.

Five additional persisted JSON regression cases are generated in `examples/regressions/`; their generator/store/runner is exercised by the test suite. They cover fake recovery, missing mechanics, false probability, omitted misses and wrong final state.

Final CLI checks also passed against the saved examples: route validation, route pricing, and all five persisted regressions. Reports are saved in `route-validation.json`, `route-economics.json`, and `regression-results.json`.

The regenerated `demo.json` records 6 search states, 24 enumerated policies, 8 distinct valid routes, a winning full-route expected cost of 16, and a 20,000-trial recovery simulation mean of 18.97855 versus analytical expectation 19. Its simulated p95 spend is 28; analytical disagreement is false.

## REAL POE2 DATA

**0 real bases and 0 real modifiers; 1 real currency overview and 1 real league catalog ingested.** The PoE2 API returned six league IDs. The Forbidden Rites Currency overview contains **51 currency records, all 51 quoted**, in the API's `divine` unit. See `market-data/currency.json`, `market-data/coverage.json`, and exact response bytes under `market-data/http-cache/snapshots/`.

The API observation as-of timestamp is 2026-10-20 22:29:45 UTC (5:29:45 PM America/Chicago). Price evidence remains INFERRED, confidence UNKNOWN and game version UNKNOWN. The ingestion worker supports refresh on invocation; no recurring automation or daemon was created. These snapshots do not verify modifier pools or crafting mechanics.

## REAL POE2 MECHANICS

**0 verified real mechanics implemented.** Named PoE2 currency behavior is unsupported and blocks validation. The generic action vocabulary implements synthetic definitions only. A software interface is not evidence that a currency is supported.

## SYNTHETIC COVERAGE

- 1 invented base and 1 item class.
- 3 exact modifier records, all with known weights, iLvl, side, tier, group, applicability, tags and explicit conflicts lists.
- 6 verified-by-definition synthetic actions.
- 1 scoped complete modifier-pool certificate.
- 7 synthetic price quotes.
- Multiple acquisition orders, probabilistic misses, preservation, removal/retry, restart, deliberate failure/settle terminals and full-route expected-cost selection.

Route A spends 1 on its first rung and 111 overall. Route B spends 5 first and **16 overall**. The planner derives B from the available action graph without receiving either route as a recipe. A third recovery-loop route costs exactly 19 overall and completes almost surely. Initial base cost is 10 in each comparison.

## MISTAKES FORGE CAN NOW CATCH

Overfilled affix sides; nonexistent protected mods; wrong rarity or iLvl; incompatible groups and explicit conflicts; unknown modifiers/mechanics; missing complete-pool evidence or relevant weights; wrong game/version/league; unknown special-state interaction; fake/missing outcome branches; false exact probabilities or route costs; after-states that an action never produces; steps assuming an expected state instead of an actual miss; illegal recovery; closed nonterminating loops; incorrect final modifiers/rarity; stale/missing prices; hidden initial base-cost assumptions; search truncation and simulation censoring.

An avoidable dead-end planner defect was found during review and fixed with a permanent test. A safe route remains selectable even when another action has an irrecoverable branch. Golden 6 also excludes unreachable actions instead of publishing unvalidated dead code.

## MISTAKES FORGE CANNOT YET CATCH

It cannot independently establish that a human supplied truthful evidence or a truly exhaustive pool certificate. Real PoE2 modifier pools, conditional spawn-weight tables, arbitrary multi-mod mechanics, stat-value rolls, specific targeting interactions, actual lock/fracture creation and consumable inventory constraints are not modeled. It cannot certify build usefulness or settle resale value beyond supplied criteria, eliminate market uncertainty, or find a globally best route outside the loaded bounded action graph.

## PLANNING CAPABILITY

Exhaustive deterministic stationary-policy search over the finite reachable state graph; almost-sure exact-target completion; exact full-route expected-spend ranking. Final requirements influence selection of the first action through the complete downstream route. No greedy next-orb choice or hard-coded acquisition order is used.

Default limits are 30 states and 10,000 policies. Exceeding either blocks a global winner. Unsupported available mechanics yield partial validation and suppress an optimum claim. Route comparison now computes exact probability of completion within a supplied budget and enforces the requested threshold (default 1). Exact cost CDFs also return bounded median/p95/p99 quantiles; work-limit exhaustion blocks the result. There is no scalable backward-search optimizer yet.

## DATA COVERAGE

Synthetic modifiers: **3/3 known weights, 3/3 known iLvl, 3/3 affix sides, 3/3 tiers, 3/3 groups, 3/3 applicability/tag/conflict records**. Six supported synthetic action IDs; no missing fixture fields. The single certificate applies only to the declared synthetic base/action/iLvl range.

Real modifier/mechanic coverage: **0 records and 0 pool certificates**. Unsupported item classes and the complete real modifier inventory are UNKNOWN, so no percentage of global real crafting coverage can be asserted. Real market coverage: **51/51 retrieved Currency records quoted**, one league, one category sampled live. Other documented categories are supported by the client but have not been ingested live in this session.

## BLOCKERS

No permitted, stable complete PoE2DB structured feed was established. No reviewed real pool, source-weight semantics, patch/league mapping or crafting-mechanic evidence exists locally. Actual API market observations are now present, with uncertainty retained. The finite enumeration solver needs a stronger search strategy before large production state spaces. These limits prevent trustworthy real craft recommendations, not use of the completed synthetic and market tools.

## NEXT PRIORITY

Integrate **one narrow, reviewed PoE2 item class and one verified acquisition mechanic end to end**: permitted source snapshot, normalized tier/eligibility/weight records, explicit completeness certificate, mechanic evidence, independently checked in-game examples, and an integration regression. Keep every unsupported field and interaction blocked.
