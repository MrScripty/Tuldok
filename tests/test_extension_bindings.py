"""Actual E1 binding/custody; optional admitted prelaunch regression, no numeric claim."""
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
        self.assertEqual(binding['project'], {'id': snapshot[0], 'manifest_sha256': snapshot[1], 'manifest_path':'project.json'})
        self.assertEqual(binding['contributions'][0]['definition'], self.model)
        self.assertEqual(binding['contributions'][0]['provider'], {
            'reference_id': 'example', **self.extension['package'],
            'sha256': self.project['extensions'][0]['sha256'],'runtime':self.extension['runtime'],
            'effects':self.extension['effects'],'resources':self.extension['resources']})
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


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the extension validator')
class BoundExtensionRecipeTests(unittest.TestCase):
    """Real owner publication/graph capture metadata; no executed scientific Run."""
    def setUp(self):
        import recipe_contract
        from model_definitions import ModelDefinitions
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.project=self.root/'project'
        package=Path(__file__).resolve().parents[1]/'examples/extensions/field-surrogate/v2'
        shutil.copytree(package,self.project)
        self.recipe=json.loads((self.project/'recipe.json').read_bytes())
        self.recipe.update(schema_version=3,format=recipe_contract.BOUND_EVIDENCE_FORMAT)
        self.recipe['model_evidence']['model_specification']['configuration']={'width':2}
        model={'format':'tuldok_contribution_v1','id':'example.scalar-a:model','version':'2.0.0',
            'kind':'model','label':'Inert bound model','requires':[],
            'parameters':{'type':'object','properties':{'width':{'type':'integer','minimum':1,'maximum':8}},
                          'required':['width'],'additionalProperties':False},
            'defaults':{'width':2},'implementation':{'source':self.recipe['entrypoint'],'entrypoint':'main'}}
        task=self.recipe['model_evidence']['task']['definition']
        task['stages'].append({'id':'post_train_mapping','version':'2.0.0','inputs':['prediction'],
            'outputs':['prediction'],'clock':'optimizer_update','failure_policy':'fail'})
        model['ports']=[copy.deepcopy(port) for port in task['ports'] if port['direction'] in ('input','output')]
        trainer=copy.deepcopy(model)
        trainer.update(id='example.scalar-a:trainer',kind='trainer',label='Inert bound trainer',
            ports=copy.deepcopy(task['ports']),stages=task['stages'],parameters={'type':'object','properties':{
                'learning_rate':{'type':'number','minimum':0.001,'maximum':0.5},
                'updates':{'type':'integer','minimum':64,'maximum':64}},
                'required':['learning_rate','updates'],'additionalProperties':False},
            defaults={key:value['default'] for key,value in self.recipe['parameters'].items()})
        evaluator=copy.deepcopy(model);evaluator.update(id='example.scalar-a:evaluator',kind='evaluator',
            ports=[copy.deepcopy(port) for port in task['ports'] if port['direction'] in ('target','output')])
        view={'format':'tuldok_contribution_v1','id':'example.scalar-a:view','version':'2.0.0','kind':'view',
            'label':'Inert bound view','requires':[],
            'view':{'primitive':'orthogonal_slices','query':{'id':'tuldok:runs.model_evidence','version':'2.0.0'},'label':'Field'}}
        self.definitions={'task':task,'model':model,'trainer':trainer,'evaluator':evaluator,'view':view}
        self.extension={'format':'tuldok_extension_v1','package':{'id':'example.scalar-a','version':'2.0.0'},
            'label':'Inert binding integration fixture','license':{'id':'private-test-fixture','notices':[]},
            'sources':[],'host_contracts':[{'id':'tuldok:extension','version':'1.0.0'},
                                          {'id':'tuldok:project','version':'2.0.0'}],
            'runtime':{'profile':'captured_cpu_python_v1'},'effects':['filesystem'],
            'resources':{'wall_seconds':self.recipe['resources']['wall_seconds'],'source_bytes':8*1024*1024,
                         'output_bytes':self.recipe['resources']['max_output_bytes']},'contributions':[]}
        for source in self.recipe['sources']:
            raw=(self.project/source['path']).read_bytes()
            self.extension['sources'].append(dict(source,bytes=len(raw)))
        for role,value in self.definitions.items():
            raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
            path=role+'-contribution.json';(self.project/path).write_bytes(raw)
            self.extension['contributions'].append({'id':value['id'],'version':value['version'],'kind':role,
                'path':path,'bytes':len(raw),'sha256':digest(raw)})
        self.recipe['extension_selection']={'selections':{ref['kind']:{key:ref[key] for key in ('id','version','sha256')}
                                                        for ref in self.extension['contributions']}}
        self.manifest=json.loads((self.project/'project.json').read_bytes())
        self.manifest.update(schema_version=2,extensions=[])
        self.write_project()
        self.dataset=Dataset(self.root/'catalog',project_roots={'fixture':self.project})
        self.addCleanup(self.dataset.close);self.owner=bind_owner(self,self.dataset)
        self.models=ModelDefinitions(self.dataset);self.dataset.models=self.models
        self.dataset.projects.open_snapshot({'root':'fixture','manifest_path':'project.json'})

    def write_project(self):
        raw=json.dumps(self.extension,sort_keys=True,separators=(',',':')).encode()
        (self.project/'provider.json').write_bytes(raw)
        self.manifest['extensions']=[{'id':'selected','label':'Selected','path':'provider.json','sha256':digest(raw)}]
        raw=json.dumps(self.recipe,sort_keys=True,separators=(',',':')).encode()
        (self.project/'recipe.json').write_bytes(raw)
        self.selector={'project_id':self.manifest['id'],'recipe_id':self.manifest['recipes'][0]['id'],'expected_sha256':digest(raw)}
        self.manifest['recipes'][0]['sha256']=digest(raw)
        (self.project/'project.json').write_text(json.dumps(self.manifest))

    def inspect(self,version=None):
        return self.dataset.pipelines.inspect_external_recipe(self.selector['project_id'],self.selector['recipe_id'],
            self.selector['expected_sha256'],contract_version=version)

    def body(self):
        from pipeline import digest as document_digest
        policy=self.recipe['model_evidence']
        return {'name':'Actual inert E1 bound Model','kind':'captured_source',
            'task':{'kind':'task','catalog_id':self.dataset.db.dataset_id,'id':policy['task']['id'],
                    'revision':policy['task']['revision'],'sha256':document_digest(policy['task']['definition'])},
            'specification':policy['model_specification'],'preprocessing_policy':policy['preprocessing_policy'],
            'output_policy':policy['output_policy'],'source_selector':self.selector}

    def test_inspect_publish_graph_and_cold_model_use_real_bound_sources(self):
        import recipe_contract
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Inert owner capture must not run')):
            inspected=self.inspect(2)
            draft=self.models.create(self.body());published=self.models.publish(draft['id'],{'revision':1})
            graph=self.dataset.pipelines.create_external({'name':'Bound graph',**self.selector,
                'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':self.manifest['data'][0]['sha256']}}})
        self.assertEqual(inspected['extension_binding']['project']['id'],self.manifest['id'])
        provider=inspected['extension_binding']['contributions'][0]['provider']
        self.assertEqual(provider['runtime'],self.extension['runtime'])
        self.assertEqual(provider['effects'],self.extension['effects'])
        self.assertEqual(provider['resources'],self.extension['resources'])
        closure={item['import_path']:self.models.read_blob(published['ref'],item['blob'])
                 for item in published['material']['source_closure']}
        self.assertIn(extension_bindings.BINDING_PATH,closure)
        self.assertIn('recipe.json',closure)
        self.assertIn('view-contribution.json',closure)
        self.assertTrue(recipe_contract.is_bound_evidence(inspected['definition']))
        self.assertFalse(recipe_contract.is_evidence(dict(inspected['definition'],schema_version=True)))
        self.assertEqual(graph['nodes'][0]['parameters']['project_id'],self.manifest['id'])
        shutil.rmtree(self.project)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Cold reads must not execute')):
            self.assertEqual(self.models.material(published['ref'],verify=True),published)
        self.assertEqual(self.dataset.runs.list(),[])

    def test_two_valid_model_configurations_bind_distinct_retained_identities(self):
        import recipe_contract
        import extension_evidence
        inspected=self.inspect();binding=inspected['extension_binding']
        self.assertEqual(inspected['model_task'],self.body()['task'])
        self.assertEqual(inspected['selection_policy']['numerical_acceptance'],'diagnostic')
        models=[]
        for width in (2,4):
            body=copy.deepcopy(self.body());body['specification']['configuration']['width']=width
            draft=self.models.create(body);published=self.models.publish(draft['id'],{'revision':1})
            self.models.material(published['ref'],verify=True)
            # This is pure static-policy derivation from actually published Model
            # bytes and authored input receipts, never a fabricated Run/completion.
            data=self.manifest['data'][0]
            execution={'catalog_id':self.dataset.db.dataset_id,'recipe':self.recipe,
                'extension_binding':binding,'parameters':recipe_contract.validate_parameters(self.recipe,{}),
                'inputs':{'fixture':{'project_id':self.manifest['id'],
                    'manifest_sha256':binding['project']['manifest_sha256'],'reference_id':data['id'],
                    'path':data['path'],'measured_sha256':data['sha256']}}}
            static=extension_evidence.resolve(self.recipe['model_evidence'],published,execution,
                model_specification=body['specification'],binding=binding)
            self.assertEqual(static['policy']['model_specification']['configuration'],{'width':width})
            with self.assertRaises(WorkbenchError):
                extension_evidence.resolve(self.recipe['model_evidence'],published,execution,
                    model_specification=dict(body['specification'],configuration={'width':3}),binding=binding)
            models.append(published)
        self.assertNotEqual(models[0]['ref']['sha256'],models[1]['ref']['sha256'])
        bad=copy.deepcopy(self.body());bad['specification']['trainable_parameters']=['changed']
        draft=self.models.create(bad)
        with self.assertRaises(WorkbenchError) as caught:self.models.publish(draft['id'],{'revision':1})
        self.assertEqual(caught.exception.code,'stale')

    def test_legacy_inspector_explicitly_refuses_new_variant(self):
        with self.assertRaises(WorkbenchError) as caught:self.inspect(1)
        self.assertEqual(caught.exception.code,'unsupported')
        self.assertIn('extension_binding',self.inspect(2))

    def test_role_config_and_trainer_controls_refuse_before_publication(self):
        import recipe_contract
        inspected=self.inspect();binding=inspected['extension_binding']
        wrong=copy.deepcopy(self.recipe)
        wrong['extension_selection']['selections']['view']=wrong['extension_selection']['selections']['model']
        with self.assertRaises(WorkbenchError):extension_bindings.validate_roles(binding,wrong['extension_selection'])
        body=copy.deepcopy(self.body());body['specification']['configuration']['width']=True
        draft=self.models.create(body)
        with self.assertRaises(WorkbenchError):self.models.publish(draft['id'],{'revision':1})
        with self.assertRaises(WorkbenchError):extension_bindings.validate_configuration(binding,self.recipe,
            {'learning_rate':0.1,'updates':63})
        wrong=copy.deepcopy(self.recipe);wrong['parameters']['updates']['default']=65
        with self.assertRaises(WorkbenchError):extension_bindings.validate_configuration(binding,wrong,
            recipe_contract.validate_parameters(self.recipe,{}))
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_materials').fetchone()[0],0)

    def _rebind_definitions(self):
        self.extension['contributions']=[]
        for role,value in self.definitions.items():
            raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
            path=role+'-contribution.json';(self.project/path).write_bytes(raw)
            self.extension['contributions'].append({'id':value['id'],'version':value['version'],'kind':role,
                'path':path,'bytes':len(raw),'sha256':digest(raw)})
        self.recipe['extension_selection']={'selections':{ref['kind']:{key:ref[key] for key in ('id','version','sha256')}
                                                        for ref in self.extension['contributions']}}
        self.manifest['id']=__import__('uuid').uuid4().hex
        self.write_project()
        self.dataset.projects.open_snapshot({'root':'fixture','manifest_path':'project.json'})

    def test_incompatible_ports_stages_clocks_and_view_query_refuse_before_effect(self):
        original=copy.deepcopy(self.definitions)
        changes=[lambda d:d['trainer']['stages'][0].update(inputs=['missing_port']),
                 lambda d:d['trainer']['stages'][0].update(clock='fictional_clock'),
                 lambda d:d['model']['ports'][0].update(units='metres'),
                 lambda d:d['view']['view'].update(query={'id':'foreign.package:query','version':'99.0.0'}),
                 lambda d:d['trainer']['ports'][0]['contract'].update(version='99.0.0')]
        for change in changes:
            self.definitions=copy.deepcopy(original);change(self.definitions)
            self._rebind_definitions()
            with self.subTest(change=change),self.assertRaises(WorkbenchError):self.inspect(2)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_materials').fetchone()[0],0)
        self.assertEqual(self.dataset.runs.list(),[])

    def test_declared_source_mask_and_correction_stages_do_not_need_host_names(self):
        task=self.definitions['task']
        template=copy.deepcopy(task['ports'][0])
        for name in ('source_term','mask'):
            port=copy.deepcopy(template);port['id']=name;task['ports'].append(port)
        corrected=copy.deepcopy(next(port for port in task['ports'] if port['direction']=='output'))
        corrected['id']='corrected';task['ports'].append(corrected)
        task['stages'].append({'id':'authored_correction','version':'1.0.0',
            'inputs':['prediction','source_term','mask'],'outputs':['corrected'],
            'clock':'optimizer_update','failure_policy':'fail'})
        for role,directions in [('model',('input','output')),('trainer',('input','target','output')),
                                 ('evaluator',('target','output'))]:
            self.definitions[role]['ports']=[copy.deepcopy(port) for port in task['ports'] if port['direction'] in directions]
        self.definitions['trainer']['stages']=copy.deepcopy(task['stages'])
        self.recipe['model_evidence']['task']['definition']=task
        self._rebind_definitions()
        # Port-only declarations cannot stand in for consumed probe/evidence I/O.
        with self.assertRaises(WorkbenchError):self.inspect(2)
        policy=self.recipe['model_evidence']
        for name in ('source_term','mask'):
            descriptor=copy.deepcopy(policy['fields'][0]['contract']['inputs'][0]);descriptor['field_id']=name
            policy['fields'][0]['contract']['inputs'].append(descriptor)
            for row in policy['probe_inputs']:row['fields'].append({'field_id':name,'artifact':'input-'+name+'.npy'})
            self.recipe['outputs'].append({'path':'input-'+name+'.npy','role':'probe_input','max_bytes':8192,'required':True})
        corrected_field=copy.deepcopy(policy['fields'][0]);corrected_field['id']='corrected'
        corrected_field['contract']['output'].update(field_id='corrected',stage='authored_correction')
        policy['fields'].append(corrected_field)
        original_outputs={item['path']:item for item in self.recipe['outputs']}
        for item in list(policy['field_outputs']):
            corrected_binding=copy.deepcopy(item);corrected_binding.update(field_id='corrected',prediction='corrected-'+item['prediction'])
            policy['field_outputs'].append(corrected_binding)
            output=copy.deepcopy(original_outputs[item['prediction']]);output['path']=corrected_binding['prediction']
            self.recipe['outputs'].append(output)
        self.recipe['resources']['profile']='captured_cpu_large_outputs_v1'
        policy['model_specification']['input_fields']+=['source_term','mask']
        policy['model_specification']['output_fields']+=['corrected']
        self._rebind_definitions()
        inspected=self.inspect(2)
        self.assertEqual(inspected['extension_binding']['contributions'][-1]['kind'],'view')
        draft=self.models.create(self.body());published=self.models.publish(draft['id'],{'revision':1})
        self.assertEqual(self.models.material(published['ref'],verify=True),published)

    def test_retained_binding_corruption_and_missing_provider_definition_refuse(self):
        import recipe_contract
        inspected=self.inspect();sources=recipe_contract.bound_sources(self.dataset.projects,inspected)
        binding=inspected['extension_binding']
        self.assertEqual(recipe_contract.validate_bound_sources(self.recipe,binding,sources),binding)
        for path in ('model-contribution.json','view-contribution.json','provider.json'):
            changed=dict(sources);changed.pop(path)
            with self.subTest(path=path),self.assertRaises(WorkbenchError):
                recipe_contract.validate_bound_sources(self.recipe,binding,changed)
        changed=dict(sources);changed['model-contribution.json']+=b' '
        with self.assertRaises(WorkbenchError):recipe_contract.validate_bound_sources(self.recipe,binding,changed)

    def test_contradictory_provider_runtime_pin_and_legacy_contract_types_refuse(self):
        for version in (True,1.0,'2',3):
            with self.subTest(version=version),self.assertRaises(WorkbenchError):self.inspect(version)
        self.extension['runtime']['snapshot_sha256']='f'*64
        self._rebind_definitions()
        with self.assertRaises(WorkbenchError) as caught:self.inspect(2)
        self.assertEqual(caught.exception.code,'stale')

    def test_provider_runtime_and_resource_requirements_intersect_before_publication(self):
        original=copy.deepcopy(self.extension)
        for change in (lambda e:e['runtime'].update(profile='unsupported_foreign_runtime_v99'),
                       lambda e:e['resources'].update(wall_seconds=self.recipe['resources']['wall_seconds']-1),
                       lambda e:e['resources'].update(output_bytes=self.recipe['resources']['max_output_bytes']-1)):
            self.extension=copy.deepcopy(original);change(self.extension)
            self._rebind_definitions()
            with self.subTest(change=change),self.assertRaises(WorkbenchError):self.inspect(2)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_materials').fetchone()[0],0)

    def test_dispatch_host_identity_selects_the_bound_source_and_query_authority(self):
        import recipe_contract
        expected=recipe_contract.recipe_host_identity(self.recipe)
        self.assertEqual(set(expected),set(recipe_contract.BOUND_EVIDENCE_HOST_NAMES))
        self.assertIn('agent_api.py',expected)
        self.assertIn('extension_bindings.py',expected)
        self.assertNotEqual(expected,recipe_contract.host_identity(evidence=True))

    @unittest.skipUnless(os.environ.get('TULDOK_BOUND_RUNTIME_CATALOG') and os.environ.get('TULDOK_BOUND_RUNTIME_DESCRIPTOR'),
                         'Requires an isolated preprovisioned actual CPU runtime catalog and descriptor')
    def test_actual_full_grant_staleness_refusal_and_bound_dispatch_without_numeric_launch(self):
        """Actual grants/charges/custody entry; the numerical launch is withheld."""
        import time
        import uuid
        from model_definitions import ModelDefinitions
        from runtime_snapshots import RuntimeSnapshots
        self.dataset.close()
        self.dataset=Dataset(Path(os.environ['TULDOK_BOUND_RUNTIME_CATALOG']),project_roots={'fixture':self.project})
        self.addCleanup(self.dataset.close)
        self.owner=bind_owner(self,self.dataset)
        expected=json.loads(Path(os.environ['TULDOK_BOUND_RUNTIME_DESCRIPTOR']).read_bytes())
        descriptor=RuntimeSnapshots(self.dataset.db,self.dataset.access,self.dataset.path).get(expected['manifest_sha256'],verify=True)
        self.assertEqual(descriptor,expected)
        self.models=ModelDefinitions(self.dataset);self.dataset.models=self.models
        self.recipe['runtime_snapshot_sha256']=descriptor['manifest_sha256']
        self.manifest['id']=uuid.uuid4().hex;self.write_project()
        self.dataset.projects.open_snapshot({'root':'fixture','manifest_path':'project.json'})
        inspected=self.inspect(2)
        draft=self.models.create(self.body());model=self.models.publish(draft['id'],{'revision':1})
        graph=self.dataset.pipelines.create_external({'name':'Actual bounded dispatch regression',**self.selector,
            'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':self.manifest['data'][0]['sha256']}}})
        study=self.dataset.studies.create({'name':'Actual bounded dispatch regression','policy':inspected['selection_policy'],
            'limits':{'attempt_slots':1,'admitted_wall_seconds':2400,'retained_bytes':2*1024**3,'peak_staging_bytes':4*1024**3}})
        trial=self.dataset.studies.prepare_trial(study['id'],{'request_key':'prepare-'+uuid.uuid4().hex,
            'revision':study['revision'],'graph_id':graph['id'],'graph_revision':graph['revision'],'model':model['ref'],'replicate':0})
        state=self.dataset.studies.get(study['id'])['study']
        self.dataset.studies.continue_study(study['id'],{'request_key':'continue-'+uuid.uuid4().hex,
            'revision':state['revision'],'admission_epoch':state['admission_epoch']})
        agent=self.dataset.access.issue({'label':'Actual bound regression consumer','scopes':['inspect','execute']})
        grant=self.dataset.studies.approve(study['id'],{'trial_id':trial['id'],'expected_material_sha256':trial['material']['sha256'],
            'consumer_actor_id':agent['identity']['actor_id']})
        state=self.dataset.studies.get(study['id'])['study']
        def body():
            return {'request_key':'admit-'+uuid.uuid4().hex,'revision':state['revision'],'admission_epoch':state['admission_epoch'],
                    'trial_id':trial['id'],'approval_id':grant['id']}
        def counts():
            return [self.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                    for table in ('workspace_runs','access_execution_consumptions','model_attempt_reservations')]
        baseline=counts()
        paths=[('source',self.project/self.recipe['entrypoint']),('provider',self.project/'provider.json'),
               ('input',self.project/self.manifest['data'][0]['path']),('disabled manifest',self.project/'project.json'),
               ('Model',self.models.path/model['ref']['sha256']/model['material']['specification']['name']),
               ('runtime',Path(descriptor['root'])/'manifest.json')]
        for label,path in paths:
            raw=path.read_bytes();mode=path.stat().st_mode&0o777
            try:
                path.chmod(0o600)
                changed=json.dumps(dict(json.loads(raw),extensions=[])).encode() if label=='disabled manifest' else raw+b' '
                path.write_bytes(changed)
                with self.subTest(changed=label),self.dataset.access.bind(agent['token']),self.assertRaises(WorkbenchError):
                    self.dataset.studies.admit(study['id'],body())
                self.assertEqual(counts(),baseline)
            finally:
                path.write_bytes(raw);path.chmod(mode)
        root=self.dataset.projects.roots.pop('fixture')
        try:
            with self.dataset.access.bind(agent['token']),self.assertRaises(WorkbenchError):
                self.dataset.studies.admit(study['id'],body())
            self.assertEqual(counts(),baseline)
        finally:
            self.dataset.projects.roots['fixture']=root
        self.assertTrue(all(value==0 for value in self.dataset.studies.get(study['id'])['charged'].values()))
        with self.dataset.access.bind(agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=self.dataset.studies.admit(study['id'],body())
        launched=[]
        def withheld(*args,**kwargs):
            launched.append(True)
            raise WorkbenchError('Intentional prelaunch dispatch regression.','unsupported',409)
        with patch('recipe_process.launch',side_effect=withheld):
            self.dataset.runs._start()
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                final=self.dataset.runs.get(admitted['run']['id'])
                if final['state'] not in ('queued','running'):break
                time.sleep(0.05)
        self.assertTrue(launched,'Bound host mismatch must not prevent entry to the qualified launch seam.')
        self.assertEqual(final['state'],'interrupted')
        self.assertEqual(counts(),[value+1 for value in baseline])
        retained=self.dataset.pipelines.recipe_material(trial['material'],verify=True)
        shutil.rmtree(self.project)
        self.assertEqual(self.dataset.pipelines.recipe_material(trial['material'],verify=True),retained)
        self.assertEqual(self.models.material(model['ref'],verify=True),model)

    def test_existing_recipe_cannot_gain_v2_project_reads_by_fallback(self):
        legacy=copy.deepcopy(self.recipe);legacy.update(schema_version=2,format='external_model_evidence_recipe_v1')
        del legacy['extension_selection']
        self.recipe=legacy;self.manifest['id']='f'*32;self.write_project()
        self.dataset.projects.open_snapshot({'root':'fixture','manifest_path':'project.json'})
        with self.assertRaises(WorkbenchError) as caught:self.inspect(2)
        self.assertEqual(caught.exception.code,'unsupported')
