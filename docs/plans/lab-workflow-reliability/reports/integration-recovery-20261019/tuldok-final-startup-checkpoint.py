import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

repo = Path('/workspace/Tuldok-integration-checkpoint')
dest = repo / 'docs/plans/lab-workflow-reliability/reports/integration-recovery-20261019'
post = Path('/tmp/tuldok-pr108-two-alias-cleanup-independent-postcheck.json')
assert post.is_file(), 'Wait for independent postcheck before changing checkpoint ref'
post_value = json.loads(post.read_text())
print('Independent postcheck:', json.dumps(post_value)[:1000])
assert post_value.get('state') == 'PASS' and all(post_value['checks'].values())
terminal = json.loads(Path('/tmp/tuldok-pr108-two-alias-cleanup-terminal.json').read_text())
assert terminal['state'] == 'complete_removed_reachable'
assert terminal['all_other_local_heads_unchanged'] and terminal['all_other_worktree_records_unchanged']
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
master = Path('/tmp/tuldok-updates-integration-acceptance-20261019.json')
m = json.loads(master.read_text())
snapshots = [json.loads(Path(f'/tmp/tuldok-pr{n}-startup-latest-ci-readiness.json').read_text()) for n in (111, 112)]
assert [r['head'] for r in snapshots] == ['29011daea37f101ee30be9bc10aab702a16c830a', '0dedbc953902ac89389dca0693006aaa02a0a87c']
m.update(state='PR108 merged and two task aliases safely retired; reviewed startup repair published in draft111/112; fresh corrected-head hosted gates pending', checkpoint_at=now, updated_at=now,
         required_pending=['PR111 head29011: latest lifecycle, captured-cpu, catalog and workspace-ui gates plus independent completed-log review',
                           'After111 merge and112 retarget with exact base/prospective-tree proof: PR112 head0ded fresh lifecycle gate and independent completed-log review',
                           'PUB-1: original failed diagnostic bytes/path/profile/caps/failure receipt',
                           'SCI-1: owned qualified criterion and compatible real lab pair'],
         resume=['Parent owns passive hosted CI monitoring; reactivate implementation lead for failures or readiness. Serial order111 then112.',
                 'Read tuldok-pending-111-112-activation.json and exact current GitHub heads before any merge. Do not relabel old0ba4 CPU success as new29011 qualification.',
                 'Preserve original82 refs,96 worktree records,91 reachable commits, README67, separate plan91 and unrelated work.'])
m['blocker'] = {'status': 'pending', 'action': 'Qualify and merge corrected PR111 then PR112', 'reason': 'Exact corrected-head hosted gates have not completed; no merge clearance', 'denied': False, 'uncertain_write': False}
m['current_resume'] = {'main': terminal['main'], 'remaining_order': [111,112], 'source_worktrees': ['/workspace/Tuldok-retained-analysis-integration-20261020','/workspace/Tuldok-captions-dialog-ci-repair-20261020'], 'activation': '/tmp/tuldok-pending-111-112-activation.json', 'state': m['state'], 'parent_role': 'passive hosted CI monitoring; reactivate this lead for failures/readiness'}
m['current_serial_integration'].update(observed_utc=now, latest_ci_snapshots=[f'/tmp/tuldok-pr{n}-startup-latest-ci-readiness.json' for n in (111,112)],
    cleanup_pr108={'status':'complete; independent postcheck clear', 'aliases':2,'remote_branches_deleted':1,'never_published_remote_aliases':1,'qa_files':10,'qa_bytes':566599,
                   'terminal':'/tmp/tuldok-pr108-two-alias-cleanup-terminal.json','independent':'/tmp/tuldok-pr108-two-alias-cleanup-independent-postcheck.json','pre_retirement_recovery':'/tmp/tuldok-pr108-two-alias-archive-recovery.json'},
    next_gate='Fresh corrected-head111 lifecycle/CPU/catalog/UI plus independent completed-log review, then112 lifecycle after retarget. Both old111 lifecycles failed and remain preserved.')
