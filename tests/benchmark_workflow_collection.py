"""Same-source WorkflowClient.collect/collect_batch paired neutral measurements.

Default: twenty 16KiB items at histories8/55, one 320KiB control at history8,
and twenty-item attached-Ref history56. Each cell has three fresh processes,
one first and two warm pairs per process. --pilot runs one first pair per source
at histories1/2 before the fixed matrix. No producer, runtime or cache changes.
"""
import argparse
import copy
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from unittest.mock import patch

from benchmark_artifact_segments import collection_observers
from benchmark_lab_workflow import (Fixture, Metrics, canonical, counts, distribution,
    environment, negative_and_recovery, save, server, sha, stop_server)

ROOT = Path(__file__).resolve().parents[1]
BASE = '322482d2ca6fa2af8effb7a6a5080313efe745b4'
SCOPE = 'Current collection facade, neutral exact bytes on local HTTP/filesystem; no whole-workflow, lab or science claim.'


def attribution():
    value = environment()
    value.update(production_base=BASE, facade_harness_sha256=sha(Path(__file__).read_bytes()),
        facade_source_sha256=sha((ROOT/'tuldok_client.py').read_bytes()),
        owner_observer_sha256=sha((ROOT/'tests/benchmark_artifact_segments.py').read_bytes()),
        comparison='Same checkout/catalog/inventory; actual facade includes verification and private file publication.')
    return value


def verify_outputs(receipt, manifest, expected, directory):
    """Independent whole-byte oracle; partial or forged receipts cannot be timed as success."""
    if (receipt.get('state') != 'complete' or receipt.get('manifest') != manifest
            or len(receipt.get('items', [])) != len(expected)):
        raise AssertionError('Facade collection is partial or differs from its manifest.')
    if set(path.name for path in directory.iterdir()) != {item['name'] for item in expected}:
        raise AssertionError('Collection left missing, extra or provisional files.')
    proofs = []
    for outcome, item in zip(receipt['items'], expected, strict=True):
        path = directory/item['name']
        raw = path.read_bytes()
        proof = outcome.get('receipt', {})
        source = manifest['source']
        run_id = source.get('run_id', source.get('ref', {}).get('run_id'))
        if (outcome.get('name') != item['name'] or outcome.get('state') != 'verified'
                or proof.get('run_id') != run_id or proof.get('name') != item['name']
                or proof.get('sha256') != item['sha256'] or proof.get('bytes') != item['bytes']
                or proof.get('verification') != 'whole_sha256_verified'
                or proof.get('output') != str(path) or proof.get('result_ref') != source.get('ref')
                or path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 != 0o600
                or len(raw) != item['bytes'] or sha(raw) != item['sha256']):
            raise AssertionError('Facade receipt or independent local whole bytes differ.')
        proofs.append(dict(item))
    return proofs


