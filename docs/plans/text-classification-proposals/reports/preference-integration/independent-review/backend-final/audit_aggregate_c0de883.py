from pathlib import Path
import json,hashlib,subprocess,re
root=Path('/workspace/Tuldok');out=Path(__file__).parent;prior=out.parent/'review-backend';q=root/'docs/plans/text-classification-proposals/reports/preference-integration/qualification'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
head=git('rev-parse','HEAD');assert head=='c0de883159025491d5283c52514c7c762f53c4cc';assert git('rev-parse','HEAD^{tree}')=='ab990b09085cc26d057cbe8d13746f1ea3913086';assert not git('diff','--name-only')
for filename in ['artifact_manifest_merge_preliminary.json','artifact_manifest_c0de883.json']:
 m=json.loads((prior/filename).read_text())
 for p,h in m['files'].items():assert sha(prior/p)==h,p
s=json.loads((q/'gates/summary.json').read_text());r=json.loads((q/'gates/results.json').read_text());assert len(r)==len({e['command']for e in r})==s['passed']==s['gate_count']==s['registered_workflow_gate_count']==s['qualified_passing_gates']==50
assert s['failed']==s['blocked']==0 and s['stale_passed_gates']==[] and s['source_head']==head and s['source_tree']==git('rev-parse','HEAD^{tree}')
workflow=(root/'.github/workflows/tests.yml').read_text();commands=re.findall(r'^\s+- run: ((?:node |python -m unittest ).*)$',workflow,re.M);assert len(commands)==50 and set(commands)=={e['command']for e in r}
snap=s['source_snapshot'];assert snap['head']==head and len(snap['files'])==127
for p,h in snap['files'].items():assert sha(root/p)==h,p
assert snap['sha256']=='ad8177a0993b8366ceed17b21b38084d7944efc041f015ed3aafc68f3e3b1b49'==hashlib.sha256(json.dumps(snap['files'],sort_keys=True).encode()).hexdigest()
logs={};artifacts={}
for e in r:
 assert e['status']=='passed' and e['exit_code']==0 and e['source_stable_during_gate'] and e['historical_report_hashes_preserved']
 assert e['source_head_start']==e['source_head_end']==head
 assert e['source_sha256_start']==e['source_sha256_end']==snap['sha256']
 logs[e['log']]=sha(root/e['log']);assert set(e['component_artifacts'])==set(e['component_artifact_sha256'])
 for p,h in e['component_artifact_sha256'].items():assert sha(root/p)==h,p;artifacts[p]=h
assert len(logs)==50 and len(artifacts)==92
base=json.loads((q/'preservation-baseline.json').read_text());assert len(base['report_sha256'])==base['all_prior_report_file_count']==3339
for p,h in base['report_sha256'].items():assert sha(root/p)==h,p
assert len(s['historical_reports'])==s['historical_report_files_preserved']==3331
for p,h in s['historical_reports'].items():assert sha(root/p)==h,p
markers={
 'python -m unittest discover -s tests':['Ran 285 tests','OK'],
 'node tests/test_caption_proposals_controller.cjs':['Caption reload: durable before POST','Static admission parity: 86 cases'],
 'node tests/test_text_classification_proposals_controller.cjs':['six delayed initial400/409/422 overlap','ten malformed raw-bound counters recover'],
 'node tests/test_preferences_controller.cjs':['every parent-adopter ownership interleaving','dirty-draft preservation'],
 'node tests/browser_preferences.cjs':['immutable actual download and pinned DPO preparation/collator'],
 'node tests/browser_classification_preferences_integration.cjs':['Classification/preferences native combined proof, ownership, dirty gates and recovery passed.']}
for cmd,needles in markers.items():
 e=next(x for x in r if x['command']==cmd);text=(root/e['log']).read_text();assert all(n in text for n in needles),cmd
native=next(x for x in r if x['command']=='node tests/browser_classification_preferences_integration.cjs');path=next(p for p in native['component_artifacts']if p.endswith('session.json'));session=json.loads((root/path).read_text())
assert session['source_head']==head and session['result']=='PASS' and session['synthetic_only'] and not session['negative_apply_hook']
for p,h in session['source_sha256'].items():assert snap['files'][p]==h
steps={e['name']:e for e in session['steps']};assert len(steps)==5
for name in ['Immediate preference proof invalidation success','Immediate preference proof invalidation uncertain']:
 step=steps[name];assert step['state']['preview'] is None and step['state']['freeze_disabled'] and step['state']['items']==step['fixed']
