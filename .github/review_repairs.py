"""One-shot, assertion-checked repair recipe; executed only on the review branch."""
import ast
import json
import os
from pathlib import Path

changed = []
def save(name, text):
    Path(name).parent.mkdir(parents=True, exist_ok=True)
    Path(name).write_text(text, encoding='utf-8', newline='\n')
    changed.append(name)

def replace(text, before, after, count=1):
    assert text.count(before) == count, (before[:100], text.count(before), count)
    return text.replace(before, after)

p = Path('pyproject.toml').read_text(encoding='utf-8')
p = replace(p, 'py-modules = ["omega_brain_mcp_standalone", "veritas_build_gates"]', 'py-modules = ["omega_brain_mcp_standalone", "veritas_build_gates", "omega_runtime", "veritas_bridge"]')
save('pyproject.toml', p)
p = Path('Dockerfile').read_text(encoding='utf-8')
p = replace(p, 'COPY veritas_build_gates.py .', 'COPY veritas_build_gates.py omega_runtime.py veritas_bridge.py .')
p = replace(p, 'WORKDIR /app', 'WORKDIR /app\nRUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*')
save('Dockerfile', p)

p = Path('omega_runtime.py').read_text(encoding='utf-8')
start = p.index('def source_identity(root):')
p = p[:start] + '''def source_paths(root):
    """Tracked and nonignored inputs; tracked files always override exclusions.

    Non-Git folders use a conservative filesystem snapshot. Symlinks and
    submodules require an explicit packaged snapshot, rather than partial hashes.
    """
    import subprocess
    root = Path(root).resolve(strict=True)
    excluded = {'.git', 'node_modules', '.venv', '__pycache__', '.sswp.json'}
    def git_files(mode):
        command = ['git', '-C', str(root), 'ls-files', mode, '-z']
        if mode == '--others': command.append('--exclude-standard')
        command.append('--')
        try:
            result = subprocess.run(command, capture_output=True, timeout=10,
                                    env=dict(os.environ, LC_ALL='C'))
        except FileNotFoundError:
            return None
        if result.returncode:
            if b'not a git repository' in result.stderr.lower(): return None
            raise ValueError('Cannot enumerate source inputs: ' + result.stderr.decode('utf-8', 'replace'))
        return {name for name in result.stdout.decode('utf-8').split('\\0') if name}
    tracked = git_files('--cached')
    if tracked is not None:
        other = git_files('--others')
        if other is None: raise ValueError('Git source enumeration became unavailable')
        candidates = tracked | {f for f in other if not (set(Path(f).parts) & excluded)}
    else:
        candidates = set()
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in excluded)
            for name in dirs + files:
                if name in excluded: continue
                path = Path(folder) / name
                if path.is_symlink(): raise ValueError('Source symlinks require an explicit packaged source snapshot')
                if path.is_file(): candidates.add(path.relative_to(root).as_posix())
    result = []
    for name in sorted(candidates):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Source path escapes the approved root')
        path = root
        for part in relative.parts:
            path = path / part
            if path.is_symlink(): raise ValueError('Source symlinks require an explicit packaged source snapshot')
        if path.is_file(): result.append(relative.as_posix())
        elif path.is_dir(): raise ValueError('Tracked directories/submodules require an explicit packaged source snapshot')
        elif path.exists(): raise ValueError('Unsupported source file type')
    return result

def source_identity(root):
    """Hash exact source inputs, including tracked data; ignore generated state."""
    root = Path(root).resolve(strict=True)
    digest = hashlib.sha256()
    for name in source_paths(root):
        sha = hashlib.sha256((root / name).read_bytes()).hexdigest()
        digest.update((name + '\\0' + sha + '\\n').encode())
    return digest.hexdigest()
'''
save('omega_runtime.py', p)

p = Path('veritas_bridge.py').read_text(encoding='utf-8')
a = p.index('def read_events(')
b = p.index('\ndef get_recent_terminal_shutdowns', a)
p = p[:a] + '''def read_events(limit=20,event_type=None,source=None,task_id=None):
    if not task_id: return []
    predicates, params = ['task_id=?'], [task_id]
    if event_type is not None:
        predicates.append('event_type=?'); params.append(event_type)
    if source is not None:
        predicates.append("json_extract(payload,'$.source')=?"); params.append(source)
    params.append(max(1, min(int(limit), 100)))
    with closing(runtime.bus()) as db:
        rows = db.execute('SELECT * FROM events WHERE ' + ' AND '.join(predicates)
                          + ' ORDER BY created_at DESC,id DESC LIMIT ?', params).fetchall()
    return [dict(r, payload=json.loads(r['payload']), timestamp=r['created_at']) for r in rows]
''' + p[b:]
p = replace(p, 'TFIDF_DIM = 128  # single source of truth for embedding dimension', 'TFIDF_DIM = 512  # hash-lexical-v2-512; legacy 128-dimensional vectors must be rebuilt')
p = replace(p, "    return re.findall(r'[a-zA-Z]{3,}', text.lower())", '    return runtime.tokens(text)')
p = replace(p, 'def tfidf_embed(text,dim=512):\n    return runtime.embed(text)', "def tfidf_embed(text,dim=TFIDF_DIM):\n    if dim != TFIDF_DIM:\n        raise ValueError('Only 512-dimensional v2 embeddings are supported; rebuild legacy vectors')\n    return runtime.embed(text)")
save('veritas_bridge.py', p)

