import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
class ReviewRegressions(unittest.TestCase):
    def run_code(self, code):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, OMEGA_BRAIN_DATA_DIR=temp+'/brain', VERITAS_SHARED_DIR=temp+'/shared', PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    def test_scoped_prompts_and_resources(self):
        self.run_code("""
import asyncio,json
import omega_brain_mcp_standalone as b
async def check():
    prompts=await b.list_prompts()
    assert all(any(a.name=='task_id' and a.required for a in p.arguments) for p in prompts)
    for p in prompts:
        try: await b.get_prompt(p.name,{})
        except ValueError: pass
        else: raise AssertionError('Unscoped prompt accepted')
    b._ingest_fragment('unique alpha decision',task_id='alpha')
    start=await b.get_prompt('omega_task_start',{'task':'unique alpha','task_id':'alpha'})
    assert '1 task-scoped fragments' in start['messages'][0].content.text
    await b.get_prompt('omega_write_handoff',{'task_id':'alpha','task':'alpha','decisions':'alpha-only'})
    await b.get_prompt('omega_seal_task',{'task_id':'beta','note':'beta-only'})
    a=json.loads(await b.read_resource('omega://task/alpha/handoff'))
    z=json.loads(await b.read_resource('omega://task/beta/handoff'))
    assert a['handoff']['task_id']=='alpha' and z['handoff']['task_id']=='beta'
    assert 'alpha-only' not in json.dumps(z)
    assert json.loads(await b.read_resource('omega://session/handoff'))['status']=='SCOPE_REQUIRED'
    assert b._STARTUP_PRELOAD['status']=='SCOPE_REQUIRED'
asyncio.run(check())
""")
    def test_nafe_ledger_scope(self):
        self.run_code("""
import json
import omega_brain_mcp_standalone as b
b.CLAEG.check_narrative_injection=lambda text:{'clean':False,'flags':['fixture']}
b._handle_veritas_tool('veritas_nafe_scan',{'text':'fixture','task_id':'alpha'})
with b._db() as db:
    events=[json.loads(r[0]) for r in db.execute('SELECT event_json FROM ledger_v2')]
assert any(e['event_type']=='nafe_violation' and e['task_id']=='alpha' for e in events)
""")
    def test_bridge_filters_before_limit_and_dimensions(self):
        self.run_code("""
import veritas_bridge as b
b.emit_event('CLAEG_TERMINAL_SHUTDOWN',{},source='wanted',task_id='alpha')
for _ in range(5):b.emit_event('NOISE',{},source='other',task_id='alpha')
assert len(b.get_recent_terminal_shutdowns(1,task_id='alpha'))==1
assert len(b.read_events(1,source='wanted',task_id='alpha'))==1
assert b.read_events(1,task_id='beta')==[]
assert b.TFIDF_DIM==len(b.tfidf_embed('example'))==512
try:b.tfidf_embed('example',dim=128)
except ValueError:pass
else:raise AssertionError('Legacy dimension silently accepted')
""")
    def test_source_manifest_tracks_data_and_ignores_generated_outputs(self):
        self.run_code("""
import tempfile,subprocess
from pathlib import Path
import omega_runtime as r
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    (root/'data').mkdir();(root/'data/input.txt').write_text('before')
    (root/'.gitignore').write_text('dist/' + chr(10))
    subprocess.run(['git','-C',str(root),'add','.'],check=True)
    old=r.source_identity(root)
    (root/'dist').mkdir();(root/'dist/artifact').write_text('generated')
    assert r.source_identity(root)==old
    (root/'data/input.txt').write_text('after')
    assert r.source_identity(root)!=old
    before=r.source_identity(root);(root/'new-input').write_text('new')
    assert r.source_identity(root)!=before
    subprocess.run(['git','-C',str(root),'add','-f','dist/artifact'],check=True)
    assert 'dist/artifact' in r.source_paths(root)
""")
