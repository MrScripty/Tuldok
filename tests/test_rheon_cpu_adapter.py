"""CPU wrapper boundaries; synthetic results do not qualify model execution."""
import copy
import io
import json
import struct
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adapters.rheon import cpu_compare as cpu, cpu_project, native_transport as transport


def result():
    config = {'schema': 'rheon-cpu-only-comparison-v1', 'device': 'cpu', 'all_model_tensors_on_cpu': True,
              'cuda_visible_devices': '', 'n': 32, 'frames': 120, 'seeds': [900,901,902,903],
              'repetitions': 1, 'native_threads_all_methods': 8, 'torch_threads': 8, 'torch_interop_threads': 1,
              'checkpoint_sha256': cpu.CHECKPOINT_SHA256, 'binary_sha256': cpu.BINARY_SHA256,
              'test_status': 'previously exposed seeds; backend/hardware comparison, no retraining',
              'source_sha256': {k:v for k,v in cpu.SOURCES.items() if k != 'verify_parallel_results.py'},
              'model_setup_s': 0, 'warmup_s': 0, 'torch': 'test-only', 'python_executable': 'test-only',
              'timing_scope': 'test-only'}
    report = {'relative_residual': 0, 'actual_divergence_max': 0, 'courant': .1, 'iterations': 0}
    metric = {'max_velocity_relative_l2': 0, 'max_tracer_relative_l2': 0,
              'frames': [{'velocity_relative_l2': 0, 'tracer_relative_l2': 0} for _ in range(120)]}
    methods = ('jacobi','sgs','learned')
    return {'status': 'verified', 'config': config, 'qualified_timed_frames': 1440,
            'max_relative_residual': 0, 'max_divergence': 0, 'python_peak_rss_bytes': 1,
            'median_120_frame_wall_ms': {m:1 for m in methods}, 'speedup_vs_jacobi': 1, 'speedup_vs_sgs': 1,
            'records': [{'repetition': 0, 'seed': seed, 'method': method, 'frames': 120,
                         'wall_ms_including_native_startup_teardown': 1,
                         'reports': [dict(report,frame=i,time=i/60) for i in range(1,121)]}
                        for seed in range(900,904) for method in methods[(seed-900)%3:]+methods[:(seed-900)%3]],
            'accuracy': [{'seed': seed, 'jacobi': copy.deepcopy(metric), 'sgs': copy.deepcopy(metric)} for seed in range(900,904)]}


