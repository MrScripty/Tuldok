"""Managed inventory custody using real helpers and authored nonexecutable assets.

These tests prove cancellable verification, refusal and cold receipts. They do
not qualify a Python installation, CUDA, optimizer work or real GPU cessation.
"""
import copy
import os
from pathlib import Path
import shlex
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import recipe_process as custody
import torch_runtime as runtime


class ManagedInventoryCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.python = self.root / 'installed/bin/python3.14'
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b'authored inventory fixture; never executable')
        (self.root / 'installed/lib/python3.14').mkdir(parents=True)
        site = self.root / 'packages'
        for name in ('torch', 'numpy'):
            path = site / (name + '-1.0.dist-info/METADATA')
            path.parent.mkdir(parents=True)
            path.write_bytes(b'Version: 1.0\n')
        self.manifest = runtime.inventory({'python': str(self.python),
            'python_root': str(self.root / 'installed'), 'site_packages': str(site)})
        raw = runtime.encoded(self.manifest)
        self.descriptor = dict(schema_version=1, profile=runtime.PROFILE, catalog_id='a'*32,
            manifest_sha256=runtime.sha(raw), manifest_bytes=len(raw),
            file_count=len(self.manifest['files']), total_bytes=self.manifest['total_bytes'])
        self.staging = self.root / 'attempt'
        (self.staging / 'runtime-bootstrap').mkdir(parents=True)
        (self.staging / 'source').mkdir()
        (self.staging / 'output').mkdir()
        self.entry = self.staging / 'source/recipe.py'
        self.entry.write_text("raise AssertionError('No fixture may enter the recipe')\n")
        self.bootstrap = self.staging / 'runtime-bootstrap/torch_runtime.py'
        self.bootstrap.write_bytes(Path(runtime.__file__).read_bytes())
        self.manifest_path = self.staging / 'runtime-bootstrap/torch-manifest.json'
        self.manifest_path.write_bytes(raw)
        self.handles = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for handle in self.handles:
            handle.close_control()
            self.assertIsNotNone(handle.process.poll(), 'Owned helper was not reaped')

    def spec(self, device='cuda'):
        executable = str(Path('/usr/bin/python3').resolve())
        return dict(schema_version=1, attempt_id=uuid.uuid4().hex, request_sha256='b'*64,
            argv=[executable, '-I', '-S', '-B', str(self.bootstrap), '--launch',
                  str(self.manifest_path), device, str(self.entry)],
            env={}, cwd=str(self.staging), stdin_base64='', wall_seconds=5,
            executable_sha256=custody.digest(Path(executable).read_bytes()),
            max_output_bytes=1024, output_dir=str(self.staging / 'output'), runtime_files=[],
            trusted_install_owner_uid=os.stat('/usr').st_uid, torch_runtime=self.descriptor,
            captured_files=[dict(path=str(path), bytes=path.stat().st_size,
                sha256=custody.digest(path.read_bytes())) for path in (self.bootstrap, self.manifest_path, self.entry)])

    def context_spec(self, device='cpu'):
        path = self.staging / custody.MODEL_CONTEXT_PATH
        if path.exists():
            path.chmod(0o600)
        path.write_bytes(custody.encoded({'fixture': 'host-owned context bytes'}))
        path.chmod(0o400)
        context = dict(path=str(path), bytes=path.stat().st_size,
                       sha256=custody.digest(path.read_bytes()))
        spec = self.spec(device)
        spec.update(schema_version=2, model_evidence_context=context)
        spec['captured_files'].append(context)
        spec['argv'].append(str(path))
        return spec

    def start(self, *, helper_source=None, spec=None):
        spec = spec or self.spec()
        with patch.object(custody, 'SOURCE', helper_source or custody.SOURCE):
            handle = custody.launch(spec, self.staging / ('custody-' + spec['attempt_id']))
        self.handles.append(handle)
        self.until(handle, lambda: handle.ready is not None)
        return handle

    def until(self, handle, predicate, timeout=8):
        events = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            events.extend(handle.poll())
            if predicate():
                return events
            time.sleep(.01)
        self.fail('Custody observation deadline: ' + repr(events))

    def finish(self, handle):
        events = self.until(handle, lambda: handle.terminal or handle.lost)
        handle.process.wait(timeout=2)
        receipt = custody.load_receipt(handle.directory / 'receipt.json', handle.expected_identity)
        self.assertTrue(receipt['drained'])
        self.assertTrue(receipt['echild'])
        self.assertIsNone(receipt['leader_returncode'])
        self.assertTrue(receipt['go_received'])
        self.assertFalse(any(event['type'] == 'started' for event in events))
        self.assertEqual(list((self.staging / 'output').iterdir()), [])
        return receipt

    def delay_inventory(self):
        # A captured authored bootstrap delays an actual asset read while keeping
        # the real inventory and per-chunk checkpoint. No fake control/drain path.
        marker = self.staging / 'hash-entered'
        injection = '''
import time
_original_file_record = file_record
def file_record(path, *, checkpoint=None):
    if checkpoint is not None:
        Path(MARKER).write_text('inventory asset verification entered')
        for _ in range(500):
            checkpoint()
            time.sleep(.01)
    return _original_file_record(path, checkpoint=checkpoint)

'''.replace('MARKER', repr(str(marker)))
        self.bootstrap.write_bytes(self.bootstrap.read_bytes().replace(
            b"if __name__=='__main__':", injection.encode() + b"if __name__=='__main__':"))
        return marker

    def test_exact_managed_spec_requires_one_profile_device_and_captured_identity(self):
        spec = self.spec()
        self.assertEqual(custody.validate_spec(spec), spec)
        for change in ({'env': {'CUDA_VISIBLE_DEVICES': ''}}, {'cpu_snapshot': {}},
                       {'resource_profile': custody.LARGE_OUTPUT_PROFILE},
                       {'wall_seconds': 601}, {'torch_runtime': dict(self.descriptor, extra=True)}):
            with self.subTest(change=change), self.assertRaises(custody.ProcessError):
                custody.validate_spec(dict(spec, **change))
        for index, value in ((7, 'auto'), (7, 'CPU'), (4, '/tmp/torch_runtime.py'),
                             (6, '/tmp/torch-manifest.json'), (8, '/tmp/recipe.py')):
            changed = copy.deepcopy(spec)
            changed['argv'][index] = value
            with self.subTest(index=index), self.assertRaises(custody.ProcessError):
                custody.validate_spec(changed)
        changed = copy.deepcopy(spec)
        changed['captured_files'][1]['sha256'] = 'f'*64
        with self.assertRaises(custody.ProcessError):
            custody.validate_spec(changed)

    def test_missing_or_changed_inventory_refused_after_go_without_child_or_cpu_retry(self):
        for mutation in ('missing', 'changed'):
            with self.subTest(mutation=mutation):
                handle = self.start()
                if mutation == 'missing':
                    self.python.unlink()
                else:
                    self.python.write_bytes(b'changed installed asset')
                handle.go(handle.ready)
                receipt = self.finish(handle)
                self.assertEqual(receipt['outcome'], 'failed')
                self.assertTrue(handle.verifying)
                self.assertEqual(handle.spec['argv'][7], 'cuda')
                self.python.write_bytes(b'authored inventory fixture; never executable')

    def test_cancel_during_inventory_drains_without_fork_and_retains_cold_identity(self):
        marker = self.delay_inventory()
        handle = self.start()
        handle.go(handle.ready)
        self.until(handle, marker.exists)
        self.assertTrue(handle.verifying)
        handle.cancel()
        receipt = self.finish(handle)
        self.assertEqual(receipt['outcome'], 'cancelled')
        raw = (handle.directory / 'receipt.json').read_bytes()
        with patch.object(runtime, 'verify', side_effect=AssertionError('Cold receipt read runtime')):
            self.assertEqual(custody.validate_receipt(raw, handle.expected_identity), receipt)
        with self.assertRaises(custody.ProcessError):
            handle.go(handle.ready)

    def test_captured_bootstrap_drift_after_ready_refuses_recipe_entry(self):
        handle = self.start()
        self.bootstrap.write_bytes(self.bootstrap.read_bytes() + b'\n# changed after approval\n')
        handle.go(handle.ready)
        receipt = self.finish(handle)
        self.assertEqual(receipt['outcome'], 'failed')
        self.assertFalse(handle.verifying, 'Captured bootstrap refusal must precede installed inventory')

    def test_controller_loss_during_inventory_drains_without_fork(self):
        marker = self.delay_inventory()
        handle = self.start()
        handle.go(handle.ready)
        self.until(handle, marker.exists)
        receipt = handle.close_control()
        self.assertTrue(receipt['drained'])
        self.assertEqual(receipt['outcome'], 'cancelled')
        self.assertEqual(receipt['reason'], 'controller_lost')
        self.assertIsNone(receipt['leader_returncode'])
        self.assertTrue(receipt['go_received'])

    def test_inventory_deadline_fails_and_drains_before_child_wall_clock(self):
        self.delay_inventory()
        # Only the authored helper's hash budget changes; production child wall
        # time remains independent and no actual Torch/GPU execution is claimed.
        source = custody.SOURCE.replace(b'TORCH_VERIFY_SECONDS = 60', b'TORCH_VERIFY_SECONDS = .1')
        self.assertNotEqual(source, custody.SOURCE)
        handle = self.start(helper_source=source)
        handle.go(handle.ready)
        receipt = self.finish(handle)
        self.assertEqual(receipt['outcome'], 'failed')
        self.assertEqual(receipt['reason'], 'verification_timeout')

    def test_managed_context_keeps_one_exact_bounded_captured_argument(self):
        for device in ('cpu', 'cuda'):
            with self.subTest(device=device):
                spec = self.context_spec(device)
                self.assertEqual(custody.validate_spec(spec), spec)
                custody.verify_model_context(spec)
        for mutation in ('no_runtime_profile', 'duplicate_arg', 'missing_arg', 'missing_capture', 'uncaptured_hash',
                         'wrong_path', 'empty', 'oversize'):
            spec = self.context_spec()
            context = spec['model_evidence_context']
            if mutation == 'no_runtime_profile': spec.pop('torch_runtime')
            elif mutation == 'duplicate_arg': spec['argv'].append(context['path'])
            elif mutation == 'missing_arg': spec['argv'].pop()
            elif mutation == 'missing_capture': spec['captured_files'].pop()
            elif mutation == 'uncaptured_hash': spec['model_evidence_context'] = dict(context, sha256='f'*64)
            elif mutation == 'wrong_path': context['path'] = str(self.staging / 'source/context.json')
            elif mutation == 'empty': context['bytes'] = 0
            else: context['bytes'] = custody.MODEL_CONTEXT_LIMIT + 1
            with self.subTest(mutation=mutation), self.assertRaises(custody.ProcessError):
                custody.validate_spec(spec)
        spec = self.context_spec()
        Path(spec['model_evidence_context']['path']).chmod(0o600)
        with self.assertRaisesRegex(custody.ProcessError, 'read-only'):
            custody.verify_model_context(spec)

    def test_managed_context_drift_after_ready_drains_without_recipe_entry(self):
        spec = self.context_spec()
        handle = self.start(spec=spec)
        context = Path(spec['model_evidence_context']['path'])
        context.chmod(0o600)
        context.write_bytes(b'changed generated context')
        context.chmod(0o400)
        handle.go(handle.ready)
        receipt = self.finish(handle)
        self.assertEqual(receipt['outcome'], 'failed')

    def test_managed_context_is_reverified_after_child_exit_before_completion(self):
        context = self.staging / custody.MODEL_CONTEXT_PATH
        # The measured dummy interpreter is an authored shell fixture which
        # mutates the generated input then exits zero. It never loads Torch or
        # CUDA; the real helper must reject completion at its post-drain check.
        quoted = shlex.quote(str(context))
        program = '#!/bin/sh\nchmod u+w ' + quoted + '\nprintf changed > ' + quoted + '\n'
        self.python.write_text(program)
        self.python.chmod(0o700)
        self.manifest = runtime.inventory({'python': str(self.python),
            'python_root': str(self.root / 'installed'), 'site_packages': str(self.root / 'packages')})
        raw = runtime.encoded(self.manifest)
        self.manifest_path.write_bytes(raw)
        self.descriptor.update(manifest_sha256=runtime.sha(raw), manifest_bytes=len(raw),
            file_count=len(self.manifest['files']), total_bytes=self.manifest['total_bytes'])
        handle = self.start(spec=self.context_spec())
        handle.go(handle.ready)
        self.until(handle, lambda: handle.terminal or handle.lost)
        handle.process.wait(timeout=2)
        receipt = custody.load_receipt(handle.directory / 'receipt.json', handle.expected_identity)
        self.assertTrue(receipt['go_received'])
        self.assertTrue(receipt['drained'])
        self.assertEqual(receipt['leader_returncode'], 0)
        self.assertEqual(receipt['reason'], 'model_context_changed')
        self.assertEqual(receipt['outcome'], 'failed')


if __name__ == '__main__':
    unittest.main()
