"""Fresh real Study/Trial with neutral custody fault; no numerical producer."""
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import signal
import sys
import threading
from unittest.mock import patch

from app import make_handler
from test_experiments import StudyTests
from test_run_publication_recovery import PublicationRecoveryTests
from workbench import WorkbenchError


def main():
    fixture = StudyTests('runTest')
    server = None
    initialized = False
    try:
        fixture.setUp()
        initialized = True
        dataset = fixture.dataset
        fixture.studies = dataset.studies
        trial, _ = fixture.prepare()
        with fixture.owner.bound(dataset):
            lineage = fixture.studies.lineage
            record = lineage.record({'request_key': 'neutral-lineage-browser-intent',
                'revision': lineage.list()['revision'], 'trial': lineage.ref(trial),
                'intent': {'ancestry': 'root', 'parent': None, 'baseline': None,
                    'cohort': 'Neutral publication UI', 'hypothesis': 'Publication preserves the original exact byte result.',
                    'change_summary': 'Recover retained output without replaying its producer.',
                    'target': {'metric_id': 'neutral_byte_identity', 'metric_definition_sha256': None,
                        'direction': 'target', 'threshold': None,
                        'acceptance': 'Inspect byte custody only; no model quality or scientific claim.'}}})
        fixture.open()
        body = fixture.admission_body(trial, fixture.approve())
        with dataset.access.bind(fixture.agent['token']), patch.object(dataset.runs, '_start'):
            admitted = fixture.studies.admit(fixture.study['id'], body)
        run = dataset.runs._load(admitted['run']['id'])
        with patch.object(dataset.runs, '_copy_verified', side_effect=OSError('Authored neutral Study publication fault')):
            dataset.runs._run_attempt(run, (dataset.runs._capacity.cores[0],), dataset.runs._capacity.claim(run))
        saved = dataset.runs._load(run['id'])
        assert saved['state'] == 'interrupted'
        with fixture.owner.bound(dataset):
            before = copy.deepcopy(fixture.studies.reconcile(fixture.study['id']))
            original_lineage = fixture.studies.lineage.get(trial['id'])
        counts = PublicationRecoveryTests.counts(None, dataset)
        reservation = dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s', (run['id'],)).fetchone()[0]
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        print(json.dumps({'port': server.server_port, 'data': str(fixture.path / 'catalog'),
            'run_id': run['id'], 'catalog_id': dataset.db.dataset_id, 'trial_id': trial['id']}), flush=True)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        sys.stdin.readline()
        server.shutdown()
        worker.join()
        with fixture.owner.bound(dataset):
            final = dataset.runs._load(run['id'])
            assert final['state'] == saved['state']
            assert final['events'] == saved['events']
            assert final['publication_continuation']['state'] == 'published'
            after = fixture.studies.reconcile(fixture.study['id'])
            assert after['reservations'] == before['reservations']
            assert after['charged'] == before['charged']
            assert fixture.studies.lineage.get(trial['id']) == original_lineage
            assert PublicationRecoveryTests.counts(None, dataset) == counts
            assert dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s', (run['id'],)).fetchone()[0] == reservation
            result = dataset.runs.publication_result(final['publication_continuation']['result_ref'])
            try:
                dataset.runs.artifact(run['id'], 'result.txt')
            except WorkbenchError:
                pass
            else:
                raise AssertionError('Legacy failed Run artifact became readable')
        Path(sys.argv[1]).write_text(json.dumps({'scope': 'Real neutral Study/Trial/custody publication lineage; no numerical or scientific acceptance',
            'trial_id': trial['id'], 'run_id': run['id'], 'lineage_record': record,
            'counts_before': counts, 'counts_after': PublicationRecoveryTests.counts(None, dataset),
            'charged_before': before['charged'], 'charged_after': after['charged'],
            'reservation_unchanged': True, 'lineage_projection_unchanged': True, 'events_unchanged': True,
            'original_run_state': final['state'], 'publication_state': 'published',
            'result_ref': result['result_ref'], 'legacy_artifact_refused': True}, indent=2)+'\n')
    finally:
        if server:
            server.shutdown()
            server.server_close()
        schema = fixture.dataset.db.schema if initialized else None
        dsn = fixture.dataset.db.dsn if initialized else None
        fixture.doCleanups()
        if schema:
            import psycopg
            from psycopg import sql
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    main()
