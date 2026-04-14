<div align="center">
  <img src="https://raw.githubusercontent.com/VrtxOmega/Gravity-Omega/master/omega_icon.png" width="100" alt="VERITAS" />
  <h1>OMEGA BRAIN MCP + VERITAS BUILD GATES</h1>
  <p><strong>Standalone Model Context Protocol Server with Built-In Intelligence + Deterministic Build Pipeline</strong></p>
  <p><em>Two files. One dependency. Full sovereign cognition + 10-gate build verification.</em></p>
</div>

![Status](https://img.shields.io/badge/Status-ACTIVE-success?style=for-the-badge&labelColor=000000&color=d4af37)
![Version](https://img.shields.io/badge/Version-v2.1.1-blue?style=for-the-badge&labelColor=000000)
![Stack](https://img.shields.io/badge/Stack-Python%20%2B%20MCP-informational?style=for-the-badge&labelColor=000000)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&labelColor=000000)

[![omega-brain-mcp MCP server](https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp/badges/card.svg)](https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp)

---

A self-contained MCP server that gives AI agents verifiable provenance, cross-session memory, a cryptographic audit trail, and a **10-gate deterministic build evaluation pipeline**. No external server required.

> **SYSTEM INVARIANT:** VERITAS Build does not determine whether code is 'good.' VERITAS Build determines whether code survives disciplined attempts to break it under explicitly declared primitives, constraints, test regimes, boundaries, cost models, evidence, and policy.

## Architecture

| Layer | Component | Role |
|-------|-----------|------|
| **Brain Core** | Vault (SQLite) | Persistent session/entry storage with FTS5 search |
| **Brain Core** | SEAL Ledger | Append-only SHA3-256 hash chain for tamper-proof audit |
| **Brain Core** | RAG Provenance | Semantic embedding store with 3-tier engine (ST/fastembed/TF-IDF) |
| **Brain Core** | Cortex | Tri-Node approval gate with steer/block modes |
| **Brain Core** | Handoff | SHA-256 sealed cross-session memory transfer |
| **Build Gates** | 10-Gate Pipeline | INTAKE→TYPE→DEPENDENCY→EVIDENCE→MATH→COST→INCENTIVE→SECURITY→ADVERSARY→TRACE/SEAL |
| **Build Gates** | Evidence Engine | Quality(e) formula, MIS_GREEDY, Agreement computation |
| **Build Gates** | CLAEG | Constraint-locked state machine with 3 terminal states |
| **Build Gates** | NAFE Scanner | Narrative failure signature detection |

## Verdict System

| Verdict | Precedence | Meaning |
|---------|-----------|---------|
| `PASS` | 0 (lowest) | All gates satisfied. Artifact is deployable under declared regime. |
| `MODEL_BOUND` | 1 | Gates pass but resource/coverage/confidence near redline. Deploy with monitoring. |
| `INCONCLUSIVE` | 2 | Insufficient evidence or timeout. Cannot affirm or deny. Block deploy. |
| `VIOLATION` | 3 (highest) | Constraint failure, security vulnerability, or test failure. Block deploy. |

## Tools (26)

### Brain Core (12)

| Tool | Purpose |
|------|---------|
| `omega_preload_context` | Episodic task briefing: RAG + vault + sealed handoff + VERITAS score |
| `omega_rag_query` | Semantic search over RAG provenance store |
| `omega_ingest` | Add text fragment to RAG store |
| `omega_vault_search` | Full-text keyword search across vault entries |
| `omega_cortex_check` | Tri-Node approval gate with similarity scoring |
| `omega_cortex_steer` | Cortex correction mode — steer drifting args or hard block |
| `omega_seal_run` | Append tamper-proof S.E.A.L. entry to audit ledger |
| `omega_log_session` | Write session record to vault |
| `omega_write_handoff` | SHA-256 sealed cross-session handoff |
| `omega_execute` | Cortex-wrapped meta-tool — default execution path |
| `omega_brain_report` | Human-readable audit report |
| `omega_brain_status` | Unified brain health: vault stats, fragment count, ledger entries |

### Build Gates (15)

| Tool | Purpose |
|------|---------|
| `veritas_intake_gate` | Gate 1/10: Canonicalize, validate fields, compute ClaimID |
| `veritas_type_gate` | Gate 2/10: Primitives, domains, operators, symbols |
| `veritas_dependency_gate` | Gate 3/10: SBOM, CVE, integrity, licenses, depth |
| `veritas_evidence_gate` | Gate 4/10: MIS_GREEDY, Quality(e), K/A/Q thresholds |
| `veritas_math_gate` | Gate 5/10: Constraint satisfaction via interval arithmetic |
| `veritas_cost_gate` | Gate 6/10: Resource utilization vs redline thresholds |
| `veritas_incentive_gate` | Gate 7/10: Source dominance and vendor concentration |
| `veritas_security_gate` | Gate 8/10: SAST, secrets, injection, auth, crypto |
| `veritas_adversary_gate` | Gate 9/10: Fuzz, mutation, exploit, outage, spike |
| `veritas_run_pipeline` | Full 10-gate pipeline — final verdict + seal hash |
| `veritas_compute_quality` | Compute Quality(e) for single evidence item |
| `veritas_mis_greedy` | Run MIS_GREEDY algorithm on evidence items |
| `veritas_claeg_resolve` | Map verdict to CLAEG terminal state |
| `veritas_claeg_transition` | Validate state transition (absence = prohibition) |
| `veritas_nafe_scan` | Scan for NAFE failure signatures in AI text |

## Resources (9)

| URI | Description |
|-----|-------------|
| `omega://session/preload` | Auto-fetched startup: RAG + handoff + vault context |
| `omega://session/handoff` | SHA-256 verified cross-session handoff |
| `omega://session/current` | Session ID, call count, data directory |
| `omega://brain/status` | DB stats, embedding engine, ledger count |
| `veritas://spec/v1.0.0` | Full canonical VERITAS Omega Build Spec |
| `veritas://claeg/grammar` | Terminal states, transitions, invariants, prohibitions |
| `veritas://gates/order` | The 10-gate pipeline sequence |
| `veritas://thresholds/baseline` | Dev/baseline regime numeric thresholds |
| `veritas://thresholds/production` | Escalated production regime thresholds |

## Quick Start

### Requirements

- Python 3.11+
- `pip install mcp`

### Optional (better embeddings)

```bash
pip install fastembed              # ONNX embeddings, ~30MB
pip install sentence-transformers numpy  # Best quality, larger
```

### Configure in Claude Desktop / Antigravity

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["path/to/omega_brain_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### SSE Mode

```bash
python omega_brain_mcp_standalone.py --sse --port 8055
# Endpoints: GET /sse, POST /messages
```

## File Structure

```
omega-brain-mcp/
  omega_brain_mcp_standalone.py   # MCP server (~1430 lines) — Brain Core + tool dispatch
  veritas_build_gates.py          # Gate engine (~1430 lines) — pure deterministic logic
  omega_client.py                 # Python client helper
  requirements.txt                # mcp>=1.0.0
  pyproject.toml                  # Package config
  tests/
    test_build_gates.py           # Gate pipeline tests
    test_veritas.py               # VERITAS scoring tests
    test_seal.py                  # SEAL chain integrity tests
    test_handoff.py               # Handoff seal/context tests
    test_cortex.py                # Cortex approval tests
    test_vault.py                 # Vault persistence tests
```

## CLAEG State Machine

```
INIT → { STABLE_CONTINUATION | ISOLATED_CONTAINMENT | TERMINAL_SHUTDOWN }
STABLE_CONTINUATION → { STABLE_CONTINUATION | ISOLATED_CONTAINMENT | TERMINAL_SHUTDOWN }
ISOLATED_CONTAINMENT → { STABLE_CONTINUATION | TERMINAL_SHUTDOWN }
TERMINAL_SHUTDOWN → {} (absorbing)
```

**Invariant:** Absence of an allowed transition is treated as prohibition.

## License

MIT

---

<div align="center">
  <sub>Built by <a href="https://github.com/VrtxOmega">RJ Lopez</a> | VERITAS Omega Framework</sub>
</div>