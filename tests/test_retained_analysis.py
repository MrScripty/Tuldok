"""Query-boundary fixtures; actual PostgreSQL assertions are separately gated.

Auth/evidence substitutes test orchestration only. They do not qualify actual
Runs custody, SQL behavior or end-to-end application acceptance.
"""
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retained_analysis as analysis
from access import AccessError
from model_evidence import canonical, digest
from psycopg.pq import TransactionStatus
from workbench import WorkbenchError

RUN = 'a' * 32
CHECKPOINTS = ['b' * 64, 'c' * 64]
EVALUATION = 'd' * 64


def fixture():
    definition = {'id': 'accuracy', 'units': 'dimensionless', 'split': 'validation',
                  'population_sha256': 'e' * 64, 'reduction': 'diagonal_over_population'}
    body = {'query_id': analysis.QUERY_ID, 'query_version': 1, 'run_id': RUN,
            'evaluation_sha256': EVALUATION, 'checkpoint_sha256': CHECKPOINTS[1],
            'metric_id': 'accuracy', 'metric_definition_sha256': digest(definition)}
    evidence = {'state': 'verified', 'manifest': {'format': 'model_evidence_v1',
                'probe': {'sha256': 'f' * 64}, 'data_sha256': '1' * 64,
                'producer': {'run_id': RUN, 'adapter_sha256': '2' * 64}},
                'metric_definitions': [definition],
                'checkpoint_index': {'entries': [{'checkpoint': {'sha256': sha}, 'clocks': {'epoch': i}}
                                                for i, sha in enumerate(CHECKPOINTS, 1)]},
                'probe': {'members': [{'ordinal': i, 'frozen_reference': {'id': f'example-{i}', 'revision': 3}}
                                      for i in range(2)]},
                'predictions': {'checkpoint_sha256': CHECKPOINTS[1], 'probe_sha256': 'f' * 64,
                                'rows': [{'ordinal': 0, 'truth_index': 0, 'predicted_index': 0, 'probabilities': [.875, .125]},
                                         {'ordinal': 1, 'truth_index': 1, 'predicted_index': 0, 'probabilities': [.75, .25]}]},
                'observations': [{'checkpoint_sha256': sha, 'metric_id': 'accuracy', 'split': 'validation',
                                  'state': 'observed', 'clocks': {'epoch': epoch}, 'value': value, 'sample_count': 2}
                                 for sha, epoch, value in zip(CHECKPOINTS, (1, 2), (.0, .5))]}
    return body, evidence


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class OwnerFixture:
    """A controlled boundary fixture, intentionally not a SQL implementation."""
    def __init__(self):
        self.body, self.evidence = fixture()
        self.reading = False
        self.events = []
        self.revoke_after_read = False
        self.artifact_reads = 0
        self.document = {'id': RUN, 'state': 'completed',
                         'artifacts': [{'name': 'model-evidence.json', 'sha256': EVALUATION}]}
        self.curve = [{'checkpoint_sha256': CHECKPOINTS[0], 'epoch': 1, 'value': .0, 'support': 2},
                      {'checkpoint_sha256': CHECKPOINTS[1], 'epoch': 2, 'value': .5, 'support': 2}]
        self.page = {'filtered_support': 2, 'rows': [
            {'ordinal': 0, 'example_id': 'example-0', 'truth_index': 0, 'predicted_index': 0,
             'confidence': .875, 'error': False, 'frozen_reference': {'id': 'example-0', 'revision': 3}},
            {'ordinal': 1, 'example_id': 'example-1', 'truth_index': 1, 'predicted_index': 0,
             'confidence': .75, 'error': True, 'frozen_reference': {'id': 'example-1', 'revision': 3}}]}
        self.db = SimpleNamespace(dataset_id='catalog-fixture', execute=self.execute,
                                  lock=SimpleNamespace(bounded=self.bounded),
                                  connection=SimpleNamespace(transaction=self.transaction,
                                      info=SimpleNamespace(transaction_status=TransactionStatus.IDLE)))
        self.access = SimpleNamespace(require=self.require)

    @contextmanager
    def bounded(self, deadline):
        yield

    @contextmanager
    def transaction(self):
        self.reading = True
        try:
            yield
        finally:
            self.reading = False

    def require(self, scope, action, run_id):
        self.events.append((scope, action, run_id, self.reading))
        if self.revoke_after_read and len(self.events) > 1:
            raise AccessError('Credential is unavailable, expired or revoked.', 'unauthenticated', 401)

    def model_evidence(self, run_id, selectors, *, contract_version):
        self.artifact_reads += 1
        assert (run_id, selectors, contract_version) == (RUN, {'checkpoint_sha256': CHECKPOINTS[1]}, 1)
        return copy.deepcopy(self.evidence)

    def execute(self, sql, params=None):
        if 'octet_length(document)' in sql:
            return Cursor([{'document': json.dumps(self.document)}])
        if sql == analysis.CURVE_SQL:
            return Cursor(copy.deepcopy(self.curve))
        if sql == analysis.EXAMPLES_SQL:
            return Cursor([copy.deepcopy(self.page)])
        return Cursor([])


