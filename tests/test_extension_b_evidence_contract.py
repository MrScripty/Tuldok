"""Synthetic protocol witnesses only; no producer, optimizer, host or real Run."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tuldok_extension_sdk import evidence as sdk
from extension_b_evidence_contract import BContractError, validate
from extension_b_numerical_oracle import decode_npy

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'examples/extensions/field-surrogate-b-independent/v1'
ROLES=dict(inputs=dict(initial='initial',source='source',mask='boundary_mask'),
           fields=dict(raw='raw',corrected='corrected'),
           producer_stages=dict(raw='raw_inference',corrected='boundary_enforcement'))


def npy(values,shape):
    header=repr(dict(descr='<f8',fortran_order=False,shape=tuple(shape)))
    raw=header.encode();raw+=b' '*((-10-len(raw)-1)%16)+b'\n'
    return b'\x93NUMPY\x01\x00'+struct.pack('<H',len(raw))+raw+struct.pack('<'+'d'*len(values),*values)


def witness(root,mutate_policy=None,mutate_arrays=None):
    """Write structurally complete zero-state evidence, never numerical success."""
    recipe=json.loads((PACKAGE/'recipe.json').read_bytes());policy=copy.deepcopy(recipe['model_evidence'])
    fixture=json.loads((PACKAGE/'fixture.json').read_bytes());case=fixture['cases'][-1];shape=fixture['shape_zyx']
    arrays={row['artifact']:npy(case[row['field_id']],shape) for row in policy['probe_inputs'][0]['fields']}
    arrays.update({'reference-raw.npy':npy(case['raw_target'],shape),'reference-corrected.npy':npy(case['corrected_target'],shape)})
    if mutate_arrays:mutate_arrays(arrays)
    if mutate_policy:mutate_policy(policy)
    catalog_id='1'*32;model=dict(kind='model',catalog_id=catalog_id,id='2'*32,revision=1,sha256='3'*64)
    task=dict(kind='task',catalog_id=catalog_id,id=policy['task']['id'],revision=policy['task']['revision'],sha256=sdk.digest(policy['task']['definition']))
    profile=copy.deepcopy(policy['profile']);profile.pop('id');profile.pop('revision')
    profile.update(format='resolved_profile_v1',definition=dict(kind='profile',catalog_id=catalog_id,id=policy['profile']['id'],
        revision=policy['profile']['revision'],sha256=sdk.digest(policy['profile'])),task_sha256=task['sha256'],model_sha256=model['sha256'],trainer_sha256='4'*64)
    members=[dict(row,ordinal=i) for i,row in enumerate(policy['probe']['candidates'])]
    probe=dict(format='probe_v1',task_sha256=task['sha256'],data_sha256=hashlib.sha256((PACKAGE/'fixture.json').read_bytes()).hexdigest(),
        split='validation',selection_policy_sha256='6'*64,members=members)
    context=dict(format=sdk.CONTEXT_FORMAT,static=dict(format='extension_evidence_static_v1',catalog_id=catalog_id,model=model,task=task,
        profile=profile,probe=probe,policy=policy,inputs=dict(fixture=dict(measured_sha256=hashlib.sha256((PACKAGE/'fixture.json').read_bytes()).hexdigest())),
        parameters=dict(learning_rate=.1,updates=64),execution_material_sha256='7'*64),
        composition=dict(kind='recipe_material',catalog_id=catalog_id,id='8'*64,sha256='8'*64),run_id='9'*32,request_sha256='a'*64)
    context_raw=sdk.canonical(context);writer=sdk.Evidence(root,context_raw)
    for name,raw in arrays.items():(root/name).write_bytes(raw)
    (root/'transform.npy').write_bytes(npy([0,0,1,1],[2,2]));writer.transform('transform.npy')
    for point in (32,64):
        (root/f'weights-{point}.npy').write_bytes(npy([0,0,0],[3]))
        metrics={}
        for semantic in ('raw','corrected'):
            values=[0.0]*64;(root/f'{semantic}-{point}.npy').write_bytes(npy(values,shape))
            target=case[semantic+'_target']
            metrics[semantic+'_reference_mse']=sum(value*value for value in target)/len(target)
        writer.checkpoint(point,dict(optimizer_update=point,epoch=None,fit_pass=None,physical_time=None,wall_elapsed_ms=point),f'weights-{point}.npy',metrics)
    writer.finish();blobs={path.name:path.read_bytes() for path in root.iterdir()}
    def doc(name):return sdk.decode(blobs[name])
    manifest=doc('model-evidence.json');index=doc('checkpoints.json')
    projected=[dict(checkpoint_sha256=entry['checkpoint']['sha256'],member_ordinal=member['ordinal'],field_id=field['id'],
        stage=field['contract']['output']['stage'],shape_zyx=shape,units=field['contract']['output']['units'])
        for entry in index['entries'] for field in policy['fields'] for member in members]
    projection=dict(state='verified',manifest=manifest,probe=probe,metric_definitions=policy['metric_definitions'],
        metric_definition_hashes={row['id']:sdk.digest(row) for row in policy['metric_definitions']},model_definition=policy['model_specification'],
        checkpoint_index=index,checkpoints=[doc(entry['checkpoint']['name']) for entry in index['entries']],observations=doc('observations.json'),fields=projected)
    expected=dict(catalog_id=catalog_id,run_id=context['run_id'],model_sha256=model['sha256'],task_sha256=task['sha256'],
        material_sha256=context['composition']['sha256'],context_sha256=hashlib.sha256(context_raw).hexdigest())
    return context_raw,projection,blobs,expected


class IndependentBContractWitnesses(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)

    def check(self,values):
        raw,projection,blobs,expected=values
        return validate(raw,projection,blobs,expected=expected,roles=ROLES)

    def test_complete_zero_state_proves_structure_only(self):
        result=self.check(witness(self.root))
        self.assertEqual(result['state'],'passed');self.assertEqual(result['field_count'],4)
        self.assertEqual(result['numerical'],'not_evaluated');self.assertEqual(result['physical'],'not_evaluated')

    def test_independently_selected_context_and_identity_refuse_changed_bytes(self):
        raw,projection,blobs,expected=witness(self.root)
        for key in expected:
            wrong=dict(expected);wrong[key]=('f'*32 if key.endswith('_id') else 'f'*64)
            with self.subTest(key=key),self.assertRaises(BContractError):
                validate(raw,projection,blobs,expected=wrong,roles=ROLES)

    def test_missing_required_source_mask_and_reordered_targets_refuse_coherent_context(self):
        def missing(policy):
            for field in policy['fields']:field['contract']['inputs']=field['contract']['inputs'][:2]
        mutations=[missing,lambda policy:policy['field_targets'].reverse(),lambda policy:policy.update(field_targets=[]),
            lambda policy:policy['fields'][1]['contract']['output'].update(stage='raw_inference')]
        for index,mutation in enumerate(mutations):
            root=self.root/str(index);root.mkdir()
            with self.subTest(index=index),self.assertRaises(BContractError):self.check(witness(root,mutate_policy=mutation))

    def test_whole_hash_repaired_swapped_reference_stages_still_refuse_admitted_targets(self):
        def swap(arrays):
            arrays['reference-raw.npy'],arrays['reference-corrected.npy']=arrays['reference-corrected.npy'],arrays['reference-raw.npy']
        values=witness(self.root,mutate_arrays=swap)
        self.assertEqual(sdk.validate_projection(values[1],values[0],values[2])['state'],'passed')
        with self.assertRaisesRegex(BContractError,'own admitted target'):self.check(values)

    def test_changed_required_input_and_nonbinary_mask_refuse_even_with_repaired_blobs(self):
        mutations=[lambda arrays:arrays.update({'input-source.npy':npy([42.0]*64,[4,4,4])}),
            lambda arrays:arrays.update({'input-boundary_mask.npy':npy([.5]*64,[4,4,4])})]
        for index,mutation in enumerate(mutations):
            root=self.root/str(index);root.mkdir();values=witness(root,mutate_arrays=mutation)
            with self.subTest(index=index),self.assertRaises(BContractError):self.check(values)

    def test_malformed_shapes_and_current_public_field_projection_refuse(self):
        raw,projection,blobs,expected=witness(self.root)
        projection['fields'][1]['stage']='raw_inference'
        with self.assertRaisesRegex(BContractError,'public field projection'):
            validate(raw,projection,blobs,expected=expected,roles=ROLES)
        for malformed in ([],None,{'inputs':None}):
            with self.subTest(malformed=malformed),self.assertRaises(BContractError):
                validate(raw,projection,blobs,expected=expected,roles=malformed)


if __name__=='__main__':unittest.main()
