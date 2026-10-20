"""Fresh neutral catalog, real preparation/queue/cancel/publication lifecycle for Chromium."""
import copy
from http.server import ThreadingHTTPServer
import json
import hashlib
from pathlib import Path
import signal
import sys
import threading
import time
from unittest.mock import patch

import recipe_contract
import recipe_process
from app import make_handler
from test_external_runs import ExternalExecutionTests


def main():
    case = ExternalExecutionTests('runTest'); case.setUp()
    dataset = case.dataset; runs = dataset.runs
    server = None; handles = []; headroom = [0]; gate = threading.Event()
    original_prepare = recipe_contract.prepare; original_copy = runs._copy_verified
    fault = [False]; preparation_gate = [True]; all_runs = []
    original_go = recipe_process.Handle.go
    def prepare(*args, **kwargs):
        if preparation_gate[0]:
            if not gate.wait(20): raise AssertionError('Browser preparation release missing')
        return original_prepare(*args, **kwargs)
    def counted(handle, helper):
        handles.append(handle); return original_go(handle, helper)
    def copy_outputs(*args, **kwargs):
        if fault[0]: raise OSError('authored browser original publication fault')
        return original_copy(*args, **kwargs)
    try:
        recipe_contract.prepare = prepare; recipe_process.Handle.go = counted
        runs._copy_verified = copy_outputs
        with patch('run_capacity.available_memory', side_effect=lambda: headroom[0]):
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
            serving = threading.Thread(target=server.serve_forever); serving.start()
            print(json.dumps({'port': server.server_port, 'data': str(case.path/'catalog'),
                'catalog_id': dataset.db.dataset_id, 'graph_id': case.graph['id']}), flush=True)
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
            for line in sys.stdin:
                command = json.loads(line)['command']
                if command == 'release-preparation':
                    preparation_gate[0] = False; gate.set()
                elif command in ('queue', 'publication'):
                    graph = copy.deepcopy(case.graph)
                    graph['nodes'][1]['parameters']['mode'] = 'sleep' if command == 'queue' else 'complete'
                    with case.owner.bound(dataset):
                        case.graph = dataset.pipelines.save(graph['id'], {'revision': graph['revision'], 'document': graph})
                        case.preflight = dataset.pipelines.preflight_external(case.graph['id'], case.graph['revision'])
                    if command == 'publication': fault[0] = True
                    run = case.queued(case.body(approval=case.approve())); all_runs.append(run)
                    runs._start(); runs._wake.set()
                elif command == 'lock-wait':
                    # A real second-thread Catalog mutex wait, not a patched clock.
                    entered = threading.Event()
                    def wait():
                        entered.set()
                        with runs._phase_catalog(all_runs[0]['id']): pass
                    with dataset.lock:
                        waiter = threading.Thread(target=wait); waiter.start()
                        assert entered.wait(3); time.sleep(.15)
                    waiter.join(5); assert not waiter.is_alive()
                elif command == 'allow':
                    headroom[0] = 64*1024**3; runs._wake.set()
                elif command == 'copy': fault[0] = False
                elif command == 'finish': break
                else: raise AssertionError('Unknown test command')
                print(json.dumps({'command': command, 'run_id': all_runs[-1]['id'] if all_runs else None}), flush=True)
            server.shutdown(); serving.join(5); assert not serving.is_alive()
            with case.owner.bound(dataset):
                first, second = [runs._load(run['id']) for run in all_runs]
                assert first['state'] == 'cancelled'
                assert second['state'] in ('failed', 'interrupted')
                continuation = second['publication_continuation']; assert continuation['state'] == 'published'
                assert runs._external_drain_receipt(first) and runs._external_drain_receipt(second)
                result = runs.publication_result(continuation['result_ref'])
                assert result['artifacts'][0]['sha256'] == hashlib.sha256(case.input).hexdigest()
                counts = {table: dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                    for table in ('workspace_runs','access_execution_grants','access_execution_consumptions')}
                assert all(count == 2 for count in counts.values()); assert len(handles) == 2
                timings = [runs.phase_timings(run['id']) for run in all_runs]
            Path(sys.argv[1]).write_text(json.dumps({'scope':'actual neutral preparation/queue/catalog mutex/cancel/drain/publication continuation; no training/science',
                'counts':counts,'go_sends':len(handles),'cancelled_run':first['id'],'publication_run':second['id'],
                'original_publication_run_state':second['state'],'result_ref':continuation['result_ref'],
                'timings':timings},indent=2)+'\n')
    finally:
        gate.set(); recipe_contract.prepare = original_prepare; recipe_process.Handle.go = original_go
        runs._copy_verified = original_copy
        if server: server.shutdown(); server.server_close()
        schema, dsn = dataset.db.schema, dataset.db.dsn
        case.doCleanups()
        import psycopg
        from psycopg import sql
        with psycopg.connect(dsn,autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__': main()
