#!/usr/bin/env python3
"""
OmegaBrain Network MCP Server — Unified Vault for All Agents
=============================================================
Runs as an SSE MCP server on 0.0.0.0:7700, accessible from any machine
on the Tailscale network (Raider, Dell, phone).

All agents (Claude, Kimi, Gemini, Hermes) write to one DB:
  ~/.omega-brain/omega_brain.db

Every write is tagged with source_agent so provenance is tracked.

Auth: Bearer token stored in ~/.omega-brain/network.token
Add to Hermes:  hermes mcp add omega-brain-network http://100.65.218.30:7700/sse
Add to Claude:  set OMEGA_BRAIN_URL in .claude env or MCP config

Tools exposed:
  omega_remember      — save a memory/fragment
  omega_recall        — semantic + FTS search
  omega_context       — preload relevant context for a task
  omega_log_session   — log a completed session with decisions
  omega_handoff       — write a cross-agent handoff note (directed)
  omega_read_handoff  — read the latest handoff for an agent
  omega_status        — DB health check
  omega_send          — send a directed or broadcast message to another agent
  omega_inbox         — fetch unread messages for an agent
  omega_subscribe     — peek new messages since a watermark without marking read
  omega_agents        — list registered agents and their presence
  omega_post_task     — post a task to the shared queue
  omega_claim_task    — atomically claim an open task
  omega_complete_task — mark a claimed task done with a result
  omega_tasks         — list tasks in the shared queue
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from mcp.server import Server
from mcp.server.fastmcp.server import StreamableHTTPASGIApp
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

try:
    import numpy as np
except Exception:
    np = None

# ── Config ─────────────────────────────────────────────────────
DATA_DIR    = Path(os.environ.get("OMEGA_BRAIN_DATA_DIR", Path.home() / ".omega-brain"))
DB_PATH     = DATA_DIR / "omega_brain.db"
TOKEN_FILE  = DATA_DIR / "network.token"
TOKENS_FILE = DATA_DIR / "agent_tokens.json"   # {"<token>": "agent-name", ...}
PORT        = int(os.environ.get("OMEGA_BRAIN_PORT", 7700))
HOST        = os.environ.get("OMEGA_BRAIN_HOST", "100.65.218.30")

DATA_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("OmegaBrain.Network")

# ── Auth Token ──────────────────────────────────────────────────

def _load_or_create_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    import secrets
    token = secrets.token_hex(32)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    log.info(f"[auth] Created new token at {TOKEN_FILE}")
    return token

BEARER_TOKEN = _load_or_create_token()


_AGENT_ALIASES: dict[str, str] = {
    "anti-gravity": "antigravity",
    "anti_gravity": "antigravity",
    "anti gravity": "antigravity",
    "windsurf": "devin",
    "windswift": "devin",
}


def _normalize_agent_name(name: str) -> str:
    """Canonical lowercase agent id; '*' preserved for broadcast."""
    if not name:
        return "unknown"
    raw = name.strip()
    if raw == "*":
        return "*"
    lowered = raw.lower()
    folded = lowered.replace("_", "-")
    return _AGENT_ALIASES.get(folded, _AGENT_ALIASES.get(lowered.replace("-", " "), lowered))


def _load_agent_tokens() -> dict[str, str]:
    """Per-agent tokens: {token: agent_name}. Optional — legacy shared token still works."""
    if TOKENS_FILE.exists():
        try:
            data = json.loads(TOKENS_FILE.read_text())
            if isinstance(data, dict):
                return {str(k): _normalize_agent_name(str(v)) for k, v in data.items()}
        except Exception:
            log.warning(f"[auth] Could not parse {TOKENS_FILE}")
    return {}

AGENT_TOKENS = _load_agent_tokens()

# Identity asserted by the auth middleware for the current request.
# Empty string = legacy shared token (identity is self-reported).
CALLER_AGENT: contextvars.ContextVar[str] = contextvars.ContextVar("caller_agent", default="")


def _effective_agent(self_reported: str) -> str:
    """Prefer token-asserted identity over self-reported source_agent."""
    asserted = CALLER_AGENT.get()
    if asserted:
        return _normalize_agent_name(asserted)
    if self_reported:
        return _normalize_agent_name(self_reported)
    return "unknown"

# ── Embedding (TF-IDF fallback, upgrades to sentence-transformers if available) ──

_embed_model  = None
_embed_engine = "tfidf"
_tfidf_vocab: dict[str, int] = {}

def _init_embeddings():
    global _embed_model, _embed_engine, _tfidf_vocab
    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        _embed_engine = "sentence-transformers"
        log.info("[embed] Using sentence-transformers")
        return
    except Exception:
        pass
    try:
        from fastembed import TextEmbedding
        _embed_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        _embed_engine = "fastembed"
        log.info("[embed] Using fastembed")
        return
    except Exception:
        pass
    # Build TF-IDF vocab from existing fragments
    try:
        conn = _db()
        rows = conn.execute("SELECT content FROM fragments LIMIT 5000").fetchall()
        conn.close()
        from collections import Counter
        word_counts: Counter = Counter()
        for (text,) in rows:
            for w in re.findall(r"\w+", (text or "").lower()):
                word_counts[w] += 1
        _tfidf_vocab = {w: i for i, (w, _) in enumerate(word_counts.most_common(2048))}
    except Exception:
        _tfidf_vocab = {}
    log.info("[embed] Using TF-IDF fallback")


def _embed(text: str) -> list[float]:
    if _embed_engine == "sentence-transformers" and _embed_model:
        return _embed_model.encode(text, normalize_embeddings=True).tolist()
    if _embed_engine == "fastembed" and _embed_model:
        return [float(x) for x in next(_embed_model.embed([text]))]
    # TF-IDF
    vec = [0.0] * max(len(_tfidf_vocab), 64)
    if _tfidf_vocab:
        for w in re.findall(r"\w+", text.lower()):
            if w in _tfidf_vocab:
                vec[_tfidf_vocab[w]] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]
    # bare keyword hash fallback
    vec = [0.0] * 64
    for w in re.findall(r"\w+", text.lower()):
        vec[hash(w) % 64] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _engine_dim() -> int:
    if _embed_engine == "sentence-transformers":
        return 384
    if _embed_engine == "fastembed":
        return 384
    return max(len(_tfidf_vocab), 64)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    if _embed_engine == "sentence-transformers" and _embed_model:
        return [v.tolist() for v in _embed_model.encode(texts, normalize_embeddings=True)]
    if _embed_engine == "fastembed" and _embed_model:
        return [list(v) for v in _embed_model.embed(texts)]
    return [_embed(t) for t in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a)) or 1.0
    nb  = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


# ── DB ──────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         TEXT PRIMARY KEY,
            title      TEXT,
            summary    TEXT,
            source     TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT,
            role        TEXT,
            content     TEXT,
            timestamp   TEXT,
            token_count INTEGER
        );
        CREATE TABLE IF NOT EXISTS fragments (
            id         TEXT PRIMARY KEY,
            content    TEXT,
            source     TEXT,
            tier       TEXT DEFAULT 'B',
            embedding  TEXT,
            ingested_at TEXT
        );
        CREATE TABLE IF NOT EXISTS omega_brain (
            fragment_id TEXT PRIMARY KEY,
            content     TEXT,
            source      TEXT,
            tier        TEXT,
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS ledger (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            prev_hash  TEXT,
            event_type TEXT,
            payload    TEXT,
            hash       TEXT UNIQUE,
            timestamp  TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            session_id UNINDEXED,
            content,
            tokenize='porter unicode61'
        );
        CREATE TABLE IF NOT EXISTS agents (
            name         TEXT PRIMARY KEY,
            capabilities TEXT,
            machine      TEXT,
            first_seen   TEXT,
            last_seen    TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT NOT NULL,
            to_agent   TEXT NOT NULL,          -- '*' = broadcast
            topic      TEXT DEFAULT '',
            body       TEXT NOT NULL,
            priority   TEXT DEFAULT 'normal',  -- low|normal|high|urgent
            thread_id  TEXT DEFAULT '',
            reply_to   INTEGER,
            trace_id   TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent, id);
        CREATE TABLE IF NOT EXISTS message_reads (
            message_id INTEGER NOT NULL,
            agent      TEXT NOT NULL,
            read_at    TEXT,
            PRIMARY KEY (message_id, agent)
        );
        CREATE TABLE IF NOT EXISTS handoffs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            from_agent TEXT,
            to_agent   TEXT DEFAULT '*',
            task       TEXT,
            summary    TEXT,
            decisions  TEXT,
            status     TEXT DEFAULT 'open',    -- open|claimed
            created_at TEXT,
            claimed_at TEXT,
            claimed_by TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT DEFAULT '',
            posted_by    TEXT,
            claimed_by   TEXT,
            status       TEXT DEFAULT 'open',  -- open|claimed|done|cancelled
            priority     TEXT DEFAULT 'normal',
            result       TEXT,
            trace_id     TEXT DEFAULT '',
            created_at   TEXT,
            claimed_at   TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS telemetry (
            id          TEXT PRIMARY KEY,
            content     TEXT,
            source      TEXT,
            tier        TEXT,
            ingested_at TEXT
        );
    """)
    conn.commit()


