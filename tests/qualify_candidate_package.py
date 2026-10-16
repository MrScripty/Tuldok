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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--production-catalog', type=Path)
    parser.add_argument('--snapshot-descriptor', type=Path)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--mask-path', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.production_catalog is not None:
        if args.snapshot_descriptor is None:
            parser.error('--snapshot-descriptor is required for production qualification.')
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
    runtime = candidate_packages.decode(files[manifest['runtime']['contract']['name']])
    snapshot_sha = runtime['snapshot']['manifest_sha256']
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = candidate_packages.fresh_verify(args.package, args.runtime, expected, snapshot_sha,
        args.output / 'verification.json', masked_paths=args.mask_path)
    report = {'format': 'candidate_package_qualification_v1', 'downloaded_whole_sha256': expected,
        'downloaded_bytes': len(raw), 'candidate': manifest['candidate'], 'runtime_snapshot_sha256': snapshot_sha,
        'fresh_verification': receipt, 'original_checkout_masked': bool(args.mask_path),
        'scope': 'Actual captured inference; numerical/physical validity and public redistribution remain separate.'}
    (args.output / 'report.json').write_bytes(candidate_packages.encoded(report))
    print(json.dumps({'verified': True, 'package_sha256': expected, 'report': str(args.output / 'report.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
