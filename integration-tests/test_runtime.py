import os,sys,tempfile,unittest,json,sqlite3,asyncio,time,subprocess,gc
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(os.environ.get('OMEGA_SUITE_ROOT',str(Path(__file__).resolve().parents[1])))
TEMP=tempfile.TemporaryDirectory();DATA=Path(TEMP.name)
os.environ.update(OMEGA_BRAIN_DATA_DIR=str(DATA/'brain'),OMEGA_STENOGRAPHER_DIR=str(DATA/'steno'),VERITAS_SHARED_DIR=str(DATA/'shared'),OMEGA_CODEX_SESSIONS=str(DATA/'sessions'),SSWP_DB=str(DATA/'sswp.sqlite'))
sys.path[:0]=[str(ROOT/'omega-brain'),str(ROOT/'omega-stenographer')]
import omega_runtime as runtime
import omega_brain_mcp_standalone as brain
import omega_stenographer_mcp as steno
import codex_capture as capture
def call(fn,name,args):return asyncio.run(fn(name,args))
def text(result):return json.loads(result[0].text)

class RuntimeTests(unittest.TestCase):
 def test_missing_security_evidence_cannot_pass(self):
  import veritas_build_gates as gates
  self.assertEqual(gates.security_gate({})['verdict'],'INCONCLUSIVE')
  self.assertEqual(gates.dependency_gate({})['verdict'],'INCONCLUSIVE')
  self.assertEqual(gates.security_gate({'security':{'secrets_detected':[{'file':'fixture'}]}})['verdict'],'VIOLATION')
 def test_embeddings_stable_and_disjoint(self):
  self.assertEqual(runtime.cosine(runtime.embed('abcd'),runtime.embed('wxyz')),0)
  self.assertEqual(runtime.cosine(runtime.embed('same words'),runtime.embed('same words')),1)
  with self.assertRaises(ValueError):runtime.cosine([1],[1,2])
  out=subprocess.check_output([sys.executable,'-c',"import sys;sys.path.insert(0,sys.argv[1]);import omega_runtime as r;print(r.canonical(r.embed('shared words'))) ",str(ROOT/'omega-brain')],env=os.environ,text=True)
  self.assertEqual(json.loads(out),runtime.embed('shared words'))
 def test_advisory_never_changes_arguments(self):
  args={'path':'C:/Approved/valid file.txt','nested':{'command':'build'}}
  result=brain._cortex_steer('write_file',args,'build another project')
  self.assertEqual(result['steered_args'],args);self.assertIsNone(result['approved']);self.assertFalse(result['permission_checked'])
 def test_scoped_index_and_supersession(self):
  old=runtime.ingest(brain.DB_PATH,'cobalt decision old','test','B','scope-a')
  runtime.ingest(brain.DB_PATH,'cobalt hidden','test','B','scope-b')
  new=runtime.ingest(brain.DB_PATH,'cobalt decision corrected','test','B','scope-a',old)
  runtime.ingest(brain.DB_PATH,'cobalt decision corrected','test','B','scope-a',old)
  result=runtime.search(brain.DB_PATH,'cobalt',50,'scope-a')
  self.assertEqual([r['id'] for r in result['fragments']],[new]);self.assertLessEqual(result['candidates_scored'],256)
  self.assertEqual(len(runtime.search(brain.DB_PATH,'cobalt',50,cross_task=True)['fragments']),2)
  with self.assertRaises(ValueError):runtime.search(brain.DB_PATH,'cobalt')
  with self.assertRaises(ValueError):runtime.ingest(brain.DB_PATH,'bad supersession','test','B','scope-b',new)
 def test_concurrent_ledger_and_tamper(self):
  path=DATA/'ledger.sqlite'
  with sqlite3.connect(path) as db:db.execute('CREATE TABLE ledger(id INTEGER,payload TEXT)');db.execute("INSERT INTO ledger VALUES(1,'original preserved')")
  with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda n:runtime.ledger_append(path,'TEST',{'nested':{'n':n}},'a'),range(32)))
  verified=runtime.ledger_verify(path);self.assertTrue(verified['valid']);self.assertEqual(verified['rows'],33)
  with sqlite3.connect(path) as db:
   self.assertEqual(db.execute('SELECT payload FROM ledger').fetchone()[0],'original preserved')
   db.execute("UPDATE ledger_v2 SET event_json=replace(event_json,'TEST','TAMPER') WHERE id=5")
  self.assertFalse(runtime.ledger_verify(path)['valid'])
 def test_task_handoffs_and_full_seal(self):
  brain._write_handoff('A','alpha',[],[],[],'handoff-a');brain._write_handoff('B','bravo',[],[],[],'handoff-b')
  self.assertEqual(brain._read_handoff('handoff-a')['summary'],'alpha')
  brain._seal_run({'task_id':'handoff-a'},'x'*1500+'tail-evidence')
  with sqlite3.connect(brain.DB_PATH) as db:self.assertIn('tail-evidence',db.execute('SELECT event_json FROM ledger_v2 ORDER BY id DESC LIMIT 1').fetchone()[0])
  result=json.loads(asyncio.run(brain.read_resource('omega://session/handoff-a')))
  self.assertEqual(result['ledger_count'],1)
  self.assertEqual(json.loads(asyncio.run(brain.read_resource('omega://session/preload')))['status'],'SCOPE_REQUIRED')
 def test_steno_brief_isolation_old_retrieval_and_milestones(self):
  for i in range(24*8):
   content=('ancienttelescope ' if i==0 else '')+f'Decided to retain significant decision number {i}. Next constraint item {i}.'
   call(steno.call_tool,'stenographer_ingest_exchange',{'role':'user','content':content,'session_id':'st-a'})
  call(steno.call_tool,'stenographer_ingest_exchange',{'role':'user','content':'secret from another conversation','session_id':'st-b'})
  brief=text(call(steno.call_tool,'stenographer_compact_guard',{'session_id':'st-a','query':'ancienttelescope'}))
  self.assertTrue(brief['briefs']);self.assertIn('number 7',brief['briefs'][0]['summary']);self.assertNotIn('secret from another',json.dumps(brief))
  with steno.get_db() as db:ex=db.execute("SELECT id FROM exchanges WHERE session_id='st-a' ORDER BY id LIMIT 1").fetchone()[0]
  with self.assertRaises(ValueError):call(steno.call_tool,'stenographer_mark_milestone',{'exchange_id':ex,'label':'bad','session_id':'st-b'})
  call(steno.call_tool,'stenographer_mark_milestone',{'exchange_id':ex,'label':'retained decision','session_id':'st-a'})
  brief=text(call(steno.call_tool,'stenographer_get_brief',{'session_id':'st-a'}));self.assertEqual(brief['milestones'][0]['id'],ex)
  with self.assertRaises(ValueError):call(steno.call_tool,'stenographer_get_brief',{})
 def test_full_text_and_idempotent_event_delivery(self):
  call(steno.call_tool,'stenographer_ingest_exchange',{'role':'assistant','content':'x '*3000+'tailsearchneedle','session_id':'event-test','source_key':'idempotency-key'})
  call(steno.call_tool,'stenographer_ingest_exchange',{'role':'assistant','content':'x '*3000+'tailsearchneedle','session_id':'event-test','source_key':'idempotency-key'})
  results=text(call(steno.call_tool,'stenographer_query_history',{'session_id':'event-test','query':'tailsearchneedle'}));self.assertEqual(len(results),1)
  state={}
  for _ in range(4):asyncio.run(capture.deliver_events(state))
  matches=runtime.search(brain.DB_PATH,'tailsearchneedle',5,'event-test')['fragments'];self.assertEqual(len(matches),1)
  with runtime.bus() as db:db.execute("DELETE FROM receipts WHERE event_id=(SELECT id FROM events WHERE task_id='event-test' LIMIT 1)")
  asyncio.run(capture.deliver_events(state));self.assertEqual(len(runtime.search(brain.DB_PATH,'tailsearchneedle',5,'event-test')['fragments']),1)
 def test_old_transcript_appends_are_captured(self):
  capture.ROOT.mkdir(exist_ok=True);p=capture.ROOT/'rollout-2026-09-01T00-00-00-00000000-0000-0000-0000-000000000000.jsonl'
  def msg(t):return json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'text','text':t}]}})+'\n'
  p.write_text(msg('old skipped'),encoding='utf-8');state={};asyncio.run(capture.scan(state))
  with p.open('a',encoding='utf-8') as f:f.write(msg('resumed durable text'))
  asyncio.run(capture.scan(state))
  with steno.get_db() as db:
   rows=db.execute("SELECT content FROM exchanges WHERE session_id='00000000-0000-0000-0000-000000000000'").fetchall()
  self.assertEqual([r[0] for r in rows],['resumed durable text'])
 def test_trace_scope(self):
  a=runtime.trace('trace-a');b=runtime.trace('trace-b');self.assertNotEqual(a['trace_id'],b['trace_id'])
  brain._bridge.update_claeg_state('TERMINAL_SHUTDOWN',task_id='trace-a')
  self.assertEqual(runtime.trace('trace-b')['claeg_state'],'STABLE_CONTINUATION')
 def test_reconcile_independent_snapshots(self):
  call(steno.call_tool,'stenographer_ingest_exchange',{'role':'user','content':'snapshotrecoveryneedle','session_id':'snapshot'})
  state={}
  for _ in range(4):asyncio.run(capture.deliver_events(state))
  with runtime.bus() as db:
   eid=db.execute("SELECT id FROM events WHERE task_id='snapshot'").fetchone()[0]
   db.execute('DELETE FROM events WHERE id=?',(eid,))
  capture.reconcile_delivery();asyncio.run(capture.deliver_events(state))
  self.assertTrue(runtime.pending('unused-consumer','snapshot'))
  with sqlite3.connect(brain.DB_PATH) as db:db.execute("DELETE FROM fragments WHERE source=?",('event:'+eid,))
  capture.reconcile_delivery();asyncio.run(capture.deliver_events(state))
  self.assertTrue(runtime.search(brain.DB_PATH,'snapshotrecoveryneedle',task_id='snapshot')['fragments'])
 def test_task_schema_and_invalid_dispatch(self):
  schemas={t.name:t.inputSchema for t in asyncio.run(brain.list_tools())}
  self.assertIn('task_id',schemas['omega_ingest']['required'])
  with self.assertRaises(ValueError):call(brain.call_tool,'omega_execute',{'tool':'sswp_witness','args':{}})

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests))
 gc.collect();TEMP.cleanup();sys.exit(not result.wasSuccessful())
