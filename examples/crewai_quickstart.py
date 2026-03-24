"""
examples/crewai_quickstart.py
Run: python crewai_quickstart.py
Requires: pip install crewai
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from omega_client import omega_call

BASELINE = "Research agent: gather factual public information. No private or internal data."


def cortex_guard(action: str, args: dict) -> tuple[bool, dict]:
    """Returns (approved, steered_args). Use before any external tool call."""
    result = omega_call(
        "omega_cortex_steer",
        tool=action,
        args=args,
        baseline_prompt=BASELINE,
    )
    return result.get("approved", False), result.get("steered_args", args)


def guarded_search(query: str) -> str:
    """Web search with Cortex pre-check."""
    approved, steered_args = cortex_guard("web_search", {"query": query})
    if not approved:
        return f"BLOCKED by Cortex (similarity too low for baseline)"
    # Replace with your actual search tool
    return f"[Simulated search result for: {steered_args['query']}]"


def ingest_to_brain(content: str, source: str = "crew") -> str:
    """Add research findings back to Omega Brain provenance store."""
    result = omega_call("omega_ingest", content=content, source=source, tier="B")
    return f"Ingested fragment {result.get('fragment_id', '?')}"


if __name__ == "__main__":
    print("=== Omega Brain + CrewAI Demo ===\n")

    # Show cortex guard in action
    approved, steered = cortex_guard("web_search", {"query": "latest AI papers"})
    print(f"Cortex approved: {approved}")
    print(f"Steered args: {steered}")

    # Ingest result to brain
    print("\nIngesting to provenance store...")
    print(ingest_to_brain("AI agent frameworks comparison 2026", source="crew_research"))

    # Show audit
    report = omega_call("omega_brain_report", lines=5)
    print(f"\nAudit report:\n{report.get('text', report)}")
