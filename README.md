# Omega Brain MCP — Standalone Edition v2.0

A fully self-contained MCP server. One Python file, one dependency (`mcp`). No external server required.

## What's Built In

| System | Description |
|---|---|
| **Provenance / RAG** | Fragment ingestion, semantic search, VERITAS scoring (agreement × quality × independence) |
| **Vault** | Local SQLite: sessions, entries, FTS full-text search, event tape |
| **Cortex** | Tri-Node approval gate + correction/steer mode (NAEF hard block at similarity < 0.45) |
| **S.E.A.L. Ledger** | Tamper-proof SHA-3 hash chain audit trail |
| **Handoff** | SHA-256 sealed cross-session memory — auto-loaded on next restart |
| **Context Detection** | CONTINUATION / CONTEXT_SWITCH / FRESH_START — automatic on every `omega_task_start` call |

## Install

```bash
pip install mcp

# Optional: better embeddings (recommended)
pip install sentence-transformers numpy
```

## Configure (`mcp_config.json`)

```json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["C:/path/to/omega_brain_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

## Data Location

Default: `~/.omega-brain/` — override with `OMEGA_BRAIN_DATA_DIR` env var.

| File | Contents |
|---|---|
| `omega_brain.db` | SQLite: vault, provenance, S.E.A.L. ledger |
| `handoff.json` | SHA-256 sealed cross-session handoff |

> **Bridging paths**: If you use the Gravity Omega-connected version alongside this standalone, they use separate data directories by default. To share the same handoff file, set `OMEGA_BRAIN_DATA_DIR=~/.gemini/antigravity` (the Gravity Omega path) on the standalone, or use `OMEGA_HANDOFF_PATH` to point both at the same `handoff.json`.

## Tools (10)

| Tool | Purpose |
|---|---|
| `omega_preload_context` | Full task briefing: RAG + vault + handoff + VERITAS score |
| `omega_rag_query` | Semantic search of provenance store |
| `omega_ingest` | Add knowledge fragment to RAG store |
| `omega_vault_search` | FTS keyword search across vault entries |
| `omega_cortex_check` | Tri-Node approval gate (approved / blocked) |
| `omega_cortex_steer` | Cortex correction mode (steers drifting args) |
| `omega_seal_run` | Append S.E.A.L. entry to hash chain ledger |
| `omega_log_session` | Write session to vault (decisions + files) |
| `omega_write_handoff` | Write sealed cross-session handoff (structured) |
| `omega_brain_status` | DB stats, embedding engine, session info |

## Slash Commands (Prompts)

Three prompts — distinct workflows:

| Command | Workflow | Fields |
|---|---|---|
| `omega_task_start` | **Task open** — detects mode, injects context | Optional: `task` |
| `omega_seal_task` | **One-tap session close** — fully automatic, no input needed | Optional: `note` |
| `omega_write_handoff` | **Structured close** — explicit fields for precise records | Optional: `task`, `decisions`, `next_steps`, `files` |

**When to use which:**
- `omega_seal_task` — quick workflow, no thinking required. Reads vault tape, auto-writes everything.
- `omega_write_handoff` — when precision matters (specific decisions, explicit next steps). The AI fills in the fields, not you.

## Session Continuity — How It Actually Works

```
Startup: MCP server starts
  → handoff.json read immediately (seal verified)
  → cached in _STARTUP_PRELOAD
  → exposed as omega://session/preload resource

omega_task_start("working on X") called:
  → keyword overlap computed: task vs handoff.task
  → mode classified:
      ≥ 0.35 overlap → CONTINUATION  (leads with last session details)
       > 0.0 overlap → CONTEXT_SWITCH (last session backgrounded)
         0.0 overlap → FRESH_START   (RAG only, handoff suppressed)
  → briefing injected

Note: the handoff IS read at startup. omega_task_start is when
context-mode detection and targeted briefing fire. If you call
any other tool first, the raw preload is still available via
omega://session/preload — you just won't get the mode-classified briefing.
```

## VERITAS Scoring

`veritas_score = agreement × quality × independence` where:
- `agreement` — score spread across top-k fragments (low spread = high agreement)
- `quality` — evidence tier weighted average (A=1.0, B=0.85, C=0.70, D=0.55)
- `independence` — 1.0 if fragments come from ≥2 sources, 0.7 if single source

## Cortex vs Context Detection Thresholds

| Threshold | Value | Used for |
|---|---|---|
| `STEER_FLOOR` | **0.45** | Cortex — security gate on *actions* (hard block, NAEF invariant) |
| `STEER_CEILING` | **0.65** | Cortex — steer zone (args corrected, not blocked) |
| `CONTINUATION_THRESHOLD` | **0.35** | Context detection — classifies *intent* (more lenient by design) |

**Why lower for context detection?** Cortex guards high-stakes *actions* where false negatives carry security risk. Context detection classifies conversational *intent* — a false negative (missing a CONTINUATION) is low-cost (you get a FRESH_START briefing instead). The 0.10 gap is intentional.

## Embedding Engine

| Available | Engine | Quality |
|---|---|---|
| `sentence-transformers` installed | `all-MiniLM-L6-v2` | High — 384-dim dense vectors |
| Fallback | Character n-gram TF-IDF (128-dim) | Functional — keyword matching |

Check active engine: `omega_brain_status` → `embedding_engine`
