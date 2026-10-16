"""Six bounded descriptor families through canonical and SDK inert seams only.

The fixtures' closed parameter schemas own their tiny example payload bounds.
Opaque tokenizer/clock/frame contracts are not scientific host validators.
"""
import builtins
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extension_contract as contract
from tuldok_extension_sdk import manifest as sdk

ROOT = Path(__file__).parent/'fixtures/extensions/modalities'
CORPUS = json.loads((ROOT/'corpus.json').read_text())
HAS_VALIDATOR = importlib.util.find_spec('jsonschema') is not None


def raw(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def config_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


@unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
class ExtensionModalityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/'modalities'
        shutil.copytree(ROOT, self.root)

    def read(self, path, limit):
        value = (self.root/path).read_bytes()
        if len(value) > limit:
            raise contract.ReadLimitError('Fixture read exceeds selected bound.', 'unavailable')
        return value

    def reference(self, entry):
        path = entry['manifest']
        return dict(id='selected', label='Selected authoring manifest', path=path,
                    sha256=contract.digest((self.root/path).read_bytes()))

    def both(self, entry):
        canonical = contract.catalog([self.reference(entry)], self.read)
        authored = sdk.validate(self.root, entry['manifest'])
        self.assertEqual(canonical, authored)
        return canonical['packages'][0]

    def change_descriptor(self, entry, mutate=None, content=None):
        directory = self.root/entry['root']
        descriptor = json.loads((directory/'descriptor.json').read_text())
        if mutate is not None:
            mutate(descriptor)
        (directory/'descriptor.json').write_bytes(raw(descriptor) if content is None else content)
        manifest = json.loads((directory/'extension.json').read_text())
        item = manifest['contributions'][0]
        content = (directory/'descriptor.json').read_bytes()
        item.update(sha256=contract.digest(content), bytes=len(content))
        (directory/'extension.json').write_bytes(raw(manifest))

    @staticmethod
    def replace_path(value, path, replacement):
        for key in path[:-1]:
            value = value[key]
        value[path[-1]] = replacement

    def test_six_descriptor_and_configuration_identities_are_exact_and_distinct(self):
        self.assertEqual({entry['modality'] for entry in CORPUS['modalities']},
                         {'image', 'text', 'audio', 'mesh', 'points', 'volume'})
        self.assertEqual(len({entry['resolved_config_digest'] for entry in CORPUS['modalities']}), 6)
        axes = set()
        for entry in CORPUS['modalities']:
            with self.subTest(modality=entry['modality']):
                directory = self.root/entry['root']
                self.assertEqual(entry['manifest_sha256'], contract.digest((directory/'extension.json').read_bytes()))
                for name, expected in entry['file_sha256'].items():
                    self.assertEqual(expected, contract.digest((directory/name).read_bytes()))
                descriptor = json.loads((directory/'descriptor.json').read_text())
                self.assertEqual(entry['descriptor_identity'], {key:descriptor[key] for key in ('id','version')} |
                                 {'sha256':contract.digest((directory/'descriptor.json').read_bytes())})
                configuration = json.loads((directory/'config.json').read_text())
                self.assertEqual(entry['config_sha256'], contract.digest((directory/'config.json').read_bytes()))
                self.assertEqual(descriptor['defaults'], configuration)
                self.assertEqual(entry['resolved_config_digest'], config_digest(configuration))
                self.assertEqual(contract.declaration((directory/'descriptor.json').read_bytes(), 'contribution'), descriptor)
                axes.update(tuple(port['axes']) for port in descriptor['ports'])
        self.assertIn(('sequence','token'), axes)
        self.assertIn(('record','point','xyz'), axes)
        self.assertIn(('sample','channel'), axes)
        self.assertIn(('face','corner'), axes)
        self.assertIn(('height','width','channel'), axes)
        self.assertIn(('z','y','x'), axes)

    def test_both_seams_are_inert_and_preserve_opaque_ports_metadata_fallback(self):
        before = {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original_import = builtins.__import__
        forbidden = {'app','projects','psycopg','torch','numpy'} | {entry['modality']+'_worker' for entry in CORPUS['modalities']}
        def no_application_or_package_import(name, *args, **kwargs):
            if name.split('.')[0] in forbidden:
                raise AssertionError('Inert descriptor inspection imported '+name)
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=no_application_or_package_import), \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('Inert descriptor inspection spawned a process')):
            for entry in CORPUS['modalities']:
                with self.subTest(modality=entry['modality']):
                    package = self.both(entry)
                    self.assertEqual(package['state'], 'valid')
                    self.assertEqual(package['host']['state'], 'compatible')
                    self.assertEqual(package['runtime']['state'], 'unavailable')
                    self.assertEqual(package['permission']['state'], 'unavailable')
                    self.assertEqual([item['state'] for item in package['contributions']], ['valid']*3)
                    self.assertEqual(package['contributions'][2]['definition']['view']['primitive'], 'metadata')
                    expected = json.loads((self.root/entry['root']/'descriptor.json').read_text())
                    self.assertEqual(package['contributions'][0]['definition']['ports'], expected['ports'])
                    self.assertEqual(sdk.validate(self.root,entry['manifest'])['execution'], 'unsupported')
        after = {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(any(p.name == 'EXECUTED' for p in self.root.rglob('*')))

    def test_authored_payload_types_and_bounds_refuse_without_coercion(self):
        for entry in CORPUS['modalities']:
            for kind in ('bad','overflow'):
                with self.subTest(modality=entry['modality'], kind=kind):
                    original = (ROOT/entry['root']/'descriptor.json').read_bytes()
                    (self.root/entry['root']/'descriptor.json').write_bytes(original)
                    negative = entry['negative_cases']
                    self.change_descriptor(entry, lambda value:self.replace_path(value['defaults'], negative[kind+'_path'], negative[kind+'_value']))
                    package = self.both(entry)
                    descriptor = package['contributions'][0]
                    self.assertEqual((descriptor['state'],descriptor['reason']),
                                     ('invalid','Defaults do not satisfy the parameter contract.'))
                    self.assertEqual([item['state'] for item in package['contributions'][1:]], ['unavailable']*2)

    def test_duplicate_nonfinite_and_closed_descriptor_objects_refuse(self):
        image = CORPUS['modalities'][0]
        for content, expected in ((b'{"format":"tuldok_contribution_v1","format":"other"}', 'Declaration must be strict UTF-8 JSON with unique fields.'),
                                  (b'{"format":"tuldok_contribution_v1","x":NaN}', 'Declaration must be strict UTF-8 JSON with unique fields.')):
            with self.subTest(content=content):
                self.change_descriptor(image, content=content)
                result = self.both(image)['contributions'][0]
                self.assertEqual(result['state'], 'invalid')
                self.assertEqual(result['reason'], expected)
        (self.root/image['root']/'descriptor.json').write_bytes((ROOT/image['root']/'descriptor.json').read_bytes())
        self.change_descriptor(image, lambda value:value['ports'][0].update(implicit_resize=True))
        result = self.both(image)['contributions'][0]
        self.assertEqual((result['state'], result['reason']), ('invalid','Declaration does not satisfy the closed contribution schema.'))

    def test_new_tokenizer_clock_frame_or_units_remain_opaque_but_exact_dependents_do_not_adapt(self):
        for entry in CORPUS['modalities']:
            with self.subTest(modality=entry['modality']):
                negative = entry['negative_cases']
                def new_author_identity(value):
                    path = negative['identity_path']
                    self.replace_path(value['defaults'], path, negative['identity_value'])
                    parameter = value['parameters']
                    for key in path:
                        parameter = parameter['properties'][key]
                    parameter['enum'] = [negative['identity_value']]
                    if parameter['type'] == 'string':
                        parameter['maxLength'] = len(negative['identity_value'])
                self.change_descriptor(entry, new_author_identity)
                package = self.both(entry)
                self.assertEqual(package['state'], 'valid')
                self.assertEqual(package['contributions'][0]['state'], 'valid')
                self.assertNotEqual(package['contributions'][0]['sha256'], entry['descriptor_identity']['sha256'])
                for dependent in package['contributions'][1:]:
                    self.assertEqual((dependent['state'],dependent['reason']),
                                     ('unavailable','Exact required contribution is unavailable.'))

    def test_port_contract_version_axes_or_units_change_identity_without_semantic_inference(self):
        entry = next(item for item in CORPUS['modalities'] if item['modality']=='volume')
        for field, replacement in [('units','kelvin'),('axes',['x','y','z']),('contract',dict(id='example.modality-volume:other',version='2.0.0'))]:
            with self.subTest(field=field):
                (self.root/entry['root']/'descriptor.json').write_bytes((ROOT/entry['root']/'descriptor.json').read_bytes())
                self.change_descriptor(entry, lambda value:value['ports'][0].update({field:replacement}))
                package = self.both(entry)
                self.assertEqual(package['contributions'][0]['state'], 'valid')
                self.assertEqual(package['contributions'][0]['definition']['ports'][0][field], replacement)
                self.assertEqual([item['state'] for item in package['contributions'][1:]], ['unavailable']*2)

    def test_unsupported_parameter_vocabulary_does_not_claim_new_modality_rules(self):
        entry = next(item for item in CORPUS['modalities'] if item['modality']=='audio')
        self.change_descriptor(entry, lambda value:value['parameters']['properties']['sample_rate_hz'].update(format='audio_clock'))
        result = self.both(entry)['contributions'][0]
        self.assertEqual((result['state'],result['reason']), ('unsupported','Unsupported parameter schema keyword.'))

    def test_bad_or_absent_field_provider_does_not_suppress_six_unrelated_descriptors(self):
        refs = [dict(self.reference(entry),id=entry['modality']) for entry in CORPUS['modalities']]
        baseline = contract.catalog(refs, self.read)['packages']
        sdk_baseline = {entry['modality']:self.both(entry) for entry in CORPUS['modalities']}
        neutral = json.loads((self.root/'image/extension.json').read_text())
        neutral['package']['id'] = 'example.unrelated-field'
        neutral['contributions'] = []
        neutral['sources'] = []
        task = dict(format='tuldok_contribution_v1',id='example.unrelated-field:task',version='1.0.0',kind='task',label='Unrelated field descriptor only',requires=[])
        content=raw(task);(self.root/'unrelated-task.json').write_bytes(content)
        neutral['contributions']=[dict(id=task['id'],version='1.0.0',kind='task',path='unrelated-task.json',sha256=contract.digest(content),bytes=len(content))]
        for mode in ('missing','malformed','incompatible','removed'):
            with self.subTest(field_provider=mode):
                candidate=copy.deepcopy(neutral)
                candidate['host_contracts'][0]['version']='99.0.0'
                content=b'{"format":' if mode=='malformed' else raw(candidate)
                path=self.root/'field-extension.json'
                path.write_bytes(content)
                field_ref=dict(id='field',label='Field sibling',path='field-extension.json',sha256=contract.digest(content))
                if mode=='missing':path.unlink()
                result=contract.catalog(refs+([] if mode=='removed' else [field_ref]),self.read)
                self.assertEqual(result['packages'][:6], baseline)
                self.assertEqual([p['state'] for p in result['packages'][:6]],['valid']*6)
                self.assertTrue(all(all(c['state']=='valid' for c in p['contributions']) for p in result['packages'][:6]))
                if mode!='removed':
                    field=result['packages'][-1]
                    self.assertEqual(field['state'],{'missing':'unavailable','malformed':'invalid','incompatible':'valid'}[mode])
                    if mode=='incompatible':self.assertEqual(field['host']['state'],'unsupported')
                for entry in CORPUS['modalities']:
                    self.assertEqual(self.both(entry), sdk_baseline[entry['modality']])


if __name__ == '__main__':
    unittest.main()
