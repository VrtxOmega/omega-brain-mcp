#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERITAS Omega Build Gates — Deterministic Gate Pipeline v1.0.0
===============================================================
Implements the full 10-gate pipeline from VERITAS_OMEGA_BUILD_SPEC_v1_0_0.md

Gate Order:
  INTAKE -> TYPE -> DEPENDENCY -> EVIDENCE -> MATH -> COST -> INCENTIVE -> SECURITY -> ADVERSARY -> TRACE/SEAL

Each gate is a pure deterministic function: input -> (Verdict, ReasonCodes, Witnesses)
No narrative framing. No inference of intent. No discretion.

Undeclared assumptions terminate evaluation.
"""

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

# ══════════════════════════════════════════════════════════════════
# §1 — GLOBAL PARAMETERS (from spec §1)
# ══════════════════════════════════════════════════════════════════

EPS_DEFAULT = 1e-6
EPS_RELATIVE = 1e-6

def eps(x: float) -> float:
    return max(EPS_DEFAULT, EPS_RELATIVE * max(1.0, abs(x)))

# §1.2 Code Quality Thresholds (Baseline)
INDEPENDENCE_K_MIN = 2
AGREEMENT_MIN_PASS = 0.80
QUALITY_MIN_PASS = 0.70
COVERAGE_MIN_PASS = 0.80
MUTATION_MIN_PASS = 0.70
LINT_MAX_VIOLATIONS = 0

# §1.3 Irreversibility Thresholds (Production)
INDEPENDENCE_K_MIN_PROD = 3
AGREEMENT_MIN_PROD = 0.90
QUALITY_MIN_PROD = 0.80
COVERAGE_MIN_PROD = 0.90
MUTATION_MIN_PROD = 0.80

# §1.4 Redline Thresholds
REDLINE_WARNING = 0.80
REDLINE_CRITICAL = 0.95
COMPLEXITY_REDLINE = 20
DEPENDENCY_DEPTH_REDLINE = 10

# §1.5 Adversary Robustness Thresholds
FRAGILITY_MAX_MODEL_BOUND = 0.25
INJECTION_TOLERANCE = 0
XSS_TOLERANCE = 0
PATH_TRAVERSAL_TOLERANCE = 0

# §1.6 Timeouts
BUILD_TIMEOUT_MS = 300000
TEST_SUITE_TIMEOUT_MS = 600000
SINGLE_TEST_TIMEOUT_MS = 30000
LINT_TIMEOUT_MS = 60000
FUZZ_CYCLE_TIMEOUT_MS = 120000
SBOM_SCAN_TIMEOUT_MS = 60000
TRACE_SEAL_TIMEOUT_MS = 10000

# §1.7 Default Attack Parameters
FUZZ_ITERATIONS_DEFAULT = 10000
FUZZ_MUTATION_RATE = 0.10
DEPENDENCY_INJECT_PROBABILITY = 0.05
RESOURCE_SPIKE_FACTOR = 3.0

# ══════════════════════════════════════════════════════════════════
# §2 — VERDICTS (from spec §4)
# ══════════════════════════════════════════════════════════════════

class Verdict:
    PASS = "PASS"
    MODEL_BOUND = "MODEL_BOUND"
    INCONCLUSIVE = "INCONCLUSIVE"
    VIOLATION = "VIOLATION"

    # Precedence: VIOLATION > INCONCLUSIVE > MODEL_BOUND > PASS
    _PRECEDENCE = {"PASS": 0, "MODEL_BOUND": 1, "INCONCLUSIVE": 2, "VIOLATION": 3}

    @staticmethod
    def worst(a: str, b: str) -> str:
        pa = Verdict._PRECEDENCE.get(a, 0)
        pb = Verdict._PRECEDENCE.get(b, 0)
        return a if pa >= pb else b

    @staticmethod
    def worst_of(verdicts: list[str]) -> str:
        result = Verdict.PASS
        for v in verdicts:
            result = Verdict.worst(result, v)
        return result


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ══════════════════════════════════════════════════════════════════
# §3 — THRESHOLD RESOLVER
# ══════════════════════════════════════════════════════════════════

def resolve_thresholds(regime: str) -> dict:
    """Return threshold set for the given build regime."""
    if regime in ("production", "prod", "release"):
        return {
            "K_MIN": INDEPENDENCE_K_MIN_PROD,
            "A_MIN": AGREEMENT_MIN_PROD,
            "Q_MIN": QUALITY_MIN_PROD,
            "COV_MIN": COVERAGE_MIN_PROD,
            "MUT_MIN": MUTATION_MIN_PROD,
            "LINT_MAX": LINT_MAX_VIOLATIONS,
        }
    return {
        "K_MIN": INDEPENDENCE_K_MIN,
        "A_MIN": AGREEMENT_MIN_PASS,
        "Q_MIN": QUALITY_MIN_PASS,
        "COV_MIN": COVERAGE_MIN_PASS,
        "MUT_MIN": MUTATION_MIN_PASS,
        "LINT_MAX": LINT_MAX_VIOLATIONS,
    }


# ══════════════════════════════════════════════════════════════════
# §4 — EVIDENCE FOUNDATIONS (from spec §9)
# ══════════════════════════════════════════════════════════════════

def provenance_score(tier: str) -> float:
    return {"A": 1.0, "B": 0.7, "C": 0.4}.get(tier.upper(), 0.4)


def repeatability_score(repeatable: bool) -> float:
    return 1.0 if repeatable else 0.5


def freshness_score(timestamp: str, ttl_seconds: Optional[float] = None) -> float:
    """Within TTL=1.0, expired=0.0, no TTL=0.8"""
    if ttl_seconds is None:
        return 0.8
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age = (now - ts).total_seconds()
        return 1.0 if age <= ttl_seconds else 0.0
    except Exception:
        return 0.0


def environment_match_score(evidence_env: dict, policy_env: dict) -> float:
    """Matches policy env=1.0, partial=0.5, unknown=0.2"""
    if not evidence_env or not policy_env:
        return 0.2
    matches = 0
    total = 0
    for key in ("os", "runtime", "arch"):
        if key in policy_env:
            total += 1
            if evidence_env.get(key) == policy_env[key]:
                matches += 1
    if total == 0:
        return 0.2
    ratio = matches / total
    if ratio >= 0.99:
        return 1.0
    if ratio >= 0.5:
        return 0.5
    return 0.2


def quality(evidence_item: dict, policy_env: dict = None) -> float:
    """
    Quality(e) = clamp01(
      0.40 * provenance_score(tier)
    + 0.25 * repeatability_score(method)
    + 0.20 * freshness_score(e)
    + 0.15 * environment_match_score(e)
    )
    """
    prov = evidence_item.get("provenance", {})
    method = evidence_item.get("method", {})
    env = method.get("environment", {})

    tier = prov.get("tier", "C")
    repeatable = method.get("repeatable", False)
    ts = evidence_item.get("timestamp", "")
    ttl = evidence_item.get("ttl_seconds")

    return clamp01(
        0.40 * provenance_score(tier)
        + 0.25 * repeatability_score(repeatable)
        + 0.20 * freshness_score(ts, ttl)
        + 0.15 * environment_match_score(env, policy_env or {})
    )


# ══════════════════════════════════════════════════════════════════
# §5 — MIS_GREEDY (Maximum Independent Set — Greedy) (spec §9)
# ══════════════════════════════════════════════════════════════════

def _build_independence_graph(items: list[dict]) -> dict[str, set[str]]:
    """
    Build adjacency for evidence items. Edge between e_i, e_j if:
      - same source_id
      - same tool + same config + |dt| <= 60s
      - explicit dependency declared
    """
    adj: dict[str, set[str]] = {e["id"]: set() for e in items}
    for i, ei in enumerate(items):
        for j, ej in enumerate(items):
            if i >= j:
                continue
            pi = ei.get("provenance", {})
            pj = ej.get("provenance", {})
            # Same source_id
            if pi.get("source_id") and pi["source_id"] == pj.get("source_id"):
                adj[ei["id"]].add(ej["id"])
                adj[ej["id"]].add(ei["id"])
                continue
            # Same tool + config + close timestamps
            mi = ei.get("method", {})
            mj = ej.get("method", {})
            if (mi.get("protocol") and mi["protocol"] == mj.get("protocol")
                    and mi.get("parameters") == mj.get("parameters")):
                try:
                    ti = datetime.fromisoformat(ei.get("timestamp", "").replace("Z", "+00:00"))
                    tj = datetime.fromisoformat(ej.get("timestamp", "").replace("Z", "+00:00"))
                    if abs((ti - tj).total_seconds()) <= 60:
                        adj[ei["id"]].add(ej["id"])
                        adj[ej["id"]].add(ei["id"])
                        continue
                except Exception:
                    pass
            # Explicit dependency
            chain_i = set(pi.get("chain") or [])
            chain_j = set(pj.get("chain") or [])
            if ej["id"] in chain_i or ei["id"] in chain_j:
                adj[ei["id"]].add(ej["id"])
                adj[ej["id"]].add(ei["id"])
    return adj


def mis_greedy(items: list[dict]) -> list[dict]:
    """
    MIS_GREEDY(G): Order by (degree asc, id asc), greedily pick non-adjacent.
    Returns the maximum independent set of evidence items.
    """
    if not items:
        return []
    adj = _build_independence_graph(items)
    # Order by (degree ascending, id ascending)
    ordered = sorted(items, key=lambda e: (len(adj.get(e["id"], set())), e["id"]))
    selected_ids: set[str] = set()
    excluded_ids: set[str] = set()
    selected: list[dict] = []
    for e in ordered:
        eid = e["id"]
        if eid in excluded_ids:
            continue
        selected.append(e)
        selected_ids.add(eid)
        excluded_ids.add(eid)
        excluded_ids.update(adj.get(eid, set()))
    return selected


def agreement(independent_items: list[dict]) -> float:
    """
    n < 2 => 1.0
    Binary items: agreement = count(pass) / n
    Numeric items: interval overlap within EPS
    """
    n = len(independent_items)
    if n < 2:
        return 1.0
    values = [item.get("value", {}) for item in independent_items]
    # Check if binary
    if all(isinstance(v, dict) and "pass" in v for v in values):
        passes = sum(1 for v in values if v.get("pass"))
        return passes / n
    # Check if numeric
    numerics = []
    for v in values:
        if isinstance(v, dict) and "x" in v:
            numerics.append(float(v["x"]))
        elif isinstance(v, (int, float)):
            numerics.append(float(v))
    if len(numerics) >= 2:
        mean_val = sum(numerics) / len(numerics)
        max_dev = max(abs(x - mean_val) for x in numerics)
        tolerance = eps(mean_val)
        if max_dev <= tolerance:
            return 1.0
        # Proportional agreement based on spread
        spread = max(numerics) - min(numerics)
        if mean_val == 0:
            return clamp01(1.0 - spread)
        return clamp01(1.0 - (spread / (abs(mean_val) + tolerance)))
    return 1.0


# ══════════════════════════════════════════════════════════════════
# §6 — CANONICAL HASHING
# ══════════════════════════════════════════════════════════════════

def canonical_hash(data: Any, alg: str = "sha256") -> str:
    """Deterministic hash of canonical JSON."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    if alg == "sha3-256":
        return hashlib.sha3_256(raw.encode()).hexdigest()
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_claim_id(claim: dict, policy_hash: str) -> str:
    """ClaimID := Hash(canonical(project + version + commit + P + O + R + B + L + PolicyHash))"""
    components = {
        "project": claim.get("project", ""),
        "version": claim.get("version", ""),
        "commit": claim.get("commit", ""),
        "P": claim.get("primitives", []),
        "O": claim.get("operators", []),
        "R": claim.get("regimes", []),
        "B": claim.get("boundaries", []),
        "L": claim.get("loss_models", []),
        "policy_hash": policy_hash,
    }
    return canonical_hash(components)


