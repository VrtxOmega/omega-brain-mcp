import unittest,tempfile,os,sys,json,asyncio,gc
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();ROOT=Path(TEMP.name)
os.environ.update(OMEGA_BRAIN_DATA_DIR=str(ROOT/'brain'),VERITAS_SHARED_DIR=str(ROOT/'shared'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import omega_brain_mcp_standalone as brain
import omega_runtime as runtime
class Contracts(unittest.TestCase):
 def test_scope_required(self):
  with self.assertRaises(ValueError):brain._rag_search('query')
 def test_scoped_retrieval(self):
  runtime.ingest(brain.DB_PATH,'violet independent context','test','B','a')
  self.assertFalse(runtime.search(brain.DB_PATH,'violet',task_id='b')['fragments'])
  self.assertTrue(runtime.search(brain.DB_PATH,'violet',task_id='a')['fragments'])
 def test_similarity_is_advisory(self):
  r=brain._cortex_steer('write',{'path':'correct.txt'},'unrelated work')
  self.assertIsNone(r['approved']);self.assertEqual(r['steered_args'],{'path':'correct.txt'})
 def test_stable_features(self):self.assertEqual(runtime.cosine(runtime.embed('abcd'),runtime.embed('wxyz')),0)
 def test_ledger_v2(self):
  runtime.ledger_append(brain.DB_PATH,'TEST',{'nested':{'value':42}},'a');self.assertTrue(runtime.ledger_verify(brain.DB_PATH)['valid'])
 def test_handoff_scope(self):
  brain._write_handoff('a','retained',[],[],[],'a');self.assertIsNone(brain._read_handoff('b'));self.assertEqual(brain._read_handoff('a')['summary'],'retained')
 def test_resources_and_schema(self):
  self.assertIn('SCOPE_REQUIRED',asyncio.run(brain.read_resource('omega://session/preload')))
  schema=next(t.inputSchema for t in asyncio.run(brain.list_tools()) if t.name=='omega_ingest');self.assertIn('task_id',schema['required'])
 def test_initialized_helper(self):
  from omega_client import OmegaBrainClient
  with OmegaBrainClient() as client:
   self.assertTrue(client.call('omega_integrity_status',{})['valid'])
   with self.assertRaises(RuntimeError):client.call('omega_rag_query',{'query':'missing scope'})
 def test_missing_evidence(self):
  from veritas_build_gates import dependency_gate,security_gate,adversary_gate
  for gate in (dependency_gate,security_gate,adversary_gate):self.assertEqual(gate({})['verdict'],'INCONCLUSIVE')
def tearDownModule():gc.collect();TEMP.cleanup()
if __name__=='__main__':unittest.main(verbosity=2)
