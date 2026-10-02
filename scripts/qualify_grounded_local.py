"""Opt-in integration smoke against an already-running loopback Pumas gateway.

Uses fictional source text in a temporary dataset. Never installs, downloads,
launches a service or bypasses candidate validation. Not a model-quality eval.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
from grounded_candidates import ACTIVE, catalog


def qualify(url, model):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.password:
        raise ValueError('This smoke accepts only credential-free HTTP loopback gateways.')
    result = {'scope': 'Real Pumas integration smoke, synthetic source only; not model-quality acceptance.',
              'gateway': url, 'requested_model': model, 'models': catalog(url)}
    if model not in result['models']:
        raise ValueError('Requested model is not in the real served catalog.')
    with tempfile.TemporaryDirectory(prefix='tuldok-pumas-smoke-') as root:
        data = Dataset(root)
        try:
            row = data.workbench.import_asset({'kind': 'text', 'text': 'Please cancel my meeting.',
                'name': 'Fictional smoke request', 'groups': ['fictional-smoke'], 'rights': 'Synthetic test fixture'})
            row = data.workbench.save(row['id'], {'revision': row['revision'], 'source_revision': row['source_revision'],
                'task': 'text_classification', 'annotation': {'label': 'cancel'}, 'groups': row['groups'], 'review': 'human_reviewed'})
            config = {'source_id': row['id'], 'revision': row['revision'], 'source_revision': row['source_revision'],
                'server_url': url, 'model': model, 'instruction': 'Rewrite politely without changing meaning.', 'count': 1, 'seed': 42}
            job = data.grounded.start(config)
            data.grounded.worker.join(190)
            if data.grounded.worker.is_alive():
                data.grounded.cancel(job['id']);data.grounded.worker.join(20)
                raise RuntimeError('Generation exceeded its bounded deadline.')
            job = data.grounded.get(job['id'])
            result['proposal'] = {'status': job['status'], 'error': job['error'], 'candidate_count': len(job['candidates']),
                'response_sha256': job['response_sha256'], 'reported_model': job.get('reported_model')}
            if job.get('raw_response_base64'):
                raw = base64.b64decode(job['raw_response_base64'], validate=True)
                result['proposal']['exact_bytes_hash_matches'] = hashlib.sha256(raw).hexdigest() == job['response_sha256']
                result['proposal']['raw_response'] = json.loads(raw)
            if job['status'] == 'completed':
                candidate = job['candidates'][0]
                # Explicit fixture-only inspection gate; do not label any model output human-reviewed.
                admitted = data.grounded.review(job['id'], {'revision': job['revision'], 'candidate_id': candidate['id'],
                    'decision': 'admit_draft', 'note': 'Automated integration fixture admission; semantic review remains required.'})['record']
                result['admission'] = {'review': admitted['review'], 'parent_matches': admitted['parents'] == [row['id']],
                    'response_hash_matches': admitted['provenance']['response_sha256'] == job['response_sha256']}
            else:
                result['admission'] = {'status': 'not exercised: production proposal validation rejected output'}
            cancel_job = data.grounded.start({**config, 'count': 10})
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                current = data.grounded.get(cancel_job['id'])
                if current['status'] != 'preparing':break
                time.sleep(.02)
            time.sleep(.2)
            before = data.grounded.get(cancel_job['id'])['status']
            started = time.monotonic()
            data.grounded.cancel(cancel_job['id']);data.grounded.worker.join(15)
            cancelled = data.grounded.get(cancel_job['id'])
            result['cancellation'] = {'before': before, 'after': cancelled['status'],
                'worker_stopped': not data.grounded.worker.is_alive(), 'elapsed_seconds': round(time.monotonic()-started, 3),
                'candidate_count': len(cancelled['candidates']), 'exercised_active_request': before in ACTIVE}
            data.close();data = Dataset(root)
            restored = data.grounded.get(job['id'])
            result['reopen'] = {'status_matches': restored['status'] == job['status'],
                'exact_response_preserved': restored.get('raw_response_base64') == job.get('raw_response_base64')}
        finally:
            data.close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.url, args.model), ensure_ascii=False, indent=2))
