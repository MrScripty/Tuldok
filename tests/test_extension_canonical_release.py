"""Actual author-side scalar A QA compilation, not E2 canonical execution."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import uuid
import zipfile

import numpy as np
from app import Dataset
from auth_helpers import bind_owner
import extension_canonical_fixture as fixture
import field_evidence
from postgres_helpers import database_snapshot
import scientific_release
from workbench import WorkbenchError, encode


class ExtensionCanonicalReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'source'; self.project.mkdir()
        self.dataset = Dataset(self.root / 'catalog', project_roots={'canonical-fixture': self.project})
        self.addCleanup(self.dataset.close)
        self.owner = bind_owner(self, self.dataset)
        self.source_raw = fixture.pinned_source()
        self.result = fixture.build_canonical_fixture(self.dataset, self.project, source_raw=self.source_raw)
        self.receipt = self.result['receipt']
        self.contract = self.receipt['contract']
        self.derivation = self.receipt['derivation']

    def verify(self, derivation=None, contract=None, releases=None, outputs=None):
        return field_evidence.validate_derivation(self.derivation if derivation is None else derivation,
            self.contract if contract is None else contract, self.result['releases'] if releases is None else releases,
            self.result['outputs'] if outputs is None else outputs)

    def test_real_owners_freeze_all_members_and_exact_original_native_values(self):
        self.assertEqual(hashlib.sha256(self.source_raw).hexdigest(), fixture.SOURCE_SHA256)
        self.assertEqual(fixture.pinned_source(), self.source_raw)
        self.assertEqual(self.verify(), self.derivation)
        self.assertTrue(fixture.verify_source_arrays(self.result['compilation'], self.result['releases']))
        self.assertEqual([case['id'] for case in self.derivation['cases']], ['train-0', 'train-1', 'validation-0'])
        self.assertEqual([case['split'] for case in self.derivation['cases']], ['train', 'train', 'validation'])
        self.assertEqual(self.derivation['fit_case_ids'], ['train-0', 'train-1'])
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 0)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_studies').fetchone()[0], 0)
        release_sha, raw = next(iter(self.result['releases'].items()))
        validated = scientific_release.validate_bytes(raw, release_sha)
        self.assertEqual(validated['split_counts'], dict(train=2, validation=1, test=0))
        self.assertEqual(validated['family_scope'], 'selected_records_only')
        source = json.loads(self.source_raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            frozen = {row['id']: row for row in json.loads(archive.read('manifest.json'))['records']}
            for original, case in zip(source['cases'], self.derivation['cases'], strict=True):
                row = frozen[case['record_id']]
                self.assertEqual(row['id'], self.result['records'][case['id']]['id'])
                self.assertEqual(row['review'], 'human_reviewed')
                self.assertEqual(case['protected_groups'], row['groups'])
                self.assertEqual(case['family'], dict(namespace='authored-extension-a-v2-qa', id=case['id']))
                with zipfile.ZipFile(io.BytesIO(archive.read(row['asset']))) as bundle:
                    self.assertEqual(json.loads(bundle.read('sources/authored-case.json')), original)
                    self.assertNotIn('sources/authored-a-v2.json', bundle.namelist())
                    proof = json.loads(bundle.read('sources/compile-receipt.json'))
                    self.assertEqual(proof['geometry'], source['geometry'])
                    self.assertEqual(proof['gauge_policy'], source['gauge_policy'])
                    for source_field, target_field in fixture.FIELD_MAPPING.items():
                        native = bundle.read('arrays/' + target_field + '.npy')
                        # Independent NumPy container decoder, separate from the
                        # compiler's writer and production scientific parser.
                        values = np.load(io.BytesIO(native), allow_pickle=False)
                        self.assertEqual(values.dtype.str, '<f8')
                        self.assertEqual(values.shape, (4, 4, 4))
                        self.assertTrue(values.flags.c_contiguous)
                        self.assertEqual(values.tobytes(order='C'), struct.pack('<64d', *original[source_field]))
                        np.testing.assert_array_equal(values.reshape(-1), original[source_field])
                        self.assertEqual(native, self.result['outputs'][original['id'] + '-' + target_field + '.npy'])
        self.assertEqual(self.receipt['native_array_count'], 6)
        self.assertFalse(self.receipt['e2_canonical_execution'])

    def test_single_storage_frame_does_not_invent_physical_time_or_prediction(self):
        self.assertEqual(self.contract['time_mode'], 'standalone')
        self.assertEqual(self.contract['inputs'][0]['field_id'], 'initial')
        self.assertEqual(self.contract['output']['field_id'], 'reference')
        self.assertEqual(self.contract['output']['stage'], 'reference_target')
        self.assertEqual(self.receipt['temporal_encoding'], fixture.TEMPORAL_ENCODING)
        for manifest in self.result['compilation']['manifests'].values():
            self.assertEqual(manifest['time_units'], 'not_applicable')
            self.assertEqual(manifest['frames'][0]['time'], '0')
            self.assertEqual(len(manifest['frames']), 1)
            self.assertEqual([field['id'] for field in manifest['fields']], ['initial', 'reference'])
        validation = self.result['compilation']['arrays']['validation-0']
        # These match A's pinned recipe native payload identities without
        # importing or executing its producer or changing any source values.
        self.assertEqual(field_evidence.digest([dict(field_id='initial', payload_sha256=hashlib.sha256(
            np.load(io.BytesIO(validation['initial']), allow_pickle=False).tobytes()).hexdigest())]),
                         'fb2a54168d0579a74de72c672c92548510ae6e35ab7edc7795a29483fb5d40ea')
        self.assertEqual(hashlib.sha256(np.load(io.BytesIO(validation['reference']), allow_pickle=False).tobytes()).hexdigest(),
                         '01575b8581ca92622705e8a456e00c220cb58fd19c17a8a50e08363538c0e9bf')

    def test_unknown_test_and_changed_membership_fail_without_catalog_mutation(self):
        before = database_snapshot(self.dataset.db)
        for split, code in [('unknown', 'invalid'), ('test', 'unsupported'), ('validation', 'invalid')]:
            altered = copy.deepcopy(self.derivation); altered['cases'][0]['split'] = split
            with self.subTest(split=split), self.assertRaises(WorkbenchError) as caught:
                self.verify(altered)
            self.assertEqual(caught.exception.code, code)
        altered = copy.deepcopy(self.derivation); altered['cases'][0]['record_id'] = 'f' * 32
        with self.assertRaisesRegex(WorkbenchError, 'membership'):
            self.verify(altered)
        altered = copy.deepcopy(self.derivation); altered['cases'].pop()
        with self.assertRaisesRegex(WorkbenchError, 'silent case drops'):
            self.verify(altered)
        self.assertEqual(database_snapshot(self.dataset.db), before)

    def test_fit_members_must_be_exact_ordered_train_population(self):
        for ids in (['train-1', 'train-0'], ['train-0'], ['train-0', 'train-1', 'validation-0'], ['validation-0']):
            altered = copy.deepcopy(self.derivation); altered['fit_case_ids'] = ids
            with self.subTest(ids=ids), self.assertRaisesRegex(WorkbenchError, 'ordered training'):
                self.verify(altered)

    def test_family_groups_and_selected_source_population_cannot_drift(self):
        for key, value in [('family', dict(namespace='other', id='other')), ('protected_groups', [])]:
            altered = copy.deepcopy(self.derivation); altered['cases'][0][key] = value
            with self.subTest(key=key), self.assertRaises(WorkbenchError):
                self.verify(altered)
        with self.assertRaises(WorkbenchError) as caught:
            self.verify(releases={})
        self.assertEqual(caught.exception.code, 'unavailable')
        extra = dict(self.result['releases']); extra['f' * 64] = next(iter(extra.values()))
        with self.assertRaisesRegex(WorkbenchError, 'Every selected source release'):
            self.verify(releases=extra)

    def test_real_release_owner_refuses_a_related_family_crossing_splits(self):
        # A new negative source is explicitly authored from a copy. Original A
        # fixture/bundles are unchanged. The real owner joins its shared family.
        raw = self.result['compilation']['bundles']['validation-0']
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            members = {name: bundle.read(name) for name in bundle.namelist()}
        manifest = json.loads(members['manifest.json'])
        manifest['family'] = self.result['compilation']['manifests']['train-0']['family']
        members['manifest.json'] = encode(manifest).encode()
        related = fixture.archive_bytes(members)
        (self.project / 'negative-related.zip').write_bytes(related)
        project = dict(schema_version=1, id=uuid.uuid4().hex, name='Explicit family leakage negative source',
            data=[dict(id='related', label='Related negative', path='negative-related.zip', sha256=fixture.sha(related))],
            recipes=[], evidence=[], requirements=[])
        (self.project / 'negative-project.json').write_text(encode(project))
        self.dataset.projects.open(dict(root='canonical-fixture', manifest_path='negative-project.json'))
        captured, source = self.dataset.projects.read_data_reference(project['id'], 'related', fixture.sha(related), 40 * 1024 * 1024)
        row = self.dataset.workbench.scientific.admit(captured, dict(name='Related negative', rights='Private authored negative QA only', groups=[], parents=[]), source)
        row = self.dataset.workbench.save(row['id'], dict(row, annotation={'note': 'Authored shared-family rejection fixture.'}, review='human_reviewed'))
        original = self.result['records']['train-0']
        request = dict(items=[{key: record[key] for key in ('id', 'revision', 'source_revision')} for record in (original, row)],
                       ratios=dict(train=50, validation=50, test=0), seed=42)
        preview = self.dataset.releases.preview(request)
        self.assertFalse(preview['eligible'])
        self.assertTrue(any('independent source groups' in blocker['message'] for blocker in preview['blockers']), preview)
        with self.assertRaises(WorkbenchError):
            self.dataset.releases.create(request)

    def test_stage_shape_geometry_gauge_and_native_output_drift_fail(self):
        for key, value in [('stage', 'post_train_mapping'), ('shape_zyx', [2, 4, 8]), ('units', 'Pa'), ('dtype', '<f4')]:
            contract = copy.deepcopy(self.contract); contract['output'][key] = value
            receipt = copy.deepcopy(self.derivation); receipt['contract_sha256'] = field_evidence.digest(contract)
            with self.subTest(key=key), self.assertRaises(WorkbenchError):
                self.verify(receipt, contract=contract)
        for key, value in [('geometry_sha256', '0' * 64), ('time', '0.0')]:
            receipt = copy.deepcopy(self.derivation); receipt['cases'][0][key] = value
            with self.subTest(key=key), self.assertRaises(WorkbenchError):
                self.verify(receipt)
        receipt = copy.deepcopy(self.derivation); receipt['cases'][0]['arrays'][0]['gauge_policy_sha256'] = '0' * 64
        with self.assertRaisesRegex(WorkbenchError, 'Gauge policy'):
            self.verify(receipt)
        # A self-consistent replacement Blob still cannot change native source.
        outputs = dict(self.result['outputs']); name = next(iter(outputs))
        native = outputs[name]; values = np.load(io.BytesIO(native), allow_pickle=False).reshape(-1).tolist(); values[0] += .125
        outputs[name] = fixture.npy(values)
        receipt = copy.deepcopy(self.derivation); receipt['cases'][0]['arrays'][0]['output'] = fixture.blob(name, outputs[name])
        with self.assertRaisesRegex(WorkbenchError, 'changes source array bytes'):
            self.verify(receipt, outputs=outputs)

    def test_original_gauge_and_geometry_bind_self_consistent_contract_changes(self):
        # The generic derivation decoder cannot interpret opaque source metadata;
        # the author-side source oracle additionally binds explicit gauge policy.
        altered = copy.deepcopy(self.result['compilation'])
        altered['contract']['inputs'][0]['gauge_policy_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source contract'):
            fixture.verify_source_arrays(altered, self.result['releases'])
        altered = copy.deepcopy(self.result['compilation']); altered['source']['geometry']['origin_xyz'][0] = 99
        with self.assertRaisesRegex(ValueError, 'pinned authored source'):
            fixture.verify_source_arrays(altered, self.result['releases'])
        with self.assertRaisesRegex(ValueError, 'exact pinned'):
            fixture.compile_authored_a(self.source_raw + b'\n')

    def test_cold_release_and_derivation_reopen_without_project_inputs(self):
        original_raw = next(iter(self.result['releases'].values()))
        for path in self.project.iterdir():
            path.unlink()
        self.assertEqual(self.verify(), self.derivation)
        self.dataset.close()
        self.dataset = Dataset(self.root / 'catalog')
        self.addCleanup(self.dataset.close)
        with self.owner.bound(self.dataset):
            raw = self.dataset.releases.locate(self.receipt['release']['id']).read_bytes()
            self.assertEqual(raw, original_raw)
            self.assertTrue(fixture.verify_source_arrays(self.result['compilation'], {fixture.sha(raw): raw}))
            for row in self.result['records'].values():
                current = self.dataset.workbench.get(row['id'])
                self.assertEqual(current['revision'], row['revision'])
                self.assertEqual(current['review'], 'human_reviewed')
