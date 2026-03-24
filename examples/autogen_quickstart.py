"""
examples/autogen_quickstart.py
Run: python autogen_quickstart.py
Requires: pip install pyautogen
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from omega_client import omega_call


# ── Omega Brain functions for the tool map ────────────────────────────────

def omega_rag(query: str) -> dict:
    """Semantic search of the Omega Brain provenance store."""
    return omega_call("omega_rag_query", query=query, top_k=5)


def omega_brain_report(lines: int = 10) -> str:
    """Human-readable SEAL chain audit: cortex verdicts, VERITAS scores."""
    r = omega_call("omega_brain_report", lines=lines)
    return r.get("text", str(r))


def omega_cortex_check(tool: str, args: dict, baseline: str) -> dict:
    """Tri-Node Cortex approval gate. Returns approved: true/false + similarity."""
    return omega_call(
        "omega_cortex_check",
        tool=tool, args=args, baseline_prompt=baseline
    )


def omega_ingest(content: str, source: str = "autogen", tier: str = "B") -> dict:
    """Add a knowledge fragment to the Omega Brain provenance store."""
    return omega_call("omega_ingest", content=content, source=source, tier=tier)


if __name__ == "__main__":
    print("=== Omega Brain + AutoGen Demo ===\n")

    # Ingest some knowledge
    result = omega_ingest("AutoGen is a multi-agent conversation framework from Microsoft.")
    print(f"Ingested: {result}")

    # Query it back
    print("\nRAG query: 'multi-agent framework'")
    rag = omega_rag("multi-agent framework")
    for f in rag.get("fragments", [])[:2]:
        print(f"  [{f['score']:.3f}] {f['content'][:80]}")
    print(f"  VERITAS score: {rag.get('veritas_score')}")

    # Cortex check example
    print("\nCortex check:")
    check = omega_cortex_check(
        "write_file",
        {"path": "/etc/passwd", "content": "..."},
        "Research assistant that reads public data only"
    )
    print(f"  Approved: {check.get('approved')} | Similarity: {check.get('similarity')}")

    # Audit report
    print("\nAudit report (tail):")
    print(omega_brain_report(lines=5))

    # In a real AutoGen setup, pass these to function_map:
    FUNCTION_MAP = {
        "omega_rag_query": omega_rag,
        "omega_brain_report": omega_brain_report,
        "omega_cortex_check": omega_cortex_check,
    }
    print("\nfunction_map keys:", list(FUNCTION_MAP.keys()))
