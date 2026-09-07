"""Initialized MCP helper. Pass task_id explicitly for scoped calls."""
import asyncio
from pathlib import Path
from stdio_client import StdioClient
class OmegaBrainClient(StdioClient):
 def __init__(self,server_path=None):super().__init__(server_path or Path(__file__).parent/'omega_brain_mcp_standalone.py')
_client=None
def omega_call(tool,**kwargs):
 global _client
 if _client is None:_client=OmegaBrainClient()
 return _client.call(tool,kwargs)
async def omega_call_async(tool,**kwargs):return await asyncio.to_thread(omega_call,tool,**kwargs)
