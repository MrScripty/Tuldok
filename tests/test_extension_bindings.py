"""Actual E1 snapshot binding and custody, without a Run or executable fixture."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth_helpers import bind_owner
from access import AccessError
from app import Dataset
import extension_bindings
from workbench import WorkbenchError

FIXTURE = Path(__file__).parent / 'fixtures/extensions/catalog'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the extension validator')
class ExtensionBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.external = self.root / 'external'
        shutil.copytree(FIXTURE, self.external)
        self.project = json.loads((self.external / 'project.json').read_bytes())
        self.extension = json.loads((self.external / 'extension.json').read_bytes())
        self.model = json.loads((self.external / 'model.json').read_bytes())
        self.dataset = Dataset(self.root / 'catalog', project_roots={'fixture': self.external})
        self.addCleanup(self.dataset.close)
        self.owner = bind_owner(self, self.dataset)
        self.selection = self.ref(self.extension['contributions'][0])

    @staticmethod
    def ref(value):
        return {key: value[key] for key in ('id', 'version', 'sha256')}

    def write_json(self, path, value):
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        (self.external / path).write_bytes(raw)
        return raw

    def save_extension(self):
        raw = self.write_json('extension.json', self.extension)
        self.project['extensions'][0]['sha256'] = digest(raw)

    def save_model(self):
        raw = self.write_json('model.json', self.model)
        self.extension['contributions'][0].update(sha256=digest(raw), bytes=len(raw))
        self.selection = self.ref(self.extension['contributions'][0])
        self.save_extension()

    def open(self, project=None, path='project.json'):
        value = self.project if project is None else project
        raw = self.write_json(path, value)
        self.dataset.projects.open_snapshot({'root': 'fixture', 'manifest_path': path})
        return value['id'], digest(raw)

    def resolve(self, snapshot=None, selections=None):
        return extension_bindings.resolve(self.dataset.projects, *(snapshot or self.open()),
            [self.selection] if selections is None else selections)

    def test_exact_deterministic_inert_capture_and_legacy_refusal(self):
        snapshot = self.open()
        before = {path.name: path.read_bytes() for path in self.external.iterdir()}
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Binding must be inert')):
            result = self.resolve(snapshot)
            self.assertEqual(result, self.resolve(snapshot))
        binding = result['binding']
        self.assertEqual(set(binding), {'format', 'project', 'schema_sha256', 'selections',
                                        'contributions', 'inventory'})
        self.assertEqual(binding['project'], {'id': snapshot[0], 'manifest_sha256': snapshot[1]})
        self.assertEqual(binding['contributions'][0]['definition'], self.model)
        self.assertEqual(binding['contributions'][0]['provider'], {
            'reference_id': 'example', **self.extension['package'],
            'sha256': self.project['extensions'][0]['sha256']})
        self.assertEqual(set(result['blobs']), {'project.json', 'extension.json', 'model.json',
                                               'worker.py', 'NOTICE.txt'})
        for item in binding['inventory']:
            self.assertEqual(item['sha256'], digest(result['blobs'][item['path']]))
            self.assertEqual(item['bytes'], len(result['blobs'][item['path']]))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.external.iterdir()})
        self.assertEqual(self.dataset.runs.list(), [])
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_grants').fetchone()[0], 0)
        for call in (
            lambda: self.dataset.projects.read_data_reference(snapshot[0], 'x', '0'*64, 32),
            lambda: self.dataset.projects.read_recipe_reference(snapshot[0], 'x', '0'*64),
            lambda: self.dataset.projects.read_recipe_sources(snapshot[0], [{'path':'worker.py','sha256':'0'*64}]),
        ):
            with self.assertRaises(WorkbenchError) as caught:
                call()
            self.assertEqual(caught.exception.code, 'unsupported')

    def test_internal_snapshot_reference_wrappers_and_current_manifest(self):
        data, recipe, source = b'inert data', b'{"format":"inert"}', (self.external/'worker.py').read_bytes()
        (self.external/'data.bin').write_bytes(data)
        (self.external/'recipe.json').write_bytes(recipe)
        for group, path, raw in [('data','data.bin',data), ('recipes','recipe.json',recipe)]:
            self.project[group] = [{'id':'selected','label':'Selected','path':path,'sha256':digest(raw)}]
        snapshot = self.open()
        projects = self.dataset.projects
        self.assertEqual(projects.read_snapshot_data_reference(snapshot[0], 'selected', digest(data), 64)[0], data)
        self.assertEqual(projects.read_snapshot_recipe_reference(snapshot[0], 'selected', digest(recipe))[0], recipe)
        self.assertEqual(projects.read_snapshot_recipe_sources(snapshot[0],
            [{'path':'worker.py','sha256':digest(source)}]), {'worker.py':source})
        changed = dict(self.project, name='Changed')
        self.write_json('project.json', changed)
        for call in (
            lambda: self.resolve(snapshot),
            lambda: projects.read_snapshot_data_reference(snapshot[0], 'selected', digest(data), 64),
            lambda: projects.read_snapshot_recipe_reference(snapshot[0], 'selected', digest(recipe)),
            lambda: projects.read_snapshot_recipe_sources(snapshot[0], [{'path':'worker.py','sha256':digest(source)}]),
        ):
            with self.assertRaises(WorkbenchError) as caught:
                call()
            self.assertEqual(caught.exception.code, 'stale')

    def add_task(self, dependency=None):
        task = {'format':'tuldok_contribution_v1', 'id':'example.field:task', 'version':'1.0.0',
                'kind':'task', 'label':'Inert task', 'requires':[dependency or self.selection]}
        raw = self.write_json('task.json', task)
        ref = {key:task[key] for key in ('id','version','kind')}
        ref.update(path='task.json', sha256=digest(raw), bytes=len(raw))
        self.extension['contributions'].append(ref)
        self.save_extension()
        return self.ref(ref)

    def test_transitive_exact_requirement_capture_and_missing_dependency(self):
        task = self.add_task()
        result = self.resolve(selections=[task])
        self.assertEqual([item['id'] for item in result['binding']['contributions']],
                         ['example.field:model','example.field:task'])
        self.assertIn('task.json', result['blobs'])
        self.assertEqual(result['binding']['selections'], [task])
        # A separately enabled immutable snapshot cannot substitute another hash.
        value = copy.deepcopy(self.project)
        value['id'] = 'd'*32
        task_value = json.loads((self.external/'task.json').read_bytes())
        task_value['requires'][0]['sha256'] = '0'*64
        raw = self.write_json('task.json', task_value)
        self.extension['contributions'][-1].update(sha256=digest(raw), bytes=len(raw))
        self.save_extension()
        value['extensions'] = self.project['extensions']
        with self.assertRaises(WorkbenchError):
            self.resolve(self.open(value, 'missing-dependency.json'), [self.ref(self.extension['contributions'][-1])])

    def test_all_contribution_kinds_retain_closed_definitions_without_dispatch(self):
        selected = [self.selection]
        for kind in ('task', 'reader', 'trainer', 'evaluator', 'view'):
            value = copy.deepcopy(self.model)
            value.update(id='example.field:'+kind, kind=kind, label='Inert '+kind)
            if kind == 'task':
                value['requires'] = [self.selection]
            if kind == 'trainer':
                value['stages'] = [{'id':'fit','version':'1.0.0','inputs':['input'],
                                    'outputs':['output'],'clock':'epoch','failure_policy':'fail'}]
            if kind == 'view':
                value.pop('implementation')
                value['view'] = {'primitive':'table','query':{'id':'example.field:query','version':'1.0.0'},
                                 'label':'Inert view'}
            raw = self.write_json(kind+'.json', value)
            ref = {key:value[key] for key in ('id','version','kind')}
            ref.update(path=kind+'.json', sha256=digest(raw), bytes=len(raw))
            self.extension['contributions'].append(ref)
            selected.append(self.ref(ref))
        self.save_extension()
        result = self.resolve(selections=list(reversed(selected)))
        self.assertEqual({item['kind'] for item in result['binding']['contributions']},
                         {'task','reader','model','trainer','evaluator','view'})
        self.assertEqual(result, self.resolve(selections=selected))

    def test_wrong_hash_wrong_provider_and_disabled_snapshot(self):
        snapshot = self.open()
        with self.assertRaises(WorkbenchError):
            self.resolve(snapshot, [dict(self.selection, sha256='0'*64)])
        with self.assertRaises(WorkbenchError):
            self.resolve(snapshot, [dict(self.selection, id='other.package:model')])
        disabled = dict(self.project, id='d'*32, extensions=[])
        with self.assertRaises(WorkbenchError):
            self.resolve(self.open(disabled, 'disabled.json'))
        self.assertEqual(self.resolve(snapshot)['binding']['selections'], [self.selection])
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve((snapshot[0], '0'*64))
        self.assertEqual(caught.exception.code, 'stale')

    def test_conflicting_package_and_ambiguous_duplicate_provider_refuse(self):
        other = dict(self.extension, label='Conflicting content')
        raw = self.write_json('other-extension.json', other)
        self.project['extensions'].append({'id':'other','label':'Other','path':'other-extension.json','sha256':digest(raw)})
        with self.assertRaises(WorkbenchError):
            self.resolve()
        # Even identical bytes with two enabled provider refs are ambiguous.
        self.project['id'] = 'd'*32
        self.project['extensions'][-1].update(path='extension.json', sha256=self.project['extensions'][0]['sha256'])
        with self.assertRaises(WorkbenchError):
            self.resolve(self.open(self.project, 'ambiguous.json'))

    def test_unsupported_host_malformed_defaults_and_nonfinite_definition(self):
        self.extension['host_contracts'][0]['version'] = '9.0.0'
        self.save_extension()
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, 'unsupported')
        self.project['id'] = 'd'*32
        self.extension['host_contracts'][0]['version'] = '1.0.0'
        self.model['defaults']['width'] = True
        self.save_model()
        with self.assertRaises(WorkbenchError):
            self.resolve(self.open(self.project, 'bad-default.json'))
        raw = (self.external/'model.json').read_bytes().replace(b'true', b'1e309')
        (self.external/'model.json').write_bytes(raw)
        self.extension['contributions'][0].update(sha256=digest(raw), bytes=len(raw))
        self.selection = self.ref(self.extension['contributions'][0])
        self.save_extension()
        self.project['id'] = 'c'*32
        with self.assertRaises(WorkbenchError):
            self.resolve(self.open(self.project, 'nonfinite.json'))

    def test_changed_root_and_symlink_source_refuse(self):
        snapshot = self.open()
        original = self.dataset.projects.roots['fixture']
        replacement = self.root/'replacement'
        shutil.copytree(self.external, replacement)
        fd = os.open(replacement, os.O_RDONLY | os.O_DIRECTORY)
        info = os.fstat(fd)
        try:
            self.dataset.projects.roots['fixture'] = (fd, [info.st_dev,info.st_ino])
            with self.assertRaises(WorkbenchError):
                self.resolve(snapshot)
        finally:
            self.dataset.projects.roots['fixture'] = original
            os.close(fd)
        worker = self.external/'worker.py'
        worker.rename(self.external/'retained-worker.py')
        worker.symlink_to('retained-worker.py')
        with self.assertRaises(WorkbenchError):
            self.resolve(snapshot)

    def test_parent_directory_replacement_during_read_refuses(self):
        nested = self.external/'nested'
        nested.mkdir()
        raw = (self.external/'worker.py').read_bytes()
        (nested/'worker.py').write_bytes(raw)
        self.extension['sources'][0]['path'] = 'nested/worker.py'
        self.model['implementation']['source'] = 'nested/worker.py'
        self.save_model()
        snapshot = self.open()
        original = self.dataset.projects._read
        def race(root, path, limit):
            result = original(root, path, limit)
            if path == 'nested/worker.py':
                nested.rename(self.external/'retained-nested')
                nested.mkdir()
                (nested/'worker.py').write_bytes(raw)
            return result
        with patch.object(self.dataset.projects, '_read', side_effect=race), self.assertRaises(WorkbenchError):
            self.resolve(snapshot)

    def test_aggregate_eight_mib_budget_preflights_large_source(self):
        worker = self.external/'worker.py'
        with worker.open('wb') as stream:
            stream.truncate(8*1024*1024)
        raw_hash = digest(worker.read_bytes())
        self.extension['sources'][0].update(bytes=8*1024*1024, sha256=raw_hash)
        self.extension['resources']['source_bytes'] = 8*1024*1024
        self.save_extension()
        with self.assertRaises(WorkbenchError):
            self.resolve()

    def test_binding_document_counts_toward_the_capture_budget(self):
        worker = self.external/'worker.py'
        size = 8*1024*1024 - 3072
        with worker.open('wb') as stream:
            stream.truncate(size)
        self.extension['sources'][0].update(bytes=size, sha256=digest(worker.read_bytes()))
        self.extension['resources']['source_bytes'] = size
        self.save_extension()
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, 'too_large')
        self.assertIn('Binding document', str(caught.exception))

    def test_closed_selection_bounds_and_owner_authority(self):
        snapshot = self.open()
        for expected in (None, True, '0'*63):
            with self.subTest(expected=expected), self.assertRaises(WorkbenchError):
                self.resolve((snapshot[0], expected))
        for selections in ([], [self.selection]*2, [dict(self.selection, extra=True)],
                           [dict(self.selection, version=True)], [self.selection]*65):
            with self.subTest(selections=selections), self.assertRaises(WorkbenchError):
                self.resolve(snapshot, selections)
        agent = self.dataset.access.issue({'label':'E1 binding boundary','scopes':['inspect','edit']})
        with self.dataset.access.bind(agent['token']), self.assertRaises(AccessError):
            self.resolve(snapshot)
