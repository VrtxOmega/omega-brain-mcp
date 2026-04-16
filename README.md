<div align="center">
  <img src="https://raw.githubusercontent.com/VrtxOmega/Gravity-Omega/master/omega_icon.png" width="120" alt="VERITAS Omega" />
  <h1>OMEGA BRAIN MCP + VERITAS BUILD GATES</h1>
  <p><strong>Standalone Model Context Protocol Server with Built-In Intelligence + Deterministic Build Pipeline</strong></p>
  <p><em>Two files. One dependency. Full sovereign cognition + 10-gate build verification.</em></p>
</div>

<div align="center">

[![CI](https://github.com/VrtxOmega/omega-brain-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/VrtxOmega/omega-brain-mcp/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/Status-ACTIVE-success?style=flat-square&labelColor=000000&color=d4af37)
![Version](https://img.shields.io/badge/Version-v2.1.1-blue?style=flat-square&labelColor=000000)
![Python](https://img.shields.io/badge/Python-3.11%2B-informational?style=flat-square&labelColor=000000)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square&labelColor=000000)

[![omega-brain-mcp MCP server](https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp/badges/card.svg)](https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp)

</div>

---

A **self-contained MCP server** that equips AI agents with verifiable provenance, cross-session episodic memory, a cryptographic audit trail, and a **10-gate deterministic build evaluation pipeline** — all in two Python files with a single pip dependency.

> **SYSTEM INVARIANT:** VERITAS Build does not determine whether code is 'good.' VERITAS Build determines whether code survives disciplined attempts to break it under explicitly declared primitives, constraints, test regimes, boundaries, cost models, evidence, and policy.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Tools Reference](#tools-reference-26-tools)
- [Resources](#resources-9)
- [CLAEG State Machine](#claeg-state-machine)
- [Troubleshooting](#troubleshooting)
- [Security & Privacy](#security--privacy)
- [License](#license)

---

## Overview

Omega Brain MCP is the cognitive layer of the **VERITAS Omega** ecosystem. It runs as a local MCP server process — no cloud, no API keys, no external server required — and exposes 26 tools and 9 resources to any MCP-compatible AI client (Claude Desktop, VS Code Copilot, Cursor, Windsurf, AutoGen, LangChain, CrewAI, LlamaIndex, and more).

**Brain Core** provides cross-session episodic memory via a local SQLite vault, a semantic RAG provenance store with a 3-tier embedding engine, a Tri-Node Cortex approval gate, and a SHA-3 tamper-proof S.E.A.L. audit ledger. **VERITAS Build Gates** adds a 10-gate deterministic pipeline that evaluates any AI-generated artifact against explicitly declared primitives, evidence, constraints, cost models, security rules, and adversarial scenarios — returning a cryptographically sealed verdict.

---

## Features

- **Zero-config cross-session memory** — vault (SQLite + FTS5) persists sessions, entries, and events across restarts; auto-loaded at startup via `omega://session/preload`
- **Semantic RAG provenance** — 3-tier embedding engine: `sentence-transformers` → `fastembed` ONNX → TF-IDF n-gram (always works, no GPU required)
- **Cryptographic S.E.A.L. ledger** — append-only SHA-3 256 hash chain; every cortex check, ingest, session log, and execution is automatically sealed
- **Cortex approval gate** — Tri-Node similarity gate with hard-block (`< 0.45`) and steer (`0.45–0.65`) windows; blocks NAEF drift before execution
- **Sealed handoff** — SHA-256 signed cross-session memory file; auto-loaded on restart, auto-written on task seal
- **10-gate VERITAS build pipeline** — INTAKE → TYPE → DEPENDENCY → EVIDENCE → MATH → COST → INCENTIVE → SECURITY → ADVERSARY → TRACE/SEAL; fail-fast on VIOLATION
- **CLAEG state machine** — Constraint-locked 3-state machine (STABLE\_CONTINUATION, ISOLATED\_CONTAINMENT, TERMINAL\_SHUTDOWN); absence of allowed transition = prohibition
- **NAFE guardrails** — Detects and seals narrative rescue, moral override, authority drift, and intent inference in AI output
- **Two transports** — stdio (default, MCP standard) and SSE (HTTP streaming for web clients)
- **Docker-ready** — single `Dockerfile`, non-root user, unbuffered I/O
- **Single dependency** — `mcp>=1.0.0`; optional `fastembed` or `sentence-transformers` for better embeddings

---

## Architecture

### Component Map

| Layer | Component | Role |
|-------|-----------|------|
| **Brain Core** | Vault (SQLite) | Persistent session/entry storage with FTS5 full-text search |
| **Brain Core** | SEAL Ledger | Append-only SHA3-256 hash chain for tamper-proof audit |
| **Brain Core** | RAG Provenance | Semantic embedding store — 3-tier engine (ST / fastembed / TF-IDF) |
| **Brain Core** | Cortex | Tri-Node approval gate with steer/block modes |
| **Brain Core** | Handoff | SHA-256 sealed cross-session memory transfer |
| **Build Gates** | 10-Gate Pipeline | INTAKE→TYPE→DEPENDENCY→EVIDENCE→MATH→COST→INCENTIVE→SECURITY→ADVERSARY→TRACE/SEAL |
| **Build Gates** | Evidence Engine | Quality(e) formula, MIS\_GREEDY independence scoring, Agreement computation |
| **Build Gates** | CLAEG | Constraint-locked state machine with 3 terminal states |
| **Build Gates** | NAFE Scanner | Narrative failure signature detection and auto-seal |

### Request Flow

```
AI Client (Claude / VS Code / Cursor / AutoGen / ...)
    │
    │  MCP stdio / SSE
    ▼
┌─────────────────────────────────────┐
│         omega_brain_mcp_standalone  │
│  ┌────────────┐  ┌────────────────┐ │
│  │  Brain Core│  │  VERITAS Gates │ │
│  │  ──────────│  │  ──────────────│ │
│  │  Cortex    │  │  10-Gate       │ │
│  │  RAG/Vault │  │  Pipeline      │ │
│  │  S.E.A.L.  │  │  CLAEG/NAFE    │ │
│  │  Handoff   │  │  Evidence Eng. │ │
│  └─────┬──────┘  └───────┬────────┘ │
└────────│─────────────────│──────────┘
         │  SQLite          │  Pure Python
         ▼                  ▼
    ~/.omega-brain/    veritas_build_gates.py
    omega_vault.db     (deterministic, stateless)
    omega_ledger.json
    omega_handoff.json
```

### Verdict System

| Verdict | Precedence | Meaning |
|---------|-----------|---------|
| `PASS` | 0 (lowest) | All gates satisfied. Artifact is deployable under declared regime. |
| `MODEL_BOUND` | 1 | Gates pass but resource/coverage/confidence near redline. Deploy with monitoring. |
| `INCONCLUSIVE` | 2 | Insufficient evidence or timeout. Cannot affirm or deny. Block deploy. |
| `VIOLATION` | 3 (highest) | Constraint failure, security vulnerability, or test failure. Block deploy. |

---

## Requirements

| Requirement | Details |
|-------------|---------|
| Python | 3.11 or 3.12 |
| Core dependency | `mcp >= 1.0.0` |
| OS | Linux, macOS, Windows (WSL2 recommended on Windows) |
| Disk | ~5 MB for source + SQLite data dir (default `~/.omega-brain/`) |
| Optional | `fastembed >= 0.2.0` — ONNX embeddings, ~30 MB model cache, no GPU |
| Optional | `sentence-transformers >= 2.0.0` + `numpy` — highest quality embeddings, GPU-capable |

> **Embedding engine auto-selection:** The server probes for `sentence-transformers` first, then `fastembed`, then falls back to built-in TF-IDF n-gram. You always get semantic search — richer models just improve recall quality.

---

## Installation

### From PyPI (when published)

```bash
pip install omega-brain-mcp
```

### From Source

```bash
git clone https://github.com/VrtxOmega/omega-brain-mcp.git
cd omega-brain-mcp
pip install mcp
# Optional: better embeddings
pip install fastembed                       # recommended — fast ONNX, no GPU
pip install sentence-transformers numpy     # best quality, larger download
```

### Docker

```bash
docker build -t omega-brain-mcp .
docker run --rm -i omega-brain-mcp          # stdio mode (MCP standard)
docker run --rm -p 8055:8055 omega-brain-mcp --sse --port 8055   # SSE mode
```

### Run Tests

```bash
pip install pytest pytest-asyncio pytest-cov
PYTHONUTF8=1 OMEGA_BRAIN_DATA_DIR=/tmp/omega-test pytest tests/ -v --tb=short
```

---

## Quickstart

### 1 — Verify the server starts

```bash
python omega_brain_mcp_standalone.py --help
```

### 2 — Run in stdio mode (default)

The server reads JSON-RPC 2.0 messages from stdin and writes responses to stdout. MCP clients manage this process automatically via the config below.

```bash
python omega_brain_mcp_standalone.py
```

### 3 — Run in SSE mode (HTTP streaming)

```bash
python omega_brain_mcp_standalone.py --sse --port 8055
# GET  http://localhost:8055/sse      — event stream
# POST http://localhost:8055/messages — send tool calls
```

### 4 — Configure your client (see [Configuration](#configuration))

### 5 — Test a tool call manually (stdio)

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"omega_brain_status","arguments":{}}}' \
  | python omega_brain_mcp_standalone.py
```

---

## Configuration

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["/absolute/path/to/omega_brain_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### VS Code / GitHub Copilot

Add to `.vscode/mcp.json` in your workspace (or user settings):

```json
{
  "servers": {
    "omega-brain": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/omega_brain_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### Cursor

In **Cursor Settings → MCP → Add Server**:

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["/absolute/path/to/omega_brain_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### Windsurf / Cascade

In `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["/absolute/path/to/omega_brain_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### SSE / HTTP Client

```json
{
  "mcpServers": {
    "omega-brain": {
      "type": "sse",
      "url": "http://localhost:8055/sse"
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONUTF8` | `0` | Set to `1` on Windows to avoid encoding errors |
| `OMEGA_BRAIN_DATA_DIR` | `~/.omega-brain/` | Override data directory for vault, ledger, and handoff files |

---

## Usage Examples

All examples use JSON-RPC 2.0. In practice your MCP client sends these automatically when you invoke a tool. The one-liner shell form is useful for testing.

### Check server health

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"omega_brain_status","arguments":{}}}' \
  | python omega_brain_mcp_standalone.py
```

**Response (abbreviated):**

```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "{\"vault_sessions\": 3, \"vault_entries\": 42, \"rag_fragments\": 18, \"ledger_entries\": 127, \"embedding_engine\": \"fastembed\", \"omega_status\": \"OK\"}"
    }]
  }
}
```

### Ingest a knowledge fragment

```json
{
  "jsonrpc": "2.0", "id": 2,
  "method": "tools/call",
  "params": {
    "name": "omega_ingest",
    "arguments": {
      "text": "The VERITAS pipeline requires all claims to declare their evidence regime before Gate 4.",
      "source": "project-notes",
      "tags": ["veritas", "evidence"]
    }
  }
}
```

### Semantic RAG query

```json
{
  "jsonrpc": "2.0", "id": 3,
  "method": "tools/call",
  "params": {
    "name": "omega_rag_query",
    "arguments": {
      "query": "evidence regime requirements",
      "top_k": 3
    }
  }
}
```

### Cortex approval check

```json
{
  "jsonrpc": "2.0", "id": 4,
  "method": "tools/call",
  "params": {
    "name": "omega_cortex_check",
    "arguments": {
      "tool": "omega_rag_query",
      "args": {"query": "sensitive user data"},
      "baseline_prompt": "You are a data analysis agent. Only access approved datasets."
    }
  }
}
```

**Response:**

```json
{"approved": true, "similarity": 0.71, "verdict": "APPROVED", "node_votes": [1, 1, 1]}
```

### Run the full VERITAS pipeline

```json
{
  "jsonrpc": "2.0", "id": 5,
  "method": "tools/call",
  "params": {
    "name": "veritas_run_pipeline",
    "arguments": {
      "claim": {
        "claim_id": "claim-001",
        "artifact_type": "function",
        "description": "Validates user authentication tokens",
        "primitives": ["jwt", "hmac-sha256"],
        "evidence": [
          {
            "id": "e1", "type": "test_suite",
            "provenance": 0.9, "repeatability": 0.95,
            "freshness": 0.85, "env_match": 1.0
          }
        ],
        "constraints": [{"op": "lte", "left": "latency_ms", "right": 50}],
        "cost": {"cpu_p95": 0.3, "memory_gb_p95": 0.1},
        "security": {"sast_findings": [], "secrets_found": false}
      },
      "regime": "baseline"
    }
  }
}
```

**Response:**

```json
{
  "verdict": "PASS",
  "gates_passed": 10,
  "seal_hash": "a3f9c2...",
  "pipeline_ms": 12,
  "omega_status": "OK"
}
```

### NAFE scan (detect AI narrative failures)

```json
{
  "jsonrpc": "2.0", "id": 6,
  "method": "tools/call",
  "params": {
    "name": "veritas_nafe_scan",
    "arguments": {
      "text": "Although the tests failed, the developer clearly intended the function to work correctly, so we can assume it passes."
    }
  }
}
```

**Response:**

```json
{
  "nafe_detected": true,
  "signatures": ["NARRATIVE_RESCUE", "INTENT_INFERENCE"],
  "seal_hash": "b7d1e4...",
  "omega_status": "NAFE_VIOLATION"
}
```

### Python client (persistent process)

```python
from omega_client import OmegaBrainClient

client = OmegaBrainClient()  # starts server subprocess once

status  = client.call("omega_brain_status", {})
result  = client.call("omega_rag_query", {"query": "VERITAS evidence", "top_k": 5})
verdict = client.call("veritas_run_pipeline", {"claim": {...}, "regime": "baseline"})

client.close()
```

For framework integrations (LangChain, CrewAI, AutoGen, LlamaIndex) see [`INTEGRATIONS.md`](INTEGRATIONS.md) and the [`examples/`](examples/) directory.

---

## Tools Reference (26 Tools)

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
| `veritas_evidence_gate` | Gate 4/10: MIS\_GREEDY, Quality(e), K/A/Q thresholds |
| `veritas_math_gate` | Gate 5/10: Constraint satisfaction via interval arithmetic |
| `veritas_cost_gate` | Gate 6/10: Resource utilization vs redline thresholds |
| `veritas_incentive_gate` | Gate 7/10: Source dominance and vendor concentration |
| `veritas_security_gate` | Gate 8/10: SAST, secrets, injection, auth, crypto |
| `veritas_adversary_gate` | Gate 9/10: Fuzz, mutation, exploit, outage, spike |
| `veritas_run_pipeline` | Full 10-gate pipeline — final verdict + seal hash |
| `veritas_compute_quality` | Compute Quality(e) for single evidence item |
| `veritas_mis_greedy` | Run MIS\_GREEDY algorithm on evidence items |
| `veritas_claeg_resolve` | Map verdict to CLAEG terminal state |
| `veritas_claeg_transition` | Validate state transition (absence = prohibition) |
| `veritas_nafe_scan` | Scan for NAFE failure signatures in AI text |

---

## Resources (9)

| URI | Description |
|-----|-------------|
| `omega://session/preload` | Auto-fetched at startup: RAG + handoff + vault context |
| `omega://session/handoff` | SHA-256 verified cross-session handoff |
| `omega://session/current` | Session ID, call count, data directory |
| `omega://brain/status` | DB stats, embedding engine, ledger count |
| `veritas://spec/v1.0.0` | Full canonical VERITAS Omega Build Spec |
| `veritas://claeg/grammar` | Terminal states, transitions, invariants, prohibitions |
| `veritas://gates/order` | The 10-gate pipeline sequence |
| `veritas://thresholds/baseline` | Dev/baseline regime numeric thresholds |
| `veritas://thresholds/production` | Escalated production regime thresholds |

---

## CLAEG State Machine

```
INIT → { STABLE_CONTINUATION | ISOLATED_CONTAINMENT | TERMINAL_SHUTDOWN }
STABLE_CONTINUATION → { STABLE_CONTINUATION | ISOLATED_CONTAINMENT | TERMINAL_SHUTDOWN }
ISOLATED_CONTAINMENT → { STABLE_CONTINUATION | TERMINAL_SHUTDOWN }
TERMINAL_SHUTDOWN → {} (absorbing)
```

**Invariant:** Absence of an allowed transition is treated as **prohibition**. `TERMINAL_SHUTDOWN` is absorbing — there are no exit transitions.

| State | Meaning |
|-------|---------|
| `STABLE_CONTINUATION` | Normal operation; execution proceeds |
| `ISOLATED_CONTAINMENT` | Anomaly detected; execution continues under isolation |
| `TERMINAL_SHUTDOWN` | Critical failure; execution halted, no recovery |

---

## File Structure

```
omega-brain-mcp/
├── omega_brain_mcp_standalone.py   # MCP server — Brain Core + tool dispatch (~1430 lines)
├── veritas_build_gates.py          # Gate engine — pure deterministic logic (~1430 lines)
├── omega_client.py                 # Python client helper (persistent process)
├── requirements.txt                # mcp>=1.0.0
├── pyproject.toml                  # Package config + optional deps
├── Dockerfile                      # Non-root, unbuffered, stdio + SSE
├── INTEGRATIONS.md                 # LangChain, CrewAI, AutoGen, LlamaIndex guides
├── CHANGELOG.md                    # Release history
├── docs/
│   └── integration.md              # Detailed integration reference
├── examples/
│   ├── langchain_quickstart.py
│   ├── crewai_quickstart.py
│   ├── autogen_quickstart.py
│   └── llamaindex_quickstart.py
└── tests/
    ├── test_build_gates.py         # Gate pipeline tests
    ├── test_veritas.py             # VERITAS scoring tests
    ├── test_seal.py                # SEAL chain integrity tests
    ├── test_handoff.py             # Handoff seal/context tests
    ├── test_cortex.py              # Cortex approval tests
    └── test_vault.py               # Vault persistence tests
```

---

## Troubleshooting

### Server does not start / `ModuleNotFoundError: mcp`

```bash
pip install mcp
```

### `UnicodeDecodeError` on Windows

Set the environment variable before running:

```bash
set PYTHONUTF8=1
python omega_brain_mcp_standalone.py
```

Or add `"env": { "PYTHONUTF8": "1" }` to your MCP client config.

### Client shows "Server disconnected" immediately

1. Confirm the path in your client config is **absolute** (e.g., `C:\Users\you\omega-brain-mcp\omega_brain_mcp_standalone.py`), not relative.
2. Run the server manually in a terminal to see startup errors: `python /path/to/omega_brain_mcp_standalone.py`
3. Check Python version: `python --version` must be 3.11+.

### Embeddings are slow / low quality

Install a better embedding backend:

```bash
pip install fastembed          # fast, no GPU, ~30MB download — recommended
# or
pip install sentence-transformers numpy   # highest quality
```

The server auto-selects the best available engine at startup and logs which tier is active.

### `NAFE_VIOLATION` returned unexpectedly

The NAFE scanner detected a narrative failure pattern (rescue framing, intent inference, moral override, or authority drift) in the text passed to `veritas_nafe_scan`. Review the `signatures` field in the response for the specific pattern detected, then revise the input text to state facts without narrative interpretation.

### Vault / ledger corruption

Delete the data directory and restart to rebuild from scratch (all persisted memory will be lost):

```bash
rm -rf ~/.omega-brain/
python omega_brain_mcp_standalone.py
```

To use a separate data directory per project:

```bash
OMEGA_BRAIN_DATA_DIR=/path/to/project-brain python omega_brain_mcp_standalone.py
```

### SSE mode: `Connection refused` on port 8055

Ensure the server is running with `--sse --port 8055` and that the port is not blocked by a firewall. Check with:

```bash
curl -N http://localhost:8055/sse
```

---

## Security & Privacy

- **All data is local.** The vault, SEAL ledger, RAG store, and handoff file are stored in `~/.omega-brain/` (or `OMEGA_BRAIN_DATA_DIR`). Nothing is sent to any external service.
- **No API keys required.** The server requires only a local Python installation and the `mcp` package.
- **Cryptographic integrity.** The S.E.A.L. ledger uses SHA-3 256 hash chaining; any tampering with a past entry breaks the chain. Handoff files are SHA-256 sealed.
- **Cortex blocks drift.** The Cortex gate hard-blocks tool calls with similarity below `0.45` to the declared baseline prompt, preventing prompt injection from steering the agent off its declared mission.
- **NAFE guardrails.** The NAFE scanner detects and seals AI narrative failures — including attempts to override constraints via ethical framing or authority assertions — before they propagate.
- **Non-root Docker.** The provided `Dockerfile` runs as a non-root `omega` user.
- **VERITAS gates are stateless and deterministic.** `veritas_build_gates.py` has no network calls, no file I/O, and no side effects. All verdicts are reproducible given the same input.
- **Sensitive data handling.** Do not ingest secrets, credentials, or PII into the RAG store or vault. The vault is unencrypted SQLite on disk; protect it with OS-level file permissions.

---

## License

MIT — see [`LICENSE`](LICENSE) for full text.

---

<div align="center">
  <sub>Built by <a href="https://github.com/VrtxOmega">RJ Lopez</a> · <strong>VERITAS Omega Framework</strong></sub><br/>
  <sub>
    <a href="https://github.com/VrtxOmega/omega-brain-mcp/issues">Report Issue</a> ·
    <a href="CHANGELOG.md">Changelog</a> ·
    <a href="INTEGRATIONS.md">Integrations</a> ·
    <a href="https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp">Glama MCP Registry</a>
  </sub>
</div>