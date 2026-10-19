import datetime
import json
import subprocess
from pathlib import Path

inventory = json.loads(Path('/tmp/tuldok-superseded-ci-candidates.json').read_text())
receipt = Path('/tmp/tuldok-superseded-ci-cancellation-results.json')
record = {'scope': 'Only superseded pending pull_request runs for task PR102–110; current heads and all main/push runs excluded', 'reason': 'Free CI capacity for current implementation qualification', 'results': [], 'no_acceptance_claim': True}

def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', 'repos/MrScripty/Tuldok/' + path], text=True))

def save():
    receipt.write_text(json.dumps(record, indent=2) + '\n')

for candidate in inventory['candidates']:
    number = candidate['pr']
    assert number in range(102, 111)
    pr = api(f'pulls/{number}')
    run_id = candidate['id']
    run = api(f'actions/runs/{run_id}')
    row = {'run': run_id, 'pr': number, 'old_head': candidate['old_head'], 'current_head': pr['head']['sha'], 'state_before': run['status'], 'url': candidate['url']}
    assert pr['state'] == 'open' and pr['head']['sha'] == candidate['current_head']
    assert pr['head']['repo']['full_name'] == 'MrScripty/Tuldok'
    assert run['event'] == 'pull_request' and run['head_sha'] == candidate['old_head']
    assert run['head_sha'] != pr['head']['sha']
    assert run['head_branch'] == pr['head']['ref'] == candidate['source_branch']
    assert run['head_repository']['full_name'] == 'MrScripty/Tuldok'
    assert [p['number'] for p in run['pull_requests']] == [number]
    if run['status'] not in ('queued', 'in_progress'):
        row['outcome'] = 'already terminal; cancellation not sent'
        row['conclusion'] = run['conclusion']
        record['results'].append(row)
        save()
        continue
    row['outcome'] = 'request intent recorded; outcome pending'
    row['requested_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record['results'].append(row)
    save()
    result = subprocess.run(['gh', 'api', '--method', 'POST', f'repos/MrScripty/Tuldok/actions/runs/{run_id}/cancel'], capture_output=True, text=True)
    row['request_exit'] = result.returncode
    row['response'] = result.stdout.strip()
    row['stderr'] = result.stderr.strip()
    if result.returncode:
        observed = api(f'actions/runs/{run_id}')
        row['observed_state'] = observed['status']
        row['observed_conclusion'] = observed['conclusion']
        if 'HTTP 409' in result.stderr and observed['status'] == 'completed':
            row['outcome'] = 'terminal race confirmed; no retry'
            save()
            continue
        row['outcome'] = 'request failed; no retry; remaining cancellation batch stopped'
        save()
        print(json.dumps(row))
        raise SystemExit(1)
    row['outcome'] = 'cancellation request accepted; terminal verification pending'
    save()
    print(json.dumps({'run': run_id, 'pr': number, 'request': 'accepted'}), flush=True)
record['batch_request_state'] = 'all candidates dispositioned; terminal verification required for accepted cancellations'
save()
