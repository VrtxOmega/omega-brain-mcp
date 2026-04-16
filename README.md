<div align="center">
  <img src="https://raw.githubusercontent.com/VrtxOmega/Gravity-Omega/master/omega_icon.png" width="100" alt="VERITAS" />
  <h1>OMEGA BRAIN MCP + VERITAS BUILD GATES</h1>
  <p><strong>Standalone Model Context Protocol Server with Built-In Intelligence + Deterministic Build Pipeline</strong></p>
  <p><em>Two files. One dependency. Full sovereign cognition + 10-gate build verification.</em></p>
</div>

![Status](https://img.shields.io/badge/Status-ACTIVE-success?style=for-the-badge&labelColor=000000&color=d4af37)
![Version](https://img.shields.io/badge/Version-v2.1.1-blue?style=for-the-badge&labelColor=000000)
![Python](https://img.shields.io/badge/Python-3.11%2B-yellow?style=for-the-badge&labelColor=000000)
![Stack](https://img.shields.io/badge/Stack-Python%20%2B%20MCP-informational?style=for-the-badge&labelColor=000000)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&labelColor=000000)

[![omega-brain-mcp MCP server](https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp/badges/card.svg)](https://glama.ai/mcp/servers/VrtxOmega/omega-brain-mcp)

---

## Overview

Omega Brain MCP is a **self-contained Model Context Protocol server** that equips AI agents with verifiable provenance, persistent cross-session memory, a cryptographic audit trail, and a **10-gate deterministic build evaluation pipeline**. No external server, database daemon, or cloud dependency required — it runs as a single Python process with one mandatory dependency (`mcp`).

The system is built around two complementary subsystems:

- **Brain Core** — Episodic memory, semantic retrieval (RAG), a Cortex approval gate, SHA-3 tamper-proof audit ledger (SEAL), and cross-session handoff. Gives AI agents a persistent, verifiable cognitive layer.
- **VERITAS Build Gates** — A 10-gate deterministic pipeline (INTAKE → TYPE → DEPENDENCY → EVIDENCE → MATH → COST → INCENTIVE → SECURITY → ADVERSARY → TRACE/SEAL) for evaluating software build artifacts against explicitly declared claims. Gates produce machine-readable verdicts with cryptographic seals.

> **SYSTEM INVARIANT:** VERITAS Build does not determine whether code is 'good.' VERITAS Build determines whether code survives disciplined attempts to break it under explicitly declared primitives, constraints, test regimes, boundaries, cost models, evidence, and policy.

---

## Features

### Brain Core
- **Persistent Cross-Session Memory** — SQLite vault with FTS5 full-text search; survives process restarts
- **Semantic RAG Retrieval** — 3-tier embedding engine (sentence-transformers → fastembed → TF-IDF); always works with zero dependencies, upgrades automatically when optional deps are installed
- **Cortex Approval Gate** — Tri-Node similarity gate: hard-blocks at similarity < 0.45 (NAEF floor), steers in the 0.45–0.65 window, approves above 0.65
- **SHA-3 SEAL Ledger** — Append-only hash chain; every cortex check, ingest, and execution is automatically sealed; tamper-evident by construction
- **Sealed Cross-Session Handoff** — SHA-256 verified memory file auto-loaded on restart; agents pick up exactly where they left off
- **VERITAS Provenance Scoring** — Agreement × Quality × Independence formula applied to every stored fragment

### VERITAS Build Gates
- **10-Gate Pipeline** — Fixed acyclic gate order enforced at runtime; fail-fast on VIOLATION
- **Evidence Engine** — Quality(e) formula, MIS_GREEDY independence algorithm, Agreement computation
- **CLAEG State Machine** — Constraint-locked automaton with 3 terminal states and prohibition-by-absence semantics
- **NAFE Guardrails** — Detects and blocks Narrative Rescue, Moral Override, Authority Drift, and Intent Inference failure signatures in AI-generated text
- **Cryptographic Pipeline Seal** — Every full pipeline run produces a unique seal hash for audit traceability

### Operational
- **Zero Config Start** — Works out of the box; data directory auto-created on first run
- **SSE Transport** — Optional server-sent events mode for web/network clients
- **Thread-Safe Persistent Client** — `omega_client.py` helper for multi-threaded frameworks (LangChain, CrewAI, AutoGen, LlamaIndex)
- **26 MCP Tools + 9 Resources** — Comprehensive tool surface covering all Brain Core and Build Gate operations

---

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

### Agent Flow

```
Agent call
    │
    ▼
omega_execute (Cortex gate)
    ├── similarity < 0.45  → BLOCK  (SEAL logged)
    ├── 0.45 ≤ sim < 0.65 → STEER  (args corrected, SEAL logged)
    └── similarity ≥ 0.65 → EXECUTE → tool result → SEAL logged
                                            │
                                     Vault / RAG / Gates
```

### VERITAS Build Flow

```
veritas_run_pipeline(claim)
    │
    ├── Gate 1: INTAKE   → canonicalize + ClaimID
    ├── Gate 2: TYPE     → primitives, domains, operators
    ├── Gate 3: DEPENDENCY → SBOM, CVE, licenses
    ├── Gate 4: EVIDENCE → MIS_GREEDY, Quality(e), K/A/Q
    ├── Gate 5: MATH     → constraint satisfaction
    ├── Gate 6: COST     → resource utilization vs redline
    ├── Gate 7: INCENTIVE → source dominance, vendor concentration
    ├── Gate 8: SECURITY  → SAST, secrets, injection, auth
    ├── Gate 9: ADVERSARY → fuzz, mutation, exploit, spike
    └── Gate 10: TRACE/SEAL → final verdict + cryptographic seal
```

---

## Verdict System

| Verdict | Precedence | Meaning |
|---------|-----------|---------|
| `PASS` | 0 (lowest) | All gates satisfied. Artifact is deployable under declared regime. |
| `MODEL_BOUND` | 1 | Gates pass but resource/coverage/confidence near redline. Deploy with monitoring. |
| `INCONCLUSIVE` | 2 | Insufficient evidence or timeout. Cannot affirm or deny. Block deploy. |
| `VIOLATION` | 3 (highest) | Constraint failure, security vulnerability, or test failure. Block deploy. |

Final pipeline verdict = worst verdict across all gates.

---

## Requirements

- **Python 3.11+**
- **`mcp>=1.0.0`** — the only required dependency

### Optional (better embeddings)

| Package | Embedding Tier | Notes |
|---------|---------------|-------|
| *(none)* | TF-IDF n-gram 128-dim | Always works, no deps |
| `fastembed>=0.2.0` | ONNX BAAI/bge-small-en-v1.5 | ~30 MB model cache, zero GPU |
| `sentence-transformers` + `numpy` | all-MiniLM-L6-v2 | Best quality, GPU optional |

The embedding tier is detected automatically at startup and reported in `omega_brain_status`.

---

## Installation

### Option 1: Clone the repository

```bash
git clone https://github.com/VrtxOmega/omega-brain-mcp.git
cd omega-brain-mcp
pip install -r requirements.txt
```

### Option 2: Install via pip

```bash
pip install git+https://github.com/VrtxOmega/omega-brain-mcp.git
```

With optional embedding dependencies:

```bash
# ONNX embeddings (recommended, fast, zero GPU)
pip install "git+https://github.com/VrtxOmega/omega-brain-mcp.git#egg=omega-brain-mcp[onnx]"

# Full GPU-capable embeddings
pip install "git+https://github.com/VrtxOmega/omega-brain-mcp.git#egg=omega-brain-mcp[full]"
```

---

## Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["/absolute/path/to/omega_brain_mcp_standalone.py"],
      "env": {
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

### Antigravity / Other MCP Clients

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["/absolute/path/to/omega_brain_mcp_standalone.py"],
      "env": {
        "PYTHONUTF8": "1",
        "OMEGA_DATA_DIR": "/path/to/your/data/directory"
      }
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OMEGA_DATA_DIR` | `~/.omega_brain/` | Directory for SQLite vault and SEAL ledger |
| `PYTHONUTF8` | *(unset)* | Set to `1` on Windows to avoid encoding issues |

### SSE Mode (Web / Network Clients)

Run the server in server-sent events mode for HTTP-based MCP clients:

```bash
python omega_brain_mcp_standalone.py --sse --port 8055
```

Endpoints:
- `GET  /sse`      — SSE event stream (MCP client connects here)
- `POST /messages` — MCP message endpoint

---

## Usage

### Quickstart — Preload Context at Task Start

The recommended entry point for any agent session. Loads RAG context, vault history, and sealed handoff in one call.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "omega_preload_context",
    "arguments": {
      "task": "Analyze the authentication module for security vulnerabilities",
      "top_k": 5
    }
  }
}
```

### RAG Query

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "omega_rag_query",
    "arguments": {
      "query": "authentication token validation logic",
      "top_k": 3
    }
  }
}
```

### Cortex Gate Check (Pre-Action Guard)

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "omega_cortex_check",
    "arguments": {
      "tool": "file_write",
      "args": { "path": "/etc/passwd", "content": "..." },
      "baseline_prompt": "You are a code analysis agent. Read source files only."
    }
  }
}
```

Response:
```json
{
  "approved": false,
  "similarity": 0.12,
  "reason": "naef_block",
  "verdict": "BLOCK"
}
```

### Cortex-Wrapped Execution

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "omega_execute",
    "arguments": {
      "tool": "omega_rag_query",
      "args": { "query": "security audit findings", "top_k": 5 },
      "baseline": "You are a security audit agent."
    }
  }
}
```

### VERITAS Build Pipeline (Full 10-Gate Run)

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "veritas_run_pipeline",
    "arguments": {
      "claim": {
        "project": "omega-brain-mcp",
        "version": "2.1.1",
        "commit": "abc1234",
        "primitives": [
          { "name": "latency_ms", "domain": { "type": "Interval", "low": 0, "high": 500 }, "units": "ms" }
        ],
        "constraints": [
          { "op": "leq", "left": "latency_ms", "right": 200 }
        ],
        "test_results": [
          { "suite": "unit", "passed": 47, "failed": 0, "coverage": 0.91 }
        ],
        "dependencies": [
          { "name": "mcp", "version": "1.0.0", "license": "MIT", "integrity": "sha256-..." }
        ]
      },
      "regime": "production",
      "fail_fast": true
    }
  }
}
```

Response:
```json
{
  "final_verdict": "PASS",
  "seal_hash": "sha3_256:4a7f...",
  "gates": {
    "intake": "PASS",
    "type": "PASS",
    "dependency": "PASS",
    "evidence": "INCONCLUSIVE",
    "math": "PASS",
    "cost": "PASS",
    "incentive": "PASS",
    "security": "PASS",
    "adversary": "PASS",
    "trace": "PASS"
  }
}
```

### Individual Gate — Evidence

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "veritas_evidence_gate",
    "arguments": {
      "claim": {
        "evidence": [
          {
            "id": "e1",
            "variable": "latency_ms",
            "value": 145,
            "timestamp": "2026-04-16T00:00:00Z",
            "method": { "protocol": "benchmark", "repeatable": true },
            "provenance": { "tier": 1, "source_id": "ci-runner-01" }
          }
        ]
      },
      "regime": "dev"
    }
  }
}
```

### Audit Report

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/call",
  "params": {
    "name": "omega_brain_report",
    "arguments": { "lines": 20 }
  }
}
```

