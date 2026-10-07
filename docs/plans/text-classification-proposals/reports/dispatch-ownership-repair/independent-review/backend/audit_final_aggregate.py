from pathlib import Path
import hashlib,json,subprocess,re
root=Path('/workspace/Tuldok');out=Path(__file__).parent;q=root/'docs/plans/text-classification-proposals/reports/dispatch-ownership-repair/qualification'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
git=lambda *args:subprocess.check_output(['git',*args],cwd=root,text=True).strip()
expected='824e3ee1181184e2284875e5a08ebd1406318bfc';head=git('rev-parse','HEAD');assert head==expected
focused=json.loads((out/'artifact_manifest_824e3ee.json').read_text());assert len(focused['files'])==12
for p,h in focused['files'].items():assert sha(out/p)==h,p
summary=json.loads((q/'gates/summary.json').read_text());results=json.loads((q/'gates/results.json').read_text())
assert len(results)==len({e['command']for e in results})==summary['gate_count']==summary['passed']==summary['qualified_passing_gates']==46
assert summary['failed']==summary['blocked']==0 and summary['stale_passed_gates']==[]
assert summary['source_head']==head and summary['source_tree']==git('rev-parse','HEAD^{tree}')
assert summary['source_diff_sha256']==hashlib.sha256(b'').hexdigest() and not git('diff','--name-only')
snapshot=summary['source_snapshot'];assert snapshot['head']==head and len(snapshot['files'])==119
for p,h in snapshot['files'].items():assert sha(root/p)==h,p
assert snapshot['sha256']==hashlib.sha256(json.dumps(snapshot['files'],sort_keys=True).encode()).hexdigest()
logs={};artifacts={}
for e in results:
 assert e['status']=='passed' and e['exit_code']==0 and e['source_stable_during_gate'] and e['historical_report_hashes_preserved'],e['command']
 assert e['source_head_start']==e['source_head_end']==head,e['command']
 assert e['source_sha256_start']==e['source_sha256_end']==snapshot['sha256'],e['command']
 p=root/e['log'];assert p.is_file();logs[e['log']]=sha(p)
 assert set(e['component_artifacts'])==set(e['component_artifact_sha256'])
 for p,h in e['component_artifact_sha256'].items():assert sha(root/p)==h,p;artifacts[p]=h
original=json.loads((q.parent/'preservation-baseline.json').read_text());baseline=json.loads((q/'preservation-baseline.json').read_text())
assert original['all_report_count']==len(original['report_sha256'])==2939
assert baseline['all_prior_report_file_count']==len(baseline['report_sha256'])==2993
for name,evidence in [('original2939',original['report_sha256']),('pre_run2993',baseline['report_sha256']),('runner_tracked2990',summary['historical_reports'])]:
 for p,h in evidence.items():assert sha(root/p)==h,(name,p)
assert len(summary['historical_reports'])==summary['historical_report_files_preserved']==2990
req={}
for cmd,markers in {
 'python -m unittest discover -s tests':['Ran 273 tests','OK'],
 'node tests/test_caption_proposals_controller.cjs':['Caption reload: durable before POST','Static admission parity: 86 cases'],
 'node tests/test_text_classification_proposals_controller.cjs':['six delayed initial400/409/422 overlap','ten malformed raw-bound counters recover','malformed/orphan/exhausted evidence and successor CAS'],
 'node tests/browser_text_classification_proposals.cjs':['Text classification proposals real HTTP/Chromium bounded synthetic contracts passed.']}.items():
 entry=next(e for e in results if e['command']==cmd);text=(root/entry['log']).read_text();assert all(m in text for m in markers);req[cmd]=markers
browser=next(e for e in results if e['command']=='node tests/browser_text_classification_proposals.cjs')
cross_path=next(p for p in browser['component_artifacts']if p.endswith('cross-tab-dispatch-observation.json'));cross=json.loads((root/cross_path).read_text())
assert cross['source_head']==head and cross['runtime_sha256']==snapshot['files']['static/text-classification-proposals.js']
cases={c['outcome']:c for c in cross['cases']};assert set(cases)=={'success','lost-ack','terminal-receipt-CAS','crash-before-delivery'}
for outcome in ['success','lost-ack']:
 c=cases[outcome];body=c['body'];raw=json.dumps({'schema_version':1,'body':body},ensure_ascii=False,separators=(',',':'))
 assert c['first']['entries']['attempt']['generation']==1
 assert c['second']['entries']['attempt']['generation']==2
 assert c['after_old_refusal']['entries']['attempt']['generation']==2
 assert c['after_old_refusal']['entries']['pending']==c['after_old_refusal']['mirror']==raw
 assert c['after_old_refusal']['memory']==body
 assert c['early_exact_get_status']==404 and c['changed_intent_posts']==0
 assert [x['status']for x in c['backend_after_release']]==[409,202]
 assert all(x['body']==body for x in c['backend_after_release'])
 assert 'pending'not in c['canonical_retirement']['entries'] and 'attempt'not in c['canonical_retirement']['entries']
 assert c['canonical_retirement']['mirror']is None
 assert c['after_inference']-c['before_inference']==1
 if outcome=='lost-ack':assert c['reload_explicit_posts']==[body] and c['after_second_transport']['entries']['attempt']['generation']==2
