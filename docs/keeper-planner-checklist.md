# Keeper planner continuation checklist

User scope: resume existing Forge; do not rebuild, rediscover sources, invent mechanics, spend game currency or contact third parties. Finish and verify this implementation slice before GitHub setup, then create a private repository `forge` after a secret audit.

## Starting point

- Existing canonical state, action/pool/legality engine, exact replay, exact route EV, probability, Monte Carlo, budget distributions, source ingestion and API client: present.
- Previous verified baseline: 78 tests. Fresh baseline reproduced: 78 tests, 15.800 seconds, pass.
- In-progress modules on disk: `keepers.py`, `ladder.py`, `pipeline.py`, policy iteration and provenance changes in existing modules. Not wired through CLI or covered by new integration tests at handoff.
- No Git metadata, NEXT_PHASE.md or durable checkpoint found. Existing reports describe the earlier 78-test scope.

## Implementation and verification

- [x] Reuse existing engines; preserve saved dataset hashes and original immutable source records.
- [x] Connect `build-craft`, `audit-ladder`, and `compile-golden6` CLI commands.
- [x] Synthetic six-exact-mod full route, keeper-safe miss/recovery, whole-route selection.
- [x] Deterministic declared victim removal; unknown omen/special-pool interactions block.
- [x] Typed provenance; simulator evidence cannot become verified live mechanic or state evidence.
- [x] Legacy dataset hashes replay unchanged.
- [x] Keeper graph audit and conditional compiler instructions verified; search remains explicitly strict-monotone. General restart/fallback search is not claimed.
- [x] Independent read-only code review and test-backed Important fixes.
- [x] Final full suite: 99 tests passed in 33.875 seconds, including three repository-audit tests. Integrated seeded 20,000-trial simulation: mean 22.9649 versus exact 23, no disagreement.
- [x] Verification writes a source-hash manifest and durable reports; versioned continuation checkpoint follows.
- [x] Only then: source-control exclusions, secret audit (68 staged files, zero findings), private GitHub repository and verified upload. The remote checkpoint tree equals the local audited index tree: `f7afb03689246202600c905b777be59e88c3320b`.
- Source checkpoint: `61f308167665039b745dddb4d6787680d5acfb76`, private repository `https://github.com/markpbrewer2019-lang/forge`, branch `main`. Final documentation closeout follows this checkpoint.

## Execution rulings

- Preserve the existing implementation rather than delete/recreate it to retrofit a test-first workflow. The user's explicit resume/no-rebuild instruction takes precedence over a newly installed skill's delete-and-rewrite advice. New bug fixes use observed failing regression tests. Cost if wrong: previously written code needs stronger review, which is being performed independently.
- Do not repeat design approval or create a new architecture process: the user supplied the exact continuation scope and authorized implementation. Cost if wrong: an interface decision might need adjustment; public compatibility tests and the review check it.
- No skill Git/worktree scripts can operate on a nonexistent Git history. Follow the user's ordering: finish source verification first, then establish a clean local Git checkpoint and private remote. Cost if wrong: no pre-existing Git diff; preserve tests, review notes and source-hash checkpoint evidence instead.

## Independent review disposition

- Final: fixed non-action provenance bypass — new state/modifier tests failed first, then passed with typed state-fact gates.
- Final: fixed unconditional Golden6 miss recovery — regression failed first; compiler now emits state conditions and separate success/miss instructions.
- Final: fixed price timestamp refresh bypass — stale observation mutation regression failed first; as-of now binds to preserved observation and cannot exceed retrieval time.
- Final: minor (deferred): permissive audit reconstruction after explicitly authorized loss of multiple initial keepers is not implemented. Strict search rejects restart policies and no such route is recommended.
- Final: Ruling: live mechanic correctness, real coverage, selected-league availability and actual live prices were not evaluated by the reviewer because no verified real crafting dataset was supplied and the review was offline. These remain explicit blockers, not claims. Cost if wrong: a user might mistake a synthetic proof for game advice; domain labels and promotion gates prevent that interpretation programmatically.
