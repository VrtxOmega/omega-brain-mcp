# Omega Brain MCP

Omega Brain provides task-scoped memory retrieval, explicit claim evaluation and local audit records for MCP clients.

The standalone 2.3 release replaces unsafe argument steering and uncalibrated approval scores with advisory alignment. SSWP can enforce Brain's operator-policy receipts at its witness entry point. Retrieval uses indexed lexical candidates with stable features; it does not claim dense semantic recall.

Install with `python -m pip install .`, then run `omega-brain-mcp` or `python omega_brain_mcp_standalone.py`. Add that command to your MCP client's persistent user configuration. Data defaults to `~/.omega-brain`; use absolute paths for a portable desktop setup.

Call `omega_preload_context` with `task` and `task_id`, then use the same ID on `omega_rag_query` and `omega_ingest`. `omega_integrity_status`, `omega_brain_report` and `omega_ecosystem_status` expose current health and historical verification limits. `omega_write_handoff` requires `conversation_id` equal to the task ID.

The supplied Python client performs the MCP initialization handshake, bounds requests, drains diagnostics and raises server errors. `omega_call("omega_rag_query", query="deployment decision", task_id="example-task")` performs a scoped lookup.

The companion [Stenographer](https://github.com/VrtxOmega/omega-stenographer-mcp) preserves conversations; [SSWP](https://github.com/VrtxOmega/sswp-mcp) runs software checks. Their shared state directory and task IDs must agree.

See [current operating contract](docs/CURRENT_STATE.md) for migration, permissions, evidence semantics and recovery. Historical manuals and examples describe older contracts; this document and the current MCP schemas take precedence. Legacy network mode is outside the standalone deployment's tested guarantees.

Run `python -m unittest discover -s tests -p "test_contracts.py"` and `python -m pytest tests/test_build_gates.py`. The integration suite lives in `integration-tests/` and uses `OMEGA_SUITE_ROOT` pointing to sibling `omega-brain`, `omega-stenographer`, `sswp` checkouts and a shared `.venv`.
