"""Actual finite native custody with synthetic stdlib workers, never ML work."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch
import uuid
import venv

import project_native_process as native
import recipe_process as custody


WORKER = textwrap.dedent('''\
    import argparse,ctypes,hashlib,json,os,signal,sys,time
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('--model-aware',action='store_true')
    parser.add_argument('--job')
    parser.add_argument('--verify-evidence')
    args=parser.parse_args()
    if args.probe:
        print(json.dumps({'available':True,'model_aware':args.model_aware,
            'secret_present': 'NATIVE_FIXTURE_SECRET' in os.environ}),flush=True)
    else:
        path=Path(args.verify_evidence or args.job)
        job=json.loads(path.read_bytes())
        assert job['parent_pid']==os.getppid() and job['parent_pid']>1
        assert ctypes.CDLL(None).prctl(1,signal.SIGKILL,0,0,0)==0
        assert job['parent_pid']==os.getppid()
        root=Path(job['output_dir'])
        if job.get('mode')=='escape':
            child=os.fork()
            if child==0:
                os.setsid();child=os.fork()
                if child:os._exit(0)
                os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN)
                (root/'escaped.pid').write_text(str(os.getpid()))
                time.sleep(30);os._exit(0)
            os.waitpid(child,0);time.sleep(30)
        else:
            phase='verify' if args.verify_evidence else 'train'
            (root/(phase+'.json')).write_text(json.dumps({'parent_pid':os.getppid(),
                'job_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'text':job['text']}))
            print(json.dumps({'phase':phase}),flush=True)
    ''').encode()


class NativeProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-native-process-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.handles=[]
        self.addCleanup(self.drain)
        executable=str(Path('/usr/bin/python3').resolve())
        raw=Path(executable).read_bytes()
        self.runtime=dict(executable=executable,executable_sha256=hashlib.sha256(raw).hexdigest(),
            trusted_install_owner_uid=os.stat('/usr').st_uid,
            files={executable:dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))})

    def drain(self):
        for handle in reversed(self.handles):
            handle.close_control()

    def prepare(self,phase='train',*,mode='complete',output=None,sources=None):
        stage=self.root/(phase+'-'+uuid.uuid4().hex)
        job=None if phase=='probe' else dict(parent_pid=1,output_dir=str(output or stage/'output'),
                                             mode=mode,text='exact Unicode 山')
        return native.prepare(stage,phase=phase,attempt_id=uuid.uuid4().hex,request_sha256='a'*64,
            runtime=self.runtime,worker='text_training.py',sources=sources or {'text_training.py':WORKER},
            job=job,model_aware=True,wall_seconds=8,max_output_bytes=16384)

    def until(self,handle,predicate,*,event_type=None,timeout=10):
        deadline=time.monotonic()+timeout;events=[]
        while time.monotonic()<deadline:
            events.extend(handle.poll())
            if predicate() and (event_type is None or any(row['type']==event_type for row in events)):
                return events
            time.sleep(.01)
        self.fail('Native fixture did not observe its exact custody condition: '+repr(events))

    def launch(self,prepared):
        handle=prepared.launch(prepared.stage/'custody');self.handles.append(handle)
        self.until(handle,lambda:handle.ready is not None)
        self.assertFalse(handle.sent_go)
        return handle

    def finish(self,prepared,handle):
        self.until(handle,lambda:handle.terminal or handle.lost)
        handle.process.wait(timeout=2)
        return prepared.evidence(handle)

    def test_real_train_and_verifier_create_new_parent_bound_evidence_without_rewriting_template(self):
        train=self.prepare();template=train.template
        self.assertEqual(json.loads(template)['job']['parent_pid'],1)
        handle=self.launch(train)
        self.assertFalse((train.stage/'effective-job.json').exists())
        handle.go(handle.ready);proof=self.finish(train,handle)
        self.assertTrue(proof['receipt']['drained']);self.assertEqual(proof['receipt']['outcome'],'completed')
        self.assertEqual((train.stage/'native-job-template.json').read_bytes(),template)
        job=json.loads(proof['effective_job']);observation=json.loads(proof['parent_observation'])
        self.assertEqual(job['parent_pid'],handle.ready['pid']);self.assertEqual(observation['helper'],handle.ready)
        self.assertEqual(json.loads((train.stage/'output/train.json').read_bytes())['text'],'exact Unicode 山')
        verify=self.prepare('verify',output=train.stage/'output')
        verifier=self.launch(verify);verifier.go(verifier.ready)
        verified=self.finish(verify,verifier)
        self.assertEqual(verified['receipt']['outcome'],'completed')
        self.assertNotEqual(handle.expected_identity,verifier.expected_identity)
        self.assertEqual(json.loads(verified['effective_job'])['parent_pid'],verifier.ready['pid'])
        self.assertTrue((train.stage/'output/verify.json').exists())
        self.assertEqual(train.template,template)

    def test_real_probe_is_direct_bounded_and_has_no_ambient_credential_environment(self):
        with patch.dict(os.environ,{'NATIVE_FIXTURE_SECRET':'not-forwarded'}):
            prepared=self.prepare('probe');handle=self.launch(prepared)
        self.assertIn('--probe',prepared.spec['argv']);self.assertNotIn('native_process_bootstrap.py',prepared.spec['argv'])
        handle.go(handle.ready);proof=self.finish(prepared,handle)
        self.assertEqual(json.loads(proof['stdout']),dict(available=True,model_aware=True,secret_present=False))
        self.assertIsNone(proof['template']);self.assertIsNone(proof['effective_job'])

    def test_owner_acknowledgement_failure_sends_no_go_and_requires_real_drain_receipt(self):
        prepared=self.prepare();handle=self.launch(prepared)
        def owner_ack():raise OSError('Synthetic canonical fsync acknowledgement failure')
        with self.assertRaises(OSError):
            try:
                owner_ack()
                handle.go(handle.ready)
            finally:handle.close_control()
        proof=prepared.evidence(handle)
        self.assertFalse(proof['receipt']['go_received']);self.assertTrue(proof['receipt']['drained'])
        self.assertIsNone(proof['receipt']['leader_returncode']);self.assertIsNone(proof['effective_job'])
        self.assertFalse((prepared.stage/'output/train.json').exists())

    def test_owner_eof_after_go_drains_actual_escaped_descendant(self):
        prepared=self.prepare(mode='escape');handle=self.launch(prepared);handle.go(handle.ready)
        marker=prepared.stage/'output/escaped.pid'
        self.until(handle,marker.exists,event_type='started')
        child=int(marker.read_text());receipt=handle.close_control()
        self.assertTrue(receipt['drained']);self.assertEqual(receipt['outcome'],'cancelled')
        self.assertFalse(Path('/proc/'+str(child)).exists())
        proof=prepared.evidence(handle)
        self.assertIsNotNone(proof['effective_job']);self.assertEqual(proof['receipt'],receipt)

    def test_template_drift_refuses_launch_before_any_helper(self):
        prepared=self.prepare();template=prepared.stage/'native-job-template.json'
        template.chmod(0o600);template.write_bytes(prepared.template+b' ');template.chmod(0o400)
        with self.assertRaises(custody.ProcessError):prepared.launch(prepared.stage/'custody')
        self.assertFalse((prepared.stage/'custody').exists())

    def test_oversized_probe_stdout_keeps_drained_receipt_for_owner_protocol_refusal(self):
        prepared=self.prepare('probe',sources={'text_training.py':b'import os\nos.write(1,b"x"*32769)\n'})
        handle=self.launch(prepared);handle.go(handle.ready)
        self.until(handle,lambda:handle.terminal);handle.process.wait(timeout=2)
        proof=prepared.evidence(handle)
        self.assertEqual(proof['receipt']['outcome'],'completed');self.assertTrue(proof['receipt']['drained'])
        self.assertEqual(proof['stdout'],b'x'*32769)
        self.assertEqual(native.read_phase_evidence(prepared.stage,prepared.spec,phase='probe',helper=handle.ready),proof)
        self.assertEqual((handle.directory/'stdout.log').stat().st_size,32769)

    def test_invalid_identity_or_job_cannot_create_a_staging_directory(self):
        for delta in (dict(phase='arbitrary'),dict(worker='../../other.py'),dict(job={'parent_pid':7}),
                      dict(runtime={}),dict(sources={'../text_training.py':WORKER})):
            stage=self.root/uuid.uuid4().hex
            args=dict(phase='train',attempt_id=uuid.uuid4().hex,request_sha256='a'*64,runtime=self.runtime,
                      worker='text_training.py',sources={'text_training.py':WORKER},
                      job=dict(parent_pid=1,output_dir=str(stage/'output')))
            args.update(delta)
            with self.subTest(delta=tuple(delta)),self.assertRaises(custody.ProcessError):native.prepare(stage,**args)
            self.assertFalse(stage.exists())

    def helper_death_window(self,*,before_arm):
        libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
        self.assertEqual(libc.prctl(37,ctypes.byref(old),0,0,0),0)
        self.assertEqual(libc.prctl(36,1,0,0,0),0)
        marker=self.root/('before-arm.pid' if before_arm else 'before-bootstrap.pid')
        release=self.root/'release-child';descriptor=None;leader=None;handle=None
        try:
            if before_arm:
                needle=b'                    if leader==0:\n                        try:\n'
                self.assertEqual(custody.SOURCE.count(needle),1)
                pause=('                    if leader==0:\n'
                       '                        Path('+repr(str(marker))+').write_text(str(os.getpid()))\n'
                       '                        while not Path('+repr(str(release))+').exists(): time.sleep(.01)\n'
                       '                        try:\n').encode()
                prepared=self.prepare()
                with patch.object(custody,'SOURCE',custody.SOURCE.replace(needle,pause)):
                    handle=self.launch(prepared)
            else:
                delayed=self.root/'native_process_bootstrap.py'
                prefix=('import os,time\nfrom pathlib import Path\nPath('+repr(str(marker))+
                        ').write_text(str(os.getpid()))\ntime.sleep(30)\n').encode()
                delayed.write_bytes(prefix+native.BOOTSTRAP.read_bytes())
                with patch.object(native,'BOOTSTRAP',delayed):prepared=self.prepare()
                handle=self.launch(prepared)
            template=prepared.template;handle.go(handle.ready)
            self.until(handle,marker.exists,event_type='started')
            leader=int(marker.read_text());descriptor=os.pidfd_open(leader)
            handle.process.kill();handle.process.wait(timeout=2)
            if before_arm:release.write_text('qualified helper is already dead')
            poll=select.poll();poll.register(descriptor,select.POLLIN)
            self.assertTrue(poll.poll(3000),'Leader survived death of its qualified helper')
            os.waitpid(leader,0);leader=None
            receipt=handle.close_control()
            self.assertFalse(receipt['drained']);self.assertEqual(receipt['outcome'],'unknown')
            with self.assertRaises(custody.ProcessError) as unavailable:prepared.evidence(handle)
            self.assertEqual(unavailable.exception.code,'unknown')
            self.assertFalse((prepared.stage/'effective-job.json').exists())
            self.assertFalse((prepared.stage/'output/train.json').exists())
            self.assertEqual((prepared.stage/'native-job-template.json').read_bytes(),template)
        finally:
            if descriptor is not None:
                if leader is not None:
                    try:signal.pidfd_send_signal(descriptor,signal.SIGKILL)
                    except ProcessLookupError:pass
                    try:os.waitpid(leader,0)
                    except ChildProcessError:pass
                os.close(descriptor)
            if handle is not None and handle.process.poll() is None:handle.close_control()
            libc.prctl(36,old.value,0,0,0)

    def test_real_helper_death_before_leader_arms_parent_signal_cannot_execute(self):
        self.helper_death_window(before_arm=True)

    def test_real_helper_death_after_exec_before_bootstrap_cannot_adopt_reaper_parent(self):
        self.helper_death_window(before_arm=False)

    def configured_venv(self):
        root=self.root/'configured-venv'
        venv.EnvBuilder(with_pip=False,symlinks=True).create(root)
        packages=root/'lib'/('python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor))/'site-packages'
        packages.mkdir(parents=True,exist_ok=True)
        (packages/'native_fixture_dependency.py').write_text('VALUE="explicit configured venv package"\n')
        executable=str(root/'bin/python')
        self.assertTrue(Path(executable).is_symlink(),'Exercise the actual configured venv alias')
        return root,executable

    def test_real_configured_venv_alias_preserves_prefix_and_installed_module_under_sealed_exec(self):
        root,executable=self.configured_venv()
        runtime=native.current_runtime(executable)
        self.assertEqual(runtime['executable'],executable)
        self.assertNotEqual(runtime['executable_source'],executable)
        self.assertIn(str(root/'pyvenv.cfg'),runtime['files'])
        source=textwrap.dedent('''\
            import json,os,sys
            from pathlib import Path
            import native_fixture_dependency as dependency
            result={'prefix':sys.prefix,'executable':sys.executable,'value':dependency.VALUE,
                    'module':dependency.__file__}
            if '--job' in sys.argv:
                job=json.loads(Path(sys.argv[-1]).read_bytes())
                assert job['parent_pid']==os.getppid()>1
                Path(job['output_dir'],'venv.json').write_text(json.dumps(result))
            print(json.dumps(result),flush=True)
            ''').encode()
        for phase in ('probe','train'):
            stage=self.root/('venv-'+phase)
            prepared=native.prepare(stage,phase=phase,attempt_id=uuid.uuid4().hex,request_sha256='b'*64,
                runtime=runtime,worker='text_training.py',sources={'text_training.py':source},
                job=None if phase=='probe' else dict(parent_pid=1,output_dir=str(stage/'output')),
                wall_seconds=8,max_output_bytes=16384)
            self.assertEqual(prepared.spec['argv'][0],executable)
            handle=self.launch(prepared);prepared.check_current_runtime();handle.go(handle.ready)
            proof=self.finish(prepared,handle);result=json.loads(proof['stdout'])
            self.assertEqual(proof['receipt']['outcome'],'completed',proof)
            self.assertEqual(result['prefix'],str(root));self.assertEqual(result['executable'],executable)
            self.assertEqual(result['value'],'explicit configured venv package')
            self.assertTrue(Path(result['module']).is_relative_to(root))
            if phase=='train':
                self.assertEqual(json.loads((stage/'output/venv.json').read_bytes()),result)

    def test_verified_executable_fd_rejects_wrong_bytes_without_closing_or_repositioning_callers_fd(self):
        prepared=self.prepare();wrong=self.root/'wrong-executable';wrong.write_bytes(b'not the qualified interpreter')
        descriptor=os.open(wrong,os.O_RDONLY)
        try:
            os.lseek(descriptor,7,os.SEEK_SET)
            with self.assertRaises(custody.ProcessError) as error:
                custody.launch(prepared.spec,prepared.stage/'custody',executable_fd=descriptor)
            self.assertEqual(error.exception.code,'stale')
            self.assertEqual(os.lseek(descriptor,0,os.SEEK_CUR),7)
            self.assertTrue(os.fstat(descriptor))
            self.assertFalse((prepared.stage/'custody').exists())
        finally:os.close(descriptor)

    def test_current_venv_config_drift_before_go_prevents_dispatch_and_still_drains(self):
        root,executable=self.configured_venv();runtime=native.current_runtime(executable)
        stage=self.root/'venv-drift'
        prepared=native.prepare(stage,phase='probe',attempt_id=uuid.uuid4().hex,request_sha256='c'*64,
            runtime=runtime,worker='text_training.py',sources={'text_training.py':WORKER},wall_seconds=8)
        handle=self.launch(prepared)
        with (root/'pyvenv.cfg').open('a') as output:output.write('\n# changed after READY\n')
        with self.assertRaises(custody.ProcessError) as error:
            try:
                prepared.check_current_runtime()
                handle.go(handle.ready)
            finally:handle.close_control()
        self.assertEqual(error.exception.code,'stale')
        proof=prepared.evidence(handle)
        self.assertFalse(proof['receipt']['go_received']);self.assertTrue(proof['receipt']['drained'])

    def test_current_interpreter_alias_drift_before_launch_cannot_select_another_interpreter(self):
        root,executable=self.configured_venv();runtime=native.current_runtime(executable)
        stage=self.root/'venv-alias-drift'
        prepared=native.prepare(stage,phase='probe',attempt_id=uuid.uuid4().hex,request_sha256='d'*64,
            runtime=runtime,worker='text_training.py',sources={'text_training.py':WORKER},wall_seconds=8)
        Path(executable).unlink();Path(executable).symlink_to(Path('/usr/bin/python3').resolve())
        with self.assertRaises(custody.ProcessError) as error:prepared.launch(stage/'custody')
        self.assertEqual(error.exception.code,'stale');self.assertFalse((stage/'custody').exists())

    def test_spawn_callback_is_not_reached_for_current_config_alias_or_capture_refusal(self):
        root,executable=self.configured_venv();runtime=native.current_runtime(executable)
        stage=self.root/'spawn-validation'
        prepared=native.prepare(stage,phase='probe',attempt_id=uuid.uuid4().hex,request_sha256='f'*64,
            runtime=runtime,worker='text_training.py',sources={'text_training.py':WORKER},wall_seconds=8)
        configuration=root/'pyvenv.cfg';original=configuration.read_bytes()
        marker={'never_launched'};calls=[]
        def before_spawn():
            calls.append('spawn');marker.discard('never_launched')
        with patch.object(custody.subprocess,'Popen',side_effect=AssertionError('Validation must precede Popen')) as spawn:
            configuration.write_bytes(original+b'\n# changed before launch\n')
            with self.assertRaises(custody.ProcessError):
                prepared.launch(stage/'custody',_before_spawn=before_spawn)
            configuration.write_bytes(original)
            Path(executable).unlink();Path(executable).symlink_to('/unavailable-native-interpreter')
            with self.assertRaises((OSError,custody.ProcessError)):
                prepared.launch(stage/'custody',_before_spawn=before_spawn)
            captured=self.prepare('probe');source=captured.stage/'source/text_training.py'
            source.chmod(0o600);source.write_bytes(WORKER+b'\n# changed capture\n');source.chmod(0o400)
            with self.assertRaises(custody.ProcessError):
                captured.launch(captured.stage/'custody',_before_spawn=before_spawn)
            spawn.assert_not_called()
        self.assertEqual(calls,[]);self.assertEqual(marker,{'never_launched'})

    def test_real_spawn_callback_runs_once_immediately_before_popen_without_sending_go(self):
        prepared=self.prepare('probe');events=[];marker={'never_launched'}
        actual_popen=custody.subprocess.Popen
        def before_spawn():
            events.append('callback');marker.discard('never_launched')
        def spawn(*args,**kwargs):
            self.assertEqual(events,['callback']);self.assertEqual(marker,set())
            events.append('popen')
            return actual_popen(*args,**kwargs)
        with patch.object(custody.subprocess,'Popen',side_effect=spawn):
            handle=prepared.launch(prepared.stage/'custody',_before_spawn=before_spawn)
        self.handles.append(handle);self.until(handle,lambda:handle.ready is not None)
        self.assertEqual(events,['callback','popen']);self.assertFalse(handle.sent_go)
        receipt=handle.close_control()
        self.assertTrue(receipt['drained']);self.assertFalse(receipt['go_received'])

    def test_popen_entry_failure_cannot_reinstate_never_launched_proof(self):
        prepared=self.prepare('probe');marker={'never_launched'};events=[]
        def before_spawn():
            events.append('callback');marker.discard('never_launched')
        def fail_spawn(*args,**kwargs):
            self.assertEqual(events,['callback']);self.assertEqual(marker,set())
            events.append('popen');raise OSError('Synthetic failure after entering Popen')
        with patch.object(custody.subprocess,'Popen',side_effect=fail_spawn):
            with self.assertRaisesRegex(OSError,'after entering Popen'):
                prepared.launch(prepared.stage/'custody',_before_spawn=before_spawn)
        self.assertEqual(events,['callback','popen']);self.assertEqual(marker,set())

    def test_post_spawn_handle_failure_cannot_reinstate_never_launched_proof(self):
        prepared=self.prepare('probe');marker={'never_launched'};processes=[]
        actual_popen=custody.subprocess.Popen
        def before_spawn():marker.discard('never_launched')
        def spawn(*args,**kwargs):
            process=actual_popen(*args,**kwargs);processes.append(process);return process
        with (patch.object(custody.subprocess,'Popen',side_effect=spawn),
              patch.object(custody,'Handle',side_effect=OSError('Synthetic post-spawn Handle failure'))):
            with self.assertRaisesRegex(OSError,'post-spawn Handle failure'):
                prepared.launch(prepared.stage/'custody',_before_spawn=before_spawn)
        self.assertEqual(marker,set());self.assertEqual(len(processes),1)
        # Owner control closes on failure. Even if the helper exits, no Handle /
        # READY identity exists to assert an acknowledged drain for this owner.
        processes[0].wait(timeout=custody.CLEANUP_SECONDS+2)

    def test_retained_spec_grammar_does_not_mistake_original_uid_for_current_permission(self):
        prepared=self.prepare();spec=prepared.spec;raw=custody.encoded(spec)
        with patch.object(custody.os,'getuid',return_value=spec['trusted_install_owner_uid']):
            with self.assertRaises(custody.ProcessError):custody.validate_spec(spec)
            retained=custody.decode_retained_spec(spec)
            checked=native.validate_prepared_spec(spec,phase='train',worker='text_training.py')
        self.assertEqual(custody.encoded(retained),raw);self.assertEqual(custody.encoded(checked),raw)
        for change in (dict(argv=[spec['argv'][0],'-c','print("unclassified")']),dict(env={'PYTHONPATH':'/outside'}),
                       dict(wall_seconds=601),dict(schema_version=True)):
            with self.subTest(change=tuple(change)),self.assertRaises(custody.ProcessError):
                native.validate_prepared_spec(dict(spec,**change),phase='train',worker='text_training.py')

    def test_pure_current_runtime_decoder_rejects_unclassified_observed_files(self):
        runtime=native.current_runtime(str(Path('/usr/bin/python3')))
        self.assertEqual(native.validate_current_runtime(runtime),runtime)
        outside=dict(runtime,files={**runtime['files'],'/arbitrary/file':{'sha256':'e'*64,'bytes':1}})
        with self.assertRaises(custody.ProcessError):native.validate_current_runtime(outside)

    def test_original_phase_reader_reuses_exact_live_evidence_without_runtime_or_process_authority(self):
        prepared=self.prepare();handle=self.launch(prepared);handle.go(handle.ready)
        live=self.finish(prepared,handle);handle.close_control()
        with (patch.object(custody,'launch',side_effect=AssertionError('No launch from original evidence')),
              patch.object(custody,'identity',side_effect=AssertionError('No current process lookup')),
              patch.object(native,'current_runtime',side_effect=AssertionError('No runtime lookup'))):
            original=native.read_phase_evidence(prepared.stage,prepared.spec,phase='train',helper=handle.ready)
        self.assertEqual(original,live)
        self.assertEqual(set(original),{'receipt','stdout','stderr','template','effective_job','parent_observation'})
        self.assertEqual(original['template'],prepared.template)

    def test_original_phase_reader_refuses_wrong_physical_stage_spec_helper_and_template(self):
        prepared=self.prepare();handle=self.launch(prepared);handle.go(handle.ready)
        self.finish(prepared,handle)
        wrong_helper={**handle.ready,'pid':handle.ready['pid']+1000000}
        for stage,spec,helper in ((self.root/'other-physical-stage',prepared.spec,handle.ready),
                                  (prepared.stage,dict(prepared.spec,wall_seconds=7),handle.ready),
                                  (prepared.stage,prepared.spec,wrong_helper)):
            with self.subTest(stage=str(stage),helper=helper['pid']),self.assertRaises(custody.ProcessError):
                native.read_phase_evidence(stage,spec,phase='train',helper=helper)
        template=prepared.stage/'native-job-template.json'
        template.chmod(0o600);template.write_bytes(prepared.template+b' ');template.chmod(0o400)
        with self.assertRaises(custody.ProcessError):
            native.read_phase_evidence(prepared.stage,prepared.spec,phase='train',helper=handle.ready)

    def test_original_phase_reader_preserves_real_failed_receipt_before_effective_job_exists(self):
        stopped=self.root/'native_process_bootstrap.py'
        stopped.write_bytes(b'raise SystemExit(17)\n')
        with patch.object(native,'BOOTSTRAP',stopped):prepared=self.prepare()
        handle=self.launch(prepared);handle.go(handle.ready)
        self.until(handle,lambda:handle.terminal);handle.process.wait(timeout=2)
        original=native.read_phase_evidence(prepared.stage,prepared.spec,phase='train',helper=handle.ready)
        self.assertTrue(original['receipt']['go_received']);self.assertTrue(original['receipt']['drained'])
        self.assertEqual(original['receipt']['outcome'],'failed')
        self.assertEqual(original['receipt']['leader_returncode'],17)
        self.assertEqual(original['template'],prepared.template)
        self.assertIsNone(original['effective_job']);self.assertIsNone(original['parent_observation'])

    def test_original_phase_reader_rejects_aliased_or_changed_evidence_bytes(self):
        prepared=self.prepare();handle=self.launch(prepared);handle.go(handle.ready)
        self.finish(prepared,handle)
        observation=prepared.stage/'native-parent-observation.json'
        alias=self.root/'evidence-hardlink';os.link(observation,alias)
        with self.assertRaises(custody.ProcessError):
            native.read_phase_evidence(prepared.stage,prepared.spec,phase='train',helper=handle.ready)
        alias.unlink()
        log=handle.directory/'stdout.log';log.write_bytes(log.read_bytes()+b'unacknowledged change')
        with self.assertRaises(custody.ProcessError):
            native.read_phase_evidence(prepared.stage,prepared.spec,phase='train',helper=handle.ready)

    def test_original_phase_reader_cannot_normalize_changed_raw_receipt_bytes(self):
        prepared=self.prepare();handle=self.launch(prepared);handle.go(handle.ready)
        self.finish(prepared,handle)
        receipt=handle.directory/'receipt.json';receipt.write_bytes(receipt.read_bytes()+b'\n')
        with self.assertRaises(custody.ProcessError) as error:
            native.read_phase_evidence(prepared.stage,prepared.spec,phase='train',helper=handle.ready)
        self.assertEqual(error.exception.code,'unknown')

    def pure_job_proof(self):
        prepared=self.prepare();helper=custody.identity(os.getpid())
        template=prepared.template;frame=custody.decode(template)
        effective=custody.encoded(dict(frame['job'],parent_pid=helper['pid']))
        observation=custody.encoded(dict(format='native_parent_observation_v1',
            attempt_id=prepared.spec['attempt_id'],request_sha256=prepared.spec['request_sha256'],
            template_sha256=hashlib.sha256(template).hexdigest(),
            effective_job_sha256=hashlib.sha256(effective).hexdigest(),helper=helper))
        receipt=dict(schema_version=1,attempt_id=prepared.spec['attempt_id'],
            request_sha256=prepared.spec['request_sha256'],
            spec_sha256=hashlib.sha256(custody.encoded(prepared.spec)).hexdigest(),helper=helper,
            go_received=True,spawn_closed=True,drained=True,echild=True,outcome='completed',reason='exited',
            leader_returncode=0,streams={name:dict(bytes=0,sha256=hashlib.sha256(b'').hexdigest()) for name in ('stdout','stderr')})
        return prepared,dict(phase='train',helper=helper,template=template,effective_job=effective,
                             parent_observation=observation,receipt=receipt)

    def test_inline_job_proof_is_pure_and_rejects_tampered_binding_or_effective_job(self):
        prepared,proof=self.pure_job_proof()
        with (patch.object(native.os,'open',side_effect=AssertionError('Inline proof never opens a path')),
              patch.object(custody,'identity',side_effect=AssertionError('Inline proof never resolves a PID')),
              patch.object(custody,'launch',side_effect=AssertionError('Inline proof never launches')),
              patch.object(native,'current_runtime',side_effect=AssertionError('Inline proof never resolves runtime'))):
            accepted=native.validate_job_evidence(prepared.spec,**proof)
            self.assertEqual(accepted,{key:proof[key] for key in ('receipt','template','effective_job','parent_observation')})
            wrong_job=custody.decode(proof['effective_job']);wrong_job['parent_pid']+=1
            wrong_observation=custody.decode(proof['parent_observation']);wrong_observation['helper']['start_ticks']='0'
            frame=custody.decode(proof['template']);frame['job']['text']='silently rewritten source'
            for change in (dict(effective_job=custody.encoded(wrong_job)),
                           dict(parent_observation=custody.encoded(wrong_observation)),
                           dict(template=custody.encoded(frame)),
                           dict(receipt=dict(proof['receipt'],spec_sha256='0'*64)),
                           dict(effective_job=None,parent_observation=None),
                           dict(parent_observation=None),
                           dict(effective_job=b'x'*(native.TEMPLATE_LIMIT+1))):
                with self.subTest(change=tuple(change)),self.assertRaises(custody.ProcessError):
                    native.validate_job_evidence(prepared.spec,**{**proof,**change})

    def test_inline_failed_phase_preserves_absent_effective_job_without_fabrication(self):
        prepared,proof=self.pure_job_proof()
        proof.update(effective_job=None,parent_observation=None,
                     receipt=dict(proof['receipt'],outcome='failed',leader_returncode=17,reason='nonzero_exit'))
        with patch.object(native.os,'open',side_effect=AssertionError('No historical path reads')):
            accepted=native.validate_job_evidence(prepared.spec,**proof)
        self.assertIsNone(accepted['effective_job']);self.assertIsNone(accepted['parent_observation'])
        self.assertEqual(accepted['template'],prepared.template)


if __name__=='__main__':unittest.main()