### Python Client (Recommended for Frameworks)

```python
from omega_client import omega_call

# Preload at task start
context = omega_call("omega_preload_context", task="My task description", top_k=5)

# RAG retrieval
results = omega_call("omega_rag_query", query="authentication security", top_k=3)

# Cortex-wrapped execution
result = omega_call(
    "omega_execute",
    tool="omega_rag_query",
    args={"query": "security findings", "top_k": 5},
    baseline="You are a security audit agent."
)

# Full build pipeline
verdict = omega_call(
    "veritas_run_pipeline",
    claim={"project": "my-app", "version": "1.0.0", ...},
    regime="production"
)
```

See [`INTEGRATIONS.md`](INTEGRATIONS.md) for LangChain, CrewAI, AutoGen, and LlamaIndex examples.

---

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

### Build Gates (14)

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

---

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

---

## File Structure

```
omega-brain-mcp/
  omega_brain_mcp_standalone.py   # MCP server (~1430 lines) — Brain Core + tool dispatch
  veritas_build_gates.py          # Gate engine (~1430 lines) — pure deterministic logic
  omega_client.py                 # Python client helper (thread-safe, async-capable)
  requirements.txt                # mcp>=1.0.0
  pyproject.toml                  # Package config with optional deps
  INTEGRATIONS.md                 # LangChain, CrewAI, AutoGen, LlamaIndex examples
  CHANGELOG.md                    # Version history
  docs/
    integration.md                # Extended integration reference
  examples/                       # Runnable quickstart scripts
  tests/
    test_build_gates.py           # Gate pipeline tests
    test_veritas.py               # VERITAS scoring tests
    test_seal.py                  # SEAL chain integrity tests
    test_handoff.py               # Handoff seal/context tests
    test_cortex.py                # Cortex approval tests
    test_vault.py                 # Vault persistence tests
```

