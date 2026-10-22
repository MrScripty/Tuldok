"""Workspace recovery/replay boundaries over disposable real PostgreSQL projections."""
import copy
import errno
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
import project_store
from project_store import ProjectStore, ProjectStoreError
from project_workspace import ProjectWorkspace, _digest
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable local PostgreSQL')
class ProjectWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tuldok-project-workspace-')
        self.path = Path(self.tmp.name)
        self.external = self.path / 'external'
        self.external.mkdir()
        self.hosts = []
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.cleanup_owned)
        self.start()

    def start(self, control=None):
        control = control or self.path / ('control-' + uuid.uuid4().hex)
        workspace = ProjectWorkspace(control, {'fixture': self.external}, dsn=os.environ['TULDOK_DATABASE_URL'])
        owner = ExplicitOwnerFixture.bootstrap(workspace)
        self.hosts.append((workspace, owner, control))
        self.workspace, self.owner = workspace, owner

    def cleanup_owned(self):
        schemas = set()
        for workspace, _owner, control in reversed(self.hosts):
            workspace.close()
            for manifest in Path(control).rglob('.tuldok.json'):
                value = json.loads(manifest.read_bytes())
                schemas.add('projection_' + value['projection_id'] if value['version'] == 2
                            else 'catalog_' + value['dataset_id'])
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            for schema in schemas:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def call(self, action, arguments=None):
        with self.owner.bound(self.workspace):
            return self.workspace.dispatch('project_files.' + action, arguments or {})

    def state(self):
        return self.call('status')

    def mutation(self, state=None, **extra):
        state = state or self.state()
        result = dict(binding=state['binding'],
                      expected_checkpoint=state['project']['checkpoint'] if state['project'] else None,
                      request_key=uuid.uuid4().hex)
        result.update(extra)
        return result

    def create(self, directory='alpha'):
        arguments = self.mutation(root='fixture', directory=directory, name='Workspace authored project')
        return self.call('new', arguments), arguments

    def import_record(self, text='Authored source'):
        arguments = self.mutation(asset=dict(text=text, name='Source', groups=['owned'], rights='Fixture authorship'))
        return self.call('import_text', arguments), arguments

    def annotate(self, row, note='Reviewed note'):
        arguments = self.mutation(record_id=row['id'], annotation=dict(
            revision=row['revision'], source_revision=1, task='text_corpus',
            annotation={'note': note}, groups=['owned'], review='human_reviewed'))
        return self.call('annotate', arguments), arguments

    def assert_code(self, code, action, arguments):
        with self.assertRaises((WorkbenchError, ProjectStoreError)) as caught:
            self.call(action, arguments)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def unknown_import(self):
        before = self.state()
        arguments = self.mutation(before, asset=dict(text='Uncertain publication', groups=['owned']))
        replace, fsync = project_store.os.replace, project_store.os.fsync
        published = False
        def after_replace(*args, **kwargs):
            nonlocal published
            replace(*args, **kwargs)
            published = True
        def fail_directory(fd):
            if published and fd == self.workspace._store._meta_fd:
                raise OSError(errno.EIO, 'actual checkpoint directory fsync failure')
            return fsync(fd)
        with patch.object(project_store.os, 'replace', side_effect=after_replace), patch.object(
                project_store.os, 'fsync', side_effect=fail_directory):
            self.assert_code('unknown', 'import_text', arguments)
        return before, arguments

    def test_unknown_fsync_status_and_explicit_current_open_reconcile_canonical_edit(self):
        self.create()
        before, edit = self.unknown_import()
        recovery = self.state()
        self.assertEqual(recovery['state'], 'recovery_required')
        self.assertEqual(recovery['binding'], before['binding'])
        self.assertEqual(recovery['project'], before['project'])
        self.assertEqual(recovery['available_actions'], ['open'])
        self.assertEqual(recovery['recovery'], dict(action='open', root='fixture', directory='alpha',
                         reason='unknown_publication', request_key=edit['request_key']))
        self.assert_code('projection_unavailable', 'close', self.mutation(recovery))
        self.assert_code('stale_project', 'open', self.mutation(recovery, root='fixture', directory='alpha',
                                                              expected_checkpoint='a' * 64))
        opened = self.call('open', self.mutation(recovery, root='fixture', directory='alpha'))
        self.assertEqual(opened['state'], 'open')
        self.assertNotEqual(opened['binding'], before['binding'])
        self.assertNotEqual(opened['project']['checkpoint'], before['project']['checkpoint'])
        replay = dict(edit, binding=opened['binding'])
        result = self.call('import_text', replay)
        self.assertEqual(result['record']['text'], 'Uncertain publication')
        self.assertEqual(result['record']['revision'], 1)
        with self.owner.bound(self.workspace):
            self.assertEqual(len(self.workspace._text.records()['items']), 1)

    def test_unknown_recovery_does_not_succeed_until_directory_sync_failure_clears(self):
        self.create()
        _before, edit = self.unknown_import()
        recovery = self.state()
        old_projection = self.workspace._projection
        metadata = (self.external / 'alpha/.tuldok').stat()
        fsync = project_store.os.fsync
        def fail_metadata_sync(fd):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) == (metadata.st_dev, metadata.st_ino):
                raise OSError(errno.EIO, 'persistent checkpoint directory fsync failure')
            return fsync(fd)
        reopen = self.mutation(recovery, root='fixture', directory='alpha')
        with patch.object(project_store.os, 'fsync', side_effect=fail_metadata_sync):
            self.assert_code('unavailable', 'open', reopen)
            self.assertEqual(self.state(), recovery)
            self.assertIs(self.workspace._projection, old_projection)
        opened = self.call('open', reopen)
        self.assertEqual(opened['state'], 'open')
        self.assertEqual(self.call('import_text', dict(edit, binding=opened['binding']))['record']['revision'], 1)

    def test_new_reconciliation_does_not_select_before_failed_parent_barrier_succeeds(self):
        before = self.state()
        arguments = self.mutation(before, root='fixture', directory='created', name='Await durable New')
        parent = self.external.stat()
        fsync = project_store.os.fsync
        def fail_published_parent(fd):
            info = os.fstat(fd)
            if ((info.st_dev, info.st_ino) == (parent.st_dev, parent.st_ino)
                    and (self.external / 'created').exists()):
                raise OSError(errno.EIO, 'persistent New parent directory fsync failure')
            return fsync(fd)
        with patch.object(project_store.os, 'fsync', side_effect=fail_published_parent):
            self.assert_code('unavailable', 'new', arguments)
            self.assertEqual(self.state(), before)
        with ProjectStore.open(self.external / 'created') as created:
            expected = created.snapshot()
        selected = self.call('new', arguments)
        self.assertEqual(selected['project']['project_id'], expected['project_id'])
        self.assertEqual(selected['project']['checkpoint'], expected['checkpoint'])

    def test_real_sql_commit_failure_reports_durable_receipt_and_explicit_open_restores(self):
        self.create()
        before = self.state()
        projection = self.workspace._projection
        projection.execute("""CREATE FUNCTION fixture_workspace_refuse_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'fixture deferred rejection' USING ERRCODE='23514'; END $$""")
        projection.execute("""CREATE CONSTRAINT TRIGGER fixture_workspace_commit_failure AFTER INSERT ON workbench_records
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fixture_workspace_refuse_commit()""")
        arguments = self.mutation(before, asset=dict(text='Durable despite rejected SQL commit', groups=['owned']))
        failure = self.assert_code('projection_unavailable', 'import_text', arguments)
        canonical = self.workspace._store.snapshot()
        self.assertEqual(failure.receipt, dict(committed=True, selected=True, project_id=canonical['project_id'],
                         checkpoint=canonical['checkpoint'], request_key=arguments['request_key']))
        self.assertEqual(projection.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 0)
        recovery = self.state()
        self.assertEqual(recovery['state'], 'recovery_required')
        self.assertEqual(recovery['project'], before['project'])
        self.assertEqual(recovery['recovery']['reason'], 'projection_unavailable')
        opened = self.call('open', self.mutation(recovery, root='fixture', directory='alpha'))
        self.assertEqual(opened['project']['checkpoint'], canonical['checkpoint'])
        result = self.call('import_text', dict(arguments, binding=opened['binding']))
        self.assertEqual(result['record']['text'], 'Durable despite rejected SQL commit')
        self.assertEqual(self.workspace._projection.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 1)
        self.assert_code('stale_project', 'import_text', arguments)

    def test_failed_reconstruction_keeps_recovery_generation_and_old_projection(self):
        self.create()
        before, edit = self.unknown_import()
        projection = self.workspace._projection
        recovery = self.state()
        arguments = self.mutation(recovery, root='fixture', directory='alpha')
        with patch.object(self.workspace, '_projection_for', side_effect=WorkbenchError('SQL unavailable', 'projection_unavailable', 503)):
            self.assert_code('projection_unavailable', 'open', arguments)
        self.assertIs(self.workspace._projection, projection)
        self.assertEqual(self.state(), recovery)
        opened = self.call('open', arguments)
        self.assertEqual(opened['state'], 'open')
        self.assertNotEqual(opened['binding'], before['binding'])
        self.assertEqual(self.call('import_text', dict(edit, binding=opened['binding']))['record']['revision'], 1)

    def test_new_projection_failure_reports_created_unselected_and_exact_retry(self):
        before = self.state()
        arguments = self.mutation(before, root='fixture', directory='created', name='Created unselected')
        with patch.object(self.workspace, '_projection_for', side_effect=RuntimeError('Projection initialization failed')):
            failure = self.assert_code('project_selection_unavailable', 'new', arguments)
        self.assertEqual(self.state(), before)
        self.assertEqual(failure.receipt, dict(committed=True, selected=False, project_id=failure.project_id,
                         checkpoint=failure.checkpoint, request_key=arguments['request_key'], root='fixture', directory='created'))
        with ProjectStore.open(self.external / 'created') as retained:
            self.assertEqual(retained.snapshot()['project_id'], failure.project_id)
        selected = self.call('new', arguments)
        self.assertEqual(selected['project']['project_id'], failure.project_id)
        self.assertEqual(selected['project']['checkpoint'], failure.checkpoint)

    def test_new_detach_failure_keeps_original_and_reconciles_after_restart(self):
        original, _ = self.create('original')
        arguments = self.mutation(root='fixture', directory='created', name='New survives failed Close')
        with patch.object(self.workspace, '_detach', side_effect=WorkbenchError('Close barrier failed', 'unavailable', 503)):
            failure = self.assert_code('project_selection_unavailable', 'new', arguments)
        self.assertEqual(self.state(), original)
        self.workspace.close()
        self.start()
        restarted = self.mutation(root='fixture', directory='created', name=arguments['name'], request_key=arguments['request_key'])
        selected = self.call('new', restarted)
        self.assertEqual(selected['project']['project_id'], failure.project_id)

    def test_new_receipt_rejects_changed_semantics_and_unrelated_existing_folder(self):
        arguments = self.mutation(root='fixture', directory='created', name='Original name')
        with patch.object(self.workspace, '_projection_for', side_effect=RuntimeError('Projection failed')):
            self.assert_code('project_selection_unavailable', 'new', arguments)
        before = (self.external / 'created/.tuldok/project.json').read_bytes()
        self.assert_code('conflict', 'new', dict(arguments, name='Changed name'))
        self.assertEqual((self.external / 'created/.tuldok/project.json').read_bytes(), before)
        with ProjectStore.create(self.external / 'unrelated', 'Other owner', 'unrelated', 'b' * 64):
            pass
        other = self.mutation(root='fixture', directory='unrelated', name='Original name')
        self.assert_code('conflict', 'new', other)
        self.assertEqual(self.state()['state'], 'no_project_open')

    def test_lifecycle_replay_is_idempotent_only_while_resulting_state_is_current(self):
        created, create_args = self.create()
        self.assertEqual(self.call('new', create_args), created)
        self.assert_code('conflict', 'new', dict(create_args, name='Changed payload'))
        imported, _ = self.import_record()
        self.assert_code('stale_project', 'new', create_args)
        save_args = self.mutation()
        saved = self.call('save', save_args)
        self.assertEqual(self.call('save', save_args), saved)
        updated, _ = self.annotate(imported['record'])
        self.assert_code('stale_project', 'save', save_args)
        close_args = self.mutation()
        closed = self.call('close', close_args)
        self.assertEqual(self.call('close', close_args), closed)
        open_args = self.mutation(root='fixture', directory='alpha')
        opened = self.call('open', open_args)
        self.assertEqual(self.call('open', open_args), opened)
        self.assertEqual(opened['state'], 'open')
        self.assert_code('stale_project', 'close', close_args)
        self.assertEqual(self.state(), opened)
        self.call('close', self.mutation())
        self.assert_code('stale_project', 'open', open_args)
        self.assertEqual(updated['record']['revision'], 2)

    def test_replay_history_never_exceeds_original_returned_revision(self):
        self.create()
        imported, import_args = self.import_record()
        annotated, annotate_args = self.annotate(imported['record'])
        self.annotate(annotated['record'], 'Third revision')
        original = self.call('import_text', import_args)
        self.assertEqual(original['record']['revision'], 1)
        self.assertEqual([item['revision'] for item in original['history']], [1])
        self.assertIsNone(original['next_history_before_revision'])
        original_review = self.call('annotate', annotate_args)
        self.assertEqual(original_review['record']['revision'], 2)
        self.assertEqual([item['revision'] for item in original_review['history']], [2])
        self.assertEqual(original_review['next_history_before_revision'], 2)

    def test_query_and_history_pages_are_bounded_and_complete(self):
        self.create()
        first, _ = self.import_record('First source')
        second, _ = self.import_record('Second source')
        current = self.state()
        query = dict(binding=current['binding'], checkpoint=current['project']['checkpoint'], limit=1)
        page = self.call('query', query)
        self.assertEqual(len(page['items']), 1)
        self.assertNotIn('text', page['items'][0])
        self.assertNotIn('annotation', page['items'][0])
        other = self.call('query', dict(query, after_id=page['next_after_id']))
        self.assertIsNone(other['next_after_id'])
        self.assertEqual({page['items'][0]['id'], other['items'][0]['id']}, {first['record']['id'], second['record']['id']})
        changed, _ = self.annotate(first['record'])
        self.annotate(changed['record'], 'Revision three')
        current = self.state()
        get = dict(binding=current['binding'], checkpoint=current['project']['checkpoint'], record_id=first['record']['id'], history_limit=2)
        detail = self.call('get', get)
        self.assertEqual([item['revision'] for item in detail['history']], [3, 2])
        older = self.call('get', dict(get, before_revision=detail['next_history_before_revision']))
        self.assertEqual([item['revision'] for item in older['history']], [1])
        self.assertIsNone(older['next_history_before_revision'])


if __name__ == '__main__':
    unittest.main()
