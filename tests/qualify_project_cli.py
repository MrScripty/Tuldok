"""Explicit real-project CLI qualification through production HTTP and custody.

Stage fixtures select existing recipes/inputs. This driver owns no model reader,
optimizer, physics or acceptance thresholds. Its report proves managed custody;
the selected project's receipts require separate numerical interpretation.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler


def write_json(path, value):
    with Path(path).open('x') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def private_file(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(value)


def qualify(catalog, project, manifest_path, stages, output, timeout=900):
    output.mkdir(parents=False, exist_ok=False)
    report = {'scope': 'Production CLI/HTTP/exact grant/captured runtime/Run/artifact/reopen custody; numerical meaning stays project-owned',
              'stages': [], 'checks': []}
    dataset = server = owner = credential = None
    worker = None

    def start():
        nonlocal dataset, server, owner, worker
        dataset = Dataset(catalog, project_roots={'qualification': project})
        owner = dataset.access.exchange(dataset.access._local_owner_token(require_existing=True))
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        return f'http://127.0.0.1:{server.server_port}'

    def stop():
        nonlocal server, dataset, worker, owner
        if server is not None:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            server = worker = None
        if dataset is not None:
            if owner is not None:
                with dataset.access.bind(owner['token']):
                    dataset.access.revoke(owner['identity']['credential_id'])
            dataset.close()
            dataset = owner = None

    def config_for(endpoint, name):
        path = output / name
        private_file(path, json.dumps({'endpoint': endpoint, 'catalog_id': report['catalog_id'],
                                      'token_file': str(output / 'agent-token.private')}))
        return path

    def cli(*args):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'project_cli.py'),
            '--config', str(config), *map(str, args)], capture_output=True, text=True, timeout=300)
        if credential['token'] in result.stdout + result.stderr:
            raise RuntimeError('CLI disclosed its credential')
        if result.returncode:
            raise RuntimeError('CLI operation refused: ' + result.stderr[:2000])
        return json.loads(result.stdout)

    try:
        endpoint = start()
        report['catalog_id'] = dataset.db.dataset_id
        with dataset.access.bind(owner['token']):
            credential = dataset.access.issue({'label': 'Explicit project CLI qualification',
                'scopes': ['inspect', 'edit', 'execute', 'cancel']})
        private_file(output / 'agent-token.private', credential['token'])
        report['actor_id'] = credential['identity']['actor_id']
        config = config_for(endpoint, 'agent-config.private')
        opened = cli('open', '--root', 'qualification', '--manifest', manifest_path)
        write_json(output / 'opened-project.json', opened)
        report['project_id'], report['manifest_sha256'] = opened['id'], opened['manifest_sha256']
        manifest_raw = (project / manifest_path).read_bytes()
        if hashlib.sha256(manifest_raw).hexdigest() != opened['manifest_sha256']:
            raise RuntimeError('Local fixture manifest differs from the registered bytes')
        manifest = json.loads(manifest_raw)
        references = {entry['id']: entry for entry in manifest['data']}
        recipes = {entry['id']: entry for entry in manifest['recipes']}
        completed = {}
        for index, stage in enumerate(stages):
            label = stage['name']
            directory = output / f'stage-{index:02d}'
            directory.mkdir()
            recipe = recipes[stage['recipe_id']]
            inputs = {}
            for slot, binding in stage['inputs'].items():
                if isinstance(binding, str):
                    reference = references[binding]
                    inputs[slot] = {'reference_id': binding, 'expected_sha256': reference['sha256']}
                else:
                    prior = completed[binding['stage']]
                    item = next(item for item in prior['artifacts'] if item['name'] == binding['artifact'])
                    inputs[slot] = {'kind': 'run_artifact', 'run_id': prior['id'],
                                    'artifact_name': item['name'], 'expected_sha256': item['sha256']}
            body = dict(name=label, project_id=opened['id'], recipe_id=recipe['id'],
                        expected_sha256=recipe['sha256'], inputs=inputs,
                        parameters=stage.get('parameters', {}))
            write_json(directory / 'graph-arguments.json', body)
            graph = cli('prepare', '--arguments', directory / 'graph-arguments.json')
            write_json(directory / 'graph.json', graph)
            preflight = cli('preflight', '--graph-id', graph['id'], '--revision', graph['revision'])
            write_json(directory / 'preflight.json', preflight)
            if not preflight['valid']:
                raise RuntimeError('Preflight is not valid')
            with dataset.access.bind(owner['token']):
                approval = dataset.runs.approve_external({'graph_id': graph['id'], 'graph_revision': graph['revision'],
                    'expected_digest': preflight['material_sha256'], 'consumer_actor_id': credential['identity']['actor_id']})
            write_json(directory / 'approval.json', approval)
            submission = dict(request_key='project-qualification-' + uuid.uuid4().hex,
                graph_id=graph['id'], graph_revision=graph['revision'],
                expected_digest=preflight['material_sha256'], approval_id=approval['id'])
            write_json(directory / 'submission.json', submission)
            run = cli('submit', '--arguments', directory / 'submission.json')
            print('ADMITTED', label, run['id'], flush=True)
            deadline = time.monotonic() + timeout
            while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
                time.sleep(.5)
                run = cli('status', '--run-id', run['id'])
            write_json(directory / 'run.json', run)
            progress = cli('status', '--run-id', run['id'], '--progress')
            write_json(directory / 'progress.json', progress)
            if run['state'] != 'completed' or run['custody_phase'] != 'drained':
                raise RuntimeError('Managed attempt did not complete: ' + run['id'] + ' ' + run['state'])
            downloads = []
            destination = directory / 'artifacts'
            destination.mkdir()
            for item in run['artifacts']:
                receipt = cli('download', '--run-id', run['id'], '--name', item['name'],
                    '--expected-sha256', item['sha256'], '--out', destination / item['name'])
                if receipt['verification'] != 'whole_sha256_verified' or receipt['bytes'] != item['bytes']:
                    raise RuntimeError('Artifact verification receipt differs')
                downloads.append(receipt)
            completed[label] = run
            report['stages'].append({'name': label, 'run_id': run['id'], 'graph_id': graph['id'],
                'material_sha256': preflight['material_sha256'], 'approval_id': approval['id'],
                'runtime_snapshot_sha256': preflight['material']['cpu_snapshot']['manifest_sha256'],
                'state': run['state'], 'custody_phase': run['custody_phase'], 'artifacts': downloads})
        report['checks'].append('All supplied stages completed under exact actor-bound one-use grants and captured CPU custody; complete CLI downloads verified.')
        stop()
        endpoint = start()
        config = config_for(endpoint, 'reopened-agent-config.private')
        for index, stage in enumerate(report['stages']):
            run = cli('status', '--run-id', stage['run_id'])
            if run['state'] != 'completed':
                raise RuntimeError('Reopened Run is not completed')
            destination = output / f'reopened-stage-{index:02d}'
            destination.mkdir()
            for item in run['artifacts']:
                cli('download', '--run-id', run['id'], '--name', item['name'],
                    '--expected-sha256', item['sha256'], '--out', destination / item['name'])
                first = output / f'stage-{index:02d}' / 'artifacts' / item['name']
                if hashlib.sha256(first.read_bytes()).digest() != hashlib.sha256((destination / item['name']).read_bytes()).digest():
                    raise RuntimeError('Reopened downloaded bytes differ')
        report['checks'].append('Catalog/service reopen preserves every completed Run and exact whole-hash-verified artifact through the CLI; no replay.')
        write_json(output / 'receipt.json', report)
        print('PASS managed project CLI qualification', output, flush=True)
        return report
    except BaseException as error:
        report['failure'] = str(error)
        write_json(output / 'failure.json', report)
        raise
    finally:
        if dataset is not None and credential is not None:
            with dataset.access.bind(owner['token']):
                dataset.access.revoke(credential['identity']['credential_id'])
        stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--manifest', default='project.json')
    parser.add_argument('--stages', type=Path, required=True,
                        help='Explicit authored stage fixture; string inputs select project refs, stage/artifact inputs select completed outputs')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    qualify(args.catalog.resolve(), args.project.resolve(), args.manifest,
            json.loads(args.stages.read_text()), args.output.resolve())
