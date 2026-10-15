"""Authored contract/custody fixtures, explicitly not numerical physics tests."""
import copy
import hashlib
import io
import json
import struct
import unittest
import zipfile

import field_evidence as evidence
from workbench import WorkbenchError
import test_scientific_release as scientific_fixture


def blob(name, raw):
    return dict(name=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), media_type='application/x-npy')


class FieldEvidenceTests(unittest.TestCase):
    def setUp(self):
        # The existing source-owned fixture freezes through actual Workbench /
        # Releases / PostgreSQL. Its authored arrays make no physics claim.
        self.fixture = scientific_fixture.ScientificRelease()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        raw, _ = self.fixture.freeze()
        sha = hashlib.sha256(raw).hexdigest()
        self.releases = {sha: raw}
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            row = json.loads(archive.read('manifest.json'))['records'][0]
        source = self.fixture.manifest
        self.contract = dict(format='field_adapter_contract_v1', owner='Authored contract test; no qualified physical adapter',
             adapter=dict(name='authored_fixture', version=1), source_sha256='a'*64, time_mode='sequence',
             inputs=[], output=None)
        for item in source['fields']:
            import scientific_fields
            expected = dict(field_id=item['id'], dtype=item['dtype'], shape_zyx=scientific_fields.shape_for(source['grid'], item),
                      centering=item['centering'], stage=item['stage'], units=item['units'], gauge_policy_sha256='b'*64)
            if self.contract['output'] is None:
                self.contract['output'] = expected
            else:
                self.contract['inputs'].append(expected)
        self.outputs, cases = {}, []
        for frame, frame_value in enumerate(source['frames']):
            arrays = []
            for expected in self.contract['inputs'] + [self.contract['output']]:
                original = next(item for item in frame_value['arrays'] if item['field'] == expected['field_id'])
                array = self.fixture.arrays[original['path']]
                field = next(item for item in source['fields'] if item['id'] == expected['field_id'])
                payload, _ = scientific_fields.npy_payload(array, field, source['grid'])
                name = str(frame) + '-' + expected['field_id'] + '.npy'
                self.outputs[name] = array
                arrays.append(dict(field_id=expected['field_id'], source_sha256=hashlib.sha256(array).hexdigest(),
                     payload_sha256=hashlib.sha256(payload).hexdigest(), gauge_policy_sha256=expected['gauge_policy_sha256'], output=blob(name, array)))
            cases.append(dict(id='authored-case-' + str(frame), release_sha256=sha, record_id=row['id'], split='train', family=source['family'],
                    protected_groups=row['groups'], frame=frame, time=frame_value['time'], geometry_sha256=evidence.digest(source['grid']), arrays=arrays))
        self.receipt = dict(format='field_input_derivation_v1', contract_sha256=evidence.digest(self.contract),
                            family_scope='selected_records_only', cases=cases, fit_case_ids=[case['id'] for case in cases])

    def verify(self, receipt=None):
        return evidence.validate_derivation(receipt or self.receipt, self.contract, self.releases, self.outputs)

    def test_canonical_derivation_preserves_exact_source_and_native_payload(self):
        result = self.verify()
        self.assertEqual(result, self.receipt)
        self.assertEqual(result['cases'][0]['time'], '0.1250')
        self.assertEqual(result['fit_case_ids'], ['authored-case-0', 'authored-case-1'])
        self.assertEqual(evidence.validate_contract(self.contract), self.contract)

    def test_changed_stage_shape_units_gauge_and_case_membership_fail(self):
        mutations = [lambda r: r['cases'][0].update(time='0.125'),
                     lambda r: r['cases'][0].update(geometry_sha256='0'*64),
                     lambda r: r['cases'][0].update(split='validation'),
                     lambda r: r['cases'][0].update(family=dict(namespace='other', id='other')),
                     lambda r: r['cases'][0]['arrays'][0].update(gauge_policy_sha256='0'*64),
                     lambda r: r.update(fit_case_ids=['validation-case'])]
        for mutation in mutations:
            value = copy.deepcopy(self.receipt)
            mutation(value)
            with self.subTest(value=value), self.assertRaises(WorkbenchError):
                self.verify(value)
        for key, value in (('stage', 'changed'), ('shape_zyx', [1, 1, 1]), ('units', 'other'), ('dtype', '<f8')):
            contract = copy.deepcopy(self.contract)
            contract['inputs'][0][key] = value
            receipt = copy.deepcopy(self.receipt)
            receipt['contract_sha256'] = evidence.digest(contract)
            with self.subTest(key=key), self.assertRaises(WorkbenchError):
                evidence.validate_derivation(receipt, contract, self.releases, self.outputs)

    def test_lossy_output_and_missing_release_fail_closed(self):
        name = next(iter(self.outputs))
        self.outputs[name] = self.outputs[name][:-1] + b'X'
        with self.assertRaisesRegex(WorkbenchError, 'blob identity'):
            self.verify()
        with self.assertRaises(WorkbenchError) as caught:
            evidence.validate_derivation(self.receipt, self.contract, {}, self.outputs)
        self.assertEqual(caught.exception.code, 'unavailable')

    def test_omitted_source_frame_cannot_disappear_from_derivation(self):
        receipt = copy.deepcopy(self.receipt)
        receipt['cases'] = receipt['cases'][:1]
        receipt['fit_case_ids'] = receipt['fit_case_ids'][:1]
        with self.assertRaisesRegex(WorkbenchError, 'silent frame drops'):
            self.verify(receipt)

    def test_test_population_is_unavailable_at_every_accessor(self):
        for accessor in evidence.ACCESSORS:
            with self.subTest(accessor=accessor), self.assertRaises(WorkbenchError) as caught:
                evidence.require_population('test', accessor)
            self.assertEqual(caught.exception.code, 'unsupported')
            evidence.require_population('validation', accessor)
        receipt = copy.deepcopy(self.receipt)
        receipt['cases'][0]['split'] = 'test'
        with self.assertRaises(WorkbenchError) as caught:
            self.verify(receipt)
        self.assertEqual(caught.exception.code, 'unsupported')

    def test_exact_inference_can_coexist_with_negative_physical_result(self):
        value = dict(format='field_co_test_v1', contract_sha256=evidence.digest(self.contract),
             inference=dict(state='passed', reason='Authored reconstruction example only.', metrics={'maximum_error': 0}),
             physical=dict(state='failed', reason='Authored negative oracle result; no real physics executed.', metrics={'relative_l2': 9}))
        self.assertEqual(evidence.validate_co_test(value, self.contract), value)
        self.assertEqual(value['physical']['state'], 'failed')
        invalid = copy.deepcopy(value)
        invalid['physical']['metrics']['relative_l2'] = float('nan')
        with self.assertRaises(WorkbenchError):
            evidence.validate_co_test(invalid, self.contract)
        invalid['physical']['metrics']['relative_l2'] = 10**400
        with self.assertRaises(WorkbenchError):
            evidence.validate_co_test(invalid, self.contract)

    def test_standalone_pair_has_no_invented_frame_and_preserves_native_arrays(self):
        contract = copy.deepcopy(self.contract)
        contract['time_mode'] = 'standalone'
        output = contract['output']
        # Authored temperature is float64/cell; a fixture pair checks only the
        # representation. It is not pressure-model or pressure-units evidence.
        name = '0-' + output['field_id'] + '.npy'
        pair = {key: output[key] for key in ('dtype', 'shape_zyx', 'centering', 'stage', 'units', 'gauge_policy_sha256')}
        pair.update(geometry=self.fixture.manifest['grid'], prediction=blob(name, self.outputs[name]),
                    reference=blob(name, self.outputs[name]), mask=None)
        self.assertEqual(evidence.validate_pair(pair, contract, self.outputs), pair)
        invalid = dict(pair, frame=0)
        with self.assertRaisesRegex(WorkbenchError, 'fields differ'):
            evidence.validate_pair(invalid, contract, self.outputs)
        from qualify_scientific_fields import npy_payload
        raw = npy_payload(struct.pack('<d', 1), '<f8', [1, 1, 1])
        singleton_contract = copy.deepcopy(contract)
        singleton_contract['output']['shape_zyx'] = [1, 1, 1]
        singleton = dict(pair, geometry=dict(pair['geometry'], shape_xyz=[1, 1, 1]), shape_zyx=[1, 1, 1],
                         prediction=blob('one.npy', raw), reference=blob('one.npy', raw))
        evidence.validate_pair(singleton, singleton_contract, {'one.npy': raw})
        invalid = dict(singleton, shape_zyx=[True, True, True])
        with self.assertRaisesRegex(WorkbenchError, 'exact positive'):
            evidence.validate_pair(invalid, singleton_contract, {'one.npy': raw})
