"""Synthetic loopback proof: prior409 is not global no-admission evidence."""
import sys,tempfile,threading,json,uuid,urllib.request,urllib.error,subprocess,hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path[:0]=['/workspace/Tuldok','/workspace/Tuldok/tests']
from app import Dataset,make_handler
from workbench import WorkbenchError
from fake_classification_model import start
root=Path('/workspace/Tuldok');out=Path(__file__).parent
source_start=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
with tempfile.TemporaryDirectory() as temporary:
 data=Dataset(temporary);model,url,requests=start();owner=data.text_classification_proposals
 row=data.workbench.import_asset(dict(kind='text',text='Synthetic delayed409 timing source',groups=['backend-dispatch-review']))
 body=dict(request_id=uuid.uuid4().hex,source_id=row['id'],revision=row['revision'],source_revision=row['source_revision'],server_url=url+'/v1/',model='classification-fixture',instruction='Exact frozen dispatch body',seed=7,labels=['Keep','keep'])
 denied,release=threading.Event(),threading.Event();original=owner.start;owner.closed=True
 def delayed_first(candidate):
  try:return original(candidate)
  except WorkbenchError as error:
   if error.status==409 and candidate['request_id']==body['request_id'] and not denied.is_set():
    denied.set();assert release.wait(4)
   raise
 owner.start=delayed_first
 http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(data));threading.Thread(target=http.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(http.server_port)+'/api/workbench/text-classification-proposals'
 def call(suffix='',payload=None):
  req=urllib.request.Request(base+suffix,data=json.dumps(payload).encode()if payload is not None else None,headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=5)as response:return response.status,json.load(response)
  except urllib.error.HTTPError as error:return error.code,json.load(error)
 first=[]
 thread=threading.Thread(target=lambda:first.append(call(payload=body)));thread.start()
 try:
  assert denied.wait(3);early=call('/'+body['request_id']);assert early[0]==404
  owner.closed=False;second=call(payload=body);assert second[0]==200 and second[1]['id']==body['request_id']
  persisted=call('/'+body['request_id']);assert persisted[0]==200
  release.set();thread.join(3);assert first[0][0]==409
  owner.worker.join(4);assert not owner.worker.is_alive();assert len(requests)==1
  completed=call('/'+body['request_id']);assert completed[1]['status']=='completed'
  # Admission lookup precedes current-source validation even after author changes source.
  data.workbench.save(row['id'],dict(row,annotation={'label':'Human draft'},review='draft'))
  replay=call(payload=body);assert replay[0]==200 and replay[1]==completed[1];assert len(requests)==1
  result={'early_GET':early,'second_explicit_POST':second,'first_delayed_POST_response':first[0],'persisted_before_first409':persisted,'completed':completed,'exact_replay_after_source_change':replay,'model_chat_requests':len(requests),'source_head_start':source_start,'source_head_end':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'backend_sha256':hashlib.sha256((root/'text_classification_proposals.py').read_bytes()).hexdigest(),'conclusion':'A pre-admission409 followed by exactGET404 does not prove that a concurrently or subsequently dispatched same-ID request cannot be admitted; matching200/GET proves one durable idempotent admission and late replay cannot repeat inference.'}
  (out/'backend409_timing_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['early_GET','second_explicit_POST','first_delayed_POST_response','persisted_before_first409','completed','exact_replay_after_source_change']},indent=2))
 finally:
  release.set();thread.join(3);http.shutdown();http.server_close();data.close();model.shutdown();model.server_close()