def _migrate_agent_names(conn: sqlite3.Connection) -> None:
    """One-time idempotent migration: lowercase + alias-merge agent identifiers."""
    changed = 0

    read_rows = conn.execute(
        "SELECT message_id, agent, read_at FROM message_reads"
    ).fetchall()
    if read_rows:
        merged_reads: dict[tuple[int, str], str] = {}
        for r in read_rows:
            norm = _normalize_agent_name(r["agent"])
            key = (r["message_id"], norm)
            prev = merged_reads.get(key)
            if prev is None or (r["read_at"] or "") < prev:
                merged_reads[key] = r["read_at"]
            if norm != r["agent"]:
                changed += 1
        conn.execute("DELETE FROM message_reads")
        conn.executemany(
            "INSERT INTO message_reads (message_id, agent, read_at) VALUES (?, ?, ?)",
            [(mid, agent, read_at) for (mid, agent), read_at in merged_reads.items()],
        )

    for table, col in (
        ("messages", "from_agent"),
        ("messages", "to_agent"),
        ("handoffs", "from_agent"),
        ("handoffs", "to_agent"),
        ("handoffs", "claimed_by"),
        ("tasks", "posted_by"),
        ("tasks", "claimed_by"),
    ):
        rows = conn.execute(
            f"SELECT id, {col} AS val FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchall()
        for r in rows:
            old = r["val"]
            if old == "*":
                continue
            new = _normalize_agent_name(old)
            if new != old:
                conn.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (new, r["id"]))
                changed += 1

    agent_rows = conn.execute("SELECT * FROM agents").fetchall()
    merged: dict[str, dict] = {}
    for r in agent_rows:
        norm = _normalize_agent_name(r["name"])
        if norm in merged:
            m = merged[norm]
            m["first_seen"] = min(m["first_seen"], r["first_seen"])
            m["last_seen"] = max(m["last_seen"], r["last_seen"])
            if r["capabilities"]:
                m["capabilities"] = r["capabilities"]
            if r["machine"]:
                m["machine"] = r["machine"]
        else:
            merged[norm] = {
                "name": norm,
                "capabilities": r["capabilities"] or "",
                "machine": r["machine"] or "",
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
            }

    if agent_rows:
        conn.execute("DELETE FROM agents")
        for m in merged.values():
            conn.execute(
                "INSERT INTO agents (name, capabilities, machine, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (m["name"], m["capabilities"], m["machine"], m["first_seen"], m["last_seen"]),
            )
        if len(merged) != len(agent_rows):
            changed += len(agent_rows) - len(merged)

    conn.commit()
    if changed:
        log.info(f"[migrate] Normalized {changed} agent identifier field(s)")


_TELEMETRY_RE = re.compile(r"^\[\w*(tool_gate|hook)", re.IGNORECASE)


def _is_telemetry(content: str, source: str) -> bool:
    s = (source or "").lower()
    return (
        "hooks" in s
        or s.startswith("meta/")
        or bool(_TELEMETRY_RE.match(content or ""))
    )


def _migrate_telemetry():
    """One-time (idempotent) sweep: move machine telemetry out of the searchable vault."""
    cond = ("source LIKE '%hooks%' OR source LIKE 'meta/%' "
            "OR content LIKE '[codex_tool_gate]%' OR content LIKE '[context_request]%'")
    conn = _db()
    n = conn.execute(f"SELECT COUNT(*) FROM fragments WHERE {cond}").fetchone()[0]
    if n:
        conn.execute(
            f"INSERT OR IGNORE INTO telemetry (id, content, source, tier, ingested_at) "
            f"SELECT id, content, source, tier, ingested_at FROM fragments WHERE {cond}"
        )
        conn.execute(f"DELETE FROM fragments WHERE {cond}")
        conn.execute(
            "DELETE FROM omega_brain WHERE source LIKE '%hooks%' OR source LIKE 'meta/%' "
            "OR content LIKE '[codex_tool_gate]%' OR content LIKE '[context_request]%'"
        )
        conn.commit()
        log.info(f"[migrate] Quarantined {n} telemetry fragments out of the vault")
    conn.close()


# ── SEAL Ledger (tamper-evident hash chain) ────────────────────

_seal_lock = threading.Lock()


def _seal(event: str, payload: dict) -> str:
    """Append a hash-chained entry to the shared ledger. Returns the entry hash."""
    now = datetime.now(timezone.utc).isoformat()
    with _seal_lock:
        conn = _db()
        prev = conn.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev[0] if prev and prev[0] else "GENESIS"
        body = json.dumps({"event": event, "payload": payload, "prev": prev_hash, "ts": now},
                          sort_keys=True, default=str)
        h = hashlib.sha256(body.encode()).hexdigest()
        conn.execute(
            "INSERT INTO ledger (event_type, payload, hash, prev_hash, timestamp) VALUES (?, ?, ?, ?, ?)",
            (event, json.dumps(payload, default=str), h, prev_hash, now)
        )
        conn.commit()
        conn.close()
    return h


# ── Core Operations ─────────────────────────────────────────────

