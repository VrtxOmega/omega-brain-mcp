#!/usr/bin/env python3
"""
Merge ~/.hermes/omega-brain/omega_brain.db into ~/.omega-brain/omega_brain.db.
Run once to unify the two diverged copies. Safe to re-run (INSERT OR IGNORE).
"""
import sqlite3
from pathlib import Path

PRIMARY = Path.home() / ".omega-brain" / "omega_brain.db"
HERMES  = Path.home() / ".hermes" / "omega-brain" / "omega_brain.db"

if not HERMES.exists():
    print(f"[merge] Hermes DB not found at {HERMES}, nothing to do.")
    raise SystemExit(0)

print(f"[merge] Primary : {PRIMARY}")
print(f"[merge] Hermes  : {HERMES}")

src  = sqlite3.connect(str(HERMES))
dst  = sqlite3.connect(str(PRIMARY))
dst.execute("PRAGMA journal_mode=WAL")

TABLES = {
    "sessions":  "INSERT OR IGNORE INTO sessions SELECT * FROM src.sessions",
    "entries":   "INSERT OR IGNORE INTO entries (session_id, role, content, timestamp, token_count) SELECT session_id, role, content, timestamp, token_count FROM src.entries",
    "fragments": "INSERT OR IGNORE INTO fragments SELECT * FROM src.fragments",
    "omega_brain": "INSERT OR IGNORE INTO omega_brain SELECT * FROM src.omega_brain",
    "cortex_vault": None,
    "ledger":    "INSERT OR IGNORE INTO ledger (event, payload, hash, prev_hash, timestamp) SELECT event, payload, hash, prev_hash, timestamp FROM src.ledger",
    "tape":      None,
}

dst.execute(f"ATTACH DATABASE '{HERMES}' AS src")

for table, sql in TABLES.items():
    if sql is None:
        continue
    try:
        before = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        dst.execute(sql)
        dst.commit()
        after = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"[merge] {table}: {before} → {after} (+{after - before})")
    except Exception as e:
        print(f"[merge] {table}: skipped ({e})")

dst.execute("DETACH DATABASE src")
dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
dst.close()
src.close()
print("[merge] Done. ~/.omega-brain/omega_brain.db is now the unified canonical DB.")
