"""Independent synthetic transport spelling probe; one loopback request, no real inference."""
import json
import sys
import tempfile
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[6]
sys.path[:0] = [str(root), str(root / 'tests')]
from app import Dataset
from fake_classification_model import start

server, url, requests = start()
try:
    with tempfile.TemporaryDirectory() as folder:
        data = Dataset(folder)
        try:
            row = data.workbench.import_asset(dict(kind='text', name='Independent synthetic URL',
                text='Synthetic classification source', groups=['review-fixture'], rights='Authored'))
            body = dict(request_id=uuid.uuid4().hex, source_id=row['id'], revision=row['revision'],
                source_revision=row['source_revision'], server_url=url+'/v1/', model='classification-fixture',
                instruction='synthetic', seed=42, labels=['keep', 'cancel'])
            job = data.text_classification_proposals.start(body)
            data.text_classification_proposals.worker.join(4)
            assert not data.text_classification_proposals.worker.is_alive()
            job = data.text_classification_proposals.get(job['id'])
            assert job['status'] == 'completed'
            assert job['config']['requested_server_url'] == body['server_url']
            assert job['config']['server_url'] == url
            assert len(requests) == 1
            assert requests[0]['path'] == '/v1/chat/completions'
            print(json.dumps({'submitted_server_url': body['server_url'],
                'frozen_server_url': job['config']['server_url'],
                'requested_server_url': job['config']['requested_server_url'],
                'status': job['status'], 'inference_requests': len(requests)}, sort_keys=True))
        finally:
            data.close()
finally:
    server.shutdown()
    server.server_close()