p = Path('omega_brain_mcp_standalone.py').read_text(encoding='utf-8')
p = replace(p, '_seal_event("nafe_violation", {"flags": result["flags"][:5]})', '_seal_event("nafe_violation", {"task_id": task_id, "flags": result["flags"][:5]})')
p = replace(p, 'description="SHA-256 verified cross-session handoff file."', 'description="Scope instructions; read omega://task/{task_id}/handoff for a task-specific handoff."')
p = replace(p, '''        elif uri == "omega://session/handoff":
            h = _read_handoff()
            return json.dumps(h if h else {"handoff_present": False})''', '''        elif uri == "omega://session/handoff":
            return json.dumps({"status": "SCOPE_REQUIRED", "uri_template": "omega://task/{task_id}/handoff"})
        elif re.fullmatch(r"omega://task/[^/]+/handoff", uri):
            from urllib.parse import unquote
            task_id = unquote(uri[len("omega://task/"):-len("/handoff")])
            if not task_id.strip(): raise ValueError("task_id is required")
            h = _read_handoff(task_id)
            return json.dumps({"task_id": task_id, "handoff_present": h is not None, "handoff": h})''')
p = replace(p, '''    async def list_resource_templates():
        return [''', '''    async def list_resource_templates():
        return [
            ResourceTemplate(uriTemplate="omega://task/{task_id}/handoff",
                             name="Task Handoff", description="Read only the named task's verified handoff.",
                             mimeType="application/json"),''')
p = replace(p, 'arguments=[PromptArgument(name="task", description="One line: what are you working on?", required=False)]),', 'arguments=[PromptArgument(name="task_id", description="Stable task identifier", required=True),\n                              PromptArgument(name="task", description="One line: what are you working on?", required=False)]),')
p = replace(p, 'PromptArgument(name="note", description="Optional one-line note appended to auto-summary", required=False)', 'PromptArgument(name="task_id", description="Stable task identifier", required=True),\n                       PromptArgument(name="note", description="Optional one-line note appended to auto-summary", required=False)')
p = replace(p, 'PromptArgument(name="task", description="What was being worked on", required=False),', 'PromptArgument(name="task_id", description="Stable task identifier", required=True),\n                       PromptArgument(name="task", description="What was being worked on", required=False),')
p = replace(p, '"No fields required. Zero typing."', '"Requires the stable task_id; other fields are optional."')
node = next(n for n in ast.walk(ast.parse(p)) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'get_prompt')
lines = p.splitlines(keepends=True)
block = ''.join(lines[node.lineno-1:node.end_lineno])
block = replace(block, '        arguments = arguments or {}', '''        arguments = arguments or {}
        task_id = arguments.get("task_id")
        if name in {"omega_task_start", "omega_seal_task", "omega_write_handoff"}:
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("task_id is required for task-scoped prompts")''')
block = replace(block, 'preload = _brain_preload(task)', 'preload = _brain_preload(task, task_id)')
block = replace(block, 'rag_count = len(preload.get("rag_fragments", []))\n            veritas = preload.get("veritas_score", 0.0)', 'rag_count = len(preload.get("rag", {}).get("fragments", []))')
block = replace(block, 'RAG: {rag_count} fragments | VERITAS {veritas:.2f}', 'RAG: {rag_count} task-scoped fragments (lexical relevance)', 3)
block = block.replace('_SESSION_ID', 'task_id')
block = replace(block, '            _STARTUP_PRELOAD["last_session_handoff"] = record\n            _STARTUP_PRELOAD["handoff_present"] = True\n', '', 2)
lines[node.lineno-1:node.end_lineno] = [block]
p = ''.join(lines)
ast.parse(p)
save('omega_brain_mcp_standalone.py', p)

save('tests/test_review_regressions.py', '''import os, subprocess, sys, tempfile, unittest
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
    (root/'.gitignore').write_text('dist/\\n')
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
''')

save('docs/REVIEW_FOLLOWUP_2026-09-07.md', '''# September 7 review follow-up

Repairs cover the installed package and Docker dependency closure; explicitly task-scoped start/seal/handoff prompts and handoff resources; NAFE task attribution; event filtering before limits; and the public 512-dimensional representation contract.

Source receipts now include all tracked files (including data directories and tracked ignored files) plus nonignored, non-runtime untracked inputs. Git-ignored generated outputs do not invalidate the source-change gate. Non-Git folders use a conservative filesystem snapshot. Symlinks and submodules require an explicit packaged source snapshot. Python and Node must use this same source-selection contract.

Regression commands: `python -m pytest tests/ -v`; install the package and import it outside the checkout; build the Docker image and import its complete runtime as the non-root image user. These changes do not authenticate a remote caller, sandbox an administrator, or certify historical records. Live databases and recovery archives are not modified by this repository repair.
''')
Path(os.environ['RUNNER_TEMP'], 'review-files.json').write_text(json.dumps(changed), encoding='utf-8')