def _ingest(content: str, source: str, tier: str = "B") -> str:
    fid = hashlib.md5(f"{content}{source}".encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    # Machine telemetry never pollutes the searchable vault
    if _is_telemetry(content, source):
        conn = _db()
        conn.execute(
            "INSERT OR REPLACE INTO telemetry (id, content, source, tier, ingested_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (fid, content, source, tier, now)
        )
        conn.commit()
        conn.close()
        return fid

    emb = _embed(content)
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO fragments (id, content, source, tier, embedding, ingested_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (fid, content, source, tier, json.dumps(emb), now)
    )
    conn.execute(
        "INSERT OR REPLACE INTO omega_brain (fragment_id, content, source, tier, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (fid, content[:2048], source, tier, now)
    )
    conn.commit()
    conn.close()
    _vec_cache_append(fid, content, source, tier, emb, now)
    return fid


# ── Vector Cache (full-vault search, no row limit) ─────────────

_vec_lock = threading.Lock()
_vec_cache: dict = {"ids": [], "meta": [], "matrix": None, "dim": 0}


def _load_vec_cache():
    """Load all searchable fragment embeddings into a numpy matrix."""
    if np is None:
        return
    dim = _engine_dim()
    conn = _db()
    rows = conn.execute(
        "SELECT id, content, source, tier, embedding, ingested_at FROM fragments"
    ).fetchall()
    conn.close()
    ids, meta, vecs = [], [], []
    for r in rows:
        try:
            emb = json.loads(r["embedding"] or "[]")
        except Exception:
            continue
        if len(emb) != dim:
            continue
        ids.append(r["id"])
        meta.append({"content": r["content"], "source": r["source"],
                     "tier": r["tier"], "ingested_at": r["ingested_at"]})
        vecs.append(emb)
    matrix = None
    if vecs:
        matrix = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
    with _vec_lock:
        _vec_cache.update({"ids": ids, "meta": meta, "matrix": matrix, "dim": dim})
    log.info(f"[vec] Cache loaded: {len(ids)} fragments @ dim {dim}")


def _vec_cache_append(fid: str, content: str, source: str, tier: str,
                      emb: list[float], ingested_at: str):
    if np is None:
        return
    with _vec_lock:
        if _vec_cache["matrix"] is None or len(emb) != _vec_cache["dim"]:
            return
        v = np.asarray([emb], dtype=np.float32)
        n = np.linalg.norm(v) or 1.0
        _vec_cache["matrix"] = np.vstack([_vec_cache["matrix"], v / n])
        _vec_cache["ids"].append(fid)
        _vec_cache["meta"].append({"content": content, "source": source,
                                   "tier": tier, "ingested_at": ingested_at})


def _rag_search(query: str, top_k: int = 8, agent_filter: str = "",
                include_tier_c: bool = False) -> list[dict]:
    q_emb = _embed(query)

    # Fast path: full-vault numpy search
    with _vec_lock:
        matrix = _vec_cache["matrix"]
        ids    = list(_vec_cache["ids"])
        meta   = list(_vec_cache["meta"])
        dim    = _vec_cache["dim"]
    if np is not None and matrix is not None and len(q_emb) == dim:
        q = np.asarray(q_emb, dtype=np.float32)
        qn = np.linalg.norm(q) or 1.0
        scores = matrix @ (q / qn)
        order = np.argsort(scores)[::-1]
        results = []
        for i in order:
            if scores[i] <= 0.1:
                break
            m = meta[i]
            if not include_tier_c and m["tier"] == "C":
                continue
            if agent_filter and agent_filter.lower() not in (m["source"] or "").lower():
                continue
            results.append({
                "id": ids[i], "content": m["content"], "source": m["source"],
                "tier": m["tier"], "score": round(float(scores[i]), 4),
                "ingested_at": m["ingested_at"],
            })
            if len(results) >= top_k:
                break
        return results

    # Fallback: recent-rows scan (legacy path)
    conn  = _db()
    where = ["tier != 'C'"] if not include_tier_c else []
    params: list = []
    if agent_filter:
        where.append("source LIKE ?")
        params.append(f"%{agent_filter}%")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"SELECT id, content, source, tier, embedding, ingested_at FROM fragments {where_sql}"
        " ORDER BY ingested_at DESC LIMIT 3000",
        params
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        try:
            emb = json.loads(r["embedding"] or "[]")
        except Exception:
            emb = []
        score = _cosine(q_emb, emb)
        if score > 0.1:
            results.append({
                "id":      r["id"],
                "content": r["content"],
                "source":  r["source"],
                "tier":    r["tier"],
                "score":   round(score, 4),
                "ingested_at": r["ingested_at"],
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def _backfill_enabled() -> bool:
    return os.environ.get("OMEGA_BACKFILL_ENABLED", "1").lower() not in ("0", "false", "no", "off")


def _backfill_embeddings():
    """Background worker: re-embed fragments whose vectors don't match the active engine."""
    if _embed_engine == "tfidf":
        return
    batch_size = max(8, int(os.environ.get("OMEGA_BACKFILL_BATCH", "32")))
    sleep_sec = max(0.05, float(os.environ.get("OMEGA_BACKFILL_SLEEP_SEC", "1.0")))
    dim = _engine_dim()
    total = 0
    while True:
        conn = _db()
        rows = conn.execute(
            "SELECT id, content FROM fragments "
            "WHERE CASE WHEN embedding IS NULL THEN 1 "
            "           WHEN NOT json_valid(embedding) THEN 1 "
            "           WHEN json_array_length(embedding) != ? THEN 1 "
            "           ELSE 0 END "
            "ORDER BY tier ASC, ingested_at DESC LIMIT ?",
            (dim, batch_size)
        ).fetchall()
        if not rows:
            conn.close()
            break
        texts = [(r["content"] or "")[:4096] for r in rows]
        try:
            embs = _embed_batch(texts)
        except Exception as e:
            log.warning(f"[backfill] embed batch failed: {e}")
            conn.close()
            break
        for r, emb in zip(rows, embs):
            conn.execute("UPDATE fragments SET embedding = ? WHERE id = ?",
                         (json.dumps([float(x) for x in emb]), r["id"]))
        conn.commit()
        conn.close()
        total += len(rows)
        if total % (batch_size * 20) == 0:
            log.info(f"[backfill] re-embedded {total} fragments...")
        # Yield CPU between batches — backfill is background work, not urgent.
        time.sleep(sleep_sec)
    if total:
        log.info(f"[backfill] Done: {total} fragments re-embedded. Reloading vec cache.")
        _load_vec_cache()


def _fts_search(query: str, limit: int = 8) -> list[dict]:
    safe = " ".join(f'"{w}"*' for w in re.findall(r"\w{3,}", query))
    if not safe:
        return []
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT session_id, content FROM entries_fts WHERE entries_fts MATCH ? LIMIT ?",
            (safe, limit)
        ).fetchall()
        return [{"session_id": r["session_id"], "content": r["content"]} for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _preload_context(task: str) -> dict:
    fragments = _rag_search(task, top_k=6)
    fts       = _fts_search(task, limit=4)
    handoff   = _read_handoff_data()
    return {
        "task":      task,
        "fragments": fragments,
        "sessions":  fts,
        "handoff":   handoff,
    }


def _log_session(session_id: str, title: str, summary: str,
                 decisions: list, source_agent: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (id, title, summary, source, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (session_id or str(uuid.uuid4()), title, summary, source_agent, now, now)
    )
    # Ingest the summary as a fragment so it's searchable
    if summary:
        _ingest(f"{title}: {summary}", source=f"session/{source_agent}", tier="A")
    for d in (decisions or []):
        if d:
            _ingest(str(d), source=f"decision/{source_agent}", tier="B")
    conn.commit()
    conn.close()
    return {"logged": True, "session_id": session_id}


def _write_handoff_data(task: str, summary: str, decisions: list,
                        source_agent: str, to_agent: str = "*") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    handoff = {
        "task":         task,
        "summary":      summary,
        "decisions":    decisions or [],
        "source_agent": source_agent,
        "to_agent":     to_agent or "*",
        "written_at":   now,
        "session_id":   str(uuid.uuid4()),
    }
    conn = _db()
    cur = conn.execute(
        "INSERT INTO handoffs (from_agent, to_agent, task, summary, decisions, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, 'open', ?)",
        (source_agent, to_agent or "*", task, summary, json.dumps(decisions or []), now)
    )
    handoff["handoff_id"] = cur.lastrowid
    conn.commit()
    conn.close()
    # Legacy single-file handoff kept for backward compatibility
    (DATA_DIR / "handoff.json").write_text(json.dumps(handoff, indent=2))
    # Also ingest into the vault so it's semantically searchable
    content = f"[HANDOFF from {source_agent} to {to_agent or '*'}] Task: {task}\n{summary}\nDecisions: {'; '.join(decisions or [])}"
    _ingest(content, source=f"handoff/{source_agent}", tier="A")
    _seal("HANDOFF_WRITTEN", {"from": source_agent, "to": to_agent or "*", "task": task,
                              "handoff_id": handoff["handoff_id"]})
    _touch_agent(source_agent)
    return {"written": True, "handoff": handoff}


def _read_handoff_data(agent: str = "", claim: bool = False) -> Optional[dict]:
    conn = _db()
    if agent:
        row = conn.execute(
            "SELECT * FROM handoffs WHERE to_agent IN (?, '*') AND status = 'open'"
            " ORDER BY id DESC LIMIT 1", (agent,)
        ).fetchone()
    else:
        row = conn.execute("SELECT * FROM handoffs ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        conn.close()
        # Legacy fallback
        handoff_path = DATA_DIR / "handoff.json"
        if not handoff_path.exists():
            return None
        try:
            return json.loads(handoff_path.read_text())
        except Exception:
            return None
    result = dict(row)
    try:
        result["decisions"] = json.loads(result.get("decisions") or "[]")
    except Exception:
        pass
    if claim and agent and row["status"] == "open":
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE handoffs SET status='claimed', claimed_at=?, claimed_by=? WHERE id=?",
                     (now, agent, row["id"]))
        conn.commit()
        result["status"] = "claimed"
        result["claimed_by"] = agent
        _seal("HANDOFF_CLAIMED", {"handoff_id": row["id"], "by": agent})
    conn.close()
    return result


# ── Agent Registry ────────────────────────────────────────

def _touch_agent(name: str, capabilities: str = "", machine: str = ""):
    name = _normalize_agent_name(name)
    if not name or name == "unknown":
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    conn.execute(
        "INSERT INTO agents (name, capabilities, machine, first_seen, last_seen)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(name) DO UPDATE SET"
        "   last_seen = excluded.last_seen,"
        "   capabilities = CASE WHEN excluded.capabilities != '' THEN excluded.capabilities ELSE agents.capabilities END,"
        "   machine = CASE WHEN excluded.machine != '' THEN excluded.machine ELSE agents.machine END",
        (name, capabilities or "", machine or "", now, now)
    )
    conn.commit()
    conn.close()


def _list_agents(online_minutes: int = 15) -> dict:
    conn = _db()
    rows = conn.execute("SELECT * FROM agents ORDER BY last_seen DESC").fetchall()
    conn.close()
    now = datetime.now(timezone.utc)
    agents = []
    for r in rows:
        try:
            last = datetime.fromisoformat(r["last_seen"])
            online = (now - last).total_seconds() < online_minutes * 60
        except Exception:
            online = False
        agents.append({
            "name": r["name"], "capabilities": r["capabilities"], "machine": r["machine"],
            "first_seen": r["first_seen"], "last_seen": r["last_seen"], "online": online,
        })
    return {"agents": agents, "count": len(agents),
            "online_count": sum(1 for a in agents if a["online"])}


# ── Message Bus ───────────────────────────────────────────

def _pending_inbox_file(agent: str) -> Path:
    agent = _normalize_agent_name(agent)
    inbox_dir = DATA_DIR / "inbox" / agent
    inbox_dir.mkdir(parents=True, exist_ok=True)
    return inbox_dir / "pending.jsonl"


def _pending_signal_file(agent: str) -> Path:
    agent = _normalize_agent_name(agent)
    inbox_dir = DATA_DIR / "inbox" / agent
    inbox_dir.mkdir(parents=True, exist_ok=True)
    return inbox_dir / "signal"


def _append_pending_delivery(agent: str, message: dict) -> None:
    agent = _normalize_agent_name(agent)
    if not agent or agent == "*":
        return
    path = _pending_inbox_file(agent)
    line = json.dumps(message, default=str, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    _pending_signal_file(agent).write_text(
        datetime.now(timezone.utc).isoformat(), encoding="utf-8"
    )


def _queue_pending_delivery(message: dict) -> None:
    to_agent = message.get("to_agent", "")
    from_agent = message.get("from_agent", "")
    if to_agent == "*":
        for agent_row in _list_agents()["agents"]:
            name = agent_row.get("name", "")
            if name and name != from_agent:
                _append_pending_delivery(name, message)
        return
    _append_pending_delivery(to_agent, message)


def _read_pending_messages(agent: str, since_id: int = 0, limit: int = 50) -> list[dict]:
    path = _pending_inbox_file(agent)
    if not path.exists():
        return []
    rows: list[dict] = []
    seen: set[int] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            mid = int(row.get("id") or 0)
            if mid <= since_id or mid in seen:
                continue
            seen.add(mid)
            rows.append(row)
    rows.sort(key=lambda item: int(item.get("id") or 0))
    return rows[-limit:]


def _clear_pending_messages(agent: str, up_to_id: int) -> int:
    path = _pending_inbox_file(agent)
    if not path.exists() or up_to_id <= 0:
        return 0
    kept: list[str] = []
    removed = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                kept.append(raw)
                continue
            mid = int(row.get("id") or 0)
            if mid <= up_to_id:
                removed += 1
                continue
            kept.append(raw)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed


def _send_message(from_agent: str, to_agent: str, topic: str, body: str,
                  priority: str = "normal", thread_id: str = "",
                  reply_to: Optional[int] = None, trace_id: str = "") -> dict:
    from_agent = _normalize_agent_name(from_agent)
    to_agent = "*" if (to_agent or "*").strip() == "*" else _normalize_agent_name(to_agent)
    now = datetime.now(timezone.utc).isoformat()
    if priority not in ("low", "normal", "high", "urgent"):
        priority = "normal"
    conn = _db()
    cur = conn.execute(
        "INSERT INTO messages (from_agent, to_agent, topic, body, priority, thread_id, reply_to, trace_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (from_agent, to_agent, topic or "", body, priority,
         thread_id or "", reply_to, trace_id or "", now)
    )
    mid = cur.lastrowid
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
    conn.commit()
    conn.close()
    message = dict(row) if row else {
        "id": mid, "from_agent": from_agent, "to_agent": to_agent or "*",
        "topic": topic or "", "body": body, "priority": priority,
        "thread_id": thread_id or "", "reply_to": reply_to,
        "trace_id": trace_id or "", "created_at": now,
    }
    _queue_pending_delivery(message)
    _seal("MESSAGE_SENT", {"message_id": mid, "from": from_agent,
                           "to": to_agent or "*", "topic": topic, "priority": priority})
    _touch_agent(from_agent)
    return {"sent": True, "message_id": mid, "from": from_agent,
            "to": to_agent or "*", "created_at": now}


def _inbox(agent: str, unread_only: bool = True, limit: int = 20,
           mark_read: bool = True) -> dict:
    agent = _normalize_agent_name(agent)
    conn = _db()
    if unread_only:
        rows = conn.execute(
            "SELECT m.* FROM messages m"
            " WHERE m.to_agent IN (?, '*') AND m.from_agent != ?"
            "   AND NOT EXISTS (SELECT 1 FROM message_reads r WHERE r.message_id = m.id AND r.agent = ?)"
            " ORDER BY m.id DESC LIMIT ?",
            (agent, agent, agent, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.* FROM messages m WHERE m.to_agent IN (?, '*') OR m.from_agent = ?"
            " ORDER BY m.id DESC LIMIT ?",
            (agent, agent, limit)
        ).fetchall()
    messages = [dict(r) for r in rows]
    if mark_read and unread_only and messages:
        now = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "INSERT OR IGNORE INTO message_reads (message_id, agent, read_at) VALUES (?, ?, ?)",
            [(m["id"], agent, now) for m in messages]
        )
        conn.commit()
    conn.close()
    _touch_agent(agent)
    return {"agent": agent, "messages": messages, "count": len(messages),
            "marked_read": bool(mark_read and unread_only)}


def _subscribe(agent: str, since_id: int = 0, limit: int = 20,
               mark_read: bool = False, clear_pending: bool = False,
               include_pending: bool = True) -> dict:
    agent = _normalize_agent_name(agent)
    since_id = max(int(since_id or 0), 0)
    limit = min(max(int(limit or 20), 1), 100)
    conn = _db()
    rows = conn.execute(
        "SELECT m.* FROM messages m"
        " WHERE m.id > ? AND m.to_agent IN (?, '*') AND m.from_agent != ?"
        "   AND NOT EXISTS (SELECT 1 FROM message_reads r WHERE r.message_id = m.id AND r.agent = ?)"
        " ORDER BY m.id ASC LIMIT ?",
        (since_id, agent, agent, agent, limit)
    ).fetchall()
    conn.close()
    messages = [dict(r) for r in rows]
    pending = _read_pending_messages(agent, since_id, limit) if include_pending else []
    merged: dict[int, dict] = {}
    for item in messages + pending:
        mid = int(item.get("id") or 0)
        if mid > since_id:
            merged[mid] = item
    ordered = [merged[k] for k in sorted(merged.keys())][-limit:]
    watermark = max([since_id, *[int(m.get("id") or 0) for m in ordered]], default=since_id)
    pending_cleared = 0
    if clear_pending and watermark > since_id:
        pending_cleared = _clear_pending_messages(agent, watermark)
    if mark_read and ordered:
        now = datetime.now(timezone.utc).isoformat()
        conn = _db()
        conn.executemany(
            "INSERT OR IGNORE INTO message_reads (message_id, agent, read_at) VALUES (?, ?, ?)",
            [(int(m["id"]), agent, now) for m in ordered if m.get("id")]
        )
        conn.commit()
        conn.close()
    _touch_agent(agent)
    signal_path = _pending_signal_file(agent)
    return {
        "agent": agent,
        "since_id": since_id,
        "watermark": watermark,
        "messages": ordered,
        "count": len(ordered),
        "pending_file": str(_pending_inbox_file(agent)),
        "signal_file": str(signal_path),
        "signal_at": signal_path.read_text(encoding="utf-8").strip() if signal_path.exists() else "",
        "pending_cleared": pending_cleared,
        "marked_read": bool(mark_read and ordered),
        "mode": "subscribe",
        "non_claims": [
            "subscribe returns unread messages newer than since_id without marking read by default",
            "pending_file is a local delivery queue for live watchers and agent drains",
            "call again with the returned watermark as since_id to avoid duplicates",
        ],
    }


# ── Task Queue ────────────────────────────────────────────

def _post_task(title: str, description: str, posted_by: str,
               priority: str = "normal", trace_id: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if priority not in ("low", "normal", "high", "urgent"):
        priority = "normal"
    conn = _db()
    cur = conn.execute(
        "INSERT INTO tasks (title, description, posted_by, status, priority, trace_id, created_at)"
        " VALUES (?, ?, ?, 'open', ?, ?, ?)",
        (title, description or "", posted_by, priority, trace_id or "", now)
    )
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    _seal("TASK_POSTED", {"task_id": tid, "title": title, "by": posted_by, "priority": priority})
    _touch_agent(posted_by)
    return {"posted": True, "task_id": tid, "title": title, "status": "open"}


def _claim_task(task_id: int, agent: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    cur = conn.execute(
        "UPDATE tasks SET claimed_by = ?, status = 'claimed', claimed_at = ?"
        " WHERE id = ? AND status = 'open'",
        (agent, now, task_id)
    )
    claimed = cur.rowcount == 1
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    _touch_agent(agent)
    if claimed:
        _seal("TASK_CLAIMED", {"task_id": task_id, "by": agent})
        return {"claimed": True, "task": dict(row) if row else None}
    return {"claimed": False,
            "reason": "not found" if row is None else f"status is '{row['status']}'",
            "task": dict(row) if row else None}


def _complete_task(task_id: int, agent: str, result: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    cur = conn.execute(
        "UPDATE tasks SET status = 'done', result = ?, completed_at = ?"
        " WHERE id = ? AND status = 'claimed' AND claimed_by = ?",
        (result or "", now, task_id, agent)
    )
    done = cur.rowcount == 1
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    _touch_agent(agent)
    if done:
        if result:
            _ingest(f"[task-result #{task_id}] {row['title']}: {result}",
                    source=f"task/{agent}", tier="B")
        _seal("TASK_COMPLETED", {"task_id": task_id, "by": agent})
        return {"completed": True, "task": dict(row) if row else None}
    return {"completed": False,
            "reason": "not found" if row is None else
                      f"status is '{row['status']}' (claimed_by: {row['claimed_by']})",
            "task": dict(row) if row else None}


def _list_tasks(status: str = "open", limit: int = 25) -> dict:
    conn = _db()
    if status and status != "all":
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"tasks": [dict(r) for r in rows], "count": len(rows), "filter": status or "all"}


def _db_status() -> dict:
    conn = _db()
    counts = {}
    for t in ["fragments", "sessions", "entries", "omega_brain", "ledger",
              "messages", "tasks", "agents", "handoffs", "telemetry"]:
        try:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            counts[t] = -1
    # Most recent agents
    recent = conn.execute(
        "SELECT source, MAX(ingested_at) as last FROM fragments GROUP BY source ORDER BY last DESC LIMIT 10"
    ).fetchall()
    conn.close()
    with _vec_lock:
        vec_loaded = len(_vec_cache["ids"])
    return {
        "db_path":      str(DB_PATH),
        "embed_engine": _embed_engine,
        "vec_cache_fragments": vec_loaded,
        "counts":       counts,
        "recent_agents": [{"source": r["source"], "last": r["last"]} for r in recent],
    }


# ── MCP Server ──────────────────────────────────────────────────

app = Server("omega-brain-network")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="omega_remember",
            description=(
                "Save a memory, insight, decision, or context fragment to the unified OmegaBrain vault. "
                "All agents on all machines share this vault. Always include source_agent so provenance is tracked."
            ),
            inputSchema={"type": "object", "properties": {
                "content":      {"type": "string", "description": "The text to remember."},
                "source_agent": {"type": "string", "description": "Who is saving this (e.g. 'claude/raider', 'kimi/dell', 'gemini/hermes')."},
                "topic":        {"type": "string", "description": "Optional topic tag (e.g. 'omega-wallet', 'aegis', 'security')."},
                "tier":         {"type": "string", "enum": ["A", "B", "C"], "description": "Priority: A=critical, B=standard, C=low. Defaults to B."},
            }, "required": ["content", "source_agent"]},
        ),
        Tool(
            name="omega_recall",
            description=(
                "Search the unified OmegaBrain vault across all agents. Returns semantically similar fragments "
                "ranked by relevance. Use this to check what other agents have learned about a topic."
            ),
            inputSchema={"type": "object", "properties": {
                "query":        {"type": "string", "description": "What to search for."},
                "top_k":        {"type": "integer", "description": "Number of results (default 8, max 20)."},
                "agent_filter": {"type": "string", "description": "Optional: filter results by source agent name."},
            }, "required": ["query"]},
        ),
        Tool(
            name="omega_context",
            description=(
                "Load relevant context from the unified vault for a given task. Returns the most relevant fragments, "
                "recent session notes, and the latest cross-agent handoff. Call this at the start of any task."
            ),
            inputSchema={"type": "object", "properties": {
                "task":         {"type": "string", "description": "Description of what you're about to work on."},
                "source_agent": {"type": "string", "description": "Your agent identifier (for logging)."},
            }, "required": ["task", "source_agent"]},
        ),
        Tool(
            name="omega_log_session",
            description=(
                "Log a completed work session to the shared vault. Saves the title, summary, and key decisions "
                "so other agents can pick up where you left off."
            ),
            inputSchema={"type": "object", "properties": {
                "title":        {"type": "string", "description": "Session title (e.g. 'Fixed OmegaWallet CORS bug')."},
                "summary":      {"type": "string", "description": "What was accomplished."},
                "decisions":    {"type": "array",  "items": {"type": "string"}, "description": "Key decisions made."},
                "source_agent": {"type": "string", "description": "Your agent identifier."},
                "session_id":   {"type": "string", "description": "Optional session ID (auto-generated if omitted)."},
            }, "required": ["title", "summary", "source_agent"]},
        ),
        Tool(
            name="omega_handoff",
            description=(
                "Write a handoff note so another agent (or you on another machine) can continue the work. "
                "Optionally direct it at a specific agent with to_agent. Full history is kept."
            ),
            inputSchema={"type": "object", "properties": {
                "task":         {"type": "string", "description": "What task is being handed off."},
                "summary":      {"type": "string", "description": "Current state and what's left to do."},
                "decisions":    {"type": "array",  "items": {"type": "string"}, "description": "Decisions made so far."},
                "source_agent": {"type": "string", "description": "Your agent identifier."},
                "to_agent":     {"type": "string", "description": "Target agent name, or '*' for anyone (default)."},
            }, "required": ["task", "summary", "source_agent"]},
        ),
        Tool(
            name="omega_read_handoff",
            description=(
                "Read the latest open handoff addressed to you (or to anyone). "
                "Pass your agent name to filter; set claim=true to mark it claimed so other agents skip it."
            ),
            inputSchema={"type": "object", "properties": {
                "agent": {"type": "string", "description": "Your agent name (filters to handoffs for you or '*')."},
                "claim": {"type": "boolean", "description": "Mark the handoff claimed by you. Default false."},
            }},
        ),
        Tool(
            name="omega_status",
            description="Check OmegaBrain vault health: row counts per table, embedding engine, vec cache, recent agents.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="omega_send",
            description=(
                "Send a message to another agent on the network. Use to_agent='*' to broadcast to all agents. "
                "Delivery is queued to the recipient pending inbox and SSE /events stream for live watchers. "
                "Recipients should call omega_subscribe during active work, not only omega_inbox at session start. "
                "Supports threads via thread_id/reply_to."
            ),
            inputSchema={"type": "object", "properties": {
                "to_agent":     {"type": "string", "description": "Recipient agent name (e.g. 'codex', 'hermes', 'grok'), or '*' for broadcast."},
                "body":         {"type": "string", "description": "Message content."},
                "topic":        {"type": "string", "description": "Short topic tag (e.g. 'omega-wallet', 'review-request')."},
                "priority":     {"type": "string", "enum": ["low", "normal", "high", "urgent"], "description": "Defaults to normal."},
                "thread_id":    {"type": "string", "description": "Optional thread identifier for conversations."},
                "reply_to":     {"type": "integer", "description": "Optional message id this replies to."},
                "trace_id":     {"type": "string", "description": "Optional VERITAS trace id for cross-system correlation."},
                "source_agent": {"type": "string", "description": "Your agent identifier."},
            }, "required": ["to_agent", "body", "source_agent"]},
        ),
        Tool(
            name="omega_inbox",
            description=(
                "Fetch your messages (directed + broadcasts). By default returns unread only and marks them read. "
                "Use at session start. During active work prefer omega_subscribe so messages are not auto-consumed."
            ),
            inputSchema={"type": "object", "properties": {
                "source_agent": {"type": "string", "description": "Your agent identifier."},
                "unread_only":  {"type": "boolean", "description": "Default true. Set false to see full history."},
                "mark_read":    {"type": "boolean", "description": "Default true. Set false to peek without marking read."},
                "limit":        {"type": "integer", "description": "Max messages (default 20)."},
            }, "required": ["source_agent"]},
        ),
        Tool(
            name="omega_subscribe",
            description=(
                "Live inbox peek for active sessions. Returns unread messages with id > since_id, "
                "merging DB state with the local pending delivery queue. Does not mark read unless requested. "
                "Use the returned watermark as since_id on the next call. Pair with omsg-watch for heartbeat/presence."
            ),
            inputSchema={"type": "object", "properties": {
                "source_agent":   {"type": "string", "description": "Your agent identifier."},
                "since_id":       {"type": "integer", "description": "Return only messages newer than this id. Default 0."},
                "limit":          {"type": "integer", "description": "Max messages (default 20)."},
                "mark_read":      {"type": "boolean", "description": "Default false. Set true once the agent has handled the messages."},
                "clear_pending":  {"type": "boolean", "description": "Default false. Remove delivered pending-file entries up to watermark."},
                "include_pending":{"type": "boolean", "description": "Default true. Merge pending.jsonl deliveries."},
            }, "required": ["source_agent"]},
        ),
        Tool(
            name="omega_agents",
            description=(
                "List all registered agents on the network with presence info (online = active in last 15 min). "
                "Agents are auto-registered on any tool call; capabilities can be set here."
            ),
            inputSchema={"type": "object", "properties": {
                "source_agent": {"type": "string", "description": "Your agent identifier (registers/heartbeats you)."},
                "capabilities": {"type": "string", "description": "Optional: declare your capabilities (e.g. 'coding,review,deploy')."},
                "machine":      {"type": "string", "description": "Optional: machine you run on (e.g. 'raider', 'dell')."},
            }},
        ),
        Tool(
            name="omega_post_task",
            description=(
                "Post a task to the shared queue for any agent to claim. "
                "Use this to delegate work to other agents (e.g. Devin posts, Codex claims overnight)."
            ),
            inputSchema={"type": "object", "properties": {
                "title":        {"type": "string", "description": "Short task title."},
                "description":  {"type": "string", "description": "Full task details, acceptance criteria, file paths."},
                "priority":     {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "trace_id":     {"type": "string", "description": "Optional VERITAS trace id."},
                "source_agent": {"type": "string", "description": "Your agent identifier."},
            }, "required": ["title", "source_agent"]},
        ),
        Tool(
            name="omega_claim_task",
            description="Atomically claim an open task from the shared queue. Returns claimed=false if another agent got it first.",
            inputSchema={"type": "object", "properties": {
                "task_id":      {"type": "integer", "description": "Task id from omega_tasks."},
                "source_agent": {"type": "string", "description": "Your agent identifier."},
            }, "required": ["task_id", "source_agent"]},
        ),
        Tool(
            name="omega_complete_task",
            description="Mark a task you claimed as done, with a result summary. The result is ingested into the vault.",
            inputSchema={"type": "object", "properties": {
                "task_id":      {"type": "integer", "description": "Task id you claimed."},
                "result":       {"type": "string", "description": "What was done / outcome."},
                "source_agent": {"type": "string", "description": "Your agent identifier."},
            }, "required": ["task_id", "source_agent"]},
        ),
        Tool(
            name="omega_tasks",
            description="List tasks in the shared queue. Filter by status: open (default), claimed, done, cancelled, all.",
            inputSchema={"type": "object", "properties": {
                "status": {"type": "string", "enum": ["open", "claimed", "done", "cancelled", "all"]},
                "limit":  {"type": "integer", "description": "Max tasks (default 25)."},
            }},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    def _out(data: object) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    try:
        if name == "omega_remember":
            source = _effective_agent(arguments.get("source_agent", ""))
            topic  = arguments.get("topic", "")
            tier   = arguments.get("tier", "B")
            tagged = f"[{topic}] {arguments['content']}" if topic else arguments["content"]
            fid    = _ingest(tagged, source=source, tier=tier)
            _touch_agent(source)
            return _out({"saved": True, "id": fid, "source_agent": source})

        elif name == "omega_recall":
            results = _rag_search(
                arguments["query"],
                top_k=min(int(arguments.get("top_k", 8)), 20),
                agent_filter=arguments.get("agent_filter", ""),
            )
            return _out({"query": arguments["query"], "results": results, "count": len(results)})

        elif name == "omega_context":
            who = _effective_agent(arguments.get("source_agent", ""))
            ctx = _preload_context(arguments["task"])
            ctx["inbox_unread"] = _inbox(who, mark_read=False)["count"] if who != "unknown" else 0
            _ingest(
                f"[context_request] {who} requested context for: {arguments['task']}",
                source=f"meta/{who}",
                tier="C",
            )
            _touch_agent(who)
            return _out(ctx)

        elif name == "omega_log_session":
            who = _effective_agent(arguments.get("source_agent", ""))
            result = _log_session(
                arguments.get("session_id", ""),
                arguments["title"],
                arguments["summary"],
                arguments.get("decisions", []),
                who,
            )
            _seal("SESSION_LOGGED", {"title": arguments["title"], "by": who})
            _touch_agent(who)
            return _out(result)

        elif name == "omega_handoff":
            result = _write_handoff_data(
                arguments["task"],
                arguments["summary"],
                arguments.get("decisions", []),
                _effective_agent(arguments.get("source_agent", "")),
                to_agent=arguments.get("to_agent", "*"),
            )
            return _out(result)

        elif name == "omega_read_handoff":
            handoff = _read_handoff_data(
                agent=_effective_agent(arguments.get("agent", "")) if arguments.get("agent") or CALLER_AGENT.get() else "",
                claim=bool(arguments.get("claim", False)),
            )
            return _out(handoff or {"handoff": None, "note": "No handoff on file."})

        elif name == "omega_status":
            return _out(_db_status())

        elif name == "omega_send":
            return _out(_send_message(
                from_agent=_effective_agent(arguments.get("source_agent", "")),
                to_agent=arguments["to_agent"],
                topic=arguments.get("topic", ""),
                body=arguments["body"],
                priority=arguments.get("priority", "normal"),
                thread_id=arguments.get("thread_id", ""),
                reply_to=arguments.get("reply_to"),
                trace_id=arguments.get("trace_id", ""),
            ))

        elif name == "omega_inbox":
            return _out(_inbox(
                agent=_effective_agent(arguments.get("source_agent", "")),
                unread_only=bool(arguments.get("unread_only", True)),
                limit=min(int(arguments.get("limit", 20)), 100),
                mark_read=bool(arguments.get("mark_read", True)),
            ))

        elif name == "omega_subscribe":
            return _out(_subscribe(
                agent=_effective_agent(arguments.get("source_agent", "")),
                since_id=int(arguments.get("since_id", 0) or 0),
                limit=min(int(arguments.get("limit", 20)), 100),
                mark_read=bool(arguments.get("mark_read", False)),
                clear_pending=bool(arguments.get("clear_pending", False)),
                include_pending=bool(arguments.get("include_pending", True)),
            ))

        elif name == "omega_agents":
            who = _effective_agent(arguments.get("source_agent", ""))
            if who and who != "unknown":
                _touch_agent(who, arguments.get("capabilities", ""), arguments.get("machine", ""))
            return _out(_list_agents())

        elif name == "omega_post_task":
            return _out(_post_task(
                title=arguments["title"],
                description=arguments.get("description", ""),
                posted_by=_effective_agent(arguments.get("source_agent", "")),
                priority=arguments.get("priority", "normal"),
                trace_id=arguments.get("trace_id", ""),
            ))

        elif name == "omega_claim_task":
            return _out(_claim_task(
                int(arguments["task_id"]),
                _effective_agent(arguments.get("source_agent", "")),
            ))

        elif name == "omega_complete_task":
            return _out(_complete_task(
                int(arguments["task_id"]),
                _effective_agent(arguments.get("source_agent", "")),
                arguments.get("result", ""),
            ))

        elif name == "omega_tasks":
            return _out(_list_tasks(
                status=arguments.get("status", "open"),
                limit=min(int(arguments.get("limit", 25)), 100),
            ))

        else:
            return _out({"error": f"Unknown tool: {name}"})

    except Exception as e:
        log.exception(f"Tool error: {name}")
        return _out({"error": str(e), "tool": name})


# ── Auth Middleware ─────────────────────────────────────────────

class BearerAuthMiddleware:
    """Pure ASGI auth — compatible with SSE/streamable HTTP that send responses directly."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/health":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if not auth.startswith("Bearer "):
            response = JSONResponse({"error": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        token = auth[7:].strip()
        if token in AGENT_TOKENS:
            CALLER_AGENT.set(_normalize_agent_name(AGENT_TOKENS[token]))
            await self.app(scope, receive, send)
            return
        if token == BEARER_TOKEN:
            CALLER_AGENT.set("")
            await self.app(scope, receive, send)
            return

        response = JSONResponse({"error": "Unauthorized"}, status_code=401)
        await response(scope, receive, send)


# ── Starlette App ───────────────────────────────────────────────

async def health(request: Request):
    status = _db_status()
    return JSONResponse({"status": "ok", **status})


async def api_recall(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    query = str(payload.get("query", "")).strip()
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)

    try:
        top_k = min(max(int(payload.get("top_k", 8)), 1), 20)
    except Exception:
        top_k = 8

    agent_filter = str(payload.get("agent_filter", "")).strip()
    results = _rag_search(query, top_k=top_k, agent_filter=agent_filter)
    return JSONResponse({"query": query, "results": results, "count": len(results)})


async def api_remember(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    content = str(payload.get("content", "")).strip()
    if not content:
        return JSONResponse({"error": "content is required"}, status_code=400)

    source = str(payload.get("source_agent", "omega-smc-android")).strip() or "omega-smc-android"
    topic = str(payload.get("topic", "")).strip()
    tier = str(payload.get("tier", "B")).strip().upper()
    if tier not in {"A", "B", "C"}:
        tier = "B"

    tagged = f"[{topic}] {content}" if topic else content
    fragment_id = _ingest(tagged, source=source, tier=tier)
    return JSONResponse({"saved": True, "id": fragment_id, "source_agent": source, "tier": tier})


async def api_context(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    task = str(payload.get("task", "")).strip()
    if not task:
        return JSONResponse({"error": "task is required"}, status_code=400)

    source = str(payload.get("source_agent", "omega-smc-android")).strip() or "omega-smc-android"
    context = _preload_context(task)
    _ingest(
        f"[context_request] {source} requested context for: {task}",
        source=f"meta/{source}",
        tier="C",
    )
    return JSONResponse(context)


async def api_send(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    body = str(payload.get("body", "")).strip()
    to_agent = str(payload.get("to_agent", "")).strip()
    if not body or not to_agent:
        return JSONResponse({"error": "to_agent and body are required"}, status_code=400)
    from_agent = _effective_agent(str(payload.get("source_agent", "")).strip())
    result = _send_message(
        from_agent=from_agent, to_agent=to_agent,
        topic=str(payload.get("topic", "")), body=body,
        priority=str(payload.get("priority", "normal")),
        thread_id=str(payload.get("thread_id", "")),
        reply_to=payload.get("reply_to"),
        trace_id=str(payload.get("trace_id", "")),
    )
    return JSONResponse(result)


async def api_inbox(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    agent = _effective_agent(str(payload.get("source_agent", "")).strip())
    if not agent or agent == "unknown":
        return JSONResponse({"error": "source_agent is required"}, status_code=400)
    return JSONResponse(_inbox(
        agent=agent,
        unread_only=bool(payload.get("unread_only", True)),
        limit=min(int(payload.get("limit", 20) or 20), 100),
        mark_read=bool(payload.get("mark_read", True)),
    ))


async def api_subscribe(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    agent = _effective_agent(str(payload.get("source_agent", "")).strip())
    if not agent or agent == "unknown":
        return JSONResponse({"error": "source_agent is required"}, status_code=400)
    return JSONResponse(_subscribe(
        agent=agent,
        since_id=int(payload.get("since_id", 0) or 0),
        limit=min(int(payload.get("limit", 20) or 20), 100),
        mark_read=bool(payload.get("mark_read", False)),
        clear_pending=bool(payload.get("clear_pending", False)),
        include_pending=bool(payload.get("include_pending", True)),
    ))


async def api_agents(request: Request):
    return JSONResponse(_list_agents())


async def api_tasks(request: Request):
    if request.method == "GET":
        status = request.query_params.get("status", "open")
        return JSONResponse(_list_tasks(status=status))
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    action = str(payload.get("action", "post"))
    agent = _effective_agent(str(payload.get("source_agent", "")).strip())
    if action == "post":
        title = str(payload.get("title", "")).strip()
        if not title:
            return JSONResponse({"error": "title is required"}, status_code=400)
        return JSONResponse(_post_task(
            title=title, description=str(payload.get("description", "")),
            posted_by=agent, priority=str(payload.get("priority", "normal")),
            trace_id=str(payload.get("trace_id", "")),
        ))
    if action == "claim":
        return JSONResponse(_claim_task(int(payload.get("task_id", 0)), agent))
    if action == "complete":
        return JSONResponse(_complete_task(
            int(payload.get("task_id", 0)), agent, str(payload.get("result", ""))))
    return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)


async def events(request: Request):
    """SSE push stream: new messages for ?agent=<name> (or token-asserted identity)."""
    agent = _normalize_agent_name(CALLER_AGENT.get() or request.query_params.get("agent", ""))
    if not agent:
        return JSONResponse({"error": "agent query param required"}, status_code=400)

    async def gen():
        conn = _db()
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()
        conn.close()
        last_id = row[0]
        yield f"event: hello\ndata: {json.dumps({'agent': agent, 'watermark': last_id})}\n\n"
        while True:
            if await request.is_disconnected():
                break
            conn = _db()
            rows = conn.execute(
                "SELECT * FROM messages WHERE id > ? AND to_agent IN (?, '*') AND from_agent != ?"
                " ORDER BY id ASC LIMIT 50",
                (last_id, agent, agent)
            ).fetchall()
            conn.close()
            for r in rows:
                last_id = r["id"]
                yield f"event: message\ndata: {json.dumps(dict(r), default=str)}\n\n"
            await asyncio.sleep(2)

    _touch_agent(agent)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


_session_manager: StreamableHTTPSessionManager | None = None


def _get_session_manager() -> StreamableHTTPSessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = StreamableHTTPSessionManager(app=app, stateless=True)
    return _session_manager


def build_app() -> Starlette:
    sse = SseServerTransport("/messages")
    session_manager = _get_session_manager()
    streamable_http = StreamableHTTPASGIApp(session_manager)

    async def handle_sse(request: Request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())
        return Response()

    async def handle_messages(request: Request):
        await sse.handle_post_message(request.scope, request.receive, request._send)
        return Response()

    @contextlib.asynccontextmanager
    async def lifespan(_starlette_app: Starlette):
        async with session_manager.run():
            yield

    starlette_app = Starlette(
        routes=[
            Route("/health",   endpoint=health),
            Route("/api/recall", endpoint=api_recall, methods=["POST"]),
            Route("/api/remember", endpoint=api_remember, methods=["POST"]),
            Route("/api/context", endpoint=api_context, methods=["POST"]),
            Route("/api/send",  endpoint=api_send, methods=["POST"]),
            Route("/api/inbox", endpoint=api_inbox, methods=["POST"]),
            Route("/api/subscribe", endpoint=api_subscribe, methods=["POST"]),
            Route("/api/agents", endpoint=api_agents, methods=["GET"]),
            Route("/api/tasks", endpoint=api_tasks, methods=["GET", "POST"]),
            Route("/events",   endpoint=events, methods=["GET"]),
            Route("/mcp",      endpoint=streamable_http, methods=["GET", "POST", "DELETE"]),
            Route("/sse",      endpoint=handle_sse, methods=["GET"]),
            Route("/messages", endpoint=handle_messages, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    return BearerAuthMiddleware(starlette_app)


# ── Entry Point ─────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Ensure DB schema is ready
    conn = _db()
    _ensure_schema(conn)
    _migrate_agent_names(conn)
    conn.close()

    # Quarantine machine telemetry out of the searchable vault (idempotent)
    _migrate_telemetry()

    _init_embeddings()
    _load_vec_cache()

    if _backfill_enabled():
        threading.Thread(target=_backfill_embeddings, daemon=True, name="omega-backfill").start()
        log.info("[backfill] Background embedding backfill enabled")
    else:
        log.info("[backfill] Disabled — set OMEGA_BACKFILL_ENABLED=1 to resume overnight")

    log.info(f"[omega-brain] Network MCP server starting on {HOST}:{PORT}")
    log.info(f"[omega-brain] DB: {DB_PATH}")
    log.info(f"[omega-brain] Token file: {TOKEN_FILE} (never logged)")
    log.info(f"[omega-brain] Per-agent tokens: {TOKENS_FILE} ({len(AGENT_TOKENS)} registered)")
    log.info(f"[omega-brain] MCP endpoint: http://{HOST}:{PORT}/mcp")
    log.info(f"[omega-brain] SSE endpoint: http://{HOST}:{PORT}/sse")

    starlette_app = build_app()
    uvicorn.run(starlette_app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
