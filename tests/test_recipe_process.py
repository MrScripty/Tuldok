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
        self.assertFalse(receipt['go_received']);self.assertEqual(receipt['outcome'],'failed')
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
        self.assertFalse(receipt['go_received']);self.assertTrue(receipt['drained'])

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
