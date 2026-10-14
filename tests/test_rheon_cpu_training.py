"""Authored boundary fixtures only; these tests do not qualify real fitting."""
import contextlib
import copy
import io
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from adapters.rheon import cpu_train as train, cpu_training_project as project, generate, native_transport


NUMPY_AVAILABLE = importlib.util.find_spec('numpy') is not None
NUMPY_REASON = 'Requires NumPy in the dedicated training interpreter; authored fixtures are not model acceptance'

def authored_bundle(seed=100):
    def message(value):
        raw=generate.encode(value);return struct.pack('<I',len(raw))+raw
    ready={'schema':'rheon-trajectory-v1','n':32,'method':'jacobi','seed':seed,'dt':1/60,'density':1.25,
           'spacing':[1/32]*3,'face_lengths':[33*32*32]*3}
    wire=bytearray(message(ready))
    for index in range(1,9):
        wire.extend(message({'frame':index,'time':index/60,'actual_divergence_max':0,'courant':0,'relative_residual':0}))
        for count,size in ((32768,8),(32768,8),(33792,4),(33792,4),(33792,4),(32768,4)):
            wire.extend(bytes(count*size))
    wire=bytes(wire);controls={'grid':32,'frames':8,'seed':seed,'method':'jacobi'}
    build=generate.encode({'binary_sha256':generate.BINARY_SHA256,'source':{k:{'commit':v} for k,v in generate.SOURCE_PINS.items()}})
    files=[{'path':generate.LIBRARY_DIRECTORY+'/'+name,'bytes':1,'sha256':'a'*64}
           for name in ('libgcc_s.so.1','libm.so.6','libc.so.6','ld-linux-x86-64.so.2')]
    policy=generate.encode({'schema_version':1,'policy':'glibc_x86_64_no_preload_v1',
        'source':{'path':'rheon-trajectory-probe','sha256':generate.BINARY_SHA256},'loader':files[-1],
        'library_directory':generate.LIBRARY_DIRECTORY,'loader_arguments':generate.LOADER_ARGUMENTS,
        'runtime_files':files,'absent_paths':['/etc/ld.so.preload']})
    maps={name:{'device':'00:01','inode':i+1} for i,name in enumerate(['sealed-native','sealed-loader']+[f['path'] for f in files[:-1]])}
    _,frames=generate.decode_wire(wire,controls)
    receipt=generate.encode({'controls':controls,'binary_sha256':generate.BINARY_SHA256,
        'wire_sha256':generate.sha(wire),'wire_bytes':len(wire),'build_receipt_sha256':generate.sha(build),
        'native_policy_sha256':generate.sha(policy),'stdin_hex':(bytes([2]*8+[0])).hex(),
        'ready':ready,'frames':[f['report'] for f in frames],
        'wrapper_sha256':generate.sha(Path(generate.__file__).read_bytes()),
        'loaded_mappings':maps})
    return generate.scientific_bundle(wire,controls,build,receipt,policy)


def comparison():
    errors=[{'relative_velocity_l2':0,'relative_tracer_l2':0,'centered_relative_pressure_l2':0,'tracer_rmse':0} for _ in range(60)]
    value={'frames':60,'errors':errors,'max_relative_velocity_l2':0,'max_relative_tracer_l2':0,'max_ai_divergence':0}
    report={'relative_residual':0,'actual_divergence_max':0,'courant':0,'iterations':0}
    ref={'method':'jacobi','frames':60,'reports':[dict(report,frame=i,time=i/60) for i in range(1,61)]}
    learned=copy.deepcopy(ref);learned['method']='learned'
    return value,ref,learned


