import os
import tempfile
import sys
from pathlib import Path

# Force isolated test environment
_temp_dir = tempfile.TemporaryDirectory()
os.environ["OMEGA_BRAIN_DATA_DIR"] = _temp_dir.name

import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from omega_brain_mcp_standalone import _vault_search, _read_handoff

def test_vault_search_exception(monkeypatch):
    import sqlite3
    def mock_db():
        class MockConn:
            def execute(self, *args, **kwargs):
                raise sqlite3.Error("Mocked error")
        return MockConn()

    monkeypatch.setattr("omega_brain_mcp_standalone._db", mock_db)
    res = _vault_search("query")
    assert res["count"] == 0

def test_read_handoff_corrupted():
    from omega_brain_mcp_standalone import HANDOFF_FILE
    if HANDOFF_FILE.exists():
        HANDOFF_FILE.unlink()
    HANDOFF_FILE.write_text("{corrupted json", encoding="utf-8")
    res = _read_handoff()
    assert res is None
    HANDOFF_FILE.unlink()
