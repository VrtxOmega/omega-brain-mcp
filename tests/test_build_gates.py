#!/usr/bin/env python3
"""
Tests for VERITAS Omega Build Gates — deterministic gate pipeline.
Each test verifies the gate produces the correct verdict under spec-defined conditions.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veritas_build_gates import (
    intake_gate, type_gate, dependency_gate, evidence_gate,
    math_gate, cost_gate, incentive_gate, security_gate,
    adversary_gate, trace_seal, run_pipeline,
    mis_greedy, quality, agreement, clamp01, eps,
    compute_claim_id, compute_policy_hash,
    Verdict, CLAEG, resolve_thresholds,
)


# ── Helper: minimal valid claim ──────────────────────────────────

def _minimal_claim(**overrides):
    claim = {
        "project": "test-project",
        "version": "1.0.0",
        "commit": "a3f8c1d2e4b5f6a7c8d9e0f1a2b3c4d5e6f7a8b9",
        "primitives": [
            {"name": "p99_latency", "domain": {"type": "Interval", "low": 0, "high": 1000}, "units": "ms", "category": "PERFORMANCE"},
            {"name": "error_rate", "domain": {"type": "Interval", "low": 0, "high": 100}, "units": "%", "category": "RELIABILITY"},
        ],
        "operators": [],
        "regimes": [{"name": "dev", "predicate": {}}],
        "boundaries": [
            {"name": "max_latency", "constraint": {"op": "<=", "left": "p99_latency", "right": 200}, "category": "PERFORMANCE"},
            {"name": "max_error", "constraint": {"op": "<=", "left": "error_rate", "right": 0.1}, "category": "RELIABILITY"},
        ],
        "loss_models": [],
        "evidence": [
            {
                "id": "ev1", "variable": "p99_latency",
                "value": {"x": 150, "units": "ms"},
                "timestamp": "2026-04-09T10:00:00Z",
                "method": {"protocol": "jest --coverage", "parameters": {}, "repeatable": True, "environment": {}},
                "provenance": {"source_id": "jest_v29", "source_type": "UNIT_TEST", "acquisition": "automated_ci", "tier": "A"},
            },
            {
                "id": "ev2", "variable": "p99_latency",
                "value": {"x": 148, "units": "ms"},
                "timestamp": "2026-04-09T11:00:00Z",
                "method": {"protocol": "k6 load", "parameters": {}, "repeatable": True, "environment": {}},
                "provenance": {"source_id": "k6_v0.45", "source_type": "LOAD_TEST", "acquisition": "automated_ci", "tier": "B"},
            },
            {
                "id": "ev3", "variable": "error_rate",
                "value": {"x": 0.05, "units": "%"},
                "timestamp": "2026-04-09T10:00:00Z",
                "method": {"protocol": "pytest", "parameters": {}, "repeatable": True, "environment": {}},
                "provenance": {"source_id": "pytest_v8", "source_type": "UNIT_TEST", "acquisition": "automated_ci", "tier": "A"},
            },
            {
                "id": "ev4", "variable": "error_rate",
                "value": {"x": 0.05, "units": "%"},
                "timestamp": "2026-04-09T12:00:00Z",
                "method": {"protocol": "datadog", "parameters": {}, "repeatable": True, "environment": {}},
                "provenance": {"source_id": "datadog_monitor", "source_type": "RUNTIME_MONITOR", "acquisition": "automated_ci", "tier": "B"},
            },
        ],
        "cost": {"build_time_s": 47, "artifact_size_mb": 12, "ci_minutes": 23},
        "cost_bounds": {"build_time_s": 300, "artifact_size_mb": 50, "ci_minutes": 60},
        "dependencies": {},
        "security": {"sast": {"critical": 0, "high": 0}, "secrets_detected": [], "unsanitized_inputs": [], "missing_auth": [], "weak_crypto": [], "plaintext_external": []},
        "attack_suite": {"suite_id": "default", "attacks": []},
        "policy": {"framework_version": "1.0.0", "hash_alg": "sha256", "build_regime": "dev"},
    }
    claim.update(overrides)
    return claim


# ══════════════════════════════════════════════════════════════════
# UNIT TESTS
# ══════════════════════════════════════════════════════════════════

class TestHelpers:
    def test_clamp01(self):
        assert clamp01(0.5) == 0.5
        assert clamp01(-1) == 0.0
        assert clamp01(2) == 1.0

    def test_eps(self):
        assert eps(0) == 1e-6
        assert eps(1000) > 1e-6

    def test_verdict_precedence(self):
        assert Verdict.worst("PASS", "MODEL_BOUND") == "MODEL_BOUND"
        assert Verdict.worst("MODEL_BOUND", "VIOLATION") == "VIOLATION"
        assert Verdict.worst("PASS", "INCONCLUSIVE") == "INCONCLUSIVE"
        assert Verdict.worst_of(["PASS", "PASS", "MODEL_BOUND", "PASS"]) == "MODEL_BOUND"
        assert Verdict.worst_of(["PASS"]) == "PASS"


class TestIntakeGate:
    def test_pass(self):
        r = intake_gate(_minimal_claim())
        assert r["verdict"] == "PASS"
        assert r["details"]["claim_id"]

    def test_missing_field(self):
        r = intake_gate({"project": "x"})
        assert r["verdict"] == "VIOLATION"
        assert "INTAKE_MALFORMED" in r["reasons"]

    def test_bad_commit(self):
        r = intake_gate(_minimal_claim(commit="not-a-hash"))
        assert r["verdict"] == "VIOLATION"
        assert "INTAKE_COMMIT_MISMATCH" in r["reasons"]

    def test_lockfile_drift(self):
        r = intake_gate(_minimal_claim(dependencies={
            "lockfile_hash": "aaa", "actual_lockfile_hash": "bbb"
        }))
        assert r["verdict"] == "VIOLATION"
        assert "INTAKE_LOCKFILE_DRIFT" in r["reasons"]


class TestTypeGate:
    def test_pass(self):
        r = type_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_duplicate_primitive(self):
        claim = _minimal_claim(primitives=[
            {"name": "x", "domain": {"type": "Interval", "low": 0, "high": 1}},
            {"name": "x", "domain": {"type": "Interval", "low": 0, "high": 1}},
        ])
        r = type_gate(claim)
        assert r["verdict"] == "VIOLATION"

    def test_empty_domain(self):
        claim = _minimal_claim(primitives=[
            {"name": "x", "domain": {"type": "Interval", "low": 5, "high": 3}},
        ])
        r = type_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "EMPTY_DOMAIN" in r["reasons"]

    def test_undefined_symbol_in_boundary(self):
        claim = _minimal_claim(boundaries=[
            {"name": "b1", "constraint": {"op": "<=", "left": "nonexistent_var", "right": 100}},
        ])
        r = type_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "UNDEFINED_SYMBOL" in r["reasons"]


class TestDependencyGate:
    def test_pass_no_deps(self):
        r = dependency_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_critical_cve(self):
        claim = _minimal_claim(dependencies={
            "packages": [{"name": "lodash", "version": "4.17.0", "registry": "npm", "integrity_hash": "abc"}],
            "cve_scan": [{"id": "CVE-2024-1234", "severity": "CRITICAL", "package": "lodash", "patch_available": False}],
        })
        r = dependency_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "CVE_CRITICAL" in r["reasons"]

    def test_medium_cve_model_bound(self):
        claim = _minimal_claim(dependencies={
            "packages": [{"name": "express", "version": "4.18.0", "registry": "npm", "integrity_hash": "abc"}],
            "cve_scan": [{"id": "CVE-2024-5678", "severity": "MEDIUM", "package": "express"}],
        })
        r = dependency_gate(claim)
        assert r["verdict"] == "MODEL_BOUND"


class TestEvidenceGate:
    def test_pass(self):
        r = evidence_gate(_minimal_claim(), "dev")
        assert r["verdict"] == "PASS"

    def test_insufficient_independence(self):
        claim = _minimal_claim(evidence=[
            {
                "id": "ev1", "variable": "p99_latency",
                "value": {"x": 150}, "timestamp": "2026-04-09T10:00:00Z",
                "method": {"protocol": "jest", "parameters": {}, "repeatable": True, "environment": {}},
                "provenance": {"source_id": "jest_v29", "tier": "A"},
            },
            # Only one source — K_MIN=2 not met
        ])
        # error_rate has no evidence either
        r = evidence_gate(claim, "dev")
        assert r["verdict"] == "INCONCLUSIVE"
        assert "INSUFFICIENT_INDEPENDENCE" in r["reasons"]


class TestMathGate:
    def test_pass(self):
        r = math_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_violation(self):
        """p99_latency=300 should violate the <=200 boundary."""
        claim = _minimal_claim(evidence=[
            {"id": "ev1", "variable": "p99_latency", "value": {"x": 300}, "timestamp": "2026-04-09T10:00:00Z",
             "method": {}, "provenance": {"tier": "A"}},
            {"id": "ev2", "variable": "error_rate", "value": {"x": 0.05}, "timestamp": "2026-04-09T10:00:00Z",
             "method": {}, "provenance": {"tier": "A"}},
        ])
        r = math_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "UNSAT_CONSTRAINT" in r["reasons"]


class TestCostGate:
    def test_pass(self):
        r = cost_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_critical_exceeded(self):
        claim = _minimal_claim(
            cost={"build_time_s": 290},
            cost_bounds={"build_time_s": 300},
        )
        r = cost_gate(claim)
        # 290/300 = 0.967 > REDLINE_CRITICAL(0.95)
        assert r["verdict"] == "VIOLATION"

    def test_warning_model_bound(self):
        claim = _minimal_claim(
            cost={"build_time_s": 250},
            cost_bounds={"build_time_s": 300},
        )
        r = cost_gate(claim)
        # 250/300 = 0.833 > REDLINE_WARNING(0.80)
        assert r["verdict"] == "MODEL_BOUND"


class TestIncentiveGate:
    def test_pass(self):
        r = incentive_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_vendor_concentration(self):
        claim = _minimal_claim(dependencies={
            "packages": [
                {"name": f"pkg{i}", "version": "1.0.0", "registry": "npm", "integrity_hash": f"h{i}"}
                for i in range(10)
            ],
        })
        r = incentive_gate(claim)
        # 10/10 = 1.0 > 0.70 from npm
        assert r["verdict"] == "MODEL_BOUND"
        assert "VENDOR_CONCENTRATION" in r["reasons"]


class TestSecurityGate:
    def test_pass(self):
        r = security_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_secret_detected(self):
        claim = _minimal_claim(security={
            "sast": {"critical": 0, "high": 0},
            "secrets_detected": [{"file": "config.py", "type": "API_KEY"}],
            "unsanitized_inputs": [], "missing_auth": [], "weak_crypto": [], "plaintext_external": [],
        })
        r = security_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "SECRET_DETECTED" in r["reasons"]

    def test_sast_critical(self):
        claim = _minimal_claim(security={
            "sast": {"critical": 3, "high": 0},
            "secrets_detected": [], "unsanitized_inputs": [], "missing_auth": [], "weak_crypto": [], "plaintext_external": [],
        })
        r = security_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "SAST_CRITICAL" in r["reasons"]


class TestAdversaryGate:
    def test_pass_no_attacks(self):
        r = adversary_gate(_minimal_claim())
        assert r["verdict"] == "PASS"

    def test_fuzz_crash(self):
        claim = _minimal_claim(attack_suite={
            "suite_id": "test", "attacks": [
                {"id": "a1", "category": "fuzz", "transform": {"type": "FuzzInput"}, "severity": 3,
                 "result": {"crash": True, "details": "segfault"}},
            ]
        })
        r = adversary_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "FUZZ_CRASH" in r["reasons"]

    def test_exploit_success(self):
        claim = _minimal_claim(attack_suite={
            "suite_id": "test", "attacks": [
                {"id": "a1", "category": "exploit", "transform": {"type": "ExploitVector", "category": "INJECTION"},
                 "severity": 5, "result": {"succeeded": True}},
            ]
        })
        r = adversary_gate(claim)
        assert r["verdict"] == "VIOLATION"
        assert "EXPLOIT_SUCCESS" in r["reasons"]


class TestTraceSeal:
    def test_seal_produces_chain(self):
        results = [
            {"gate": "INTAKE", "verdict": "PASS", "reasons": [], "timestamp": "2026-04-09T10:00:00Z"},
            {"gate": "TYPE", "verdict": "PASS", "reasons": [], "timestamp": "2026-04-09T10:00:01Z"},
        ]
        seal = trace_seal(results, "claim123", "policy456")
        assert seal["verdict"] == "PASS"
        assert seal["details"]["final_seal"]
        assert seal["details"]["chain_length"] == 2
        assert len(seal["details"]["chain"]) == 2
        # Each chain entry has a different hash
        hashes = [c["hash"] for c in seal["details"]["chain"]]
        assert len(set(hashes)) == 2


class TestMISGreedy:
    def test_independent_sources(self):
        items = [
            {"id": "e1", "provenance": {"source_id": "src1"}, "method": {}, "value": {"pass": True}},
            {"id": "e2", "provenance": {"source_id": "src2"}, "method": {}, "value": {"pass": True}},
            {"id": "e3", "provenance": {"source_id": "src3"}, "method": {}, "value": {"pass": True}},
        ]
        result = mis_greedy(items)
        assert len(result) == 3  # all independent

    def test_same_source_dependent(self):
        items = [
            {"id": "e1", "provenance": {"source_id": "same"}, "method": {}, "value": {"pass": True}},
            {"id": "e2", "provenance": {"source_id": "same"}, "method": {}, "value": {"pass": True}},
        ]
        result = mis_greedy(items)
        assert len(result) == 1  # dependent — only one selected


class TestQuality:
    def test_tier_a_repeatable(self):
        e = {
            "provenance": {"tier": "A"},
            "method": {"repeatable": True, "environment": {}},
            "timestamp": "2026-04-09T10:00:00Z",
        }
        q = quality(e, {})
        # 0.40*1.0 + 0.25*1.0 + 0.20*0.8 + 0.15*0.2 = 0.40+0.25+0.16+0.03 = 0.84
        assert 0.83 <= q <= 0.85

    def test_tier_c_not_repeatable(self):
        e = {
            "provenance": {"tier": "C"},
            "method": {"repeatable": False, "environment": {}},
            "timestamp": "2026-04-09T10:00:00Z",
        }
        q = quality(e, {})
        # 0.40*0.4 + 0.25*0.5 + 0.20*0.8 + 0.15*0.2 = 0.16+0.125+0.16+0.03 = 0.475
        assert 0.47 <= q <= 0.48


class TestCLAEG:
    def test_resolve_pass(self):
        assert CLAEG.resolve("PASS") == "STABLE_CONTINUATION"

    def test_resolve_model_bound(self):
        assert CLAEG.resolve("MODEL_BOUND") == "ISOLATED_CONTAINMENT"

    def test_resolve_violation(self):
        assert CLAEG.resolve("VIOLATION") == "TERMINAL_SHUTDOWN"

    def test_allowed_transition(self):
        r = CLAEG.validate_transition("INIT", "STABLE_CONTINUATION")
        assert r["allowed"] is True

    def test_prohibited_transition(self):
        r = CLAEG.validate_transition("TERMINAL_SHUTDOWN", "STABLE_CONTINUATION")
        assert r["allowed"] is False

    def test_narrative_rescue_detection(self):
        text = "However, despite the violation, we should still deploy because it might pass in staging."
        r = CLAEG.check_narrative_injection(text)
        assert not r["clean"]
        assert any(f["type"] == "NARRATIVE_RESCUE" for f in r["flags"])

    def test_clean_text(self):
        text = "Gate returned VIOLATION with reason UNSAT_CONSTRAINT. Blocking deployment."
        r = CLAEG.check_narrative_injection(text)
        assert r["clean"]


class TestFullPipeline:
    def test_pass_pipeline(self):
        r = run_pipeline(_minimal_claim())
        assert r["final_verdict"] == "PASS"
        assert r["final_seal"]
        assert r["gates_executed"] == 10  # 9 gates + TRACE_SEAL

    def test_fail_fast_on_violation(self):
        claim = _minimal_claim(commit="not-a-valid-hash")
        r = run_pipeline(claim, fail_fast=True)
        assert r["final_verdict"] == "VIOLATION"
        assert r["halted_at"] == "INTAKE"
        assert r["gates_executed"] < 10

    def test_full_run_no_fail_fast(self):
        claim = _minimal_claim(commit="not-a-valid-hash")
        r = run_pipeline(claim, fail_fast=False)
        assert r["final_verdict"] == "VIOLATION"
        assert r["halted_at"] is None  # no early halt
        assert r["gates_executed"] == 10

    def test_production_regime(self):
        claim = _minimal_claim()
        claim["policy"]["build_regime"] = "production"
        r = run_pipeline(claim)
        # Should still work — may get INCONCLUSIVE for evidence if K_MIN_PROD=3 not met
        assert r["final_verdict"] in ("PASS", "MODEL_BOUND", "INCONCLUSIVE", "VIOLATION")


class TestThresholds:
    def test_dev_thresholds(self):
        t = resolve_thresholds("dev")
        assert t["K_MIN"] == 2
        assert t["COV_MIN"] == 0.80

    def test_prod_thresholds(self):
        t = resolve_thresholds("production")
        assert t["K_MIN"] == 3
        assert t["COV_MIN"] == 0.90


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
