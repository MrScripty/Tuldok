import datetime
import hashlib
import json
from pathlib import Path
import subprocess

cwd = '/workspace/Tuldok-retained-analysis-integration-20261020'
plan = json.loads(Path('/tmp/tuldok-pr108-two-alias-cleanup-precheck.json').read_text())
archive = json.loads(Path('/tmp/tuldok-pr108-two-alias-archive-recovery.json').read_text())
assert archive['status'] == 'PASS' and archive['files_verified'] >= 706
review = Path('/tmp/tuldok-pr108-two-alias-cleanup-independent-precheck.json')
assert review.is_file()
receipt = Path('/tmp/tuldok-pr108-two-alias-cleanup-terminal.json')
assert not receipt.exists(), 'Inspect any existing outcome before retrying'
record = {'state': 'validating', 'selected': plan['selected'], 'main': plan['main'], 'archive': archive,
          'review_sha256': hashlib.sha256(review.read_bytes()).hexdigest(), 'operations': []}

def save():
    receipt.write_text(json.dumps(record, indent=2) + '\n')

def git(*args):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/MrScripty/Tuldok/' + path], text=True))

assert api('git/ref/heads/main')['object']['sha'] == plan['main']
archive_root = Path('/workspace/Tuldok-integration-checkpoint/docs/plans/lab-workflow-reliability/reports/integration-recovery-20261019')
evidence = json.loads((archive_root / 'tuldok-pr108-two-alias-pre-retirement-qa-archive.json').read_text())['copied']
for item in evidence:
    raw = Path(item['source']).read_bytes()
    assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256']
    assert (archive_root / item['archive']).read_bytes() == raw
for row in plan['selected']:
    pr = api('pulls/' + str(row['pr']))
    assert pr['merged'] and pr['head']['sha'] == row['head'] and pr['merge_commit_sha'] == row['merge_sha']
    assert not api('pulls?state=open&base=' + row['branch'] + '&per_page=100')
    assert git('rev-parse', 'refs/heads/' + row['branch']) == row['head']
    subprocess.run(['git', 'merge-base', '--is-ancestor', row['head'], plan['main']], cwd=cwd, check=True)
    assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=row['path'], text=True)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=row['path'], text=True).strip() == row['head']
    ignored = subprocess.check_output(['git', 'ls-files', '--others', '--ignored', '--exclude-standard'], cwd=row['path'], text=True).splitlines()
    actual = {str(Path(row['path']) / p) for p in ignored if '__pycache__/' not in p and not p.endswith('.pyc')}
    assert actual == {p['source'] for p in evidence if p['alias_key'] == row['alias_key']}
record['all_local_heads_before'] = dict(line.split() for line in git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads').splitlines())
record['worktree_records_before'] = git('worktree', 'list', '--porcelain')
refs = ['refs/heads/' + r['branch'] for r in plan['selected']]
remote = subprocess.check_output(['git', '-c', 'credential.helper=!gh auth git-credential', 'ls-remote', '--heads', 'origin', *refs], cwd=cwd, text=True)
observed = {line.split()[1]: line.split()[0] for line in remote.splitlines()}
assert observed == {ref: row['head'] for ref, row in zip(refs, plan['selected']) if row['remote_present']}
remote_refs = [ref for ref, row in zip(refs, plan['selected']) if row['remote_present']]
record['state'] = 'remote_compare_and_swap_delete_intent'
save()
# Expected-head leases guard deletion; no branch history is overwritten.
leases = ['--force-with-lease=' + ref + ':' + row['head'] for ref, row in zip(refs, plan['selected']) if row['remote_present']]
result = subprocess.run(['git', '-c', 'credential.helper=!gh auth git-credential', 'push', '--atomic', *leases, 'origin', *(':' + ref for ref in remote_refs)], cwd=cwd, capture_output=True, text=True)
record['remote_command'] = {'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
save()
after_remote = subprocess.check_output(['git', '-c', 'credential.helper=!gh auth git-credential', 'ls-remote', '--heads', 'origin', *refs], cwd=cwd, text=True)
record['remote_after'] = after_remote
save()
assert result.returncode == 0 and not after_remote.strip(), 'Remote outcome checked; no automatic retry'
for row in plan['selected']:
    record['state'] = 'ordinary_worktree_remove_intent'
    record['target'] = row['path']
    save()
    subprocess.run(['git', 'worktree', 'remove', row['path']], cwd=cwd, check=True)
    record['operations'].append({'worktree_removed': row['path']})
    save()
    subprocess.run(['git', 'update-ref', '-d', 'refs/heads/' + row['branch'], row['head']], cwd=cwd, check=True)
    tracking = 'refs/remotes/origin/' + row['branch']
    old_tracking = subprocess.run(['git', 'rev-parse', '--verify', tracking], cwd=cwd, text=True, capture_output=True)
    if old_tracking.returncode == 0:
        assert old_tracking.stdout.strip() == row['head']
        subprocess.run(['git', 'update-ref', '-d', tracking, row['head']], cwd=cwd, check=True)
    record['operations'].append({'local_ref_removed': 'refs/heads/' + row['branch']})
    save()
heads_after = dict(line.split() for line in git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads').splitlines())
expected = {r: h for r, h in record['all_local_heads_before'].items() if r not in refs}
assert heads_after == expected
worktrees_after = git('worktree', 'list', '--porcelain')
before_records = {block.split('\n', 1)[0]: block for block in record['worktree_records_before'].split('\n\n') if block}
after_records = {block.split('\n', 1)[0]: block for block in worktrees_after.split('\n\n') if block}
removed_record_keys = {'worktree ' + row['path'] for row in plan['selected']}
assert after_records == {key: value for key, value in before_records.items() if key not in removed_record_keys}
for row in plan['selected']:
    assert not Path(row['path']).exists() and 'worktree ' + row['path'] + '\n' not in worktrees_after
    subprocess.run(['git', 'merge-base', '--is-ancestor', row['head'], plan['main']], cwd=cwd, check=True)
record.update(state='complete_removed_reachable', all_other_local_heads_unchanged=True, all_other_worktree_records_unchanged=True, worktree_records_after=worktrees_after,
              completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
save()
print(json.dumps({'state': record['state'], 'removed': [r['pr'] for r in plan['selected']], 'main': plan['main']}))
