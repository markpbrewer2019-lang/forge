# Source action execution continuation

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Continue the saved toolchain into executable source-action shapes, preserving unknowns and all previous proofs.

**Architecture:** Extend the existing catalog's BaseItemTypes card extraction, then its description-to-rule adapter. Add atomic remove-and-add and reviewed removal selection to the canonical engine; all planner/replay/economics paths continue to use that engine. Source proposals stay INFERRED until reviewed scoped evidence and all required fields exist.

**Tech stack:** Existing Python standard-library modules, SQLite source library and unittest.

**Spec:** User continuation attachment `0316e1c6-db36-41dc-a777-8682b3846f7b`, existing `docs/plans/2026-10-21-source-planning.md`, and `docs/SOURCE_PLANNER_REPORT.md`.

The user explicitly directed resuming implementation without restarting or repeating completed work. This is an extension of the approved source-to-transition and forward-proof work, not a new design approval cycle. Preserve existing dataset hashes when optional fields are absent. No real mechanic is verified merely by matching text; no PoE1 data or alternate currency provider is allowed.

- [x] Reproduce currency-style BaseItemTypes omission with a failing test; include those cards in projection and independent raw inventory. Preserve source display class separately from item class, all raw HTML and description properties. Rebuild only the local catalog, without refetching completed pages.
- [x] Add failing canonical regressions for remove-and-add as one atomic action, pool eligibility after the victim is removed, rejected invalid branches, explicit removal selection/lowest-level ties, and rarity-changing additions. Implement with exact branch probabilities and provenance through the existing engine, preserving protected/fractured state rules.
- [x] Parse only complete recognized source description patterns into canonical action proposals, including minimum modifier-level floors where explicit. Unsupported text/interactions/distributions remain diagnostic blockers. Integrate proposals into catalog lookup and no-dataset build-craft diagnostics, never fabricate a recipe.
- [x] Verify full-route planner/replay/EV uses composite outcomes without allowing a decision or free stop between removal and addition. Run old/new tests, fresh offline actual-source checks and source audit; independently review and address findings. Save a clean audited checkpoint in the existing private repository.

## Review focus

Completed: all four tasks; 158-test full verification and offline actual-source proof pass. Captured-source audit 33,069/33,069, no missing/mismatched/extra rows. Three independent review findings reproduced and fixed. Ruling: unspecified final rarity is a search decision, as final flags already were; both optimizers and replay now enforce explicit requirements without requiring a caller rarity hint. Ruling: preserve affirmative properties in descriptionless references; missing descriptions are unknown, not assertions of absent effects. Current clean workspace was reused to preserve the existing ignored source library; no parallel implementer edited it. Publication is the previously authorized private checkpoint operation.

Currency versus cosmetic CSS classes; duplicate source occurrences; absent item-class metadata; random versus uniform selection; lowest-level ties; protected/fractured candidates; rejected compound branches without probability renormalization; pool certificates for the composite action; resulting rarity capacities; minimum modifier iLvl versus item/equip level; unverified source proposals; unknown description suffixes/interactions; unchanged legacy hashes.
