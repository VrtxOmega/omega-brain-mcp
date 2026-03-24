# Changelog

## v2.0.0 — 2026-03-24

**First public release.**

Omega Brain MCP is a self-contained MCP server that gives AI agents verifiable provenance,
cross-session memory, and a cryptographic audit trail. No external server required. One file.

### Added

**Core systems (all built-in)**
- **Provenance / RAG** — Fragment ingestion (`omega_ingest`), semantic search (`omega_rag_query`), VERITAS scoring (agreement × quality × independence)
- **Vault** — Local SQLite: sessions, entries, FTS full-text search (`omega_vault_search`), event tape
- **Cortex** — Tri-Node approval gate (`omega_cortex_check`) + correction mode (`omega_cortex_steer`). NAEF hard block at similarity < 0.45, steer window 0.45–0.65
- **S.E.A.L. ledger** — SHA-3 tamper-proof hash chain. Auto-appended on every cortex check, ingest, session log, and execution
- **Handoff** — SHA-256 sealed cross-session memory file. Auto-loaded on restart, auto-written on `omega_seal_task`
- **Context detection** — CONTINUATION / CONTEXT_SWITCH / FRESH_START via keyword overlap (threshold 0.35, intentionally below cortex floor)

**Tools (12)**
`omega_preload_context`, `omega_rag_query`, `omega_ingest`, `omega_vault_search`,
`omega_cortex_check`, `omega_cortex_steer`, `omega_seal_run`, `omega_log_session`,
`omega_write_handoff`, `omega_execute`, `omega_brain_report`, `omega_brain_status`

**Prompts (3)**
- `omega_task_start` — Context-mode aware briefing on task open
- `omega_seal_task` — One-tap session close: autoseal, vault log, SEAL trace, handoff write
- `omega_write_handoff` — Structured close with explicit fields

**Embedding engine (3-tier)**
1. `sentence-transformers/all-MiniLM-L6-v2` — if installed
2. `fastembed ONNX/BAAI/bge-small-en-v1.5` — `pip install fastembed`, zero GPU
3. TF-IDF n-gram 128-dim — always works, no deps

**New in this release**
- `omega_execute` — Cortex-wrapped meta-tool: the default execution path for all internal tools
- `omega_brain_report` — Human-readable audit: SEAL chain tail, cortex verdict counts, VERITAS avg
- `omega_client.py` — Persistent-process client module for external frameworks (thread-safe, async-capable)
- `examples/` — Runnable quickstarts for LangChain, CrewAI, AutoGen, LlamaIndex
- `tests/` — Invariant test suite: cortex thresholds, VERITAS formula, SEAL chain, handoff tamper detection

### Invariants (must not change without major version bump)
- `STEER_FLOOR = 0.45` — NAEF hard block floor
- Hash algorithm: `sha3_256`
- Handoff seal: `sha256`
- CONTINUATION_THRESHOLD < STEER_FLOOR (always)