class RequestTests(unittest.TestCase):
    def test_defaults_and_explicit_field_projection(self):
        body, _ = fixture()
        value = analysis.validate_request(body)
        self.assertEqual((value['limit'], value['offset'], value['errors_only']), (50, 0, False))
        self.assertEqual(value['fields'], list(analysis.FIELDS))
        self.assertEqual(analysis.validate_request(dict(body, fields=['example_id']))['fields'], ['example_id'])
        self.assertNotIn('limit', body)

    def test_closed_bounds_and_types_before_evidence_read(self):
        changes = [({'sql': 'SELECT secret'}, 'invalid'), ({'query_version': True}, 'unsupported'),
                   ({'query_id': 'raw_sql'}, 'unsupported'), ({'limit': True}, 'invalid'),
                   ({'limit': 101}, 'invalid'), ({'limit': 0}, 'invalid'), ({'offset': -1}, 'invalid'),
                   ({'offset': 10001}, 'invalid'), ({'errors_only': 1}, 'invalid'),
                   ({'fields': ['example_id', 'probabilities']}, 'invalid'),
                   ({'fields': ['confidence']}, 'invalid'), ({'fields': ['example_id'] * 2}, 'invalid'),
                   ({'fields': [[]]}, 'invalid'), ({'metric_id': []}, 'invalid'),
                   ({'metric_id': "accuracy'); DROP TABLE workspace_runs;--"}, 'invalid'),
                   ({'run_id': '../catalog'}, 'invalid'), ({'checkpoint_sha256': 'B' * 64}, 'invalid')]
        for changed, code in changes:
            with self.subTest(changed=changed):
                owner = OwnerFixture()
                with self.assertRaises(WorkbenchError) as caught:
                    analysis.query(owner, dict(owner.body, **changed))
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(owner.artifact_reads, 0)
                self.assertEqual(owner.events, [])
        for value in (None, [], 'query'):
            with self.subTest(value=value), self.assertRaises(WorkbenchError):
                analysis.validate_request(value)


class ProjectionTests(unittest.TestCase):
    def test_exact_frozen_examples_and_retained_confidence(self):
        body, evidence = fixture()
        definition, checkpoints, raw = analysis._projection(evidence, body)
        rows = json.loads(raw)
        self.assertEqual([row['example_id'] for row in rows], ['example-0', 'example-1'])
        self.assertEqual([row['error'] for row in rows], [False, True])
        self.assertEqual([row['confidence'] for row in rows], [.875, .75])
        self.assertEqual(rows[1]['frozen_reference'], {'id': 'example-1', 'revision': 3})
        self.assertEqual(checkpoints[1], {'checkpoint_sha256': CHECKPOINTS[1], 'epoch': 2})
        self.assertEqual(definition['units'], 'dimensionless')

    def test_foreign_metric_checkpoint_and_population_are_distinct_failures(self):
        body, evidence = fixture()
        for changed, code in (({'metric_definition_sha256': '0' * 64}, 'stale'),
                              ({'checkpoint_sha256': '0' * 64}, 'not_found')):
            with self.subTest(changed=changed), self.assertRaises(WorkbenchError) as caught:
                analysis._projection(evidence, dict(body, **changed))
            self.assertEqual(caught.exception.code, code)
        evidence['predictions']['probe_sha256'] = '0' * 64
        with self.assertRaisesRegex(WorkbenchError, 'Selected checkpoint predictions differ'):
            analysis._projection(evidence, body)

    def test_unsupported_task_and_oversize_are_explicit(self):
        body, evidence = fixture()
        evidence['checkpoint_index']['entries'][0]['clocks']['epoch'] = None
        with self.assertRaises(WorkbenchError) as caught:
            analysis._projection(evidence, body)
        self.assertEqual(caught.exception.code, 'unsupported')
        body, evidence = fixture()
        with patch.object(analysis, 'MAX_EXAMPLES', 1), self.assertRaises(WorkbenchError) as caught:
            analysis._projection(evidence, body)
        self.assertEqual((caught.exception.code, caught.exception.status), ('limit', 413))


