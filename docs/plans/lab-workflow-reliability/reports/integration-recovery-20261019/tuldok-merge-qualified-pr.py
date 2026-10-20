import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

plan = json.loads(Path(sys.argv[1]).read_text())
number, head, base = plan['pr'], plan['head'], plan['base']
receipt = Path(f'/tmp/tuldok-pr{number}-final-merge-receipt.json')
assert not receipt.exists(), 'Existing merge receipt must be inspected before any retry'
record = dict(plan, state='checking', observed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())

def save():
    receipt.write_text(json.dumps(record, indent=2) + '\n')

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/MrScripty/Tuldok/' + path], text=True))

def git(*args):
    return subprocess.check_output(['git', *args], cwd=plan['source_worktree'], text=True).strip()

record['review_sha256'] = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in plan['reviews']}
assert api('git/ref/heads/main')['object']['sha'] == base
subprocess.run(['git', '-c', 'credential.helper=!gh auth git-credential', 'fetch', 'origin', 'refs/heads/main'], cwd=plan['source_worktree'], check=True)
assert git('rev-parse', head + '^{tree}') == plan['tree']
assert git('merge-tree', '--write-tree', base, head) == plan['tree']
record['prospective_tree_verified'] = plan['tree']
pr = api(f'pulls/{number}')
assert pr['state'] == 'open' and pr['head']['sha'] == head and pr['base']['ref'] == 'main' and pr['base']['sha'] == base
checks = api(f'commits/{head}/check-runs?per_page=100')
assert checks['total_count'] <= 100 and checks['check_runs']
assert {r['name'] for r in checks['check_runs']} == set(plan['check_names'])
latest = {}
for check in checks['check_runs']:
    if check['name'] not in latest or check['id'] > latest[check['name']]['id']:
        latest[check['name']] = check
# Duplicate older executions do not replace the latest required context.
# A known same-head failure still requires explicit disposition before merging.
assert not any(r['conclusion'] in ('failure', 'timed_out', 'action_required', 'startup_failure') for r in checks['check_runs'])
assert all(r['status'] == 'completed' and r['conclusion'] == 'success' for r in latest.values())
record['checks'] = [{'id': r['id'], 'name': r['name'], 'status': r['status'], 'conclusion': r['conclusion'], 'url': r['details_url']} for r in checks['check_runs']]
record['latest_required_check_ids'] = {name: r['id'] for name, r in latest.items()}
if pr['draft']:
    record['state'] = 'ready_transition_intent'
    save()
    subprocess.run(['gh', 'pr', 'ready', str(number), '--repo', 'MrScripty/Tuldok'], check=True)
pr = api(f'pulls/{number}')
assert not pr['draft'] and pr['head']['sha'] == head and pr['base']['sha'] == base
assert pr['mergeable'] and pr['mergeable_state'] == 'clean'
assert api('git/ref/heads/main')['object']['sha'] == base
request = Path(f'/tmp/tuldok-pr{number}-merge-request.json')
request.write_text(json.dumps({'sha': head, 'merge_method': 'merge'}))
record['state'] = 'merge_request_intent_recorded'
save()
result = subprocess.run(['gh', 'api', '--method', 'PUT', f'repos/MrScripty/Tuldok/pulls/{number}/merge', '--input', str(request)], text=True, capture_output=True)
record.update(command_exit=result.returncode, response=result.stdout, stderr=result.stderr)
save()
if result.returncode:
    observed = api(f'pulls/{number}')
    record.update(state='failed_checked_no_retry', observed_merged=observed['merged'], observed_merge_commit=observed['merge_commit_sha'])
    save()
    raise SystemExit(result.returncode)
response = json.loads(result.stdout)
record.update(state='merge_response_received', merge_response=response)
save()
assert response['merged'], response
commit = api('git/commits/' + response['sha'])
assert commit['tree']['sha'] == plan['tree']
assert [p['sha'] for p in commit['parents']] == [base, head]
record.update(state='merged_and_tree_verified', merge_sha=response['sha'], merged_tree=commit['tree']['sha'], current_main=api('git/ref/heads/main')['object']['sha'], merged_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
save()
print(json.dumps({'pr': number, 'merge_sha': record['merge_sha'], 'tree_equal': True, 'current_main': record['current_main']}))
