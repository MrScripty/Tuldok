from pathlib import Path
import json,hashlib,subprocess,re
root=Path('/workspace/Tuldok');out=Path(__file__).parent;prior=out.parent/'review-backend';q=root/'docs/plans/text-classification-proposals/reports/judgment-save-ownership-repair/qualification'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();git=lambda *a:subprocess.check_output(['git',*a],cwd=root,text=True).strip()
head=git('rev-parse','HEAD');assert head=='f2b61ce3ebcae8380dcbea9c384c124e803083be';assert git('rev-parse','HEAD^{tree}')=='39491c6e3b8ff1582c5dfe870f199f4304605e35';assert not git('diff','--name-only')
for folder,name in [(prior,'initial_busy_only_evidence_manifest.json'),(prior/'epoch-candidate','workingtree_evidence_manifest.json'),(prior,'artifact_manifest_f2b61ce.json')]:
 m=json.loads((folder/name).read_text())
 for p,h in m['files'].items():assert sha(folder/p)==h,p
s=json.loads((q/'gates/summary.json').read_text());r=json.loads((q/'gates/results.json').read_text());assert len(r)==len({e['command']for e in r})==s['passed']==s['gate_count']==s['registered_workflow_gate_count']==s['qualified_passing_gates']==50
assert s['failed']==s['blocked']==0 and s['stale_passed_gates']==[] and s['source_head']==head and s['source_tree']==git('rev-parse','HEAD^{tree}')
commands=re.findall(r'^\s+- run: ((?:node |python -m unittest ).*)$',(root/'.github/workflows/tests.yml').read_text(),re.M);assert len(commands)==50 and set(commands)=={e['command']for e in r}
snap=s['source_snapshot'];assert snap['head']==head and len(snap['files'])==127
for p,h in snap['files'].items():assert sha(root/p)==h,p
assert snap['sha256']=='352aa0c4a5379d28249ec2c35e1250022177b629fd0b881245124c70e2308d73'==hashlib.sha256(json.dumps(snap['files'],sort_keys=True).encode()).hexdigest()
logs={};artifacts={}
for e in r:
 assert e['status']=='passed' and e['exit_code']==0 and e['source_stable_during_gate'] and e['historical_report_hashes_preserved']
 assert e['source_head_start']==e['source_head_end']==head and e['source_sha256_start']==e['source_sha256_end']==snap['sha256']
 logs[e['log']]=sha(root/e['log']);assert set(e['component_artifacts'])==set(e['component_artifact_sha256'])
 for p,h in e['component_artifact_sha256'].items():assert sha(root/p)==h,p;artifacts[p]=h
assert len(logs)==50 and len(artifacts)==92
base=json.loads((q/'preservation-baseline.json').read_text());assert len(base['report_sha256'])==base['all_prior_report_file_count']==3559
backup=Path(base['backup'])
for p,h in base['report_sha256'].items():assert sha(root/p)==sha(backup/p)==h,p
assert len(s['historical_reports'])==s['historical_report_files_preserved']==3551
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
assert session['source_head']==head and session['result']=='PASS' and session['synthetic_only'] and not session['negative_apply_hook'] and session['classification_script_override_sha256']is None
for p,h in session['source_sha256'].items():assert snap['files'][p]==h
steps={e['name']:e for e in session['steps']};assert len(steps)==10
for name in ['Immediate preference proof invalidation success','Immediate preference proof invalidation uncertain']:
 step=steps[name];assert step['state']['preview']is None and step['state']['freeze_disabled'] and step['state']['items']==step['fixed']
step=steps['Held classification Apply retains later judgment draft'];assert step['retained']['dirty']and step['retained']['review']=='draft'and step['retained']['editor']['id']==step['opened']['editor']['id']
step=steps['Classification Reject preserves unrelated judgment save owner'];assert step['state']['dirty']and step['state']['review']=='draft'and step['state']['editor']['revision']==2
step=steps['Recovery unchanged across actual answer and judgment saves'];assert step['early_exact_get_status']==404 and step['answer_revision']==step['judgment_revision']==2 and step['after_inference']-step['before_inference']==1
for suffix,status in [('refusal',409),('success',200)]:
 step=steps['Clean stale judgment save first '+suffix];assert step['apply_posts_while_busy']==0 and step['save_response']['status']==status
 before,during,after=step['before'],step['during'],step['after'];assert before['busy']and during['busy']and not before['dirty']and not during['dirty']and not after['busy']
 for key in ['editor','answers','body','current','editor_epoch','judgment_epoch','items','review','rationale','pending','mirror']:assert during[key]==before[key],(suffix,key)
 assert after['editor']['id']==before['editor']['id']and not after['form_hidden']and after['current']==before['current']
