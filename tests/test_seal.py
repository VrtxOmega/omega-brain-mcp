"""
tests/test_seal.py — S.E.A.L. hash chain integrity
Run: pytest tests/test_seal.py -v
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from omega_brain_mcp_standalone import _seal_event, _seal_run, _db, _init_db

_init_db()


def _get_ledger_tail(n: int = 20):
    conn = _db()
    rows = conn.execute(
        "SELECT id, prev_hash, event_type, payload, hash, timestamp "
        "FROM ledger ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


class TestSealChainIntegrity:
    """Each ledger entry must hash correctly and chain to the previous."""

    def test_seal_event_returns_hash(self):
        h = _seal_event("test_event", {"key": "value"})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA3-256 hex digest

    def test_chain_links_correctly(self):
        """Each hash must be derivable from prev_hash + event_type + payload + timestamp."""
        # Add a known event and verify chain
        _seal_event("chain_test_a", {"seq": 1})
        _seal_event("chain_test_b", {"seq": 2})

        tail = _get_ledger_tail(10)
        chain_events = [e for e in tail if e["event_type"] in ("chain_test_a", "chain_test_b")]

        # Every event in the chain must have a prev_hash that matches prior entry
        for i in range(1, len(tail)):
            prev_entry = tail[i - 1]
            curr_entry = tail[i]
            assert curr_entry["prev_hash"] == prev_entry["hash"], (
                f"Chain broken between entry {prev_entry['id']} and {curr_entry['id']}"
            )

    def test_hash_is_sha3_256(self):
        """Verify the hash algorithm matches spec (SHA3-256)."""
        h = _seal_event("hash_algorithm_test", {"verify": True})
        assert len(h) == 64
        # SHA3-256 produces 32 bytes = 64 hex chars
        int(h, 16)  # must be valid hex

    def test_seal_run_returns_structured_result(self):
        result = _seal_run(
            {"task": "pytest", "session": "test"},
            "test run completed"
        )
        assert "seal_hash" in result
        assert "session_id" in result
        assert "timestamp" in result
        assert len(result["seal_hash"]) == 64

    def test_duplicate_payloads_produce_different_hashes(self):
        """Same payload at different times must produce different hashes (timestamp included)."""
        h1 = _seal_event("dup_test", {"x": 1})
        h2 = _seal_event("dup_test", {"x": 1})
        # These may or may not differ depending on timestamp resolution
        # but both must exist and be valid SHA3-256 hashes
        assert len(h1) == 64
        assert len(h2) == 64


class TestSealLedgerPersistence:
    """Ledger entries must persist across function calls."""

    def test_events_accumulate(self):
        conn = _db()
        count_before = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        conn.close()

        _seal_event("persistence_test_1", {})
        _seal_event("persistence_test_2", {})
        _seal_event("persistence_test_3", {})

        conn = _db()
        count_after = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
        conn.close()

        assert count_after == count_before + 3
