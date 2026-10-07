from pathlib import Path
import hashlib,json,subprocess,datetime

REPO=Path('/workspace/Tuldok')
OUT=Path(__file__).resolve().parent
QUAL=REPO/'docs/plans/text-classification-proposals/reports/judgment-save-ownership-repair/qualification'
HEAD='f2b61ce3ebcae8380dcbea9c384c124e803083be'
TREE='39491c6e3b8ff1582c5dfe870f199f4304605e35'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify_map(mapping,base=REPO):
    for name,wanted in mapping.items():
        actual=digest(base/name)
        assert actual==wanted,(name,wanted,actual)
    return len(mapping)

summary=json.loads((QUAL/'gates/summary.json').read_text())
results=json.loads((QUAL/'gates/results.json').read_text())
baseline=json.loads((QUAL/'preservation-baseline.json').read_text())
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==HEAD
assert summary['source_head']==HEAD and summary['source_tree']==TREE
assert summary['gate_count']==summary['recorded_gates']==summary['passed']==summary['qualified_passing_gates']==50
assert summary['failed']==summary['blocked']==0 and summary['stale_passed_gates']==[]
assert len(results)==len({r['command'] for r in results})==50
snapshot=summary['source_snapshot'];assert snapshot['head']==HEAD
assert hashlib.sha256(json.dumps(snapshot['files'],sort_keys=True).encode()).hexdigest()==snapshot['sha256']
source_count=verify_map(snapshot['files'])
artifact_count=0;logs={}
for row in results:
    assert row['status']=='passed' and row['exit_code']==0 and row['source_stable_during_gate']
    assert row['source_head_start']==row['source_head_end']==HEAD
    assert row['source_sha256_start']==row['source_sha256_end']==snapshot['sha256']
    assert row['historical_report_hashes_preserved']
    assert set(row['component_artifacts'])==set(row['component_artifact_sha256'])
    artifact_count+=verify_map(row['component_artifact_sha256'])
    logs[row['log']]=digest(REPO/row['log'])
historical_count=verify_map(summary['historical_reports'])
assert summary['historical_report_hashes_preserved'] and historical_count==summary['historical_report_files_preserved']
baseline_count=verify_map(baseline['report_sha256'])
backup=Path(baseline['backup']);backup_count=verify_map(baseline['report_sha256'],backup)
assert baseline_count==backup_count==3559
native=next(r for r in results if r['command']=='node tests/browser_classification_preferences_integration.cjs')
native_sessions=[REPO/name for name in native['component_artifacts'] if name.endswith('/session.json')]
assert len(native_sessions)==1
session=json.loads(native_sessions[0].read_text());assert session['source_head']==HEAD and session['result']=='PASS' and session['synthetic_only']
assert session['negative_apply_hook'] is False
assert len(session['steps'])==10
assert all(snapshot['files'][name]==wanted for name,wanted in session['source_sha256'].items())
for screenshot in session['screenshots']:
    assert digest(native_sessions[0].parent/screenshot['filename'])==screenshot['sha256']
old_root=OUT.parent
for directory in [old_root/'published-6aba-negative',old_root/'busy-guard-only-negative',old_root/'workingtree-repair-first-pass',old_root/'workingtree-repair-v2',old_root/'workingtree-save-epoch',old_root/('candidate-'+HEAD)]:
    verify_map(json.loads((directory/'sha256-manifest.json').read_text()),directory)
evidence={'review':'Independent exact-head aggregate and preservation audit','candidate':HEAD,'tree':TREE,'audited_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verdict':'PASS','gate_count':50,'source_snapshot_sha256':snapshot['sha256'],'source_files_verified':source_count,'gate_logs_hashed':len(logs),'component_artifact_hashes_verified':artifact_count,'historical_summary_hashes_verified':historical_count,'preexisting_all_report_hashes_verified':baseline_count,'preexisting_backup_bytes_verified':backup_count,'native_combined_session':str(native_sessions[0].relative_to(REPO)),'native_combined_source_hashes_verified':len(session['source_sha256']),'native_combined_step_count':len(session['steps']),'native_combined_screenshot_count':len(session['screenshots']),'independent_13case_and_negative_reports_preserved':True,'native_steps':[step['name'] for step in session['steps']],'summary_sha256':digest(QUAL/'gates/summary.json'),'results_sha256':digest(QUAL/'gates/results.json'),'baseline_sha256':digest(QUAL/'preservation-baseline.json'),'logs_sha256':logs,'limitations':['Audit verifies saved results/source/log and artifact hashes; it does not rerun browsers or real inference.','Earlier fixed defects and retained negative evidence remain in historical reports; this audit does not revise them.']}
(OUT/'receipt-aggregate-f2b61.json').write_text(json.dumps(evidence,indent=2)+'\n')
(OUT/'native-combined-session-copy.json').write_bytes(native_sessions[0].read_bytes())
print(json.dumps({key:evidence[key] for key in ['candidate','verdict','gate_count','source_files_verified','component_artifact_hashes_verified','historical_summary_hashes_verified','preexisting_all_report_hashes_verified','native_combined_step_count','native_combined_screenshot_count']},indent=2))
