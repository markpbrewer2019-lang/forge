# Source-control scope

The private repository includes all Forge source modules, original and keeper-pipeline tests, synthetic fixtures/regression cases, schemas, provenance/ingestion/market integration code, command-line tooling, documentation, verification scripts and the versioned continuation checkpoint.

Intentionally excluded, preserved locally:

- Environment/credential files and key material: .env variants (except a safe .env.example template), SSH/AWS/Codex machine settings, private keys and credential JSON files. Authentication is handled by the connected GitHub plugin or normal user sign-in; no token is written into source.
- Python bytecode, caches, virtual environments, build products, temporary files, logs and editor settings: machine-specific and reproducible.
- reports/ and root generated result JSON files: reproducible verification/demo output, not implementation or canonical data. `python tools/verify.py` recreates the keeper proof and test evidence.
- market-data/: live response caches, raw snapshots and historical league/price observations. They remain local evidence; committing them would distribute stale prices and incidental HTTP metadata as project data. The client, schemas, source enforcement, normalization and tests remain included.
- local-data/: the persistent source library (SQLite index, immutable public source bodies and acquisition receipts). This is preserved user data, not a disposable cache. Keep the directory intact and back it up as described in docs/LOCAL_DATA.md; its adapters, tests and recall instructions are included in Git.

The Git index is audited before commit by `tools/audit_repository.py`: exact staged bytes, known secret/token/key patterns, forbidden credential filenames and unexpected binary files. Findings include only paths/line numbers/categories; matched values are never printed. A clean audit is evidence against these patterns, not a guarantee against every possible undisclosed secret format. The candidate file list is also reviewed before upload.

Required Forge functionality is not removed or rewritten for repository cleanliness. No real crafting-data completeness is implied by the repository or infrastructure.