class QueryBoundaryTests(unittest.TestCase):
    def test_exact_provenance_and_values_with_fresh_access_outside_snapshot(self):
        owner = OwnerFixture()
        result = analysis.query(owner, owner.body)
        self.assertEqual([p['value'] for p in result['curve']], [.0, .5])
        self.assertEqual(result['provenance']['evaluation_sha256'], EVALUATION)
        self.assertEqual(result['metric']['support'], 2)
        self.assertEqual(result['examples']['population_support'], 2)
        self.assertEqual(result['sampling'], {'method': 'none', 'population': 'frozen_validation_probe'})
        self.assertEqual(len(owner.events), 2)
        self.assertTrue(all(event == ('inspect', 'runs.retained_analysis', RUN, False) for event in owner.events))

    def test_export_and_repeated_retrieval_do_not_bypass_current_authority(self):
        owner = OwnerFixture()
        analysis.query(owner, owner.body)
        owner.revoke_after_read = True
        with self.assertRaises(AccessError) as caught:
            analysis.query(owner, owner.body, export=True)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(owner.artifact_reads, 1)
        self.assertEqual(owner.events[-1][1], 'runs.export_retained_analysis')

    def test_revocation_during_read_prevents_return(self):
        owner = OwnerFixture()
        owner.revoke_after_read = True
        with self.assertRaises(AccessError) as caught:
            analysis.query(owner, owner.body)
        self.assertEqual(caught.exception.code, 'unauthenticated')
        self.assertEqual(owner.artifact_reads, 1)
        self.assertFalse(owner.reading)

    def test_error_filter_does_not_change_metric_population_and_page_identity(self):
        owner = OwnerFixture()
        owner.page = {'filtered_support': 1, 'rows': [owner.page['rows'][1]]}
        result = analysis.query(owner, dict(owner.body, errors_only=True, fields=['example_id'], limit=1))
        self.assertEqual(result['metric']['support'], 2)
        self.assertEqual(result['examples']['filtered_support'], 1)
        self.assertEqual(result['examples']['rows'], [{'example_id': 'example-1', 'ordinal': 1,
                                                     'frozen_reference': {'id': 'example-1', 'revision': 3}}])
        self.assertIsNone(result['examples']['next_offset'])
        self.assertEqual(result['examples']['filters'], {'errors_only': True})

    def test_catalog_mismatch_is_refused(self):
        for field, value in (('value', .25), ('support', 3), ('epoch', 3)):
            owner = OwnerFixture()
            owner.curve[0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(WorkbenchError, 'Catalog curve differs'):
                analysis.query(owner, owner.body)
        owner = OwnerFixture()
        owner.document['artifacts'][0]['sha256'] = '0' * 64
        with self.assertRaises(WorkbenchError) as caught:
            analysis.query(owner, owner.body)
        self.assertEqual(caught.exception.code, 'stale')
        self.assertEqual(owner.artifact_reads, 0)

    def test_nested_transaction_and_oversized_response_refused(self):
        owner = OwnerFixture()
        owner.db.connection.info.transaction_status = TransactionStatus.INTRANS
        with self.assertRaises(WorkbenchError) as caught:
            analysis.query(owner, owner.body)
        self.assertEqual(caught.exception.code, 'unavailable')
        self.assertEqual(owner.artifact_reads, 0)
        owner = OwnerFixture()
        with patch.object(analysis, 'MAX_RESPONSE_BYTES', 1), self.assertRaises(WorkbenchError) as caught:
            analysis.query(owner, owner.body)
        self.assertEqual(caught.exception.status, 413)

    def test_malformed_catalog_envelope_preserves_typed_failure(self):
        for document in ({'artifacts': None}, {'artifacts': [{'sha256': '0' * 64}]}, [], None):
            owner = OwnerFixture()
            owner.document = document
            with self.subTest(document=document), self.assertRaises(WorkbenchError) as caught:
                analysis.query(owner, owner.body)
            self.assertEqual((caught.exception.code, caught.exception.status), ('unavailable', 409))
            self.assertEqual(str(caught.exception), 'Retained Run envelope is unavailable.')
            self.assertEqual(owner.artifact_reads, 0)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Existing authorized PostgreSQL configuration required; no credentials created.')
class ActualPostgresSqlTests(unittest.TestCase):
    def test_parameterized_curve_and_stable_error_page_on_actual_postgres(self):
        import psycopg
        from psycopg.rows import dict_row
        from metadata import connection_info
        with psycopg.connect(connection_info(), row_factory=dict_row) as db:
            # A rollback-only temporary relation never changes application schema.
            with db.transaction(force_rollback=True):
                db.execute('CREATE TEMP TABLE workspace_runs(id text, document text) ON COMMIT DROP')
                doc = {'metrics': {'history': [{'epoch': 1, 'validation': {'accuracy': .125, 'examples': 8}},
                                              {'epoch': 2, 'validation': {'accuracy': .375, 'examples': 8}}]}}
                db.execute('INSERT INTO workspace_runs VALUES (%s,%s)', (RUN, json.dumps(doc)))
                cp = [{'checkpoint_sha256': sha, 'epoch': i} for i, sha in enumerate(CHECKPOINTS, 1)]
                rows = db.execute(analysis.CURVE_SQL, (json.dumps(cp), 'accuracy', RUN, 129)).fetchall()
                self.assertEqual([row['value'] for row in rows], [.125, .375])
                self.assertEqual([row['support'] for row in rows], [8, 8])
                body, evidence = fixture()
                _, _, raw = analysis._projection(evidence, body)
                page = db.execute(analysis.EXAMPLES_SQL, (raw, True, 1, 0)).fetchone()
                self.assertEqual(page['filtered_support'], 1)
                self.assertEqual(page['rows'][0]['example_id'], 'example-1')
                empty = db.execute(analysis.EXAMPLES_SQL, (raw, True, 1, 1)).fetchone()
                self.assertEqual(empty, {'filtered_support': 1, 'rows': []})


if __name__ == '__main__':
    unittest.main()