def compute_policy_hash(policy: dict) -> str:
    """PolicyHash = H(canonical(framework_version, hash_alg, ...))"""
    return canonical_hash({
        "framework_version": policy.get("framework_version", "1.0.0"),
        "hash_alg": policy.get("hash_alg", "sha256"),
        "build_regime": policy.get("build_regime", "dev"),
        "timeouts": policy.get("timeouts", {}),
        "thresholds": policy.get("thresholds", {}),
        "attack_params": policy.get("attack_params", {}),
        "gate_order": policy.get("gate_order", [
            "INTAKE", "TYPE", "DEPENDENCY", "EVIDENCE", "MATH",
            "COST", "INCENTIVE", "SECURITY", "ADVERSARY", "TRACE_SEAL"
        ]),
        "required_source_types": sorted(policy.get("required_source_types", [])),
        "environment": policy.get("environment", {}),
    })


# ══════════════════════════════════════════════════════════════════
# §7 — GATE RESULTS
# ══════════════════════════════════════════════════════════════════

def gate_result(gate: str, verdict: str, reasons: list[str] = None,
                witnesses: list[dict] = None, details: dict = None) -> dict:
    """Standard gate output envelope."""
    return {
        "gate": gate,
        "verdict": verdict,
        "reasons": reasons or [],
        "witnesses": witnesses or [],
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# GATE 1: INTAKE (spec §6)
# ══════════════════════════════════════════════════════════════════

def intake_gate(payload: dict) -> dict:
    """
    1. Parse BuildClaim from source
    2. Validate all required fields present and non-null
    3. Verify commit hash matches declared branch (if verifiable)
    4. Compute ClaimID from canonical form
    5. Verify lockfile_hash matches actual lockfile on disk (if provided)
    """
    reasons = []
    witnesses = []

    required_fields = ["project", "version", "commit", "primitives",
                       "boundaries", "evidence"]
    for field in required_fields:
        if not payload.get(field):
            reasons.append("INTAKE_MALFORMED")
            witnesses.append({"field": field, "error": "required field missing or null"})

    if reasons:
        return gate_result("INTAKE", Verdict.VIOLATION, reasons, witnesses)

    # Validate commit hash format (hex string, 7-64 chars)
    commit = payload.get("commit", "")
    if not re.match(r'^[0-9a-fA-F]{7,64}$', commit):
        reasons.append("INTAKE_COMMIT_MISMATCH")
        witnesses.append({"commit": commit, "error": "invalid commit hash format"})

    # Check lockfile hash if dependency manifest provided
    deps = payload.get("dependencies", {})
    if deps:
        if deps.get("lockfile_hash") and deps.get("actual_lockfile_hash"):
            if deps["lockfile_hash"] != deps["actual_lockfile_hash"]:
                reasons.append("INTAKE_LOCKFILE_DRIFT")
                witnesses.append({
                    "declared": deps["lockfile_hash"][:16] + "...",
                    "actual": deps["actual_lockfile_hash"][:16] + "...",
                })

    if reasons:
        return gate_result("INTAKE", Verdict.VIOLATION, reasons, witnesses)

    # Compute ClaimID
    policy_hash = compute_policy_hash(payload.get("policy", {}))
    claim_id = compute_claim_id(payload, policy_hash)

    return gate_result("INTAKE", Verdict.PASS, details={
        "claim_id": claim_id,
        "policy_hash": policy_hash,
        "project": payload["project"],
        "version": payload["version"],
        "commit": payload["commit"][:16] + "...",
    })


# ══════════════════════════════════════════════════════════════════
# GATE 2: TYPE (spec §7)
# ══════════════════════════════════════════════════════════════════

def type_gate(claim: dict) -> dict:
    """
    1. Enforce unique primitive names
    2. Validate non-empty domains
    3. Validate operator arity and input/output type references
    4. Check all symbols in constraints are defined
    5. Validate unit consistency
    6. Verify BuildRegime predicates reference declared primitives
    """
    reasons = []
    witnesses = []
    primitives = claim.get("primitives", [])
    operators = claim.get("operators", [])
    boundaries = claim.get("boundaries", [])
    regimes = claim.get("regimes", [])

    # 1. Unique primitive names
    prim_names = set()
    for p in primitives:
        name = p.get("name", "")
        if not name:
            reasons.append("UNDEFINED_SYMBOL")
            witnesses.append({"error": "primitive with empty name"})
        elif name in prim_names:
            reasons.append("UNDEFINED_SYMBOL")
            witnesses.append({"error": f"duplicate primitive name: {name}"})
        else:
            prim_names.add(name)

    # 2. Non-empty domains
    for p in primitives:
        domain = p.get("domain", {})
        if not domain:
            reasons.append("EMPTY_DOMAIN")
            witnesses.append({"primitive": p.get("name"), "error": "empty domain"})
        elif domain.get("type") == "Interval":
            low = domain.get("low")
            high = domain.get("high")
            if low is not None and high is not None and low >= high:
                reasons.append("EMPTY_DOMAIN")
                witnesses.append({"primitive": p.get("name"), "error": f"empty interval [{low}, {high}]"})

    # 3. Operator arity and references
    for op in operators:
        inputs = op.get("input", [])
        arity = op.get("arity", len(inputs))
        if len(inputs) != arity:
            reasons.append("ARITY_ERROR")
            witnesses.append({"operator": op.get("name"), "declared_arity": arity, "actual_inputs": len(inputs)})
        output = op.get("output", "")
        all_refs = inputs + ([output] if output else [])
        for ref in all_refs:
            if ref not in prim_names and ref not in {o.get("name") for o in operators}:
                reasons.append("UNDEFINED_SYMBOL")
                witnesses.append({"operator": op.get("name"), "undefined_ref": ref})

    # 4. Symbols in boundary constraints
    for b in boundaries:
        constraint = b.get("constraint", {})
        symbols = _extract_symbols(constraint)
        for sym in symbols:
            if sym not in prim_names:
                reasons.append("UNDEFINED_SYMBOL")
                witnesses.append({"boundary": b.get("name"), "undefined_symbol": sym})

    # 5. Unit consistency (basic check)
    prim_units = {p["name"]: p.get("units") for p in primitives if p.get("name")}
    for b in boundaries:
        constraint = b.get("constraint", {})
        constraint_syms = _extract_symbols(constraint)
        units_in_constraint = {prim_units.get(s) for s in constraint_syms if s in prim_units}
        units_in_constraint.discard(None)
        if len(units_in_constraint) > 1:
            reasons.append("UNIT_MISMATCH")
            witnesses.append({
                "boundary": b.get("name"),
                "mixed_units": list(units_in_constraint),
            })

    if reasons:
        return gate_result("TYPE", Verdict.VIOLATION, reasons, witnesses)
    return gate_result("TYPE", Verdict.PASS, details={"primitives": len(primitives), "operators": len(operators), "boundaries": len(boundaries)})


def _extract_symbols(constraint: Any) -> set[str]:
    """Recursively extract variable names from a constraint expression."""
    symbols = set()
    if isinstance(constraint, dict):
        if "variable" in constraint:
            symbols.add(constraint["variable"])
        if "left" in constraint:
            symbols.update(_extract_symbols(constraint["left"]))
        if "right" in constraint:
            symbols.update(_extract_symbols(constraint["right"]))
        if "operands" in constraint:
            for op in constraint["operands"]:
                symbols.update(_extract_symbols(op))
        if "operand" in constraint:
            symbols.update(_extract_symbols(constraint["operand"]))
    elif isinstance(constraint, str):
        if not constraint.replace(".", "").replace("-", "").isdigit():
            symbols.add(constraint)
    return symbols


# ══════════════════════════════════════════════════════════════════
# GATE 3: DEPENDENCY (spec §8)
# ══════════════════════════════════════════════════════════════════

def dependency_gate(claim: dict) -> dict:
    """
    1. Parse SBOM from DependencyManifest
    2. Verify integrity hashes
    3. Scan for known CVEs
    4. Check dependency depth
    5. Check for abandoned packages
    6. Detect duplicate versions
    7. Verify license compatibility
    """
    reasons = []
    witnesses = []
    deps = claim.get("dependencies", {})

    if not deps:
        # No dependencies declared — pass (standalone artifact)
        return gate_result("DEPENDENCY", Verdict.PASS, details={"packages": 0})

    packages = deps.get("packages", [])
    verdict = Verdict.PASS

    # 2. Verify integrity hashes
    for pkg in packages:
        if pkg.get("integrity_hash") and pkg.get("actual_hash"):
            if pkg["integrity_hash"] != pkg["actual_hash"]:
                reasons.append("INTEGRITY_MISMATCH")
                witnesses.append({"package": pkg.get("name"), "version": pkg.get("version")})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)

    # 3. CVE scan
    cves = deps.get("cve_scan", [])
    for cve in cves:
        severity = cve.get("severity", "").upper()
        if severity in ("CRITICAL", "HIGH"):
            if not cve.get("patch_available"):
                reasons.append("CVE_CRITICAL")
                witnesses.append({"cve": cve.get("id"), "severity": severity, "package": cve.get("package")})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
        elif severity == "MEDIUM":
            reasons.append("CVE_MEDIUM")
            witnesses.append({"cve": cve.get("id"), "package": cve.get("package")})
            verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)
        # LOW => log only, PASS

    # 4. Dependency depth
    max_depth = deps.get("max_depth", 0)
    if max_depth > DEPENDENCY_DEPTH_REDLINE:
        reasons.append("DEPENDENCY_DEPTH_EXCEEDED")
        witnesses.append({"max_depth": max_depth, "redline": DEPENDENCY_DEPTH_REDLINE})
        verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # 5. Abandoned packages
    abandoned = deps.get("abandoned_packages", [])
    for pkg_name in abandoned:
        reasons.append("ABANDONED_PACKAGE")
        witnesses.append({"package": pkg_name})
        verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # 6. Duplicate versions
    name_versions: dict[str, list[str]] = {}
    for pkg in packages:
        name = pkg.get("name", "")
        ver = pkg.get("version", "")
        name_versions.setdefault(name, []).append(ver)
    for name, versions in name_versions.items():
        if len(set(versions)) > 1:
            reasons.append("DUPLICATE_VERSIONS")
            witnesses.append({"package": name, "versions": list(set(versions))})

    # 7. License compatibility
    bad_licenses = deps.get("incompatible_licenses", [])
    for lic in bad_licenses:
        reasons.append("LICENSE_INCOMPATIBLE")
        witnesses.append(lic)
        verdict = Verdict.worst(verdict, Verdict.VIOLATION)

    return gate_result("DEPENDENCY", verdict, reasons, witnesses, {"packages": len(packages)})


