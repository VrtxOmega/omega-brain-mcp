# Changelog

## v2.1.0 — 2026-04-09

**VERITAS Omega Build Gates — 10-gate deterministic build pipeline.**

### Added

**VERITAS Build Gate Pipeline (10 gates)**
- `veritas_build_gates.py` — Pure deterministic gate engine, ~1430 lines, zero narrative framing
- Gate Order: INTAKE → TYPE → DEPENDENCY → EVIDENCE → MATH → COST → INCENTIVE → SECURITY → ADVERSARY → TRACE/SEAL
- Fail-fast by default: any gate returning VIOLATION halts execution
- `veritas_run_pipeline` — Full pipeline runner with final verdict + cryptographic seal hash

**Build Gate Tools (15 new tools)**
- Individual gate tools: `veritas_intake_gate` through `veritas_adversary_gate`
- Evidence utilities: `veritas_compute_quality`, `veritas_mis_greedy`
- CLAEG tools: `veritas_claeg_resolve`, `veritas_claeg_transition`
- NAFE scanner: `veritas_nafe_scan`

**Resources (5 new)**
- `veritas://spec/v1.0.0` — Canonical specification (read-only source of truth)
- `veritas://claeg/grammar` — Terminal states, transitions, invariants, prohibitions
- `veritas://gates/order` — 10-gate pipeline sequence
- `veritas://thresholds/baseline` — Dev regime numeric thresholds
- `veritas://thresholds/production` — Escalated production regime thresholds

**Evidence Engine**
- Quality(e) = clamp01(0.40×provenance + 0.25×repeatability + 0.20×freshness + 0.15×env_match)
- MIS_GREEDY — Maximum Independent Set greedy algorithm for evidence independence
- Agreement — Numeric interval overlap and binary pass-rate computation

**CLAEG State Machine**
- 3 terminal states: STABLE_CONTINUATION, ISOLATED_CONTAINMENT, TERMINAL_SHUTDOWN
- Prohibited inferences: intent, motive, preference
- Absorbing state: TERMINAL_SHUTDOWN has no exit transitions

**NAFE Guardrails**
- Narrative Rescue detection (explaining away VIOLATIONs)
- Moral Override detection (ethical framing to bypass gates)
- Authority Drift detection (AI assuming ungranted authority)
- Intent Inference detection (inferring developer motive)
- Auto-sealed to SEAL ledger as `nafe_violation`

**Verdict System**
- PASS, MODEL_BOUND, INCONCLUSIVE, VIOLATION (precedence order)
- Final pipeline verdict = worst across all gates

### Changed
- `omega_execute` now dispatches to all 15 Build Gate tools in addition to Brain Core tools
- `omega_brain_report` version identifier updated

### Invariants (added)
- 10-gate order is fixed and acyclic
- CLAEG transitions: absence of allowed transition = prohibition
- TERMINAL_SHUTDOWN is absorbing (no exit)
- FRAGILITY_MAX_MODEL_BOUND = 0.25
- REDLINE_CRITICAL = 0.95, REDLINE_WARNING = 0.80

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
