"""Own fresh PostgreSQL catalog: real lock fault, queued neutral custody and lost reply."""
import json
from pathlib import Path
import signal
import socket
import sys
import threading

import recipe_process
from app import make_handler
from http.server import ThreadingHTTPServer
from test_run_coordinator_recovery import CoordinatorRecoveryTests


def main():
    case = CoordinatorRecoveryTests('runTest')
    case.setUp()
    dataset = case.dataset
    server = None
    go = recipe_process.Handle.go
    sends, dropped = [], []

    def counted(handle, helper):
        sends.append(handle)
        return go(handle, helper)

    try:
        run = case.queued(case.body(approval=case.approve()))
        with dataset.lock:
            original = dataset.runs._load(run['id'])
        case.lock_fault()
        recipe_process.Handle.go = counted
        handler = make_handler(dataset)

        class LoseFirstRecoveryReply(handler):
            def reply(self, data, status=200, content_type='application/json', headers=()):
                if self.command == 'POST' and self.path == '/api/workspace/coordinator/recover' and status == 200 and not dropped:
                    dropped.append(True)
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                return super().reply(data, status, content_type, headers)

        server = ThreadingHTTPServer(('127.0.0.1', 0), LoseFirstRecoveryReply)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        print(json.dumps({'port': server.server_port, 'data': str(case.path/'catalog'),
                          'run_id': run['id'], 'catalog_id': dataset.db.dataset_id}), flush=True)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        sys.stdin.readline()
        server.shutdown(); worker.join(5)
        assert not worker.is_alive()
        with case.owner.bound(dataset):
            current = dataset.runs._load(run['id'])
            health = dataset.runs.coordinator_health()
            assert current['state'] == 'completed'
            assert dataset.runs._external_drain_receipt(current)
            assert health['generation'] == 2 and health['admission_ready']
            assert health['recovery_request']['completed_generation'] == 2
            assert len(sends) == 1 and dropped == [True]
            for key in ('id', 'request_key', 'request_sha256', 'admission_id', 'approval_id'):
                assert current[key] == original[key]
            counts = {name: dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0]
                      for name in ('workspace_runs', 'access_execution_grants', 'access_execution_consumptions')}
            assert all(value == 1 for value in counts.values())
        Path(sys.argv[1]).write_text(json.dumps({'scope': 'Real coordinator lock fault, HTTP acknowledgement loss and first neutral GO; no training/science claim',
            'health': health, 'go_sends': len(sends), 'dropped_reply': True, 'counts': counts,
            'original_admission_identity_unchanged': True, 'run_state': current['state'],
            'custody_drained': True}, indent=2)+'\n')
    finally:
        recipe_process.Handle.go = go
        if server:
            server.shutdown(); server.server_close()
        schema, dsn = dataset.db.schema, dataset.db.dsn
        case.doCleanups()
        import psycopg
        from psycopg import sql
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    main()