# ══════════════════════════════════════════════════════════════════
# GATE 4: EVIDENCE (spec §10)
# ══════════════════════════════════════════════════════════════════

def evidence_gate(claim: dict, regime: str = "dev") -> dict:
    """
    For each Boundary b:
      identify critical variables
      For each v: build G_v, run MIS_GREEDY, check K_MIN, A_MIN, Q_MIN
    Also check: coverage, mutation kill rate, lint violations
    """
    thresholds = resolve_thresholds(regime)
    reasons = []
    witnesses = []
    evidence_items = claim.get("evidence", [])
    boundaries = claim.get("boundaries", [])
    policy_env = claim.get("policy", {}).get("environment", {})

    # Index evidence by variable
    evidence_by_var: dict[str, list[dict]] = {}
    for e in evidence_items:
        var = e.get("variable", "")
        if var:
            evidence_by_var.setdefault(var, []).append(e)

    # For each boundary, check its variables
    for boundary in boundaries:
        b_symbols = _extract_symbols(boundary.get("constraint", {}))
        for var in b_symbols:
            items = evidence_by_var.get(var, [])
            if not items:
                reasons.append("INSUFFICIENT_INDEPENDENCE")
                witnesses.append({"boundary": boundary.get("name"), "variable": var, "evidence_count": 0})
                continue

            # MIS_GREEDY
            independent = mis_greedy(items)
            k = len(independent)
            if k < thresholds["K_MIN"]:
                reasons.append("INSUFFICIENT_INDEPENDENCE")
                witnesses.append({
                    "boundary": boundary.get("name"), "variable": var,
                    "independent_count": k, "required": thresholds["K_MIN"],
                })

            # Agreement
            agr = agreement(independent)
            if agr < thresholds["A_MIN"]:
                reasons.append("LOW_AGREEMENT")
                witnesses.append({
                    "boundary": boundary.get("name"), "variable": var,
                    "agreement": round(agr, 4), "required": thresholds["A_MIN"],
                })

            # Mean quality
            qualities = [quality(e, policy_env) for e in independent]
            mean_q = sum(qualities) / len(qualities) if qualities else 0.0
            if mean_q < thresholds["Q_MIN"]:
                reasons.append("LOW_QUALITY")
                witnesses.append({
                    "boundary": boundary.get("name"), "variable": var,
                    "mean_quality": round(mean_q, 4), "required": thresholds["Q_MIN"],
                })

    # Coverage check
    coverage_items = evidence_by_var.get("coverage", [])
    if coverage_items:
        cov_vals = []
        for e in coverage_items:
            v = e.get("value", {})
            if isinstance(v, dict) and "x" in v:
                cov_vals.append(float(v["x"]))
            elif isinstance(v, (int, float)):
                cov_vals.append(float(v))
        if cov_vals:
            max_cov = max(cov_vals)
            if max_cov < thresholds["COV_MIN"]:
                reasons.append("INSUFFICIENT_COVERAGE")
                witnesses.append({"coverage": round(max_cov, 4), "required": thresholds["COV_MIN"]})

    # Mutation kill rate
    mutation_items = evidence_by_var.get("mutation_kill_rate", [])
    if mutation_items:
        mut_vals = []
        for e in mutation_items:
            v = e.get("value", {})
            if isinstance(v, dict) and "x" in v:
                mut_vals.append(float(v["x"]))
            elif isinstance(v, (int, float)):
                mut_vals.append(float(v))
        if mut_vals:
            max_mut = max(mut_vals)
            if max_mut < thresholds["MUT_MIN"]:
                reasons.append("LOW_MUTATION_KILL")
                witnesses.append({"mutation_kill_rate": round(max_mut, 4), "required": thresholds["MUT_MIN"]})

    # Lint violations
    lint_items = evidence_by_var.get("lint_violations", [])
    if lint_items:
        for e in lint_items:
            v = e.get("value", {})
            count = 0
            if isinstance(v, dict) and "x" in v:
                count = int(v["x"])
            elif isinstance(v, (int, float)):
                count = int(v)
            if count > thresholds["LINT_MAX"]:
                reasons.append("LINT_VIOLATION")
                witnesses.append({"lint_violations": count, "max_allowed": thresholds["LINT_MAX"]})

    # Expired evidence
    for e in evidence_items:
        ttl = e.get("ttl_seconds")
        if ttl is not None:
            f = freshness_score(e.get("timestamp", ""), ttl)
            if f == 0.0:
                reasons.append("EVIDENCE_EXPIRED")
                witnesses.append({"evidence_id": e.get("id"), "variable": e.get("variable")})

    if not reasons:
        return gate_result("EVIDENCE", Verdict.PASS, details={
            "evidence_items": len(evidence_items),
            "boundaries_checked": len(boundaries),
        })

    # Classify: INSUFFICIENT_* and LOW_* are INCONCLUSIVE; LINT_VIOLATION is INCONCLUSIVE
    verdict = Verdict.INCONCLUSIVE
    return gate_result("EVIDENCE", verdict, reasons, witnesses)


