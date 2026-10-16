"""Real frozen-source custody at owner seams; no producer Run/numerical claim."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app import Dataset
from auth_helpers import bind_owner
import extension_canonical_fixture as fixture
import extension_evidence as evidence
from model_definitions import ModelDefinitions
from pipeline import execution_digest
import recipe_contract
import test_extension_bindings as bindings_tests
from workbench import WorkbenchError

HAS_HELPER = importlib.util.find_spec('extension_canonical') is not None


class ReachedRuntime(Exception):
    """Intentional stop after real source validation; no runtime is fabricated."""


class ClosedCapturedInputTests(unittest.TestCase):
    def test_exact_private_capture_inventory_and_typed_sizes(self):
        raw=b'exact retained input';path='input/source'
        material={'inputs':{'source':{}},'captures':{path:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}}
        self.assertEqual(recipe_contract.captured_inputs(material,{path:raw}),{path:raw})
        for captures in ({}, {path:raw,'input/undeclared':b'x'}, {path:raw+b'x'}, {path:bytearray(raw)}, {1:raw}):
            with self.subTest(captures=list(captures)),self.assertRaises(WorkbenchError):
                recipe_contract.captured_inputs(material,captures)
        for invalid in ({},dict(material,captures=None),dict(material,captures={path:{'bytes':True,'sha256':hashlib.sha256(raw).hexdigest()}})):
            with self.subTest(invalid=invalid),self.assertRaises(WorkbenchError):recipe_contract.captured_inputs(invalid,{path:raw})

    def test_new_policy_requires_explicit_bound_recipe_and_dependency(self):
        recipe={'schema_version':3,'format':recipe_contract.BOUND_EVIDENCE_FORMAT,
                'model_evidence':{'format':recipe_contract.CANONICAL_POLICY_FORMAT}}
        self.assertTrue(recipe_contract.is_canonical_evidence(recipe))
        for other in (dict(recipe,schema_version=True),dict(recipe,schema_version=2),
                      dict(recipe,format=recipe_contract.EVIDENCE_FORMAT),
                      dict(recipe,model_evidence={'format':evidence.POLICY_FORMAT})):
            self.assertFalse(recipe_contract.is_canonical_evidence(other))
        if not HAS_HELPER:
            with self.assertRaises(WorkbenchError) as caught:recipe_contract.validate_canonical_captures({'recipe':recipe},{})
            self.assertEqual(caught.exception.code,'unavailable')


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and HAS_HELPER,
                     'Requires disposable PostgreSQL and the reviewed canonical helper')
class CanonicalOwnerGlueTests(unittest.TestCase):
    def setUp(self):
        self.case=bindings_tests.BoundExtensionRecipeTests('test_inspect_publish_graph_and_cold_model_use_real_bound_sources')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        case=self.case
        case.dataset.close()
        source=case.root/'canonical-source';source.mkdir()
        self.dataset=Dataset(case.root/'catalog',project_roots={'fixture':case.project,'canonical-fixture':source})
        self.addCleanup(self.dataset.close)
        self.owner=bind_owner(self,self.dataset)
        case.dataset=self.dataset;case.models=ModelDefinitions(self.dataset);self.dataset.models=case.models
        result=fixture.build_canonical_fixture(self.dataset,source)
        self.result=result
        self.recipe=case.recipe;self.policy=self.recipe['model_evidence']
        self.policy['format']=recipe_contract.CANONICAL_POLICY_FORMAT
        self.recipe['inputs']={'canonical':{'max_bytes':1048576},'derivation':{'max_bytes':65536},'provenance':{'max_bytes':65536}}
        for token in self.recipe['arguments']:
            if token.get('input')=='fixture':token['input']='canonical'
        derivation=copy.deepcopy(result['receipt']['derivation']);self.outputs={}
        for row in derivation['cases']:
            for item in row['arrays']:
                original=item['output']['name']
                selected=('input-initial.npy' if item['field_id']=='initial' else 'reference.npy') if row['split']=='validation' else original
                item['output']['name']=selected;self.outputs[selected]=result['outputs'][original]
                if original==selected:self.recipe['outputs'].append({'path':selected,'role':'field_source','required':True,'max_bytes':8192})
        self.recipe['outputs'].append({'path':'canonical-derivation.json','role':'field_derivation','required':True,'max_bytes':65536})
        release_sha,release_raw=next(iter(result['releases'].items()))
        self.derivation_raw=evidence.canonical(derivation);self.provenance_raw=evidence.canonical(result['receipt'])
        self.canonical={'format':'canonical_field_inputs_v1','release':{'input':'canonical','sha256':release_sha},
            'derivation':{'input':'derivation','sha256':evidence.digest(derivation),'output':'canonical-derivation.json'},
            'provenance':{'input':'provenance','sha256':hashlib.sha256(self.provenance_raw).hexdigest()},
            'contract':result['receipt']['contract'],
            'members':[{'case_id':row['id'],'record_id':result['records'][row['id']]['id'],
                'revision':result['records'][row['id']]['revision'],'source_revision':result['records'][row['id']]['source_revision'],
                'split':row['split']} for row in derivation['cases']],
            'mapping':{'inputs':[{'source_field_id':'initial','model_field_id':'initial'}],'target':{'source_field_id':'reference'}}}
        self.policy['canonical']=self.canonical;self.policy['probe']['data_input']='canonical'
        for ref in [*self.policy['fit_members'],*[item['frozen_reference'] for item in self.policy['probe']['candidates']]]:
            ref.update(input='canonical',sha256=release_sha)
        population=evidence.digest(sorted([item['frozen_reference'] for item in self.policy['probe']['candidates']],key=evidence.canonical))
        for metric in self.policy['metric_definitions']:metric['population_sha256']=population
        self.outputs['canonical-derivation.json']=self.derivation_raw
        for rule in self.recipe['outputs']:
            filename=rule['path']
            if filename in self.outputs and filename.endswith('.npy'):rule['role']='field_source'
            elif filename.startswith('prediction-'):rule['role']='field_prediction'
            elif filename.startswith('checkpoint-'):rule['role']='model_checkpoint'
            elif filename.startswith('weights-') or filename=='transform.npy':rule['role']='model_state'
        # Inert role-index documents only; no checkpoint, fitted state, producer
        # execution, or completed Run is fabricated. The native source bytes and
        # Release/proof above are actual and pass the real scientific validators.
        self.outputs['checkpoints.json']=evidence.canonical({'entries':[{'checkpoint':{'name':f'checkpoint-{point}.json'}} for point in (16,32,48,64)]})
        for point in (16,32,48,64):self.outputs[f'checkpoint-{point}.json']=evidence.canonical({'weights':{'name':f'weights-{point}.npy'}})
        self.outputs['fitted-transform.json']=evidence.canonical({'state':{'name':'transform.npy'}})
        case.manifest['data']=[]
        for name,raw in [('derivation',self.derivation_raw),('provenance',self.provenance_raw)]:
            path=name+'.json';(case.project/path).write_bytes(raw)
            case.manifest['data'].append({'id':name,'label':name,'path':path,'sha256':hashlib.sha256(raw).hexdigest()})
        case._rebind_definitions()
        self.policy=self.recipe['model_evidence'];self.canonical=self.policy['canonical']
        self.bindings={'canonical':{'kind':'frozen_release','release_id':release_sha,'expected_sha256':release_sha},
            'derivation':{'reference_id':'derivation','expected_sha256':self.canonical['derivation']['sha256']},
            'provenance':{'reference_id':'provenance','expected_sha256':self.canonical['provenance']['sha256']}}

    def graph(self,bindings=None):
        return self.dataset.pipelines.create_external({'name':'Canonical source glue only',**self.case.selector,
                                                       'inputs':self.bindings if bindings is None else bindings})

    def captured(self):
        inputs={};captured={}
        for name,selected in self.bindings.items():
            if name=='canonical':
                raw,receipt=self.dataset.releases.capture_input(selected['release_id'],selected['expected_sha256'],self.recipe['inputs'][name]['max_bytes'])
            else:
                raw,receipt=self.dataset.projects.read_snapshot_data_reference(self.case.manifest['id'],selected['reference_id'],
                    selected['expected_sha256'],self.recipe['inputs'][name]['max_bytes'])
            inputs[name]=receipt;captured['input/'+name]=raw
        material={'catalog_id':self.dataset.db.dataset_id,'recipe':self.recipe,'inputs':inputs,
                  'captures':{path:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for path,raw in captured.items()}}
        return material,captured

    def test_explicit_version_and_closed_canonical_declaration(self):
        self.assertTrue(recipe_contract.is_canonical_evidence(recipe_contract.decode_definition(evidence.canonical(self.recipe))))
        for change in (lambda r:r.update(schema_version=2,format=recipe_contract.EVIDENCE_FORMAT),
                       lambda r:r['model_evidence'].update(format='extension_field_policy_v1'),
                       lambda r:r['model_evidence'].pop('canonical')):
            invalid=copy.deepcopy(self.recipe);change(invalid)
            with self.subTest(change=change),self.assertRaises(WorkbenchError):recipe_contract.decode_definition(evidence.canonical(invalid))
        self.assertEqual(set(recipe_contract.recipe_host_identity(self.recipe)),set(recipe_contract.CANONICAL_EVIDENCE_HOST_NAMES))
        self.assertNotEqual(recipe_contract.recipe_host_identity(self.recipe),recipe_contract.host_identity(evidence=True,bound=True))

    def test_all_incompatible_kind_bindings_refuse_before_input_or_runtime_capture(self):
        for name,selected in [('canonical',{'kind':'frozen_release','release_id':'f'*64,'expected_sha256':'f'*64}),
                              ('derivation',{'kind':'run_artifact','run_id':'a'*32,'artifact_name':'proof','expected_sha256':'b'*64}),
                              ('provenance',{'kind':'frozen_release','release_id':'c'*64,'expected_sha256':'c'*64})]:
            bindings=copy.deepcopy(self.bindings);bindings[name]=selected;graph=self.graph(bindings)
            with self.subTest(name=name),patch.object(self.dataset.releases,'capture_input',side_effect=AssertionError('Input owner must not run')),\
                    patch.object(self.dataset.projects,'read_snapshot_data_reference',side_effect=AssertionError('Project input must not run')),\
                    patch.object(recipe_contract,'runtime_identity',side_effect=AssertionError('Runtime must not run')),self.assertRaises(WorkbenchError):
                recipe_contract.prepare(self.dataset.projects,graph,execution_digest(graph),releases=self.dataset.releases,runs=self.dataset.runs)

    def test_real_source_and_proof_validation_precedes_every_runtime_capture(self):
        graph=self.graph()
        with patch.object(recipe_contract,'runtime_identity',side_effect=ReachedRuntime),self.assertRaises(ReachedRuntime):
            recipe_contract.prepare(self.dataset.projects,graph,execution_digest(graph),releases=self.dataset.releases,runs=self.dataset.runs)
        self.assertEqual(self.dataset.runs.list(),[])
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_cold_validator_consumes_exact_retained_inputs_and_authoritative_outputs(self):
        material,captured=self.captured()
        self.assertEqual(recipe_contract.validate_canonical_captures(material,captured),captured)
        self.assertEqual(recipe_contract.validate_canonical_captures(material,captured,outputs=self.outputs),captured)
        invalid=dict(self.outputs);selected=self.canonical['derivation']['output'];invalid[selected]+=b' '
        with self.assertRaises(WorkbenchError):recipe_contract.validate_canonical_captures(material,captured,outputs=invalid)
        invalid=dict(captured);invalid['input/derivation']+=b' '
        with self.assertRaises(WorkbenchError):recipe_contract.validate_canonical_captures(material,invalid)
        invalid=dict(captured);invalid['input/undeclared']=b'not captured'
        with self.assertRaises(WorkbenchError):recipe_contract.validate_canonical_captures(material,invalid)

    def test_rehashed_wrong_record_proof_refuses_before_runtime(self):
        derivation=json.loads(self.derivation_raw);derivation['cases'][0]['record_id']='f'*32
        # This is a validly rehashed Project document and immutable binding; the
        # canonical source, rather than a stale outer hash, must refuse it.
        self.derivation_raw=evidence.canonical(derivation)
        self.canonical['derivation']['sha256']=hashlib.sha256(self.derivation_raw).hexdigest()
        (self.case.project/'derivation.json').write_bytes(self.derivation_raw)
        next(row for row in self.case.manifest['data'] if row['id']=='derivation')['sha256']=self.canonical['derivation']['sha256']
        self.case._rebind_definitions();self.bindings['derivation']['expected_sha256']=self.canonical['derivation']['sha256']
        graph=self.graph()
        with patch.object(recipe_contract,'runtime_identity',side_effect=AssertionError('Runtime must not run')),self.assertRaises(WorkbenchError):
            recipe_contract.prepare(self.dataset.projects,graph,execution_digest(graph),releases=self.dataset.releases,runs=self.dataset.runs)
