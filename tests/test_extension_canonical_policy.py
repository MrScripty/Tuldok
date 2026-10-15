"""Real canonical source custody for the explicit future policy; no Run claim."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from app import Dataset
from auth_helpers import bind_owner
import extension_canonical as canonical
import extension_canonical_fixture as fixture
import extension_evidence as evidence
from workbench import WorkbenchError

PACKAGE = Path(__file__).resolve().parents[1] / 'examples/extensions/field-surrogate/v2'


class CanonicalPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); project = self.root/'source'; project.mkdir()
        self.dataset = Dataset(self.root/'catalog', project_roots={'canonical-fixture': project})
        self.addCleanup(self.dataset.close); self.owner = bind_owner(self, self.dataset)
        result = fixture.build_canonical_fixture(self.dataset, project)
        self.definition = json.loads((PACKAGE/'recipe.json').read_bytes())
        self.definition.update(schema_version=3,format='external_model_evidence_recipe_v2')
        self.policy = self.definition['model_evidence']; self.policy['format'] = canonical.POLICY_FORMAT
        member=self.policy['probe']['candidates'][0]
        self.policy['field_targets']=[dict(member_id=member['frozen_reference']['member_id'],field_id=self.policy['fields'][0]['id'],payload_sha256=member['target_sha256'])]
        member['target_sha256']=evidence.digest([{key:row[key] for key in ('field_id','payload_sha256')} for row in self.policy['field_targets']])
        del self.definition['inputs']['fixture']
        self.definition['inputs'].update(canonical={'max_bytes':1048576}, derivation={'max_bytes':65536}, provenance={'max_bytes':65536})
        derivation = copy.deepcopy(result['receipt']['derivation']); self.outputs = {}
        for case in derivation['cases']:
            for row in case['arrays']:
                old = row['output']['name']
                name = ('input-initial.npy' if row['field_id']=='initial' else 'reference.npy') if case['split']=='validation' else old
                row['output']['name'] = name; self.outputs[name] = result['outputs'][old]
                if name == old:self.definition['outputs'].append(dict(path=name, role='field_source', required=True, max_bytes=8192))
        self.definition['outputs'].append(dict(path='canonical-derivation.json', role='field_derivation', required=True, max_bytes=65536))
        release_sha, raw = next(iter(result['releases'].items()))
        self.derivation_raw = evidence.canonical(derivation); provenance_raw = evidence.canonical(result['receipt'])
        self.value = dict(format=canonical.FORMAT, release=dict(input='canonical',sha256=release_sha),
            derivation=dict(input='derivation',sha256=hashlib.sha256(self.derivation_raw).hexdigest(),output='canonical-derivation.json'),
            provenance=dict(input='provenance',sha256=hashlib.sha256(provenance_raw).hexdigest()), contract=result['receipt']['contract'],
            members=[dict(case_id=case['id'],record_id=result['records'][case['id']]['id'],
                revision=result['records'][case['id']]['revision'],source_revision=result['records'][case['id']]['source_revision'],split=case['split'])
                for case in derivation['cases']], mapping=dict(inputs=[dict(source_field_id='initial',model_field_id='initial')],target=dict(source_field_id='reference')))
        self.policy['canonical'] = self.value; self.policy['probe']['data_input'] = 'canonical'
        for ref in [*self.policy['fit_members'],*[row['frozen_reference'] for row in self.policy['probe']['candidates']]]:
            ref['input']='canonical'; ref['sha256']=release_sha
        self.material = dict(catalog_id=self.dataset.db.dataset_id,inputs=dict(
            canonical=dict(kind='frozen_release',catalog_id=self.dataset.db.dataset_id,release_id=release_sha,measured_sha256=release_sha,bytes=len(raw)),
            derivation=dict(measured_sha256=self.value['derivation']['sha256']),provenance=dict(measured_sha256=self.value['provenance']['sha256'])))
        self.captured = {'input/canonical':raw,'input/derivation':self.derivation_raw,'input/provenance':provenance_raw}
        self.outputs['canonical-derivation.json'] = self.derivation_raw
        for rule in self.definition['outputs']:
            filename=rule['path']
            if filename in self.outputs and filename.endswith('.npy'):rule['role']='field_source'
            elif filename.startswith('prediction-'):rule['role']='field_prediction'
            elif filename.startswith('checkpoint-'):rule['role']='model_checkpoint'
            elif filename.startswith('weights-') or filename=='transform.npy':rule['role']='model_state'
        # Clearly synthetic descriptor-role witnesses; source arrays/Release above are actual.
        self.outputs['checkpoints.json']=evidence.canonical(dict(entries=[dict(checkpoint=dict(name=f'checkpoint-{point}.json')) for point in (16,32,48,64)]))
        for point in (16,32,48,64):self.outputs[f'checkpoint-{point}.json']=evidence.canonical(dict(weights=dict(name=f'weights-{point}.npy')))
        self.outputs['fitted-transform.json']=evidence.canonical(dict(state=dict(name='transform.npy')))

    def verify(self, outputs=None):
        return canonical.validate_captured(self.value,self.policy,self.definition,self.material,self.captured,outputs=outputs)

    def test_actual_frozen_release_and_complete_native_outputs_verify_before_and_after_custody(self):
        before = self.verify(); self.assertEqual(self.verify(self.outputs),before)
        self.assertEqual(before['members'],self.value['members'])
        self.assertEqual(len(self.definition['outputs']),32)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

    def test_explicit_version_and_all_unsupported_bindings_refuse_before_capture(self):
        bindings=dict(canonical=dict(kind='frozen_release',release_id=self.value['release']['sha256'],expected_sha256=self.value['release']['sha256']),
            derivation=dict(reference_id='proof',expected_sha256=self.value['derivation']['sha256']))
        self.assertEqual(canonical.validate_bindings(self.value,bindings),bindings)
        for kind in ('run_artifact','frozen_release','unknown'):
            with self.subTest(kind=kind),self.assertRaises(WorkbenchError):
                canonical.validate_bindings(self.value,dict(bindings,unused=dict(kind=kind)))
        self.policy['format']='extension_field_policy_v1'
        with self.assertRaises(WorkbenchError):self.verify()

    def test_record_revisions_splits_member_order_and_fit_population_are_exact(self):
        original=copy.deepcopy(self.value)
        for key,value in [('revision',True),('revision',1.0),('revision',99),('source_revision',99),('record_id','f'*32),('split','test')]:
            self.value['members'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(WorkbenchError):self.verify()
            self.value.clear();self.value.update(copy.deepcopy(original))
        self.value['members'].reverse()
        with self.assertRaises(WorkbenchError):self.verify()

    def test_changed_native_output_or_exact_derivation_refuses_even_with_same_size(self):
        outputs=dict(self.outputs); name='train-0-initial.npy'; outputs[name]=outputs[name][:-1]+bytes([outputs[name][-1]^1])
        with self.assertRaises(WorkbenchError):self.verify(outputs)
        outputs=dict(self.outputs);outputs['canonical-derivation.json']=self.derivation_raw+b' '
        with self.assertRaises(WorkbenchError):self.verify(outputs)
        self.captured['input/canonical']+=b' '
        with self.assertRaises(WorkbenchError):self.verify()

    def test_probe_native_semantics_and_bindings_cannot_drift(self):
        for mutate in (lambda:self.policy['probe_inputs'][0]['fields'][0].update(artifact='other.npy'),
                       lambda:self.policy['fields'][0]['contract']['inputs'][0].update(units='other'),
                       lambda:self.policy['fields'][0]['geometry'].update(origin_xyz=[1,0,0])):
            policy=copy.deepcopy(self.policy);mutate()
            with self.assertRaises(WorkbenchError):self.verify()
            self.policy.clear();self.policy.update(policy);self.value=self.policy['canonical']

    def test_unused_input_kind_and_missing_canonical_proof_fail_closed(self):
        self.material['inputs']['unused']=dict(kind='run_artifact')
        with self.assertRaises(WorkbenchError):self.verify()
        del self.material['inputs']['unused'];del self.captured['input/provenance']
        with self.assertRaises(WorkbenchError):self.verify()

    def test_malformed_containers_geometry_aliases_and_known_byte_bounds_fail_typed(self):
        original_policy=copy.deepcopy(self.policy)
        self.policy['fields']=[]
        with self.assertRaises(WorkbenchError):self.verify()
        self.policy.clear();self.policy.update(original_policy);self.value=self.policy['canonical']
        with self.assertRaises(WorkbenchError):
            canonical.validate_captured(self.value,self.policy,self.definition,self.material,[])
        with self.assertRaises(WorkbenchError):
            canonical.validate_captured(self.value,self.policy,self.definition,dict(self.material,inputs=[]),self.captured)
        self.policy['fields'][0]['geometry']['orientation'][0][0]=True
        with self.assertRaises(WorkbenchError):self.verify()
        self.policy['fields'][0]['geometry']['orientation'][0][0]=1
        rule=next(row for row in self.definition['outputs'] if row['path']=='canonical-derivation.json')
        rule['max_bytes']=1
        for outputs in (None,self.outputs):
            with self.subTest(outputs=outputs is not None),self.assertRaises(WorkbenchError):self.verify(outputs)

    def test_derivation_native_output_collision_and_impossible_total_refuse_before_runtime(self):
        selected=self.value['derivation']['output']
        for filename in ('reference.npy','model-evidence.json','prediction-16.npy','input-initial.npy','checkpoint-16.json','weights-16.npy'):
            self.value['derivation']['output']=filename
            with self.subTest(filename=filename),self.assertRaises(WorkbenchError):self.verify()
        self.value['derivation']['output']=selected
        self.policy['profile']['limits']['total_output_bytes']=1
        with self.assertRaises(WorkbenchError):self.verify()

    def test_rehashed_train_and_validation_source_cannot_be_relabelled_as_prediction(self):
        for case_id in ('train-0','validation-0'):
            definition=copy.deepcopy(self.definition);policy=copy.deepcopy(self.policy);value=policy['canonical']
            material=copy.deepcopy(self.material);captured=dict(self.captured);outputs=dict(self.outputs)
            derivation=evidence.decode(captured['input/derivation'])
            case=next(case for case in derivation['cases'] if case['id']==case_id)
            row=next(row for row in case['arrays'] if row['field_id']=='reference');old=row['output']['name']
            row['output']['name']='prediction-16.npy';outputs['prediction-16.npy']=outputs[old]
            if case_id=='validation-0':
                for binding in policy['field_outputs']:binding['reference']='prediction-16.npy'
            raw=evidence.canonical(derivation);captured['input/derivation']=raw;outputs['canonical-derivation.json']=raw
            value['derivation']['sha256']=hashlib.sha256(raw).hexdigest();material['inputs']['derivation']['measured_sha256']=value['derivation']['sha256']
            for supplied in (None,outputs):
                with self.subTest(case_id=case_id,post=supplied is not None),self.assertRaises(WorkbenchError):
                    canonical.validate_captured(value,policy,definition,material,captured,outputs=supplied)

    def test_native_source_cannot_serve_checkpoint_weights_transform_or_common_evidence(self):
        for source_name in ('train-0-reference.npy','reference.npy'):
            for target,document in [('checkpoint-16.json',dict(weights=dict(name=source_name))),
                                    ('fitted-transform.json',dict(state=dict(name=source_name)))]:
                outputs=dict(self.outputs);outputs[target]=evidence.canonical(document)
                with self.subTest(source=source_name,target=target),self.assertRaises(WorkbenchError):self.verify(outputs)

    def test_schema3_target_map_is_explicit_ordered_complete_and_matches_actual_source(self):
        original=copy.deepcopy(self.policy)
        for mutate in (lambda:self.policy.pop('field_targets'),lambda:self.policy.update(field_targets=[]),
                       lambda:self.policy['field_targets'].append(copy.deepcopy(self.policy['field_targets'][0])),
                       lambda:self.policy['field_targets'][0].update(field_id='unknown'),
                       lambda:self.policy['field_targets'][0].update(payload_sha256='f'*64),
                       lambda:self.policy['probe']['candidates'][0].update(target_sha256=original['field_targets'][0]['payload_sha256'])):
            mutate()
            with self.assertRaises(WorkbenchError):self.verify()
            self.policy.clear();self.policy.update(copy.deepcopy(original));self.value=self.policy['canonical']
        self.policy['field_targets'][0]['payload_sha256']='f'*64
        self.policy['probe']['candidates'][0]['target_sha256']=evidence.digest([dict(field_id=row['field_id'],payload_sha256=row['payload_sha256']) for row in self.policy['field_targets']])
        with self.assertRaises(WorkbenchError):self.verify()
        self.policy.clear();self.policy.update(copy.deepcopy(original));self.value=self.policy['canonical']
        self.definition['schema_version']=3.0
        with self.assertRaises(WorkbenchError):self.verify()
        self.definition.update(schema_version=2,format='external_model_evidence_recipe_v1')
        with self.assertRaises(WorkbenchError):self.verify()