def worker(config, destination, repeats):
    metrics = Metrics()
    metrics.labels = {'artifacts': config['artifacts'], 'terminal_history': config['history'],
                      'condition': 'fresh_process', 'source_kind': config['source']['kind']}
    Dataset = metrics.observe('process.import_application', lambda: importlib.import_module('app').Dataset)
    from agent_api import AgentClient
    from tuldok_client import WorkflowClient
    pairs = []
    http = dataset = None
    result = {'scope': SCOPE, 'source': config['source'], 'expected_artifacts': config['expected'],
              'process_id': os.getpid(), 'sample': config['sample'], 'rows': metrics.rows, 'pairs': pairs}
    try:
        with patch('recipe_process.launch', side_effect=AssertionError('Facade measurement replayed compute')) as launch:
            dataset = metrics.observe('catalog.cold_reopen', lambda: Dataset(config['catalog'],
                project_roots={'fixture': Path(config['project'])}))
            before = counts(dataset)
            http, thread, endpoint = server(dataset, metrics)
            client = AgentClient(endpoint, config['agent_token'], dataset.db.dataset_id)
            metrics.observe('client.bootstrap', client.bootstrap)
            facade = WorkflowClient(client)
            source = config['source']
            run_id = source.get('run_id', source.get('ref', {}).get('run_id'))
            with dataset.access.bind(config['owner_token']):
                original = copy.deepcopy(dataset.runs._load(run_id))
            selection = {'run_id': run_id} if source['kind'] == 'run' else {'result_ref': source['ref']}
            manifest = metrics.observe('facade.export_manifest', lambda: facade.collection_manifest(
                names=[item['name'] for item in config['expected']], **selection))
            if manifest['items'] != config['expected']:
                raise AssertionError('Exported exact facade inventory differs.')
            result.update(state_before=before, manifest=manifest, original_run_sha256=sha(canonical(original)))
            metrics.observe('instrumentation.noop_calibration', lambda: None)
            with collection_observers(dataset, metrics):
                for cycle in range(repeats+1):
                    order = ['individual', 'batch'] if (config['sample']+cycle) % 2 == 0 else ['batch', 'individual']
                    metrics.labels = {'artifacts': config['artifacts'], 'terminal_history': config['history'],
                        'condition': 'first_pair_fresh_process' if cycle == 0 else 'warm_pair_same_process',
                        'cycle': cycle, 'sample': config['sample'], 'source_kind': source['kind'], 'order': order}
                    proofs, walls = {}, {}
                    for arm in order:
                        function = facade.collect if arm == 'individual' else facade.collect_batch
                        with tempfile.TemporaryDirectory(prefix='facade-'+arm+'-', dir=config['output_parent']) as name:
                            directory = Path(name)
                            started = datetime.now(timezone.utc).isoformat()
                            receipt = metrics.observe('facade.'+source['kind']+'.'+arm,
                                lambda: function(manifest, directory))
                            row = metrics.rows[-1]
                            row.update(started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat())
                            row['detail'] = {'receipt_state': receipt.get('state')}
                            # Independent local byte reread and directory teardown
                            # are outside the timed facade call, for both arms.
                            proofs[arm] = verify_outputs(receipt, manifest, config['expected'], directory)
                            walls[arm] = row['wall_ns']
                            row['detail']['whole_artifacts'] = proofs[arm]
                    if proofs['individual'] != proofs['batch']:
                        raise AssertionError('Paired whole artifact identities differ.')
                    pairs.append(dict(metrics.labels, individual_wall_ns=walls['individual'],
                        batch_wall_ns=walls['batch'], batch_over_individual=walls['batch']/walls['individual'],
                        whole_artifacts_equal=True))
            after = counts(dataset)
            with dataset.access.bind(config['owner_token']):
                retained = dataset.runs._load(run_id)
            if before != after or retained != original:
                raise AssertionError('Facade collection changed accounting or the original Run.')
            launch.assert_not_called()
            result.update(state_after=after, original_run_unchanged=True, events_unchanged=True,
                          compute_replay_calls=launch.call_count, availability='eligible_exact_inventory')
    except BaseException as error:
        result['failure'] = {'type': type(error).__name__, 'message': str(error)[:1000]}
        raise
    finally:
        try:
            if http is not None:
                stop_server(http, thread)
            if dataset is not None:
                dataset.close()
        finally:
            save(destination, result)


def run_processes(fixture, source, history, raw, samples, repeats):
    fixture.close()
    config = fixture.state()
    config.update(source=source, history=history, output_parent=str(fixture.path))
    private = fixture.path/'facade-worker.json'
    results = []
    for sample in range(samples):
        config['sample'] = sample
        private.write_bytes(canonical(config)); private.chmod(0o600)
        destination = raw/f'{source["kind"]}-items-{fixture.pieces}-history-{history}-process-{sample}.json'
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', str(private),
            '--out', str(destination), '--warm-repeats', str(repeats)], cwd=ROOT, check=True, timeout=600)
        results.append(json.loads(destination.read_bytes()))
        print(json.dumps({'progress': 'facade_pairs', 'source': source['kind'], 'items': fixture.pieces,
                          'history': history, 'process': sample}), flush=True)
    return results


