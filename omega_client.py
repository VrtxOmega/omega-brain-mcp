"""
omega_client.py — Omega Brain MCP persistent-process client
============================================================
Drop this into any project. One import, all tools available.

Usage:
    from omega_client import omega_call, omega_call_async

    # Sync
    result = omega_call("omega_rag_query", query="my search")

    # Async (LlamaIndex, FastAPI, etc.)
    result = await omega_call_async("omega_rag_query", query="my search")
"""

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path

# Path resolution: looks next to this file, then on PATH
_SERVER_CANDIDATES = [
    Path(__file__).parent / "omega_brain_mcp_standalone.py",
    Path.home() / ".omega-brain" / "omega_brain_mcp_standalone.py",
]
_SERVER_PATH = next((str(p) for p in _SERVER_CANDIDATES if p.exists()), "omega_brain_mcp_standalone.py")


class OmegaBrainClient:
    """
    Persistent subprocess MCP client.
    Thread-safe (internal lock). For async use, call via omega_call_async().
    """

    def __init__(self, server_path: str = _SERVER_PATH):
        self._path = server_path
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._call_id = 0
        self._start()

    def _start(self):
        self._proc = subprocess.Popen(
            [sys.executable, self._path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
        )

    def _restart_if_dead(self):
        if self._proc and self._proc.poll() is not None:
            self._start()

    def call(self, tool: str, args: dict) -> dict:
        """Call a tool synchronously. Returns dict — never raises."""
        with self._lock:
            self._restart_if_dead()
            self._call_id += 1
            payload = json.dumps({
                "jsonrpc": "2.0",
                "id": self._call_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args},
            }) + "\n"
            try:
                self._proc.stdin.write(payload)
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
                if not line:
                    return {"error": "empty response", "tool": tool, "omega_status": "CLIENT_ERROR"}
                response = json.loads(line)
                content = response.get("result", {}).get("content", [])
                text = content[0].get("text", "{}") if content else "{}"
                return json.loads(text)
            except json.JSONDecodeError as e:
                return {"error": f"JSON decode: {e}", "tool": tool, "omega_status": "CLIENT_ERROR"}
            except (BrokenPipeError, OSError) as e:
                return {"error": f"pipe: {e}", "tool": tool, "omega_status": "CLIENT_ERROR"}
            except Exception as e:
                return {"error": str(e), "tool": tool, "omega_status": "CLIENT_ERROR"}

    def close(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()


# ── Module-level singleton ──────────────────────────────────────────────────
_client = OmegaBrainClient()


def omega_call(tool: str, **kwargs) -> dict:
    """Synchronous call. Safe for multi-threaded use."""
    return _client.call(tool, kwargs)


async def omega_call_async(tool: str, **kwargs) -> dict:
    """Async wrapper — runs the blocking call in a thread pool.
    Use this with LlamaIndex, FastAPI, or any async agent framework."""
    return await asyncio.to_thread(_client.call, tool, kwargs)
