"""
tests/test_handoff.py — Handoff seal verification and preload
Run: pytest tests/test_handoff.py -v
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import omega_brain_mcp_standalone as brain


class TestHandoffSeal:
    """Handoff must be SHA-256 sealed and tamper-evident."""

    def _with_temp_handoff(self, fn):
        """Run fn with a temporary HANDOFF_FILE so tests don't clobber real data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = brain.HANDOFF_FILE
            brain.HANDOFF_FILE = Path(tmpdir) / "handoff.json"
            try:
                return fn()
            finally:
                brain.HANDOFF_FILE = original

    def test_write_handoff_produces_seal(self):
        def run():
            record = brain._write_handoff(
                task="test task",
                summary="test summary",
                decisions=["decision A"],
                files=["file_x.py"],
                next_steps=["next step 1"],
                conversation_id="test-conv-123",
            )
            assert "seal" in record
            assert len(record["seal"]) == 64  # SHA-256 hex
        self._with_temp_handoff(run)

    def test_read_handoff_verifies_seal(self):
        def run():
            brain._write_handoff(
                task="seal verify test",
                summary="verifying seal on read",
                decisions=[], files=[], next_steps=[], conversation_id="",
            )
            loaded = brain._read_handoff()
            assert loaded is not None
            assert loaded.get("seal_verified") is True
            assert loaded["task"] == "seal verify test"
        self._with_temp_handoff(run)

    def test_tampered_handoff_returns_none(self):
        """Modifying any field after sealing must cause read to return None."""
        def run():
            brain._write_handoff(
                task="original task",
                summary="original summary",
                decisions=[], files=[], next_steps=[], conversation_id="",
            )
            # Tamper with the file
            raw = json.loads(brain.HANDOFF_FILE.read_text())
            raw["task"] = "TAMPERED"
            brain.HANDOFF_FILE.write_text(json.dumps(raw))

            loaded = brain._read_handoff()
            assert loaded is None  # tamper detected
        self._with_temp_handoff(run)

    def test_missing_handoff_returns_none(self):
        def run():
            # Ensure file doesn't exist
            if brain.HANDOFF_FILE.exists():
                brain.HANDOFF_FILE.unlink()
            assert brain._read_handoff() is None
        self._with_temp_handoff(run)

    def test_handoff_fields_preserved(self):
        """All fields must survive write → read round-trip."""
        def run():
            brain._write_handoff(
                task="round trip task",
                summary="round trip summary",
                decisions=["d1", "d2"],
                files=["f1.py", "f2.py"],
                next_steps=["ns1"],
                conversation_id="conv-abc",
            )
            loaded = brain._read_handoff()
            assert loaded["task"] == "round trip task"
            assert loaded["summary"] == "round trip summary"
            assert loaded["decisions"] == ["d1", "d2"]
            assert loaded["files_modified"] == ["f1.py", "f2.py"]
            assert loaded["next_steps"] == ["ns1"]
            assert loaded["conversation_id"] == "conv-abc"
        self._with_temp_handoff(run)


class TestContextDetection:
    """Context mode classification must match documented thresholds."""

    def _make_handoff(self, task: str) -> dict:
        return {"task": task, "summary": "", "decisions": [], "files_modified": [], "next_steps": []}

    def test_continuation_high_overlap(self):
        mode, score = brain._detect_context_mode(
            "working on omega brain MCP handoff",
            self._make_handoff("omega brain MCP handoff implementation"),
        )
        assert mode == "CONTINUATION"
        assert score >= brain.CONTINUATION_THRESHOLD

    def test_fresh_start_no_handoff(self):
        mode, score = brain._detect_context_mode("some task", {})
        assert mode == "FRESH_START"
        assert score == 0.0

    def test_context_switch_partial_overlap(self):
        mode, score = brain._detect_context_mode(
            "building something omega related",
            self._make_handoff("completely unrelated astronomy project"),
        )
        # Low or zero overlap → FRESH_START or CONTEXT_SWITCH
        assert mode in ("FRESH_START", "CONTEXT_SWITCH")
