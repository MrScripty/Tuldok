"""Prepare a small actual native classifier Run for query/HTTP/browser acceptance.

Uses the normal PostgreSQL catalog, explicit local test owner, frozen release,
Pipeline validation and supervised CPU Run. No retained document is manufactured.
The six authored images establish transport/numeric behavior, not model quality.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tests' / 'fixtures'))
from app import Dataset
from auth_helpers import ExplicitOwnerFixture
from image_classification_fixture import populate
import image_training


def prepare(directory):
    directory = Path(directory).resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    dataset = Dataset(directory / 'catalog')
    try:
        owner = ExplicitOwnerFixture.bootstrap(dataset)
        with owner.bound(dataset):
            rows = populate(dataset)
            selection = {'format': 'image_classification_v1',
                         'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                         'ratios': {'train': 34, 'validation': 33, 'test': 33}, 'seed': 42}
            preview = dataset.releases.preview(selection)
            release = dataset.releases.create(dict(selection, preview_token=preview['preview_token']))
            graph = dataset.pipelines.create({'name': 'Retained analysis actual fixture',
                                              'release_id': release['id'], 'recipe': image_training.MODEL_RECIPE})
            changed = copy.deepcopy(graph)
            next(node for node in changed['nodes'] if node['type'] == 'train')['parameters'].update(
                epochs=2, widths=[4, 8, 12], input_size=32)
            graph = dataset.pipelines.save(graph['id'], {'revision': graph['revision'], 'document': changed})
            validation = dataset.pipelines.validate(graph['id'], {'revision': graph['revision']})
            run = dataset.runs.submit({'request_key': 'retained-analysis-actual-v1', 'graph_id': graph['id'],
                                       'graph_revision': graph['revision'], 'validation_token': validation['validation_token']})
            deadline = time.monotonic() + 120
            while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
                time.sleep(.1)
                run = dataset.runs.get(run['id'])
            if run['state'] != 'completed':
                raise AssertionError('Actual retained fixture did not complete: ' + str(run.get('error')))
            evidence = dataset.runs.model_evidence(run['id'])
            evaluation = next(item['sha256'] for item in run['artifacts'] if item['name'] == 'model-evidence.json')
            request = {'query_id': 'retained_checkpoint_examples', 'query_version': 1, 'run_id': run['id'],
                       'evaluation_sha256': evaluation,
                       'checkpoint_sha256': evidence['checkpoint_index']['entries'][0]['checkpoint']['sha256'],
                       'metric_id': 'accuracy', 'metric_definition_sha256': evidence['metric_definition_hashes']['accuracy'],
                       'limit': 1, 'offset': 0}
        # Secret bytes remain in a private task-owned file, never a report or argv.
        descriptor = os.open(directory / 'owner-token', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(owner.token)
        receipt = {'format': 'retained_analysis_actual_fixture_v1', 'scope': 'Authored transport fixture; no model-quality claim',
                   'catalog_path': str(dataset.path), 'catalog_id': dataset.db.dataset_id,
                   'run_id': run['id'], 'release_sha256': run['release_sha256'], 'request': request,
                   'artifacts': [{key: item[key] for key in ('name', 'sha256', 'bytes')} for item in run['artifacts']],
                   'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                       ('retained_analysis.py', 'tests/retained_analysis_actual_fixture.py', 'runs.py', 'model_evidence.py')}}
        (directory / 'fixture.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt
    finally:
        dataset.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.directory), sort_keys=True))
