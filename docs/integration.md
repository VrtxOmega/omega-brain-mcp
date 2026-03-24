# Omega Brain MCP — Agent Framework Integration Guide

All tools referenced here (`omega_execute`, `omega_brain_report`, `omega_cortex_check`, `omega_cortex_steer`, `omega_rag_query`) are implemented in the current standalone server. Copy `omega_client.py` from the repo root into your project for the persistent-process client.

> **Note on `omega_execute` scope:** `omega_execute` wraps Omega Brain tools only. For external tools (LangChain tools, shell commands, HTTP calls), use `omega_cortex_steer` to get Cortex-checked/steered args, then call the external tool yourself with the returned `steered_args`. This boundary is intentional — Omega Brain can't inject itself into arbitrary subprocess calls.

---

## Base Helper — Persistent Process (Recommended)

Keep one server process alive across all calls. This avoids the 2–3s cold-start cost of loading the embedding model and SQLite on every invocation.

```python
# Copy omega_client.py from the repo root, then:
from omega_client import omega_call, omega_call_async
```

Or inline:

```python
import asyncio, json, subprocess, sys, threading
from pathlib import Path

_SERVER_PATH = str(Path(__file__).parent / "omega_brain_mcp_standalone.py")

class OmegaBrainClient:
    def __init__(self):
        self._proc = subprocess.Popen(
            [sys.executable, _SERVER_PATH],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, encoding="utf-8"
        )
        self._lock = threading.Lock()
        self._id = 0

    def call(self, tool: str, args: dict) -> dict:
        with self._lock:
            self._id += 1
            payload = json.dumps({
                "jsonrpc": "2.0", "id": self._id,
                "method": "tools/call", "params": {"name": tool, "arguments": args}
            }) + "\n"
            try:
                self._proc.stdin.write(payload)
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
                result = json.loads(line).get("result", {})
                text = result.get("content", [{}])[0].get("text", "{}")
                return json.loads(text)
            except (json.JSONDecodeError, BrokenPipeError, OSError) as e:
                return {"error": str(e), "tool": tool, "omega_status": "CLIENT_ERROR"}

_client = OmegaBrainClient()

def omega_call(tool: str, **kwargs) -> dict:
    """Sync call — thread-safe."""
    return _client.call(tool, kwargs)

async def omega_call_async(tool: str, **kwargs) -> dict:
    """Async call for LlamaIndex, FastAPI, and other async-first frameworks."""
    return await asyncio.to_thread(_client.call, tool, kwargs)
```

---

## One-Off Script Fallback (Subprocess Per Call)

Only use this when making a handful of calls in a script that runs once. Cold-start is 100ms–3s depending on the embedding tier.

```python
def omega_call_oneoff(tool: str, **kwargs) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": kwargs}
    })
    try:
        proc = subprocess.run(
            [sys.executable, "omega_brain_mcp_standalone.py"],
            input=payload, capture_output=True, text=True, timeout=15
        )
        result = json.loads(proc.stdout)
        text = result.get("result", {}).get("content", [{}])[0].get("text", "{}")
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "omega_status": "CLIENT_ERROR"}
```

---

## LangChain

`omega_execute` wraps any Omega Brain tool through Cortex automatically. For external LangChain tools, use `omega_cortex_steer` to get Cortex-verified args first.

```python
from langchain.tools import Tool

BASELINE = "You are a research assistant. Retrieve factual information only."

def cortex_rag(query: str) -> str:
    """RAG with automatic Cortex gate and SEAL trace."""
    result = omega_call(
        "omega_execute", tool="omega_rag_query",
        args={"query": query}, baseline=BASELINE
    )
    if not result.get("executed"):
        return f"BLOCKED: {result.get('reason', 'cortex_block')}"
    frags = result.get("result", {}).get("fragments", [])
    return "\n".join(f["content"] for f in frags[:3]) or "No results."

def guard_external_tool(tool_name: str, args: dict) -> dict:
    """Use omega_cortex_steer for external tools — returns steered_args or blocks."""
    return omega_call(
        "omega_cortex_steer", tool=tool_name,
        args=args, baseline_prompt=BASELINE
    )

tools = [
    Tool(name="omega_rag", func=cortex_rag,
         description="Search Omega Brain provenance store."),
]
```

---

## CrewAI

```python
BASELINE = "Research agent: gather factual public information only."

def cortex_guard(action: str, args: dict) -> tuple[bool, dict]:
    result = omega_call("omega_cortex_steer", tool=action,
                        args=args, baseline_prompt=BASELINE)
    return result.get("approved", False), result.get("steered_args", args)

def guarded_search(query: str) -> str:
    approved, steered = cortex_guard("web_search", {"query": query})
    if not approved:
        return "Action blocked by Cortex"
    return actual_search(steered["query"])
```

---

## AutoGen

```python
def omega_rag(query: str) -> dict:
    return omega_call("omega_rag_query", query=query, top_k=5)

def omega_report(lines: int = 10) -> str:
    r = omega_call("omega_brain_report", lines=lines)
    return r.get("text", str(r))

FUNCTION_MAP = {
    "omega_rag_query": omega_rag,
    "omega_brain_report": omega_report,
}
```

---

## LlamaIndex (Async-First)

LlamaIndex inspects function signatures to auto-generate tool schemas. **Do not use lambdas** — use named `def` functions so parameter names appear in the schema.

```python
from llama_index.core.tools import FunctionTool

# Named defs — signature is inspectable
def omega_rag_query_tool(query: str, top_k: int = 5) -> dict:
    """Search Omega Brain provenance store semantically."""
    return omega_call("omega_rag_query", query=query, top_k=top_k)

async def omega_rag_query_async_tool(query: str, top_k: int = 5) -> dict:
    """Async version for LlamaIndex async pipelines."""
    return await omega_call_async("omega_rag_query", query=query, top_k=top_k)

def omega_execute_tool(tool: str, args: dict, baseline: str) -> dict:
    """Cortex-verified execution of Omega Brain tools.
    For external tools, returns steered_args for you to call yourself."""
    return omega_call("omega_execute", tool=tool, args=args, baseline=baseline)

def omega_report_tool(lines: int = 10) -> str:
    """Session audit: SEAL chain, cortex verdicts, VERITAS scores."""
    r = omega_call("omega_brain_report", lines=lines)
    return r.get("text", str(r))

omega_tools = [
    FunctionTool.from_defaults(fn=omega_rag_query_async_tool, name="omega_rag"),
    FunctionTool.from_defaults(fn=omega_execute_tool, name="omega_execute"),
    FunctionTool.from_defaults(fn=omega_report_tool, name="omega_brain_report"),
]
```

---

## Quick-Reference Pattern Table

| Goal | Tool | Notes |
|---|---|---|
| Pre-action guard (binary) | `omega_cortex_check` | Returns `approved: true/false` |
| Pre-action guard + auto-fix args | `omega_cortex_steer` | Returns steered args in 0.45–0.65 window; hard blocks below 0.45 |
| Cortex-wrapped execution | `omega_execute` | **Omega Brain tools only** — for external tools, use `omega_cortex_steer` + call yourself |
| Memory / context retrieval | `omega_rag_query` / `omega_preload_context` | Use at agent task start |
| Human-readable audit | `omega_brain_report` | SEAL chain tail, blocked/steered counts, VERITAS avg |
| Session persistence | `omega_seal_task` | One tap, zero fields, auto-generated from vault tape |
