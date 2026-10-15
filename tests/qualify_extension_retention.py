"""Opt-in actual A/P5 stopped retention witness; never admit or replay work.

The released source is read only. Backup/restore use the production transfer
owners; credentials and revocation are confined to the new restored database.
This is A retention, not B disable/removal or a numerical/physical acceptance.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backup_metadata as transfer
from metadata import Metadata
from qualify_scientific_restore import (compare, compact, raw_restored,
                                        save_private, snapshot, verify_backup)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def log(message):
    print(message, flush=True)


def read_receipt(path):
    require(path.is_file() and path.stat().st_size <= 1024 * 1024, 'Bounded P5 receipt required.')
    value = json.loads(path.read_bytes())
    require(value.get('format') == 'p5_field_charged_qualification_v1', 'Actual charged P5 receipt required.')
    return value


def selected_reads(dataset, receipt, *, expected=None):
    """Current bound inspector, no project roots, no executable reconstruction."""
    from runtime_snapshots import RuntimeSnapshots
    identities = [receipt[key] for key in ('source_run_id', 'package_run_id', 'verifier_run_id')]
    runs = [dataset.runs.get(identity) for identity in identities]
    require(all(run['state'] == 'completed' and run['custody_phase'] == 'drained' for run in runs),
            'Actual completed/drained Runs required.')
    require(dataset.projects.list_snapshots()['roots'] == [], 'Project roots must be absent.')
    public = dataset.runs.model_evidence(identities[0], {}, contract_version=2)
    require(public['state'] == 'verified', 'Retained scientific evidence is unavailable.')
    checkpoint = receipt['fresh_verification']['checkpoint_sha256']
    require(checkpoint in [entry['checkpoint']['sha256'] for entry in public['checkpoint_index']['entries']],
            'P5 checkpoint is absent from actual A evidence.')
    query = dict(checkpoint_sha256=checkpoint, member_ordinal=0, field_id='raw', axis='z', index=2)
    field = dataset.runs.model_evidence(identities[0], query, contract_version=2)
    require(field['field']['stage'] == 'post_train_mapping', 'Raw field stage differs.')
    package = dataset.studies.package_state(receipt['candidate_id'])
    require(package['state'] == 'fresh_verified', 'Retained package/verifier linkage differs.')
    require(any(item['run_id'] == identities[1] and item['sha256'] == receipt['package_sha256']
                for item in package['packages']), 'P5 whole package identity differs.')
    require(any(item['run_id'] == identities[2] and item['receipt'] == receipt['fresh_verification']
                for item in package['verifications']), 'P5 fresh receipt differs.')
    study = dataset.studies.get(receipt['study_id'])
    require(study['charged'] == receipt['charged'] and len(study['reservations']) == 3
            and all(row['state'] == 'settled' for row in study['reservations']),
            'Actual three-attempt Study accounting differs.')
    runtime = RuntimeSnapshots(dataset.db, dataset.access, dataset.path).get(
        receipt['runtime_snapshot']['manifest_sha256'], verify=True)
    wanted_runtime = dict(receipt['runtime_snapshot'], root=str(dataset.path / 'runtime-snapshots' /
                                                              receipt['runtime_snapshot']['manifest_sha256']))
    require(runtime == wanted_runtime, 'Retained runtime differs beyond its new catalog root.')
    artifacts = []
    for run in runs:
        for item in run['artifacts']:
            checksum, size = hashlib.sha256(), 0
            with dataset.runs.open_artifact(run['id'], item['name']) as (stream, metadata):
                while chunk := stream.read(1024 * 1024):
                    checksum.update(chunk)
                    size += len(chunk)
                require(size == metadata['bytes'] == item['bytes'] and checksum.hexdigest() == item['sha256'],
                        'Retained whole download differs.')
            artifacts.append(dict(run_id=run['id'], name=item['name'], bytes=size, sha256=checksum.hexdigest()))
    # Frozen source/model/profile inspection must also work without a live root.
    raw_run = dataset.runs._load(identities[0])
    material_ref = raw_run['extension_context']['composition']
    material = dataset.pipelines.recipe_material(material_ref, verify=True)
    model_ref = raw_run['extension_context']['static']['model']
    model = dataset.models.material(model_ref, verify=True)
    source_hashes = {}
    for item in model['material']['source_closure']:
        raw = dataset.models.read_blob(model_ref, item['blob'])
        source_hashes[item['import_path']] = hashlib.sha256(raw).hexdigest()
    result = dict(runs=runs, public=public, query=query, field=field, package=package, study=study,
                  runtime=runtime, artifacts=artifacts, material=material, model=model,
                  source_hashes=source_hashes)
    if expected is not None:
        require(result == expected, 'Cold/current authorized retained meaning differs.')
    require(dataset.runs._thread is None, 'Read-only retention started the Runs scheduler.')
    return result


def serve(dataset):
    from app import make_handler
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, 'http://127.0.0.1:' + str(server.server_port)


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    require(not thread.is_alive(), 'HTTP service did not stop.')


def inspect_restored(destination, connection, receipt, report):
    from access import AccessError
    from agent_api import AgentClient, verify_artifact
    from app import Dataset
    from auth_helpers import ExplicitOwnerFixture
    from workbench import WorkbenchError
    dataset = server = None
    # Prove reads cannot invoke a consumer, runtime, replay or Run scheduler.
    with patch('subprocess.Popen', side_effect=AssertionError('Retained reads must not execute')), \
            patch('runs.Runs._start', side_effect=AssertionError('Retained reads must not schedule')):
        try:
            dataset = Dataset(destination, dsn=connection, project_roots={})
            owner = ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                reader = dataset.access.issue({'label': 'Actual A restored retention reader', 'scopes': ['inspect']})
                successor = dataset.access.issue({'label': 'Current independent retained reader', 'scopes': ['inspect']})
            with dataset.access.bind(reader['token']):
                expected = selected_reads(dataset, receipt)
                run_id = receipt['source_run_id']
                targets = [(run_id, 'model-evidence.json'), (receipt['package_run_id'], 'package.zip'),
                           (receipt['verifier_run_id'], 'verification.json')]
                selected_checkpoint = next(entry for entry in expected['public']['checkpoint_index']['entries']
                    if entry['checkpoint']['sha256'] == expected['query']['checkpoint_sha256'])
                checkpoint_raw, _ = dataset.runs.artifact(run_id, selected_checkpoint['checkpoint']['name'])
                weights_name = json.loads(checkpoint_raw)['weights']['name']
                targets.append((run_id, weights_name))
                targets = [(identity, next(item for run in expected['runs'] if run['id'] == identity
                                          for item in run['artifacts'] if item['name'] == name)) for identity, name in targets]
                for identity, item in targets:
                    raw, _ = dataset.runs.artifact(identity, item['name'])
                    captured, capture = dataset.runs.capture_artifact(identity, item['name'], item['sha256'])
                    require(raw == captured and hashlib.sha256(raw).hexdigest() == item['sha256']
                            and capture['measured_sha256'] == item['sha256'], 'Capture/whole retained identity differs.')
                unentered = dataset.runs.open_artifact(receipt['package_run_id'], 'package.zip')
                try:
                    dataset.runs.model_evidence(run_id, {'split': 'test'}, contract_version=2)
                except WorkbenchError as error:
                    require(error.code in ('unsupported', 'invalid'), 'Unexpected test selector refusal.')
                    report['test_selector'] = {'state': 'refused', 'code': error.code}
                else:
                    raise RuntimeError('Test selector unexpectedly accepted.')
                server, thread, endpoint = serve(dataset)
                client = AgentClient(endpoint, reader['token'], dataset.db.dataset_id)
                require(client.selected_contracts()['runs.model_evidence'] == 2, 'Exact field API2 was not negotiated.')
                require(client.call('runs.model_evidence', dict(run_id=run_id, **expected['query']))['result'] == expected['field'],
                        'Real negotiated HTTP selected field differs.')
                require(client.call('studies.package_state', {'candidate_id': receipt['candidate_id']})['result'] == expected['package'],
                        'Real HTTP package state differs.')
                report['downloads'] = []
                for identity, item in targets:
                    proof = verify_artifact(client, identity, item['name'], item['sha256'], chunk_bytes=4096)
                    require(proof['bytes'] == item['bytes'], 'Whole-hash segmented HTTP length differs.')
                    request = Request(endpoint + f"/api/workspace/runs/{identity}/artifacts/{item['name']}",
                                      headers={'Authorization': 'Bearer ' + reader['token']})
                    with urlopen(request, timeout=30) as response:
                        raw = response.read(item['bytes'] + 1)
                    require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'],
                            'Whole HTTP download differs.')
                    report['downloads'].append(dict(run_id=identity, name=item['name'], **proof))
                with owner.bound(dataset):
                    dataset.access.revoke(reader['identity']['credential_id'])
                identity, item = targets[1]
                reads = {
                    'selected_field': lambda: dataset.runs.model_evidence(run_id, expected['query'], contract_version=2),
                    'whole': lambda: dataset.runs.artifact(identity, item['name']),
                    'segment': lambda: dataset.runs.artifact_segment(identity, item['name'],
                        dict(expected_sha256=item['sha256'], offset=0, max_bytes=4096)),
                    'capture': lambda: dataset.runs.capture_artifact(identity, item['name'], item['sha256']),
                    'package_state': lambda: dataset.studies.package_state(receipt['candidate_id']),
                    'model': lambda: dataset.models.material(expected['model']['ref'], verify=True),
                    'recipe': lambda: dataset.pipelines.recipe_material(material_ref_from(expected), verify=True),
                }
                report['revoked'] = []
                for label, action in reads.items():
                    try:
                        action()
                    except AccessError as error:
                        require((error.code, error.status) == ('unauthenticated', 401), 'Revoked read returned wrong refusal.')
                        report['revoked'].append(label)
                    else:
                        raise RuntimeError('Revoked read accepted: ' + label)
                try:
                    with unentered:
                        raise RuntimeError('Revoked unentered download accepted.')
                except AccessError as error:
                    require(error.status == 401, 'Revoked download refused incorrectly.')
                report['revoked'].append('unentered_download')
                for operation, body in [('runs.model_evidence', dict(run_id=run_id, **expected['query'])),
                        ('studies.package_state', {'candidate_id': receipt['candidate_id']}),
                        ('runs.artifact_chunk', dict(run_id=identity, name=item['name'], expected_sha256=item['sha256'], offset=0, max_bytes=4096))]:
                    require(client.call(operation, body)['status'] == 401, 'Revoked negotiated HTTP read accepted.')
                try:
                    urlopen(request, timeout=30)
                except HTTPError as error:
                    require(error.code == 401, 'Revoked HTTP download refused incorrectly.')
                    error.close()
                else:
                    raise RuntimeError('Revoked whole HTTP download accepted.')
            stop(server, thread)
            server = None
            dataset.close()
            dataset = Dataset(destination, dsn=connection, project_roots={})
            try:
                with dataset.access.bind(reader['token']):
                    raise RuntimeError('Revoked credential rebound after cold reopen.')
            except AccessError as error:
                require(error.status == 401, 'Cold revoked credential refused incorrectly.')
            with dataset.access.bind(successor['token']):
                selected_reads(dataset, receipt, expected=expected)
            report.update(artifact_inventory=expected['artifacts'], selected_field_sha256=transfer.digest(expected['field']),
                          public_evidence_sha256=transfer.digest(expected['public']),
                          package_state_sha256=transfer.digest(expected['package']),
                          source_hashes=expected['source_hashes'], charged=expected['study']['charged'],
                          root_absent=True, cold_reopen=True, execution_blocked=True)
        finally:
            if server is not None:
                stop(server, thread)
            if dataset is not None:
                dataset.close()


def material_ref_from(expected):
    material = expected['material']
    return material['ref']


def main(args):
    require(args.quiesced, 'Explicit released catalog/stopped-writers assertion --quiesced is required.')
    source = args.source.resolve()
    output = args.output.resolve()
    transfer.separate_paths(source, output)
    output.mkdir(parents=True, exist_ok=False)
    receipt = read_receipt(args.p5_receipt)
    connection = os.environ['TULDOK_DATABASE_URL']
    report = dict(format='extension_a_retention_qualification_v1', state='in_progress', source=str(source),
                  output=str(output), driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  host_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  p5_receipt_sha256=transfer.file_hash(args.p5_receipt),
                  source_run_id=receipt['source_run_id'], package_run_id=receipt['package_run_id'],
                  verifier_run_id=receipt['verifier_run_id'], candidate_id=receipt['candidate_id'],
                  package_sha256=receipt['package_sha256'], started_unix=time.time(),
                  scope='Actual A stopped retention only; no B disable/removal, replay, numerical or physical acceptance.')
    database = 'tuldok_a_retention_' + uuid.uuid4().hex
    created = False
    try:
        log('Inventory released source and verify stopped worker locks/custody')
        base = snapshot(source, connection)
        require(base['dataset_id'] == receipt['runtime_snapshot']['catalog_id'], 'P5/source catalog mismatch.')
        require(base['run_states'] == {receipt[key]: 'completed' for key in
                ('source_run_id', 'package_run_id', 'verifier_run_id')}, 'Actual source must contain exactly the three completed P5 Runs.')
        save_private(output / 'baseline.private.json', base)
        report['baseline'] = compact(base)
        required = 2 * sum(entry.get('bytes', 0) for entry in base['files'].values()) + 1024**3
        require(shutil.disk_usage(output).free > required, 'Keep backup/restore plus 1 GiB operational reserve.')
        backup = output / 'stopped-backup'
        log('Create production stopped backup; verify every byte/mode and SQL row')
        transfer.backup_catalog(source, backup, dsn=connection, quiesced=True)
        report['backup'] = verify_backup(backup, base)
        with psycopg.connect(connection, autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        created = True
        restored_connection = make_conninfo(connection, dbname=database)
        destination = output / 'restored-catalog'
        log('Restore into fresh PostgreSQL/database directory and reconcile raw state before owner login')
        transfer.restore_catalog(backup, destination, dsn=restored_connection)
        _, restored = raw_restored(backup, destination, base, restored_connection)
        report['raw_restore'] = compact(restored)
        log('Inspect actual A fields/package/runtime without project roots; revoke current reader and reopen cold')
        inspect_restored(destination, restored_connection, receipt, report)
        final = snapshot(destination, restored_connection,
                         exclude=tuple(path.name for path in destination.glob('.restore-receipt-*.json')))
        # Owner/reader issuance and read/denial audit records are expected only on
        # the restored copy. All domain documents and finite charges stay exact.
        immutable = [name for name in base['tables'] if name not in
                     ('access_actors', 'access_credentials', 'access_audit')]
        require(all(final['tables'][name] == base['tables'][name] for name in immutable),
                'Retention reads changed domain/grant/reservation/consumption state.')
        require(final['files'] == base['files'] and final['modes'] == base['modes']
                and final['custody'] == base['custody'], 'Retained files/modes/custody changed after inspection.')
        compare(snapshot(source, connection), base)
        report.update(state='passed', source_unchanged=True, immutable_tables=immutable,
                      restored_database=database, restored_database_retained=True,
                      finished_unix=time.time())
        save_private(output / 'report.json', report)
        log('PASS actual A retention ' + str(output))
    except BaseException as error:
        report.update(state='failed', error_type=type(error).__name__, failure=str(error),
                      restored_database=database if created else None)
        save_private(output / 'failure.json', report)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--p5-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quiesced', action='store_true')
    main(parser.parse_args())
