"""Shared runtime closures: compact storage, exact logical Run documents."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import project_record_dedupe as dedupe
import project_store as store_module
from project_store import ProjectStore


def runtime():
    files = {f'/opt/py/lib/module{i}.py': dict(bytes=10 + i, sha256=f'{i:064x}') for i in range(40)}
    return dict(assumption='fixture', closure_sha256='c' * 64, executable='/opt/py/bin/python',
                executable_sha256='e' * 64, files=files, flags=[], profile='fixture', trusted_install_owner_uid=0)


def run(identity, *, unique=3):
    edges = [dict(blob=dict(bytes=len(path), sha256=item['sha256']), name=f'runtime-files/{n}', population='unknown',
                  preservation='regenerable', required_for=['scientific_inspection'], role='historical_runtime')
             for n, (path, item) in enumerate(sorted(runtime()['files'].items()))]
    before = [dict(blob=dict(bytes=n, sha256=f'{n+100:064x}'), name=f'input/{identity}/{n}', population='unknown',
                   preservation='unique', required_for=['execution_proof'], role='execution_source') for n in range(unique)]
    after = [dict(blob=dict(bytes=7, sha256='a' * 64), name='output/model', population='unknown',
                  preservation='unique', required_for=['inspect'], role='output')]
    spec = dict(argv=['python', 'train.py', identity], runtime_files=[dict(path=p, **v) for p, v in sorted(runtime()['files'].items())])
    document = dict(format='project_run_history_v1', origin_catalog_id='a' * 32, admission_proof=None, publication=None,
                    run=dict(id=identity, spec=spec, material=dict(recipe=dict(id='r'), runtime=runtime()), events=[1.5, -0.0, 'é']),
                    payloads=before + edges + after)
    return dict(family='run_history', id='a' * 32 + '.' + identity, document=document)


class CompactionTests(unittest.TestCase):
    def test_exact_roundtrip_and_refusals(self):
        record = run('one')
        compacted, closure = dedupe.compact(record['document'])
        self.assertEqual(compacted['format'], dedupe.RUN_V2)
        self.assertNotIn('runtime_files', compacted['run']['spec'])
        self.assertEqual(store_module._encode(dedupe.expand(compacted, closure)), store_module._encode(record['document']))
        split = copy.deepcopy(record['document'])
        split['payloads'].insert(10, split['payloads'].pop(0))
        self.assertIsNone(dedupe.compact(split), 'A non-contiguous runtime block stays uncompacted')
        tampered = copy.deepcopy(closure); tampered['runtime']['profile'] = 'other'
        with self.assertRaises(store_module.ProjectStoreError):
            dedupe.expand(compacted, tampered)


class StoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-dedupe-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'project'
        self.store = ProjectStore.create(self.root, 'Dedupe fixture', 'new', 'a' * 64)
        self.addCleanup(lambda: self.store.close())

    def files(self, family):
        manifest = json.loads((self.root / '.tuldok/project.json').read_bytes())
        return [json.loads((self.root / '.tuldok' / e['path']).read_bytes()) for e in manifest['inventory'] if e['family'] == family]

    def test_runs_share_one_stored_closure_and_read_back_exactly(self):
        records = [run('one'), run('two', unique=5)]
        committed = self.store.commit(copy.deepcopy(records), self.store.summary()['checkpoint'], 'runs', 'b' * 64)
        self.assertEqual([r['document'] for r in committed['records']], [r['document'] for r in records])
        self.assertEqual([d['format'] for d in self.files('run_history')], [dedupe.RUN_V2, dedupe.RUN_V2])
        self.assertEqual(len(self.files(dedupe.CLOSURE_FAMILY)), 1)
        self.assertNotIn(dedupe.CLOSURE_FAMILY, {r['family'] for r in self.store.snapshot()['records']})
        self.store.close()
        self.store = ProjectStore.open(self.root)
        self.assertEqual(self.store.snapshot(), committed)
        # Editing one Run keeps the other's verified revision and the closure.
        changed = copy.deepcopy(records); changed[0]['document']['run']['events'].append('edited')
        again = self.store.commit(changed, committed['checkpoint'], 'edit', 'c' * 64)
        self.assertEqual(again['records'][0]['document'], changed[0]['document'])
        self.store.close()
        self.store = ProjectStore.open(self.root)
        self.assertEqual(self.store.snapshot(), again)
        self.assertEqual(len(self.files(dedupe.CLOSURE_FAMILY)), 1)

    def test_closures_are_store_owned(self):
        with self.assertRaises(store_module.ProjectStoreError):
            self.store.commit([dict(family=dedupe.CLOSURE_FAMILY, id='x', document=dict(format=dedupe.CLOSURE_FORMAT))],
                              self.store.summary()['checkpoint'], 'forged', 'd' * 64)


if __name__ == '__main__':
    unittest.main()


import os
import uuid


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class WorkingStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-dedupe-working-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'project'
        with ProjectStore.create(self.root, 'Legacy runs', 'new', 'a' * 64) as store:
            records = [run('one'), run('two', unique=4)]
            self.legacy = store.commit(copy.deepcopy(records), store.summary()['checkpoint'], 'runs', 'b' * 64)
        self.working_id = uuid.uuid4().hex
        self.addCleanup(self.drop)

    def drop(self):
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        with psycopg.connect(connection_info(None), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier('working_' + self.working_id)))

    def working(self):
        from project_working_store import WorkingProjectStore
        parent, leaf = os.path.split(str(self.root))
        descriptor = os.open(parent, store_module.DIR_FLAGS)
        try:
            folder = ProjectStore.open_folder_at(descriptor, leaf, root_path=parent)
        finally:
            os.close(descriptor)
        return WorkingProjectStore.open(folder, self.working_id)

    def test_migration_keeps_logical_records_and_saves_compact_files(self):
        from project_composition import _record_sha
        store = self.working()
        try:
            before = store.snapshot()['records']
            previous, after = store.compact_run_closures('compact-runs', 'c' * 64)
            self.assertNotEqual(previous, after['checkpoint'])
            self.assertEqual(store.snapshot()['records'], before, 'Logical records are unchanged')
            self.assertEqual(store.records('run_history'), [r for r in before if r['family'] == 'run_history'])
            self.assertEqual(store.record('run_history', before[0]['id']), before[0])
            view = store.records_view('run_history')
            self.assertNotIn(dedupe.CLOSURE_FAMILY, {r['family'] for r in view})
            digests = store.envelope_digests()
            for record in before:
                self.assertEqual(digests[(record['family'], record['id'])], _record_sha(record))
            # An edit through the session path keeps the shared closure.
            changed = copy.deepcopy(before); changed[1]['document']['run']['events'].append('edited')
            edited = store.commit(changed, after['checkpoint'], 'edit', 'd' * 64, changed={(changed[1]['family'], changed[1]['id']), })
            store.save(edited['checkpoint'])
            saved = store.snapshot()
        finally:
            store.close()
        manifest = json.loads((self.root / '.tuldok/project.json').read_bytes())
        families = [e['family'] for e in manifest['inventory']]
        self.assertEqual(families.count(dedupe.CLOSURE_FAMILY), 1)
        self.assertEqual({e['format'] for e in manifest['inventory'] if e['family'] == 'run_history'}, {dedupe.RUN_V2})
        with ProjectStore.open(self.root) as reread:
            self.assertEqual(reread.snapshot(), saved, 'The file store reads the same logical records')