---

## CLAEG State Machine

```
INIT → { STABLE_CONTINUATION | ISOLATED_CONTAINMENT | TERMINAL_SHUTDOWN }
STABLE_CONTINUATION → { STABLE_CONTINUATION | ISOLATED_CONTAINMENT | TERMINAL_SHUTDOWN }
ISOLATED_CONTAINMENT → { STABLE_CONTINUATION | TERMINAL_SHUTDOWN }
TERMINAL_SHUTDOWN → {} (absorbing)
```

**Invariant:** Absence of an allowed transition is treated as prohibition.

**Prohibited inferences:** CLAEG never infers intent, motive, or preference — only structural state from verdict evidence.

---

## Troubleshooting

### Server doesn't start / MCP client can't connect

- Verify Python 3.11+ is installed: `python --version`
- Verify `mcp` is installed: `pip show mcp`
- Use an **absolute path** to `omega_brain_mcp_standalone.py` in the MCP config — relative paths fail in most MCP clients
- On Windows, set `"PYTHONUTF8": "1"` in the `env` block to prevent encoding errors

### `omega_brain_status` shows TF-IDF instead of better embeddings

- Install optional deps: `pip install fastembed` or `pip install sentence-transformers numpy`
- Restart the MCP server process after installing (embedding tier is detected at startup)