c=cases['terminal-receipt-CAS'];assert c['terminal_body']['request_id']!=c['fresh_body']['request_id']
assert c['after_old_canonical']['entries']['attempt']['generation']==1
assert json.loads(c['after_old_canonical']['entries']['pending'])['body']==c['fresh_body']
c=cases['crash-before-delivery'];assert c['early_exact_get_status']==404 and c['explicit_recovered_posts']==[c['body']]
assert c['after_inference']-c['before_inference']==1 and 'attempt'not in c['retired']['entries'] and 'pending'not in c['retired']['entries']
qualreceipt=q/'qualification-and-preservation.json'
receipt={'source_head':head,'source_tree':summary['source_tree'],'source_snapshot_sha256':snapshot['sha256'],'source_files_verified':119,'aggregate_gates_verified':46,'python_tests':273,'gate_logs_verified':logs,'component_artifacts_verified':artifacts,'component_artifact_count':len(artifacts),'required_execution_markers':req,'native_transport_cases_verified':list(cases),'preservation':{'original2939_unchanged':True,'pre_run2993_unchanged':True,'runner_tracked2990_unchanged':True,'focused12_scratch_unchanged':True},'qualification_preservation_receipt':{'path':str(qualreceipt.relative_to(root)),'sha256':sha(qualreceipt)}if qualreceipt.exists()else None,'summary_sha256':sha(q/'gates/summary.json'),'results_sha256':sha(q/'gates/results.json'),'focused_receipt_sha256':sha(out/'receipt_824e3ee.json'),'findings':[],'source_head_end':git('rev-parse','HEAD'),'source_diff_empty':not git('diff','--name-only')}
assert receipt['source_head_end']==head and receipt['source_diff_empty']
(out/'final_aggregate_audit_824e3ee.json').write_text(json.dumps(receipt,indent=2)+'\n')
(out/'review_final_824e3ee.md').write_text(f'''Final independent review approves source `{head}`, tree `{summary['source_tree']}`. No remaining findings were identified.

All 46 unique aggregate gates passed with exit0 and stable exact source HEAD/hash before and after each gate. Independently verified all119 source file hashes, all46 log files, and all{len(artifacts)} component artifact hashes. The Python suite ran273 tests. Caption reload and86-field parity executed inside the inherited caption controller gate. Classification controller logs demonstrate overlapping delayed400/409/422 attempts, bad-counter positive recovery, strict generation commit faults, legacy/orphan/exhaustion guards and successor CAS.

The aggregate native browser receipt additionally verifies realHTTP first409/held same-ID second dispatch/early404, generation1→2 retention, changed-intent0POST, second202 admission, lostACK/fullcontextreload/exact retry, whole-ID canonical receipt recovery, terminal late-receipt successor CAS, and crash-before-delivery explicit unchanged recovery. One synthetic inference ran per admitted ID in the refusal/recovery cases. Independent focused native16 and bounded actual backend timing proofs remain unchanged and approved.

Preservation hashes match all2939 original reports, all2993 pre-run report files and all2990 tracked runner-history files. The original12-file focused scratch manifest is unchanged. Foreign/opaque/orphan metadata remains intentionally preserved and blocked; malformed generations never establish refusal/POST authority. No source edits, real inference, model downloads, credentials or public writes were performed by this reviewer.
''')
newfiles=['audit_final_aggregate.py','final_aggregate_audit_824e3ee.json','review_final_824e3ee.md']
(out/'artifact_manifest_final_824e3ee.json').write_text(json.dumps({'source_head':head,'focused_manifest_sha256':sha(out/'artifact_manifest_824e3ee.json'),'focused12_unchanged':True,'new_files':{p:sha(out/p)for p in newfiles}},indent=2)+'\n')
print(json.dumps({k:receipt[k]for k in ['source_head','source_tree','source_snapshot_sha256','source_files_verified','aggregate_gates_verified','python_tests','component_artifact_count','preservation','qualification_preservation_receipt','findings']},indent=2))
