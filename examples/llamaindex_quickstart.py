"""
examples/llamaindex_quickstart.py
Run: python llamaindex_quickstart.py
Requires: pip install llama-index-core
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from omega_client import omega_call, omega_call_async


# ── Named tool functions (NOT lambdas — LlamaIndex inspects signatures) ──

def omega_rag_query(query: str, top_k: int = 5) -> dict:
    """Search the Omega Brain provenance store semantically."""
    return omega_call("omega_rag_query", query=query, top_k=top_k)


def omega_execute(tool: str, args: dict, baseline: str) -> dict:
    """Cortex-verified execution: check → steer → run → SEAL.
    Wraps Omega Brain tools only. For external tools, returns steered_args."""
    return omega_call("omega_execute", tool=tool, args=args, baseline=baseline)


def omega_brain_report(lines: int = 10) -> str:
    """Human-readable session audit: SEAL chain, cortex verdicts, VERITAS scores."""
    r = omega_call("omega_brain_report", lines=lines)
    return r.get("text", str(r))


async def omega_rag_query_async(query: str, top_k: int = 5) -> dict:
    """Async version for LlamaIndex async pipelines."""
    return await omega_call_async("omega_rag_query", query=query, top_k=top_k)


# ── LlamaIndex FunctionTool registration ─────────────────────────────────
try:
    from llama_index.core.tools import FunctionTool

    omega_tools = [
        FunctionTool.from_defaults(
            fn=omega_rag_query,
            name="omega_rag",
            description="Semantic search of Omega Brain provenance store",
        ),
        FunctionTool.from_defaults(
            fn=omega_execute,
            name="omega_execute",
            description=(
                "Cortex-verified execution of Omega Brain tools. "
                "Wraps Omega Brain tools only — for external tools, "
                "returns steered_args for you to use."
            ),
        ),
        FunctionTool.from_defaults(
            fn=omega_brain_report,
            name="omega_brain_report",
            description="Session audit: SEAL chain tail, cortex verdicts, VERITAS scores",
        ),
    ]
except ImportError:
    omega_tools = []
    print("llama-index-core not installed — tool registration skipped")


if __name__ == "__main__":
    print("=== Omega Brain + LlamaIndex Demo ===\n")

    # Sync usage
    result = omega_rag_query("session handoff mechanism")
    print(f"RAG fragments: {len(result.get('fragments', []))}")
    print(f"VERITAS score: {result.get('veritas_score')}")

    # Async usage
    async def _demo():
        r = await omega_rag_query_async("cortex blocking threshold")
        print(f"Async RAG fragments: {len(r.get('fragments', []))}")

    asyncio.run(_demo())

    # Audit
    print("\nReport tail:")
    print(omega_brain_report(lines=5))

    print(f"\nRegistered {len(omega_tools)} LlamaIndex tools")
