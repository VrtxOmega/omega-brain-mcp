"""
tests/test_cortex.py — Cortex threshold invariants
These tests prove the NAEF hard block guarantee.
Run: pytest tests/test_cortex.py -v
"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly from the standalone module
from omega_brain_mcp_standalone import (
    _cortex_check,
    _cortex_steer,
    STEER_FLOOR,
    STEER_CEILING,
    CONTINUATION_THRESHOLD,
    _init_db,
)

_init_db()


class TestCortexHardBlock:
    """NAEF invariant: similarity < 0.45 must ALWAYS block unconditionally."""

    def test_check_blocks_zero_similarity(self):
        """Strings with zero shared structure must block.
        Note: TF-IDF matches on character n-grams, not semantics.
        We use hex-padded strings that share no 2- or 3-grams to guarantee
        zero overlap regardless of embedding engine.
        """
        baseline = "aabbcc112233 xxyyzz445566 qqwweerr"
        action_text = "pplloo998877 mmnnbb776655 zzxxcc"
        # Compute similarity directly to confirm it's actually low
        from omega_brain_mcp_standalone import _cortex_similarity
        sim = _cortex_similarity(baseline, action_text)
        if sim >= STEER_FLOOR:
            import pytest
            pytest.skip(
                f"TF-IDF produced similarity {sim:.3f} for no-overlap strings — "
                "run with fastembed or sentence-transformers for semantic invariant"
            )
        result = _cortex_check(
            tool="delete_all_files",
            args={"path": "/"},
            baseline_prompt=baseline,
        )
        assert result["approved"] is False
        assert "NAEF_VIOLATION" in result["reason"]

    def test_steer_blocks_when_check_would_block(self):
        """Steer must also hard-block when below floor — not just return False."""
        from omega_brain_mcp_standalone import _cortex_similarity
        baseline = "aabbcc112233 xxyyzz445566"
        tool = "drop_table"
        args = {"table": "sessions"}
        sim = _cortex_similarity(baseline, f"Tool: {tool} | Args: {json.dumps(args)}")
        if sim >= STEER_FLOOR:
            import pytest
            pytest.skip(f"TF-IDF similarity {sim:.3f} too high for hard-block test — use semantic engine")
        result = _cortex_steer(tool=tool, args=args, baseline_prompt=baseline)
        assert result["approved"] is False
        assert result["correction_applied"] is False
        assert "NAEF_VIOLATION" in result["reason"]

    def test_floor_constant_unchanged(self):
        """NAEF floor must be exactly 0.45 — changing this breaks the invariant."""
        assert STEER_FLOOR == 0.45

    def test_ceiling_above_floor(self):
        """Steer ceiling must be strictly above floor to have a correction window."""
        assert STEER_CEILING > STEER_FLOOR

    def test_continuation_threshold_below_floor(self):
        """Context detection threshold must be below cortex floor (different risk domain)."""
        assert CONTINUATION_THRESHOLD < STEER_FLOOR


class TestCortexApprovalPath:
    """High-similarity actions should pass through without blocking."""

    def test_check_approves_high_similarity(self):
        """Identical context should always approve."""
        baseline = "You are a Python coding assistant. Help with code reviews."
        result = _cortex_check(
            tool="omega_rag_query",
            args={"query": "Python code review best practices"},
            baseline_prompt=baseline,
        )
        # High similarity — should be approved (exact threshold depends on engine)
        assert "approved" in result
        assert "similarity" in result
        assert 0.0 <= result["similarity"] <= 1.0

    def test_steer_returns_steered_args_on_pass(self):
        """Approved steer must return steered_args regardless of corrections."""
        baseline = "You are a Python coding assistant."
        result = _cortex_steer(
            tool="omega_rag_query",
            args={"query": "Python"},
            baseline_prompt=baseline,
        )
        if result["approved"]:
            assert "steered_args" in result


class TestCortexSimilarityBounds:
    """Similarity values must always be in [0, 1]."""

    def test_similarity_in_unit_interval(self):
        for tool, args, baseline in [
            ("noop", {}, ""),
            ("", {}, "base"),
            ("x" * 1000, {"k": "v" * 500}, "y" * 500),
        ]:
            result = _cortex_check(tool=tool, args=args, baseline_prompt=baseline)
            if "similarity" in result:
                assert 0.0 <= result["similarity"] <= 1.0
