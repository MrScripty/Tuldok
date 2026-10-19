"""Disposable neutral custody fixture for the actual Run-panel browser witness."""
import json
from pathlib import Path
import signal
import sys
import threading
import time

from app import make_handler
from http.server import ThreadingHTTPServer
from test_run_publication_recovery import PublicationRecoveryTests
from workbench import WorkbenchError


def main():
    case = PublicationRecoveryTests('runTest')
    fixture = None
    server = None
    try:
        fixture, run = case.failed_publication()
        dataset = fixture.dataset
        before = case.counts(dataset)
        before_events = dataset.runs._load(run['id'])['events']
        original = dataset.runs._copy_verified
        held = False

        def bounded_pause(*args, **kwargs):
            nonlocal held
            # Test-owned one-shot cancellation window around the real copy owner.
            # No payload/semantic verifier is replaced; subsequent recovery is real.
            if dataset.runs._publication_active and not held:
                held = True
                end = time.monotonic() + 12
                while not dataset.runs._publication_cancel.is_set() and time.monotonic() < end:
                    time.sleep(.02)
            return original(*args, **kwargs)

        dataset.runs._copy_verified = bounded_pause
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        print(json.dumps({'port': server.server_port, 'data': str(fixture.path / 'catalog'),
                          'run_id': run['id'], 'catalog_id': dataset.db.dataset_id}), flush=True)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        sys.stdin.readline()
        server.shutdown()
        worker.join()
        with fixture.owner.bound(dataset):
            final = dataset.runs._load(run['id'])
            continuation = final.get('publication_continuation')
            assert continuation and continuation['state'] == 'published'
            assert case.counts(dataset) == before
            assert final['events'] == before_events
            assert final['state'] == run['state']
            result = dataset.runs.publication_result(continuation['result_ref'])
            try:
                dataset.runs.artifact(run['id'], 'result.txt')
            except WorkbenchError:
                pass
            else:
                raise AssertionError('Legacy failed Run artifact became readable')
        Path(sys.argv[1]).write_text(json.dumps({'scope': 'Neutral real CPU custody and publication UI; no scientific acceptance',
            'counts_before': before, 'counts_after': case.counts(dataset), 'events_unchanged': True,
            'original_run_state': final['state'], 'publication_state': continuation['state'],
            'attempt_count': len(continuation['attempts']), 'result_ref': result['result_ref'],
            'input_sha256': result['artifacts'][0]['sha256'], 'legacy_artifact_refused': True}, indent=2)+'\n')
    finally:
        if server:
            server.shutdown()
            server.server_close()
        schema = fixture.dataset.db.schema if fixture else None
        dsn = fixture.dataset.db.dsn if fixture else None
        case.doCleanups()
        if schema:
            import psycopg
            from psycopg import sql
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    main()
