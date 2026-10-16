"""Synthetic negative witnesses for the independent B retained-artifact adapter."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

import extension_b_cold_consumer as consumer
from extension_b_cold_consumer import verify
from extension_b_numerical_oracle import OracleError, closed_form_state, reconstruct, retallied_mse, training_population
from test_extension_b_evidence_contract import PACKAGE, npy, witness
from tuldok_extension_sdk import evidence as sdk


def analytic_witness(root,mutation=None,transform_delta=0):
    """Closed-form synthetic protocol state only; no optimizer/producer/Run."""
    base=root/'base';base.mkdir();raw,_,_,expected=witness(base)
    context=sdk.decode(raw);fixture_raw=(PACKAGE/'fixture.json').read_bytes();fixture=json.loads(fixture_raw)
    if mutation:mutation(context)
    raw=sdk.canonical(context);expected['context_sha256']=hashlib.sha256(raw).hexdigest()
    output=root/'analytic';output.mkdir();writer=sdk.Evidence(output,raw);policy=context['static']['policy']
    cases={case['id']:case for case in fixture['cases']};case=cases[fixture['probe_member_id']];shape=fixture['shape_zyx']
    population=training_population([x for key in fixture['fit_member_ids'] for x in cases[key]['initial']],
        [x for key in fixture['fit_member_ids'] for x in cases[key]['source']])
    for row in policy['probe_inputs'][0]['fields']:(output/row['artifact']).write_bytes(npy(case[row['field_id']],shape))
    for semantic in ('raw','corrected'):(output/f'reference-{semantic}.npy').write_bytes(npy(case[semantic+'_target'],shape))
    (output/'transform.npy').write_bytes(npy([population.mean_initial+transform_delta,population.mean_source,
        population.std_initial,population.std_source],[2,2]));writer.transform('transform.npy')
    for point in (32,64):
        weights=closed_form_state(population,.1,point);(output/f'weights-{point}.npy').write_bytes(npy(weights,[3]))
        fields=reconstruct(case['initial'],case['source'],case['boundary_mask'],population,weights,shape=tuple(shape));metrics={}
        for semantic in ('raw','corrected'):
            values=getattr(fields,semantic);(output/f'{semantic}-{point}.npy').write_bytes(npy(values,shape))
            metrics[semantic+'_reference_mse']=retallied_mse(values,case[semantic+'_target'])
        writer.checkpoint(point,dict(optimizer_update=point,epoch=None,fit_pass=None,physical_time=None,wall_elapsed_ms=point),f'weights-{point}.npy',metrics)
    writer.finish();blobs={path.name:path.read_bytes() for path in output.iterdir()};doc=lambda name:sdk.decode(blobs[name])
    index=doc('checkpoints.json');members=context['static']['probe']['members']
    projection=dict(state='verified',manifest=doc('model-evidence.json'),probe=context['static']['probe'],metric_definitions=policy['metric_definitions'],
        metric_definition_hashes={row['id']:sdk.digest(row) for row in policy['metric_definitions']},model_definition=policy['model_specification'],
        checkpoint_index=index,checkpoints=[doc(entry['checkpoint']['name']) for entry in index['entries']],observations=doc('observations.json'),
        fields=[dict(checkpoint_sha256=entry['checkpoint']['sha256'],member_ordinal=member['ordinal'],field_id=field['id'],
            stage=field['contract']['output']['stage'],shape_zyx=shape,units=field['contract']['output']['units'])
            for entry in index['entries'] for field in policy['fields'] for member in members])
    return raw,projection,blobs,expected,fixture_raw


class BColdConsumerNegatives(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)

    def test_zero_state_structural_witness_is_not_a_passing_numerical_run(self):
        raw,projection,blobs,expected=witness(self.root)
        fixture=(PACKAGE/'fixture.json').read_bytes()
        with self.assertRaisesRegex(OracleError,'train-only normalization'):
            verify(raw,projection,blobs,fixture,expected=expected,fixture_sha256=hashlib.sha256(fixture).hexdigest())

    def test_fixture_hash_is_operator_frozen_before_inspecting_candidate_values(self):
        raw,projection,blobs,expected=witness(self.root)
        fixture=(PACKAGE/'fixture.json').read_bytes()
        with self.assertRaisesRegex(OracleError,'source fixture identity'):
            verify(raw,projection,blobs,fixture+b' ',expected=expected,fixture_sha256=hashlib.sha256(fixture).hexdigest())

    def test_synthetic_closed_form_state_reaches_full_adapter_without_training(self):
        raw,projection,blobs,expected,fixture=analytic_witness(self.root)
        result=verify(raw,projection,blobs,fixture,expected=expected,fixture_sha256=hashlib.sha256(fixture).hexdigest())
        self.assertEqual(result['state'],'passed');self.assertEqual(len(result['diagnostics']),4)
        self.assertEqual(result['physical'],'not_evaluated');self.assertEqual(result['quality'],'diagnostic_only')

    def test_coherently_rebuilt_geometry_gauge_and_probe_source_drift_refuse(self):
        mutations=[lambda context:[field['geometry'].update(origin_xyz=[17,0,0]) for field in context['static']['policy']['fields']],
            lambda context:context['static']['probe'].update(data_sha256='f'*64)]
        for index,mutation in enumerate(mutations):
            root=self.root/str(index);root.mkdir();raw,projection,blobs,expected,fixture=analytic_witness(root,mutation)
            with self.subTest(index=index),self.assertRaisesRegex(OracleError,'frozen source|probe source'):
                verify(raw,projection,blobs,fixture,expected=expected,fixture_sha256=hashlib.sha256(fixture).hexdigest())

    def test_replay_uses_retained_transform_after_separate_train_fit_check(self):
        raw,projection,blobs,expected,fixture=analytic_witness(self.root,transform_delta=5e-11)
        result=verify(raw,projection,blobs,fixture,expected=expected,fixture_sha256=hashlib.sha256(fixture).hexdigest())
        self.assertGreater(result['normalization_max_error'],1e-11)
        self.assertGreater(max(row['max_replay_error'] for row in result['diagnostics']),1e-12)

    def test_cli_count_and_byte_bounds_apply_before_excess_reads(self):
        artifacts=self.root/'artifacts';artifacts.mkdir();report=self.root/'report.json'
        for index in range(65):(artifacts/str(index)).write_bytes(b'x')
        with patch.object(consumer,'read_regular',wraps=consumer.read_regular) as read:
            with self.assertRaisesRegex(OracleError,'count/aggregate'):consumer.read_artifacts(artifacts,report)
            self.assertEqual(read.call_count,64)
        for path in artifacts.iterdir():path.unlink()
        for index in range(3):
            with (artifacts/str(index)).open('wb') as output:output.truncate(6*1024**2)
        with patch.object(consumer,'read_regular',wraps=consumer.read_regular) as read:
            with self.assertRaisesRegex(OracleError,'bounded regular'):consumer.read_artifacts(artifacts,report)
            self.assertEqual(read.call_args.args[1],4*1024**2)

    def test_cli_preserves_downloaded_directory_and_refuses_symlink_inputs(self):
        artifacts=self.root/'artifacts';artifacts.mkdir();(artifacts/'native.npy').write_bytes(b'preserve')
        for report in (artifacts/'report.json',artifacts/'nested/report.json'):
            with self.assertRaisesRegex(OracleError,'outside downloaded'):consumer.read_artifacts(artifacts,report)
        (artifacts/'alias.npy').symlink_to(artifacts/'native.npy')
        with self.assertRaises(OSError):consumer.read_artifacts(artifacts,self.root/'report.json')
        self.assertEqual((artifacts/'native.npy').read_bytes(),b'preserve')

    def test_cli_starts_directly_without_inherited_pythonpath_or_app_import(self):
        environment={key:value for key,value in os.environ.items() if key!='PYTHONPATH'}
        completed=subprocess.run([sys.executable,'-I',str(Path(consumer.__file__).resolve()),'--help'],
            cwd=self.root,env=environment,capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)
        code="import sys;sys.path[:0]=sys.argv[1:];import extension_b_cold_consumer;assert not any(name in sys.modules for name in ('app','projects','psycopg','numpy','torch'))"
        completed=subprocess.run([sys.executable,'-I','-c',code,str(Path(consumer.__file__).parent),str(Path(consumer.__file__).parents[1])],
            cwd=self.root,env=environment,capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)


if __name__=='__main__':unittest.main()
