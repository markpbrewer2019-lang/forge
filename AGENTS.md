# Forge laws

- POE2 ONLY. DO NOT SUBSTITUTE POE1.
- DO NOT INVENT MECHANICS. UNKNOWN STAYS UNKNOWN.
- THE CRAFT IS PLANNED BEFORE THE FIRST ORB.
- OPTIMIZE THE FULL ROUTE, NOT THE NEXT ACTION.
- TRACK THE EXACT ITEM STATE using the canonical immutable model.
- FUTURE REQUIREMENTS MUST INFLUENCE EARLY RUNGS.
- RECOVERY MUST BE PROVEN through the same transition engine.
- VALIDATION PRECEDES ECONOMICS OUTPUT.
- MECHANICAL VALIDATION PRECEDES GOLDEN 6.
- GOLDEN 6 DOES NOT INVENT CRAFTING LOGIC.
- EVERY DISCOVERED CLASS OF MISTAKE SHOULD BECOME A REGRESSION TEST.
- DO NOT WEAKEN TESTS MERELY TO MAKE THEM PASS.
- Synthetic evidence never verifies a real PoE2 mechanic or pool.
- Missing pool completeness, scope, weights, evidence, or prices must block dependent calculations.
- Keep source access outside the solver. Preserve source snapshots and provenance.
- All real currency market data MUST originate from the poe.ninja PoE2 economy API. No manual prices, alternate providers, PoE1 endpoints, or silent fallback. Preserve the API snapshot and match quotes to it. Synthetic fixtures remain SYNTHETIC.

# Recall saved sources before browsing

- Current continuation: `docs/SOURCE_ACTIONS_REPORT.md`. `catalog-action` exposes offline complete-description proposals. Unresolved rules, removal scope/ties, floor scope, resource identity, source contradictions and unverified evidence remain blocking. Use atomic `remove_add`; never split one currency into independently usable removal/addition actions or hide keeper destruction when the same modifier returns.

- Persistent PoE2DB and poe.ninja observations are in `local-data/sources/`. This is user data; never clear it as disposable cache.
- Read `docs/LOCAL_DATA.md`, then use `forge.source_store.SourceStore` or the `data-status` / `data-search` CLI before revisiting sources. Both are offline; explicit acquisition is `tools/sync_sources.py`.
- Preserve snapshot hashes, URLs, revisions, observation ages and per-field unknowns. Local availability is not verification of game semantics or pool completeness.
- Use `forge.catalog.Catalog` / `catalog-query` for modifier iLvl/weight and base stats; `catalog-audit` independently counts saved raw structures. `catalog-rule` proposals stay INFERRED and blocked until all physical semantics are reviewed. See `docs/SOURCE_FIELD_CONTRACT.md` and `docs/SOURCE_PLANNER_REPORT.md` before continuing planner work.
