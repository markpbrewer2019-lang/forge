# Source action continuation — 2026-10-21

Resumed `0fd1c91a3366a3eb52795495e18a6cd8af30fa62`, preserving existing components and saved sources. **Blind real-craft readiness remains NO.**

## Implemented and verified

- Fixed BaseItemTypes extraction to include currency/other display styles, rather than only white-item CSS. Existing raw pages were reused without network acquisition. Raw cards, display classes and unknowns remain available offline.
- Added canonical atomic `remove_add`: select a victim under a reviewed rule, validate that intermediate state, then sample the certified addition pool from it. Probabilities multiply across those stages. There is no intervening player decision, free stop or second resource charge. An unsupported/empty branch rejects the action rather than being discarded and renormalized.
- Added explicit uniform/lowest-modifier-level removal selection, eligibility/protection scope and tie handling. Unknown selection/scope/ties block. Rarity-changing additions use resulting-rarity slots, and explicit modifier-level floors filter pools. Both optimizers now choose final rarity when unspecified while enforcing explicit final-rarity requirements.
- Carried actual removal events into planner, replay, lifecycle checks and audit: destroying a keeper and rolling its same modifier ID again still counts as destruction. Distinct victims retain distinct labels even if final states coincide.
- Added `forge/grammar.py` / `catalog-action`: complete source descriptions generate canonical Action proposals with provenance and unknowns. `build-craft` discovers supported source action/Omen variants without player hints. Unsupported clauses/properties remain blocked; canonical `unresolved_rules` also block if only an evidence status is changed.
- Reward-list references without descriptions do not assert absent mechanics. Affirmative identity/properties from all references are compared; contradictions block. A complete described record must cover the observed property union, rather than silently dropping or merging partial facts.

`python tools/verify.py`: **158 passed; 0 failures/errors**. The existing synthetic six-mod proof retains exact EV 23; 20,000 simulations mean 22.9649, zero keeper loss, no analytical disagreement. An invented atomic retry route has exact EV 6 with one charge per attempt.

New regressions cover the above behavior, both optimizers and replay. Independent review found three source/provenance defects; each was reproduced by a failing regression and fixed. Final focused reviews reported no remaining Important finding.

Fresh-process lookup with socket creation disabled retrieved actual Chaos Orb's atomic proposal, Perfect Orb of Transmutation's reported floor 70, and source variants. Real `build-craft` stayed BLOCKED with no Golden 6. Evidence remains in `reports/source-action-proof.json`, `reports/verification.json` and local `catalog-audit.json`.

## Exact captured-source audit

| Measure | Result |
|---|---:|
| Available rows | 33,069 |
| Local matched rows | 33,069 |
| Missing / mismatched / extra | 0 / 0 / 0 |
| Captured-row coverage | 100% |
| Modifier occurrences | 26,575 |
| Base-type card/reference occurrences | 6,494 |
| Distinct source base-type IDs | 2,494 |

This adds 2,643 card/reference occurrences and 258 distinct IDs to the preceding catalog, correcting its presentation-style boundary. Counts include duplicates, non-equipment types and descriptionless references. They do not establish complete stats, hidden fields or every site page.

URLs remain 121/122 saved; `Misc_Map_Items` is HTTP 404, SOURCE_UNAVAILABLE. Source omissions remain 1,296 weights, 38 levels and two descriptions. All 560 conditional-weight rows retain their entries and unresolved condition semantics. No values were invented.

The narrow grammar examines 308 distinct StackableCurrency/Omen IDs: **16 currency action shapes plus one composed Whittling variant**, one Omen relation, and 13 Liquid-item property conflicts. Most other mechanics, including multi-mod actions and most Omen/Essence effects, remain unsupported. Recognition never certifies execution.

## Remaining proof inputs

Reviewed version/league scope; certified applicable base/action/iLvl pools; class/family/exclusion/conditional-weight mappings; physical-state facts; real removal distributions/protection scopes/ties; Omen activation/consumption/compatibility; floor application scope; other currency/Essence/Desecration/fracture/Augment interactions.

Source-resource identity must map to current matching **poe.ninja PoE2 API** quotes. Proposals use explicit unmapped resource identifiers instead of free costs or guessed aliases. Existing quotes remain historical; no alternative provider was introduced.

Numeric rolls, general multi-mod generation/targeting/inventory semantics, inferred temporary lifecycles and general non-monotone recovery/restart synthesis also remain unfinished. The finite reviewed synthetic graph is the proven execution domain. No real recipe, route EV or Golden 6 has been certified.
