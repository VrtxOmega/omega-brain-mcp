<div align="center">
  <img src="https://raw.githubusercontent.com/VrtxOmega/Gravity-Omega/master/omega_icon.png" width="100" alt="VERITAS" />
  <h1>OMEGA BRAIN MCP</h1>
  <p><strong>Standalone Model Context Protocol Server with Built-In Intelligence</strong></p>
  <p><em>One file. One dependency. Full sovereign cognition.</em></p>
</div>

![Status](https://img.shields.io/badge/Status-ACTIVE-success?style=for-the-badge&labelColor=000000&color=d4af37)
![Version](https://img.shields.io/badge/Version-v2.0-blue?style=for-the-badge&labelColor=000000)
![Stack](https://img.shields.io/badge/Stack-Python%20%2B%20MCP-informational?style=for-the-badge&labelColor=000000)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge&labelColor=000000)

---

A fully self-contained MCP server. One Python file, one dependency (`mcp`). No external server required. Ships with provenance RAG, SEAL audit chain, VERITAS scoring, episodic memory, and a tri-node cortex approval gate — all built in.

> **Drop it into any MCP-compatible client and get a full intelligence layer instantly.**

## Built-In Systems

| System | Description |
|--------|-------------|
| **Provenance / RAG** | Fragment ingestion, semantic search, VERITAS scoring (agreement x quality) |
| **SEAL Audit Chain** | Tamper-evident SHA-256 hash chain for every operation |
| **Episodic Memory** | Session logging, cross-session handoff with sealed context |
| **Vault** | Full-text search across local persistent knowledge store |
| **Cortex Gate** | Tri-node approval checking with semantic similarity scoring |
| **Cortex Steer** | Drift correction for arguments that deviate from baseline |
| **Execute** | Cortex-wrapped execution with auto-logging to SEAL chain |

## Available Tools

| Tool | Purpose |
|------|---------|
| `omega_ingest` | Add text fragments to the provenance RAG store |
| `omega_rag_query` | Semantic search with ranked results and VERITAS scores |
| `omega_vault_search` | Full-text keyword search across the local vault |
| `omega_seal_run` | Append tamper-proof entry to the audit ledger |
| `omega_preload_context` | Episodic task briefing with RAG + vault + handoff context |
| `omega_log_session` | Write session record to the local vault |
| `omega_write_handoff` | SHA-256 sealed cross-session handoff |
| `omega_cortex_check` | Tri-node approval gate for high-impact operations |
| `omega_cortex_steer` | Correct drifting arguments back into baseline |
| `omega_execute` | Cortex-wrapped execution with auto-audit |
| `omega_brain_status` | Vault stats, fragment count, ledger entries |
| `omega_brain_report` | Human-readable session audit report |

## Quick Start

### Requirements
- Python 3.10+
- `pip install mcp`

### Install

`ash
pip install mcp
python omega_brain_mcp.py
`

### Configure in Claude Desktop

Add to your `claude_desktop_config.json`:

`json
{
  "mcpServers": {
    "omega-brain": {
      "command": "python",
      "args": ["path/to/omega_brain_mcp.py"]
    }
  }
}
`

### Configure in Gemini CLI

Add to your MCP server configuration and the tools will be available automatically.

## Architecture

`
omega_brain_mcp.py (single file)
|
+-- Provenance Store (in-memory + disk)
|     Fragment ingestion, embedding, search
|
+-- SEAL Ledger (append-only hash chain)
|     SHA-256 linked entries, tamper detection
|
+-- Vault (JSON file store)
|     Sessions, handoffs, knowledge items
|
+-- Cortex (tri-node gate)
      Approval checking, drift steering, similarity
`

All state persists to disk in the `~/.omega-brain/` directory.

## License

MIT

---

<div align="center">
  <sub>Built by <a href="https://github.com/VrtxOmega">RJ Lopez</a> | VERITAS Framework</sub>
</div>