"""Isolated real stdio MCP regression: same protocol and bundles used by Codex."""
import subprocess,os,json,queue,threading,tempfile,pathlib,sys,time,sqlite3,secrets
ROOT=pathlib.Path(os.environ.get('OMEGA_SUITE_ROOT',str(pathlib.Path(__file__).resolve().parents[1])))
NODE=pathlib.Path(os.environ.get('OMEGA_NODE',__import__('shutil').which('node') or 'node'))
class Client:
 def __init__(self,cmd,env):
  self.q=queue.Queue();self.errors=[];self.n=0
  self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',text=True,env=env,cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  def reader():
   for line in self.p.stdout:self.q.put(json.loads(line))
  threading.Thread(target=reader,daemon=True).start();threading.Thread(target=lambda:self.errors.extend(self.p.stderr.readlines()),daemon=True).start()
  self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'omega-regression','version':'2'}})
  self.p.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');self.p.stdin.flush()
 def request(self,method,params):
  self.n+=1;self.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.n,'method':method,'params':params})+'\n');self.p.stdin.flush()
  until=time.monotonic()+60
  while time.monotonic()<until:
   r=self.q.get(timeout=max(.1,until-time.monotonic()))
   if r.get('id')==self.n:
    if 'error' in r:raise RuntimeError(r['error'])
    return r['result']
  raise TimeoutError('MCP request timed out')
 def call(self,name,args,allow_error=False):
  r=self.request('tools/call',{'name':name,'arguments':args})
  if not allow_error and r.get('isError'):raise AssertionError(r)
  return r
 def close(self):
  self.p.terminate();self.p.wait(10)
  self.p.stdin.close();self.p.stdout.close();self.p.stderr.close()
def content(r):return json.loads(r['content'][0]['text'])
def run():
 with tempfile.TemporaryDirectory() as td:
  base=pathlib.Path(td);shared=base/'shared';shared.mkdir();repo=base/'repo';repo.mkdir();(repo/'input.txt').write_text('source fixture')
  (shared/'operator-policy.json').write_text(json.dumps({'witness_roots':[repo.as_posix()],'projects':{}}));(shared/'approval.key').write_bytes(secrets.token_bytes(32))
  env=dict(os.environ,PYTHONUTF8='1',OMEGA_BRAIN_DATA_DIR=str(base/'brain'),OMEGA_STENOGRAPHER_DIR=str(base/'steno'),VERITAS_SHARED_DIR=str(shared),SSWP_DB=str(base/'sswp.sqlite'),OMEGA_CODEX_SESSIONS=str(base/'sessions'))
  clients=[]
  try:
   brain=Client([sys.executable,str(ROOT/'omega-brain/omega_brain_mcp_standalone.py')],env);clients.append(brain)
   steno=Client([sys.executable,str(ROOT/'omega-stenographer/codex_capture.py')],env);clients.append(steno)
   sswp=Client([str(NODE),str(ROOT/'sswp/dist/sswp.cjs')],env);clients.append(sswp)
   counts=[len(c.request('tools/list',{})['tools']) for c in clients];assert counts==[30,6,9],counts
   assert brain.call('omega_ingest',{'content':'unscoped'},True)['isError']
   assert steno.call('stenographer_get_brief',{},True)['isError']
   assert sswp.call('sswp_witness',{'repoPath':repo.as_posix(),'task_id':'flow','approval':{}},True)['isError']
   approval=content(brain.call('omega_authorize_action',{'tool':'sswp_witness','args':{'repoPath':repo.as_posix()},'task_id':'flow'}))
   result=content(sswp.call('sswp_witness',{'repoPath':repo.as_posix(),'task_id':'flow','approval':approval}))
   assert result['attestation']['taskId']=='flow'
   assert (repo/'.sswp.json').exists()
   assert content(sswp.call('sswp_verify',{'filePath':str(repo/'.sswp.json')}))['verified']
   assert sswp.call('sswp_witness',{'repoPath':repo.as_posix(),'task_id':'flow','approval':approval},True)['isError']
   steno.call('stenographer_ingest_exchange',{'role':'user','content':'Decided to keep interoperablefixture memory.','session_id':'flow'})
   until=time.monotonic()+25;found=False
   while time.monotonic()<until:
    r=content(brain.call('omega_rag_query',{'query':'interoperablefixture','task_id':'flow'}))
    if r['fragments']:found=True;break
    time.sleep(.5)
   assert found,'Steno event was not delivered automatically'
   attestations=content(brain.call('omega_rag_query',{'query':'SSWP_ATTESTATION','task_id':'flow'}))
   assert attestations['fragments'],'SSWP outbox was not ingested by Brain'
   assert not content(brain.call('omega_rag_query',{'query':'interoperablefixture','task_id':'different'}))['fragments']
   assert content(brain.call('omega_integrity_status',{}))['valid']
   for c in (brain,steno):
    resources=c.request('resources/list',{})['resources'];uri=resources[0]['uri'];assert c.request('resources/read',{'uri':uri})['contents']
   print(json.dumps({'result':'PASS','tool_counts':counts,'verified':['protocol schemas and true MCP errors','Brain receipt to SSWP witness','one-use receipt replay rejection','nested attestation verification','automatic SSWP and Steno delivery to Brain','task isolation','resource reads','v2 ledger integrity']}))
  finally:
   for c in reversed(clients):c.close()
if __name__=='__main__':run()