### Gates return INCONCLUSIVE instead of PASS

- `INCONCLUSIVE` means the evidence was insufficient to affirm or deny — not a failure
- Add more evidence items to the claim (minimum K_min=2 independent sources for dev, K_min=3 for production)
- Check individual gate verdicts using `veritas_evidence_gate` before running the full pipeline

### Cortex blocks legitimate actions

- If Cortex is blocking valid operations, review the `baseline_prompt` — it must accurately describe the agent's intended role and scope
- The steer window (0.45–0.65) is intentional; adjust your `baseline_prompt` to be more specific about what actions are expected

### Handoff data missing on restart

- The handoff file is stored in `OMEGA_DATA_DIR` (default: `~/.omega_brain/`)
- Verify the same `OMEGA_DATA_DIR` is configured across sessions
- Use `omega_brain_status` to confirm the data directory path

### SEAL chain tamper detection

- If you see SEAL integrity errors, the ledger file may have been modified outside the server
- The SEAL ledger is append-only; any external modification breaks the hash chain by design
- Do not edit `omega_seal_ledger.jsonl` manually

---

## Security & Privacy

- **No network calls** — Brain Core makes zero outbound network requests. All data stays local.
- **No telemetry** — No usage data, crash reports, or analytics are sent anywhere.
- **Local-only storage** — The SQLite vault and SEAL ledger are stored entirely in `OMEGA_DATA_DIR` on your machine.
- **Cryptographic audit trail** — Every operation is SHA-3 sealed in the SEAL ledger. Tampering breaks the hash chain and is immediately detectable.
- **Cortex hard block** — The NAEF floor (similarity < 0.45) provides a structural barrier against prompt injection and scope creep — agents cannot be steered outside their declared baseline without triggering a block.
- **NAFE guardrails** — Detects and seals narrative manipulation patterns (Narrative Rescue, Moral Override, Authority Drift, Intent Inference) before they influence agent behavior.
- **Evidence independence** — MIS_GREEDY enforces that build evidence comes from independent sources; vendor-dominated or single-source evidence cannot achieve PASS.
- **Open source** — Full source code is auditable. No compiled binaries, no obfuscated logic.

---

## License

MIT

---

<div align="center">
  <sub>Built by <a href="https://github.com/VrtxOmega">RJ Lopez</a> | VERITAS Omega Framework</sub>
</div>