step=steps['Held Apply acknowledgment retains later clean judgment save'];assert step['save_response']['status']==409
for key in ['editor','answers','body','current','editor_epoch','judgment_epoch','items','review','rationale']:assert step['during'][key]==step['before'][key],key
assert step['backend_parent']['review']=='draft'and step['backend_parent']['revision']==step['after']['current']['revision']+1 and step['after']['editor']==step['before']['editor']
for suffix,status,phase in [('refusal',409,'after-backend-commit'),('success',200,'before-backend-transport')]:
 step=steps['Clean judgment '+suffix+' settles before older Apply acknowledgment'];assert step['save_response']['status']==status and step['apply_hold_phase']==phase
 a,b,c,d=step['before_save'],step['dispatched'],step['settled'],step['after'];assert not a['busy']and b['busy']and not c['busy']and not d['busy']
 assert b['judgment_epoch']==a['judgment_epoch']+1==c['judgment_epoch']==d['judgment_epoch']
 for key in ['editor','answers','body','current','editor_epoch','judgment_epoch','items','review','rationale','pending','mirror','form_hidden']:assert c[key]==d[key],(suffix,key)
 assert not d['dirty']and not d['form_hidden']and step['backend_parent']['review']=='draft'and step['backend_parent']['revision']==d['current']['revision']+1
 if suffix=='refusal':assert d['editor']==a['editor']
 else:assert d['editor']['revision']==a['editor']['revision']+1
qual=q/'qualification-and-preservation.json'
if qual.exists():
 qr=json.loads(qual.read_text());assert qr['source_head']==head and qr['source_snapshot_sha256']==snap['sha256'] and qr['qualified_passing_gates']==50
result={'source_head':head,'source_tree':s['source_tree'],'source_snapshot_sha256':snap['sha256'],'source_files_verified':127,'unique_gates_verified':50,'matches_50_registered_CI_checks':True,'python_tests':285,'gate_log_sha256':logs,'component_artifact_sha256':artifacts,'component_artifact_count':92,'required_execution_markers':markers,'native_actual_HTTP_10_cases_verified':list(steps),'native_busy_first_Apply_POST_count':0,'native_late_success_and_refusal_dispatch_lifetime_epochs_verified':True,'all3559_prior_report_files_and_external_backup_verified':True,'all3551_tracked_history_hashes_preserved':True,'prior_negative_and_positive_review_manifests_unchanged':True,'qualification_receipt_sha256':sha(qual)if qual.exists()else None,'summary_sha256':sha(q/'gates/summary.json'),'results_sha256':sha(q/'gates/results.json'),'exact_focused_receipt_sha256':sha(prior/'receipt_f2b61ce.json'),'source_head_end':git('rev-parse','HEAD'),'source_diff_empty':not git('diff','--name-only'),'findings':[]}
assert result['source_head_end']==head and result['source_diff_empty']
(out/'final_aggregate_audit_f2b61ce.json').write_text(json.dumps(result,indent=2)+'\n')
(out/'review_final_f2b61ce.md').write_text(f'''Final independent review approves `{head}`, tree `{s['source_tree']}`. No remaining findings in the reviewed repair.

All50 unique aggregate gates pass and exactly match the50 registered CI checks. Every gate retains the exact HEAD and127-file source hash `{snap['sha256']}`. Independently verified50 log hashes,92 component artifact hashes and285 Python tests. Existing admission-generation, caption reload/parity, preference and pinned DPO consumer gates also pass.

The real Chromium/synthetic HTTP combined receipt contains ten cases with no script override or disabled invalidation hook. It proves zero classification Apply POSTs while an earlier clean judgment Save is busy, for both real200 and409 outcomes, without editor/answer/body/selection ownership changes. It also proves a later clean Save remains intact while ApplyACK precedes its409, and after either a real409 settles following committed Apply or a feasible200 settles before held Apply transport is delivered. Dispatch advances the judgment lifetime epoch exactly once; the editor/current/answers/body/review/selections survive the older ApplyACK after busy has cleared. Backend classification is draft at the next parent revision, so stale UI bindings remain subject to strict CAS. Earlier proof invalidation, late dirty intent, Reject ownership and exact admission recovery cases remain passing.

All3559 prior reports match both their saved hashes and the external backup; all3551 tracked history hashes match. Earlier failed busy-only and passing working-tree/frozen-source review artifacts remain unchanged. Historical6aba qualification is preserved as evidence and does not cover the subsequently discovered clean-busy/settled-save cases. The final two runtime sites are the Apply preflight busy guard and validated judgment-dispatch epoch advance; backend/schema/admission runtime is unchanged. No source edits, test reruns, real inference/model downloads, credential changes or public writes were performed by this final auditor. Publication remains owned by the parent.
''')
files=['audit_f2b61ce.py','final_aggregate_audit_f2b61ce.json','review_final_f2b61ce.md'];(out/'artifact_manifest_final_f2b61ce.json').write_text(json.dumps({'source_head':head,'files':{p:sha(out/p)for p in files}},indent=2)+'\n')
print(json.dumps({k:result[k]for k in ['source_head','source_snapshot_sha256','source_files_verified','unique_gates_verified','matches_50_registered_CI_checks','python_tests','component_artifact_count','native_busy_first_Apply_POST_count','native_late_success_and_refusal_dispatch_lifetime_epochs_verified','all3559_prior_report_files_and_external_backup_verified','prior_negative_and_positive_review_manifests_unchanged','qualification_receipt_sha256','findings']},indent=2))