class CPUAdapterTests(unittest.TestCase):
    def test_generic_definition_binds_runtime_and_all_original_sources(self):
        recipe = cpu_project.definition({'cpu_compare.py': b'x'}, 'a'*64)
        self.assertEqual(recipe['runtime'], 'captured_cpu_python_v1')
        self.assertEqual(recipe['runtime_snapshot_sha256'], 'a'*64)
        self.assertEqual(recipe['resources']['wall_seconds'], 600)
        self.assertEqual(len(recipe['outputs']), 6)
        self.assertEqual(set(recipe['inputs']), {'checkpoint','freeze','build_receipt'})
        for value in ('', 'a'*63, 'G'*64, None):
            with self.assertRaises(ValueError): cpu_project.definition({}, value)

    def test_controls_reject_bool_and_outside_budget(self):
        for args in ((True,1),(0,1),(9,1),(8,True),(8,4)):
            with self.assertRaises(ValueError): cpu.controls(*args)
        cpu.controls(8,3)

    def test_result_requires_complete_trajectories_and_accuracy(self):
        cpu.validate_result(result(),8,1)
        for mutate in (lambda r:r['records'].pop(),lambda r:r['records'][0]['reports'].pop(),
                       lambda r:r['accuracy'].pop(),lambda r:r.update(status='partial'),
                       lambda r:r['config'].update(device='cuda')):
            value=result();mutate(value)
            with self.assertRaises(ValueError): cpu.validate_result(value,8,1)

    def test_result_rejects_nonfinite_failure_and_iterative_learned_path(self):
        for key,bad in (('relative_residual',float('nan')),('actual_divergence_max',1),('courant',1.1),('courant',10**400)):
            value=result();value['records'][0]['reports'][0][key]=bad
            with self.assertRaises(ValueError):cpu.validate_result(value,8,1)
        value=result();value['records'][2]['reports'][0]['iterations']=1
        with self.assertRaises(ValueError):cpu.validate_result(value,8,1)
        value=result();value['accuracy'][0]['jacobi']['max_velocity_relative_l2']=1e-5
        with self.assertRaises(ValueError):cpu.validate_result(value,8,1)

    def test_report_maxima_full_frame_errors_and_cross_artifacts(self):
        for mutate in (lambda r:r['accuracy'][0]['jacobi']['frames'][0].clear(),
                       lambda r:r['accuracy'][0]['jacobi']['frames'][0].update(velocity_relative_l2=float('nan')),
                       lambda r:r['accuracy'][0]['jacobi'].update(max_velocity_relative_l2=1e-8),
                       lambda r:r.update(qualified_timed_frames=1), lambda r:r.update(speedup_vs_sgs=2),
                       lambda r:r['config'].update(cuda_visible_devices='0'),
                       lambda r:r['records'][0].update(frames=119)):
            value=result();mutate(value)
            with self.assertRaises(ValueError):cpu.validate_result(value,8,1)
        value=result();timing={k:v for k,v in copy.deepcopy(value).items() if k not in ('status','accuracy')}
        cpu.validate_artifacts(value['config'],timing,value,8,1)
        timing['speedup_vs_sgs']=2
        with self.assertRaises(ValueError):cpu.validate_artifacts(value['config'],timing,value,8,1)

    def test_prefix_reader_preserves_exact_ready_and_following_wire(self):
        stream=transport.PrefixReader(b'abc',io.BytesIO(b'defghi'))
        self.assertEqual(stream.read(2),b'ab');self.assertEqual(stream.read(4),b'cdef')
        self.assertEqual(stream.read(3),b'ghi')
        with self.assertRaises(ValueError):stream.read()
        stream.close()
        with self.assertRaises(ValueError):transport.exact(io.BytesIO(b'x'),2)

    def test_transport_rejects_unadmitted_commands_without_launch(self):
        value=object.__new__(transport.Transport);value.binary='/captured/native'
        with patch.object(transport.subprocess,'Popen',side_effect=AssertionError('Unexpected launch')):
            for args in (['/other','32','jacobi','900'],['/captured/native','8','jacobi','900'],
                         ['/captured/native','32','jacobi','100']):
                with self.assertRaises(ValueError):value.Popen(args,stdin=-1,stdout=-1)

    def test_unknown_checkpoint_and_receipt_refused_without_torch(self):
        with self.assertRaises(ValueError):cpu.inputs(b'bad',b'{}',b'{}',b'bad')

    @unittest.skipUnless(os.environ.get('TULDOK_RHEON_PARALLEL_BINARY'), 'Explicit pinned parallel binary required; READY/STOP only')
    def test_actual_proxy_ready_replay_stop_and_failure_cleanup(self):
        import recipe_contract
        from adapters.rheon import generate
        binary=Path(os.environ['TULDOK_RHEON_PARALLEL_BINARY'])
        native=binary.read_bytes()
        definition={'native_sources':['native']}
        policy=recipe_contract.native_policies(definition,{'native':native},recipe_contract.runtime_identity())['native']
        def make():return transport.Transport(binary,generate.encode(policy))
        value=make()
        process=value.Popen([str(binary),'32','jacobi','900'],stdin=-1,stdout=-1)
        try:
            length,=struct.unpack('<I',transport.exact(process.stdout,4))
            ready=json.loads(transport.exact(process.stdout,length))
            self.assertEqual(ready,value.evidence[0]['ready'])
            process.stdin.write(b'\0');process.stdin.flush();process.stdin.close()
            self.assertEqual(process.wait(timeout=10),0)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=3)
            process.stdout.close()
        for failure in ('truncated','mapping','geometry'):
            value=make();created=[];original=transport.subprocess.Popen
            def launch(*args,**kwargs):
                child=original(*args,**kwargs);created.append(child);return child
            with patch.object(transport.subprocess,'Popen',side_effect=launch):
                if failure=='truncated':
                    with patch.object(transport,'exact',side_effect=ValueError('Truncated READY')):
                        with self.assertRaises(ValueError):value.Popen([str(binary),'32','jacobi','900'],stdin=-1,stdout=-1)
                elif failure=='mapping':
                    with patch.object(generate,'mapping_evidence',side_effect=ValueError('Mapping refused')):
                        with self.assertRaises(ValueError):value.Popen([str(binary),'32','jacobi','900'],stdin=-1,stdout=-1)
                else:
                    decode=generate.decode
                    def wrong(raw):
                        item=decode(raw);item['face_lengths']=[1,1,1];return item
                    with patch.object(generate,'decode',side_effect=wrong):
                        with self.assertRaises(ValueError):value.Popen([str(binary),'32','jacobi','900'],stdin=-1,stdout=-1)
            self.assertEqual(len(created),1);self.assertIsNotNone(created[0].poll())
            self.assertTrue(created[0].stdin.closed);self.assertTrue(created[0].stdout.closed)

    @unittest.skipUnless(all(os.environ.get(x) for x in ('TULDOK_RHEON_LAB','TULDOK_RHEON_PARALLEL_BINARY','TULDOK_RHEON_PARALLEL_BUILD_RECEIPT')),
                         'Set explicit pinned lab/build paths for actual-byte assembly; no model execution')
    def test_actual_inputs_and_original_scripts_retained_no_execution(self):
        lab=Path(os.environ['TULDOK_RHEON_LAB'])
        with tempfile.TemporaryDirectory() as root, patch.object(transport.subprocess,'Popen',side_effect=AssertionError('Unexpected execution')):
            destination=Path(root)/'project'
            arguments=(lab,os.environ['TULDOK_RHEON_PARALLEL_BINARY'],os.environ['TULDOK_RHEON_PARALLEL_BUILD_RECEIPT'],'a'*64,destination)
            cpu_project.assemble(*arguments)
            checkpoint=(destination/'model.pt').read_bytes();freeze=(destination/'freeze.json').read_bytes()
            native=(destination/'lab/target/release/rheon-trajectory-parallel').read_bytes()
            receipt=json.loads((destination/'build-receipt.json').read_bytes())
            for mutation in ('missing','arbitrary','rehash'):
                bad=copy.deepcopy(receipt)
                if mutation=='missing':
                    bad.pop('lock_sha256_before');bad.pop('lock_sha256_after')
                elif mutation=='arbitrary':
                    bad['lock_sha256_before']=bad['lock_sha256_after']='a'*64
                else:bad['toolchain']['cargo']='invented'
                with self.assertRaises(ValueError):cpu.inputs(checkpoint,freeze,json.dumps(bad).encode(),native)
            for name in cpu.SOURCES:
                self.assertEqual((destination/'lab/scripts'/name).read_bytes(),(lab/'scripts'/name).read_bytes())
            for name in ('model.pt','freeze.json'):
                self.assertEqual((destination/name).read_bytes(),(lab/'experiments/trajectory-v2'/name).read_bytes())
            with self.assertRaises(FileExistsError):cpu_project.assemble(*arguments)


if __name__=='__main__':unittest.main()
