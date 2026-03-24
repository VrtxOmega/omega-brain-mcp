"""
examples/langchain_quickstart.py
Run: python langchain_quickstart.py
Requires: pip install langchain langchain-openai
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from omega_client import omega_call

BASELINE = "You are a research assistant. Retrieve and summarize factual information only."


# ── Tool 1: Cortex-wrapped RAG via omega_execute ──────────────────────────
from langchain.tools import Tool

def cortex_rag(query: str) -> str:
    """Semantic search with automatic Cortex gate and SEAL audit trace."""
    result = omega_call(
        "omega_execute",
        tool="omega_rag_query",
        args={"query": query},
        baseline=BASELINE,
    )
    if not result.get("executed"):
        return f"BLOCKED: {result.get('reason', 'cortex_block')}"
    frags = result.get("result", {}).get("fragments", [])
    return "\n".join(f["content"] for f in frags[:3]) or "No results."


# ── Tool 2: Session audit report ─────────────────────────────────────────
def brain_report(query: str = "") -> str:
    """Return the Omega Brain audit report — SEAL chain, verdicts, VERITAS."""
    r = omega_call("omega_brain_report", lines=10)
    return r.get("text", str(r))


tools = [
    Tool(name="omega_rag", func=cortex_rag,
         description="Search Omega Brain provenance store. Input: search query."),
    Tool(name="omega_report", func=brain_report,
         description="Get the Omega Brain session audit report."),
]

# ── Agent ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Minimal demo without requiring an API key
    print("=== Omega Brain + LangChain Demo ===\n")
    print("Calling omega_rag('MCP session handoff'):")
    print(cortex_rag("MCP session handoff"))
    print("\nCalling brain_report():")
    print(brain_report())