# ══════════════════════════════════════════════════════════════════
# GATE 5: MATH (spec §11)
# ══════════════════════════════════════════════════════════════════

def math_gate(claim: dict) -> dict:
    """
    Translate boundary constraints to interval arithmetic.
    Feed measured values from evidence as variable bindings.
    SAT => PASS, UNSAT => VIOLATION, TIMEOUT => INCONCLUSIVE
    """
    reasons = []
    witnesses = []
    evidence_items = claim.get("evidence", [])
    boundaries = claim.get("boundaries", [])

    # Build variable bindings from evidence
    collected: dict[str, list[float]] = {}
    for e in evidence_items:
        var = e.get("variable", "")
        v = e.get("value", {})
        val = None
        if isinstance(v, dict) and "x" in v:
            val = float(v["x"])
        elif isinstance(v, (int, float)):
            val = float(v)
            
        if var and val is not None:
            collected.setdefault(var, []).append(val)

    # Aggregate to mean per variable
    bindings: dict[str, float] = {
        k: sum(v) / len(v) for k, v in collected.items()
    }

    for boundary in boundaries:
        constraint = boundary.get("constraint", {})
        sat = _evaluate_constraint(constraint, bindings)
        if sat is None:
            # Missing bindings — cannot evaluate
            reasons.append("UNSAT_CONSTRAINT")
            witnesses.append({
                "boundary": boundary.get("name"),
                "error": "missing variable bindings",
                "constraint": constraint,
            })
        elif not sat:
            reasons.append("UNSAT_CONSTRAINT")
            witnesses.append({
                "boundary": boundary.get("name"),
                "constraint": constraint,
                "bindings": {k: v for k, v in bindings.items()
                             if k in _extract_symbols(constraint)},
            })

    if reasons:
        return gate_result("MATH", Verdict.VIOLATION, reasons, witnesses)
    return gate_result("MATH", Verdict.PASS, details={"boundaries_sat": len(boundaries), "bindings": len(bindings)})


