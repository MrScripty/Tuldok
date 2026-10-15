"""Actual B owner refusals with freshly rehashed private declarations.

No author source is executed or edited. These tests check declared compatibility
and exact bindings, not the numerical meaning of opaque authored fixture JSON.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from app import Dataset
from auth_helpers import bind_owner
import extension_evidence as evidence
from model_definitions import ModelDefinitions
import recipe_contract
from workbench import WorkbenchError

PACKAGE=Path(__file__).resolve().parents[1]/'examples/extensions/field-surrogate-b-independent/v1'
AUTHOR_COMMIT='db5ce54'
# Exact corrected B source, before any private negative declaration changes.
RECIPE_SHA='7d089b3fe85191e5dbb3c222899e8b9629f4889708a10b854c533b73b0796416'
TABLES=('access_execution_grants','workspace_runs','access_execution_consumptions','model_attempt_reservations')


class ReachedRuntime(Exception):
    """Stop before runtime capture; source custody has used actual owner reads."""


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the extension validator')
class IndependentBRefusalTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.project=self.root/'project'
        shutil.copytree(PACKAGE,self.project)
        self.assertEqual(hashlib.sha256((self.project/'recipe.json').read_bytes()).hexdigest(),RECIPE_SHA)
        self.original={str(path.relative_to(self.project)):path.read_bytes() for path in self.project.rglob('*') if path.is_file()}
        self.dataset=Dataset(self.root/'catalog',project_roots={'b':self.project})
        self.addCleanup(self.dataset.close);self.owner=bind_owner(self,self.dataset)
        self.models=ModelDefinitions(self.dataset);self.dataset.models=self.models
        self.reset()
        self.assertEqual(self.counts(),dict.fromkeys(TABLES,0))

    def counts(self):
        return {table:self.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in TABLES}

    def reset(self):
        for name,raw in self.original.items():(self.project/name).write_bytes(raw)
        self.recipe=json.loads(self.original['recipe.json']);self.policy=self.recipe['model_evidence']
        self.provider=json.loads(self.original['extension.json']);self.manifest=json.loads(self.original['project.json'])
        self.definitions={row['kind']:json.loads(self.original[row['path']]) for row in self.provider['contributions']}

    def open(self):
        self.dataset.projects.open_snapshot({'root':'b','manifest_path':'project.json'})
        self.selector={'project_id':self.manifest['id'],'recipe_id':self.manifest['recipes'][0]['id'],
                       'expected_sha256':self.manifest['recipes'][0]['sha256']}

    def recapture(self):
        """Fresh exact Project/provider/recipe refs, including dependency closure."""
        references={}
        for row in self.provider['contributions']:
            definition=self.definitions[row['kind']]
            for requirement in definition['requires']:
                if requirement['id'] in references:requirement.update(references[requirement['id']])
            raw=evidence.canonical(definition);(self.project/row['path']).write_bytes(raw)
            row.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            references[row['id']]={key:row[key] for key in ('id','version','sha256')}
        for row in self.provider['sources']+self.provider['license']['notices']:
            raw=(self.project/row['path']).read_bytes();row.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        provider_raw=evidence.canonical(self.provider);(self.project/'extension.json').write_bytes(provider_raw)
        self.recipe['extension_selection']['selections']={row['kind']:{key:row[key] for key in ('id','version','sha256')}
                                                         for row in self.provider['contributions']}
        self.policy['task']['definition']=copy.deepcopy(self.definitions['task'])
        for row in self.recipe['sources']:row['sha256']=hashlib.sha256((self.project/row['path']).read_bytes()).hexdigest()
        adapter=evidence.digest(sorted(self.recipe['sources'],key=lambda row:row['path']))
        self.policy['adapter_sha256']=adapter
        for field in self.policy['fields']:field['contract']['source_sha256']=adapter
        for metric in self.policy['metric_definitions']:metric['evaluator_sha256']=adapter
        # Rehash the target aggregate even for malformed ordered role rows, so
        # the negative cannot be explained by a stale aggregate digest alone.
        for member in self.policy['probe']['candidates']:
            member['target_sha256']=evidence.digest([{key:row[key] for key in ('field_id','payload_sha256')}
                for row in self.policy['field_targets'] if row['member_id']==member['frozen_reference']['member_id']])
        raw=evidence.canonical(self.recipe);(self.project/'recipe.json').write_bytes(raw)
        self.manifest['id']=uuid.uuid4().hex
        self.manifest['recipes'][0]['sha256']=hashlib.sha256(raw).hexdigest()
        self.manifest['extensions'][0]['sha256']=hashlib.sha256(provider_raw).hexdigest()
        (self.project/'project.json').write_bytes(evidence.canonical(self.manifest))
        self.open()

    def inspect(self):
        return self.dataset.pipelines.inspect_external_recipe(self.selector['project_id'],self.selector['recipe_id'],
            self.selector['expected_sha256'],contract_version=2)

    def body(self):
        return {'name':'Independent B refusal gate','kind':'captured_source',
            'task':{'kind':'task','catalog_id':self.dataset.db.dataset_id,'id':self.policy['task']['id'],
                    'revision':self.policy['task']['revision'],'sha256':evidence.digest(self.policy['task']['definition'])},
            'specification':self.policy['model_specification'],'preprocessing_policy':self.policy['preprocessing_policy'],
            'output_policy':self.policy['output_policy'],'source_selector':self.selector}

    def refuse(self,mutate,reason):
        self.reset();mutate();self.recapture();before=self.counts()
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Semantic refusal must be inert')),\
                patch.object(recipe_contract,'runtime_identity',side_effect=AssertionError('No runtime capture')),\
                self.assertRaisesRegex(WorkbenchError,reason):self.inspect()
        self.assertEqual(self.counts(),before)

    def test_corrected_b_exact_source_inspects_publishes_and_reaches_pre_runtime_barrier(self):
        self.open();before=self.counts()
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Owner preparation must be inert')):
            inspected=self.inspect();draft=self.models.create(self.body());model=self.models.publish(draft['id'],{'revision':1})
            self.assertEqual(inspected['model_task'],model['material']['task'])
            graph=self.dataset.pipelines.create_external({'name':'B bounded preflight',**self.selector,
                'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':self.manifest['data'][0]['sha256']}}})
            with patch.object(recipe_contract,'runtime_identity',side_effect=ReachedRuntime),self.assertRaises(ReachedRuntime):
                self.dataset.pipelines.preflight_external(graph['id'],graph['revision'])
        self.assertEqual(self.counts(),before)
        self.assertNotEqual(self.policy['field_targets'][0]['payload_sha256'],self.policy['field_targets'][1]['payload_sha256'])

    def test_required_source_mask_coverage_and_typed_port_mismatches_refuse(self):
        for field_id in ('source','boundary_mask'):
            def missing():
                for field in self.policy['fields']:
                    field['contract']['inputs']=[row for row in field['contract']['inputs'] if row['field_id']!=field_id]
                for row in self.policy['probe_inputs']:row['fields']=[item for item in row['fields'] if item['field_id']!=field_id]
            with self.subTest(missing=field_id):self.refuse(missing,'Every declared Task input')
        def wrong_source():
            for port in self.definitions['model']['ports']:
                if port['id']=='source':port['units']='m'
        self.refuse(wrong_source,'Contribution ports are incompatible')
        def missing_mask():
            self.definitions['model']['ports']=[row for row in self.definitions['model']['ports'] if row['id']!='boundary_mask']
        self.refuse(missing_mask,'Contribution ports are incompatible')

    def test_stage_gauge_and_time_mismatches_refuse_fresh_project_definitions(self):
        self.refuse(lambda:self.policy['fields'][1]['contract']['output'].update(stage='raw_inference'),
                    'declared producer stage')
        def wrong_dataflow():
            for role in ('task','trainer'):self.definitions[role]['stages'][1]['inputs'][0]='unproduced_raw'
        self.refuse(wrong_dataflow,'Stage dataflow or clock')
        self.refuse(lambda:self.policy['fields'][1]['contract']['output'].update(gauge_policy_sha256='f'*64),
                    'Explicit gauge identity differs')
        self.refuse(lambda:self.policy['fields'][1]['contract'].update(time_mode='trajectory'),
                    'temporal')

    def test_raw_corrected_target_roles_cannot_swap_or_conflate_ordered_mapping(self):
        self.refuse(lambda:self.policy['field_targets'].reverse(),'Field target order/membership')
        def conflate_role():self.policy['field_targets'][1]['field_id']='raw'
        self.refuse(conflate_role,'Field target order/membership')

    def test_model_and_preflight_bindings_refuse_before_any_execution_effect(self):
        self.open();self.inspect();before=self.counts()
        body=copy.deepcopy(self.body());body['specification']['input_fields'].remove('boundary_mask')
        draft=self.models.create(body)
        with self.assertRaisesRegex(WorkbenchError,'Model architecture differs'):
            self.models.publish(draft['id'],{'revision':1})
        for inputs in ({},{'fixture':{'kind':'run_artifact','run_id':'a'*32,'artifact_name':'input.npy','expected_sha256':'b'*64}}):
            graph=self.dataset.pipelines.create_external({'name':'B invalid binding',**self.selector,'inputs':inputs})
            with self.subTest(inputs=inputs),patch.object(self.dataset.projects,'read_snapshot_data_reference',side_effect=AssertionError('No input capture')),\
                    patch.object(recipe_contract,'runtime_identity',side_effect=AssertionError('No runtime capture')),self.assertRaises(WorkbenchError):
                self.dataset.pipelines.preflight_external(graph['id'],graph['revision'])
            self.assertEqual(self.counts(),before)