def pair_distributions(pairs):
    groups = {}
    for pair in pairs:
        key = (pair['source_kind'], pair['artifacts'], pair['terminal_history'], pair['condition'])
        groups.setdefault(key, []).append(pair['batch_over_individual'])
    return [{'source_kind': source, 'artifacts': items, 'terminal_history': history,
        'condition': condition, 'n': len(values), 'batch_over_individual': {
            'min': min(values), 'median': statistics.median(values), 'max': max(values)}}
        for (source, items, history, condition), values in sorted(groups.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--warm-repeats', type=int, default=2)
    args = parser.parse_args()
    if args.worker:
        if not 0 <= args.warm_repeats <= 2:
            parser.error('Worker warm repeats must be bounded0..2.')
        worker(json.loads(args.worker.read_bytes()), args.out, args.warm_repeats)
        return
    if not os.environ.get('TULDOK_DATABASE_URL'):
        parser.error('Select an explicitly disposable PostgreSQL database.')
    args.out.mkdir(parents=True, exist_ok=False)
    raw = args.out/'raw'; raw.mkdir()
    start = attribution(); save(args.out/'environment-start.json', start)
    rows, pairs, cleanup, integrity = [], [], [], []
    samples, repeats = (1, 0) if args.pilot else (3, 2)
    cells = [(20, [1])] if args.pilot else [(1, [8]), (20, [8, 55])]
    try:
        for items, histories in cells:
            fixture = Fixture.__new__(Fixture)
            try:
                fixture.__init__(items, 327680)
                for history in histories:
                    fixture.open()
                    current = counts(fixture.dataset)['workspace_runs']
                    while current < history:
                        fixture.populate_one(); current += 1
                        print(json.dumps({'progress': 'real_history', 'items': items, 'completed': current,
                                          'target': history}), flush=True)
                    for value in run_processes(fixture, {'kind': 'run', 'run_id': fixture.target},
                            history, raw, samples, repeats):
                        rows.extend(value['rows']); pairs.extend(value['pairs'])
                if items == 20:
                    # Reuse the existing actual negative/same-Run recovery tail.
                    # Its input mutation is restored before measured Ref reads;
                    # it never changes installed runtime or producer source bytes.
                    checked = negative_and_recovery(fixture, 0)
                    integrity.append(checked)
                    history = counts(fixture.dataset)['workspace_runs']
                    for value in run_processes(fixture, {'kind': 'publication', 'ref': checked['recovered_result_ref']},
                            history, raw, samples, repeats):
                        rows.extend(value['rows']); pairs.extend(value['pairs'])
                save(raw/f'items-{items}-setup.json', {'rows': fixture.metrics.rows, 'integrity': integrity[-1:]})
            finally:
                if hasattr(fixture, 'schema'):
                    cleaned = fixture.cleanup(); cleanup.append(cleaned)
                    save(raw/f'items-{items}-cleanup.json', cleaned)
        finish = attribution()
        for key in ('head', 'source_sha256', 'harness_sha256', 'facade_harness_sha256',
                    'facade_source_sha256', 'owner_observer_sha256'):
            if start[key] != finish[key]:
                raise AssertionError('Frozen source/harness changed during measurement.')
        save(args.out/'summary.json', {'scope': SCOPE, 'source': start, 'environment_finish': finish,
            'pilot': args.pilot, 'matrix': {'cells': cells, 'aggregate_bytes': 327680,
                'process_samples_per_cell': samples, 'warm_pairs_per_process': repeats,
                'attached_ref': 'Twenty items after an additional real interrupted Run; history2 pilot/history56 final'},
            'distributions': distribution(rows), 'paired_ratio_distributions': pair_distributions(pairs),
            'pairs': pairs, 'cleanup': cleanup, 'integrity': integrity,
            'limits': ['Manifest export, imports, catalog reopen and client bootstrap are separate untimed setup observations.',
                'Timed facade includes current inventory check, HTTP, whole-hash verification, private file write/fsync/no-clobber publication.',
                'Fresh output directory creation, independent local oracle reread and directory cleanup are excluded for both arms.',
                'One first pair per fresh process; its second arm follows the first. No OS/PG cache flush.',
                'Every pair/outlier retained; order alternates by process and cycle; no invented improvement threshold.',
                'CPU excludes PostgreSQL backend; RSS/HWM are snapshots/lifetime; inclusive owner spans are not additive.',
                'Neutral local20x16KiB and1x320KiB cells do not prove performance for2–19 items, remote/larger payloads, whole workflows or science.']})
    except BaseException as error:
        save(args.out/'failure.json', {'type': type(error).__name__, 'message': str(error)[:1000],
                                     'cleanup': cleanup, 'environment': attribution()})
        raise


if __name__ == '__main__':
    main()
