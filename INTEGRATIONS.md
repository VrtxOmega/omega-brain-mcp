# Omega Brain MCP — Agent Framework Integration Guide

`omega_execute`, `omega_brain_report`, `omega_cortex_check`, `omega_cortex_steer`, and `omega_rag_query` are all available in the standalone server out of the box.

---

## Base Helper — Persistent Process (Recommended)

Keep one server process alive across calls. This avoids the 2–3s cold-start cost of loading the embedding model and SQLite on every call.

```python
import subprocess, json, threading, queue, sys
from pathlib import Path

_OMEGA_PATH = str(Path(__file__).parent / "omega_brain_mcp_standalone.py")

class OmegaBrainClient:
    """Persistent-process MCP client for Omega Brain."""
    def __init__(self):
        self._proc = subprocess.Popen(
            [sys.executable, _OMEGA_PATH],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1
        )
        self._lock = threading.Lock()

    def call(self, tool: str, args: dict) -> dict:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool, "arguments": args}
        }) + "\n"
        try:
            with self._lock:
                self._proc.stdin.write(payload)
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
            response = json.loads(line)
            content = response.get("result", {}).get("content", [{}])
            text = content[0].get("text", "{}") if content else "{}"
            return json.loads(text)
        except (json.JSONDecodeError, BrokenPipeError, OSError) as e:
            return {"error": str(e), "tool": tool, "omega_status": "CLIENT_ERROR"}

    def close(self):
        self._proc.stdin.close()
        self._proc.wait(timeout=5)

# Module-level singleton
_omega = OmegaBrainClient()

def omega_call(tool: str, **kwargs) -> dict:
    """Call Omega Brain. Returns dict with 'error' key on failure — never raises."""
    return _omega.call(tool, kwargs)
```

> **Note:** The `_lock` makes this safe for multi-threaded frameworks (LangChain, CrewAI). For async frameworks, wrap in `asyncio.to_thread`.

---

## One-Off Script Fallback (Subprocess Per Call)

Use this only for scripts that make a handful of calls total. Cold-start is 100ms–3s depending on which embedding tier loads.

```python
import subprocess, json, sys

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

`omega_execute` wraps any Omega Brain tool through Cortex automatically — Cortex check, steer if needed, execute, SEAL trace.

```python
from langchain.tools import tool

BASELINE = "You are a data analysis agent. Only access approved datasets."

@tool
def guarded_rag(query: str) -> str:
    """RAG query with automatic Cortex gate and SEAL audit trace."""
    result = omega_call(
        "omega_execute",
        tool="omega_rag_query",
        args={"query": query},
        baseline=BASELINE
    )
    if not result.get("executed"):
        return f"BLOCKED: {result.get('reason', 'cortex_block')}"
    return json.dumps(result.get("result", {}))

@tool
def cortex_guard_external(action: str, args: dict) -> dict:
    """Use this before calling any external tool — returns approved args or blocks."""
    return omega_call(
        "omega_cortex_steer",
        tool=action, args=args, baseline_prompt=BASELINE
    )
```

---

## CrewAI

Wire `omega_cortex_steer` as a pre-task guard:

```python
from crewai import Agent, task
import json

BASELINE = "Research agent: gather factual public information only."

def guarded_call(action: str, args: dict) -> tuple[bool, dict]:
    """Returns (approved, steered_args)."""
    result = omega_call("omega_cortex_steer",
                        tool=action, args=args, baseline_prompt=BASELINE)
    return result.get("approved", False), result.get("steered_args", args)

def cortex_wrapped_search(query: str) -> str:
    approved, steered_args = guarded_call("web_search", {"query": query})
    if not approved:
        return "Action blocked by Cortex"
    return actual_search(steered_args["query"])
```

---

## AutoGen

Register Omega Brain tools in a `ConversableAgent` function map:

```python
import autogen

def omega_report(lines: int = 10) -> str:
    r = omega_call("omega_brain_report", lines=lines)
    return r.get("text", str(r))

def omega_rag(query: str) -> dict:
    return omega_call("omega_rag_query", query=query, top_k=5)

assistant = autogen.AssistantAgent(
    name="omega_agent",
    system_message="Agent with Omega Brain memory and Cortex verification.",
)
user_proxy = autogen.UserProxyAgent(
    name="user", human_input_mode="NEVER",
    function_map={
        "omega_rag_query": omega_rag,
        "omega_brain_report": omega_report,
    }
)
```

---

## LlamaIndex

```python
from llama_index.core.tools import FunctionTool

omega_tools = [
    FunctionTool.from_defaults(
        fn=lambda query: omega_call("omega_rag_query", query=query, top_k=5),
        name="omega_rag",
        description="Semantic search of the Omega Brain provenance store"
    ),
    FunctionTool.from_defaults(
        fn=lambda tool, args, baseline: omega_call(
            "omega_execute", tool=tool, args=args, baseline=baseline),
        name="omega_execute",
        description="Cortex-verified execution: check → steer → run → SEAL"
    ),
    FunctionTool.from_defaults(
        fn=lambda lines=10: omega_call("omega_brain_report", lines=lines),
        name="omega_brain_report",
        description="Human-readable session audit: SEAL chain, cortex verdicts, VERITAS scores"
    ),
]

from llama_index.core.agent import FunctionCallingAgent
agent = FunctionCallingAgent.from_tools(omega_tools)
```

---

## Quick-Reference Pattern Table

| Goal | Tool | Notes |
|---|---|---|
| Pre-action guard (binary) | `omega_cortex_check` | Returns `approved: true/false` |
| Pre-action guard + auto-fix | `omega_cortex_steer` | Returns steered args if in 0.45–0.65 window |
| Full Cortex-wrapped execution | `omega_execute` | Omega Brain tools only; returns steered_args for external tools |
| Memory / context retrieval | `omega_rag_query` / `omega_preload_context` | Use at agent task start |
| Human-readable audit | `omega_brain_report` | SEAL chain tail, blocked count, VERITAS avg |
| Session persistence | `omega_seal_task` | One tap, no fields required |
