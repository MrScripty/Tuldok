import sys,tempfile,uuid,json,hashlib,subprocess,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=['/workspace/Tuldok','/workspace/Tuldok/tests']
from app import Dataset
from fake_classification_model import start
from preferences import SELECTION_FIELDS
from workbench import WorkbenchError
root=Path('/workspace/Tuldok');out=Path(__file__).parent
paths=['app.py','workbench.py','preferences.py','dataset_releases.py','text_classification_proposals.py']
hashes=lambda:{p:hashlib.sha256((root/p).read_bytes()).hexdigest()for p in paths}
source_start=hashes();head_start=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
with tempfile.TemporaryDirectory()as temporary:
 d=Dataset(temporary);model,url,requests=start();w,p,r,owner=d.workbench,d.workbench.preferences,d.releases,d.text_classification_proposals
 try:
  row=w.import_asset(dict(kind='text',text='Independent synthetic prompt for classification and comparative judgment.',groups=['independent-cross-feature'],rights='Authored bounded fixture'))
  def answer(text):return w.save_response(dict(id=uuid.uuid4().hex,revision=0,prompt_id=row['id'],parent_revision=row['revision'],source_revision=row['source_revision'],completion=text,review='draft'))['response']
  left,right=answer(' Exact left answer 😀\r\n'),answer('Exact right answer')
  judgment_body=dict(id=uuid.uuid4().hex,revision=0,prompt_id=row['id'],parent_revision=row['revision'],source_revision=row['source_revision'],left_id=left['id'],left_revision=left['revision'],right_id=right['id'],right_revision=right['revision'],outcome='left',rationale='Independent explicit human comparison',review='human_reviewed')
  judgment=p.save(judgment_body)['judgment'];assert w.get(row['id'])==row
  request=dict(format='text_preference_v1',items=[{key:judgment[key]for key in SELECTION_FIELDS}],ratios=dict(train=100,validation=0,test=0),seed=42)
  preview=r.preview(request);assert preview['eligible'],preview
  release=r.create(dict(request,preview_token=preview['preview_token']));archive=r.get(release['id']);frozen_bytes=archive.read_bytes();frozen_hash=hashlib.sha256(frozen_bytes).hexdigest()
  with zipfile.ZipFile(archive)as z:
   manifest=json.loads(z.read('manifest.json'));assert manifest['judgments']==[judgment] and manifest['prompts']==[row]
  config=dict(request_id=uuid.uuid4().hex,source_id=row['id'],revision=row['revision'],source_revision=row['source_revision'],server_url=url,model='classification-fixture',instruction='Frozen exact classification',seed=42,labels=['cancel','keep'])
  job=owner.start(config);owner.worker.join(5);assert not owner.worker.is_alive();job=owner.get(job['id']);assert job['status']=='completed',job
  preference_history=p.history(judgment['id']);answer_history={a['id']:w.response_history(a['id'])for a in [left,right]};origin=w.get(row['id'])['provenance']
  apply=dict(revision=job['revision'],decision='apply_draft',labels=config['labels'])
  with patch.object(owner,'_save',side_effect=RuntimeError('Independent atomic rollback fixture')):
   try:owner.decide(job['id'],apply);raise AssertionError('Expected rollback')
   except RuntimeError as error:assert str(error)=='Independent atomic rollback fixture'
  assert w.get(row['id'])==row and owner.get(job['id'])==job
  assert p.history(judgment['id'])==preference_history and r.preview(request)['eligible']
  result=owner.decide(job['id'],apply);applied=result['record'];assert applied['review']=='draft' and applied['revision']==row['revision']+1
  assert applied['provenance']==origin and applied['source_revision']==row['source_revision'] and applied['source_sha256']==row['source_sha256']
  listed=p.list(row['id']);assert listed['judgments'][0]['stale_warning'] and p._get(judgment['id'])==judgment
  assert p.history(judgment['id'])==preference_history
  assert all(w._response(a['id'])==a and w.response_history(a['id'])==answer_history[a['id']] for a in [left,right])
  stale=r.preview(request);assert not stale['eligible'] and any(x['status']==409 for x in stale['blockers'])
  try:r.create(dict(request,preview_token=preview['preview_token']));raise AssertionError('Old proof must fail')
  except WorkbenchError as error:assert error.status==409
  try:p.save(dict(judgment_body,revision=judgment['revision']));raise AssertionError('Old parent binding must fail')
  except WorkbenchError as error:assert error.status==409
  assert archive.read_bytes()==frozen_bytes and hashlib.sha256(archive.read_bytes()).hexdigest()==frozen_hash
  replay=owner.start(config);assert replay==result['job'] and len(requests)==1
  duplicate=owner.decide(job['id'],apply);assert duplicate['changed']is False and duplicate['record']==applied
  rebound=p.save(dict(judgment_body,revision=judgment['revision'],parent_revision=applied['revision']))['judgment'];assert rebound['revision']==2 and rebound['review']=='human_reviewed'
  current_request=dict(request,items=[{key:rebound[key]for key in SELECTION_FIELDS}]);fresh=r.preview(current_request);assert fresh['eligible'] and fresh['preview_token']!=preview['preview_token']
  assert applied['review']=='draft' and w.get(row['id'])==applied
  new_release=r.create(dict(current_request,preview_token=fresh['preview_token']));assert new_release['id']!=release['id']
  receipt={'source_head_start':head_start,'source_head_end':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'runtime_hashes_start':source_start,'runtime_hashes_end':hashes(),'checks':['judgment/answers do not change parent or invalidate frozen classification admission','independent reviewed preference release can use an unannotated draft parent','classification Apply rollback preserves source/job/preferences/answers and preview','draft-only Apply increments parent revision and preserves source/acquisition provenance','existing judgment and history remain immutable but list marks stale','old preference selection/preview proof/save reject409 after Apply','prior frozen release bytes unchanged','exact classification admission replay and duplicate Apply idempotent with one synthetic inference','explicit current-parent rejudgment creates revision2 and new eligible preference proof/archive without reviewing classification'],'old_release_sha256':frozen_hash,'old_release_id':release['id'],'new_release_id':new_release['id'],'stale_preference_blockers':stale['blockers'],'synthetic_model_requests':len(requests),'findings':[]}
  assert receipt['runtime_hashes_start']==receipt['runtime_hashes_end']
  (out/'classification_preference_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'checks':len(receipt['checks']),'synthetic_model_requests':len(requests),'source_head_start':head_start,'source_head_end':receipt['source_head_end'],'runtime_unchanged':True,'findings':[]},indent=2))
 finally:d.close();model.shutdown();model.server_close()
