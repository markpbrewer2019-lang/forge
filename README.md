# Forge crafting intelligence toolchain

Keeper-planner continuation: `build-craft` now connects exact six-target input, strict keeper-safe policy iteration, replay, full-route pricing, adaptive recovery audit and a conditional Golden 6 compiler. Fresh verification: **99 tests** (96 crafting/integration tests plus 3 repository-audit tests), plus a **20,000-trial** integrated six-mod synthetic proof (exact expected cost 23; simulation mean 22.9649). Read [the keeper planner scope](docs/keeper-planner.md) and [continuation checklist](docs/keeper-planner-checklist.md) for exact boundaries. Real modifier/mechanic coverage remains zero.

Working Python 3.11+ correctness harness. Standard library only. No UI, no recipe-specific solver logic, no real PoE2 recipes yet.

**THE CRAFT IS PLANNED BEFORE THE FIRST ORB.**

## Run

From this directory, with a working Python 3.11+ executable:

```powershell
python -m unittest discover -v
python -m forge demo --output demo.json
python -m forge inspect-item --input examples/inspect.json
python -m forge eligible-mods --input examples/pool.json
python -m forge validate-route --input examples/route.json
python -m forge price-route --input examples/route.json
python -m forge simulate --input examples/route.json --output simulation.json
python -m forge compare-routes --input examples/compare.json
python -m forge plan-ladder --input examples/plan.json --output planning.json
```

Use a working Python 3.11+ installation. On Windows, if `python` is a Store alias, use `py` or the full path to your installed Python executable.

No installation is necessary. Optional packaging: `python -m pip install -e .` enables the `forge` command. This packaging path has not been tested and may need network access for build dependencies.

All commands accept JSON from `--input` or stdin and return JSON, optionally through `--output`. Invalid, blocked, or partial top-level results exit 2. Successful commands exit 0. Reports always identify synthetic versus PoE2 scope where relevant. A route is mechanically `VALIDATED` independently of price availability; only `price-route` certifies both. A user-provided status string is never a validation credential.

Examples pin their dataset hash and use an explicit historical `valuation_at` equal to the saved price timestamp. This makes them reproducible without pretending old quotes are current. `demo` constructs a fresh synthetic dataset and price book. Regenerate examples with `python -m forge.export_examples` into a new directory through its Python API; the append-only regression store intentionally refuses to overwrite an existing identical case.

## Functioning tools

| Command | Responsibility |
|---|---|
| `inspect-item` | Canonical state, exact IDs/tiers/groups/tags, protections, slots |
| `eligible-mods` | Certified complete scoped pool, weights, exclusions and reasons |
| `validate-action` | Evidence, prerequisites, rarity, slots, conflicts, special-state interactions |
| `explain-transition` | Verify the supplied after-state is an actual outcome, then diff it |
| `calculate-probability` | Exact rational probability from shared transitions |
| `replay-route`, `validate-route` | Every positive-probability branch, actual states, assertions, failure locations |
| `future-conflicts` | Structural slot/group/iLvl warnings; recovery can resolve warnings |
| `analyze-target` | Modifier evidence, current methods, local blockers; no unsupported placement claim |
| `failure-tree` | Finite branch graph including retained/lost target progress |
| `recover` | Bounded policy search from exact miss state; incremental repair versus priced restart |
| `price-route` | Exact absorbing-chain EV, completion/settle/failure probabilities, expected visits/resources, rung contributions |
| `compare-routes` | Full-route EV ranking with exact completion and optional budget constraints |
| `budget-distribution` | Exact cost CDF and completion within budget, including zero-cost cycles |
| `analyze-settle` | Deliberate stopping against explicit build requirements and budget thresholds |
| `adversarial-test` | Generate bad-plan mutations and export regression-ready results |
| `market-leagues`, `refresh-currency` | Live PoE2 economy ingestion, shared cache, conditional refresh, error throttling, raw snapshots |
| `market-coverage`, `currency-quote` | Inspect actual API observations, quote availability and provenance |
| `plan-ladder` | Exhaustive finite stationary-policy search, validated forward against exact final requirements |
| `simulate` | Seeded Monte Carlo over the same validated transitions, quantiles, budget exceedance, censoring and analytical checks |
| `coverage` | Known/missing fields, evidence statuses, supported action IDs, pool certificates |
| `ingest` | Normalize reviewed JSON exports, structural validation, raw hash-addressed snapshots, atomic local dataset refresh |
| `normalize-ninja` | Normalize a saved PoE2 currency exchange response; leaves observations INFERRED pending review |
| `store-regression`, `run-regressions` | Append-only JSON cases and independent expectation checks |
| `golden6` | Mechanical and economic gates; groups reachable actions into at most six declared rungs without dropping branches |

