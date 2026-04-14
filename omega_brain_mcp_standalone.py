#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ── Venv auto-activation shim ──────────────────────────────────
# If running from system Python but uv installed deps into .venv,
# re-exec with the venv Python so imports resolve correctly.
import os as _os, sys as _sys
if not _sys.prefix != _sys.base_prefix:  # not already in a venv
    _venv_py = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".venv",
                             "Scripts" if _sys.platform == "win32" else "bin", "python")
    if _os.path.isfile(_venv_py):
        _os.execv(_venv_py, [_venv_py] + _sys.argv)
del _os, _sys
# ── End shim ───────────────────────────────────────────────────
"""
Omega Brain MCP + VERITAS Build Gates — Standalone Edition v2.1.0
==========================================
A fully self-contained MCP server with built-in:
  - Provenance layer (RAG, fragment ingestion, VERITAS scoring)
  - Vault (local SQLite: sessions, entries, FTS, tape/event-bus)
  - Cortex (Tri-Node approval gate + correction/steer mode)
  - S.E.A.L. ledger (tamper-proof hash chain)
  - Session handoff (SHA-256 sealed cross-session memory)
  - Smart context detection (CONTINUATION / CONTEXT_SWITCH / FRESH_START)

No external server required. One file, one dependency (mcp).

Install:
    pip install mcp

Optional (better embeddings):
    pip install sentence-transformers numpy

Run (add to mcp_config.json):
    {
      "mcpServers": {
        "omega-brain": {
          "command": "python",
          "args": ["path/to/omega_brain_mcp_standalone.py"],
          "env": { "PYTHONUTF8": "1" }
        }
      }
    }

Data stored at: ~/.omega-brain/  (configurable via OMEGA_BRAIN_DATA_DIR)
"""

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# VERITAS Omega Build Gates — deterministic gate pipeline
try:
    from veritas_build_gates import (
        run_pipeline, intake_gate, type_gate, dependency_gate,
        evidence_gate, math_gate, cost_gate, incentive_gate,
        security_gate, adversary_gate, trace_seal,
        compute_claim_id, compute_policy_hash,
        mis_greedy, quality as compute_quality, agreement as compute_agreement,
        Verdict, CLAEG, GATE_ORDER,
        resolve_thresholds, canonical_hash,
    )
    HAS_BUILD_GATES = True
except ImportError:
    HAS_BUILD_GATES = False

log = logging.getLogger("OmegaBrain.Standalone")

# ══════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════

DATA_DIR     = Path(os.environ.get("OMEGA_BRAIN_DATA_DIR",
                   str(Path.home() / ".omega-brain")))
DB_PATH      = DATA_DIR / "omega_brain.db"
HANDOFF_FILE = DATA_DIR / "handoff.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_SESSION_ID      = str(uuid.uuid4())
_CALL_COUNTER    = 0
_SERVER_START_TS = datetime.now(timezone.utc)

# Cortex thresholds (VERITAS Ω spec §14)
STEER_FLOOR   = 0.45   # below → hard block (NAEF invariant)
STEER_CEILING = 0.65   # above → pass as-is

# Context detection threshold — intentionally lower than STEER_FLOOR.
# Cortex guards *actions* (high-stakes, security boundary).
# Context detection classifies *intent* (more lenient — false negatives are low-cost).
CONTINUATION_THRESHOLD = 0.35

# ══════════════════════════════════════════════════════════════════
# EMBEDDING ENGINE  —  3-tier: sentence-transformers → fastembed (ONNX) → TF-IDF
# fastembed: pip install fastembed  (~7MB onnxruntime, downloads model on first use)
# This gives always-good embeddings with a single small dep and no GPU required.
# ══════════════════════════════════════════════════════════════════

_embed_model = None
_EMBED_ENGINE = "tfidf"   # updated in _init_embeddings

def _init_embeddings():
    global _embed_model, _EMBED_ENGINE
    # Tier 1: sentence-transformers (if already installed)
    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBED_ENGINE = "sentence-transformers"
        log.info("[omega-brain] Embeddings: sentence-transformers/all-MiniLM-L6-v2")
        return
    except Exception:
        pass
    # Tier 2: fastembed (ONNX — zero GPU, ~30MB model cached on first use)
    try:
        from fastembed import TextEmbedding
        _embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        _EMBED_ENGINE = "fastembed-onnx"
        log.info("[omega-brain] Embeddings: fastembed ONNX (BAAI/bge-small-en-v1.5)")
        return
    except Exception:
        pass
    # Tier 3: TF-IDF n-gram fallback (no deps, always works)
    _EMBED_ENGINE = "tfidf"
    log.info("[omega-brain] Embeddings: TF-IDF fallback — pip install fastembed for ONNX quality")

def _embed(text: str) -> list[float]:
    """Embed text to a dense vector. 3-tier: sentence-transformers, fastembed, TF-IDF."""
    if not text:
        return []
    if _EMBED_ENGINE == "sentence-transformers" and _embed_model:
        return _embed_model.encode(text, normalize_embeddings=True).tolist()
    if _EMBED_ENGINE == "fastembed-onnx" and _embed_model:
        return list(next(iter(_embed_model.embed([text]))))
    # TF-IDF n-gram fallback (128-dim)
    t = text.lower()
    ngrams: dict[str, int] = {}
    for n in (2, 3):
        for i in range(len(t) - n + 1):
            g = t[i:i+n]
            ngrams[g] = ngrams.get(g, 0) + 1
    keys = sorted(ngrams.keys())[:128]
    vec = [float(ngrams.get(k, 0)) for k in keys]
    norm = math.sqrt(sum(v*v for v in vec)) or 1.0
    return [v / norm for v in vec]

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    a, b = a[:min_len], b[:min_len]
    dot = sum(x*y for x,y in zip(a,b))
    na  = math.sqrt(sum(x*x for x in a)) or 1.0
    nb  = math.sqrt(sum(x*x for x in b)) or 1.0
    return max(-1.0, min(1.0, dot / (na * nb)))

_init_embeddings()

