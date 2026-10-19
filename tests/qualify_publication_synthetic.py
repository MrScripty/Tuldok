"""Real custody and semantic recovery of explicitly synthetic field evidence.

This opt-in qualification provisions a fresh disposable PostgreSQL catalog and
captures an explicitly nominated existing CPU runtime. The child only serializes
fixture states. No numerical producer, optimizer, training or oracle is executed.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg
from psycopg import sql

from app import Dataset
from auth_helpers import ExplicitOwnerFixture
from pipeline import digest
import recipe_process
from runtime_snapshots import RuntimeSnapshots
from workbench import WorkbenchError, encode

PACKAGE = ROOT / 'examples/extensions/field-surrogate/v2'
PUBLICATION_RESERVE = 512 * 1024**2
SCOPE = 'Synthetic serialization through real CPU custody and semantic recovery; no training or numerical acceptance'

PRODUCER = r'''"""Synthetic protocol serialization only: counters are fixture labels, not optimizer updates."""
import json
from pathlib import Path
import struct
import sys
from evidence_writer import Evidence

def npy(values, shape):
    header = repr({'descr': '<f8', 'fortran_order': False, 'shape': tuple(shape)}).encode('ascii')
    header += b' ' * ((-(10 + len(header) + 1)) % 16) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack('<' + 'd' * len(values), *values)

fixture_path, context_path, output_path = map(Path, sys.argv[1:])
fixture = json.loads(fixture_path.read_bytes())
writer = Evidence(output_path, context_path.read_bytes())
member = next(row for row in fixture['cases'] if row['id'] == fixture['probe_member_id'])
(output_path / 'transform.npy').write_bytes(npy([0, 1], [2]))
writer.transform('transform.npy')
(output_path / 'input-initial.npy').write_bytes(npy(member['initial'], [4, 4, 4]))
(output_path / 'reference.npy').write_bytes(npy(member['target'], [4, 4, 4]))
for label in (16, 32, 48, 64):
    (output_path / f'weights-{label}.npy').write_bytes(npy([0, 0], [2]))
    (output_path / f'prediction-{label}.npy').write_bytes(npy(member['target'], [4, 4, 4]))
    clocks = {'optimizer_update': label, 'epoch': None, 'fit_pass': None,
              'physical_time': None, 'wall_elapsed_ms': label}
    writer.checkpoint(label, clocks, f'weights-{label}.npy',
                      {metric['id']: 0 for metric in writer.policy['metric_definitions']})
writer.finish()
writer.write('diagnostics.json', {'scope': 'synthetic serialization only; no training',
    'clock_values': 'protocol fixture labels, not measured optimizer updates or elapsed time',
    'numerical_acceptance': 'not_evaluated'})
print('synthetic_serialization_complete_no_training', flush=True)
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def project_fixture(root, runtime_sha):
    """New source/recipe/model identities; preserve the original example bytes."""
    root.mkdir()
    definition = json.loads((PACKAGE / 'recipe.json').read_bytes())
    payloads = {row['path']: (PACKAGE / row['path']).read_bytes() for row in definition['sources']
                if row['path'] != 'producer.py'}
    payloads['synthetic_producer.py'] = PRODUCER.encode()
    provider = json.loads(payloads['extension.json'])
    provider['package']['version'] = '2.0.1'
    provider['label'] = 'Synthetic publication recovery protocol fixture; no training'
    provider['runtime']['snapshot_sha256'] = runtime_sha
    provider['sources'] = [{'path': name, 'sha256': sha(payloads[name]), 'bytes': len(payloads[name])}
                           for name in ('synthetic_producer.py', 'evidence_writer.py')]
    payloads['extension.json'] = encode(provider).encode()
    for name, raw in payloads.items():
        (root / name).write_bytes(raw)
    (root / 'fixture.json').write_bytes((PACKAGE / 'fixture.json').read_bytes())
    definition.update(id='synthetic-publication-recovery', name=SCOPE, entrypoint='synthetic_producer.py',
                      runtime_snapshot_sha256=runtime_sha, parameters={})
    definition['sources'] = [{'path': name, 'sha256': sha(raw)} for name, raw in sorted(payloads.items())]
    policy = definition['model_evidence']
    policy['adapter_sha256'] = digest(definition['sources'])
    policy['model_specification'] = {'format': 'synthetic_serialization_fixture_v1',
        'trainable_parameters': [], 'input_fields': ['initial'], 'output_fields': ['prediction'],
        'scope': 'Synthetic protocol states only; no fitted or trained model'}
    policy['profile'].update(id='synthetic.publication-recovery', revision=1)
    for metric in policy['metric_definitions']:
        metric.update(id='synthetic_fixture_constant', reduction='constant_fixture_label_no_numerical_measurement',
                      evaluator_sha256=policy['adapter_sha256'])
    for field in policy['fields']:
        field['contract']['source_sha256'] = policy['adapter_sha256']
    raw = encode(definition).encode()
    (root / 'recipe.json').write_bytes(raw)
    manifest = json.loads((PACKAGE / 'project.json').read_bytes())
    import uuid
    manifest.update(id=uuid.uuid4().hex, name='Synthetic publication recovery; no science claim')
    manifest['recipes'][0].update(id='synthetic', label='Synthetic serialization only', sha256=sha(raw))
    (root / 'project.json').write_bytes(encode(manifest).encode())
    return definition, manifest, sha(raw)


def counts(dataset):
    return {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            for table in ('workspace_runs', 'access_execution_grants',
                          'access_execution_consumptions', 'model_attempt_reservations')}


def qualify(args, receipt):
    require(bool(os.environ.get('TULDOK_DATABASE_URL')), 'Set the disposable PostgreSQL DSN explicitly')
    require(args.reserve_bytes >= PUBLICATION_RESERVE + 16 * 1024**2,
            'Owner-selected runtime reserve must retain publication floor and bounded fixture headroom')
    config = json.loads(args.runtime_config.read_bytes())
    receipt.update(scope=SCOPE, base='6cc594389659b15ae2d8cf677c3d8f8c46be61ea',
        expected_runtime_sha256=args.expected_runtime_sha256, runtime_config_sha256=sha(args.runtime_config.read_bytes()),
        owner_selected_reserve_bytes=args.reserve_bytes, publication_reserve_bytes=PUBLICATION_RESERVE,
        training_executed=False, numerical_acceptance='not_evaluated', checks=[])
    receipt['source_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dataset = None
    schema = None
    with tempfile.TemporaryDirectory(prefix='tuldok-publication-synthetic-', dir=args.temporary_parent) as temporary:
        root = Path(temporary)
        receipt['temporary_root'] = str(root)
        definition, manifest, recipe_sha = project_fixture(root / 'project', args.expected_runtime_sha256)
        receipt.update(producer_sha256=sha(PRODUCER.encode()), recipe_sha256=recipe_sha,
                       output_file_count=len(definition['outputs']), output_bound_bytes=definition['resources']['max_output_bytes'])
        try:
            dataset = Dataset(root / 'catalog', project_roots={'synthetic': root / 'project'})
            schema = dataset.db.schema
            owner = ExplicitOwnerFixture.bootstrap(dataset)
            with owner.bound(dataset):
                snapshots = RuntimeSnapshots(dataset.db, dataset.access, dataset.path)
                print('Inspecting explicitly nominated runtime', flush=True)
                inventory = snapshots.inspect(config)
                required = inventory['total_bytes'] + inventory['manifest_bytes'] + args.reserve_bytes
                receipt['capture_capacity'] = {'free_bytes': inventory['free_bytes'], 'required_bytes': required,
                    'payload_bytes': inventory['total_bytes'], 'manifest_bytes': inventory['manifest_bytes']}
                require(inventory['inventory_sha256'] == args.expected_runtime_sha256,
                        'Current runtime differs from exact nomination; no fallback')
                require(inventory['free_bytes'] >= required, 'Insufficient space for fresh capture and selected reserve')
                print('Capturing runtime into fresh disposable catalog', flush=True)
                descriptor = snapshots.create(config, args.expected_runtime_sha256, quiesced=True,
                                              reserve_bytes=args.reserve_bytes)
                receipt['runtime'] = {key: descriptor[key] for key in
                    ('manifest_sha256', 'manifest_bytes', 'file_count', 'total_bytes', 'packages')}
                receipt['free_after_capture_bytes'] = shutil.disk_usage(dataset.path).free
                project = dataset.projects.open_snapshot({'root': 'synthetic', 'manifest_path': 'project.json'})
                graph = dataset.pipelines.create_external({'name': SCOPE, 'project_id': project['id'],
                    'recipe_id': 'synthetic', 'expected_sha256': recipe_sha,
                    'inputs': {'fixture': {'reference_id': 'fixture', 'expected_sha256': manifest['data'][0]['sha256']}}})
                policy = definition['model_evidence']
                draft = dataset.models.create({'name': SCOPE, 'kind': 'captured_source',
                    'task': {'kind': 'task', 'catalog_id': dataset.db.dataset_id, 'id': policy['task']['id'],
                             'revision': policy['task']['revision'], 'sha256': digest(policy['task']['definition'])},
                    'specification': policy['model_specification'], 'preprocessing_policy': policy['preprocessing_policy'],
                    'output_policy': policy['output_policy'], 'source_selector': {'project_id': project['id'],
                    'recipe_id': 'synthetic', 'expected_sha256': recipe_sha}})
                model = dataset.models.publish(draft['id'], {'revision': draft['revision']})
                selection = {'format': 'selection_policy_v1', 'metric_definition_sha256': digest(policy['metric_definitions'][0]),
                    'checkpoint_rule': 'last', 'replicate_reduce': 'individual',
                    'required_capabilities': policy['profile']['required_capabilities'],
                    'numerical_acceptance': 'diagnostic', 'tie_break': 'trial_id'}
                study = dataset.studies.create({'name': SCOPE, 'policy': selection, 'limits': {'attempt_slots': 1,
                    'admitted_wall_seconds': 600, 'retained_bytes': 64 * 1024**2, 'peak_staging_bytes': 64 * 1024**2}})
                trial = dataset.studies.prepare_trial(study['id'], {'request_key': 'synthetic-prepare-request',
                    'revision': study['revision'], 'graph_id': graph['id'], 'graph_revision': graph['revision'],
                    'model': model['ref'], 'replicate': 0})
                current = dataset.studies.get(study['id'])['study']
                dataset.studies.continue_study(study['id'], {'request_key': 'synthetic-open-request',
                    'revision': current['revision'], 'admission_epoch': current['admission_epoch']})
                grant = dataset.studies.approve(study['id'], {'trial_id': trial['id'],
                    'expected_material_sha256': trial['material']['sha256'], 'consumer_actor_id': owner.identity['actor_id']})
                current = dataset.studies.get(study['id'])['study']
                with patch.object(dataset.runs, '_start'):
                    admitted = dataset.studies.admit(study['id'], {'request_key': 'synthetic-admit-request',
                        'revision': current['revision'], 'admission_epoch': current['admission_epoch'],
                        'trial_id': trial['id'], 'approval_id': grant['id']})
                run = dataset.runs._load(admitted['run']['id'])
                copy_output = dataset.runs._copy_verified
                injected = []
                def copy_fault(directory, name, item, output=None, **kwargs):
                    if output is not None and not injected:
                        injected.append(True)
                        raise OSError('Authored publication copy fault after real synthetic serialization')
                    return copy_output(directory, name, item, output, **kwargs)
                print('Executing synthetic serialization through actual custodian', flush=True)
                with patch.object(dataset.runs, '_copy_verified', side_effect=copy_fault):
                    dataset.runs._run_attempt(run, (dataset.runs._capacity.cores[0],), dataset.runs._capacity.claim(run))
                require(injected, 'Execution did not reach the intended publication copy fault')
                saved = dataset.runs._load(run['id'])
                require(saved['state'] == 'interrupted' and saved['custody_phase'] == 'drained', 'Original attempt did not drain')
                require(saved['publication_fault']['code'] == 'unavailable', 'Expected recoverable copy fault was not retained')
                stage = dataset.runs._external_directory(saved)
                custody_raw = (stage / 'custody/receipt.json').read_bytes()
                custody = recipe_process.validate_receipt(custody_raw, saved['custody_identity'])
                require(custody['outcome'] == 'completed' and custody['drained'], 'Synthetic child did not complete/drain')
                stdout = (stage / 'custody/stdout.log').read_bytes()
                require(len(stdout) == custody['streams']['stdout']['bytes'] and sha(stdout) == custody['streams']['stdout']['sha256'],
                        'Actual child output differs from retained custody')
                require(b'synthetic_serialization_complete_no_training' in stdout, 'Synthetic producer completion marker missing')
                runtime_reports = [json.loads(line)['tuldok_cpu_runtime'] for line in stdout.decode().splitlines()
                                   if line.startswith('{"tuldok_cpu_runtime":')]
                require(len(runtime_reports) == 1, 'Actual captured runtime launch proof missing')
                launch = runtime_reports[0]
                require(launch['snapshot_sha256'] == descriptor['manifest_sha256'] and
                        launch['packages'] == {name: descriptor['packages'][name] for name in ('torch', 'numpy')},
                        'Actual child used a different captured runtime')
                receipt['custody'] = {'sha256': sha(custody_raw), 'outcome': custody['outcome'],
                    'drained': custody['drained'], 'leader_returncode': custody['leader_returncode'],
                    'runtime_snapshot_sha256': launch['snapshot_sha256'], 'runtime_packages': launch['packages'],
                    'synthetic_complete_marker': True}
                original_events = copy.deepcopy(saved['events'])
                source_ref = saved['publication_source']
                baseline_counts = counts(dataset)
                before = dataset.studies.reconcile(study['id'])
                reservation = dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s',
                                                (run['id'],)).fetchone()[0]
                require(before['reservations'][0]['state'] == 'settled', 'Original reservation did not settle')
            dataset.close()
            dataset = Dataset(root / 'catalog', project_roots={'synthetic': root / 'project'})
            with owner.bound(dataset):
                semantic = dataset.runs._verify_extension
                verified_paths = []
                def verify(directory, value, **kwargs):
                    result = semantic(directory, value, **kwargs)
                    require(result['state'] == 'verified', 'Actual extension semantics did not verify')
                    verified_paths.append(str(Path(directory).relative_to(dataset.runs.path)))
                    return result
                body = {'run_id': run['id'], 'source_ref': source_ref, 'request_key': 'synthetic-recovery-request'}
                print('Recovering original Run with real source/destination semantic verification', flush=True)
                with patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')), \
                        patch.object(dataset.runs, '_verify_extension', side_effect=verify):
                    recovered = dataset.runs.recover_publication(body)
                    result = dataset.runs.publication_result(recovered['result_ref'])
                    diagnostics = next(row for row in result['artifacts'] if row['name'] == 'diagnostics.json')
                    raw, _ = dataset.runs.publication_artifact(recovered['result_ref'], diagnostics['name'], diagnostics['sha256'])
                    require(json.loads(raw)['numerical_acceptance'] == 'not_evaluated', 'Synthetic scope was lost')
                    require(dataset.runs.recover_publication(body) == recovered, 'Same request did not converge')
                require('.external-' + run['id'] + '/output' in verified_paths, 'Source semantics were bypassed')
                require(run['id'] in verified_paths, 'Destination/reader semantics were bypassed')
                if args.publication_interfaces:
                    qualify_interfaces(dataset, owner, recovered['result_ref'], root, receipt)
                require(counts(dataset) == baseline_counts, 'Recovery changed Run/grant/reservation counts')
                after = dataset.studies.reconcile(study['id'])
                require(after['charged'] == before['charged'] and after['reservations'] == before['reservations'],
                        'Recovery changed conservative Study accounting')
                require(dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s',
                        (run['id'],)).fetchone()[0] == reservation, 'Reservation document changed')
                cold = dataset.runs._load(run['id'])
                require(cold['state'] == saved['state'] and cold['events'] == original_events, 'Original outcome/events changed')
                try:
                    dataset.runs.artifact(run['id'], 'diagnostics.json')
                except WorkbenchError:
                    pass
                else:
                    raise AssertionError('Legacy failed-Run artifact reader accepted recovered bytes')
                try:
                    legacy = dataset.runs.model_evidence(run['id'], {})
                except WorkbenchError as error:
                    require((error.code, error.status) == ('unavailable', 409), 'Unexpected legacy evidence refusal')
                else:
                    require(legacy['state'] != 'verified', 'Legacy evidence gate widened')
                try:
                    dataset.studies.select_candidate(study['id'], {'request_key': 'synthetic-candidate-refusal',
                        'revision': after['study']['revision'], 'trial_id': trial['id'], 'run_id': run['id']})
                except WorkbenchError:
                    pass
                else:
                    raise AssertionError('Legacy candidate promotion accepted the interrupted Run')
                receipt.update(catalog_id=dataset.db.dataset_id, run_id=run['id'], original_state=cold['state'],
                    source_ref=source_ref, result_ref=recovered['result_ref'], artifact_count=len(result['artifacts']),
                    semantic_verification_paths=verified_paths, charged=after['charged'], counts=baseline_counts,
                    checks=['real_runtime_capture', 'real_model_study_context_custody', 'frozen_source_after_copy_fault',
                            'cold_same_run_recovery', 'real_source_destination_reader_semantics', 'no_compute_replay',
                            'exact_idempotence', 'unchanged_counts_reservation_charge_events',
                            'legacy_failed_readers_and_candidate_promotion_refuse'])
        finally:
            if dataset is not None:
                dataset.close()
            if schema is not None:
                with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
                    connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                receipt['temporary_schema_removed'] = True


def qualify_interfaces(dataset, owner, ref, root, receipt):
    """Actual Ref query/comparison and sealed CLI SDK; only synthetic values."""
    from http.server import ThreadingHTTPServer
    import threading
    import agent_api
    from app import make_handler
    inspector = dataset.access.issue({'label': 'Synthetic publication evidence inspector', 'scopes': ['inspect']})
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    try:
        endpoint = 'http://127.0.0.1:' + str(server.server_port)
        client = agent_api.AgentClient(endpoint, inspector['token'], dataset.db.dataset_id)
        with patch('recipe_process.launch', side_effect=AssertionError('Evidence query/comparison replayed compute')):
            response = client.call('runs.publication_model_evidence', {'ref': ref})
            require(response['status'] == 200 and response['result']['result_ref'] == ref, 'Exact HTTP evidence Ref differs')
            evidence = response['result']['evidence']
            require(evidence['state'] == 'verified', 'Recovered synthetic evidence did not verify over HTTP')
            entries = evidence['checkpoint_index']['entries']; metric = evidence['metric_definitions'][0]
            selectors = {'checkpoint_sha256': entries[0]['checkpoint']['sha256'], 'member_ordinal': 0,
                         'field_id': evidence['fields'][0]['field_id'], 'axis': 'z', 'index': 0}
            field = client.call('runs.publication_model_evidence', {'ref': ref, 'selectors': selectors})
            require(field['status'] == 200 and field['result']['evidence']['field']['prediction'] ==
                    field['result']['evidence']['field']['reference'], 'Synthetic exact field slice differs')
            result = dataset.runs.publication_result(ref)
            evaluation = next(item['sha256'] for item in result['artifacts'] if item['name'] == 'model-evidence.json')
            selection = {'checkpoint_sha256': entries[0]['checkpoint']['sha256'],
                'other_checkpoint_sha256': entries[-1]['checkpoint']['sha256'], 'evaluation_sha256': evaluation,
                'other_evaluation_sha256': evaluation, 'metric_id': metric['id'],
                'metric_definition_sha256': evidence['metric_definition_hashes'][metric['id']],
                'other_metric_definition_sha256': evidence['metric_definition_hashes'][metric['id']], 'mode': 'paired'}
            compared = client.call('runs.compare_publication_evidence', {'ref': ref, 'other_ref': ref, 'selection': selection})
            require(compared['status'] == 200 and compared['result']['result_refs'] == [ref, ref], 'Exact comparison Refs differ')
            comparison = compared['result']['comparison']
            require(comparison['state'] == 'compatible' and comparison['delta']['value'] == 0,
                    'Synthetic fixture comparison arithmetic differs; no science inference is intended')
            refused = client.call('runs.compare_publication_evidence', {'ref': ref, 'other_ref': ref,
                'selection': dict(selection, evaluation_sha256='f' * 64)})
            require(refused['status'] == 409 and refused['result']['code'] == 'stale', 'Foreign evaluation was accepted')
            token_path = root / 'inspector-token'; token_path.write_text(inspector['token']); token_path.chmod(0o600)
            config_path = root / 'inspector-config.json'
            config_path.write_text(encode({'endpoint': endpoint, 'catalog_id': dataset.db.dataset_id, 'token_file': str(token_path)}))
            config_path.chmod(0o600)
            ref_path = root / 'result-ref.json'; ref_path.write_text(encode(ref))
            selection_path = root / 'comparison-selection.json'; selection_path.write_text(encode(selection))
            sdk = subprocess.run([sys.executable, '-m', 'tuldok_extension_sdk', 'compare-publication',
                '--config', str(config_path), '--cli', str(ROOT / 'project_cli.py'),
                '--cli-sha256', sha((ROOT / 'project_cli.py').read_bytes()), '--ref', str(ref_path),
                '--other-ref', str(ref_path), '--selection', str(selection_path), '--deadline-seconds', '120'],
                cwd=ROOT, capture_output=True, timeout=130)
            require(sdk.returncode == 0, 'Sealed public-CLI SDK comparison refused: ' + sdk.stdout.decode()[:500])
            sdk_result = json.loads(sdk.stdout)
            require(sdk_result['state'] == 'compared' and sdk_result['result_refs'] == [ref, ref]
                    and sdk_result['numerical'] == 'not_evaluated', 'SDK exact comparison result differs')
        receipt['publication_interfaces'] = {'http_evidence': 'verified', 'http_exact_field_slice': 'verified',
            'exact_ref_paired_comparison': 'compatible_synthetic_fixture_only', 'foreign_evaluation': 'refused_stale',
            'sealed_cli_sdk_comparison': 'compared', 'numerical_acceptance': 'not_evaluated'}
    finally:
        server.shutdown(); server.server_close(); worker.join(5)
        require(not worker.is_alive(), 'Qualification HTTP server did not drain')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config', required=True, type=Path)
    parser.add_argument('--expected-runtime-sha256', required=True)
    parser.add_argument('--reserve-bytes', required=True, type=int)
    parser.add_argument('--temporary-parent', type=Path, default=Path('/workspace'))
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--publication-interfaces', action='store_true', help='Also qualify current selected evidence/compare and SDK interfaces')
    args = parser.parse_args()
    receipt = {'state': 'in_progress', 'driver_sha256': sha(Path(__file__).read_bytes())}
    started = time.monotonic()
    try:
        qualify(args, receipt)
        receipt['state'] = 'passed'
        print('PASS synthetic semantic recovery; no training or numerical acceptance', flush=True)
    except BaseException as error:
        receipt.update(state='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        receipt['seconds'] = round(time.monotonic() - started, 3)
        if 'temporary_root' in receipt:
            receipt['temporary_catalog_removed'] = not Path(receipt['temporary_root']).exists()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
