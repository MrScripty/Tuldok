"""Text-domain acceptance through real PostgreSQL and canonical POSIX files."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import psycopg
from psycopg import sql

from access import Access, AccessError
from metadata import Metadata
from project_store import ProjectStore, ProjectStoreError, _encode
from project_text import ProjectText, ProjectTextError, decode_records


class ProjectTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = self.metadata('host')
        self.access = Access(self.host, self.host.path)
        self.token = self.access.exchange(self.access._local_owner_token())['token']
        self.enterContext(self.access.bind(self.token))
        self.db = self.metadata('projection')
        self.store = ProjectStore.create(self.root / 'project', 'Authored text', 'new-project', 'a' * 64)
        self.addCleanup(self.store.close)
        self.text = ProjectText(self.store, self.db, self.access)
        self.text.restore()

    def metadata(self, name):
        database = Metadata(self.root / name)
        def drop_fixture():
            with psycopg.connect(database.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(database.schema)))
        self.addCleanup(drop_fixture)
        self.addCleanup(database.close)
        return database

    def body(self, source='Hello 😀 cafe\u0301\r\nSecond\rline', **extra):
        return dict(text=source, name='Original note', groups=['owned-fixture'], rights='Authored fixture; no grant implied', **extra)

    def import_text(self, source='Hello 😀 cafe\u0301\r\nSecond\rline', key='import-one', **extra):
        return self.text.import_text(self.body(source, **extra), self.text.checkpoint, key)

    def annotation(self, row, **extra):
        return dict(revision=row['revision'], source_revision=1, task='text_entities',
                    annotation={'spans': [dict(label='emoji', start=6, end=7)]},
                    groups=['owned-fixture', 'reviewed-fixture'], review='human_reviewed', **extra)

    def save_annotation(self, row, key='annotate-one'):
        return self.text.annotate(row['id'], self.annotation(row), self.text.checkpoint, key)

    def test_cold_fresh_database_restores_raw_normalized_history_and_inert_facts(self):
        source = 'Hello 😀 cafe\u0301\r\nSecond\rline'
        row = self.import_text(source)
        saved = self.save_annotation(row)
        history = self.text.history(row['id'])
        snapshot = self.store.snapshot()
        doc = snapshot['records'][0]['document']
        self.assertEqual(doc['original_text'], source)
        self.assertEqual(saved['text'], 'Hello 😀 café\nSecond\nline')
        self.assertEqual(saved['source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(saved['content_hash'], hashlib.sha256(saved['text'].encode()).hexdigest())
        self.assertEqual([item['revision'] for item in doc['history']], [1, 2])
        self.assertEqual(doc['audit'][1]['action'], 'workbench.approve_review')
        serialized = json.dumps(snapshot)
        self.assertNotIn(self.token, serialized)
        self.assertNotIn('credential_id', serialized)
        self.assertNotIn('access_credentials', serialized)
        self.store.save(self.text.checkpoint)
        self.store.close()
        self.db.close()
        # A new installation grants its own current permission; old audit facts
        # neither create credentials nor require the old installation to exist.
        new_host = self.metadata('other-host')
        new_access = Access(new_host, new_host.path)
        token = new_access.exchange(new_access._local_owner_token())['token']
        fresh = self.metadata('fresh-projection')
        reopened = ProjectStore.open(self.root / 'project')
        self.addCleanup(reopened.close)
        cold = ProjectText(reopened, fresh, new_access)
        cold.restore()
        with new_access.bind(token):
            actual = cold.get(row['id'])
            self.assertEqual({k: v for k, v in saved.items() if k != 'request_key'}, actual)
            self.assertEqual(history, cold.history(row['id']))
            self.assertEqual(cold.query({'q': 'emoji'})['total'], 1)
            self.assertEqual(reopened.save(cold.checkpoint), snapshot)
        self.assertEqual(fresh.execute('SELECT count(*) FROM access_credentials').fetchone()[0], 0)
        self.assertEqual(fresh.execute('SELECT original_text FROM workbench_records').fetchone()[0], source)

    def test_retry_returns_original_target_revision_before_stale_precondition(self):
        before = self.text.checkpoint
        body = self.body()
        row = self.text.import_text(body, before, 'import-one')
        self.save_annotation(row)
        checkpoint = self.text.checkpoint
        replay = self.text.import_text(body, before, 'import-one')
        self.assertEqual((replay['id'], replay['revision']), (row['id'], 1))
        self.assertEqual(replay['checkpoint'], checkpoint)
        self.assertEqual(self.text.query()['total'], 1)
        self.assertEqual(len(self.text.history(row['id'])), 2)
        with self.assertRaises(ProjectStoreError) as failure:
            self.text.import_text(self.body('different'), before, 'import-one')
        self.assertEqual(failure.exception.code, 'conflict')
        self.assertEqual(self.text.checkpoint, checkpoint)

    def test_parent_lineage_and_annotation_replay_survive_restore(self):
        parent = self.import_text()
        child = self.import_text('A distinct child', key='import-child', parents=[parent['id']])
        body = dict(revision=1, source_revision=1, task='text_corpus', annotation={'note': 'Deliberate corpus review'},
                    groups=child['groups'], review='human_reviewed')
        before = self.text.checkpoint
        reviewed = self.text.annotate(child['id'], body, before, 'review-child')
        self.text.restore()
        replay = self.text.annotate(child['id'], body, before, 'review-child')
        self.assertEqual(reviewed, replay)
        self.assertEqual(self.text.get(child['id'])['parents'], [parent['id']])

    def test_unavailable_operations_and_invalid_annotation_have_no_effects(self):
        row = self.import_text()
        before = self.store.snapshot()
        cases = [lambda: self.text.import_text(dict(kind='image', image='not decoded'), self.text.checkpoint, 'image'),
                 lambda: self.text.annotate(row['id'], dict(self.annotation(row), review='programmatically_verified'), self.text.checkpoint, 'verify'),
                 lambda: self.text.annotate(row['id'], dict(self.annotation(row), task='image_detection'), self.text.checkpoint, 'image-task'),
                 lambda: self.text.annotate(row['id'], dict(self.annotation(row), annotation={'spans': [dict(label='bad', start=True, end=7)]}), self.text.checkpoint, 'invalid-span')]
        for action in cases:
            with self.subTest(action=action), self.assertRaises(ProjectTextError if action != cases[-1] else ValueError):
                action()
            self.assertEqual(self.store.snapshot(), before)
            self.assertEqual(self.text.get(row['id'])['revision'], 1)
        self.assertFalse(hasattr(self.text, 'import_asset'))
        self.assertFalse(hasattr(self.text, 'preferences'))

    def test_expected_checkpoint_and_record_revision_reject_without_publish(self):
        checkpoint = self.text.checkpoint
        row = self.import_text()
        before = self.store.snapshot()
        with self.assertRaises(ProjectTextError):
            self.text.import_text(self.body('another'), checkpoint, 'stale-project')
        self.save_annotation(row)
        current = self.store.snapshot()
        with self.assertRaises(ValueError):
            self.text.annotate(row['id'], self.annotation(row), self.text.checkpoint, 'stale-record')
        self.assertEqual(self.store.snapshot(), current)
        self.assertNotEqual(current, before)

    def test_file_publication_failure_rolls_back_actual_sql(self):
        before = self.store.snapshot()
        with patch.object(self.store, '_publish', side_effect=ProjectStoreError('fixture unavailable', 'unavailable', 503)):
            with self.assertRaises(ProjectStoreError):
                self.import_text()
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_history').fetchone()[0], 0)
        self.assertEqual(self.text.query()['total'], 0)

    def test_real_postgres_commit_failure_retains_canonical_success_and_rebuilds(self):
        # Deferred trigger fails at the actual outer PostgreSQL COMMIT, after
        # canonical file publication, rather than replacing the DB adapter.
        self.db.execute("""CREATE FUNCTION fixture_refuse_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'fixture deferred rejection' USING ERRCODE='23514'; END $$""")
        self.db.execute('''CREATE CONSTRAINT TRIGGER fixture_commit_failure AFTER INSERT ON workbench_records
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fixture_refuse_commit()''')
        with self.assertRaises(ProjectTextError) as failure:
            self.import_text()
        self.assertEqual(failure.exception.code, 'projection_unavailable')
        self.assertTrue(failure.exception.committed)
        snapshot = self.store.snapshot()
        self.assertEqual(failure.exception.receipt, dict(committed=True, selected=True,
            project_id=snapshot['project_id'], checkpoint=snapshot['checkpoint'], request_key='import-one'))
        self.assertEqual(len(snapshot['records']), 1)
        self.assertFalse(self.text.available)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 0)
        with self.assertRaises(ProjectTextError):
            self.text.query()
        self.db.execute('DROP TRIGGER fixture_commit_failure ON workbench_records')
        self.text.restore()
        replay = self.text.import_text(self.body(), '0' * 64, 'import-one')
        self.assertEqual(replay['id'], snapshot['records'][0]['id'])
        self.assertEqual(self.text.query()['total'], 1)

    def test_external_checkpoint_and_immutable_byte_edits_fence_reads_and_writes(self):
        row = self.import_text()
        manifest_path = self.root / 'project' / '.tuldok' / 'project.json'
        original = manifest_path.read_bytes()
        manifest = json.loads(original)
        manifest['name'] = 'External checkout'
        del manifest['checkpoint']
        manifest['checkpoint'] = hashlib.sha256(_encode(manifest)).hexdigest()
        manifest_path.write_bytes(_encode(manifest))
        for action in (lambda: self.text.query(), lambda: self.text.get(row['id']),
                       lambda: self.text.history(row['id']), lambda: self.import_text('another', key='drift')):
            with self.assertRaises(ProjectStoreError) as failure:
                action()
            self.assertEqual(failure.exception.code, 'stale')
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 1)
        manifest_path.write_bytes(original)
        manifest = json.loads(original)
        record_path = self.root / 'project' / '.tuldok' / manifest['inventory'][0]['path']
        record_path.write_text('{}')
        with self.assertRaises(ProjectStoreError):
            self.text.query()
        with self.assertRaises(ProjectStoreError):
            self.import_text('another', key='corrupt')

    def test_cold_decoder_rejects_corrupt_semantics_before_any_projection_write(self):
        row = self.import_text()
        original = self.store.snapshot()['records']
        mutations = {
            'extra credential': lambda d: d.update(access_credentials=[]),
            'missing source bytes': lambda d: d.pop('original_text'),
            'changed raw source': lambda d: d.update(original_text='forged'),
            'normalized hash': lambda d: d['history'][0].update(content_hash='f' * 64),
            'noninteger revision': lambda d: d['current'].update(revision=True),
            'future task': lambda d: d['history'][0].update(task='text_future'),
            'missing history': lambda d: d.update(history=[]),
            'missing audit': lambda d: d.update(audit=[]),
            'credential in fact': lambda d: d['audit'][0].update(credential_id='1' * 32),
            'forged review': lambda d: d['history'][0].update(review='programmatically_verified'),
            'broken parent': lambda d: d['history'][0].update(parents=['1' * 32]),
            'foreign target': lambda d: d['operations'][0].update(target='1' * 32),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                records = copy.deepcopy(original)
                mutate(records[0]['document'])
                if label == 'broken parent':
                    records[0]['document']['current']['parents'] = ['1' * 32]
                before = self.db.execute('SELECT snapshot FROM workbench_history').fetchone()[0]
                key = label.replace(' ', '-')
                self.store.commit(records, self.store.snapshot()['checkpoint'], 'bad-' + key, hashlib.sha256(label.encode()).hexdigest())
                with self.assertRaises(ValueError):
                    self.text.restore()
                self.assertEqual(self.db.execute('SELECT snapshot FROM workbench_history').fetchone()[0], before)
                self.store.commit(original, self.store.snapshot()['checkpoint'], 'repair-' + key, hashlib.sha256(('repair' + label).encode()).hexdigest())
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 1)

    def test_decoder_rejects_unknown_formats_families_and_validly_hashed_broken_lineage(self):
        row = self.import_text()
        original = self.store.snapshot()['records']
        for field, value in [('family', 'future_family'), ('format', 'workbench_text_v2')]:
            records = copy.deepcopy(original)
            if field == 'family':
                records[0][field] = value
            else:
                records[0]['document'][field] = value
            with self.assertRaises(ProjectTextError) as failure:
                decode_records(records)
            self.assertEqual(failure.exception.code, 'unsupported')
        from workbench import encode
        for parent, message in [('1' * 32, 'missing'), (row['id'], 'cycle')]:
            records = copy.deepcopy(original)
            doc = records[0]['document']
            doc['current']['parents'] = [parent]
            doc['history'][0]['parents'] = [parent]
            doc['audit'][0]['details']['content_sha256'] = hashlib.sha256(encode(doc['history'][0]).encode()).hexdigest()
            with self.assertRaisesRegex(ProjectTextError, message):
                decode_records(records)

    def test_anonymous_current_access_is_not_granted_by_imported_history(self):
        row = self.import_text()
        unrelated_host = self.metadata('unrelated-host')
        access = Access(unrelated_host, unrelated_host.path)
        reader = ProjectText(self.store, self.db, access)
        reader.restore()
        # Current context is bound to the original host, not this installation.
        with self.assertRaises(AccessError):
            reader.get(row['id'])
        self.assertEqual(unrelated_host.execute('SELECT count(*) FROM access_credentials').fetchone()[0], 0)

    def test_scoped_agent_draft_edits_and_reads_keep_owner_review_authority(self):
        credential = self.access.issue(dict(label='Project fixture agent', scopes=['inspect', 'edit']))
        with self.access.bind(credential['token']):
            row = self.import_text()
            body = dict(self.annotation(row), review='draft')
            updated = self.text.annotate(row['id'], body, self.text.checkpoint, 'agent-draft')
            self.assertEqual(updated['revision'], 2)
            self.assertEqual(self.text.get(row['id'])['annotation'], body['annotation'])
            self.assertEqual(self.text.query()['total'], 1)
            self.assertEqual(len(self.text.records()['items']), 1)
            self.assertEqual(len(self.text.history(row['id'])), 2)
            before = self.store.snapshot()
            with self.assertRaises(AccessError):
                self.text.annotate(row['id'], self.annotation(updated), self.text.checkpoint, 'agent-approval')
            self.assertEqual(self.store.snapshot(), before)
        portable = json.dumps(self.store.snapshot())
        self.assertNotIn(credential['token'], portable)
        self.assertNotIn('credential_id', portable)
        inspection = self.access.issue(dict(label='Read-only fixture agent', scopes=['inspect']))
        with self.access.bind(inspection['token']):
            self.assertEqual(self.text.get(row['id'])['revision'], 2)
            with self.assertRaises(AccessError):
                self.import_text('Read only cannot import', key='read-only-write')
        self.assertEqual(self.store.snapshot(), before)

    def test_no_dataset_or_recovery_owner_is_constructed(self):
        with patch('app.Dataset', side_effect=AssertionError('Dataset must remain absent')):
            fresh = ProjectText(self.store, self.db, self.access)
            fresh.restore()
            row = fresh.import_text(self.body(), fresh.checkpoint, 'inert-import')
            self.assertEqual(fresh.get(row['id'])['revision'], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 0)

    def test_nested_caller_transaction_cannot_acknowledge_before_outer_commit(self):
        before = self.store.snapshot()
        with self.db.transaction():
            with self.assertRaises(ProjectTextError):
                self.import_text()
        self.assertEqual(self.store.snapshot(), before)

    def test_current_owner_revocation_waits_for_canonical_publication(self):
        credential_id = self.access.require('edit', 'workbench.import_asset').credential_id
        administrator = self.access.exchange(self.access._local_owner_token())['token']
        at_publication, proceed, revocation_attempt = threading.Event(), threading.Event(), threading.Event()
        outcomes, failures = [], []
        original_commit = self.store.commit
        def commit(*args, **kwargs):
            at_publication.set()
            if not proceed.wait(5):
                raise AssertionError('Publication fixture timed out')
            result = original_commit(*args, **kwargs)
            outcomes.append('canonical')
            return result
        def mutate():
            try:
                with self.access.bind(self.token):
                    self.import_text()
            except BaseException as error:
                failures.append(error)
        def revoke():
            try:
                revocation_attempt.set()
                with self.access.bind(administrator):
                    self.access.revoke(credential_id)
                    outcomes.append('revoked')
            except BaseException as error:
                failures.append(error)
        writer, revoker = threading.Thread(target=mutate), threading.Thread(target=revoke)
        with patch.object(self.store, 'commit', side_effect=commit):
            writer.start()
            try:
                self.assertTrue(at_publication.wait(5))
                revoker.start()
                self.assertTrue(revocation_attempt.wait(5))
                acquired = self.access.lock.mutex.acquire(blocking=False)
                if acquired:
                    self.access.lock.mutex.release()
                self.assertFalse(acquired, 'Host authority must stay locked through canonical publication')
            finally:
                proceed.set()
                writer.join(5)
                if revoker.ident is not None:
                    revoker.join(5)
        self.assertFalse(writer.is_alive())
        self.assertFalse(revoker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(outcomes, ['canonical', 'revoked'])
        with self.assertRaises(AccessError):
            self.text.query()
        with self.access.bind(administrator):
            self.assertEqual(len(self.text.records()['items']), 1)

    def test_full_current_records_include_text_without_query_pagination(self):
        first = self.import_text()
        second = self.import_text('Another complete text', key='second')
        full = self.text.records()
        self.assertEqual(full['checkpoint'], self.text.checkpoint)
        self.assertEqual({row['id'] for row in full['items']}, {first['id'], second['id']})
        self.assertEqual({row['text'] for row in full['items']}, {first['text'], second['text']})
        self.assertNotIn('text', self.text.query({'limit': 1})['items'][0])

    def test_lost_canonical_publication_reply_requires_reopen_and_reconciles(self):
        publish = self.store._publish
        def publish_then_lose_reply(*args, **kwargs):
            publish(*args, **kwargs)
            raise ProjectStoreError('Fixture lost publication reply.', 'unknown', 503)
        with patch.object(self.store, '_publish', side_effect=publish_then_lose_reply):
            with self.assertRaises(ProjectStoreError) as failure:
                self.import_text()
        self.assertEqual(failure.exception.code, 'unknown')
        self.assertFalse(self.text.available)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 0)
        self.store.close()
        reopened = ProjectStore.open(self.root / 'project')
        self.addCleanup(reopened.close)
        restored = ProjectText(reopened, self.db, self.access)
        restored.restore()
        replay = restored.import_text(self.body(), '0' * 64, 'import-one')
        self.assertEqual(replay['id'], reopened.snapshot()['records'][0]['id'])
        self.assertEqual(len(restored.records()['items']), 1)

    def test_closed_process_opens_files_without_old_projection(self):
        row = self.import_text()
        self.save_annotation(row)
        expected = self.store.snapshot()
        self.store.close()
        script = '''
import json,sys
from project_store import ProjectStore
from project_text import decode_records
with ProjectStore.open(sys.argv[1]) as store:
    snapshot=store.snapshot()
    decode_records(snapshot['records'])
    print(json.dumps(snapshot,ensure_ascii=False,sort_keys=True))
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.root / 'project')], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), expected)


if __name__ == '__main__':
    unittest.main()