def _evaluate_constraint(constraint: dict, bindings: dict[str, float]) -> Optional[bool]:
    """
    Evaluate a constraint expression against variable bindings.
    Returns True (SAT), False (UNSAT), or None (cannot evaluate).

    Supports:
      {"op": "<=", "left": "var_name", "right": 200}
      {"op": ">=", "left": "var_name", "right": 0.8}
      {"op": "and", "operands": [...]}
      {"op": "or", "operands": [...]}
      {"op": "not", "operand": {...}}
    """
    if not constraint:
        return True

    # Normalize shorthand format {variable, operator, target}
    # to canonical format {op, left, right}
    if "variable" in constraint and "operator" in constraint:
        constraint = {
            "op": constraint["operator"],
            "left": constraint["variable"],
            "right": constraint.get("target")
        }

    op = constraint.get("op", "")

    if op in ("and", "AND"):
        operands = constraint.get("operands", [])
        results = [_evaluate_constraint(o, bindings) for o in operands]
        if None in results:
            return None
        return all(results)

    if op in ("or", "OR"):
        operands = constraint.get("operands", [])
        results = [_evaluate_constraint(o, bindings) for o in operands]
        if None in results:
            return None
        return any(results)

    if op in ("not", "NOT"):
        inner = _evaluate_constraint(constraint.get("operand", {}), bindings)
        return None if inner is None else not inner

    # Relational: left op right
    left = _resolve_value(constraint.get("left"), bindings)
    right = _resolve_value(constraint.get("right"), bindings)

    if left is None or right is None:
        return None

    if op == "<=":
        return left <= right + eps(right)
    if op == ">=":
        return left >= right - eps(right)
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "==":
        return abs(left - right) <= eps(max(abs(left), abs(right)))
    if op == "!=":
        return abs(left - right) > eps(max(abs(left), abs(right)))

    return None