m['pr111_lifecycle_failure_0ba4'].update(diagnosis='Both old0ba4 lifecycle jobs failed first scientific Open project59:77/64. Controlled real-browser reproduction established an enabled-control/null-handler lost-click path; exact hosted pointer trace is absent. Reviewed two-line readiness fix and actual local green are source-hash-bound; fresh hosted acceptance remains pending.')
master.write_text(json.dumps(m,indent=2)+'\n')
activation_path=Path('/tmp/tuldok-pending-111-112-activation.json')
activation=json.loads(activation_path.read_text());activation['observed_utc']=now
for row,snap in zip(activation['prs'],snapshots): row['latest_ci_snapshot']=snap;row['merge_clearance']=False
activation_path.write_text(json.dumps(activation,indent=2)+'\n')
for p in [master,activation_path,Path('/tmp/tuldok-retire-108-two-alias.py'),Path(__file__)]: shutil.copyfile(p,dest/p.name)
for pattern in ['tuldok-pr108-two-alias-*.json','tuldok-pr111-startup-latest-ci-readiness.json','tuldok-pr112-startup-latest-ci-readiness.json']:
    for p in Path('/tmp').glob(pattern): shutil.copyfile(p,dest/p.name)
(dest/'RESTORE.md').write_text('''# Task recovery checkpoint

Clone branch `checkpoint/lab-integration-20261019` from MrScripty/Tuldok with the
existing configured GitHub authentication. Verify every evidence file's byte count
and SHA-256 against `manifest.json`. This branch retains task-owned public source
and review evidence; it contains no credentials, catalogs or runtime data. Its old
parent is recovery history, not the current product base.

## Current state

Main is `c1fc60dbf2d96d3cb0ac0739a6822c6b3301f0ad` after PR108. P1–P6 and E1–E4
were integrated earlier. PR89/90 and PR92–110 are merged. Actual merge trees were
verified against qualified source trees. Do not replay completed operations or
restart design work. The historical ledger retains previous pending snapshots;
this file and `tuldok-pending-111-112-activation.json` identify current work.

The remaining serial order is **111 →112**. Both are drafts.

| PR | Published head | Base | Gate still required |
| --- | --- | --- | --- |
|111|29011daea37f101ee30be9bc10aab702a16c830a|main c1fc60db|Fresh lifecycle, captured-cpu, catalog, workspace-ui and independent completed-log review|
|112|0dedbc953902ac89389dca0693006aaa02a0a87c|111 head29011dae|Fresh lifecycle and independent completed-log review; retarget after111 merge|

Parent owns passive hosted CI monitoring and reactivates the implementation lead
when failures or readiness require work. Recheck exact live heads and latest
required contexts before every merge. A pending newer context is not replaced by
an older success. Known same-head failures require disposition. Before retarget,
prove the qualified base tree equals current main and the prospective merge tree
equals the reviewed source. Keep111 until112 is retargeted. No current-head CI
jobs were cancelled. There is no uncertain publication or merge write.

## Exact failure, repair and validation scope

PR108 head9f084 passed all172 lifecycle steps, with1744 unit tests and72 skips,
plus the recorded actual CPU/browser gates. Independent log review is archived.
Merged treef245dcc821ebec18145a7e5340e19adab165d8f8 equals qualified source.
Optional artifact12240856492 ZIP download was blocked by proxy403; its contents
were not inspected or claimed verified. Required log/source evidence is retained.

Both PR111 old0ba4 lifecycle jobs39360310903/39360311316 failed at the first
scientific Open project wait59:77/64. This is distinct from the caption dialog
error. Both original failures and full logs are preserved. Their full unit suites
reported1771 tests with83 skips before the browser failure; later gates were
skipped. Both old
captured-CPU jobs passed13/13 with independent review, which is historical
source-specific evidence and does not qualify the corrected head.

The controlled original-entrypoint reproduction held the actual project module
and recorded a native click on an enabled button while its handler was null. It
reproduced the same timeout. Exact hosted pointer traces are absent, so that
host-event cause is not asserted. The two-line product fix disables Open project
until its owning controller binds all listeners. Existing scientific CI entrypoint
now executes the startup regression and all five original scientific checks.
Actual PostgreSQL/Chromium red and green logs, four tested-source hashes matching
29011, independent review and exact schema cleanup receipts are archived in
`project-startup-ci-source`, `project-startup-ci-evidence` and
`project-startup-ci-raw`. This is authored-array reader/custody evidence, not
physics acceptance. A late browser cache cleanup is documented separately;
an all-descendant process-cleanup guarantee is not claimed.

PR112 retains the independently reviewed caption test repair: event-owned exact
confirm waits, bounded CDP/diagnostics and owned-child cleanup, without weakening
assertions or workflows. Its actual PostgreSQL/Chromium journey passed. Receipt
source_commit records the pre-commit base; tested-file hashes bind publishedabba.
Root normally merged29011 into1120ded and verified both repairs' tested-file
hashes plus focused regressions before atomic publication. Fresh hosted lifecycle
qualification still remains. Old112abba run39364911305 is terminally cancelled,
with original logs preserved, never success. Old PR105 duplicate39349523584 is
also terminally cancelled; its newer exact-head primary passed all170 steps.

## Preservation and recovery

Twenty accepted task aliases/worktrees have been safely retired across recorded
groups. The latest two aliases both referenced accepted PR1089f084: the feature
remote branch was deleted; its repair alias had never been published remotely.
Both local refs and worktrees were removed ordinarily after dependent retarget,
live-head guards, no-active-use check, independent precheck and remote recovery
verification of all706 files. Ten QA files,566599 bytes, were archived intact.
Terminal and independent postcheck receipts verify exact nonselected head and
worktree-record equality and original82 refs,96 records and91 reachable commits.
Do not delete unrelated worktrees or original aliases. README67 and independent
plan91 remain separate/unmerged. Plan91 remainsb446d9a on
`docs/lab-workflow-reliability-plan`; PR71 is historical documentation only.

The final checkpoint also retains the retirement receipts and latest CI snapshots.
Use exact recorded commits when recovering retired sources from main; do not
substitute a later tree for an old test receipt.

## Remaining external inputs and evidence limits

PUB-1 requires original failed diagnostic bytes/path, admitted profile/caps and
failure receipt. SCI-1 requires an owned qualified criterion and compatible real
lab pair. Qualified per-case science pass/fail remains input-dependent; thresholds,
units and operators must not be invented. Generic scientific fixtures explicitly
use authored terminal arrays and nonrunnable metadata.

Actual CPU classifier training, correction, automatic checkpoints/probes and
separate fresh captured inference/package gates have their own source-specific
receipts. Runtime-byte-integrity observation passed with cleanup verification;
it establishes no full T5/preparation/cache/performance gain. No CUDA, unmeasured
hardware/runtime, model quality or scientific acceptance is inferred.
''')
manifest_path=dest/'manifest.json';manifest=json.loads(manifest_path.read_text())
manifest['current_main']=terminal['main'];manifest['remaining_pr_heads']={str(r['pr']):r['head'] for r in snapshots};manifest['snapshot_utc']=now
manifest['files']=[{'path':p.relative_to(dest).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(dest.rglob('*')) if p.is_file() and p!=manifest_path]
manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run(['git','add','--',str(dest.relative_to(repo))],cwd=repo,check=True)
subprocess.run(['git','diff','--cached','--check','--','*.py','*.md','*.json','*.cjs',':(exclude)docs/plans/lab-workflow-reliability/reports/integration-recovery-20261019/pre-retirement-qa/**'],cwd=repo,check=True)
subprocess.run(['git','commit','--quiet','-m','test: preserve indexed retirement and exact corrected-head CI handoff'],cwd=repo,check=True)
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
publication={'state':'push_intent','head':head,'files':len(manifest['files'])};receipt=Path('/tmp/tuldok-startup-final-checkpoint-publication.json');assert not receipt.exists()
receipt.write_text(json.dumps(publication,indent=2)+'\n')
r=subprocess.run(['git','-c','credential.helper=!gh auth git-credential','push','origin','HEAD:checkpoint/lab-integration-20261019'],cwd=repo,capture_output=True,text=True)
publication.update(exit=r.returncode,stdout=r.stdout,stderr=r.stderr)
receipt.write_text(json.dumps(publication,indent=2)+'\n')
remote=subprocess.check_output(['git','-c','credential.helper=!gh auth git-credential','ls-remote','--heads','origin','refs/heads/checkpoint/lab-integration-20261019'],cwd=repo,text=True).split()[0]
publication['remote']=remote;publication['state']='published_verified' if remote==head and r.returncode==0 else 'inspect_outcome_no_retry'
receipt.write_text(json.dumps(publication,indent=2)+'\n');assert publication['state']=='published_verified'
print(json.dumps(publication))
