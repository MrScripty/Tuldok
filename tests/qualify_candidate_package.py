"""Verify actual downloaded bytes using only package and approved captured runtime.

Requires a trusted expected whole SHA (argument or sibling package-result.json).
Use --mask-path for the original checkout and model cache to obtain filesystem
absence evidence. This standalone consumer is explicit; production automation
uses prepare_verifier_project and ordinary approved study admission instead.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidate_packages


def qualify_production(catalog, snapshot_descriptor, output, fixture_path=None):
    """Actual train→candidate→package→HTTP download→charged captured verifier.

    The catalog is explicitly provisioned disposable qualification state; an
    existing authored RGB fixture is reusable. No completion rows are injected.
    """
    import copy
    import os
    import threading
    import time
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from app import Dataset, make_handler
    from auth_helpers import ExplicitOwnerFixture
    from qualify_model_development import populate, freeze
    p = candidate_packages
    backend = Path(__file__).resolve().parents[1]
    fixture_path = fixture_path or backend / 'tests/fixtures/model_development/fixture.json'
    out = Path(output).resolve()
    out.mkdir(mode=448, parents=True, exist_ok=False)
    descriptor = p.decode(Path(snapshot_descriptor).read_bytes())
    dataset = Dataset(catalog, project_roots={'qualification': out})
    if descriptor['catalog_id'] != dataset.db.dataset_id:
        dataset.close()
        raise ValueError('Runtime descriptor belongs to another qualification catalog.')
    owner = ExplicitOwnerFixture.bootstrap(dataset)
    server = None
    phases = []
    original_capture = dataset.pipelines.prepare_external_material

    def measured_capture(*args, **kwargs):
        assert not dataset.db.in_transaction, 'Capture entered a DB transaction'
        phases.append({'owner': 'Pipeline.prepare_external_material', 'in_transaction': dataset.db.in_transaction})
        return original_capture(*args, **kwargs)
    dataset.pipelines.prepare_external_material = measured_capture
    try:
        with owner.bound(dataset):
            fixture = json.loads(fixture_path.read_text())
            existing = dataset.db.execute('SELECT id FROM samples').fetchall()
            rows = [dataset.workbench.get(row[0]) for row in existing] if existing else populate(dataset, fixture)
            release = freeze(dataset, rows)
            definitions = dataset.pipelines.definitions()
            template = next((x for x in definitions['recipes'] if x['id'] == 'image_classification_model_v2'))['model_template']
            template = copy.deepcopy(template)
            template['name'] = 'P5 actual inference source'
            template['specification'].update(widths=[8, 12, 16], input_size=32)
            template['preprocessing_policy']['size'] = [32, 32]
            model = dataset.models.create(template)
            material = dataset.models.publish(model['id'], {'revision': model['revision']})
            graph = dataset.pipelines.create({'name': 'P5 actual training', 'release_id': release['id'], 'recipe': 'image_classification_model_v2'})
            edited = copy.deepcopy(graph)
            next((x for x in edited['nodes'] if x['type'] == 'train'))['parameters'].update(epochs=2, widths=[8, 12, 16], input_size=32)
            graph = dataset.pipelines.save(graph['id'], {'revision': graph['revision'], 'document': edited})
            policy = dataset.pipelines.validate_graph(graph)['selection_policy']
            study = dataset.studies.create({'name': 'P5 charged candidate inference qualification', 'limits': {'attempt_slots': 6, 'admitted_wall_seconds': 6000, 'retained_bytes': 2 * 1024 ** 3, 'peak_staging_bytes': 3 * 1024 ** 3}, 'policy': policy})

        def bound_call(fn, *args, **kwargs):
            with owner.bound(dataset):
                return fn(*args, **kwargs)

        def current():
            return bound_call(dataset.studies.get, study['id'])['study']

        def admit(trial, key, builtin=False):
            state = current()
            if not state['open']:
                bound_call(dataset.studies.continue_study, study['id'], {'request_key': out.name + '-continue-' + key, 'revision': state['revision'], 'admission_epoch': state['admission_epoch']})
                state = current()
            body = {'request_key': out.name + '-admit-' + key, 'revision': state['revision'], 'admission_epoch': state['admission_epoch'], 'trial_id': trial['id']}
            if not builtin:
                approval = bound_call(dataset.studies.approve, study['id'], {'trial_id': trial['id'], 'expected_material_sha256': trial['material']['sha256'], 'consumer_actor_id': owner.identity['actor_id']})
                body['approval_id'] = approval['id']
            admitted = bound_call(dataset.studies.admit, study['id'], body)
            run = admitted['run']
            end = time.monotonic() + 300
            print('ADMITTED', key, run['id'], flush=True)
            while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < end:
                time.sleep(0.2)
                run = bound_call(dataset.runs.get, run['id'])
            print('TERMINAL', key, run['state'], run.get('error'), flush=True)
            if run['state'] != 'completed':
                raise RuntimeError(json.dumps(run))
            bound_call(dataset.studies.reconcile, study['id'])
            (out / (key + '-run.json')).write_bytes(p.encoded(run))
            return run
        trial = bound_call(dataset.studies.prepare_trial, study['id'], {'request_key': out.name + '-prepare-training', 'revision': current()['revision'], 'graph_id': graph['id'], 'graph_revision': graph['revision'], 'model': material['ref'], 'replicate': 0})
        training = admit(trial, 'training', True)
        candidate = bound_call(dataset.studies.select_candidate, study['id'], {'request_key': out.name + '-select-candidate', 'revision': current()['revision'], 'trial_id': trial['id'], 'run_id': training['id']})
        (out / 'candidate.json').write_bytes(p.encoded(candidate))
        body = {'request_key': out.name + '-prepare-package', 'revision': current()['revision'], 'candidate_id': candidate['ref']['id'], 'root': 'qualification', 'directory': 'package-project', 'runtime_snapshot_sha256': descriptor['manifest_sha256']}
        package_prepared = bound_call(p.prepare_candidate_package, dataset.studies, study['id'], body)
        assert bound_call(p.prepare_candidate_package, dataset.studies, study['id'], body) == package_prepared
        package_run = admit(package_prepared['trial'], 'package')
        state = bound_call(p.candidate_package_state, dataset.studies, candidate['ref']['id'])
        assert state['state'] == 'package_complete', state
        package = state['packages'][0]
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = 'http://127.0.0.1:' + str(server.server_port)
        for name in ('package.zip', 'package-result.json'):
            req = Request(endpoint + '/api/workspace/runs/' + package_run['id'] + '/artifacts/' + name, headers=owner.headers)
            with urlopen(req, timeout=60) as response:
                raw = response.read()
            (out / name).write_bytes(raw)
        assert p.sha((out / 'package.zip').read_bytes()) == package['sha256']
        verify_body = {'request_key': out.name + '-prepare-verifier', 'revision': current()['revision'], 'candidate_id': candidate['ref']['id'], 'root': 'qualification', 'directory': 'verifier-project', 'runtime_snapshot_sha256': descriptor['manifest_sha256'], 'package_run_id': package_run['id'], 'package_sha256': package['sha256']}
        verify_prepared = bound_call(p.prepare_candidate_verifier, dataset.studies, study['id'], verify_body)
        verify_run = admit(verify_prepared['trial'], 'verifier')
        state = bound_call(p.candidate_package_state, dataset.studies, candidate['ref']['id'])
        assert state['state'] == 'fresh_verified', state
        totals = bound_call(dataset.studies.get, study['id'])
        assert totals['charged']['attempt_slots'] == 3, totals['charged']
        report = {'format': 'p5_charged_qualification_v1', 'actual_training': True, 'actual_package_run': True, 'actual_captured_verifier_run': True, 'study_id': study['id'], 'candidate_id': candidate['ref']['id'], 'training_run_id': training['id'], 'package_run_id': package_run['id'], 'verifier_run_id': verify_run['id'], 'package_sha256': package['sha256'], 'runtime_snapshot': descriptor, 'charged': totals['charged'], 'state': state, 'source_fixture_sha256': p.sha(fixture_path.read_bytes()), 'capture_phases': phases}
        (out / 'receipt.json').write_bytes(p.encoded(report))
        return report
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        dataset.close()


def qualify_field_production(catalog, snapshot_descriptor, output, study_id, candidate_id, limits=None):
    """Two real charged attempts from an existing authorized scientific selection.

    The producer Run/candidate must already exist; this never fabricates evidence,
    retrains, installs a runtime, derives a core metric or changes selection policy.
    """
    import threading
    import time
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from app import Dataset, make_handler
    from auth_helpers import ExplicitOwnerFixture
    p = candidate_packages; out = Path(output).resolve(); out.mkdir(mode=0o700, parents=True, exist_ok=False)
    descriptor = p.decode(Path(snapshot_descriptor).read_bytes())
    dataset = Dataset(catalog, project_roots={'qualification': out}); server = None
    try:
        owner = ExplicitOwnerFixture.bootstrap(dataset)
        def call(function, *args, **kwargs):
            with owner.bound(dataset):
                return function(*args, **kwargs)
        def current():
            return call(dataset.studies.get, study_id)['study']
        candidate = call(dataset.studies.candidate, candidate_id)
        assert candidate['candidate']['study_id'] == study_id
        source = call(dataset.runs.get, candidate['run_id'])
        assert source['state'] == 'completed'
        assert call(dataset.runs.model_evidence, source['id'], {}, contract_version=2)['state'] == 'verified'
        before = call(dataset.studies.get, study_id)['charged']['attempt_slots']
        budget_amendment = None
        if limits is not None:
            # Explicit caller-owned finite qualification amendment, never a
            # budget retry/fallback or reuse of the producer's execution grant.
            assert limits['attempt_slots'] == before + 2
            reconciled = call(dataset.studies.reconcile, study_id)
            assert all(row['state'] == 'settled' for row in reconciled['reservations'])
            original = current()
            stopped = call(dataset.studies.stop, study_id, {'request_key': out.name + '-close-before-budget', 'revision': original['revision']})
            closed_study = current()
            save_body = {'revision': closed_study['revision'], 'name': closed_study['name'], 'limits': limits, 'policy': closed_study['policy']}
            saved = call(dataset.studies.save, study_id, save_body)
            budget_amendment = {'original_study': original, 'stop_response': stopped, 'save_body': save_body, 'save_response': saved}
            (out / 'budget-amendment.json').write_bytes(p.encoded(budget_amendment))
        def admit(trial, key):
            state = current()
            if not state['open']:
                call(dataset.studies.continue_study, study_id, {'request_key': out.name + '-continue-' + key,
                    'revision': state['revision'], 'admission_epoch': state['admission_epoch']})
                state = current()
            approval = call(dataset.studies.approve, study_id, {'trial_id': trial['id'],
                'expected_material_sha256': trial['material']['sha256'], 'consumer_actor_id': owner.identity['actor_id']})
            result = call(dataset.studies.admit, study_id, {'request_key': out.name + '-admit-' + key,
                'revision': state['revision'], 'admission_epoch': state['admission_epoch'], 'trial_id': trial['id'], 'approval_id': approval['id']})
            run = result['run']; end = time.monotonic() + 300
            print('ADMITTED', key, run['id'], flush=True)
            while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < end:
                time.sleep(.2); run = call(dataset.runs.get, run['id'])
            assert run['state'] == 'completed', run
            call(dataset.studies.reconcile, study_id); (out / (key + '-run.json')).write_bytes(p.encoded(run))
            return run
        prepared = call(p.prepare_candidate_package, dataset.studies, study_id, {'request_key': out.name + '-prepare-package',
            'revision': current()['revision'], 'candidate_id': candidate_id, 'root': 'qualification', 'directory': 'package-project',
            'runtime_snapshot_sha256': descriptor['manifest_sha256']})
        package_run = admit(prepared['trial'], 'package')
        state = call(p.candidate_package_state, dataset.studies, candidate_id)
        package = next(item for item in state['packages'] if item['run_id'] == package_run['id'])
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        for name in ('package.zip', 'package-result.json'):
            request = Request('http://127.0.0.1:' + str(server.server_port) + '/api/workspace/runs/' + package_run['id'] + '/artifacts/' + name,
                              headers=owner.headers)
            with urlopen(request, timeout=60) as response:
                raw = response.read()
            (out / name).write_bytes(raw)
        manifest, files = p.inspect_package((out / 'package.zip').read_bytes(), package['sha256'])
        assert p.decode(files[manifest['task']['name']])['format'] == p.SCALAR_A_TASK_FORMAT
        prepared = call(p.prepare_candidate_verifier, dataset.studies, study_id, {'request_key': out.name + '-prepare-verifier',
            'revision': current()['revision'], 'candidate_id': candidate_id, 'root': 'qualification', 'directory': 'verifier-project',
            'runtime_snapshot_sha256': descriptor['manifest_sha256'], 'package_run_id': package_run['id'], 'package_sha256': package['sha256']})
        verifier = admit(prepared['trial'], 'verifier')
        receipt = p.decode(call(dataset.runs.artifact, verifier['id'], 'verification.json')[0])
        assert receipt['format'] == 'fresh_field_inference_verification_v1' and receipt['verified'] is True
        assert receipt['candidate'] == candidate['ref'] and receipt['package_sha256'] == package['sha256']
        totals = call(dataset.studies.get, study_id)['charged']; assert totals['attempt_slots'] == before + 2
        result = {'format': 'p5_field_charged_qualification_v1', 'study_id': study_id, 'candidate_id': candidate_id,
            'source_run_id': source['id'], 'source_evaluation_sha256': candidate['candidate']['evaluation_sha256'],
            'package_run_id': package_run['id'], 'verifier_run_id': verifier['id'], 'package_sha256': package['sha256'],
            'runtime_snapshot': descriptor, 'charged_before': before, 'charged': totals, 'fresh_verification': receipt,
            'budget_amendment': budget_amendment,
            'scope': 'Actual retained-source package reconstruction only; independent numerical/physical acceptance remains separate.'}
        (out / 'receipt.json').write_bytes(p.encoded(result)); return result
    finally:
        if server is not None:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        dataset.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--production-catalog', type=Path)
    parser.add_argument('--snapshot-descriptor', type=Path)
    parser.add_argument('--source-study')
    parser.add_argument('--source-candidate')
    parser.add_argument('--field-limits', type=Path, help='Explicit finite limits JSON; close/save through the Study owner before the two package attempts.')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--expected-profile', choices=('classifier', 'scalar_a'),
        help='Require the explicitly nominated package task profile before any captured consumer execution.')
    parser.add_argument('--mask-path', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.production_catalog is not None:
        if args.snapshot_descriptor is None:
            parser.error('--snapshot-descriptor is required for production qualification.')
        if args.source_study is not None or args.source_candidate is not None:
            if args.source_study is None or args.source_candidate is None:
                parser.error('--source-study and --source-candidate must be supplied together.')
            limits = candidate_packages.decode(args.field_limits.read_bytes()) if args.field_limits is not None else None
            receipt = qualify_field_production(args.production_catalog, args.snapshot_descriptor, args.output, args.source_study, args.source_candidate, limits)
        else:
            receipt = qualify_production(args.production_catalog, args.snapshot_descriptor, args.output)
        print(json.dumps({'verified': True, 'receipt': str(args.output / 'receipt.json'), 'study_id': receipt['study_id']}))
        return
    if args.package is None or args.runtime is None:
        parser.error('--package and --runtime are required for downloaded-package qualification.')
    expected = args.expected_sha256
    if expected is None:
        result = args.package.with_name('package-result.json')
        if not result.is_file():
            parser.error('Supply --expected-sha256 from the published Run or its downloaded package-result.json.')
        expected = candidate_packages.decode(result.read_bytes())['package_sha256']
    raw = args.package.read_bytes()
    manifest, files = candidate_packages.inspect_package(raw, expected)
    task = candidate_packages.decode(files[manifest['task']['name']])
    if args.expected_profile is not None:
        required = {'classifier': 'package_classifier_task_v1', 'scalar_a': candidate_packages.SCALAR_A_TASK_FORMAT}[args.expected_profile]
        if task.get('format') != required:
            parser.error('Downloaded package does not match the explicitly nominated task profile.')
    runtime = candidate_packages.decode(files[manifest['runtime']['contract']['name']])
    snapshot_sha = runtime['snapshot']['manifest_sha256']
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = candidate_packages.fresh_verify(args.package, args.runtime, expected, snapshot_sha,
        args.output / 'verification.json', masked_paths=args.mask_path)
    report = {'format': 'candidate_package_qualification_v1', 'downloaded_whole_sha256': expected,
        'downloaded_bytes': len(raw), 'candidate': manifest['candidate'], 'runtime_snapshot_sha256': snapshot_sha,
        'package_task_format': task['format'],
        'fresh_verification': receipt, 'original_checkout_masked': bool(args.mask_path),
        'scope': 'Actual captured inference; numerical/physical validity and public redistribution remain separate.'}
    (args.output / 'report.json').write_bytes(candidate_packages.encoded(report))
    print(json.dumps({'verified': True, 'package_sha256': expected, 'report': str(args.output / 'report.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
