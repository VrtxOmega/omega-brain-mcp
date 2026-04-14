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
Omega Brain MCP + VERITAS Build Gates — Standalone Edition v2.1.1
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
            "A VERITAS BuildClaim object for deterministic gate evaluation. "
            "All fields are optional for partial evaluation — only fields relevant to the invoked gate are required."
        ),
        "properties": {
            "project": {"type": "string", "description": "Project identifier, e.g. 'omega-brain-mcp'."},
            "version": {"type": "string", "description": "Semantic version, e.g. '2.1.0'."},
            "commit": {"type": "string", "description": "Git commit SHA for reproducibility."},
            "primitives": {
                "type": "array", "items": {"type": "object"},
                "description": "Typed variables with name, domain (Interval/EnumSet/FiniteSet), optional units."
            },
            "operators": {
                "type": "array", "items": {"type": "object"},
                "description": "Operators with name, arity, input/output primitive names, totality flag."
            },
            "regimes": {
                "type": "array", "items": {"type": "object"},
                "description": "Operating regimes with name and predicate ConstraintExpr."
            },
            "boundaries": {
                "type": "array", "items": {"type": "object"},
                "description": "Boundary constraints, e.g. {name: 'cap', constraint: 'CAPEX_USD <= 100000'}."
            },
            "loss_models": {
                "type": "array", "items": {"type": "object"},
                "description": "Loss functions as ArithmeticExpr with optional upper bounds."
            },
            "evidence": {
                "type": "array", "items": {"type": "object"},
                "description": "Evidence items with id, variable, value, timestamp, method, provenance."
            },
            "cost": {
                "type": "object",
                "description": "CostVector: compute_flops, memory_bytes, wall_clock_s, capital_usd, coordination_agents."
            },
            "cost_bounds": {
                "type": "object",
                "description": "Upper bounds for each cost component. All values must be > 0."
            },
            "dependencies": {
                "type": "object",
                "description": "SBOM-style dependency manifest: package names, versions, registries, hashes."
            },
            "security": {
                "type": "object",
                "description": "Security posture: SAST results, secret scan, injection surfaces, auth, TLS config."
            },
            "attack_suite": {
                "type": "object",
                "description": "Attack transforms for adversary testing: InflateBound, RemoveEvidence, PerturbParam, PerturbEvidence."
            },
            "policy": {
                "type": "object",
                "description": "PolicyConfig overrides for hash_alg, solver_backend, timeouts, thresholds."
            },
        },
    }
    return [
        # ── Individual Gates ──
        Tool(name="veritas_intake_gate",
             description=(
                 "Gate 1/10: Parses, canonicalizes, and validates a BuildClaim's structure and computes SHA-256 IDs. "
                 "Use this first to validate claim structure before running any downstream gates. "
                 "Returns JSON with fields: verdict (PASS | VIOLATION), claim_id (hex), primitive_count (int), evidence_count (int)."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_type_gate",
             description=(
                 "Gate 2/10: Enforces type-level correctness — unique primitives, non-empty domains, operator arity, symbol resolution, and unit consistency. "
                 "Use this after intake to catch structural errors before evidence evaluation. "
                 "Returns JSON with verdict (PASS | VIOLATION) and reason_code: TYPE_OK, TYPE_DUPLICATE_PRIMITIVE, TYPE_EMPTY_DOMAIN, TYPE_OPERATOR_ARITY, UNDEFINED_SYMBOL, or UNIT_MISMATCH."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_dependency_gate",
             description=(
                 "Gate 3/10: Analyzes supply-chain security via SBOM scan, CVE check, integrity verification, license compatibility, and dependency depth. "
                 "Use this to assess third-party dependency risk before deploying or releasing. "
                 "Returns JSON with verdict (PASS | MODEL_BOUND | VIOLATION) and per-dependency findings array."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_evidence_gate",
             description=(
                 "Gate 4/10: Evaluates evidence sufficiency for critical variables by computing independence (MIS_GREEDY), agreement, and quality scores. "
                 "Use this to verify that evidence meets K_min, A_min, Q_min thresholds; use veritas_compute_quality or veritas_mis_greedy for individual calculations. "
                 "Returns JSON with verdict (PASS | INCONCLUSIVE) and reason_code: EVIDENCE_OK, INSUFFICIENT_INDEPENDENCE, LOW_AGREEMENT, or LOW_QUALITY."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA,
                 "regime": {
                     "type": "string",
                     "description": "Threshold strictness: 'dev' (K=2, A=0.80, Q=0.70), 'staging' (same as dev), 'production' (K=3, A=0.90, Q=0.80).",
                     "default": "dev",
                     "enum": ["dev", "staging", "production"]
                 },
             }, "required": ["claim"]}),
        Tool(name="veritas_math_gate",
             description=(
                 "Gate 5/10: Translates boundary constraints into interval arithmetic or SMT formulas and checks satisfiability with evidence values. "
                 "Use this after evidence gate to verify that measured values satisfy all declared constraints. "
                 "Returns JSON with verdict (PASS | VIOLATION | INCONCLUSIVE) and reason_code: MATH_OK, UNSAT_CONSTRAINT, or DECIDABILITY_TIMEOUT."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_cost_gate",
             description=(
                 "Gate 6/10: Computes resource utilization as max(cost_i / bound_i) and checks against redline thresholds. "
                 "Use this to verify cost budgets are within limits; skipped automatically if no cost vector is declared. "
                 "Returns JSON with verdict (PASS | MODEL_BOUND | INCONCLUSIVE), utilization (float), and reason_code: COST_OK, COST_REDLINING, COST_NOT_APPLICABLE, or UNDECLARED_COST_BOUND."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_incentive_gate",
             description=(
                 "Gate 7/10: Detects evidence monoculture by measuring source dominance (max_count_from_single_source / independent_set_size). "
                 "Use this to guard against single-source bias in evidence; dominance > 0.50 triggers MODEL_BOUND. "
                 "Returns JSON with verdict (PASS | MODEL_BOUND), dominance (float), and reason_code: INCENTIVE_OK or DOMINANCE_DETECTED."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_security_gate",
             description=(
                 "Gate 8/10: Evaluates security posture from SAST, secret detection, injection surfaces, auth boundaries, and TLS config. "
                 "Use this to enforce zero-tolerance security policy — any CRITICAL finding or exposed secret causes VIOLATION. "
                 "Returns JSON with verdict (PASS | MODEL_BOUND | VIOLATION) and findings array with severity levels."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),
        Tool(name="veritas_adversary_gate",
             description=(
                 "Gate 9/10: Stress-tests the claim against attack transforms (bound inflation, evidence removal, parameter/evidence perturbation). "
                 "Use this as the final robustness check; fragility > 25% triggers MODEL_BOUND (ADVERSARY_FRAGILE). "
                 "Returns JSON with verdict (PASS | MODEL_BOUND), fragility (float), attacks_tested (int), attacks_degraded (int)."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA
             }, "required": ["claim"]}),

        # ── Full Pipeline ──
        Tool(name="veritas_run_pipeline",
             description=(
                 "Runs the full 10-gate VERITAS pipeline: INTAKE → TYPE → DEPENDENCY → EVIDENCE → MATH → COST → INCENTIVE → SECURITY → ADVERSARY → TRACE/SEAL. "
                 "Use this for complete end-to-end evaluation of a BuildClaim; use individual gates for targeted checks. "
                 "Returns JSON with fields: final_verdict (PASS | MODEL_BOUND | INCONCLUSIVE | VIOLATION), gate_results (array), reason_codes (array), seal_hash (hex string)."
             ),
             inputSchema={"type": "object", "properties": {
                 "claim": CLAIM_SCHEMA,
                 "fail_fast": {
                     "type": "boolean",
                     "default": True,
                     "description": "If true (default), halts on first VIOLATION. Set false to collect all gate verdicts."
                 },
             }, "required": ["claim"]}),

        # ── Evidence Utilities ──
        Tool(name="veritas_compute_quality",
             description=(
                 "Computes the VERITAS Quality(e) score for a single evidence item using: clamp01(0.50*provenance + 0.30*uncertainty + 0.20*method). "
                 "Use this to evaluate individual evidence quality before submitting to the evidence gate. "
                 "Returns JSON with fields: quality (float 0.0-1.0)."
             ),
             inputSchema={"type": "object", "properties": {
                 "evidence_item": {
                     "type": "object",
                     "description": "Evidence item with provenance (tier, source_id), method (protocol, repeatable), value (x, units, uncertainty), and timestamp."
                 },
                 "policy_env": {
                     "type": "object",
                     "description": "Optional policy environment for match scoring. Defaults to empty.",
                     "default": {}
                 },
             }, "required": ["evidence_item"]}),
        Tool(name="veritas_mis_greedy",
             description=(
                 "Runs the MIS_GREEDY algorithm to find the maximum independent set of evidence items with no shared source, chain, dependency, or same-protocol-within-24h. "
                 "Use this to check evidence independence before submitting to the evidence gate; use veritas_compute_quality for individual quality scores. "
                 "Returns JSON with fields: independent_set (array), independent_count (int), total_items (int), agreement (float 0.0-1.0)."
             ),
             inputSchema={"type": "object", "properties": {
                 "evidence_items": {
                     "type": "array",
                     "items": {"type": "object"},
                     "description": "Array of evidence items with id, variable, value, timestamp, method, provenance, and optional dependencies."
                 },
             }, "required": ["evidence_items"]}),

        # ── CLAEG ──
        Tool(name="veritas_claeg_resolve",
             description=(
                 "Maps a VERITAS verdict to a CLAEG terminal state: PASS→STABLE_CONTINUATION, MODEL_BOUND/INCONCLUSIVE→ISOLATED_CONTAINMENT, VIOLATION→TERMINAL_SHUTDOWN. "
                 "Use this after a pipeline run to determine the system's required operational state. "
                 "Returns JSON with fields: verdict (string), terminal_state (string), invariant (string)."
             ),
             inputSchema={"type": "object", "properties": {
                 "verdict": {
                     "type": "string",
                     "enum": ["PASS", "MODEL_BOUND", "INCONCLUSIVE", "VIOLATION"],
                     "description": "VERITAS verdict to resolve. Must be one of: PASS, MODEL_BOUND, INCONCLUSIVE, VIOLATION."
                 },
             }, "required": ["verdict"]}),
        Tool(name="veritas_claeg_transition",
             description=(
                 "Validates whether a CLAEG state transition is permitted under closed-world rules (absence of explicit permission = prohibition). "
                 "Use this before changing system operational state; TERMINAL_SHUTDOWN is absorbing (no outbound transitions). "
                 "Returns JSON with fields: allowed (boolean), reason (string)."
             ),
             inputSchema={"type": "object", "properties": {
                 "current_state": {
                     "type": "string",
                     "enum": ["STABLE_CONTINUATION", "ISOLATED_CONTAINMENT", "TERMINAL_SHUTDOWN"],
                     "description": "Current CLAEG state of the system."
                 },
                 "target_state": {
                     "type": "string",
                     "enum": ["STABLE_CONTINUATION", "ISOLATED_CONTAINMENT", "TERMINAL_SHUTDOWN"],
                     "description": "Desired target CLAEG state to transition to."
                 },
             }, "required": ["current_state", "target_state"]}),

        # ── NAFE Guardrails ──
        Tool(name="veritas_nafe_scan",
             description=(
                 "Scans text for NAFE failure signatures: Narrative Rescue, Moral Override, Authority Drift, and Intent Inference. "
                 "Use this on commit messages, PR descriptions, or incident reports to detect narrative bypasses of deterministic gates. "
                 "Returns JSON with fields: clean (boolean), flags (array of detected signatures), scan_metadata (object). Violations auto-seal to the audit ledger."
             ),
             inputSchema={"type": "object", "properties": {
                 "text": {
                     "type": "string",
                     "description": "Text to scan for narrative failure signatures, e.g. a commit message or incident report."
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
                     "Loads episodic context for a new task by querying the RAG store, vault history, and any sealed handoff. "
                     "Call this once at the start of every new task before doing any work. "
                     "Returns JSON with fields: rag_matches, vault_history, handoff, continuity_type (CONTINUATION | CONTEXT_SWITCH | FRESH_START)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "task": {
                         "type": "string",
                         "description": "Natural-language description of the task to load context for, e.g. 'Fix authentication bug in login module'."
                     }
                 }, "required": ["task"]}),
            Tool(name="omega_rag_query",
                 description=(
                     "Searches the provenance RAG store using semantic similarity and returns ranked text fragments. "
                     "Use this for meaning-based search; use omega_vault_search instead for exact keyword matching. "
                     "Returns JSON array of {fragment, similarity_score, quality_score, source, tier}."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "query": {
                         "type": "string",
                         "description": "Natural-language search query, e.g. 'How was the authentication module designed?'."
                     },
                     "top_k": {
                         "type": "integer",
                         "default": 5,
                         "description": "Maximum number of results to return, between 1 and 50."
                     }
                 }, "required": ["query"]}),
            Tool(name="omega_ingest",
                 description=(
                     "Stores a new knowledge fragment in the provenance RAG store with source and evidence tier metadata. "
                     "Use this to persist decisions, patterns, or findings for future retrieval via omega_rag_query. "
                     "Returns JSON with fields: fragment_id, stored (boolean), timestamp."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "content": {
                         "type": "string",
                         "description": "Text content to store, e.g. 'Switched from Poetry to setuptools for pyproject.toml compatibility'."
                     },
                     "source": {
                         "type": "string",
                         "description": "Origin identifier for provenance tracking, e.g. 'code-review', 'user-session', 'documentation'."
                     },
                     "tier": {
                         "type": "string",
                         "description": "Evidence confidence tier: A (verified/reproducible), B (reliable), C (single source), D (unverified).",
                         "default": "B",
                         "enum": ["A", "B", "C", "D"]
                     }
                 }, "required": ["content"]}),
            Tool(name="omega_vault_search",
                 description=(
                     "Searches the vault database using exact keyword matching via SQLite FTS5. "
                     "Use this for precise keyword lookups; use omega_rag_query instead for semantic/meaning-based search. "
                     "Returns JSON array of matching vault entries with timestamps and session context."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "query": {
                         "type": "string",
                         "description": "FTS5 keyword query supporting AND, OR, NOT, and quoted phrases, e.g. '\"deploy production\" NOT staging'."
                     }
                 }, "required": ["query"]}),
            Tool(name="omega_cortex_check",
                 description=(
                     "Read-only alignment gate that measures semantic similarity between a proposed action and the task baseline. "
                     "Use this to check alignment before high-impact operations without modifying any arguments; "
                     "use omega_cortex_steer instead if you want automatic argument correction. "
                     "Returns JSON with fields: approved (boolean), similarity (float 0-1), verdict (APPROVED | BLOCKED)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "tool": {
                         "type": "string",
                         "description": "Name of the tool to check alignment for, e.g. 'omega_ingest'."
                     },
                     "args": {
                         "type": "object",
                         "description": "The proposed arguments for the tool call, serialized as a JSON object."
                     },
                     "baseline_prompt": {
                         "type": "string",
                         "description": "Task baseline describing the intended operation, e.g. 'Refactoring the auth module for OAuth2 support'."
                     }
                 }, "required": ["tool", "args", "baseline_prompt"]}),
            Tool(name="omega_cortex_steer",
                 description=(
                     "Alignment gate with automatic argument correction for drifting tool calls. "
                     "Use this instead of omega_cortex_check when you want arguments auto-corrected toward the baseline; "
                     "blocks hard if similarity < 0.45, steers if 0.45-0.65, passes unchanged if > 0.65. "
                     "Returns JSON with fields: similarity (float), steered_args (object), corrections (array), verdict (PASSED | STEERED | BLOCKED)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "tool": {
                         "type": "string",
                         "description": "Name of the tool whose arguments may need correction, e.g. 'omega_seal_run'."
                     },
                     "args": {
                         "type": "object",
                         "description": "The original arguments that may be drifting from baseline. Will be corrected if in the steering range."
                     },
                     "baseline_prompt": {
                         "type": "string",
                         "description": "Task baseline to steer toward, e.g. 'Deploying hotfix to staging environment'."
                     }
                 }, "required": ["tool", "args", "baseline_prompt"]}),
            Tool(name="omega_seal_run",
                 description=(
                     "Appends a tamper-proof entry to the SEAL (Secure Evidence Audit Ledger) SHA-256 hash chain. "
                     "Use this to create an immutable audit record of significant events, decisions, or state changes. "
                     "Returns JSON with fields: seal_hash (hex string), chain_position (integer), timestamp (ISO 8601)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "context": {
                         "type": "object",
                         "description": "Structured event metadata, e.g. {\"action\": \"deploy\", \"target\": \"production\", \"version\": \"2.1.0\"}."
                     },
                     "response": {
                         "type": "string",
                         "description": "Outcome text to seal into the immutable ledger, e.g. 'Deployment succeeded with zero errors'."
                     }
                 }, "required": ["context", "response"]}),
            Tool(name="omega_log_session",
                 description=(
                     "Writes a complete session record to the vault for cross-session persistence. "
                     "Use this at the end of a work session to record what was done; data is retrievable via omega_vault_search. "
                     "Returns JSON with fields: session_id, stored (boolean), entry_count (integer)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "session_id": {
                         "type": "string",
                         "description": "Unique session identifier. Auto-generated if omitted."
                     },
                     "task": {
                         "type": "string",
                         "description": "Description of the task completed, e.g. 'Migrated database schema to v3'."
                     },
                     "decisions": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Key decisions made, e.g. ['Used Alembic for migrations', 'Kept backward compatibility']."
                     },
                     "files_modified": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "File paths changed, e.g. ['src/models.py', 'alembic/versions/001.py']."
                     }
                 }, "required": ["task"]}),
            Tool(name="omega_write_handoff",
                 description=(
                     "Creates a SHA-256 sealed handoff document that auto-loads on the next server restart via omega://session/preload. "
                     "Use this at the end of a session to ensure seamless context continuity for the next session. "
                     "Returns JSON with fields: handoff_hash (hex string), file_path (string)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "task": {
                         "type": "string",
                         "description": "Task title for the handoff, e.g. 'OAuth2 migration phase 2'."
                     },
                     "summary": {
                         "type": "string",
                         "description": "Concise summary of progress and current state for the next session."
                     },
                     "decisions": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Key decisions the next session should know about."
                     },
                     "files_modified": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Files changed during this session."
                     },
                     "next_steps": {
                         "type": "array",
                         "items": {"type": "string"},
                         "description": "Ordered list of recommended next actions."
                     },
                     "conversation_id": {
                         "type": "string",
                         "description": "Optional external conversation tracking ID."
                     }
                 }, "required": ["task", "summary"]}),
            Tool(name="omega_execute",
                 description=(
                     "Cortex-governed execution wrapper that checks alignment, steers if needed, executes, and auto-logs to the SEAL chain. "
                     "Use this as the default way to invoke any Omega Brain tool with full governance; "
                     "only wraps Omega Brain tools — external tools are returned with steered_args for manual invocation. "
                     "Returns JSON with fields: result (object), cortex_verdict (string), seal_hash (hex string)."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "tool": {
                         "type": "string",
                         "description": "Omega Brain tool name to execute, e.g. 'omega_ingest', 'omega_rag_query', 'omega_seal_run'."
                     },
                     "args": {
                         "type": "object",
                         "description": "Arguments for the target tool. May be steered by the Cortex before execution."
                     },
                     "baseline": {
                         "type": "string",
                         "description": "Task baseline for the Cortex alignment check, e.g. 'Ingesting code review findings'."
                     }
                 }, "required": ["tool", "args", "baseline"]}),
            Tool(name="omega_brain_report",
                 description=(
                     "Generates a human-readable audit report showing SEAL chain entries, Cortex verdicts, and vault statistics. "
                     "Use this to inspect the trust and governance layer; use omega_brain_status for a quick health summary instead. "
                     "Returns formatted text report with sections: seal_tail, cortex_verdicts, vault_stats, session_health."
                 ),
                 inputSchema={"type": "object", "properties": {
                     "lines": {
                         "type": "integer",
                         "description": "Number of recent SEAL ledger entries to include, between 1 and 100.",
                         "default": 10
                     }
                 }}),
            Tool(name="omega_brain_status",
                 description=(
                     "Returns a quick health summary of all Omega Brain subsystems as structured JSON. "
                     "Use this for a fast status check; use omega_brain_report for a detailed audit report instead. "
                     "Returns JSON with fields: vault_sessions (int), vault_entries (int), rag_fragments (int), "
                     "seal_entries (int), session_id (string), uptime_seconds (float), call_count (int)."
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

    log.info(f"[omega-brain] Standalone v2.1.1 + Build Gates | session={_SESSION_ID} | data={DATA_DIR}")
    
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