Call Python functions directly for the same APIs. See `forge/cli.py` for complete request dispatch. All dataset and plan structures are demonstrated in `examples/`. The plan format is documented in `schemas/craft-plan.schema.json`; semantic validation runs in Python without a JSON Schema dependency.

## Architecture and dependency order

The workspace was empty. Implementation followed the requested P0 dependency order, combining closely coupled stages into one testable vertical slice:

1. P0A: provenance, scoped datasets, canonical immutable item, structural validation, tests.
2. P0B/C: certified pools, declarative actions, legality, transitions, full branch replay and regression errors.
3. P0D/E: exact probabilities, branch graph, proven recovery, replaceable price books, absorbing-chain economics.
4. P0F/G: finite policy enumeration, route comparison, Monte Carlo and adversarial tests.
5. P0H: local normalized ingestion, coverage auditing and live PoE2 economy ingestion. Verified real crafting mechanics and modifier feed expansion remain unfinished.

`source/export -> data.py -> model.py -> engine.py -> routes.py -> economics.py -> planner.py -> optional Golden 6`

The planner enumerates action choices over all reachable states, evaluates the *entire* route with exact mathematics, and only then selects a route. Final requirements are validated first. This satisfies future-aware ordering in the finite proving ground without claiming a scalable backward-regression solver. Failure states with no legal continuation are explicit failure terminals; they do not prevent selection of a different safe policy. Search bounds block optimality claims instead of returning a partial optimum. Unverified available mechanics prevent a global winner claim.

## Synthetic proof

One base, three modifiers (`power`, `speed`, `junk`), six actions, one pool-completeness certificate, seven price quotes. These are invented rules, not PoE mechanics.

| Route | First action | Craft spend | Base | Full expected spend |
|---|---:|---:|---:|---:|
| A: power then speed | 1 | 101 | 10 | 111 |
| B: speed then power | 5 | 6 | 10 | **16** |
| C: speed then random prefix with removal/retry | 5 | 9 | 10 | 19 |

The independent planner selects B without being given these recipes. C has exact success probability 1, expected two rolls and one removal. A separate restart regression proves replacement bases and repeated early investment are included. Simulation executes 20,000 trials for C and compares both spend and completion frequency to analytical values.

## Evidence and trust boundary

All real currency market data must originate exclusively from the **poe.ninja PoE2 economy API**. Real price books require an allowed PoE2 exchange endpoint and league, a preserved response and matching hash, and quotes/units matching that response. Alternate providers, manual overrides, PoE1 endpoints and silent fallback values are rejected. Synthetic prices are permitted only in the separate SYNTHETIC domain. Currency crafting behavior still requires mechanic evidence; the market API does not establish crafting rules. The live client supports the documented PoE2 exchange categories, including Currency, Essences and Ritual; see `forge/currency_source.py`. Multiple category books can be passed as `{"books": [...]}`; units/scopes must agree and conflicting prices block use.