class TrainingTests(unittest.TestCase):
    def test_closed_definition_really_consumes_six_releases(self):
        recipe=project.definition({'cpu_train.py':b'fixture'},'a'*64)
        self.assertEqual(set(recipe['inputs']),set(train.RELEASE_NAMES)|{'build_receipt'})
        self.assertEqual([a['input'] for a in recipe['arguments'] if 'input' in a],list(train.RELEASE_NAMES)+['build_receipt'])
        self.assertEqual(recipe['resources']['max_output_bytes'],64*1024*1024)
        self.assertEqual({o['role'] for o in recipe['outputs']} & {'checkpoint','result_summary'},{'checkpoint','result_summary'})
        with self.assertRaises(ValueError):project.definition({},'bad')

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_REASON)
    def test_authored_six_field_wire_bundle_preserves_exact_fit_arrays(self):
        raw=authored_bundle()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:build_hash=generate.sha(archive.read('sources/build-receipt.json'))
        with patch.object(train,'SERIAL_BUILD_SHA256',build_hash):seed,rhs,pressure,receipt=train.validate_asset(raw)
        self.assertEqual(seed,100);self.assertEqual(len(rhs),8);self.assertEqual(len(pressure),8)
        self.assertEqual(rhs[0].dtype.str,'<f8');self.assertEqual(rhs[0].shape,(32768,))
        self.assertEqual(receipt['arrays'][0]['rhs_sha256'],generate.sha(bytes(32768*8)))
        with self.assertRaises(ValueError):train.validate_asset(authored_bundle(112))

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_REASON)
    def test_array_rehash_cannot_hide_disagreement_with_wire(self):
        raw=authored_bundle();members={}
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:members={n:archive.read(n) for n in archive.namelist()}
        manifest=json.loads(members['manifest.json']);entry=manifest['frames'][0]['arrays'][0]
        changed=bytearray(members[entry['path']]);changed[-8:]=struct.pack('<d',.25)
        members[entry['path']]=bytes(changed);entry['sha256']=generate.sha(changed)
        members['manifest.json']=generate.encode(manifest)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as archive:
            for name,data in members.items():archive.writestr(name,data)
        with patch.object(train,'SERIAL_BUILD_SHA256',generate.sha(members['sources/build-receipt.json'])):
            with self.assertRaises(ValueError):train.validate_asset(out.getvalue())

    def test_validation_gates_recompute_and_require_complete_reports(self):
        train.validate_comparison(*comparison())
        for change in (lambda a:a[0]['errors'][0].update(relative_velocity_l2=float('nan')),
                       lambda a:a[0].update(max_relative_velocity_l2=1),
                       lambda a:a[1]['reports'].pop(),lambda a:a[2]['reports'][0].update(iterations=1)):
            data=comparison();change(data)
            with self.assertRaises(ValueError):train.validate_comparison(*data)

    def test_ablation_requires_exact_positive_native_physics_diagnostic(self):
        def diagnostic(raw,code=1):
            return {'seed':500,'method':'learned','exit_code':code,'stderr_hex':raw.hex(),'stderr_sha256':generate.sha(raw)}
        self.assertTrue(train.physics_rejection(diagnostic(b'trajectory probe: stored divergence 2.5 exceeds 0.00001\n')))
        # Exact native line retained from failed Run ece8abe0a4024d1483048d91b7980cf0.
        actual=b'trajectory probe: stored divergence 0.20241660624742508 exceeds 0.00001\n'
        self.assertTrue(train.physics_rejection(diagnostic(actual)))
        corrupt=diagnostic(actual);corrupt['stderr_sha256']='a'*64
        self.assertFalse(train.physics_rejection(corrupt))
        self.assertFalse(train.physics_rejection(diagnostic(b'Error: stored divergence 2.5 exceeds 0.00001\n')))
        for raw in (b'trajectory probe: native loader unavailable\n',b'trajectory probe: stored divergence 0 exceeds 0.00001\n',
                    b'trajectory probe: relative residual NaN exceeds 1e-5\n',b'trajectory probe: stored divergence 2 exceeds 1e-4\n'):
            self.assertFalse(train.physics_rejection(diagnostic(raw)))
        self.assertFalse(train.physics_rejection(diagnostic(b'trajectory probe: stored divergence 2 exceeds 1e-5\n',-9)))

    @unittest.skipUnless(NUMPY_AVAILABLE, NUMPY_REASON)
    def test_authored_combined_release_order_and_cross_family_refusal(self):
        import numpy as np
        import scientific_release
        def fake_asset(raw):
            seed=int(raw)
            arrays=[np.full(32768,seed*10+i,dtype='<f8') for i in range(1,9)]
            return seed,arrays,arrays,{'seed':seed,'frames':8}
        def write_releases(folder, mode):
            paths=[]
            for pair in range(6):
                rows=[];assets={}
                for seed in (101+pair*2,100+pair*2):
                    asset=f'assets/{seed}.zip';assets[asset]=str(seed).encode()
                    rows.append({'id':str(seed),'revision':1,'asset':asset,'split':'test' if mode=='split' and seed==100 else 'train',
                                 'groups':['shared'] if mode=='family' and seed in (100,102) else [str(seed)],
                                 'parents':[],'content_hash':str(seed),'pixel_hash':None,'kind':'field_sequence'})
                path=Path(folder)/str(pair)
                with zipfile.ZipFile(path,'w') as archive:
                    archive.writestr('manifest.json',json.dumps({'records':rows}))
                    for name,data in assets.items():archive.writestr(name,data)
                paths.append(path)
            return paths
        with tempfile.TemporaryDirectory() as folder, patch.object(scientific_release,'validate_bytes',return_value={'field_sequence_count':2}), \
                patch.object(train,'validate_asset',side_effect=fake_asset), contextlib.redirect_stdout(io.StringIO()):
            paths=write_releases(folder,'valid');rhs,pressure,receipt=train.load_training(paths)
            self.assertEqual(rhs.shape,(96,32768));self.assertEqual(rhs[0,0],1001);self.assertEqual(rhs[-1,0],1118)
            self.assertEqual(receipt['trajectory_order'],list(range(100,112)))
            for mode in ('family','split'):
                with self.assertRaises(ValueError):train.load_training(write_releases(folder,mode))
            paths=write_releases(folder,'valid');paths[1]=paths[0]
            with self.assertRaises(ValueError):train.load_training(paths)

    def test_incomplete_policy_and_memory_limits_refused(self):
        with zipfile.ZipFile(io.BytesIO(authored_bundle())) as archive:
            policy=json.loads(archive.read('sources/native-policy.json'))
            mappings=json.loads(archive.read('sources/producer-receipt.json'))['loaded_mappings']
        train.validate_policy_evidence(policy,mappings)
        for mutate in (lambda p:p.update(schema_version=True),lambda p:p.update(runtime_files=[]),lambda p:p['loader'].pop('sha256'),
                       lambda p:p['runtime_files'][0].update(bytes=True)):
            bad=copy.deepcopy(policy);mutate(bad)
            with self.assertRaises(ValueError):train.validate_policy_evidence(bad,mappings)
        train.validate_memory({'python_peak_rss_bytes':100,'gpu_peak_allocated_bytes':0,'gpu_peak_reserved_bytes':0})
        with self.assertRaises(ValueError):train.validate_memory({'python_peak_rss_bytes':20000000000,'gpu_peak_allocated_bytes':0,'gpu_peak_reserved_bytes':0})

    def test_progress_protocol_reports_observed_counts_only(self):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):train.progress('fit',0,1)
        event=json.loads(stream.getvalue());self.assertEqual(event,{'format':'tuldok_progress_v1','stage':'fit','completed':0,'total':1,'metrics':{}})

    def test_optional_diagnostics_are_exact_bounded_and_closed_authored_process(self):
        from types import SimpleNamespace
        ready={'schema':'rheon-trajectory-v1','n':32,'method':'learned','seed':500,'dt':1/60,'density':1.25,
               'spacing':[1/32]*3,'face_lengths':[33792]*3}
        raw=generate.encode(ready);wire=struct.pack('<I',len(raw))+raw
        loader='/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'
        for diagnostic in (b'trajectory probe: stored divergence 2 exceeds 0.00001\n',b'x'*65537):
            owner=object.__new__(native_transport.Transport)
            owner.binary='/native';owner.allowed_seeds=('500','501');owner.capture_diagnostics=True
            owner.native=b'fixture';owner.policy={'loader':{'path':loader},'loader_arguments':[]}
            owner.observed={loader:(b'fixture',None)};owner.evidence=[];owner.diagnostics=[]
            captured=[]
            def launch(*args,**kwargs):
                stream=kwargs['stderr'];captured.append(stream);stream.write(diagnostic);stream.flush()
                return SimpleNamespace(pid=123,stdin=io.BytesIO(),stdout=io.BytesIO(wire),wait=lambda **kw:1)
            stderr=SimpleNamespace(buffer=io.BytesIO())
            with patch.object(native_transport.subprocess,'Popen',side_effect=launch), \
                    patch.object(generate,'mapping_evidence',return_value={}),patch.object(native_transport.sys,'stderr',stderr):
                child=owner.Popen(['/native','32','learned','500'],stdin=-1,stdout=-1)
                if len(diagnostic)>65536:
                    with self.assertRaises(ValueError):child.wait(timeout=1)
                else:
                    self.assertEqual(child.wait(timeout=1),1)
                    self.assertEqual(bytes.fromhex(owner.diagnostics[0]['stderr_hex']),diagnostic)
                    self.assertEqual(stderr.buffer.getvalue(),diagnostic)
                self.assertTrue(captured[0].closed)
                child.stdin.close();child.stdout.close()

    def test_seed_scope_is_closed_and_default_unchanged(self):
        for seeds in ((100,),[500,501],(True,501),(900,500)):
            with self.assertRaises(ValueError):native_transport.Transport('absent',b'{}',allowed_seeds=seeds)
        value=object.__new__(native_transport.Transport);value.binary='/native';value.allowed_seeds=('500','501')
        with patch.object(native_transport.subprocess,'Popen',side_effect=AssertionError('No authored native acceptance')):
            with self.assertRaises(ValueError):value.Popen(['/native','32','learned','900'],stdin=-1,stdout=-1)

    def test_missing_release_count_fails_before_any_input_read(self):
        with self.assertRaises(ValueError):train.load_training([])

    @unittest.skipUnless(all(os.environ.get(x) for x in ('TULDOK_RHEON_LAB','TULDOK_RHEON_PARALLEL_BINARY','TULDOK_RHEON_PARALLEL_BUILD_RECEIPT')),
                         'Explicit pinned existing inputs required; assembly never executes fitting')
    def test_actual_byte_assembly_captures_reader_and_original_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'project'
            args=(os.environ['TULDOK_RHEON_LAB'],os.environ['TULDOK_RHEON_PARALLEL_BINARY'],os.environ['TULDOK_RHEON_PARALLEL_BUILD_RECEIPT'],'a'*64,target)
            project.assemble(*args)
            self.assertTrue((target/'cold/scientific_release.py').is_file())
            self.assertEqual((target/'lab/scripts/trajectory_model.py').read_bytes(),(Path(args[0])/'scripts/trajectory_model.py').read_bytes())
            with self.assertRaises(FileExistsError):project.assemble(*args)


if __name__=='__main__':unittest.main()
