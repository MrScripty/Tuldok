"""Authored boundary fixtures only; no autonomous model qualification."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from adapters.rheon import evaluate as ev, evaluation_project as project, generate, cpu_compare, native_transport

NUMPY = importlib.util.find_spec('numpy') is not None


def inputs():
    data={'checkpoint':b'authored-checkpoint','build_receipt':b'authored-build'}
    source={'source_sha256':cpu_compare.SOURCES,'binary_sha256':cpu_compare.BINARY_SHA256,
            'runtime_snapshot_sha256':'a'*64,'device':'cpu','threads':8,'build_receipt_sha256':generate.sha(data['build_receipt'])}
    receipt={'shape':[96,32768],'dtype':'<f8','trajectory_order':list(range(100,112)),
             'frame_order':list(range(1,9)),'releases':[{'sha256':str(i)} for i in range(6)]}
    data['training_inputs']=generate.encode(receipt)
    freeze={'schema':'rheon-trajectory-freeze-v1','n':32,'device':'cpu','test_frames':120,'test_seeds':list(ev.SEEDS),
            'benchmark_repetitions':5,'methods':list(ev.METHODS),'training_frames':8,'validation_frames':60,
            'checkpoint_sha256':generate.sha(data['checkpoint']),'training_data_sha256':'b'*64,
            'training_releases':receipt['releases'],'source':source,'training':{},'validation':[],
            'ablation':'untrained_unit_gains_rejected_by_physics_gate'}
    data['freeze']=generate.encode(freeze)
    result={'status':'verified','freeze_sha256':generate.sha(data['freeze']),'checkpoint_sha256':freeze['checkpoint_sha256'],
            'input_receipt_sha256':generate.sha(data['training_inputs']),'training_data_sha256':freeze['training_data_sha256'],
            'releases':receipt['releases'],'source':source,'training':{},'validation':[],'ablation':freeze['ablation']}
    data['training_result']=generate.encode(result)
    origin={key:'fixture' for key in ('catalog_id','run_id','attempt_id','request_sha256','material_sha256','custody_receipt_sha256','custody_identity','custody_receipt_base64')}
    evidence={name:{'kind':'run_artifact','source':dict(origin,schema_version=1,artifact_role=role,
              artifact_bytes=len(data[name]),measured_sha256=generate.sha(data[name]))} for name,(role,cap) in ev.INPUTS.items()}
    evidence['build_receipt']={'reference_id':'fixture'}
    return data,evidence


class EvaluationTests(unittest.TestCase):
    def test_exact_finite_output_inventory_and_input_evidence(self):
        recipe=project.definition({'evaluate.py':b'fixture'},'a'*64)
        self.assertEqual(len(recipe['outputs']),89)
        self.assertEqual(len({i['path'] for i in recipe['outputs']}),89)
        self.assertEqual(recipe['resources'],{'profile':'captured_cpu_large_outputs_v1','wall_seconds':2400,'max_output_bytes':3500000000})
        self.assertIn({'input_evidence':True},recipe['arguments'])
        self.assertEqual(sum(i['role']=='scientific_fields' for i in recipe['outputs']),64)
        with self.assertRaises(ValueError):project.definition({},'bad')

    def test_inputs_bind_one_run_roles_hashes_and_immutable_freeze(self):
        data,evidence=inputs()
        with patch.object(cpu_compare,'BUILD_RECEIPT_SHA256',generate.sha(data['build_receipt'])):
            ev.validate_inputs(data,evidence,'a'*64)
            for mutation in (lambda e:e['checkpoint']['source'].update(run_id='other'),
                             lambda e:e['freeze']['source'].update(artifact_role='checkpoint'),
                             lambda e:e['training_result']['source'].update(measured_sha256='f'*64),
                             lambda e:e['checkpoint'].update(kind='project_reference')):
                bad=copy.deepcopy(evidence);mutation(bad)
                with self.assertRaises(ValueError):ev.validate_inputs(data,bad,'a'*64)
            with self.assertRaises(ValueError):ev.validate_inputs(data,evidence,'b'*64)
            bad=dict(data,checkpoint=b'mutated')
            with self.assertRaises(ValueError):ev.validate_inputs(bad,evidence,'a'*64)

    def test_tee_bound_exact_digest_and_trailing_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            tee=ev.TeeReader(io.BytesIO(b'abcdef'),Path(folder)/'wire')
            self.assertEqual(tee.read(2),b'ab');self.assertEqual(tee.read(4),b'cdef');tee.close()
            self.assertEqual(tee.path.read_bytes(),b'abcdef');self.assertEqual(tee.digest.hexdigest(),generate.sha(b'abcdef'))
            bad=ev.TeeReader(io.BytesIO(b'extra'),Path(folder)/'extra')
            with self.assertRaises(ValueError):bad.close()
            self.assertTrue(bad.closed)
            limited=ev.TeeReader(io.BytesIO(b'xx'),Path(folder)/'limit')
            with patch.object(ev,'WIRE_LIMIT',1):
                with self.assertRaises(ValueError):limited.read(2)
            with self.assertRaises(ValueError):limited.close()

    def test_original_result_coverage_numbers_and_memory_refusals(self):
        records=[]
        for repeat in range(5):
            for offset,seed in enumerate(ev.SEEDS):
                rotation=(repeat+offset)%3
                for method in ev.METHODS[rotation:]+ev.METHODS[:rotation]:
                    reports=[{'frame':i,'time':i/60,'relative_residual':0,'actual_divergence_max':0,'courant':0,'iterations':0} for i in range(1,121)]
                    records.append({'repetition':repeat,'seed':seed,'method':method,'frames':120,
                                    'wall_ms_including_native_startup_teardown':1,'reports':reports})
        accuracy=[{'seed':seed,'frames':120,'max_relative_velocity_l2':0,'max_relative_tracer_l2':0,'max_ai_divergence':0,
                   'errors':[{'relative_velocity_l2':0,'relative_tracer_l2':0,'centered_relative_pressure_l2':0,'tracer_rmse':0} for _ in range(120)]} for seed in ev.SEEDS]
        result={'schema':'rheon-trajectory-result-v1','freeze_sha256':'a'*64,'checkpoint_sha256':'b'*64,'benchmark':records,
                'accuracy':accuracy,'median_120_frame_wall_ms':dict.fromkeys(ev.METHODS,1),
                'speedup_vs_jacobi':1,'speedup_vs_sgs':1,'python_peak_rss_bytes':100,
                'gpu_peak_allocated_bytes':0,'gpu_peak_reserved_bytes':0,'model_warmup_s':0}
        ev.validate_result(result,{'checkpoint_sha256':'b'*64},'a'*64)
        for mutation in (lambda r:r['benchmark'].pop(),lambda r:r.update(speedup_vs_jacobi=2),
                         lambda r:r['accuracy'][0]['errors'][0].update(relative_tracer_l2=float('nan')),
                         lambda r:r.update(python_peak_rss_bytes=8000000000)):
            bad=copy.deepcopy(result);mutation(bad)
            with self.assertRaises(ValueError):ev.validate_result(bad,{'checkpoint_sha256':'b'*64},'a'*64)

    def test_chunk_partition_covers_wire_and_keeps_tee_on_failure_authored(self):
        ready={'schema':'rheon-trajectory-v1','n':32,'method':'jacobi','seed':900,'spacing':[1/32]*3,
               'dt':1/60,'density':1.25,'face_lengths':[33792]*3}
        header=generate.encode(ready);raw=struct.pack('<I',len(header))+header+bytes(range(120))
        def decoded(handle,method,index,state,record):
            self.assertEqual(handle.read(1),bytes([index-1]))
            return {'frame':index},[]
        def chunk(path,method,seed,ready,frames,wire,start,end,identity):
            path.write_bytes(wire)
            return {'path':path.name,'sha256':generate.sha(wire),'bytes':len(wire),
                    'frame_start':frames[0][0]['frame'],'frame_end':frames[-1][0]['frame'],
                    'stdout_start':start,'stdout_end':end,'stdout_sha256':generate.sha(wire)}
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output';output.mkdir()
            tee=ev.TeeReader(io.BytesIO(raw),Path(folder)/'wire');tee.read(len(raw));tee.close()
            with patch.object(ev,'checked_frame',side_effect=decoded),patch.object(ev,'write_chunk',side_effect=chunk):
                index=ev.retain_trajectory(tee,'jacobi',900,[None]*120,[None]*120,output,{})
            self.assertFalse(tee.path.exists())
            self.assertEqual([(c['frame_start'],c['frame_end']) for c in index['chunks']],[(i,min(i+15,120)) for i in range(1,121,16)])
            self.assertEqual(b''.join((output/c['path']).read_bytes() for c in index['chunks']),raw)
            tee=ev.TeeReader(io.BytesIO(raw),Path(folder)/'failed-wire');tee.read(len(raw));tee.close()
            with patch.object(ev,'checked_frame',side_effect=decoded),patch.object(ev,'write_chunk',side_effect=ValueError('refused chunk')):
                with self.assertRaises(ValueError):ev.retain_trajectory(tee,'jacobi',900,[None]*120,[None]*120,output,{})
            self.assertTrue(tee.path.exists())

    def test_private_workspace_retains_failed_attempt_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            with ev.private_workspace(root) as complete:
                (complete/'copy').write_bytes(b'verified redundant fixture')
            self.assertFalse(complete.exists())
            with self.assertRaises(ValueError):
                with ev.private_workspace(root) as failed:
                    (failed/'wire').write_bytes(b'incomplete evidence')
                    raise ValueError('fixture failure')
            self.assertEqual((failed/'wire').read_bytes(),b'incomplete evidence')

    def test_evaluation_transport_mode_is_closed_without_execution(self):
        for kwargs in ({'evaluation_mode':True,'allowed_seeds':(500,501)}, {'capture_hook':lambda a,b:b},
                       {'evaluation_mode':'yes'}, {'evaluation_mode':True,'capture_hook':3}):
            with self.assertRaises(ValueError):native_transport.Transport('absent',b'{}',**kwargs)

    @unittest.skipUnless(NUMPY,'Authored NPY/wire tests require dedicated NumPy interpreter; no model acceptance')
    def test_learned_request_framing_and_generic_six_field_chunk(self):
        import numpy as np
        import scientific_fields
        report={'frame':1,'time':1/60,'relative_residual':0,'actual_divergence_max':0,'courant':0,'iterations':0}
        encoded=generate.encode(report);state={'velocity':[]};raws=[]
        for name,dtype,center,stage in ev.FIELDS:
            array=np.zeros(tuple(ev.shape(center)),dtype=dtype)
            if name=='rhs':array.flat[0]=-0.0
            raws.append(array.tobytes())
            if name.startswith('velocity_'):state['velocity'].append(array.reshape(-1))
            else:state[name]=array.reshape(-1)
        wire=raws[0]+struct.pack('<I',len(encoded))+encoded+b''.join(raws)
        decoded=ev.checked_frame(io.BytesIO(wire),'learned',1,state,report)
        self.assertEqual(decoded[1][0]['raw'],raws[0])
        with self.assertRaises(ValueError):ev.checked_frame(io.BytesIO(wire[:-1]),'learned',1,state,report)
        corrupt=bytearray(wire);corrupt[0]=1
        with self.assertRaises(ValueError):ev.checked_frame(io.BytesIO(corrupt),'learned',1,state,report)
        ready={'spacing':[1/32]*3}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'chunk.zip'
            ev.write_chunk(path,'learned',900,ready,[decoded],wire,0,len(wire),{'fixture':True})
            meta=scientific_fields.parse_bundle(path.read_bytes())
            self.assertEqual((meta['frame_count'],meta['field_count']),(1,6))
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.read('sources/wire.bin'),wire)
                trace=json.loads(archive.read('sources/evaluation-trace.json'))
                self.assertTrue(trace['learned_rhs_request_before_report'])
                self.assertEqual(trace['stdout_sha256'],generate.sha(wire))

    @unittest.skipUnless(all(os.environ.get(n) for n in ('TULDOK_RHEON_LAB','TULDOK_RHEON_PARALLEL_BINARY','TULDOK_RHEON_PARALLEL_BUILD_RECEIPT')),
                         'Explicit original inputs required for source-only assembly')
    def test_original_sources_assemble_without_execution_or_checkpoint_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'project'
            args=(os.environ['TULDOK_RHEON_LAB'],os.environ['TULDOK_RHEON_PARALLEL_BINARY'],os.environ['TULDOK_RHEON_PARALLEL_BUILD_RECEIPT'],'a'*64,destination)
            project.assemble(*args)
            self.assertEqual((destination/'lab/scripts/trajectory_experiment.py').read_bytes(),(Path(args[0])/'scripts/trajectory_experiment.py').read_bytes())
            self.assertFalse((destination/'model.pt').exists())
            with self.assertRaises(FileExistsError):project.assemble(*args)


if __name__=='__main__':unittest.main()