- Only `POE2` and `SYNTHETIC` are valid domains. They cannot share verified evidence.
- Each record pins source/reference, timezone-aware retrieval timestamp, version, league, evidence status and notes.
- VERIFIED means a reviewer asserted the evidence is adequate. Software checks scope and structure; it cannot establish that a reviewer told the truth. There is no cryptographic trust or multi-reviewer workflow yet.
- One complete pool certificate is required for the exact base/action/iLvl scope. Its modifier IDs define the asserted exhaustive universe; present database rows alone never establish completeness.
- Missing eligibility fields, relevant weights, certificates, mechanics, special-state interactions or prices block dependent operations. Unknowns may be ingested but are not guessed.
- State keys include quality, rarity, flags, fractures and protections. Unrecognized flags block actions unless explicitly declared handled. Modifier IDs are exact tier-specific records; numeric rolled stat ranges are not modeled.
- Action operation names describe generic mathematical operations. None is a claim that a real named currency behaves this way.
- Price books pin domain, version, league, quote unit and as-of time. Freshness is checked at valuation. Raw ninja prices remain INFERRED; no automatic verification.

## Bounds and unfinished work

The planner is exponential and deliberately bounded (30 states, 10,000 policies by default). It optimizes almost-sure completion and mean spend within the loaded finite action universe. Route comparison additionally enforces exact budget-completion constraints when given `budget` and optional `min_budget_completion` (default 1). Exact cost distributions have explicit lattice/work bounds and fail closed on overflow. Settle analysis uses supplied modifier requirements and validated continuation costs; it cannot invent build usefulness or market resale value.

The state/action vocabulary currently supports single fixed/pool additions, uniform eligible removal, reset, and declared flag/rarity changes. It cannot represent arbitrary multi-mod generation, stat-value rolls, conditional spawn-weight tables, complex targeting, nonlinear interactions, consumable inventory constraints or real currency semantics without extensions and evidence. Reset with fractures/protections is blocked. No real fracture/lock creation mechanic exists.

Recovery search uses the same planner; it compares incremental spend with a supplied verified restart route. It excludes sunk costs and failure-item resale value. Action resources must explicitly include replacement bases for in-route restart; the first base must be purchased or explicitly owned.

Golden 6 is a developer grouping/gating tool. It preserves required actions and branches but is not a finished concise player-facing explanation generator. The source tree contains no consumer UI or HTTP server.

See `docs/SOURCES.md` for source findings and `COMPLETION_REPORT.md` for this session's measured results and next task.

## Live market workflow

```powershell
python -m forge market-leagues --input examples/live-leagues-request.json --output market-data/leagues.json
python -m forge refresh-currency --input examples/live-currency-request.json --output market-data/currency.json
python -m forge market-coverage --input examples/market-coverage-request.json
python -m forge currency-quote --input examples/currency-quote-request.json
```

`refresh-currency` takes explicit `league`, `version`, `cache_dir` and optional `category` (default Currency). Use a returned league ID; `version=UNKNOWN` is retained in the supplied discovery example because no real mechanic/patch mapping has been verified. Price-dependent crafting remains blocked until that mapping and evidence are adequate. Supply `client_options.user_agent` identifying the deployment and contact when deploying an ingestion worker. Use one shared worker/cache rather than fetching separately for every player.

The client stores exact response bytes and normalized decimal strings. It enforces request intervals, server Retry-After, conditional ETag/Last-Modified refresh, no-cache revalidation and no-store restrictions. A 304 does not freshen old quote observation timestamps. Source errors return BLOCKED, never fallback prices. Refresh commands return PARTIALLY_VALIDATED (exit 2) for successfully ingested but unreviewed market observations; their JSON report distinguishes this from ingestion failure. `prices_file` can point directly to a saved refresh response for inspection or route pricing; route evidence gates remain active.

The checked-in live sample contains 51 actual Currency quotes for Forbidden Rites, observed on 2026-10-20. It is historical evidence, not a perpetual current-price fixture. The as-of time is in `market-data/coverage.json`.
