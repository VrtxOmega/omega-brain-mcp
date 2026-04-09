import os
import tempfile
import sys
from pathlib import Path

# Force isolated test environment
_temp_dir = tempfile.TemporaryDirectory()
os.environ["OMEGA_BRAIN_DATA_DIR"] = _temp_dir.name

import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from omega_brain_mcp_standalone import _vault_log_session, _vault_search, _vault_autoseal, _init_db

_init_db()

class TestVault:
    def test_vault_log_session(self):
        sid = "test-session-1"
        res = _vault_log_session(sid, "testing vault log", ["dec1", "dec2"], ["file1.py"])
        assert res["logged"] is True
        assert res["session_id"] == sid

        # Test Search
        search_res = _vault_search("dec1")
        assert search_res["count"] >= 1

    def test_vault_autoseal(self):
        res = _vault_autoseal("test-session-1", "my hint")
        assert isinstance(res, dict)
        assert res["task"] == "my hint"

    def test_vault_search_empty(self):
        res = _vault_search("")
        assert res["count"] == 0
