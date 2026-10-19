"""Real isolated Linux custody, failure/restart evidence and bounded native streams."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import recipe_process as custody

FIXTURE=Path(__file__).parent/'fixtures/external_recipe.py'


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.output=self.root/'output';self.output.mkdir()
        self.source=self.root/'source.py';self.source.write_bytes(FIXTURE.read_bytes())
        self.input=self.root/'input.txt';self.input.write_bytes(b'exact fixture input\n')
        self.handles=[];self.addCleanup(self.cleanup)

    def cleanup(self):
        for handle in self.handles:
            handle.close_control()
            try:handle.process.wait(timeout=12)
            except Exception:
                handle.process.kill();handle.process.wait(timeout=2)

    def spec(self,mode='complete',*args):
        executable=str(Path('/usr/bin/python3').resolve())
        return dict(schema_version=1,attempt_id=uuid.uuid4().hex,request_sha256='a'*64,
            argv=[executable,str(self.source),mode,*(str(arg) for arg in args)] if args else [executable,str(self.source),mode,str(self.input),str(self.output)],
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},cwd=str(self.root),stdin_base64='',wall_seconds=5,
            executable_sha256=hashlib.sha256(Path(executable).read_bytes()).hexdigest(),max_output_bytes=8192,output_dir=str(self.output),
            runtime_files=[],trusted_install_owner_uid=os.stat('/usr').st_uid,
            captured_files=[dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in (self.source,self.input)])

    def start(self,spec):
        handle=custody.launch(spec,self.root/('custody-'+spec['attempt_id']));self.handles.append(handle)
        self.until(handle,lambda:handle.ready is not None)
        return handle

    def until(self,handle,predicate,timeout=15):
        deadline=time.monotonic()+timeout;events=[]
        while time.monotonic()<deadline:
            events.extend(handle.poll())
            if predicate():return events
            time.sleep(.02)
        self.fail('Custody observation deadline: '+repr(events))

    def finish(self,handle):
        self.until(handle,lambda:handle.terminal or handle.lost)
        handle.process.wait(timeout=2)
        return custody.load_receipt(handle.directory/'receipt.json',handle.expected_identity)

    def test_artifact_source_cold_identity_and_completed_custody(self):
        import copy
        identity={'attempt_id':'a'*32,'request_sha256':'b'*64,'spec_sha256':'c'*64,
                  'helper':custody.identity(os.getpid())}
        receipt=dict(identity,schema_version=1,go_received=True,spawn_closed=True,drained=True,
                     echild=True,outcome='completed',reason='completed',leader_returncode=0,
                     streams={name:{'bytes':0,'sha256':custody.digest(b'')} for name in ('stdout','stderr')})
        raw=custody.encoded(receipt);payload=b'authored artifact'
        source=dict(schema_version=1,catalog_id='d'*32,run_id='a'*32,attempt_id='a'*32,
                    request_sha256='b'*64,material_sha256='e'*64,artifact_name='model.pt',
                    artifact_role='checkpoint',artifact_bytes=len(payload),measured_sha256=custody.digest(payload),
                    custody_receipt_sha256=custody.digest(raw),custody_identity=identity,
                    custody_receipt_base64=base64.b64encode(raw).decode())
        self.assertEqual(custody.validate_artifact_source(source,custody.digest(payload),len(payload)),source)
        for change in ({'extra':1},{'run_id':'f'*32},{'artifact_name':'../model.pt'},
                       {'artifact_bytes':len(payload)+1},{'custody_receipt_base64':source['custody_receipt_base64']+'\n'},
                       {'custody_receipt_sha256':'f'*64}):
            with self.subTest(change=change),self.assertRaises(custody.ProcessError):
                custody.validate_artifact_source(dict(source,**change),custody.digest(payload),len(payload))
        changed=copy.deepcopy(source);changed['custody_identity']['request_sha256']='f'*64
        with self.assertRaises(custody.ProcessError):custody.validate_artifact_source(changed,custody.digest(payload),len(payload))
        bad=custody.encoded(dict(receipt,outcome='unknown',drained=False,echild=False))
        changed=dict(source,custody_receipt_base64=base64.b64encode(bad).decode(),custody_receipt_sha256=custody.digest(bad))
        with self.assertRaisesRegex(custody.ProcessError,'completed and drained'):
            custody.validate_artifact_source(changed,custody.digest(payload),len(payload))
        with self.assertRaises(custody.ProcessError) as error:
            custody.validate_artifact_source(source,'f'*64,len(payload))
        self.assertEqual(error.exception.code,'conflict')

    def test_barrier_complete_exact_output_and_cold_receipt(self):
        handle=self.start(self.spec())
        time.sleep(.08);self.assertFalse((self.output/'result.txt').exists())
        handle.go(handle.ready)
        with self.assertRaises(custody.ProcessError):handle.go(handle.ready)
        receipt=self.finish(handle)
        self.assertEqual(receipt['outcome'],'completed');self.assertTrue(receipt['echild'])
        self.assertEqual((self.output/'result.txt').read_bytes(),self.input.read_bytes())
        log=(handle.directory/'stdout.log').read_bytes()
        self.assertIn(b'child complete',log);self.assertIn(b'"stage": "done"',log)
        self.assertEqual(receipt['streams']['stdout']['sha256'],hashlib.sha256(log).hexdigest())
        wrong=dict(handle.expected_identity,request_sha256='b'*64)
        with self.assertRaises(custody.ProcessError):custody.load_receipt(handle.directory/'receipt.json',wrong)

    def test_native_policy_absence_is_closed_and_receipt_is_pure(self):
        spec=self.spec(); spec['native_loader_policy']='glibc_x86_64_no_preload_v1'
        self.assertEqual(custody.validate_spec(spec),spec)
        with patch.object(custody.os,'stat',return_value=object()):
            with self.assertRaises(custody.ProcessError): custody.verify_native_loader_policy(spec['trusted_install_owner_uid'])
        with patch.object(custody.os,'stat',side_effect=FileNotFoundError):
            custody.verify_native_loader_policy(spec['trusted_install_owner_uid'])
        with patch.object(custody.os,'stat',side_effect=PermissionError):
            with self.assertRaises(PermissionError): custody.verify_native_loader_policy(spec['trusted_install_owner_uid'])
        bad=dict(spec,native_loader_policy='arbitrary-absence-path')
        with self.assertRaises(custody.ProcessError): custody.validate_spec(bad)
        handle=self.start(spec); handle.go(handle.ready); receipt=self.finish(handle)
        raw=(handle.directory/'receipt.json').read_bytes()
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure receipt validation read disk')):
            self.assertEqual(custody.validate_receipt(raw,handle.expected_identity),receipt)
        for malformed in (b'',b'x'*16385,b'{"schema_version":1,"schema_version":1}',b'{"x":NaN}'):
            with self.assertRaises((custody.ProcessError,ValueError)):
                custody.validate_receipt(malformed,handle.expected_identity)

    def test_cancel_before_go_and_controller_loss(self):
        for reason in ('cancel','loss'):
            with self.subTest(reason=reason):
                handle=self.start(self.spec())
                if reason=='cancel':handle.cancel()
                else:handle.close_control()
                handle.process.wait(timeout=12)
                receipt=custody.load_receipt(handle.directory/'receipt.json',handle.expected_identity)
                self.assertEqual(receipt['outcome'],'cancelled');self.assertFalse(receipt['go_received']);self.assertTrue(receipt['echild'])

    def test_setsid_double_fork_and_term_resistance_are_drained(self):
        marker=self.root/'escaped.pid';handle=self.start(self.spec('escape',marker));handle.go(handle.ready)
        deadline=time.monotonic()+3
        while not marker.exists() and time.monotonic()<deadline:handle.poll();time.sleep(.02)
        pid=int(marker.read_text());handle.cancel();receipt=self.finish(handle)
        self.assertTrue(receipt['drained']);self.assertEqual(receipt['outcome'],'cancelled')
        self.assertFalse(Path(f'/proc/{pid}').exists())

    def test_wall_and_stream_limits_and_nonzero_exit(self):
        for mode,reason in [('sleep','wall_timeout'),('flood','stream_limit'),('nonzero','nonzero_exit')]:
            with self.subTest(mode=mode):
                spec=self.spec(mode);spec['wall_seconds']=1
                handle=self.start(spec);handle.go(handle.ready);receipt=self.finish(handle)
                self.assertEqual(receipt['outcome'],'failed');self.assertEqual(receipt['reason'],reason)
                self.assertTrue(receipt['drained']);self.assertLessEqual((handle.directory/'stdout.log').stat().st_size,custody.STREAM_LIMIT)

    def test_source_drift_after_ready_does_not_execute(self):
        handle=self.start(self.spec());self.input.write_bytes(b'drift')
        handle.go(handle.ready);receipt=self.finish(handle)
        self.assertTrue(receipt['go_received']);self.assertEqual(receipt['outcome'],'failed')
        self.assertIsNone(receipt['leader_returncode'])
        self.assertFalse((self.output/'result.txt').exists())

    def test_spec_rejects_invalid_bounds_and_executable_hash_before_spawn(self):
        for update in ({'wall_seconds':601},{'stdin_base64':'?'},{'max_output_bytes':True},{'schema_version':True},{'extra':1}):
            with self.subTest(update=update),self.assertRaises(custody.ProcessError):custody.validate_spec(dict(self.spec(),**update))
        spec=self.spec();spec['executable_sha256']='0'*64
        with self.assertRaises(custody.ProcessError):custody.launch(spec,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_malformed_control_and_receipt_loss_never_claim_completion(self):
        handle=self.start(self.spec())
        handle.channel.send(b'{"type":"go","type":"cancel"}')
        receipt=self.finish(handle)
        self.assertFalse(receipt['go_received']);self.assertTrue(receipt['drained'])
        self.assertIsNone(receipt['leader_returncode'])
        handle=self.start(self.spec())
        (handle.directory/'receipt.tmp').write_bytes(b'collision')
        handle.go(handle.ready)
        self.until(handle,lambda:handle.lost)
        result=handle.close_control()
        self.assertFalse(result['drained']);self.assertEqual(result['outcome'],'unknown')

    def test_controller_eof_after_go_drains_escaped_child(self):
        marker=self.root/'escaped-eof.pid';handle=self.start(self.spec('escape',marker));handle.go(handle.ready)
        self.until(handle,marker.exists)
        pid=int(marker.read_text());receipt=handle.close_control()
        self.assertTrue(receipt['drained']);self.assertEqual(receipt['outcome'],'cancelled')
        self.assertFalse(Path(f'/proc/{pid}').exists())

    def test_helper_death_preserves_unknown_even_when_leader_is_dead(self):
        # The test process is a separate outer custodian solely to clean its own
        # fixture descendants after deliberately destroying the production one.
        libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
        self.assertEqual(libc.prctl(37,ctypes.byref(old),0,0,0),0)
        self.assertEqual(libc.prctl(36,1,0,0,0),0)
        marker=self.root/'orphan.pid';owned=[]
        try:
            handle=self.start(self.spec('escape',marker));handle.go(handle.ready)
            events=self.until(handle,marker.exists)
            leader=next(event['leader']['pid'] for event in events if event['type']=='started')
            child=int(marker.read_text())
            owned=[(pid,os.pidfd_open(pid)) for pid in (leader,child)]
            handle.process.kill();handle.process.wait(timeout=2)
            signal.pidfd_send_signal(owned[0][1],signal.SIGKILL)
            os.waitpid(leader,0)
            self.assertTrue(Path(f'/proc/{child}').exists())
            result=handle.close_control()
            self.assertEqual(result['outcome'],'unknown');self.assertFalse(result['drained'])
            self.assertFalse((handle.directory/'receipt.json').exists())
        finally:
            for pid,fd in owned:
                try:signal.pidfd_send_signal(fd,signal.SIGKILL)
                except ProcessLookupError:pass
                os.close(fd)
                try:os.waitpid(pid,0)
                except ChildProcessError:pass
            libc.prctl(36,old.value,0,0,0)

    def test_output_and_runtime_drift_bounds(self):
        spec=self.spec('outputs',self.output);spec['max_output_bytes']=1024
        handle=self.start(spec);handle.go(handle.ready);receipt=self.finish(handle)
        self.assertEqual(receipt['outcome'],'failed');self.assertTrue(receipt['drained'])
        self.assertLessEqual((self.output/'large').stat().st_size,1024)
        runtime=self.root/'runtime.dat';runtime.write_bytes(b'original')
        spec=self.spec();spec['runtime_files']=[dict(path=str(runtime),bytes=8,sha256=hashlib.sha256(b'original').hexdigest())]
        handle=self.start(spec);runtime.write_bytes(b'mutation');handle.go(handle.ready)
        receipt=self.finish(handle)
        self.assertTrue(receipt['go_received']);self.assertTrue(receipt['drained'])
        self.assertIsNone(receipt['leader_returncode'])

    def test_closed_controller_channel_reports_lost_once_and_cancel_is_idempotent(self):
        for _ in range(10):
            handle=self.start(self.spec('sleep'));handle.go(handle.ready)
            handle.cancel()
            for _repeat in range(100):handle.cancel()
            receipt=self.finish(handle)
            self.assertTrue(receipt['drained']);self.assertEqual(receipt['outcome'],'cancelled')
        handle=self.start(self.spec())
        handle.cancel();handle.process.wait(timeout=12)
        # Deterministically reproduce a send failure before queued terminal events
        # were observed, then require the parent supervisor to get a loss event.
        handle.sent_cancel=False;handle.cancel()
        self.assertIsNone(handle.channel)
        self.assertEqual(handle.poll(),[{'type':'lost','reason':'custodian_channel_closed'}])
        self.assertEqual(handle.poll(),[])
        self.assertTrue(handle.close_control()['drained'])


class CpuSnapshotContractTests(unittest.TestCase):
    """Authored tiny inventories prove custody checks, not package acceptance."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        contents={
            'python/bin/python3.12':b'\x7fELFauthored interpreter, not executable',
            'system/lib/ld-linux-x86-64.so.2':b'\x7fELFauthored loader, not executable',
            'python/lib/python3.12/os.py':b'# authored stdlib fixture\n',
            'python/lib/python3.12/lib-dynload/_fixture.so':b'\x7fELFauthored extension',
            'packages/numpy/__init__.py':b'# authored package fixture\n',
        }
        self.manifest={'schema_version':1,'profile':custody.CPU_PROFILE,'python_version':'3.12',
            'packages':{'numpy':'fixture','torch':'fixture'},
            'launch':{'python':'python/bin/python3.12','loader':'system/lib/ld-linux-x86-64.so.2',
                'home':'python','stdlib':'python/lib/python3.12','dynload':'python/lib/python3.12/lib-dynload',
                'packages':'packages','library_dirs':['system/lib']},
            'files':[{'path':name,'bytes':len(raw),'sha256':custody.digest(raw),
                      'mode':0o500 if name in ('python/bin/python3.12','system/lib/ld-linux-x86-64.so.2') else 0o400,
                      'kind':'elf' if raw.startswith(b'\x7fELF') else 'data'} for name,raw in sorted(contents.items())],
            'total_bytes':sum(map(len,contents.values()))}
        raw=custody.encoded(self.manifest);self.root=self.base/'runtime-snapshots'/custody.digest(raw)
        self.root.mkdir(parents=True,mode=0o700)
        for item in self.manifest['files']:
            target=self.root/item['path'];target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(contents[item['path']]);target.chmod(item['mode'])
        (self.root/'manifest.json').write_bytes(raw);(self.root/'manifest.json').chmod(0o400)
        self.descriptor={'schema_version':1,'profile':custody.CPU_PROFILE,'catalog_id':'a'*32,
            'root':str(self.root),'manifest_sha256':custody.digest(raw),'manifest_bytes':len(raw),
            'file_count':len(contents),'total_bytes':self.manifest['total_bytes'],'python_version':'3.12',
            'packages':self.manifest['packages'],'launch':self.manifest['launch']}

    def test_virtual_torch_origins_are_exact_and_captured(self):
        import sys
        import types
        defining=types.ModuleType('torch._ops')
        defining.__file__=str(self.root/'packages/torch/_ops.py')
        cls=type('_Ops',(types.ModuleType,),{'__module__':'torch._ops','__file__':'_ops.py'})
        defining._Ops=cls
        module=cls('torch.ops')
        modules={'torch._ops':defining,'torch.ops':module}
        manifest={**self.manifest,'files':[*self.manifest['files'],{'path':'packages/torch/_ops.py'}]}
        paths=[str(self.root/manifest['launch'][key]) for key in ('stdlib','dynload','packages')]
        def check():
            with patch.object(sys,'modules',modules),patch.object(sys,'path',paths):
                return custody._cpu_origins(manifest,self.descriptor,'/captured/bootstrap.py')
        self.assertEqual(check()['torch.ops']['defining_path'],defining.__file__)
        modules['other.ops']=modules.pop('torch.ops')
        with self.assertRaises(custody.ProcessError):check()
        modules['torch.ops']=modules.pop('other.ops')
        modules['torch.ops']=types.ModuleType('torch.ops');modules['torch.ops'].__file__='_ops.py'
        with self.assertRaises(custody.ProcessError):check()
        modules['torch.ops']=module;module.__file__='other.py'
        with self.assertRaises(custody.ProcessError):check()
        module.__file__='_ops.py';defining.__file__='/outside/_ops.py'
        with self.assertRaises(custody.ProcessError):check()

    def test_canonical_roundtrip_without_live_packages(self):
        self.assertEqual(custody.validate_cpu_snapshot_descriptor(self.descriptor),self.descriptor)
        self.assertEqual(custody.verify_cpu_snapshot(self.descriptor),self.manifest)

    def test_pure_bounds_paths_modes_and_descriptor_binding(self):
        import copy
        for field,value in [('file_count',40001),('total_bytes',custody.CPU_TOTAL_LIMIT+1),
                            ('manifest_bytes',True),('root',str(self.base/'elsewhere')),('catalog_id','x')]:
            altered=copy.deepcopy(self.descriptor);altered[field]=value
            with self.subTest(field=field),self.assertRaises(custody.ProcessError):custody.validate_cpu_snapshot_descriptor(altered)
        for field,value in [('path','../escape'),('mode',0o777),('bytes',custody.CPU_FILE_LIMIT+1),('kind','symlink')]:
            altered=copy.deepcopy(self.manifest);altered['files'][0][field]=value
            with self.subTest(field=field),self.assertRaises(custody.ProcessError):custody.validate_cpu_manifest(altered)
        altered=copy.deepcopy(self.manifest);altered['launch']['library_dirs']=['system/lib:/usr/lib']
        with self.assertRaises(custody.ProcessError):custody.validate_cpu_manifest(altered)
        altered=copy.deepcopy(self.descriptor);altered['packages']['numpy']='changed'
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(altered)

    def test_mutated_bytes_mode_missing_and_unlisted_refused(self):
        target=self.root/'packages/numpy/__init__.py';raw=target.read_bytes()
        target.chmod(0o600);target.write_bytes(b'X'*len(raw));target.chmod(0o400)
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)
        target.chmod(0o600);target.write_bytes(raw)
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)
        target.chmod(0o400);extra=self.root/'packages/unauthorized.py';extra.write_text('raise RuntimeError()')
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)
        extra.unlink();target.unlink()
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)

    def test_symlink_and_hardlink_file_custody_refused(self):
        target=self.root/'packages/numpy/__init__.py';raw=target.read_bytes();target.unlink()
        outside=self.base/'outside';outside.write_bytes(raw);outside.chmod(0o400);target.symlink_to(outside)
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)
        target.unlink();os.link(outside,target)
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)

    def test_manifest_change_and_kind_mismatch_refused(self):
        target=self.root/'manifest.json';target.chmod(0o600);target.write_bytes(target.read_bytes()+b'\n');target.chmod(0o400)
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)

    def cpu_spec(self):
        executable=str(Path('/usr/bin/python3').resolve())
        (self.base/'source').mkdir(exist_ok=True);(self.base/'runtime-bootstrap').mkdir(exist_ok=True)
        entry=self.base/'source/recipe.py';entry.write_text('pass\n')
        bootstrap=self.base/'runtime-bootstrap/recipe_process.py';bootstrap.write_bytes(custody.SOURCE)
        descriptor=self.base/'runtime-bootstrap/snapshot.json';descriptor.write_bytes(custody.encoded(self.descriptor))
        spec={'schema_version':1,'attempt_id':'b'*32,'request_sha256':'c'*64,
            'argv':[executable,'-I','-S','-B',str(bootstrap),'--cpu-launch',str(descriptor),str(entry)],
            'env':{},'cwd':str(self.base),'stdin_base64':'','wall_seconds':5,'executable_sha256':custody.digest(Path(executable).read_bytes()),
            'max_output_bytes':1024,'output_dir':str(self.base),'runtime_files':[],
            'trusted_install_owner_uid':os.stat('/usr').st_uid,'native_loader_policy':'glibc_x86_64_no_preload_v1',
            'cpu_snapshot':self.descriptor,'captured_files':[{'path':str(path),'bytes':path.stat().st_size,'sha256':custody.digest(path.read_bytes())} for path in (bootstrap,descriptor,entry)]}
        return spec

    def test_large_resource_profile_requires_full_cpu_identity_and_keeps_input_bounds(self):
        import copy
        spec=self.cpu_spec()
        large=dict(spec,resource_profile=custody.LARGE_OUTPUT_PROFILE,wall_seconds=2400,
                   max_output_bytes=4*1024*1024*1024)
        self.assertEqual(custody.validate_spec(large),large)
        for change in ({'wall_seconds':2401},{'max_output_bytes':4*1024*1024*1024+1},
                       {'resource_profile':'large'},{'resource_profile':None},{'wall_seconds':True}):
            with self.subTest(change=change),self.assertRaises(custody.ProcessError):
                custody.validate_spec(dict(large,**change))
        no_cpu=copy.deepcopy(large);del no_cpu['cpu_snapshot']
        with self.assertRaises(custody.ProcessError):custody.validate_spec(no_cpu)
        malformed=copy.deepcopy(large);malformed['cpu_snapshot']['manifest_sha256']='bad'
        with self.assertRaises(custody.ProcessError):custody.validate_spec(malformed)
        altered=copy.deepcopy(large);altered['captured_files'][1]['sha256']='d'*64
        with self.assertRaises(custody.ProcessError):custody.validate_spec(altered)
        for change in ({'wall_seconds':601},{'max_output_bytes':64*1024*1024+1}):
            with self.subTest(legacy=change),self.assertRaises(custody.ProcessError):
                custody.validate_spec(dict(spec,**change))
        large['captured_files'].append(dict(path=str(self.base/'input/oversize'),bytes=40*1024*1024+1,sha256='e'*64))
        with self.assertRaisesRegex(custody.ProcessError,'bounded named input'):custody.validate_spec(large)
        large['captured_files'].pop()
        large['captured_files'].append(dict(path=str(self.base/'source/oversize'),bytes=64*1024*1024+1,sha256='e'*64))
        with self.assertRaisesRegex(custody.ProcessError,'captured file size'):custody.validate_spec(large)

    def test_output_scan_tolerates_a_regular_file_renamed_after_listing(self):
        output=self.base/'rename-output';output.mkdir()
        profile=output/'profile.json';profile.write_bytes(b'original profile')
        spec={'output_dir':str(output),'max_output_bytes':32}
        original=Path.lstat
        def rename_then_stat(path):
            if path==profile:profile.rename(output/'training-profile.json')
            return original(path)
        with patch.object(Path,'lstat',rename_then_stat):custody._outputs(spec)
        custody._outputs(spec)
        (output/'training-profile.json').write_bytes(b'x'*33)
        with self.assertRaises(custody.ProcessError):custody._outputs(spec)

    def test_output_scan_does_not_ignore_other_observation_errors(self):
        output=self.base/'unreadable-output';output.mkdir()
        item=output/'result';item.write_bytes(b'x')
        original=Path.lstat
        def deny_file(path):
            if path==item:raise PermissionError('fixture observation denied')
            return original(path)
        with patch.object(Path,'lstat',deny_file),self.assertRaises(PermissionError):
            custody._outputs({'output_dir':str(output),'max_output_bytes':32})

    def test_large_output_scan_has_exact_file_total_and_count_bounds_without_large_writes(self):
        output=self.base/'large-output';output.mkdir()
        spec=dict(self.cpu_spec(),resource_profile=custody.LARGE_OUTPUT_PROFILE,
                  output_dir=str(output),max_output_bytes=4*1024*1024*1024)
        spec=custody.validate_spec(spec)
        for index in range(8):
            with (output/str(index)).open('wb') as stream:stream.truncate(512*1024*1024)
        custody._outputs(spec)
        (output/'extra').write_bytes(b'x')
        with self.assertRaises(custody.ProcessError):custody._outputs(spec)
        (output/'extra').unlink()
        for path in output.iterdir():path.unlink()
        with (output/'too-big').open('wb') as stream:stream.truncate(512*1024*1024+1)
        with self.assertRaises(custody.ProcessError):custody._outputs(spec)
        (output/'too-big').unlink()
        for index in range(96):(output/str(index)).touch()
        custody._outputs(spec)
        (output/'97').touch()
        with self.assertRaises(custody.ProcessError):custody._outputs(spec)
        for path in output.iterdir():path.unlink()
        (output/'link').symlink_to(self.base/'source/recipe.py')
        with self.assertRaises(custody.ProcessError):custody._outputs(spec)

    def test_cpu_capture_and_input_bounds_are_profile_specific(self):
        import copy
        spec=self.cpu_spec()
        for index in range(6):
            spec['captured_files'].append(dict(path=str(self.base/'input'/str(index)),bytes=40*1024*1024,sha256='d'*64))
        self.assertEqual(custody.validate_spec(spec),spec)
        over=copy.deepcopy(spec)
        over['captured_files'].append(dict(path=str(self.base/'input/extra'),bytes=17*1024*1024,sha256='e'*64))
        with self.assertRaisesRegex(custody.ProcessError,'input aggregate'):custody.validate_spec(over)
        for path in ('input/nested/file','outside/file'):
            bad=copy.deepcopy(spec);bad['captured_files'][3]['path']=str(self.base/path)
            with self.assertRaises(custody.ProcessError):custody.validate_spec(bad)
        over=copy.deepcopy(spec)
        over['captured_files'].extend(dict(path=str(self.base/'source'/str(index)),bytes=40*1024*1024,sha256='f'*64) for index in range(3))
        with self.assertRaisesRegex(custody.ProcessError,'closure exceeds'):custody.validate_spec(over)
        legacy=copy.deepcopy(spec);del legacy['cpu_snapshot']
        with self.assertRaisesRegex(custody.ProcessError,'closure exceeds'):custody.validate_spec(legacy)
        invalid=copy.deepcopy(spec);invalid['cpu_snapshot']['profile']='invented'
        with self.assertRaises(custody.ProcessError):custody.validate_spec(invalid)

    def test_cpu_exact_aggregate_boundaries_and_per_input_limit(self):
        spec=self.cpu_spec()
        for index in range(7):
            spec['captured_files'].append(dict(path=str(self.base/'input'/str(index)),
                bytes=(40 if index<6 else 16)*1024*1024,sha256='d'*64))
        remaining=320*1024*1024-sum(row['bytes'] for row in spec['captured_files'])
        spec['captured_files'].append(dict(path=str(self.base/'source/filler'),bytes=remaining,sha256='e'*64))
        self.assertEqual(custody.validate_spec(spec),spec)
        spec['captured_files'][-1]['bytes']+=1
        with self.assertRaisesRegex(custody.ProcessError,'closure exceeds'):custody.validate_spec(spec)
        spec['captured_files'][-1]['bytes']-=1
        spec['captured_files'][3]['bytes']+=1
        with self.assertRaisesRegex(custody.ProcessError,'bounded named input'):custody.validate_spec(spec)

    def test_cpu_launch_vector_requires_bound_descriptor(self):
        spec=self.cpu_spec()
        self.assertEqual(custody.validate_spec(spec),spec)
        spec['captured_files'][1]['sha256']='d'*64
        with self.assertRaises(custody.ProcessError):custody.validate_spec(spec)

    def test_directory_and_preparation_budget_are_bounded(self):
        (self.root/'empty-unlisted').mkdir()
        with self.assertRaises(custody.ProcessError):custody.verify_cpu_snapshot(self.descriptor)
        (self.root/'empty-unlisted').rmdir()
        with patch.object(custody.time,'monotonic',side_effect=[0,61]):
            with self.assertRaisesRegex(custody.ProcessError,'deadline'):
                custody.verify_cpu_snapshot(self.descriptor)
        import copy
        altered=copy.deepcopy(self.manifest)
        altered['files'][0]['path']='/'.join(['deep']*33)
        with self.assertRaises(custody.ProcessError):custody.validate_cpu_manifest(altered)

    def test_cancel_during_delayed_go_verification_drains_before_fork(self):
        # Fault-injected verification latency, real helper/control/drain. The tiny
        # authored ELF files never execute and do not qualify a CPU runtime.
        injected=b"""
_original_verify_cpu_snapshot = verify_cpu_snapshot
def verify_cpu_snapshot(descriptor, *, checkpoint=None):
    if checkpoint is not None:
        (Path(descriptor['root']).parent.parent/'verification-entered').write_text('entered')
        for _ in range(500):
            checkpoint()
            time.sleep(.01)
    return _original_verify_cpu_snapshot(descriptor, checkpoint=checkpoint)

"""
        source=custody.SOURCE.replace(b"if __name__=='__main__':",injected+b"if __name__=='__main__':")
        with patch.object(custody,'SOURCE',source):
            handle=custody.launch(self.cpu_spec(),self.base/'custody')
        try:
            deadline=time.monotonic()+8
            while not handle.ready and time.monotonic()<deadline:
                handle.poll();time.sleep(.01)
            self.assertIsNotNone(handle.ready);handle.go(handle.ready)
            while not (self.base/'verification-entered').exists() and time.monotonic()<deadline:
                handle.poll();time.sleep(.01)
            self.assertTrue((self.base/'verification-entered').exists())
            handle.cancel();events=[]
            while not handle.terminal and time.monotonic()<deadline:
                events.extend(handle.poll());time.sleep(.01)
            self.assertTrue(handle.terminal)
            self.assertFalse(any(event['type']=='started' for event in events))
            receipt=custody.load_receipt(handle.directory/'receipt.json',handle.expected_identity)
            self.assertEqual(receipt['outcome'],'cancelled');self.assertTrue(receipt['drained'])
            self.assertIsNone(receipt['leader_returncode']);self.assertTrue(receipt['go_received'])
        finally:
            handle.close_control()

    def test_cpu_launch_environment_is_fresh_unicode_capable_and_locale_closed(self):
        descriptor=self.base/'snapshot.json';descriptor.write_bytes(custody.encoded(self.descriptor))
        with patch.dict(os.environ,{'LD_PRELOAD':'host.so','PYTHONPATH':'/host','UNKNOWN_OVERRIDE':'x'},clear=True):
            with patch.object(custody.os,'execve') as execute:
                custody._cpu_launch_runtime(str(descriptor),str(self.base/'recipe-λ.py'),['λ'])
        executable,argv,env=execute.call_args.args
        self.assertEqual(env,{'LANG':'C','LC_ALL':'C','PYTHONCOERCECLOCALE':'0','PYTHONUTF8':'1',
            'PYTHONHOME':str(self.root/'python'),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''})
        self.assertEqual(executable,str(self.root/self.manifest['launch']['loader']))
        self.assertEqual(argv[-2:],[str(self.base/'recipe-λ.py'),'λ'])
