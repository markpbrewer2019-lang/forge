# PoE2DB source display contract

Reference: https://cdn.poe2db.tw/js/ModsView.f39fca410dd746d3.js

Preserved local asset: `local-data/bootstrap/ModsView.js`; SHA-256 `967efb19b218b4d92a7129fb60ee694ea3fee3a3015dd75cf7dd64d6cbb0a2a5`. Its receipt preserves the actual script URL found on the source page. The raw asset remains local source data, outside Git.

| Source field | Observed presentation meaning | Limit |
|---|---|---|
| `Level` | Modifier item-level threshold used by the source's maximum-iLvl filter | Does not establish every acquisition method's eligibility |
| `DropChance` | Relative displayed weight used by the source's weighted selection function | Does not certify game probabilities or conditional pool completeness |
| `ModGenerationTypeID` + `gen` | Source's Prefix/Suffix label | Unknown/unmapped IDs remain unknown |
| `ModFamilyList[0]` | First family used by the source's display grouping | Not a certification of all exclusion interactions |
| displayed tier | Rank of distinct levels descending within one view/pool/generation/first-family group | Separate from source-provided `Tier`; never inferred across views |
| static table `Weight` | Scalar or ordered condition/weight entries | Conditions are preserved; their matching/evaluation remains unverified |
| base card `Requires: Level` | Character equip requirement | Never substituted for modifier iLvl or minimum drop iLvl |

The source asset also contains legacy/shared crafting and filter code. Forge imports **no action semantics** from it. Legacy filter fields are retained as source filter values, not certified PoE2 crafting tags. PoE1 currencies, fossil behavior, influences and similar code are not a real PoE2 mechanic model.

The catalog is an offline source reference. All projected rows remain INFERRED. Complete action/base/level pools, numeric roll distributions, conditional weighting, physical state rules and game/league scope still need reviewed evidence before solver promotion. `catalog-rule` emits an INFERRED physical-rule proposal with unresolved fields; it cannot turn parsing into verification.
