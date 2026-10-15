"""Strict, bounded evidence reads and retained-document type rejection."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import model_evidence
import test_model_evidence


class EvidenceReadTests(unittest.TestCase):
    def test_nested_exponent_overflow_is_rejected_as_nonfinite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for number in ('1e309', '-1e309', 'NaN', 'Infinity'):
                with self.subTest(number=number):
                    (directory / 'document.json').write_text('{"nested":[' + number + ']}')
                    with self.assertRaises(ValueError):
                        model_evidence.read_document(directory, 'document.json')

    def test_document_byte_depth_and_node_bounds_are_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / 'document.json'
            path.write_text('{"finite":1.25,"selected":true,"optional":null}')
            self.assertEqual(model_evidence.read_document(directory, path.name),
                             {'finite': 1.25, 'selected': True, 'optional': None})
            with self.assertRaises(ValueError):
                model_evidence.read_document(directory, path.name, maximum=4)
            for content in ('[' * 17 + '0' + ']' * 17, json.dumps([0] * 32768),
                            '{"duplicate":1,"duplicate":2}'):
                with self.subTest(content_prefix=content[:25]):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        model_evidence.read_document(directory, path.name)

    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            fifo = Path(temporary) / 'document.json'
            os.mkfifo(fifo)
            command = ('from pathlib import Path; import sys,model_evidence\n'
                       'try: model_evidence.read_binary(Path(sys.argv[1]))\n'
                       'except ValueError: print("rejected")\n'
                       'else: raise AssertionError("FIFO accepted")')
            result = subprocess.run([sys.executable, '-c', command, str(fifo)],
                                    capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'rejected')

    def test_symlinks_and_hardlinks_do_not_become_evidence_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = directory / 'original.json'
            original.write_text('{}')
            (directory / 'symlink.json').symlink_to(original)
            with self.assertRaises(ValueError):
                model_evidence.read_document(directory, 'symlink.json')
            os.link(original, directory / 'hardlink.json')
            with self.assertRaises(ValueError):
                model_evidence.read_document(directory, 'hardlink.json')


@unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'),
                     'Separately provisioned qualified CPU runtime required.')
class ActualEvidenceDecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the actual CPU producer fixture without inheriting its test cases.
        test_model_evidence.ActualEvidenceTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_model_evidence.ActualEvidenceTests.tearDownClass.__func__(cls)

    @staticmethod
    def write(path, value):
        path.write_bytes(model_evidence.canonical(value) + b'\n')

    def test_boolean_schema_and_profile_integer_cannot_verify(self):
        source = self.dataset.runs.path / self.completed_run['id']
        for name, fields in (('model-evidence.json', ('schema_version',)),
                             ('model-evidence.json', ('task', 'revision')),
                             ('profile.json', ('capture', 'interval'))):
            with self.subTest(name=name, fields=fields), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / 'output'
                shutil.copytree(source, target)
                value = json.loads((target / name).read_text())
                parent = value
                for field in fields[:-1]:
                    parent = parent[field]
                parent[fields[-1]] = True
                self.write(target / name, value)
                with self.assertRaises(ValueError):
                    model_evidence.verify(target, self.private, self.private['metrics'])

    def test_rehashed_observations_and_metric_versions_reject_boolean_integers(self):
        source = self.dataset.runs.path / self.completed_run['id']
        for name in ('observations.json', 'metric-definitions.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / 'output'
                shutil.copytree(source, target)
                values = json.loads((target / name).read_text())
                if name == 'observations.json':
                    values[0]['clocks']['epoch'] = True
                else:
                    values[0]['semantic_version'] = True
                self.write(target / name, values)
                manifest_path = target / 'model-evidence.json'
                manifest = json.loads(manifest_path.read_text())
                if name == 'observations.json':
                    manifest['observations'][0] = model_evidence.blob(target / name)
                else:
                    manifest['metric_definitions'] = model_evidence.blob(target / name)
                self.write(manifest_path, manifest)
                with self.assertRaises(ValueError):
                    model_evidence.verify(target, self.private, self.private['metrics'])

    def test_rehashed_checkpoint_cannot_use_boolean_or_unsafe_integer_clocks(self):
        source = self.dataset.runs.path / self.completed_run['id']
        for field, number, epoch in (('epoch', True, 1), ('wall_elapsed_ms', 2**53, 2)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / 'output'
                shutil.copytree(source, target)
                index = json.loads((target / 'checkpoints.json').read_text())
                entry = index['entries'][epoch - 1]
                old_sha = entry['checkpoint']['sha256']
                descriptor_path = target / entry['checkpoint']['name']
                descriptor = json.loads(descriptor_path.read_text())
                descriptor['clocks'][field] = number
                if field == 'wall_elapsed_ms':
                    entry['clocks'][field] = number
                self.write(descriptor_path, descriptor)
                entry['checkpoint'] = model_evidence.blob(descriptor_path)
                manifest_path = target / 'model-evidence.json'
                manifest = json.loads(manifest_path.read_text())
                # Rebind every declared observation shard so the malformed
                # clock cannot be rejected merely for an obsolete content hash.
                for item in manifest['observations']:
                    path = target / item['name']
                    values = json.loads(path.read_text().replace(old_sha, entry['checkpoint']['sha256']))
                    if item['name'] == 'observations.json':
                        for observation in values:
                            if observation['checkpoint_sha256'] == entry['checkpoint']['sha256']:
                                observation['clocks'] = copy.deepcopy(entry['clocks'])
                    self.write(path, values)
                self.write(target / 'checkpoints.json', index)
                manifest['checkpoints'] = model_evidence.blob(target / 'checkpoints.json')
                manifest['observations'] = [model_evidence.blob(target / item['name'])
                                            for item in manifest['observations']]
                self.write(manifest_path, manifest)
                with self.assertRaises(ValueError):
                    model_evidence.verify(target, self.private, self.private['metrics'])


if __name__ == '__main__':
    unittest.main()
