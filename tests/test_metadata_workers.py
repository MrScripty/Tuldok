"""Real PostgreSQL worker ownership and publication failures; no provider inference."""
from auth_helpers import bind_owner
import base64
from contextlib import contextmanager
import io
import json
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from PIL import Image

from app import Dataset
from metadata import connection_info
from workbench import WorkbenchError


@contextmanager
def rejected_write(db, table, *, deferred=False, condition=None):
    """Use actual PostgreSQL statement/commit failures, not fake transactions."""
    function, trigger = 'reject_worker_fixture', 'reject_worker_fixture'
    with db.transaction():
        db.execute(sql.SQL('CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS {}').format(
            sql.Identifier(function), sql.Literal(
                "BEGIN RAISE EXCEPTION 'injected worker persistence failure' USING ERRCODE='23514'; END")))
        statement = ('CREATE CONSTRAINT TRIGGER {} AFTER INSERT ON {} DEFERRABLE INITIALLY DEFERRED '
                     'FOR EACH ROW EXECUTE FUNCTION {}()' if deferred else
                     'CREATE TRIGGER {} BEFORE UPDATE ON {} FOR EACH ROW ' +
                     ('WHEN (' + condition + ') ' if condition else '') + 'EXECUTE FUNCTION {}()')
        db.execute(sql.SQL(statement).format(sql.Identifier(trigger), sql.Identifier(table), sql.Identifier(function)))
    try:
        yield
    finally:
        with db.transaction():
            db.execute(sql.SQL('DROP TRIGGER {} ON {}').format(sql.Identifier(trigger), sql.Identifier(table)))
            db.execute(sql.SQL('DROP FUNCTION {}()').format(sql.Identifier(function)))


class MetadataWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.opened = []
        self.data = self.open()
        self.schema = self.data.db.schema

    def tearDown(self):
        for data in reversed(self.opened):
            if not data.db.connection.closed:
                data.close()
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.tmp.cleanup()

    def open(self):
        data = Dataset(self.tmp.name)
        self.actor = bind_owner(self, data)
        self.opened.append(data)
        return data

    def image(self):
        output = io.BytesIO()
        Image.new('RGB', (20, 12), 'blue').save(output, 'PNG')
        return base64.b64encode(output.getvalue()).decode()

    def caption_body(self, row):
        return dict(request_id=uuid.uuid4().hex, source_id=row['id'], revision=row['revision'],
                    source_revision=row['source_revision'], server_url='http://127.0.0.1:1234',
                    model='caption-fixture', instruction='Describe the image', seed=42)

    def generation_body(self):
        return dict(server_url='http://127.0.0.1:1234', model='image-fixture', prompt='A blue rectangle',
                    width=512, height=512, count=1, strategy='repeat', session_id='worker-fixture')

    def test_peer_open_preserves_active_jobs_and_reopen_recovers_without_replay(self):
        jobs = {}
        names = ('generation_jobs', 'grounded', 'caption_proposals', 'text_classification_proposals')
        with self.data.lock, self.data.db.transaction():
            for name in names:
                owner = getattr(self.data, name)
                job = dict(id=uuid.uuid4().hex, revision=0, status='generating', completed=0,
                           config={'protocol': 'pumas_typed_v1', 'width': 512, 'height': 512})
                owner._save(job)
                jobs[name] = dict(job)
        with patch('synthetic.prompt_batch') as prompts, patch('caption_proposals.complete') as captions, \
                patch('text_classification_proposals.complete') as classifications, patch('grounded_candidates.complete') as rewrites:
            peer = self.open()
            self.assertNotEqual(self.data.db.connection.info.backend_pid, peer.db.connection.info.backend_pid)
            for name in names:
                owner = getattr(peer, name)
                self.assertFalse(owner.runtime_owner)
                observed = owner.snapshot()['jobs'][0] if name == 'generation_jobs' else owner.get(jobs[name]['id'])
                self.assertEqual(observed, jobs[name])
            self.data.close()
            # A reader does not silently take over merely because a peer closed.
            self.assertFalse(peer.generation_jobs.runtime_owner)
            reopened = self.open()
            for name in names:
                owner = getattr(reopened, name)
                self.assertTrue(owner.runtime_owner)
                observed = owner.snapshot()['jobs'][0] if name == 'generation_jobs' else owner.get(jobs[name]['id'])
                self.assertEqual(observed['status'], 'interrupted')
                if name != 'generation_jobs':
                    self.assertEqual(observed['provider_outcome'], 'unknown')
                self.assertIsNone(owner.worker)
            for provider in (prompts, captions, classifications, rewrites):
                provider.assert_not_called()

    def test_live_caption_peer_receipt_and_concurrent_apply_do_not_replay(self):
        row = self.data.workbench.import_asset(dict(kind='image', image=self.image(), name='fixture',
                                                   groups=['fixture'], rights='Authored fixture'))
        body = self.caption_body(row)
        entered, release = threading.Event(), threading.Event()

        def complete(job, stop):
            entered.set()
            if not release.wait(10):
                raise AssertionError('Controlled worker was not released')
            return json.dumps({'model': 'caption-fixture', 'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps({'caption': 'A blue rectangle.'})}}]}).encode()

        with patch('caption_proposals.ai_http.text_models', return_value={
                'models': [{'id': 'caption-fixture'}], 'qualification': 'Controlled fixture'}), \
                patch('caption_proposals.complete', side_effect=complete) as provider:
            job = self.data.caption_proposals.start(body)
            try:
                self.assertTrue(entered.wait(5))
                peer = self.open()
                receipt = peer.caption_proposals.start(body)
                self.assertEqual(receipt['status'], 'generating')
                with self.assertRaisesRegex(WorkbenchError, 'another open application'):
                    peer.caption_proposals.start(dict(body, request_id=uuid.uuid4().hex))
                self.assertFalse(peer.caption_proposals.cancel({'job_id': job['id']})['cancelled'])
            finally:
                release.set()
                self.data.caption_proposals.worker.join(5)
            self.assertFalse(self.data.caption_proposals.worker.is_alive())
            job = self.data.caption_proposals.get(job['id'])
            self.assertEqual(job['status'], 'completed', job.get('error'))
            barrier, results, errors = threading.Barrier(2), [], []

            def apply(owner):
                with self.actor.bound(self.data):
                    try:
                        barrier.wait(5)
                        results.append(owner.decide(job['id'], dict(revision=job['revision'], decision='apply_draft')))
                    except BaseException as error:
                        errors.append(error)

            threads = [threading.Thread(target=apply, args=(data.caption_proposals,)) for data in (self.data, peer)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(sorted(result['changed'] for result in results), [False, True])
            self.assertEqual(peer.workbench.get(row['id'])['revision'], row['revision'] + 1)
            self.assertEqual(provider.call_count, 1)

    def dispatch_cases(self):
        image = self.data.workbench.import_asset(dict(kind='image', image=self.image(), name='fixture',
                                                     groups=['fixture'], rights='Authored fixture'))
        text = self.data.workbench.import_asset(dict(kind='text', text='Keep exact text.', name='fixture',
                                                    groups=['fixture'], rights='Authored fixture'))
        reviewed = self.data.workbench.save(text['id'], dict(text, annotation={'label': 'keep'},
                                                            review='human_reviewed'))
        unannotated = self.data.workbench.import_asset(dict(kind='text', text='Another exact text.', name='fixture',
                                                          groups=['another'], rights='Authored fixture'))
        grounding = dict(source_id=reviewed['id'], revision=reviewed['revision'], source_revision=reviewed['source_revision'],
                         server_url='http://127.0.0.1:1234', model='grounded-fixture', instruction='Rewrite', count=1, seed=42)
        classification = dict(self.caption_body(unannotated), model='classification-fixture', labels=['keep', 'cancel'])
        return [('generation_jobs', 'generation_jobs', self.generation_body()),
                ('grounded', 'grounded_jobs', grounding),
                ('caption_proposals', 'caption_proposals', self.caption_body(image)),
                ('text_classification_proposals', 'text_classification_proposals', classification)]

    def test_real_commit_failure_never_dispatches_any_worker(self):
        for name, table, body in self.dispatch_cases():
            with self.subTest(owner=name), rejected_write(self.data.db, table, deferred=True), \
                    patch('threading.Thread.start') as dispatch:
                with self.assertRaises(psycopg.errors.CheckViolation):
                    getattr(self.data, name).start(body)
                dispatch.assert_not_called()
                self.assertIsNone(getattr(self.data, name).worker)
                self.assertEqual(self.data.db.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0], 0)

    def test_nested_start_and_resume_refuse_dispatch_before_outer_rollback(self):
        for name, table, body in self.dispatch_cases():
            with self.subTest(owner=name), patch('threading.Thread.start') as dispatch:
                with self.data.db.transaction(force_rollback=True):
                    with self.assertRaisesRegex(ValueError, 'requires its own committed transaction'):
                        getattr(self.data, name).start(body)
                dispatch.assert_not_called()
                self.assertIsNone(getattr(self.data, name).worker)
                self.assertEqual(self.data.db.execute(sql.SQL('SELECT COUNT(*) FROM {}').format(sql.Identifier(table))).fetchone()[0], 0)
        job = dict(id=uuid.uuid4().hex, status='failed', completed=0, config=self.generation_body())
        with self.data.db.transaction():
            self.data.generation_jobs._save(job)
        with patch('threading.Thread.start') as dispatch:
            with self.data.db.transaction(force_rollback=True):
                with self.assertRaisesRegex(ValueError, 'requires its own committed transaction'):
                    self.data.generation_jobs.resume(job['id'])
            dispatch.assert_not_called()
        self.assertEqual(self.data.generation_jobs.snapshot()['jobs'], [job])

    def test_retained_unicode_evidence_survives_edits_without_relaxing_new_input(self):
        workbench = self.data.workbench
        row = workbench.import_asset(dict(kind='text', text='Exact source.', name='fixture',
                                         groups=['fixture'], rights='Authored fixture'))
        raw = '{ "rights" : "Authored fixture", "nested" : ["\\ud800", "\\u0000", "café"] }'
        with self.data.db.transaction():
            self.data.db.execute('UPDATE workbench_records SET provenance_json=%s WHERE id=%s', (raw, row['id']))
        prior_history = self.data.db.execute(
            'SELECT snapshot FROM workbench_history WHERE id=%s AND revision=1', (row['id'],)).fetchone()[0]
        corrected = workbench.correct_rights_note(row['id'], dict(
            revision=row['revision'], source_revision=row['source_revision'], note='Updated note'))['record']
        self.assertEqual(self.data.db.execute(
            'SELECT provenance_json FROM workbench_records WHERE id=%s', (row['id'],)).fetchone()[0], raw)
        edited = workbench.save(row['id'], dict(corrected, annotation={'label': 'keep'}, review='human_reviewed'))
        self.assertEqual(edited['provenance']['nested'], json.loads(raw)['nested'])
        self.assertEqual(workbench.history(row['id'])[0], edited)
        self.assertEqual(self.data.db.execute(
            'SELECT snapshot FROM workbench_history WHERE id=%s AND revision=1', (row['id'],)).fetchone()[0], prior_history)
        with self.assertRaises(WorkbenchError):
            workbench.import_asset(dict(kind='text', text='Invalid new \ud800', name='fixture',
                                        groups=['fixture'], rights='Authored fixture'))

    def test_summary_projection_preserves_escaped_unicode_and_exact_stored_json(self):
        for name in ('caption_proposals', 'text_classification_proposals'):
            for character in ('\0', '\ud800'):
                with self.subTest(owner=name, character=repr(character)):
                    owner = getattr(self.data, name)
                    job = dict(id=uuid.uuid4().hex, revision=1, status='completed',
                               config={'retained': 'exact' + character + 'evidence'},
                               source={'text': 'private' + character + 'source', 'name': 'label' + character},
                               raw_response_base64='retained response', input_image_base64='retained image')
                    # A retained legacy JSON value is text containing escapes, not
                    # an attempt to write a NUL or unpaired surrogate as PG text.
                    with self.data.db.transaction():
                        self.data.db.execute(sql.SQL('INSERT INTO {} (id,data) VALUES (%s,%s)').format(
                            sql.Identifier(name)), (job['id'], json.dumps(job)))
                    query = sql.SQL('SELECT data FROM {} WHERE id=%s').format(sql.Identifier(name))
                    before = self.data.db.execute(query, (job['id'],)).fetchone()[0]
                    summary = owner.snapshot()['jobs'][0]
                    self.assertEqual(summary['config']['retained'], job['config']['retained'])
                    self.assertEqual(summary['source']['name'], job['source']['name'])
                    self.assertNotIn('raw_response_base64', summary)
                    if name == 'caption_proposals':
                        self.assertNotIn('input_image_base64', summary)
                    else:
                        self.assertNotIn('text', summary['source'])
                    self.assertEqual(self.data.db.execute(query, (job['id'],)).fetchone()[0], before)

    def test_import_receipts_match_escaped_unicode_and_detect_cross_path_ambiguity(self):
        import bulk_import
        import sequence_batch_import
        from test_sequence_batch import body as sequence_body, synthetic

        def text_body(value):
            return dict(source_name='fixture.jsonl', row_number=1, request_id=uuid.uuid4().hex,
                        line=json.dumps(dict(kind='text', text=value, groups=['fixture'], rights='Authored fixture')))

        cases = [(bulk_import, 'acquisition', bulk_import.import_row, text_body('First'), text_body('Second')),
                 (sequence_batch_import, 'sequence_acquisition', sequence_batch_import.import_item,
                  sequence_body(), sequence_body(*synthetic()))]
        for owner, field, admit, first_body, second_body in cases:
            with self.subTest(owner=owner.__name__):
                first = admit(self.data.workbench, first_body)
                second = admit(self.data.workbench, second_body)
                query = 'SELECT provenance_json FROM workbench_records WHERE id=%s'
                origin = json.loads(self.data.db.execute(query, (first['record_id'],)).fetchone()[0])
                for character in ('\0', '\ud800'):
                    evidence = json.dumps(dict(origin, legacy_evidence='exact' + character + 'evidence'))
                    with self.data.db.transaction():
                        self.data.db.execute('UPDATE workbench_records SET provenance_json=%s WHERE id=%s',
                                             (evidence, first['record_id']))
                    found = owner.find_result(self.data.workbench, first_body['request_id'])
                    self.assertTrue(found['found'])
                    self.assertEqual(found['record_id'], first['record_id'])
                    self.assertEqual(self.data.db.execute(query, (first['record_id'],)).fetchone()[0], evidence)
                second_origin = json.loads(self.data.db.execute(query, (second['record_id'],)).fetchone()[0])
                second_origin[field]['request_id'] = first_body['request_id']
                with self.data.db.transaction():
                    self.data.db.execute('UPDATE workbench_records SET provenance_json=%s WHERE id=%s',
                                         (json.dumps(second_origin, ensure_ascii=False), second['record_id']))
                with self.assertRaisesRegex(WorkbenchError, 'ambiguous'):
                    owner.find_result(self.data.workbench, first_body['request_id'])

    def test_failed_generation_completion_restores_progress_and_removes_files(self):
        with rejected_write(self.data.db, 'generation_jobs', condition="NEW.data::json ->> 'completed' = '1'"), \
                patch.object(self.data.image_requests, '_generate_admitted', return_value={'image': self.image(), 'metadata': {}}) as provider:
            self.data.generation_jobs.start(self.generation_body())
            self.data.generation_jobs.worker.join(5)
            self.assertFalse(self.data.generation_jobs.worker.is_alive())
        snapshot = self.data.generation_jobs.snapshot()
        self.assertEqual(snapshot['jobs'][0]['status'], 'failed')
        self.assertEqual(snapshot['jobs'][0]['completed'], 0)
        self.assertEqual(snapshot['entries'][0]['status'], 'failed')
        self.assertIsNone(snapshot['entries'][0]['sample_id'])
        self.assertEqual(self.data.rows(), [])
        self.assertEqual(list((self.data.path / 'images').iterdir()), [])
        self.assertEqual(provider.call_count, 1)

    def test_disconnected_shutdown_stops_and_joins_local_workers(self):
        owners = [self.data.caption_proposals, self.data.text_classification_proposals]
        for owner in owners:
            owner.worker = threading.Thread(target=owner.stop.wait)
            owner.worker.start()
        self.data.db.close()
        self.data.close()
        for owner in owners:
            self.assertTrue(owner.closed)
            self.assertTrue(owner.stop.is_set())
            self.assertFalse(owner.worker.is_alive())


if __name__ == '__main__':
    unittest.main()
