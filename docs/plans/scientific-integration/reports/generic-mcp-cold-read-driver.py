import asyncio, hashlib, importlib.util, json, os
from pathlib import Path
import re, subprocess, sys, tempfile, time
root=Path('/workspace/Tuldok-generic-mcp')
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
import qualify_scientific_restore as restore
import qualify_agent_scientific as agent
catalog=Path('/workspace/scratch/tuldok-cpu-qualification/restored-catalog-20261013')
report=Path('/tmp/tuldok-generic-mcp-cold-read-20261014');report.mkdir(exist_ok=False)
marker=next(catalog.glob('.restore-receipt-*.json')).name
connection=os.environ['TULDOK_RESTORE_DATABASE_URL']
assert os.environ['TULDOK_DATABASE_URL']==connection
def actors():
 metadata=restore.Metadata(catalog,dsn=connection,create=False,schema_version=None)
 try:
  with metadata.lock,metadata.transaction():
   return {row[0]:list(row) for row in metadata.connection.execute('SELECT id,kind,label,created_at FROM access_actors ORDER BY id').fetchall()}
 finally: metadata.close()
start=time.monotonic(); before=restore.snapshot(catalog,connection,exclude=(marker,)); before_actors=actors()
app_python='/workspace/Tuldok/.venv/bin/python'
args=type('Args',(),{'evidence':Path('/workspace/Tuldok-p5c/build/qa/workspace-rheon-evaluation/run-hWVrH7'),'project':Path('/workspace/scratch/tuldok-cpu-qualification/evaluation-project')})()
credential=cookie=endpoint=None
with tempfile.TemporaryDirectory(prefix='tuldok-generic-mcp-private-') as private:
 private=Path(private)
 with (report/'app.log').open('w+') as log:
  server=subprocess.Popen([app_python,'-u','app.py','--data',str(catalog),'--port','0','--project-root','sample='+str(args.project)],cwd=root,stdout=log,stderr=subprocess.STDOUT)
  try:
   deadline=time.monotonic()+60
   while time.monotonic()<deadline:
    log.flush(); match=re.search(r'127\.0\.0\.1:(\d+)',(report/'app.log').read_text())
    if match: endpoint='http://127.0.0.1:'+match[1];break
    assert server.poll() is None,'Application exited before readiness';time.sleep(.1)
   assert endpoint,'Readiness timeout'
   login=private/'owner-login'
   subprocess.run([app_python,'access.py','login','--data',str(catalog),'--out',str(login)],cwd=root,check=True,capture_output=True)
   owner,headers=agent.http(endpoint,'/api/access/session',body={'token':login.read_text().strip()});login.unlink()
   cookie=headers['Set-Cookie'].split(';')[0]
   credential,_=agent.http(endpoint,'/api/access/credentials',cookie,{'label':'Generic MCP retained-result read-only QA','scopes':['inspect'],'ttl_seconds':3600})
   token_file,config=private/'agent-token',private/'config.json'
   agent.private_file(token_file,(credential['token']+'\n').encode())
   agent.private_file(config,json.dumps({'endpoint':endpoint,'catalog_id':owner['catalog_id'],'token_file':str(token_file),'timeout':120}).encode())
   result=asyncio.run(agent.qualify(args,endpoint,credential,config,report))
   agent.http(endpoint,'/api/access/credentials/'+credential['identity']['credential_id']+'/revoke',cookie,{})
   credential=None;result['inspect_credential_revoked']=True
   agent.http(endpoint,'/api/access/logout',cookie,{})
   cookie=None;result['qa_owner_logged_out']=True
  finally:
   try:
    if credential is not None: agent.http(endpoint,'/api/access/credentials/'+credential['identity']['credential_id']+'/revoke',cookie,{})
    if cookie is not None: agent.http(endpoint,'/api/access/logout',cookie,{})
   finally:
    server.terminate()
    try: server.wait(timeout=15)
    except subprocess.TimeoutExpired: server.kill();server.wait(timeout=5)
after=restore.snapshot(catalog,connection,exclude=(marker,))
for key in ('dataset_id','schema_version','schema_sha256','sequences','files','modes','custody','run_states','runtime_manifests'):
 assert before[key]==after[key],key
changed=[name for name in before['tables'] if before['tables'][name]!=after['tables'][name]]
assert set(changed)== {'access_actors','access_audit','access_credentials'}, changed
after_actors=actors()
assert all(after_actors.get(key)==row for key,row in before_actors.items()),'Existing actor rows changed'
assert set(after_actors)-set(before_actors)=={result['actor_id']},'Unexpected new actor'
assert after_actors[result['actor_id']][1:3]==['agent','Generic MCP retained-result read-only QA'], 'Unexpected actor authority'
metadata=restore.Metadata(catalog,dsn=connection,create=False,schema_version=None)
try:
 with metadata.lock,metadata.transaction():
  credentials=metadata.connection.execute('SELECT revoked FROM access_credentials WHERE actor_id=%s',(result['actor_id'],)).fetchall()
  assert credentials and all(row[0]==1 for row in credentials),'QA agent credential still active'
finally: metadata.close()
result['existing_actor_rows_unchanged']=True
result['new_actor_is_exact_explicit_qa_agent']=True
result.update({'status':'passed','scope':'Generic MCP component; actual retained scientific transport/custody only, not new model acceptance. Current before/after state, not original pre-auth parity.','files_modes_runs_identity_sequences_unchanged':True,'changed_tables':changed,'elapsed_seconds':time.monotonic()-start,'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()),'source_hashes':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('agent_api.py','mcp_stdio.py','app.py','runs.py','tests/qualify_agent_scientific.py','requirements-agent.lock')},'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
(report/'receipt.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
print(json.dumps({'status':result['status'],'calls':len(result['calls']),'transferred_artifacts':[{'name':a['name'],'bytes':a['bytes'],'sha256':a['sha256'],'segments':len(a['segments'])} for a in result['transferred_artifacts']],'changed_tables':changed,'unchanged':True,'qa_credentials_revoked':True,'receipt_sha256':hashlib.sha256((report/'receipt.json').read_bytes()).hexdigest(),'elapsed_seconds':result['elapsed_seconds']}))
