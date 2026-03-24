# Contributing to Omega Brain MCP

## How to Add a New Tool

1. **Define the tool** in `list_tools()` inside `omega_brain_mcp_standalone.py`:
   ```python
   Tool(name="omega_my_tool",
        description="What it does.",
        inputSchema={"type": "object", "properties": {
            "param": {"type": "string", "description": "..."}
        }, "required": ["param"]})
   ```

2. **Implement the dispatch** in `call_tool()`:
   ```python
   elif name == "omega_my_tool":
       result = _my_tool_logic(arguments.get("param", ""))
       return [TextContent(type="text", text=json.dumps(result, indent=2))]
   ```

3. **Write the logic** as a module-level function (prefix `_`):
   ```python
   def _my_tool_logic(param: str) -> dict:
       _seal_event("my_tool_called", {"param": param})  # always SEAL it
       return {"result": ..., "param": param}
   ```

4. **Add a test** in `tests/` covering at least:
   - Expected output structure
   - Edge case (empty input, boundary value)
   - SEAL event was written (check ledger count)

5. **Open a PR** — CI runs pytest on 3.11 + 3.12 automatically.

## Invariants That Must Not Break

| Invariant | Test file | What it guards |
|---|---|---|
| `STEER_FLOOR == 0.45` | `test_cortex.py` | NAEF hard block |
| SEAL chain links | `test_seal.py` | Audit integrity |
| Handoff tamper detection | `test_handoff.py` | Cross-session trust |
| VERITAS score ∈ [0,1] | `test_veritas.py` | Score validity |

Do not change these values or the hash algorithm (`sha3_256`) without filing an issue first.

## Dev Setup

```bash
git clone https://github.com/RJLopezAI/omega-brain-mcp
cd omega-brain-mcp
pip install mcp pytest pytest-asyncio
# Optional:
pip install fastembed  # ONNX embeddings
pytest tests/ -v
```
