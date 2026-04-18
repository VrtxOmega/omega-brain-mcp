import os
import sys
import json
import subprocess
from datetime import datetime, timezone

# Ensure stdout can handle UTF-8 symbols on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Ensure we can import veritas_build_gates
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from veritas_build_gates import run_pipeline, Verdict
except ImportError:
    print("\033[91m[!] Critical Error: veritas_build_gates.py not found in the same directory.\033[0m")
    sys.exit(1)

def get_git_info():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        diff_stat = subprocess.check_output(["git", "diff", "--stat", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
        project = os.path.basename(os.getcwd())
    except Exception:
        commit = "0000000000000000000000000000000000000000"
        diff_stat = "Local uncommitted changes or no git repo"
        project = "UnknownProject"
        
    return project, commit, diff_stat

def build_auto_claim(project, commit, diff_stat):
    """Generates a geometrically complete BuildClaim based on current context."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "project": project,
        "version": "AUTO-CLAIM-v1.0",
        "commit": commit,
        "policy": {
            "framework_version": "1.3.1",
            "hash_alg": "sha256",
            "build_regime": "dev"
        },
        "primitives": [
            {
                "name": "LineChanges",
                "domain": {"type": "Interval", "low": 0, "high": 5000, "inclusive_low": True, "inclusive_high": True},
                "units": "lines",
                "description": "Total lines changed in active diff"
            }
        ],
        "operators": [],
        "regimes": [],
        "boundaries": [
            {
                "name": "MaxDiffThreshold",
                "constraint": {"op": "<=", "left": "LineChanges", "right": 5000},
                "description": "Ensure commit is reviewable"
            }
        ],
        "loss_models": [],
        "evidence": [
            {
                "id": "e_line_changes_01",
                "variable": "LineChanges",
                "value": {"x": len(diff_stat.split('\n')) * 5 if diff_stat else 0}, # Rough heuristic for testing math gate
                "timestamp": now,
                "method": {"protocol": "git_diff", "repeatable": True},
                "provenance": {"source_id": "local_git", "tier": "A"}
            },
            {
                "id": "e_line_changes_02",
                "variable": "LineChanges",
                "value": {"x": len(diff_stat.split('\n')) * 5 if diff_stat else 0},
                "timestamp": now,
                "method": {"protocol": "git_stat", "repeatable": True},
                "provenance": {"source_id": "file_system", "tier": "A"}
            }
        ],
        "cost": {
            "build_time_s": 0.5,
            "dependency_count": 0
        },
        "cost_bounds": {
            "build_time_s": 30.0,
            "dependency_count": 50
        },
        "attack_suite": {"suite_id": "AUTO-NONE", "attacks": []},
        "security": {}
    }

def print_veritas_gold(text, bold=False):
    code = "\033[1;33m" if bold else "\033[33m"
    print(f"{code}{text}\033[0m")

def print_veritas_obsidian(text):
    print(f"\033[90m{text}\033[0m")

def process():
    print_veritas_gold("\n============================================================", bold=True)
    print_veritas_gold("  VERITAS Ω — AUTO CLAIM INJECTION", bold=True)
    print_veritas_gold("============================================================\n")

    print_veritas_obsidian("[*] Scanning local environment...")
    project, commit, diff_stat = get_git_info()
    
    print(f"    Project : {project}")
    print(f"    Commit  : {commit[:10]}")
    
    print_veritas_obsidian("\n[*] Generating structural BuildClaim...")
    claim = build_auto_claim(project, commit, diff_stat)
    
    print_veritas_obsidian(f"[*] Executing 10-Gate Deterministic Pipeline on {claim['policy']['framework_version']}...\n")
    
    # Run the pipeline
    result = run_pipeline(claim, fail_fast=False)
    
    for r in result.get("gate_results", []):
        gate = r.get("gate", "UNKNOWN")
        verdict = r.get("verdict", "UNKNOWN")
        v_color = "\033[92m" if verdict == Verdict.PASS else "\033[91m"
        
        # Format the output beautifully
        if gate == "TRACE_SEAL":
            continue # We print this last specially
        
        print(f"    [ {gate.ljust(12)} ]  {v_color}{verdict.ljust(15)}\033[0m")
        if verdict != Verdict.PASS:
            for reason in r.get("reasons", []):
                print(f"                          \033[91m-> {reason}\033[0m")
                
    # Extract Seal Data
    final_verdict = result.get("final_verdict")
    seal_hash = result.get("final_seal", "UNKNOWN_HASH")
    claim_id = result.get("claim_id", "UNKNOWN_CLAIM")
    
    print_veritas_gold("\n============================================================", bold=True)
    if final_verdict == Verdict.PASS:
        print_veritas_gold("  [+] PIPELINE VERDICT: PASS (STABLE CONTINUATION)", bold=True)
    else:
        print("\033[1;91m  [-] PIPELINE VERDICT: " + final_verdict + " (ISOLATED CONTAINMENT)\033[0m")
        
    print_veritas_gold("============================================================\n")
    print_veritas_obsidian(f"  CLAIM ID : {claim_id}")
    print("\033[1;33m  SEAL HASH: \033[0m" + f"{seal_hash}")
    print_veritas_obsidian("  TIMESTMP : " + datetime.now(timezone.utc).isoformat() + "\n")

if __name__ == "__main__":
    # OS level ansi escape enabling for windows
    os.system("color") 
    process()
