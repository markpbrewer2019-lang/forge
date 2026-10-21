# Source-grounded planner continuation

User requirements: continue the checkpoint; every available craft-relevant source modifier and base must be locally accessible, with actual levels/weights/stats and provenance. Exact starting state plus exact final target must drive a complete route before any action. Keep unknown mechanics blocked. Full continuation specification is the user attachment dated 2026-10-21; no Warmonger-specific logic.

## Existing checkpoint

Private main: 5ce785ef13961ffbf62a0cc1b7efdddf602e379e. 113 tests passed. Persistent source library: 63 discovered absolute modifier-category URLs, 23,753 class/pool rows, 51 historical API quotes. No verified live crafting dataset. Relative category links were missed by the first source discovery; raw source semantics and base statistics have not been projected for planning.

## Authorized implementation sequence

1. Extend the existing source adapter, not a new ingestion stack: resolve actual relative category links, preserve all exposed rows and base cards, retain source IDs, required modifier levels, displayed weights, stats and unknowns. Establish field meanings against preserved source presentation code. Build offline exact lookup/filter and independently compare stored rows with raw source inventory; distinguish ingestion failures from unavailable source fields/pages.
2. Extend canonical state/transition rules for generic irreversible commitments, socket occupation and evidence-backed capacity changes. An action cannot remove a permanent installed property, and a planner cannot select a commitment whose remaining graph fails final requirements. Add synthetic regressions; no fabricated real mechanics.
3. Give temporary modifiers explicit lifecycle obligations in the existing replay/search path, particularly active blockers that remain protected until a release condition. Use full-route successor/predecessor viability, exact replay and the existing economics; preserve existing hash compatibility and Golden 6 gates.
4. Integrate source-to-planning diagnostics: unresolved data/rules must identify exact blocking fields, not output plausible recipes. Re-run all tests, actual offline lookups, source coverage audit and existing 20,000-trial proof. Obtain independent code review and fix Important findings.

## Scope and evidence rules

The supplied detailed continuation requirements authorize extending the existing flows. Do not restart design approvals, replace working engines, or invent source mappings. Source display semantics are source facts, not proof of every in-game interaction. Every denominator and coverage percentage must name its inventory; hidden/unavailable source data is not counted as ingested. Readiness for the blind real craft remains NO until its state, mechanics, pools and prices are all proven.

## Closeout

Report actual implementation, tests, available/matched/missing/mismatched rows and percentage, exact remaining mechanics, blind-craft readiness YES/NO and remaining work. Commit appropriate source after tests and audit; preserve the local source library outside disposable caches.
