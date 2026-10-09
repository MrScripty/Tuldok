"""Audit already-produced bounded classification browser artifacts; no inference."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[7]
sys.path.insert(0,str(ROOT))
from text_classification_proposals import SYSTEM_PROMPT, PROMPT_VERSION, payload
from workbench import encode

HEAD=sys.argv[2] if len(sys.argv)>2 else 'f95cd5c95189165534d21c204a227f4dd8145c92'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==HEAD
run=Path(sys.argv[1]).resolve()
assert ROOT in run.parents
session=json.loads((run/'session.json').read_text())
assert session['source_head']==HEAD
archive=run/'classification-reviewed.zip'
assert archive.stat().st_size<1024*1024
sha=lambda data:hashlib.sha256(data).hexdigest()
assert sha(archive.read_bytes())==session['downloaded_zip_sha256']
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    manifest=json.loads(z.read('manifest.json'))
    rows=[json.loads(line) for line in z.read('train/records.jsonl').splitlines()]
    assert len(rows)==1 and len(manifest['records'])==1
    row=rows[0];frozen=manifest['records'][0]
    assert row==frozen
    asset=z.read(row['asset'])
source='Please cancel the café meeting 😀.\nExact source.'
assert row['text']==source and asset==source.encode()
assert sha(asset)==row['asset_sha256']==row['content_hash']==row['source_sha256']
assert row['annotation']=={'label':'cancel'} and row['review']=='human_reviewed'
assert row['task']=='text_classification' and row['parents']==[] and row['groups']==['Cancel source']
assert row['provenance']=={'method':'import','normalization':'NFC; LF newlines','rights':'Authored synthetic fixture'}
evidence=row['target_proposal'];config=evidence['config']
assert evidence['job_id']==session['job_id']
assert evidence['applied_revision']==session['application_revision']
assert row['revision']==evidence['applied_revision']+1
assert evidence['source_revision']==row['source_revision']==1
fixed=next(value for value in session['fixed'] if value['id']==row['id'])
assert fixed['revision']==evidence['captured_revision']==1
assert fixed['revision']<row['revision'] and fixed['source_revision']==row['source_revision']
assert config['labels']==session['labels']==['cancel','keep','café 😀']
assert evidence['labels_sha256']==sha(encode(config['labels']).encode())
assert evidence['source_text_sha256']==evidence['source_sha256']==sha(source.encode())
assert config['instruction']=='Classify exact request' and config['seed']==42
assert config['model']==config['requested_model']=='classification-fixture'
assert config['provider']=='pumas_chat_compatible'
assert config['requested_server_url']==config['server_url']+'/v1/'
assert evidence['prompt_version']==PROMPT_VERSION
assert evidence['prompt_sha256']==sha(SYSTEM_PROMPT.encode())
wire=payload({'config':config,'source':{'text':source},'system_prompt':SYSTEM_PROMPT})
assert evidence['canonical_request_sha256']==sha(encode(wire).encode())
synthetic_output={'model':'classification-fixture','choices':[{'finish_reason':'stop','message':{'content':json.dumps({'label':'cancel'},ensure_ascii=True)}}]}
assert evidence['response_sha256']==sha(json.dumps(synthetic_output,ensure_ascii=False).encode())
assert evidence['verification']=='Exact label shape only; applied as draft, never approved.'
reload=json.loads((run/'reload-recovery-observation.json').read_text())
assert reload['expected_id']==session['persistent_recovery_id']
assert reload['restored_before_submit']==reload['restored_pending']==session['persistent_recovery_body']
assert reload['posted_bodies']==[] and reload['before_inference']==reload['after_inference']
early=json.loads((run/'early404-reload-observation.json').read_text())
assert early['real_exact_get_status']==404 and early['restored_via_visible_buttons']
assert early['body']['request_id']==session['early404_reload_id']
assert early['after_inference']==early['before_inference']+1
validation=json.loads((run/'native-validation-observation.json').read_text())
assert validation['url_code_points']==2072 and validation['accepted_guidance_code_points']==2000
for value in (validation['rejected_url'],validation['rejected_guidance']):
    assert value['pending'] is None and value['stored'] is None and value['blocked']=='' and value['recoveryId'] is None
assert validation['rejected_url']['posts']==0 and validation['rejected_guidance']['posts']==1
assert len(validation['explicit_posts'])==2 and validation['after_inference']==validation['before_inference']+2
assert validation['explicit_posts'][1]['instruction']=='g'*2000
fixture=(ROOT/'tests/browser_text_classification_proposals.cjs').read_text()
assert 'caption-proposal' not in fixture
assert 'j.status==="abstained"' in fixture and '"Apply as draft"' in fixture
assert "assert.equal(applied.review,'draft')" in fixture
assert "assert.equal(await evaluate('releasePreview.eligible'),false)" in fixture
print(json.dumps({'head':HEAD,'run':str(run.relative_to(ROOT)),'archive_sha256':sha(archive.read_bytes()),
    'record_id':row['id'],'job_id':evidence['job_id'],'source_sha256':sha(asset),
    'labels':config['labels'],'captured_revision':evidence['captured_revision'],'applied_draft_revision':evidence['applied_revision'],
    'reviewed_export_revision':row['revision'],'fixed_selection_revision':fixed['revision'],
    'exact_source_labels_prompt_provider_request_response_provenance_verified':True,
    'review_and_stale_export_assertions':'Archive revisions and passed native fixture assertions; abstention is asserted in the native fixture and has no exported target.',
    'reload_and_early404_observations_verified':True,'native_validation_observations_verified':True,
    'synthetic_fixture_only':True,'new_inference_calls':0},indent=2))
