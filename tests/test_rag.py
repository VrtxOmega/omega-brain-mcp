import os
import tempfile
import sys
from pathlib import Path

# Force isolated test environment
_temp_dir = tempfile.TemporaryDirectory()
os.environ["OMEGA_BRAIN_DATA_DIR"] = _temp_dir.name

sys.path.insert(0, str(Path(__file__).parent.parent))

from omega_brain_mcp_standalone import _ingest_fragment, _rag_search, _brain_preload, _init_db

_init_db()

class TestRag:
    def test_ingest_and_search(self):
        fid = _ingest_fragment("This is a novel fact about quantum computing.", "test_src", "A")
        assert fid is not None

        res = _rag_search("quantum computing fact")
        assert "fragments" in res
        assert len(res["fragments"]) > 0

    def test_brain_preload(self):
        res = _brain_preload("quantum computing")
        assert "rag_fragments" in res
        assert "veritas_score" in res