# ══════════════════════════════════════════════════════════════════
# DATABASE — SCHEMA + INIT
# ══════════════════════════════════════════════════════════════════

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _init_db():
    conn = _db()
    conn.executescript("""
        -- Vault: sessions
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            source TEXT DEFAULT 'antigravity',
            created_at TEXT,
            updated_at TEXT
        );
        -- Vault: entries (decisions, files, messages)
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            token_count INTEGER DEFAULT 0
        );
        -- Vault: event bus (tape)
        CREATE TABLE IF NOT EXISTS tape (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            payload TEXT,
            timestamp TEXT
        );
        -- Provenance: RAG fragments
        CREATE TABLE IF NOT EXISTS fragments (
            id TEXT PRIMARY KEY,
            content TEXT,
            source TEXT,
            tier TEXT DEFAULT 'B',
            embedding TEXT,
            ingested_at TEXT
        );
        -- S.E.A.L. ledger (hash chain)
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prev_hash TEXT,
            event_type TEXT,
            payload TEXT,
            hash TEXT UNIQUE,
            timestamp TEXT
        );
    """)
    # FTS5 for vault entries
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                content, session_id, tokenize='porter unicode61'
            )
        """)
    except Exception:
        pass
    conn.commit()
    conn.close()
    log.info(f"[omega-brain] DB initialized at {DB_PATH}")

_init_db()

# ══════════════════════════════════════════════════════════════════
# S.E.A.L. LEDGER
# ══════════════════════════════════════════════════════════════════

def _seal_event(event_type: str, payload: dict) -> str:
    """Append a sealed event to the ledger. Returns the new hash."""
    conn = _db()
    last = conn.execute(
        "SELECT hash FROM ledger ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = last["hash"] if last else ("GENESIS:" + _SESSION_ID)
    now = datetime.now(timezone.utc).isoformat()
    payload_str = json.dumps(payload, sort_keys=True)
    new_hash = hashlib.sha3_256(
        (prev_hash + event_type + payload_str + now).encode()
    ).hexdigest()
    conn.execute(
        "INSERT INTO ledger (prev_hash, event_type, payload, hash, timestamp) VALUES (?,?,?,?,?)",
        (prev_hash, event_type, payload_str, new_hash, now)
    )
    conn.commit()
    conn.close()
    return new_hash

def _seal_run(context: dict, response: str) -> dict:
    """S.E.A.L. trace for an agentic run."""
    h = _seal_event("agentic_run", {"context": context, "response": response[:500]})
    return {"seal_hash": h, "session_id": _SESSION_ID, "timestamp": datetime.now(timezone.utc).isoformat()}

# ══════════════════════════════════════════════════════════════════
# VAULT
# ══════════════════════════════════════════════════════════════════

def _vault_log_session(session_id: str, task: str, decisions: list, files: list) -> dict:
    """Write a session record to the local vault."""
    sid = session_id or _SESSION_ID
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    conn.execute("""
        INSERT INTO sessions (id, title, summary, source, created_at, updated_at)
        VALUES (?, ?, ?, 'antigravity', ?, ?)
        ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, summary=excluded.summary
    """, (sid, task[:200], f"{len(decisions)} decisions | {len(files)} files", now, now))
    for d in decisions[:50]:
        conn.execute(
            "INSERT INTO entries (session_id, role, content, timestamp, token_count) VALUES (?,?,?,?,?)",
            (sid, "assistant", str(d)[:2000], now, len(str(d)))
        )
        try:
            conn.execute("INSERT INTO entries_fts (content, session_id) VALUES (?,?)", (str(d)[:2000], sid))
        except Exception:
            pass
    if files:
        payload = f"Files modified: {json.dumps(files[:100])}"
        conn.execute(
            "INSERT INTO entries (session_id, role, content, timestamp, token_count) VALUES (?,?,?,?,?)",
            (sid, "system", payload, now, 0)
        )
    conn.execute(
        "INSERT INTO tape (event_type, payload, timestamp) VALUES (?,?,?)",
        ("antigravity_session", json.dumps({
            "session_id": sid, "task": task[:200],
            "decisions_count": len(decisions), "files_count": len(files)
        }), now)
    )
    conn.commit()
    conn.close()
    seal = _seal_event("vault_session", {"session_id": sid, "task": task[:100]})
    return {"logged": True, "session_id": sid, "seal_hash": seal[:16]}

def _vault_search(query: str) -> dict:
    """FTS keyword search over vault entries."""
    if not query:
        return {"results": [], "count": 0}
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT content, session_id as title FROM entries_fts WHERE entries_fts MATCH ? LIMIT 20",
            (query,)
        ).fetchall()
        conn.close()
        return {"query": query, "results": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        return {"query": query, "results": [], "count": 0, "error": str(e)}

def _vault_autoseal(session_id: str = "", hint_task: str = "") -> dict:
    """Auto-generate session summary from vault tape. No user input required."""
    conn = _db()
    tape_rows = conn.execute(
        "SELECT payload, timestamp FROM tape WHERE event_type='antigravity_session' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    entry_rows = []
    sid = session_id or _SESSION_ID
    entry_rows = conn.execute(
        "SELECT role, content FROM entries WHERE session_id=? ORDER BY id DESC LIMIT 20",
        (sid,)
    ).fetchall()
    conn.close()

    tape_sessions = []
    for row in tape_rows:
        try:
            tape_sessions.append(json.loads(row["payload"]))
        except Exception:
            pass

    task = hint_task or (tape_sessions[0].get("task", "session") if tape_sessions else "session")
    decisions, files = [], []
    for row in entry_rows:
        if row["role"] == "assistant" and row["content"]:
            decisions.append(row["content"][:200])
        elif row["role"] == "system" and "Files modified:" in (row["content"] or ""):
            try:
                files = json.loads(row["content"].replace("Files modified: ", ""))[:20]
            except Exception:
                pass

    parts = []
    for s in tape_sessions[:3]:
        t = s.get("task", "")
        if t:
            parts.append(f"{t} ({s.get('decisions_count',0)} decisions)")
    summary = "Session work: " + " | ".join(parts) if parts else task

    return {
        "task": task, "summary": summary,
        "decisions": decisions[:20], "files_modified": files,
        "auto_generated": True, "source_tape_entries": len(tape_sessions),
    }

# ══════════════════════════════════════════════════════════════════
# PROVENANCE / RAG
# ══════════════════════════════════════════════════════════════════

def _ingest_fragment(content: str, source: str = "user", tier: str = "B") -> str:
    """Add a text fragment to the RAG provenance store."""
    fid = hashlib.sha256(content.encode()).hexdigest()[:32]
    vec = _embed(content)
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    conn.execute("""
        INSERT OR IGNORE INTO fragments (id, content, source, tier, embedding, ingested_at)
        VALUES (?,?,?,?,?,?)
    """, (fid, content[:4000], source, tier, json.dumps(vec), now))
    conn.commit()
    conn.close()
    return fid

def _rag_search(query: str, top_k: int = 5) -> dict:
    """Semantic search over stored RAG fragments. Returns top-k with VERITAS score."""
    q_vec = _embed(query)
    conn = _db()
    rows = conn.execute("SELECT id, content, source, tier, embedding FROM fragments").fetchall()
    conn.close()

    results = []
    for row in rows:
        try:
            fv = json.loads(row["embedding"] or "[]")
            sim = _cosine(q_vec, fv)
            results.append({
                "id": row["id"],
                "content": row["content"][:500],
                "source": row["source"],
                "tier": row["tier"],
                "score": round(sim, 4),
            })
        except Exception:
            pass

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:top_k]

    # VERITAS scoring
    tier_map = {"A": 1.0, "B": 0.85, "C": 0.70, "D": 0.55}
    quality = (sum(tier_map.get(r["tier"], 0.5) for r in top) / len(top)) if top else 0.0
    sources = set(r["source"] for r in top)
    indep = 1.0 if len(sources) >= 2 else 0.7
    scores = [r["score"] for r in top if r["score"] > 0]
    spread = (max(scores) - min(scores)) if len(scores) >= 2 else 0.0
    agreement = max(0.0, 1.0 - spread)
    veritas_score = round(min(1.0, max(0.0, agreement * quality * indep)), 4)

    return {
        "query": query,
        "fragments": top,
        "veritas_score": veritas_score,
        "fragment_count": len(top),
        "total_indexed": len(rows),
        "session_id": _SESSION_ID,
    }

def _brain_preload(task: str) -> dict:
    """Full brain preload: RAG + handoff + vault context bundled with integrity hash."""
    rag = _rag_search(task, top_k=5)
    vault_recent = []
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT title, summary, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        conn.close()
        vault_recent = [dict(r) for r in rows]
    except Exception:
        pass

    handoff = _read_handoff()
    bundle = {
        "task": task,
        "rag_fragments": rag.get("fragments", []),
        "veritas_score": rag.get("veritas_score", 0.0),
        "vault_recent": vault_recent,
        "last_session_handoff": handoff or {},
        "handoff_present": bool(handoff),
        "session_id": _SESSION_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    bundle_str = json.dumps({k: v for k, v in bundle.items() if k != "preload_hash"}, sort_keys=True)
    bundle["preload_hash"] = hashlib.sha256(bundle_str.encode()).hexdigest()[:32]
    return bundle

# ══════════════════════════════════════════════════════════════════
# CORTEX — TRI-NODE APPROVAL + STEER
# ══════════════════════════════════════════════════════════════════

def _cortex_similarity(baseline: str, action: str) -> float:
    bv = _embed(baseline)
    av = _embed(action)
    return _cosine(bv, av)

def _cortex_check(tool: str, args: dict, baseline_prompt: str) -> dict:
    """Tri-Node approval gate."""
    if not tool or not baseline_prompt:
        return {"approved": False, "reason": "MISSING_PARAMS"}
    action_text = f"Tool: {tool} | Args: {json.dumps(args)}"
    sim = _cortex_similarity(baseline_prompt, action_text)
    approved = sim >= STEER_FLOOR
    _seal_event("cortex_check", {"tool": tool, "similarity": round(sim, 4), "approved": approved})
    return {
        "approved": approved,
        "similarity": round(sim, 4),
        "session_id": _SESSION_ID,
        "reason": "APPROVED" if approved else f"NAEF_VIOLATION: similarity {sim:.3f} below floor {STEER_FLOOR}",
    }

def _cortex_steer(tool: str, args: dict, baseline_prompt: str) -> dict:
    """Cortex correction mode: steer instead of just blocking."""
    if not tool or not baseline_prompt:
        return {"approved": False, "correction_applied": False, "reason": "MISSING_PARAMS"}
    action_text = f"Tool: {tool} | Args: {json.dumps(args)}"
    sim = _cortex_similarity(baseline_prompt, action_text)

    if sim < STEER_FLOOR:
        _seal_event("cortex_steer_block", {"tool": tool, "similarity": round(sim, 4)})
        return {
            "approved": False, "correction_applied": False,
            "similarity": round(sim, 4),
            "reason": f"NAEF_VIOLATION: {sim:.3f} below floor {STEER_FLOOR}. Unconditional block.",
        }

    if sim < STEER_CEILING:
        steered_args, corrections = {}, []
        for k, v in args.items():
            if isinstance(v, str) and (v.startswith("/") or v.startswith("C:\\") or len(v) > 500):
                steered_args[k] = v[:200] + "...[steered]"
                corrections.append(k)
            else:
                steered_args[k] = v
        _seal_event("cortex_steer_corrected", {"tool": tool, "similarity": round(sim, 4), "corrections": corrections})
        return {
            "approved": True, "correction_applied": True,
            "similarity": round(sim, 4), "steered_args": steered_args,
            "corrections": corrections,
            "reason": f"STEER_APPLIED: {len(corrections)} arg(s) corrected.",
        }

    return {"approved": True, "correction_applied": False, "similarity": round(sim, 4), "steered_args": args}

# ══════════════════════════════════════════════════════════════════
# HANDOFF — SHA-256 SEALED CROSS-SESSION MEMORY
# ══════════════════════════════════════════════════════════════════

def _write_handoff(task: str, summary: str, decisions: list,
                   files: list, next_steps: list, conversation_id: str) -> dict:
    record = {
        "conversation_id": conversation_id or _SESSION_ID,
        "task": task[:500],
        "summary": summary[:2000],
        "decisions": decisions[:50],
        "files_modified": files[:100],
        "next_steps": next_steps[:20],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mcp_session_id": _SESSION_ID,
    }
    content = json.dumps(record, sort_keys=True)
    record["seal"] = hashlib.sha256(content.encode()).hexdigest()
    HANDOFF_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    _seal_event("handoff_written", {"task": task[:100]})
    log.info(f"[omega-brain] Handoff sealed → {HANDOFF_FILE}")
    return record

def _read_handoff() -> Optional[dict]:
    if not HANDOFF_FILE.exists():
        return None
    try:
        raw = json.loads(HANDOFF_FILE.read_text(encoding="utf-8"))
        seal = raw.pop("seal", None)
        expected = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        if seal != expected:
            log.warning("[omega-brain] Handoff seal mismatch — ignoring")
            return None
        raw["seal"] = seal
        raw["seal_verified"] = True
        return raw
    except Exception as e:
        log.warning(f"[omega-brain] Handoff read error: {e}")
        return None

# ── Startup preload (auto-fired at import) ──────────────────────
_STARTUP_PRELOAD: dict = {}

def _run_startup_preload():
    global _STARTUP_PRELOAD
    handoff = _read_handoff()
    preload = _brain_preload("general workspace context and recent decisions")
    if handoff:
        preload["last_session_handoff"] = handoff
        preload["handoff_present"] = True
        log.info(f"[omega-brain] Handoff loaded: {handoff.get('task','')[:60]}")
    else:
        preload["handoff_present"] = False
    _STARTUP_PRELOAD = preload

try:
    _run_startup_preload()
except Exception as _e:
    _STARTUP_PRELOAD = {"status": "PRELOAD_ERROR", "error": str(_e)}
    log.warning(f"[omega-brain] Startup preload error (non-fatal): {_e}")

# ══════════════════════════════════════════════════════════════════
# CONTEXT MODE DETECTION
# ══════════════════════════════════════════════════════════════════

def _detect_context_mode(task: str, handoff: dict) -> tuple[str, float]:
    """
    Returns (mode, overlap_score).
    CONTINUATION   >= 0.35 keyword overlap with last session
    CONTEXT_SWITCH  > 0.0  but < 0.35
    FRESH_START     0.0    or no handoff
    """
    if not handoff:
        return "FRESH_START", 0.0
    handoff_task = handoff.get("task", "")
    if not handoff_task:
        return "FRESH_START", 0.0
    a_words = set(w.lower() for w in task.split() if len(w) > 3)
    b_words = set(w.lower() for w in handoff_task.split() if len(w) > 3)
    if not a_words or not b_words:
        return "FRESH_START", 0.0
    overlap = len(a_words & b_words) / max(len(a_words), len(b_words))
    if overlap >= CONTINUATION_THRESHOLD:
        return "CONTINUATION", overlap
    elif overlap > 0.0:
        return "CONTEXT_SWITCH", overlap
    return "FRESH_START", 0.0

# ══════════════════════════════════════════════════════════════════
# VERITAS Ω BUILD GATE — MCP TOOL DEFINITIONS
# ══════════════════════════════════════════════════════════════════

def _veritas_build_tools():
    """Return MCP Tool definitions for the VERITAS Build gate pipeline."""
    from mcp.types import Tool
    CLAIM_SCHEMA = {
        "type": "object",
        "description": (
            "A VERITAS BuildClaim object containing all declared primitives, operators, "
            "regimes, boundaries, loss models, evidence items, cost vectors, and policy "
            "configuration needed for deterministic gate evaluation. "
            "All fields are optional for partial evaluation — only the fields relevant "
            "to the gate being invoked are required."
        ),
        "properties": {
            "project": {"type": "string", "description": "Unique project identifier, e.g. 'omega-brain-mcp'."},
            "version": {"type": "string", "description": "Semantic version string of the build being evaluated, e.g. '2.1.0'."},
            "commit": {"type": "string", "description": "Git commit SHA for reproducibility and audit trail."},
            "primitives": {
                "type": "array", "items": {"type": "object"},
                "description": "Declared typed variables with name, domain (Interval/EnumSet/FiniteSet), optional units, and description."
            },
            "operators": {
                "type": "array", "items": {"type": "object"},
                "description": "Declared operators with name, arity, input primitive names, output primitive name, and totality flag."
            },
            "regimes": {
                "type": "array", "items": {"type": "object"},
                "description": "Named operating regimes, each with a predicate ConstraintExpr over declared primitives."
            },
            "boundaries": {
                "type": "array", "items": {"type": "object"},
                "description": "Named boundary constraints (e.g. 'CAPEX_USD <= 100000') that the claim must satisfy."
            },
            "loss_models": {
                "type": "array", "items": {"type": "object"},
                "description": "Named loss functions as ArithmeticExpr over primitives, with optional upper bounds."
            },
            "evidence": {
                "type": "array", "items": {"type": "object"},
                "description": "Evidence items, each with id, variable, value (Numeric or Categorical), timestamp, method, provenance, and optional dependencies."
            },
            "cost": {
                "type": "object",
                "description": "CostVector with optional fields: compute_flops, memory_bytes, wall_clock_s, capital_usd, coordination_agents."
            },
            "cost_bounds": {
                "type": "object",
                "description": "Upper bounds for each cost component. Utilization = max(cost_i / bound_i). Values must be > 0."
            },
            "dependencies": {
                "type": "object",
                "description": "SBOM-style dependency manifest for supply-chain analysis: package names, versions, registries, and integrity hashes."
            },
            "security": {
                "type": "object",
                "description": "Security posture declaration: SAST results, secret scan findings, injection surfaces, auth boundaries, and TLS/crypto configuration."
            },
            "attack_suite": {
                "type": "object",
                "description": "AttackSuite with suite_id and list of Attack transforms (InflateBound, RemoveEvidence, PerturbParam, PerturbEvidence) for adversary gate."
            },
            "policy": {
                "type": "object",
                "description": "PolicyConfig overrides: hash_alg, solver_backend, timeouts, thresholds. Defaults to VERITAS Omega v1.3.1 canonical values if omitted."
            },
        },
    }
    return [
        # ── Individual Gates ──
        Tool(name="veritas_intake_gate",
             description=(
                 "VERITAS Gate 1/10: INTAKE. Parses and canonicalizes a BuildClaim, validates all required fields are present, "
                 "computes deterministic EvidenceIDs and ClaimID via SHA-256 hashing. "
                 "Use this gate first to validate claim structure before running downstream gates. "
                 "Returns PASS with claim_id and counts, or VIOLATION with reason code INTAKE_ID_MISMATCH if provided IDs conflict."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_type_gate",
             description=(
                 "VERITAS Gate 2/10: TYPE. Performs pure type-level verification on a BuildClaim. "
                 "Enforces unique primitive names, non-empty domains, correct operator arity and input/output resolution, "
                 "defined symbols in all expressions, and unit consistency between primitives and evidence. "
                 "Returns PASS (TYPE_OK) or VIOLATION with reason codes: TYPE_DUPLICATE_PRIMITIVE, TYPE_EMPTY_DOMAIN, "
                 "TYPE_OPERATOR_ARITY, UNDEFINED_SYMBOL, or UNIT_MISMATCH."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_dependency_gate",
             description=(
                 "VERITAS Gate 3/10: DEPENDENCY. Performs supply-chain security analysis on declared dependencies. "
                 "Runs SBOM scan, CVE vulnerability check, integrity hash verification, license compatibility analysis, "
                 "and dependency depth analysis. Supply chain is treated as a first-class attack surface. "
                 "Returns PASS, MODEL_BOUND, or VIOLATION with detailed findings per dependency."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_evidence_gate",
             description=(
                 "VERITAS Gate 4/10: EVIDENCE. Evaluates evidence sufficiency for all critical variables referenced "
                 "in regime/boundary/loss expressions. For each variable: builds an independence graph, runs MIS_GREEDY "
                 "to find the maximum independent set, then checks K_min (independent count), A_min (agreement), and "
                 "Q_min (quality) thresholds. All calculations are server-side — the AI does not guess scores. "
                 "Returns PASS (EVIDENCE_OK) or INCONCLUSIVE with reason codes: INSUFFICIENT_INDEPENDENCE, "
                 "LOW_AGREEMENT, or LOW_QUALITY."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA,
                 "regime": {
                     "type": "string",
                     "description": "Build regime that determines evidence threshold strictness. 'dev' uses baseline thresholds (K=2, A=0.80, Q=0.70), 'production' uses escalated irreversibility thresholds (K=3, A=0.90, Q=0.80).",
                     "default": "dev",
                     "enum": ["dev", "staging", "production"]
                 },
             }, "required": ["claim"]}),
        Tool(name="veritas_math_gate",
             description=(
                 "VERITAS Gate 5/10: MATH. Translates all boundary constraints and regime predicates into interval arithmetic "
                 "or SMT-LIB formulas, then feeds measured evidence values as variable bindings. Returns SAT (constraints are "
                 "satisfiable — PASS, MATH_OK), UNSAT (contradiction found — VIOLATION, UNSAT_CONSTRAINT), or TIMEOUT "
                 "(solver exceeded time limit — INCONCLUSIVE, DECIDABILITY_TIMEOUT). No narrative interpretation of results."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_cost_gate",
             description=(
                 "VERITAS Gate 6/10: COST. Computes resource utilization as max(cost_i / bound_i) across all declared cost "
                 "components with bounds. Utilization >= 0.95 (REDLINE_CRITICAL) returns MODEL_BOUND with code COST_REDLINING. "
                 "Utilization >= 0.80 (REDLINE_WARNING) emits a warning but still PASS. Missing bounds on declared costs "
                 "return INCONCLUSIVE with code UNDECLARED_COST_BOUND. If no cost vector is provided, returns PASS (COST_NOT_APPLICABLE)."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_incentive_gate",
             description=(
                 "VERITAS Gate 7/10: INCENTIVE. Detects evidence monoculture by computing source dominance for each critical "
                 "variable's independent set. Dominance = max_count_by_source_id / |independent_set|. "
                 "If dominance exceeds 0.50 (more than half of independent evidence from a single source), returns "
                 "MODEL_BOUND with code DOMINANCE_DETECTED. Otherwise returns PASS (INCENTIVE_OK)."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_security_gate",
             description=(
                 "VERITAS Gate 8/10: SECURITY. Evaluates security posture from SAST findings, secret detection scans, "
                 "injection surface analysis, authentication boundary verification, and TLS/crypto configuration. "
                 "Zero tolerance policy: any CRITICAL finding, exposed secret, or unguarded injection surface "
                 "results in VIOLATION. Returns PASS, MODEL_BOUND, or VIOLATION with detailed security findings."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_adversary_gate",
             description=(
                 "VERITAS Gate 9/10: ADVERSARY. Stress-tests the claim against an attack suite of transforms "
                 "(bound inflation, evidence removal, parameter perturbation, uncertainty widening). For each attack, "
                 "re-runs the full gate pipeline on the modified claim and checks if the verdict degrades. "
                 "Fragility = fraction of attacks that degrade the verdict. Fragility > 25% returns MODEL_BOUND "
                 "(ADVERSARY_FRAGILE). Any exploit that directly succeeds returns VIOLATION."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),

        # ── Full Pipeline ──
        Tool(name="veritas_run_pipeline",
             description=(
                 "Run the full VERITAS Omega 10-gate deterministic pipeline in order: "
                 "INTAKE -> TYPE -> DEPENDENCY -> EVIDENCE -> MATH -> COST -> INCENTIVE -> SECURITY -> ADVERSARY -> TRACE/SEAL. "
                 "Use this tool to evaluate a complete BuildClaim end-to-end. "
                 "Returns the final verdict (PASS, MODEL_BOUND, INCONCLUSIVE, or VIOLATION), all individual gate results "
                 "with reason codes, and a tamper-proof SHA-256 seal hash for audit trail. "
                 "When fail_fast is true (default), the pipeline halts immediately on the first VIOLATION, "
                 "skipping remaining gates. Set fail_fast to false to collect all gate verdicts regardless of failures."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA,
                 "fail_fast": {
                     "type": "boolean",
                     "default": True,
                     "description": "When true (default), halt the pipeline on the first VIOLATION verdict and skip remaining gates. Set to false to run all gates and collect every verdict."
                 },
             }, "required": ["claim"]}),

        # ── Evidence Utilities ──
        Tool(name="veritas_compute_quality",
             description=(
                 "Compute the VERITAS Quality(e) score for a single evidence item. "
                 "The score is calculated as clamp01(0.50 * provenance_score + 0.30 * uncertainty_score + 0.20 * method_score). "
                 "Provenance score maps tier A=1.0, B=0.85, C=0.70, D=0.55, E=0.40. "
                 "Method score considers protocol presence and repeatability. "
                 "Uncertainty score penalizes high uncertainty relative to the measurement magnitude. "
                 "Returns a float in [0.0, 1.0] where higher values indicate stronger evidence quality."
             ),
             inputSchema={"type": "object", "properties": {
                 "evidence_item": {
                     "type": "object",
                     "description": "A single VERITAS evidence item containing at minimum: provenance (with tier and source_id), method (with protocol and repeatable flag), value (with x, units, and optional uncertainty), and timestamp."
                 },
                 "policy_env": {
                     "type": "object",
                     "description": "Optional policy environment specification for environment-match scoring. Defaults to empty object if omitted.",
                     "default": {}
                 },
             }, "required": ["evidence_item"]}),
        Tool(name="veritas_mis_greedy",
             description=(
                 "Run the MIS_GREEDY (Maximum Independent Set, greedy approximation) algorithm on a set of evidence items. "
                 "Builds an independence graph where edges connect evidence items that share a source, chain, dependency, "
                 "or same-protocol-within-24-hours. Then greedily selects the largest independent set (no two items share an edge). "
                 "Returns the independent set, its count, total input count, and the pairwise agreement score. "
                 "Use this to verify evidence independence before submitting to the evidence gate."
             ),
             inputSchema={"type": "object", "properties": {
                 "evidence_items": {
                     "type": "array",
                     "items": {"type": "object"},
                     "description": "Array of VERITAS evidence items to analyze for independence. Each item should have id, variable, value, timestamp, method, provenance, and optional dependencies."
                 },
             }, "required": ["evidence_items"]}),

        # ── CLAEG ──
        Tool(name="veritas_claeg_resolve",
             description=(
                 "CLAEG (Constrained Language & Evaluation Grammar) verdict resolver. Maps a VERITAS pipeline verdict "
                 "to one of three terminal states: STABLE_CONTINUATION (PASS — system continues normally), "
                 "ISOLATED_CONTAINMENT (MODEL_BOUND/INCONCLUSIVE — system operates with constraints), or "
                 "TERMINAL_SHUTDOWN (VIOLATION — system must halt). No narrative framing is applied — "
                 "the mapping is deterministic and absorbing (TERMINAL_SHUTDOWN cannot be reversed)."
             ),
             inputSchema={"type": "object", "properties": {
                 "verdict": {
                     "type": "string",
                     "enum": ["PASS", "MODEL_BOUND", "INCONCLUSIVE", "VIOLATION"],
                     "description": "The VERITAS verdict to resolve into a CLAEG terminal state. Must be one of the four canonical verdict values."
                 },
             }, "required": ["verdict"]}),
        Tool(name="veritas_claeg_transition",
             description=(
                 "CLAEG state transition validator. Checks whether a transition from current_state to target_state "
                 "is permitted under the CLAEG state machine rules. The absence of an explicitly allowed transition "
                 "is treated as prohibition (closed-world assumption). "
                 "Returns an object with 'allowed' (boolean) and 'reason' (string). "
                 "Use this to validate system state changes before executing them."
             ),
             inputSchema={"type": "object", "properties": {
                 "current_state": {
                     "type": "string",
                     "description": "The current CLAEG state of the system, e.g. 'STABLE_CONTINUATION', 'ISOLATED_CONTAINMENT', or 'TERMINAL_SHUTDOWN'."
                 },
                 "target_state": {
                     "type": "string",
                     "description": "The desired target CLAEG state to transition to. The validator checks if this transition is permitted."
                 },
             }, "required": ["current_state", "target_state"]}),

        # ── NAFE Guardrails ──
        Tool(name="veritas_nafe_scan",
             description=(
                 "NAFE (Narrative & Agency Elimination Framework) scanner for post-incident analysis. "
                 "Scans the provided text for four categories of failure signatures that indicate narrative manipulation: "
                 "Narrative Rescue (justifying failures with stories), Moral Override (ethical arguments bypassing gates), "
                 "Authority Drift (appeals to authority or seniority), and Intent Inference (assuming good intentions instead of verifying). "
                 "Returns clean status (boolean), list of detected flags, and scan metadata. "
                 "Any detected NAFE violation is automatically sealed to the audit ledger."
             ),
             inputSchema={"type": "object", "properties": {
                 "text": {
                     "type": "string",
                     "description": "The text content to scan for NAFE failure signatures. Can be a commit message, PR description, incident report, or any narrative text that might attempt to bypass deterministic gate verdicts."
                 },
             }, "required": ["text"]}),
    ]


def _handle_veritas_tool(name: str, arguments: dict) -> Optional[str]:
    """Handle VERITAS Build gate tool calls. Returns JSON string or None if not a veritas tool."""
    if not HAS_BUILD_GATES:
        return json.dumps({"error": "VERITAS Build Gates not available. Check veritas_build_gates.py."})

    if name == "veritas_intake_gate":
        return json.dumps(intake_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_type_gate":
        return json.dumps(type_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_dependency_gate":
        return json.dumps(dependency_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_evidence_gate":
        regime = arguments.get("regime", "dev")
        return json.dumps(evidence_gate(arguments.get("claim", {}), regime), indent=2, default=str)

    if name == "veritas_math_gate":
        return json.dumps(math_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_cost_gate":
        return json.dumps(cost_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_incentive_gate":
        return json.dumps(incentive_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_security_gate":
        return json.dumps(security_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_adversary_gate":
        return json.dumps(adversary_gate(arguments.get("claim", {})), indent=2, default=str)

    if name == "veritas_run_pipeline":
        fail_fast = arguments.get("fail_fast", True)
        result = run_pipeline(arguments.get("claim", {}), fail_fast=fail_fast)
        # Auto-seal to SEAL ledger
        _seal_event("veritas_pipeline_run", {
            "claim_id": result.get("claim_id", "")[:32],
            "verdict": result.get("final_verdict", ""),
            "regime": result.get("regime", ""),
            "seal": result.get("final_seal", "")[:32],
        })
        return json.dumps(result, indent=2, default=str)

    if name == "veritas_compute_quality":
        q = compute_quality(arguments.get("evidence_item", {}), arguments.get("policy_env", {}))
        return json.dumps({"quality": round(q, 6)})

    if name == "veritas_mis_greedy":
        items = arguments.get("evidence_items", [])
        independent = mis_greedy(items)
        agr = compute_agreement(independent)
        return json.dumps({
            "independent_set": independent,
            "independent_count": len(independent),
            "total_items": len(items),
            "agreement": round(agr, 6),
        }, indent=2, default=str)

    if name == "veritas_claeg_resolve":
        verdict = arguments.get("verdict", "")
        state = CLAEG.resolve(verdict)
        return json.dumps({
            "verdict": verdict,
            "terminal_state": state,
            "invariant": "Human presence is a logged condition, not an authority.",
        })

    if name == "veritas_claeg_transition":
        current = arguments.get("current_state", "")
        target = arguments.get("target_state", "")
        result = CLAEG.validate_transition(current, target)
        return json.dumps(result)

    if name == "veritas_nafe_scan":
        text = arguments.get("text", "")
        result = CLAEG.check_narrative_injection(text)
        if not result["clean"]:
            _seal_event("nafe_violation", {"flags": result["flags"][:5]})
        return json.dumps(result, indent=2)

    return None


# ══════════════════════════════════════════════════════════════════
# MCP SERVER
# ══════════════════════════════════════════════════════════════════

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, Resource, Prompt, PromptMessage, PromptArgument
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    log.error("MCP SDK not installed. Run: pip install mcp")

if HAS_MCP:
    app = Server("omega-brain-standalone")

    # ── Tools ────────────────────────────────────────────────────

    @app.list_tools()
    async def list_tools():
        return [
            Tool(name="omega_preload_context",
                 description=(
                     "Load episodic task context at the start of a new task or conversation. "
                     "Retrieves relevant fragments from the provenance RAG store, recent vault sessions, "
                     "any sealed cross-session handoff, and computes a VERITAS continuity score. "
                     "Call this tool first when beginning work on a task to establish full situational awareness. "
                     "Returns a context briefing with RAG matches, vault history, handoff data, and session continuity classification "
                     "(CONTINUATION, CONTEXT_SWITCH, or FRESH_START)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "task": {
                         "type": "string",
                         "description": "A natural-language description of the task you are starting. This is used to query the RAG store for relevant prior knowledge and to classify context continuity."
                     }
                 }, "required": ["task"]}),
            Tool(name="omega_rag_query",
                 description=(
                     "Perform semantic search across the local provenance RAG store. "
                     "Returns ranked text fragments sorted by cosine similarity, each with a VERITAS quality score "
                     "based on provenance tier, method repeatability, and freshness. "
                     "Use this to find prior knowledge, decisions, or evidence fragments relevant to your current task."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "query": {
                         "type": "string",
                         "description": "Natural-language search query to match against stored knowledge fragments using semantic similarity."
                     },
                     "top_k": {
                         "type": "integer",
                         "default": 5,
                         "description": "Maximum number of ranked results to return. Higher values return more matches but may include lower-relevance fragments."
                     }
                 }, "required": ["query"]}),
            Tool(name="omega_ingest",
                 description=(
                     "Ingest a new text fragment into the provenance RAG store for future retrieval. "
                     "Use this to teach the brain new knowledge — decisions, findings, code patterns, or any information "
                     "that should persist across sessions. Each fragment is stored with provenance metadata (source and evidence tier) "
                     "and becomes searchable via omega_rag_query. "
                     "Returns the fragment ID and storage confirmation."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "content": {
                         "type": "string",
                         "description": "The text content to ingest into the RAG store. Can be any knowledge fragment: a decision rationale, code pattern, finding, or reference material."
                     },
                     "source": {
                         "type": "string",
                         "description": "Identifier for the origin of this knowledge, e.g. 'user-session', 'code-review', 'documentation'. Used for provenance tracking and dominance analysis."
                     },
                     "tier": {
                         "type": "string",
                         "description": "VERITAS evidence tier rating. A = highest confidence (verified, reproducible), B = high (reliable source), C = moderate (single source), D = low (unverified). Affects Quality(e) scoring.",
                         "default": "B",
                         "enum": ["A", "B", "C", "D"]
                     }
                 }, "required": ["content"]}),
            Tool(name="omega_vault_search",
                 description=(
                     "Perform full-text keyword search across the local vault database. "
                     "Unlike omega_rag_query (semantic similarity), this performs exact keyword matching against "
                     "session logs, entries, and stored data using SQLite FTS5. "
                     "Use this when you need precise keyword matches rather than semantic relevance. "
                     "Returns matching vault entries with timestamps and context."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "query": {
                         "type": "string",
                         "description": "Keyword search query for full-text search. Supports SQLite FTS5 syntax: AND, OR, NOT, phrase matching with double quotes."
                     }
                 }, "required": ["query"]}),
            Tool(name="omega_cortex_check",
                 description=(
                     "Tri-Node Cortex approval gate. Computes semantic similarity between a proposed tool invocation "
                     "and the declared task baseline to detect intent drift. Returns an approval decision (approved/blocked) "
                     "and the similarity score. Use this before high-impact or irreversible operations to verify alignment "
                     "with the current task. Similarity below 0.45 (STEER_FLOOR) results in a hard block per NAEF invariant."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "tool": {
                         "type": "string",
                         "description": "The name of the tool being checked for alignment, e.g. 'omega_ingest' or 'veritas_run_pipeline'."
                     },
                     "args": {
                         "type": "object",
                         "description": "The arguments that will be passed to the tool. These are serialized and compared against the baseline for drift detection."
                     },
                     "baseline_prompt": {
                         "type": "string",
                         "description": "The declared task baseline describing the intended operation. The Cortex measures semantic distance between this baseline and the tool+args to detect drift."
                     }
                 }, "required": ["tool", "args", "baseline_prompt"]}),
            Tool(name="omega_cortex_steer",
                 description=(
                     "Cortex correction mode for drifting tool arguments. When a tool invocation's similarity to the "
                     "task baseline falls in the steering range (0.45–0.65), this tool attempts to correct the arguments "
                     "back toward alignment rather than blocking outright. Below 0.45 similarity, a hard block is enforced "
                     "(NAEF invariant — no narrative override). Returns steered arguments, similarity score, and correction details."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "tool": {
                         "type": "string",
                         "description": "The name of the tool whose arguments need steering, e.g. 'omega_ingest' or 'omega_seal_run'."
                     },
                     "args": {
                         "type": "object",
                         "description": "The original tool arguments that may be drifting from the baseline. These will be corrected if within steering range."
                     },
                     "baseline_prompt": {
                         "type": "string",
                         "description": "The task baseline that defines the intended direction. Arguments are steered toward alignment with this baseline."
                     }
                 }, "required": ["tool", "args", "baseline_prompt"]}),
            Tool(name="omega_seal_run",
                 description=(
                     "Append a tamper-proof entry to the S.E.A.L. (Secure Evidence Audit Ledger) hash chain. "
                     "Each entry is linked to the previous via SHA-256, creating an immutable audit trail. "
                     "Use this to record significant events, decisions, or state changes that must be verifiable. "
                     "Returns the seal hash, chain position, and timestamp."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "context": {
                         "type": "object",
                         "description": "Structured metadata for the seal entry. Should contain key-value pairs describing the event being recorded, e.g. {'action': 'deploy', 'target': 'production', 'version': '2.1.0'}."
                     },
                     "response": {
                         "type": "string",
                         "description": "The response or outcome text to seal into the audit ledger. This becomes part of the immutable hash chain."
                     }
                 }, "required": ["context", "response"]}),
            Tool(name="omega_log_session",
                 description=(
                     "Write a complete session record to the local vault for cross-session persistence. "
                     "Records the task description, key decisions made, and files modified during the session. "
                     "This data is retrievable via omega_vault_search and omega_preload_context in future sessions. "
                     "Returns the stored session ID and write confirmation."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "session_id": {
                         "type": "string",
                         "description": "Optional unique identifier for this session. If omitted, the current server session ID is used."
                     },
                     "task": {
                         "type": "string",
                         "description": "Natural-language description of the task completed during this session."
                     },
                     "decisions": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "List of key decisions made during the session, e.g. ['Used setuptools over poetry', 'Pinned dependency to v3.2.1']."
                     },
                     "files_modified": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "List of file paths that were created or modified during the session, e.g. ['src/main.py', 'pyproject.toml']."
                     }
                 }, "required": ["task"]}),
            Tool(name="omega_write_handoff",
                 description=(
                     "Write a SHA-256 sealed cross-session handoff document. This handoff is automatically loaded "
                     "via omega://session/preload on the next server restart, providing seamless context continuity. "
                     "Use at the end of a session to preserve critical state for the next session. "
                     "Returns the handoff hash and file path."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "task": {
                         "type": "string",
                         "description": "The task that was being worked on, used as the handoff title."
                     },
                     "summary": {
                         "type": "string",
                         "description": "Concise summary of what was accomplished and the current state. This is the primary context the next session will receive."
                     },
                     "decisions": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Key architectural or implementation decisions that the next session should be aware of."
                     },
                     "files_modified": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Files that were changed during this session, so the next session knows what to review."
                     },
                     "next_steps": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Ordered list of recommended next actions for the continuation session."
                     },
                     "conversation_id": {
                         "type": "string",
                         "description": "Optional conversation identifier for cross-referencing with external conversation tracking systems."
                     }
                 }, "required": ["task", "summary"]}),
            Tool(name="omega_execute",
                 description=(
                     "Cortex-wrapped meta-execution tool. The recommended default execution path for all Omega Brain tool calls. "
                     "Pass any Omega Brain tool name and its arguments — the Cortex automatically checks alignment with "
                     "the task baseline, steers drifting arguments if needed, executes the tool, and logs the result to the "
                     "SEAL audit chain. This makes Cortex governance the default rather than an optional check. "
                     "Returns the execution result, Cortex verdict, and SEAL hash."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "tool": {
                         "type": "string",
                         "description": "The name of the Omega Brain tool to execute, e.g. 'omega_ingest', 'omega_rag_query', 'omega_seal_run'. Only Omega Brain tools can be dispatched through this wrapper."
                     },
                     "args": {
                         "type": "object",
                         "description": "The arguments to pass to the target tool. These may be steered by the Cortex if they drift from the baseline."
                     },
                     "baseline": {
                         "type": "string",
                         "description": "Task baseline description for the Cortex alignment check. The Cortex measures semantic distance between this baseline and the tool+args."
                     }
                 }, "required": ["tool", "args", "baseline"]}),
            Tool(name="omega_brain_report",
                 description=(
                     "Generate a human-readable session audit report. Displays the SEAL chain tail (recent audit entries), "
                     "VERITAS quality scores, Cortex verdicts (blocked, approved, or steered), vault statistics, "
                     "and session health metrics. Use this to make the trust and governance layer visible and inspectable. "
                     "Returns a formatted text report suitable for display or logging."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "lines": {
                         "type": "integer",
                         "description": "Number of recent SEAL ledger entries to include in the report. Higher values show more audit history.",
                         "default": 10
                     }
                 }}),
            Tool(name="omega_brain_status",
                 description=(
                     "Retrieve unified brain health metrics. Returns vault statistics (total sessions, entries, "
                     "database size), RAG fragment count, SEAL ledger entry count, current session ID, "
                     "server uptime, and call counter. Use this for a quick health check of the Omega Brain "
                     "subsystems without generating a full audit report."
                 ),
                 inputSchema={"type": "object", "properties": {}}),
        ] + (_veritas_build_tools() if HAS_BUILD_GATES else [])

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        global _CALL_COUNTER
        _CALL_COUNTER += 1
        arguments = arguments or {}
        try:
            if name == "omega_preload_context":
                result = _brain_preload(arguments.get("task", "general context"))
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "omega_rag_query":
                result = _rag_search(arguments["query"], int(arguments.get("top_k", 5)))
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "omega_ingest":
                fid = _ingest_fragment(
                    arguments["content"],
                    arguments.get("source", "user"),
                    arguments.get("tier", "B")
                )
                _seal_event("fragment_ingested", {"id": fid, "source": arguments.get("source", "user")})
                return [TextContent(type="text", text=json.dumps({"ingested": True, "fragment_id": fid}))]

            elif name == "omega_vault_search":
                return [TextContent(type="text", text=json.dumps(_vault_search(arguments["query"]), indent=2))]

            elif name == "omega_cortex_check":
                result = _cortex_check(arguments.get("tool",""), arguments.get("args",{}), arguments.get("baseline_prompt",""))
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "omega_cortex_steer":
                result = _cortex_steer(arguments.get("tool",""), arguments.get("args",{}), arguments.get("baseline_prompt",""))
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "omega_seal_run":
                result = _seal_run(arguments.get("context",{}), arguments.get("response",""))
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "omega_log_session":
                result = _vault_log_session(
                    arguments.get("session_id",""),
                    arguments.get("task",""),
                    arguments.get("decisions",[]),
                    arguments.get("files_modified",[])
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "omega_write_handoff":
                record = _write_handoff(
                    arguments.get("task",""),
                    arguments.get("summary",""),
                    arguments.get("decisions",[]),
                    arguments.get("files_modified",[]),
                    arguments.get("next_steps",[]),
                    arguments.get("conversation_id","")
                )
                _STARTUP_PRELOAD["last_session_handoff"] = record
                _STARTUP_PRELOAD["handoff_present"] = True
                return [TextContent(type="text", text=json.dumps({
                    "written": True, "path": str(HANDOFF_FILE),
                    "seal": record["seal"][:16] + "...",
                    "message": "Handoff sealed. Next session auto-loads this context.",
                }, indent=2))]

            elif name == "omega_execute":
                # Cortex-wrapped meta-tool: the default execution path
                target_tool = arguments.get("tool", "")
                target_args = arguments.get("args", {})
                baseline    = arguments.get("baseline", "")

                if not target_tool:
                    return [TextContent(type="text", text=json.dumps({"error": "tool is required"}))]

                # 1. Cortex check
                steer_result = _cortex_steer(target_tool, target_args, baseline)
                if not steer_result.get("approved"):
                    return [TextContent(type="text", text=json.dumps({
                        "executed": False,
                        "cortex": steer_result,
                        "reason": steer_result.get("reason", "BLOCKED"),
                    }, indent=2))]

                # 2. Use steered args if corrections applied
                exec_args = steer_result.get("steered_args", target_args)

                # 3. Dispatch to internal tool (Omega Brain tools only)
                _INTERNAL_DISPATCH = {
                    "omega_preload_context": lambda a: json.dumps(_brain_preload(a.get("task","general")), indent=2),
                    "omega_rag_query":       lambda a: json.dumps(_rag_search(a["query"], int(a.get("top_k",5))), indent=2),
                    "omega_vault_search":    lambda a: json.dumps(_vault_search(a["query"]), indent=2),
                    "omega_ingest":          lambda a: json.dumps({"ingested": True, "id": _ingest_fragment(a["content"], a.get("source","user"), a.get("tier","B"))}),
                    "omega_log_session":     lambda a: json.dumps(_vault_log_session(a.get("session_id",""), a.get("task",""), a.get("decisions",[]), a.get("files_modified",[])), indent=2),
                    "omega_cortex_check":    lambda a: json.dumps(_cortex_check(a.get("tool",""), a.get("args",{}), a.get("baseline_prompt","")), indent=2),
                    "omega_brain_status":    lambda a: "{}",
                }
                # Add VERITAS tools to internal dispatch if available
                if HAS_BUILD_GATES:
                    _INTERNAL_DISPATCH.update({
                        k: (lambda n: lambda a: _handle_veritas_tool(n, a) or "{}")(k)
                        for k in [
                            "veritas_intake_gate", "veritas_type_gate", "veritas_dependency_gate",
                            "veritas_evidence_gate", "veritas_math_gate", "veritas_cost_gate",
                            "veritas_incentive_gate", "veritas_security_gate", "veritas_adversary_gate",
                            "veritas_run_pipeline", "veritas_compute_quality", "veritas_mis_greedy",
                            "veritas_claeg_resolve", "veritas_claeg_transition", "veritas_nafe_scan",
                        ]
                    })
                if target_tool not in _INTERNAL_DISPATCH:
                    return [TextContent(type="text", text=json.dumps({
                        "executed": False,
                        "cortex": steer_result,
                        "reason": f"omega_execute only wraps Omega Brain tools. '{target_tool}' is external \u2014 use the steered_args to call it yourself.",
                        "steered_args": exec_args,
                    }, indent=2))]

                tool_output = _INTERNAL_DISPATCH[target_tool](exec_args)

                # 4. Auto-SEAL every execution
                seal_h = _seal_event("omega_execute", {
                    "tool": target_tool,
                    "cortex_similarity": steer_result.get("similarity"),
                    "correction_applied": steer_result.get("correction_applied", False),
                })

                return [TextContent(type="text", text=json.dumps({
                    "executed": True,
                    "tool": target_tool,
                    "cortex": {
                        "approved": True,
                        "similarity": steer_result.get("similarity"),
                        "correction_applied": steer_result.get("correction_applied", False),
                        "corrections": steer_result.get("corrections", []),
                    },
                    "seal_hash": seal_h[:16] + "...",
                    "result": json.loads(tool_output),
                }, indent=2))]

            elif name == "omega_brain_report":
                n = int(arguments.get("lines", 10))
                conn = _db()

                # SEAL chain tail
                ledger_rows = conn.execute(
                    "SELECT event_type, hash, timestamp FROM ledger ORDER BY id DESC LIMIT ?", (n,)
                ).fetchall()

                # Cortex verdict breakdown
                blocked  = conn.execute("SELECT COUNT(*) FROM ledger WHERE event_type='cortex_steer_block'").fetchone()[0]
                steered  = conn.execute("SELECT COUNT(*) FROM ledger WHERE event_type='cortex_steer_corrected'").fetchone()[0]
                approved = conn.execute("SELECT COUNT(*) FROM ledger WHERE event_type='cortex_check' OR event_type='omega_execute'").fetchone()[0]

                # VERITAS: last few RAG queries from tape
                rag_scores = []
                tape_rows = conn.execute(
                    "SELECT payload FROM tape ORDER BY id DESC LIMIT 20"
                ).fetchall()
                for row in tape_rows:
                    try:
                        p = json.loads(row["payload"])
                        if "veritas_score" in p:
                            rag_scores.append(float(p["veritas_score"]))
                    except Exception:
                        pass

                # Vault stats
                sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                entries  = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                frags    = conn.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
                ledger_total = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
                conn.close()

                avg_veritas = round(sum(rag_scores)/len(rag_scores), 4) if rag_scores else None
                seal_tail = "\n".join(
                    f"  {r['timestamp'][:19]}  {r['event_type']:<30} {r['hash'][:16]}..."
                    for r in reversed(ledger_rows)
                ) or "  (no entries yet)"

                report = (
                    f"═══════════════════════════════════════════════════\n"
                    f"  OMEGA BRAIN AUDIT REPORT\n"
                    f"  Session: {_SESSION_ID[:16]}...   Engine: {_EMBED_ENGINE}\n"
                    f"  Generated: {datetime.now(timezone.utc).isoformat()[:19]}Z\n"
                    f"═══════════════════════════════════════════════════\n\n"
                    f"CORTEX VERDICTS (all time)\n"
                    f"  Blocked  : {blocked}\n"
                    f"  Steered  : {steered}\n"
                    f"  Approved : {approved}\n\n"
                    f"VERITAS\n"
                    f"  Avg score (last {len(rag_scores)} queries): {avg_veritas if avg_veritas is not None else 'n/a'}\n\n"
                    f"VAULT\n"
                    f"  Sessions: {sessions}  Entries: {entries}  Fragments: {frags}\n"
                    f"  Total SEAL entries: {ledger_total}\n\n"
                    f"SEAL CHAIN TAIL (last {n})\n"
                    f"  {'TIMESTAMP':<20} {'EVENT':<30} HASH\n"
                    f"{seal_tail}\n\n"
                    f"HANDOFF: {'PRESENT ' + chr(0x2713) if _STARTUP_PRELOAD.get('handoff_present') else 'not found'}\n"
                    f"═══════════════════════════════════════════════════"
                )
                return [TextContent(type="text", text=report)]

            elif name == "omega_brain_status":
                conn = _db()
                session_count  = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                entry_count    = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
                fragment_count = conn.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
                ledger_count   = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
                tape_count     = conn.execute("SELECT COUNT(*) FROM tape").fetchone()[0]
                conn.close()
                # Session age + break recommendation
                session_age_min = int(
                    (datetime.now(timezone.utc) - _SERVER_START_TS).total_seconds() / 60
                )
                break_recommended = session_age_min >= 90 or _CALL_COUNTER >= 60
                if session_age_min >= 90:
                    break_reason = (f"Session is {session_age_min} min old — quota pressure likely. "
                                    f"Call omega_seal_task then start a new conversation.")
                elif _CALL_COUNTER >= 60:
                    break_reason = (f"{_CALL_COUNTER} tool calls this session — context growing. "
                                    f"Call omega_seal_task then start a new conversation.")
                else:
                    break_reason = ""
                return [TextContent(type="text", text=json.dumps({
                    "status": "ONLINE", "mode": "STANDALONE",
                    "session_id": _SESSION_ID, "call_counter": _CALL_COUNTER,
                    "session_age_minutes":  session_age_min,
                    "break_recommended":    break_recommended,
                    "break_reason":         break_reason,
                    "break_action":         "Call omega_seal_task then open a new conversation" if break_recommended else "",
                    "data_dir": str(DATA_DIR),
                    "embedding_engine": _EMBED_ENGINE,
                    "db_stats": {
                        "sessions": session_count, "entries": entry_count,
                        "fragments": fragment_count, "ledger_entries": ledger_count,
                        "tape_events": tape_count,
                    },
                    "handoff_present": _STARTUP_PRELOAD.get("handoff_present", False),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, indent=2))]

            # VERITAS Build Gate tools
            if name.startswith("veritas_"):
                vr = _handle_veritas_tool(name, arguments)
                if vr is not None:
                    return [TextContent(type="text", text=vr)]

            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


        except Exception as e:
            log.error(f"Tool {name} error: {e}")
            return [TextContent(type="text", text=json.dumps({
                "error": str(e), "tool": name, "veritas_code": "TOOL_ERROR"
            }))]

    # ── Resources ────────────────────────────────────────────────

    @app.list_resources()
    async def list_resources():
        return [
            Resource(uri="omega://session/preload", name="Omega Startup Brain Preload",
                     description="Auto-fetched at startup: RAG + handoff + vault. Zero manual calls needed.",
                     mimeType="application/json"),
            Resource(uri="omega://session/handoff", name="Last Session Handoff",
                     description="SHA-256 verified cross-session handoff file.",
                     mimeType="application/json"),
            Resource(uri="omega://session/current", name="Current MCP Session",
                     description="Session ID and call count.",
                     mimeType="application/json"),
            Resource(uri="omega://brain/status", name="Omega Brain Status",
                     description="DB stats, embedding engine, ledger count.",
                     mimeType="application/json"),
            Resource(uri="veritas://spec/v1.0.0", name="VERITAS Omega Build Spec v1.0.0",
                     description="Canonical specification: invariants, thresholds, gate order, type system. Read-only source of truth.",
                     mimeType="application/json"),
            Resource(uri="veritas://claeg/grammar", name="CLAEG Grammar",
                     description="Constraint-Locked Alignment Evaluation Grammar: terminal states, allowed transitions, prohibitions.",
                     mimeType="application/json"),
            Resource(uri="veritas://gates/order", name="VERITAS Gate Order",
                     description="The 10-gate pipeline order: INTAKE->TYPE->DEPENDENCY->EVIDENCE->MATH->COST->INCENTIVE->SECURITY->ADVERSARY->TRACE/SEAL",
                     mimeType="application/json"),
            Resource(uri="veritas://thresholds/baseline", name="VERITAS Baseline Thresholds",
                     description="Numeric thresholds for dev/baseline regime.",
                     mimeType="application/json"),
            Resource(uri="veritas://thresholds/production", name="VERITAS Production Thresholds",
                     description="Escalated numeric thresholds for production/release regime.",
                     mimeType="application/json"),
        ]

    @app.read_resource()
    async def read_resource(uri: str) -> str:
        if uri == "omega://session/preload":
            return json.dumps(_STARTUP_PRELOAD, indent=2)
        elif uri == "omega://session/handoff":
            h = _read_handoff()
            return json.dumps(h if h else {"handoff_present": False})
        elif uri == "omega://session/current":
            return json.dumps({"session_id": _SESSION_ID, "call_counter": _CALL_COUNTER,
                                "data_dir": str(DATA_DIR)})
        elif uri == "omega://brain/status":
            conn = _db()
            fc = conn.execute("SELECT COUNT(*) FROM fragments").fetchone()[0]
            lc = conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0]
            conn.close()
            return json.dumps({"fragments": fc, "ledger_entries": lc, "mode": "STANDALONE"})
        if uri == "veritas://spec/v1.0.0":
            spec_path = Path(__file__).parent.parent / "VERITAS_OMEGA_BUILD_SPEC_v1_0_0.md"
            if spec_path.exists():
                return spec_path.read_text(encoding="utf-8")
            return json.dumps({"error": "Spec file not found", "searched": str(spec_path)})
        elif uri == "veritas://claeg/grammar":
            if HAS_BUILD_GATES:
                return json.dumps({
                    "terminal_states": list(CLAEG.TERMINAL_STATES),
                    "transitions": {k: list(v) for k, v in CLAEG.TRANSITIONS.items()},
                    "invariants": [
                        "Undeclared assumptions terminate evaluation.",
                        "Absence of an allowed transition is treated as prohibition.",
                        "Human presence is a logged condition, not an authority.",
                        "Policy invariants are binding and non-discretionary.",
                    ],
                    "prohibited_inferences": [
                        "Intent inference",
                        "Motive attribution",
                        "Preference assumption",
                    ],
                }, indent=2)
            return json.dumps({"error": "Build gates not loaded"})
        elif uri == "veritas://gates/order":
            if HAS_BUILD_GATES:
                return json.dumps({"gate_order": GATE_ORDER, "count": len(GATE_ORDER)})
            return json.dumps({"gate_order": [
                "INTAKE","TYPE","DEPENDENCY","EVIDENCE","MATH",
                "COST","INCENTIVE","SECURITY","ADVERSARY","TRACE_SEAL"
            ]})
        elif uri == "veritas://thresholds/baseline":
            if HAS_BUILD_GATES:
                return json.dumps(resolve_thresholds("dev"), indent=2)
            return json.dumps({"error": "Build gates not loaded"})
        elif uri == "veritas://thresholds/production":
            if HAS_BUILD_GATES:
                return json.dumps(resolve_thresholds("production"), indent=2)
            return json.dumps({"error": "Build gates not loaded"})
        return json.dumps({"error": f"Unknown resource: {uri}"})

    # ── Prompts ──────────────────────────────────────────────────

    @app.list_prompts()
    async def list_prompts():
        return [
            Prompt(name="omega_task_start",
                   description="Brief Antigravity at task start. Detects CONTINUATION / CONTEXT_SWITCH / FRESH_START automatically.",
                   arguments=[PromptArgument(name="task", description="One line: what are you working on?", required=False)]),
            Prompt(name="omega_seal_task",
                   description=(
                       "ONE TAP end-of-session seal. Fully automatic: reads vault tape, "
                       "auto-generates summary, logs to vault, writes S.E.A.L. trace, writes handoff. "
                       "No fields required. Zero typing."
                   ),
                   arguments=[
                       PromptArgument(name="note", description="Optional one-line note appended to auto-summary", required=False)
                   ]),
            Prompt(name="omega_write_handoff",
                   description=(
                       "Structured handoff with explicit fields. Use when you want to be precise "
                       "about task, decisions, files, and next steps. The AI fills these in — you don't type them. "
                       "omega_seal_task is preferred for quick workflow; this is for detailed records."
                   ),
                   arguments=[
                       PromptArgument(name="task", description="What was being worked on", required=False),
                       PromptArgument(name="decisions", description="Key decisions made (comma-separated)", required=False),
                       PromptArgument(name="next_steps", description="What to do next session (comma-separated)", required=False),
                       PromptArgument(name="files", description="Files modified (comma-separated paths)", required=False),
                   ]),
        ]

    @app.get_prompt()
    async def get_prompt(name: str, arguments: dict) -> dict:
        arguments = arguments or {}

        if name == "omega_task_start":
            task = arguments.get("task", "").strip() or "general workspace context"
            preload = _brain_preload(task)
            handoff = preload.get("last_session_handoff", {})
            mode, overlap = _detect_context_mode(task, handoff)
            rag_count = len(preload.get("rag_fragments", []))
            veritas = preload.get("veritas_score", 0.0)

            if mode == "CONTINUATION":
                files_preview = ", ".join((handoff.get("files_modified") or [])[:4]) or "none"
                decisions_preview = "\n  ".join((handoff.get("decisions") or [])[:3]) or "none logged"
                next_preview = ", ".join((handoff.get("next_steps") or [])[:3]) or "not specified"
                briefing = (
                    f"▶ CONTINUING: {handoff.get('task','')}\n\n"
                    f"Summary: {handoff.get('summary','')[:400]}\n\n"
                    f"Files: {files_preview}\n"
                    f"Decisions:\n  {decisions_preview}\n"
                    f"Next steps: {next_preview}\n\n"
                    f"RAG: {rag_count} fragments | VERITAS {veritas:.2f}"
                )
            elif mode == "CONTEXT_SWITCH":
                briefing = (
                    f"◀ CONTEXT SWITCH → {task}\n\n"
                    f"Previous: {handoff.get('task','')}\n"
                    f"Summary: {handoff.get('summary','')[:200]}\n\n"
                    f"RAG: {rag_count} fragments | VERITAS {veritas:.2f}"
                )
            else:
                briefing = (
                    f"★ NEW: {task}\n\n"
                    f"No prior session for this context.\n"
                    f"RAG: {rag_count} fragments | VERITAS {veritas:.2f}"
                )

            return {"messages": [PromptMessage(role="user",
                content=TextContent(type="text", text=briefing))]}

        elif name == "omega_seal_task":
            # Fully automatic — hits autoseal, no user input needed
            note = arguments.get("note", "").strip()
            auto = _vault_autoseal(_SESSION_ID, note)
            task     = auto.get("task", note or "session")
            summary  = auto.get("summary", task)
            decisions = auto.get("decisions", [])
            files    = auto.get("files_modified", [])
            _vault_log_session(_SESSION_ID, task, decisions, files)
            _seal_run({"task": task, "session_id": _SESSION_ID}, summary)
            record = _write_handoff(task, summary, decisions, files, [], _SESSION_ID)
            _STARTUP_PRELOAD["last_session_handoff"] = record
            _STARTUP_PRELOAD["handoff_present"] = True
            files_short = (", ".join(files[:4]) + (" ..." if len(files) > 4 else "")) if files else "none"
            return {"messages": [PromptMessage(role="user", content=TextContent(type="text", text=(
                f"OMEGA SEALED ✓ (auto)\n"
                f"Task: {task[:80]}\nFiles: {files_short}\n"
                f"Seal: {record['seal'][:16]}...\n\n"
                f"Next session detects CONTINUATION / CONTEXT_SWITCH / FRESH_START automatically."
            )))]}

        elif name == "omega_write_handoff":
            # Structured mode — uses explicit fields provided by the AI
            task_arg = arguments.get("task", "").strip()
            decisions_raw = arguments.get("decisions", "")
            next_raw = arguments.get("next_steps", "")
            files_raw = arguments.get("files", "")
            decisions = [d.strip() for d in decisions_raw.split(",") if d.strip()] if isinstance(decisions_raw, str) else (decisions_raw or [])
            next_steps = [s.strip() for s in next_raw.split(",") if s.strip()] if next_raw else []
            files = [f.strip() for f in files_raw.split(",") if f.strip()] if files_raw else []
            # Fall back to autoseal for missing fields
            auto = _vault_autoseal(_SESSION_ID, task_arg)
            task = task_arg or auto.get("task", "session")
            summary = auto.get("summary", task)
            if not decisions:
                decisions = auto.get("decisions", [])
            if not files:
                files = auto.get("files_modified", [])
            _vault_log_session(_SESSION_ID, task, decisions, files)
            _seal_run({"task": task, "session_id": _SESSION_ID}, summary)
            record = _write_handoff(task, summary, decisions, files, next_steps, _SESSION_ID)
            _STARTUP_PRELOAD["last_session_handoff"] = record
            _STARTUP_PRELOAD["handoff_present"] = True
            return {"messages": [PromptMessage(role="user", content=TextContent(type="text", text=(
                f"OMEGA HANDOFF SEALED ✓ (structured)\n"
                f"Task: {task[:80]}\n"
                f"Decisions: {len(decisions)} | Files: {len(files)} | Next steps: {len(next_steps)}\n"
                f"Seal: {record['seal'][:16]}...\n\n"
                f"Next session detects CONTINUATION / CONTEXT_SWITCH / FRESH_START automatically."
            )))]}

        return {"messages": [{"role": "user", "content": {"type": "text", "text": f"Unknown prompt: {name}"}}]}


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════

async def run_sse(port: int):
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Route
    except ImportError:
        print("ERROR: SSE mode requires starlette and uvicorn. Run: pip install starlette uvicorn", file=sys.stderr)
        sys.exit(1)
        
    from mcp.server.sse import SseServerTransport

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ],
    )
    
    config = uvicorn.Config(starlette_app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    if not HAS_MCP:
        print("ERROR: pip install mcp", file=sys.stderr)
        sys.exit(1)
        
    import argparse
    parser = argparse.ArgumentParser(description="Omega Brain MCP Standalone")
    parser.add_argument("--sse", action="store_true", help="Run over SSE instead of stdio")
    parser.add_argument("--port", type=int, default=8055, help="Port for SSE server (default 8055)")
    args, unknown = parser.parse_known_args()

    log.info(f"[omega-brain] Standalone v2.1.0 + Build Gates | session={_SESSION_ID} | data={DATA_DIR}")
    
    if args.sse:
        log.info(f"[omega-brain] Starting SSE Server on port {args.port}")
        await run_sse(args.port)
    else:
        log.info("[omega-brain] Starting stdio server")
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

def cli():
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

if __name__ == "__main__":
    cli()