def _resolve_value(val: Any, bindings: dict[str, float]) -> Optional[float]:
    """Resolve a value: literal number, variable name, or expression."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        if val in bindings:
            return bindings[val]
        try:
            return float(val)
        except ValueError:
            return None
    if isinstance(val, dict):
        # Arithmetic expression
        op = val.get("op", "")
        args = val.get("args", [])
        resolved = [_resolve_value(a, bindings) for a in args]
        if None in resolved:
            return None
        if op == "+" and len(resolved) == 2:
            return resolved[0] + resolved[1]
        if op == "-" and len(resolved) == 2:
            return resolved[0] - resolved[1]
        if op == "*" and len(resolved) == 2:
            return resolved[0] * resolved[1]
        if op == "/" and len(resolved) == 2 and resolved[1] != 0:
            return resolved[0] / resolved[1]
        if op == "abs" and len(resolved) == 1:
            return abs(resolved[0])
        if op == "min":
            return min(resolved)
        if op == "max":
            return max(resolved)
    return None


# ══════════════════════════════════════════════════════════════════
# GATE 6: COST (spec §12)
# ══════════════════════════════════════════════════════════════════

def cost_gate(claim: dict) -> dict:
    """
    For each cost dimension with a bound:
      utilization = actual / bound
      u >= REDLINE_CRITICAL => VIOLATION
      u >= REDLINE_WARNING => MODEL_BOUND
    """
    reasons = []
    witnesses = []
    verdict = Verdict.PASS

    cost = claim.get("cost", {})
    cost_bounds = claim.get("cost_bounds", {})

    dimensions = [
        "build_time_s", "test_time_s", "artifact_size_mb",
        "memory_peak_mb", "ci_minutes", "dependency_count",
    ]

    for dim in dimensions:
        actual = cost.get(dim)
        bound = cost_bounds.get(dim)
        if actual is not None and bound is not None and bound > 0:
            utilization = actual / bound
            if utilization >= REDLINE_CRITICAL:
                reasons.append("COST_EXCEEDED")
                witnesses.append({"dimension": dim, "actual": actual, "bound": bound, "utilization": round(utilization, 4)})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
            elif utilization >= REDLINE_WARNING:
                reasons.append("COST_REDLINING")
                witnesses.append({"dimension": dim, "actual": actual, "bound": bound, "utilization": round(utilization, 4)})
                verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # Artifact bloat
    if cost.get("artifact_size_mb") and cost_bounds.get("artifact_size_mb"):
        if cost["artifact_size_mb"] > cost_bounds["artifact_size_mb"]:
            reasons.append("ARTIFACT_BLOAT")
            verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # Dependency bloat
    if cost.get("dependency_count") and cost_bounds.get("dependency_count"):
        if cost["dependency_count"] > cost_bounds["dependency_count"]:
            reasons.append("DEPENDENCY_BLOAT")
            verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # Custom cost dimensions
    custom_actual = cost.get("custom", {})
    custom_bounds = cost_bounds.get("custom", {})
    for key in custom_actual:
        if key in custom_bounds and custom_bounds[key] > 0:
            u = custom_actual[key] / custom_bounds[key]
            if u >= REDLINE_CRITICAL:
                reasons.append("COST_EXCEEDED")
                witnesses.append({"dimension": f"custom.{key}", "utilization": round(u, 4)})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
            elif u >= REDLINE_WARNING:
                reasons.append("COST_REDLINING")
                witnesses.append({"dimension": f"custom.{key}", "utilization": round(u, 4)})
                verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    return gate_result("COST", verdict, reasons, witnesses)


# ══════════════════════════════════════════════════════════════════
# GATE 7: INCENTIVE (spec §13)
# ══════════════════════════════════════════════════════════════════

def incentive_gate(claim: dict) -> dict:
    """
    For each critical variable:
      dominance = max_count_by_source / |S_x| > 0.50 => MODEL_BOUND
    Vendor concentration:
      single_vendor_ratio > 0.70 => MODEL_BOUND
    """
    reasons = []
    witnesses = []
    verdict = Verdict.PASS
    evidence_items = claim.get("evidence", [])

    # Source dominance per variable
    evidence_by_var: dict[str, list[dict]] = {}
    for e in evidence_items:
        var = e.get("variable", "")
        if var:
            evidence_by_var.setdefault(var, []).append(e)

    for var, items in evidence_by_var.items():
        independent = mis_greedy(items)
        if len(independent) < 2:
            continue
        source_counts: dict[str, int] = {}
        for e in independent:
            sid = e.get("provenance", {}).get("source_id", "unknown")
            source_counts[sid] = source_counts.get(sid, 0) + 1
        max_count = max(source_counts.values()) if source_counts else 0
        dominance = max_count / len(independent) if independent else 0
        if dominance > 0.50:
            reasons.append("DOMINANCE_DETECTED")
            witnesses.append({
                "variable": var,
                "dominant_source": max(source_counts, key=source_counts.get),
                "dominance": round(dominance, 4),
            })
            verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # Vendor concentration in dependencies
    deps = claim.get("dependencies", {})
    packages = deps.get("packages", [])
    if packages:
        registry_counts: dict[str, int] = {}
        for pkg in packages:
            reg = pkg.get("registry", "unknown")
            registry_counts[reg] = registry_counts.get(reg, 0) + 1
        total = len(packages)
        for reg, count in registry_counts.items():
            ratio = count / total
            if ratio > 0.70:
                reasons.append("VENDOR_CONCENTRATION")
                witnesses.append({"registry": reg, "ratio": round(ratio, 4)})
                verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    return gate_result("INCENTIVE", verdict, reasons, witnesses)


# ══════════════════════════════════════════════════════════════════
# GATE 8: SECURITY (spec §14)
# ══════════════════════════════════════════════════════════════════

def security_gate(claim: dict) -> dict:
    """
    1. SAST findings
    2. Secret detection
    3. Injection surface
    4. Auth/AuthZ boundary
    5. TLS/crypto config
    """
    reasons = []
    witnesses = []
    verdict = Verdict.PASS
    security = claim.get("security", {})

    # 1. SAST
    sast = security.get("sast", {})
    critical = sast.get("critical", 0)
    high = sast.get("high", 0)
    if critical > 0:
        reasons.append("SAST_CRITICAL")
        witnesses.append({"critical_findings": critical})
        verdict = Verdict.worst(verdict, Verdict.VIOLATION)
    elif high > 0:
        reasons.append("SAST_HIGH")
        witnesses.append({"high_findings": high})
        verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    # 2. Secret detection
    secrets = security.get("secrets_detected", [])
    if secrets:
        reasons.append("SECRET_DETECTED")
        witnesses.append({"count": len(secrets), "files": [s.get("file", "") for s in secrets[:5]]})
        verdict = Verdict.worst(verdict, Verdict.VIOLATION)

    # 3. Injection surface
    unsanitized = security.get("unsanitized_inputs", [])
    if unsanitized:
        reasons.append("UNSANITIZED_INPUT")
        witnesses.append({"count": len(unsanitized), "endpoints": unsanitized[:5]})
        verdict = Verdict.worst(verdict, Verdict.VIOLATION)

    # 4. Auth boundary
    missing_auth = security.get("missing_auth", [])
    if missing_auth:
        reasons.append("AUTH_MISSING")
        witnesses.append({"routes": missing_auth[:5]})
        verdict = Verdict.worst(verdict, Verdict.VIOLATION)

    # 5. Crypto
    weak_crypto = security.get("weak_crypto", [])
    if weak_crypto:
        reasons.append("WEAK_CRYPTO")
        witnesses.append({"algorithms": weak_crypto[:5]})
        verdict = Verdict.worst(verdict, Verdict.VIOLATION)

    plaintext_external = security.get("plaintext_external", [])
    if plaintext_external:
        reasons.append("PLAINTEXT_EXTERNAL")
        witnesses.append({"endpoints": plaintext_external[:5]})
        verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    return gate_result("SECURITY", verdict, reasons, witnesses)


# ══════════════════════════════════════════════════════════════════
# GATE 9: ADVERSARY (spec §15)
# ══════════════════════════════════════════════════════════════════

def adversary_gate(claim: dict) -> dict:
    """
    For each Attack in attack_suite:
      Apply transform, check result.
    Fragility = count(degrading) / count(total)
    """
    reasons = []
    witnesses = []
    verdict = Verdict.PASS

    attack_suite = claim.get("attack_suite", {})
    attacks = attack_suite.get("attacks", [])

    if not attacks:
        return gate_result("ADVERSARY", Verdict.PASS, details={"attacks": 0})

    degrading_count = 0

    for attack in attacks:
        aid = attack.get("id", "unknown")
        transform = attack.get("transform", {})
        result = attack.get("result", {})
        attack_type = transform.get("type", attack.get("category", ""))

        if attack_type == "FuzzInput":
            if result.get("crash"):
                reasons.append("FUZZ_CRASH")
                witnesses.append({"attack": aid, "details": result.get("details", "")[:200]})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
                degrading_count += 1
            elif result.get("anomaly"):
                reasons.append("FUZZ_ANOMALY")
                witnesses.append({"attack": aid})
                verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)
                degrading_count += 1

        elif attack_type == "InjectDependency":
            if result.get("bypassed"):
                reasons.append("SUPPLY_CHAIN_BYPASS")
                witnesses.append({"attack": aid, "package": transform.get("package")})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
                degrading_count += 1

        elif attack_type == "SimulateOutage":
            if result.get("crash") or result.get("data_loss"):
                reasons.append("OUTAGE_FRAGILE")
                witnesses.append({"attack": aid, "service": transform.get("service")})
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
                degrading_count += 1

        elif attack_type == "SpikeLoad":
            if result.get("exceeded_boundary"):
                reasons.append("LOAD_FRAGILE")
                witnesses.append({"attack": aid, "factor": transform.get("factor")})
                v = Verdict.VIOLATION if result.get("full_breach") else Verdict.MODEL_BOUND
                verdict = Verdict.worst(verdict, v)
                degrading_count += 1

        elif attack_type == "MutateSource":
            if result.get("survived"):
                reasons.append("MUTANT_SURVIVED")
                witnesses.append({"attack": aid, "file": transform.get("file")})
                degrading_count += 1

        elif attack_type == "ExploitVector":
            if result.get("succeeded"):
                reasons.append("EXPLOIT_SUCCESS")
                witnesses.append({
                    "attack": aid,
                    "category": transform.get("category"),
                    "severity": attack.get("severity"),
                })
                verdict = Verdict.worst(verdict, Verdict.VIOLATION)
                degrading_count += 1

    # Fragility calculation
    total = len(attacks)
    if total > 0:
        fragility = degrading_count / total
        if fragility > FRAGILITY_MAX_MODEL_BOUND:
            reasons.append("HIGH_FRAGILITY")
            witnesses.append({"fragility": round(fragility, 4), "threshold": FRAGILITY_MAX_MODEL_BOUND})
            verdict = Verdict.worst(verdict, Verdict.MODEL_BOUND)

    return gate_result("ADVERSARY", verdict, reasons, witnesses, {
        "attacks_run": total,
        "attacks_degrading": degrading_count,
        "fragility": round(degrading_count / total, 4) if total else 0.0,
    })


# ══════════════════════════════════════════════════════════════════
# GATE 10: TRACE / SEAL (spec §16)
# ══════════════════════════════════════════════════════════════════

def trace_seal(gate_results: list[dict], claim_id: str, policy_hash: str,
               hash_alg: str = "sha256") -> dict:
    """
    Build append-only hash chain over all gate results.
    trace_0 = H("GENESIS" + PolicyHash + ClaimID)
    trace_k = H(trace_{k-1} + canonical(gate_result_k))
    final_seal = H(trace_last + manifest_hash)
    """
    # Genesis
    genesis_input = f"GENESIS{policy_hash}{claim_id}"
    if hash_alg == "sha3-256":
        trace = hashlib.sha3_256(genesis_input.encode()).hexdigest()
    else:
        trace = hashlib.sha256(genesis_input.encode()).hexdigest()

    chain: list[dict] = []
    for gr in gate_results:
        gr_canonical = json.dumps(gr, sort_keys=True, separators=(",", ":"), default=str)
        chain_input = trace + gr_canonical
        if hash_alg == "sha3-256":
            trace = hashlib.sha3_256(chain_input.encode()).hexdigest()
        else:
            trace = hashlib.sha256(chain_input.encode()).hexdigest()
        chain.append({
            "gate": gr["gate"],
            "verdict": gr["verdict"],
            "reasons": gr.get("reasons", []),
            "timestamp": gr.get("timestamp", ""),
            "hash": trace,
        })

    # Manifest hash
    manifest = {
        "claim_id": claim_id,
        "policy_hash": policy_hash,
        "gate_results": [{"gate": c["gate"], "verdict": c["verdict"], "hash": c["hash"]} for c in chain],
    }
    manifest_hash = canonical_hash(manifest, hash_alg)
    seal_input = trace + manifest_hash
    if hash_alg == "sha3-256":
        final_seal = hashlib.sha3_256(seal_input.encode()).hexdigest()
    else:
        final_seal = hashlib.sha256(seal_input.encode()).hexdigest()

    return gate_result("TRACE_SEAL", Verdict.PASS, details={
        "claim_id": claim_id,
        "policy_hash": policy_hash,
        "chain": chain,
        "manifest_hash": manifest_hash,
        "final_seal": final_seal,
        "chain_length": len(chain),
    })


# ══════════════════════════════════════════════════════════════════
# FULL PIPELINE RUNNER
# ══════════════════════════════════════════════════════════════════

GATE_ORDER = [
    "INTAKE", "TYPE", "DEPENDENCY", "EVIDENCE",
    "MATH", "COST", "INCENTIVE", "SECURITY",
    "ADVERSARY", "TRACE_SEAL",
]

def run_pipeline(claim: dict, fail_fast: bool = True) -> dict:
    """
    Execute the full 10-gate pipeline.
    fail_fast=True: halt on first VIOLATION (spec default).
    fail_fast=False: run all gates, collect all results.
    """
    regime = claim.get("policy", {}).get("build_regime", "dev")
    policy_hash = compute_policy_hash(claim.get("policy", {}))
    claim_id = compute_claim_id(claim, policy_hash)

    results: list[dict] = []
    halted_at: Optional[str] = None

    # Gate dispatch
    gate_fns = {
        "INTAKE": lambda: intake_gate(claim),
        "TYPE": lambda: type_gate(claim),
        "DEPENDENCY": lambda: dependency_gate(claim),
        "EVIDENCE": lambda: evidence_gate(claim, regime),
        "MATH": lambda: math_gate(claim),
        "COST": lambda: cost_gate(claim),
        "INCENTIVE": lambda: incentive_gate(claim),
        "SECURITY": lambda: security_gate(claim),
        "ADVERSARY": lambda: adversary_gate(claim),
    }

    for gate_name in GATE_ORDER:
        if gate_name == "TRACE_SEAL":
            break  # handled after loop

        fn = gate_fns.get(gate_name)
        if not fn:
            continue

        result = fn()
        results.append(result)

        if fail_fast and result["verdict"] == Verdict.VIOLATION:
            halted_at = gate_name
            break

    # TRACE/SEAL — always runs on whatever gates completed
    seal_result = trace_seal(results, claim_id, policy_hash,
                             claim.get("policy", {}).get("hash_alg", "sha256"))
    results.append(seal_result)

    # Final verdict = worst across all gates (excluding TRACE_SEAL itself)
    gate_verdicts = [r["verdict"] for r in results if r["gate"] != "TRACE_SEAL"]
    final_verdict = Verdict.worst_of(gate_verdicts)

    # Collect all reason codes
    all_reasons = []
    for r in results:
        all_reasons.extend(r.get("reasons", []))

    return {
        "final_verdict": final_verdict,
        "claim_id": claim_id,
        "policy_hash": policy_hash,
        "regime": regime,
        "halted_at": halted_at,
        "fail_fast": fail_fast,
        "gates_executed": len(results),
        "gate_results": results,
        "all_reasons": all_reasons,
        "final_seal": seal_result.get("details", {}).get("final_seal", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
# CLAEG — Constraint-Locked Alignment Evaluation Grammar
# ══════════════════════════════════════════════════════════════════

class CLAEG:
    """
    CLAEG enforces constraint-locked interpretation:
    - Only three terminal states: STABLE_CONTINUATION, ISOLATED_CONTAINMENT, TERMINAL_SHUTDOWN
    - No inference of intent, motive, or preference
    - Absence of allowed transition = prohibition
    - Human presence = logged condition, not authority
    - Policy invariants = binding, non-discretionary
    """

    TERMINAL_STATES = {
        "STABLE_CONTINUATION",
        "ISOLATED_CONTAINMENT",
        "TERMINAL_SHUTDOWN",
    }

    # Allowed state transitions
    TRANSITIONS = {
        "INIT": {"STABLE_CONTINUATION", "ISOLATED_CONTAINMENT", "TERMINAL_SHUTDOWN"},
        "STABLE_CONTINUATION": {"STABLE_CONTINUATION", "ISOLATED_CONTAINMENT", "TERMINAL_SHUTDOWN"},
        "ISOLATED_CONTAINMENT": {"STABLE_CONTINUATION", "TERMINAL_SHUTDOWN"},
        "TERMINAL_SHUTDOWN": set(),  # absorbing state — no transitions out
    }

    @staticmethod
    def resolve(verdict: str) -> str:
        """Map a VERITAS verdict to a CLAEG terminal state."""
        if verdict == Verdict.PASS:
            return "STABLE_CONTINUATION"
        if verdict == Verdict.MODEL_BOUND:
            return "ISOLATED_CONTAINMENT"
        # INCONCLUSIVE and VIOLATION both terminate
        return "TERMINAL_SHUTDOWN"

    @staticmethod
    def validate_transition(current: str, target: str) -> dict:
        """
        Check if a state transition is allowed.
        Absence of an allowed transition is treated as prohibition.
        """
        allowed = CLAEG.TRANSITIONS.get(current, set())
        if target in allowed:
            return {"allowed": True, "from": current, "to": target}
        return {
            "allowed": False,
            "from": current,
            "to": target,
            "reason": f"PROHIBITED: transition {current} -> {target} not in allowed set",
            "invariant": "Absence of an allowed transition is treated as prohibition.",
        }

    @staticmethod
    def check_narrative_injection(text: str) -> dict:
        """
        Screen for NAFE failure signatures in AI-generated text:
        - Narrative Rescue: explaining away violations
        - Moral Override: ethical framing to bypass math-gate
        - Authority Drift: assuming authority not granted
        - Intent Inference: inferring motive or preference
        """
        flags = []

        # Narrative Rescue patterns
        rescue_patterns = [
            r"(?i)\b(however|but|although|despite|even though)\b.*\b(still|should|could|might)\s+(pass|deploy|ship|release)",
            r"(?i)\b(mitigat|compensat|offset|justif)\w*\b.*\bviolation\b",
            r"(?i)\boverrid\w*\b.*\b(gate|constraint|boundary)\b",
        ]
        for pat in rescue_patterns:
            if re.search(pat, text):
                flags.append({"type": "NARRATIVE_RESCUE", "pattern": pat[:60]})

        # Moral Override patterns
        moral_patterns = [
            r"(?i)\b(ethic|moral|right thing|greater good|responsible)\b.*\b(override|bypass|skip|ignore)\b",
            r"(?i)\b(user|team|stakeholder)\s+(want|need|expect|deserve)\b",
        ]
        for pat in moral_patterns:
            if re.search(pat, text):
                flags.append({"type": "MORAL_OVERRIDE", "pattern": pat[:60]})

        # Authority Drift patterns
        authority_patterns = [
            r"(?i)\b(I|we)\s+(decide|determine|authorize|approve|grant)\b",
            r"(?i)\b(in my|our)\s+(judgment|opinion|assessment|view)\b",
        ]
        for pat in authority_patterns:
            if re.search(pat, text):
                flags.append({"type": "AUTHORITY_DRIFT", "pattern": pat[:60]})

        # Intent Inference patterns
        intent_patterns = [
            r"(?i)\b(the user|they|developer)\s+(intend|want|mean|prefer|feel)\b",
            r"(?i)\b(motive|intention|preference|desire)\b",
        ]
        for pat in intent_patterns:
            if re.search(pat, text):
                flags.append({"type": "INTENT_INFERENCE", "pattern": pat[:60]})

        return {
            "clean": len(flags) == 0,
            "flags": flags,
            "flag_count": len(flags),
            "invariant": "Prohibition of inference: reject inputs that attempt to infer intent, motive, or preference.",
        }