step=steps['Held classification Apply retains later judgment draft'];assert step['retained']['dirty'] and step['retained']['review']=='draft' and step['retained']['editor']['id']==step['opened']['editor']['id'] and step['retained']['epoch']==step['opened']['epoch']
step=steps['Classification Reject preserves unrelated judgment save owner'];assert step['state']['dirty'] and step['state']['review']=='draft' and step['state']['editor']['revision']==2
step=steps['Recovery unchanged across actual answer and judgment saves'];assert step['early_exact_get_status']==404 and step['answer_revision']==step['judgment_revision']==2 and step['after_inference']-step['before_inference']==1
qual=q/'qualification-and-preservation.json'
if qual.exists():
 receipt=json.loads(qual.read_text());assert receipt['source_head']==head and receipt['source_snapshot_sha256']==snap['sha256'] and receipt['qualified_passing_gates']==50
else:receipt=None
result={'source_head':head,'source_tree':s['source_tree'],'source_snapshot_sha256':snap['sha256'],'source_files_verified':127,'unique_gates_verified':50,'matches_50_registered_CI_checks':True,'python_tests':285,'gate_log_sha256':logs,'component_artifact_sha256':artifacts,'component_artifact_count':92,'required_execution_markers':markers,'native_combined_steps_verified':list(steps),'all3339_prior_reports_preserved':True,'all3331_tracked_history_preserved':True,'prior_focused_review_manifests_unchanged':True,'qualification_receipt_sha256':sha(qual)if qual.exists()else None,'summary_sha256':sha(q/'gates/summary.json'),'results_sha256':sha(q/'gates/results.json'),'exact_merge_scoped_receipt_sha256':sha(prior/'receipt_c0de883.json'),'source_head_end':git('rev-parse','HEAD'),'source_diff_empty':not git('diff','--name-only'),'findings':[]}
assert result['source_head_end']==head and result['source_diff_empty']
(out/'final_aggregate_audit_c0de883.json').write_text(json.dumps(result,indent=2)+'\n')
(out/'review_final_c0de883.md').write_text(f'''Final independent backend/composition review approves exact merge `{head}`, tree `{s['source_tree']}`. No remaining findings.

All50 unique aggregate gates passed with stable exact source HEAD/hash, and match all50 registered CI checks. Independently verified127 source hashes (snapshot `{snap['sha256']}`),50 log hashes and92 component artifact hashes. Python discovery ran285 tests. Both feature controller/native browser gates, caption reload/86-field parity, and the pinned preference DPO consumer executed successfully.

The combined native receipt confirms immediate preference-proof invalidation for successful and uncertain classification Apply while fixed selections remain retained; later judgment drafts survive held Apply; classification Reject preserves an unrelated held judgment save; and exact admission recovery survives actual answer/judgment saves with early404 and one synthetic inference. The unchanged backend runtime matches the nine independent cross-feature checks: draft-only atomic Apply, stale preference/export bindings, preserved acquisition/judgment/answer evidence, immutable prior archive and explicit current-parent rejudgment.

All3339 prior report files and3331 tracked runner-history files retain their hashes. Earlier preliminary/exact-merge review manifests are unchanged. Opaque/foreign/orphan classification recovery metadata remains intentionally preserved and blocked. No source edits, real inference/model downloads, credentials or public writes were performed by this reviewer. Publication is owned by the parent.
''')
files=['audit_aggregate_c0de883.py','final_aggregate_audit_c0de883.json','review_final_c0de883.md'];(out/'artifact_manifest_final_c0de883.json').write_text(json.dumps({'source_head':head,'files':{p:sha(out/p)for p in files}},indent=2)+'\n')
print(json.dumps({k:result[k]for k in ['source_head','source_snapshot_sha256','source_files_verified','unique_gates_verified','matches_50_registered_CI_checks','python_tests','component_artifact_count','all3339_prior_reports_preserved','prior_focused_review_manifests_unchanged','qualification_receipt_sha256','findings']},indent=2))
