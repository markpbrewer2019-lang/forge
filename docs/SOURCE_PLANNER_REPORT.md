# Source-grounded planner checkpoint — 2026-10-21

Continued private `main` from `5ce785ef13961ffbf62a0cc1b7efdddf602e379e`. Existing functionality and synthetic evidence gates were preserved. This checkpoint completes the authorized continuation slice, **not the real-game crafting engine**. Blind unfamiliar real-craft readiness: **NO**.

## Implemented

- Expanded the existing persistent source adapter to relative/absolute modifier links, all discovered Items/Modifiers categories, static modifier tables and base cards. Offline indexed lookup exposes reported iLvl, scalar/conditional weights, scoped display tiers, families, base stats, equip requirements and raw provenance. Missing source fields remain explicit; shared/legacy source filter fields are not promoted to game mechanics.
- Connected `build-craft` without a reviewed dataset to offline base/target resolution and explicit source/mechanic blockers. Added reviewable INFERRED physical-property rule proposals. Actual saved Serle's Triumph description yields permanent/+1 suffix candidate facts, with socket/application/action semantics still unresolved; it cannot be used as a temporary removable component or silently become verified.
- Extended the existing canonical engine with evidence-gated permanent flags, occupied sockets, capacity changes, incompatible properties and action restrictions. Unknown property semantics fail closed. Both existing optimizers audit the entire reachable post-commitment continuation and reject incompatible failure/settle suffixes. Final physical requirements are checked in forward replay. A regression proves a capacity commitment can be selected without caller-supplied final flags.
- Added explicit FINAL_KEEPER, ACTIVE_BLOCKER, TEMP_SETUP, DISPOSABLE and TARGETED_VICTIM lifecycle obligations to existing replay/search. Release conditions use the actual pre-action state; required blockers survive until release, and declared removal/replacement/action restrictions are enforced. **Automatic inference of those lifecycles from real mechanic data is not complete.**

## Verification

`python tools/verify.py`: **138 tests passed, 0 failures/errors**. The preserved synthetic six-mod pipeline forward-validates its ladder and Golden 6: exact full-route EV 23; 20,000 trials mean 22.9649; zero keeper loss; no analytical/simulation disagreement.

Regressions cover permanent removal/replacement, unknown property rules, occupied sockets, incompatible post-commitment routes, both optimizers, temporary blocker release/action/replacement restrictions, exact final physical requirements, relative source links, static/conditional weights, display tiers isolated by source view, raw inventory versus projected rows, indexed-column corruption, and SQLite large-write locking. Independent review found indexed-field audit and conditional-weight gaps; failing regressions reproduced them and their fixes passed. The raw inventory comparison additionally caught two real blank-description rows, now retained.

A fresh process with socket creation disabled retrieved actual saved modifier iLvl/weight, base stats, the Serle property proposal and a historical ninja observation, then returned BLOCKED/no Golden 6 for an unprovable real request. Detailed generated evidence remains in `reports/` and `local-data/sources/`.

## Captured-source coverage

| Measure | Exact result |
|---|---:|
| Available raw source rows | 30,426 |
| Local matched rows | 30,426 |
| Missing rows | 0 |
| Mismatched rows | 0 |
| Extra rows | 0 |
| Row coverage within captured documents | 100% |
| Modifier occurrences across page/pool scopes | 26,575 |
| Base-card occurrences | 3,851 |
| Distinct source base IDs, including non-equipment types | 2,236 |

These counts cover literal JSON modifier arrays, exposed modifier tables and base cards in 122 saved PoE2DB source documents (including source indexes/robots). They are **not unique verified game-modifier counts** and do not establish hidden-field coverage.

Discovery found 78 modifier-calculator categories, 91 Modifiers-index category links and 63 Items-index category links: union 122 URLs, **121 saved**. The remaining `https://poe2db.tw/us/Misc_Map_Items` returns HTTP 404: **SOURCE_UNAVAILABLE**, not INGESTION_FAILURE. Row coverage is against captured source structures, not a claim that every possible site page or hidden API has been discovered.

Within saved rows, the source exposes no weight for **1,296**, no modifier level for **38**, and no description for **2**. These are retained SOURCE_UNAVAILABLE fields. Another **560** rows expose ordered conditional weights: every entry and raw row is retained; their game-condition evaluation remains explicitly unresolved. No weight was invented. The old unscoped source-search row count differs because it indexes direct calculator imports; use `catalog-audit.json` for this expanded projection.

## Remaining work / actual blockers

1. Map preserved observations to a reviewed game version and selected league, certify applicable base/level/action pools, and verify source-to-engine class, group/exclusion and conditional-weight mappings. **Zero real game pools are automatically verified.**
2. Implement and evidence real action transformations/interactions for currencies, Omens, Essences, Desecration, Whittling, fractures and Augments. Verify socket consumption/application/removal restrictions, capacities and other relevant physical state rules. Presentation JavaScript is not a PoE2 action grammar.
3. Model numeric stat rolls, conditional spawn tables, multi-mod generation, relevant targeting and consumable/inventory interactions. Unsupported dimensions block exact-target proofs.
4. Infer temporary roles, acquisition/removal dependencies and release/replacement obligations from reviewed mechanics. Extend strict monotone keeper search to general recovery/restart synthesis and scalable constrained whole-route optimization. Current declared lifecycles and finite synthetic proofs do not establish that capability.
5. Fetch and review current matching selected-league prices through the existing **poe.ninja PoE2 API only**, covering every route resource, then run an unfamiliar starting-item/final-target acceptance case. The 51 saved currency quotes are historical observations, not authorization for current spend.

Until these are established, the real-data pipeline deliberately returns BLOCKED and identifies its missing proof inputs. No real recipe, EV or Golden 6 has been certified.

## Source control

Source, tests, schemas, adapters, CLI tools and documentation are included. Persistent `local-data/`, historical `market-data/`, generated `reports/`, environments/caches and credential categories remain excluded and preserved locally as appropriate. See `SOURCE_CONTROL.md`; the source library must be backed up with its blobs, not deleted as cache. Repository audit scans exact staged blobs before publication; it does not prove coverage of every possible secret encoding.
