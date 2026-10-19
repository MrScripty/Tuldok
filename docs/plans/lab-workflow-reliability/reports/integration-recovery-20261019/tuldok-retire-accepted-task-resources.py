import datetime
import json
import subprocess
from pathlib import Path

REPO = '/workspace/Tuldok-integration-checkpoint'
RECORD = Path('/tmp/tuldok-task-merged-cleanup-terminal.json')
record = json.loads(RECORD.read_text())

def run(args):
    return subprocess.check_output(args, text=True).strip()

def git(*args):
    return run(['git', '-C', REPO, *args])

def save():
    RECORD.write_text(json.dumps(record, indent=2) + '\n')

def worktrees(text):
    result = {}
    for block in text.strip().split('\n\n'):
        lines = block.splitlines()
        result[lines[0].removeprefix('worktree ')] = lines
    return result

protected_refs = dict(line.split() for line in Path('/tmp/tuldok-20261019-protected-local-heads.txt').read_text().splitlines())
protected_trees = worktrees(Path('/tmp/tuldok-20261019-protected-worktrees.txt').read_text())

def preservation():
    current = worktrees(git('worktree', 'list', '--porcelain'))
    for ref, oid in protected_refs.items():
        assert git('rev-parse', ref) == oid, ref
        git('cat-file', '-e', oid + '^{commit}')
    for path, lines in protected_trees.items():
        assert current.get(path) == lines, path
        assert Path(path).is_dir(), path
    for oid in record['protected_original_oids']:
        git('cat-file', '-e', oid + '^{commit}')
    return {'refs_exact': len(protected_refs), 'worktrees_exact': len(protected_trees), 'original_oids_exist': len(record['protected_original_oids'])}

assert record['execution_state'] == 'prepared; no deletion yet'
assert git('rev-parse', 'origin/main') == record['expected_main']
remote = dict((ref, oid) for oid, ref in (line.split() for line in git('ls-remote', 'origin').splitlines()))
assert remote['refs/heads/main'] == record['expected_main']
open_prs = []
page = 1
while True:
    rows = json.loads(run(['gh', 'api', '--method', 'GET', 'repos/MrScripty/Tuldok/pulls', '-f', 'state=open', '-f', 'per_page=100', '-f', f'page={page}']))
    open_prs.extend(rows)
    if len(rows) < 100:
        break
    page += 1
current_trees = worktrees(git('worktree', 'list', '--porcelain'))
for row in record['scope']:
    assert row['branch'] not in protected_refs
    assert row['path'] not in protected_trees
    assert git('rev-parse', row['branch']) == row['head']
    assert remote[row['remote_branch']] == row['head']
    subprocess.run(['git', '-C', REPO, 'merge-base', '--is-ancestor', row['head'], 'origin/main'], check=True)
    assert not any(pr['base']['ref'] == row['branch'].removeprefix('refs/heads/') for pr in open_prs)
    lines = current_trees[row['path']]
    assert 'HEAD ' + row['head'] in lines and 'branch ' + row['branch'] in lines
    assert not any(line.startswith(('locked', 'prunable')) for line in lines)
    assert not run(['git', '-C', row['path'], 'status', '--porcelain', '--untracked-files=all'])
record['immediate_precheck'] = preservation()
record['execution_state'] = 'prechecks complete; remote retirement pending'
save()

# Exact compare-and-swap deletion: concurrent branch updates refuse the entire
# atomic push. All commits are independently retained by verified remote main.
args = ['git', '-C', REPO, '-c', 'credential.helper=!gh auth git-credential', 'push', '--atomic']
args.extend('--force-with-lease=' + row['remote_branch'] + ':' + row['head'] for row in record['scope'])
args.append('origin')
args.extend(':' + row['remote_branch'] for row in record['scope'])
record['remote_delete_intent_recorded_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
save()
subprocess.run(args, check=True)
remote_after = dict((ref, oid) for oid, ref in (line.split() for line in git('ls-remote', 'origin').splitlines()))
assert all(row['remote_branch'] not in remote_after for row in record['scope'])
record['remote_branches_removed'] = True
record['execution_state'] = 'remote branches retired; local resources pending'
save()

for row in record['scope']:
    assert git('rev-parse', row['branch']) == row['head']
    assert not run(['git', '-C', row['path'], 'status', '--porcelain', '--untracked-files=all'])
    subprocess.run(['git', '-C', REPO, 'worktree', 'remove', row['path']], check=True)
    subprocess.run(['git', '-C', REPO, 'update-ref', '-d', row['branch'], row['head']], check=True)
    assert not Path(row['path']).exists()
    assert row['path'] not in worktrees(git('worktree', 'list', '--porcelain'))
    assert subprocess.run(['git', '-C', REPO, 'show-ref', '--verify', '--quiet', row['branch']]).returncode == 1
    subprocess.run(['git', '-C', REPO, 'merge-base', '--is-ancestor', row['head'], 'origin/main'], check=True)
    row['outcome'] = 'removed-reachable'
    row['removed_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
record['postcheck'] = preservation()
record['execution_state'] = 'complete; all ten exact branches/worktrees removed-reachable'
save()
print(json.dumps({'state': record['execution_state'], 'protected': record['postcheck'], 'retained_main': record['expected_main']}))
