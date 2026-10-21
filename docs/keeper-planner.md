# Keeper-preserving ladder pipeline

This phase connects the existing engines. It does not establish real-game mechanic or modifier coverage.

`build-craft` accepts the normal JSON dataset/item/price inputs and six exact modifier IDs, or objects `{ "modifier": "id", "tier": 1 }`. A supplied tier must match the immutable modifier record. Numeric stat-value targets block: rolled values are not yet canonical state fields.

```powershell
python tools/verify.py
python -m forge build-craft --input reports/keeper-request.json --output reports/craft.json
```

The verification tool constructs an explicitly synthetic request. It runs the full test suite, then a complete six-target craft and a seeded 20,000-trial simulation. The generated `reports/` directory is durable local evidence, excluded from Git. Source, tests, schemas and verification tooling remain tracked.

## Reused components

Canonical `Item`, legality, eligible pools, transitions, branch replay, exact economics, budget CDF, Monte Carlo, currency API price books and source snapshots remain the authorities. No solver scrapes sources or maintains a contradictory item model. User keeper intent is separate from physical `protected`/`fractured` state: declaring a keeper never magically protects it from random removal.

## Proven search scope

The `policy_iteration` option in the existing `plan_ladder` builds the reachable legal graph, removes actions whose positive-probability outcomes violate the keeper policy, computes almost-sure winning states and a proper initial policy, then improves it with exact rational linear solves. It minimizes full-route expected spend, then expected action count. The costly-first/cheap-later tradeoff is evaluated through the entire route.

Default end-to-end scope is strict preservation of initial keepers and all exact targets as acquired. State and iteration limits block optimum promotion. Candidate policies from the improvement sequence are available for completion/budget filtering. This is not an exhaustive constrained-cost optimizer, and the output says so. Acceptable settles currently support explicit dead-end fallback states, not market utility optimization or arbitrary optimal stopping.

## Replay, recovery and economics

Keeper-aware route replay and audit retain actual before/after states, source evidence, affix capacity, groups, current keepers, disposable modifiers, objectives, branch probabilities and classifications. Classification vocabulary is ADVANCE, RETRY_SAME_RUNG, FALLBACK_ONE_RUNG, RESTART, ACCEPT_SETTLE; unknown candidate transitions are BLOCKED_UNKNOWN diagnostics. Replay checks one-rung regression against the historical peak rather than allowing successive unbounded one-rung losses. Search currently declines non-monotone fallback/restart policies instead of inventing them.

Audit reports exact probability of ever losing keepers or restarting, not just one-step risk. Whole-route economics exposes expected action visits, resources, attempts and cost drivers. Authorized loss of multiple initial keepers followed by multi-action restart reconstruction is not implemented; strict search rejects such policies. A reviewer identified the permissive audit-policy limitation; it is documented rather than claimed supported.

## Evidence and immutable data

Evidence can carry SOURCE_FACT, VERIFIED_GAME_OBSERVATION, SIMULATOR_OBSERVATION, MATHEMATICAL_ASSUMPTION or UNKNOWN and an exact supporting fact. Real mechanic and state/pool facts require verified source/game evidence. Simulator observations and assumptions cannot silently become verified live-game facts. Probability normalization remains labeled mathematical arithmetic, separate from evidence that a roll mechanic applies.

Legacy synthetic evidence retains its explicit laboratory interpretation. Optional new fields are omitted when absent, preserving existing dataset hashes and saved plans. The planner does not change source records or weights. Unknown omen interactions and special acquisition pools fail closed; no PoE2 currency or Desecration behavior has been implemented from memory.

## Golden 6 gate

`compile-golden6` requires a full keeper-aware replay and economic validation. It groups by exact-target progress into at most six objective steps, names every selected action, retains state conditions and outcome-specific retry/advance rules, and hides the full graph from the player output. For example, exact junk removal is conditional on the junk miss; success advances immediately without removal. The developer audit keeps the full graph for inspection.

Real end-to-end recommendations require explicit selected league, matching dataset/API prices, verified game version and a current price observation. A price book's mutable `as_of` cannot renew an old observation; it must match the preserved source time and cannot exceed retrieval time. Historical unreviewed market samples are not current economic recommendations.

## Actual remaining blockers

Real bases/modifier pools/mechanics remain unverified in this project. No unfamiliar real six-mod craft is certified. The synthetic universe proves orchestration and arithmetic only. Full numeric rolls, general non-monotone keeper recovery, scalable constrained optimization, true settle resale valuation and complex real acquisition interactions remain unfinished.
