import os
import tempfile
import sys
from pathlib import Path

# Force isolated test environment
_temp_dir = tempfile.TemporaryDirectory()
os.environ["OMEGA_BRAIN_DATA_DIR"] = _temp_dir.name

sys.path.insert(0, str(Path(__file__).parent.parent))

from omega_brain_mcp_standalone import _cortex_steer, _init_db

_init_db()

class TestSteer:
    def test_cortex_steer_approved(self):
        # We need something with very high similarity to pass check and get approved
        res = _cortex_steer("some_tool", {"k": "v"}, "Tool: some_tool | Args: {\"k\": \"v\"}")
        assert res["approved"] is True
