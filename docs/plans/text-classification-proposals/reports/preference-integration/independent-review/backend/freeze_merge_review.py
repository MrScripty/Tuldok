from pathlib import Path
import hashlib,json,subprocess
root=Path('/workspace/Tuldok');out=Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
git=lambda *args:subprocess.check_output(['git',*args],cwd=root,text=True).strip()
head=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}');assert head=='c0de883159025491d5283c52514c7c762f53c4cc' and tree=='ab990b09085cc26d057cbe8d13746f1ea3913086'
parents=git('show','-s','--format=%P','HEAD').split();assert parents==['7ec7e47a090467fa37b68d33a7e81438828eea9d','321f710a9b185bf6e9eac518579c083079a6d751']
manifest=json.loads((out/'artifact_manifest_merge_preliminary.json').read_text());assert len(manifest['files'])==11
for p,h in manifest['files'].items():assert sha(out/p)==h,p
prior=json.loads((out/'review_merge_preliminary.json').read_text());probe=json.loads((out/'classification_preference_receipt.json').read_text());assert len(probe['checks'])==9 and probe['synthetic_model_requests']==1 and probe['runtime_hashes_start']==probe['runtime_hashes_end']
for p,h in prior['runtime_hashes'].items():assert sha(root/p)==h,p
paths=list(prior['runtime_hashes'])+['caption_proposals.py','static/workbench.js','static/text-classification-proposals.js','static/preferences.js','scripts/qualify_text_classification_local.py']
for ref,files in [(parents[0],['text_classification_proposals.py','caption_proposals.py']),(parents[1],['preferences.py','dataset_releases.py'])]:
 for p in files:assert subprocess.check_output(['git','show',ref+':'+p],cwd=root)==(root/p).read_bytes(),p
assert not git('diff','--name-only')
receipt={'source_head':head,'source_tree':tree,'parents':parents,'runtime_sha256':{p:sha(root/p)for p in paths},'backend_runtime_matches_preliminary':True,'prior11_review_files_unchanged':True,'cross_feature_checks':probe['checks'],'cross_feature_probe_receipt_sha256':sha(out/'classification_preference_receipt.json'),'cross_feature_probe_scope':'Executed in-progress merge; all five backend runtime bytes proven identical to exact frozen merge. No redundant rerun needed.','findings':[],'limitations':['Reviewed preference evidence remains independently human-reviewed but stale after classification Apply; authors must deliberately rejudge current parent revisions before a new preference export. Classification stays draft.','Opaque/foreign/orphan classification admission metadata remains preserved and blocked under the inherited reviewed recovery contract.','Aggregate50 qualification is still running; this scoped signoff does not claim its final result.'],'source_head_end':git('rev-parse','HEAD'),'source_diff_empty':not git('diff','--name-only'),'no_source_or_public_writes':True}
assert receipt['source_head_end']==head and receipt['source_diff_empty']
(out/'receipt_c0de883.json').write_text(json.dumps(receipt,indent=2)+'\n')
(out/'review_c0de883.md').write_text('''Independent backend/composition review approves exact normal merge `c0de883159025491d5283c52514c7c762f53c4cc`, tree `ab990b09085cc26d057cbe8d13746f1ea3913086`, with both authorized parents `7ec7e47a090467fa37b68d33a7e81438828eea9d` and `321f710a9b185bf6e9eac518579c083079a6d751`. No remaining scoped findings.

All five shared/backend runtime files match the preliminary reviewed/probed bytes exactly; classification/caption runtime matches PR18 and preference/release runtime matches development. The nine cross-feature checks with one synthetic provider request therefore apply to this exact backend merge. They prove atomic rollback, draft-only classification Apply, unchanged acquisition provenance and preference/answer history, stale preference bindings, rejection of old export proofs, immutable prior archive, idempotent admission/Apply, and deliberate rejudgment restoring preference eligibility without reviewing the classification. No redundant unchanged-runtime test rerun was needed.

Frontend composition includes preference edits in the shared unsaved/ownership epochs and invalidates preference preview on successful or uncertain classification Apply. Existing source/label/config admission evidence and durable recovery logic remain inherited. UI races are independently owned by the interaction reviewer. All11 earlier scratch review artifacts remain unchanged. Aggregate50 qualification is running separately and is not claimed here. No source edits, real inference/downloads, credential changes or public writes were performed.
''')
files=['freeze_merge_review.py','receipt_c0de883.json','review_c0de883.md']
(out/'artifact_manifest_c0de883.json').write_text(json.dumps({'source_head':head,'preliminary_manifest_sha256':sha(out/'artifact_manifest_merge_preliminary.json'),'prior11_unchanged':True,'files':{p:sha(out/p)for p in files}},indent=2)+'\n')
print(json.dumps({'source_head':head,'source_tree':tree,'backend_runtime_matches_preliminary':True,'prior11_unchanged':True,'findings':[]},indent=2))
