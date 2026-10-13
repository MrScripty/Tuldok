"""Actual retained producer bytes, full native contract and frozen custody checks."""
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from app import Dataset
from postgres_helpers import database_snapshot
import canonical_release
import rheon_sequence_contract as contract
import rheon_sequences
import sequence_release
from test_mesh_release import change_manifest, rewrite
from test_sequences import body, fixture
from workbench import WorkbenchError, encode

FIXTURE = Path(__file__).parent / 'fixtures' / 'rheon_actual_fee7b4a'


class SequenceRelease(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dataset = Dataset(self.temporary.name)
        self.addCleanup(self.dataset.close)
        self.workbench = self.dataset.workbench
        self.sources = [(FIXTURE / name).read_bytes() for name in ('run.json', 'frames.jsonl')]

    def freeze(self, also_synthetic=False):
        sources = [self.sources] + ([fixture()] if also_synthetic else [])
        rows = []
        for index, (run, frames) in enumerate(sources):
            row = rheon_sequences.admit(self.workbench, body(run, frames, name=f'Trajectory {index}', rights='Retained authored test fixture'))
            row = self.workbench.save(row['id'], dict(row, annotation={'note': 'Inspected native transport fields.'}, review='human_reviewed'))
            rows.append(row)
        request = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                       ratios=dict(train=100, validation=0, test=0), seed=4)
        preview = self.dataset.releases.preview(request)
        result = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        self.path = self.dataset.releases.locate(result['id'])
        return self.path.read_bytes(), rows

    def test_actual_native_bits_numeric_metadata_and_readonly_custody(self):
        raw, rows = self.freeze()
        before = database_snapshot(self.dataset.db)
        result = sequence_release.validate_release(self.path, hashlib.sha256(raw).hexdigest())
        self.assertEqual(database_snapshot(self.dataset.db), before)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual((result['sequence_count'], result['frame_count']), (1, 9))
        self.assertEqual(result['family_scope'], 'selected_records_only')
        report = result['sequences'][0]
        self.assertEqual(report['geometry']['counts'], [16, 8, 4])
        self.assertEqual(report['units']['time'], 's')
        self.assertEqual([frame['time_s'] for frame in report['frame_index']], [i / 16 for i in range(9)])
        numeric = report['technical_validation']
        self.assertEqual((numeric['volume_m3'], numeric['mass_kg'], numeric['centroid_x_m']), (0.125, 100.0, 0.5))
        receipt = json.loads((FIXTURE / 'producer-receipt.json').read_bytes())
        self.assertEqual(report['run_sha256'], receipt['run_sha256'])
        self.assertEqual(report['frames_sha256'], receipt['frames_sha256'])
        self.assertEqual(report['provenance']['source_commit'], receipt['producer_commit'])
        with zipfile.ZipFile(io.BytesIO(raw)) as release:
            manifest = json.loads(release.read('manifest.json'))
            with zipfile.ZipFile(io.BytesIO(release.read(manifest['records'][0]['asset']))) as bundle:
                observed = [bundle.read(name) for name in ('run.json', 'frames.jsonl')]
        self.assertEqual(observed, self.sources)
        # Independent struct decoding observes all native bits without the app's
        # _fields helper; original bytes and array order must both survive.
        source_frames = [json.loads(line) for line in self.sources[1].splitlines()]
        output_frames = [json.loads(line) for line in observed[1].splitlines()]
        for index, (source, output) in enumerate(zip(source_frames, output_frames)):
            for name, dtype in contract.FIELD_TYPES.items():
                fmt = '<' + ('f' if dtype == 'f32' else 'd')
                self.assertEqual([struct.pack(fmt, value) for value in source['fields'][name]],
                                 [struct.pack(fmt, value) for value in output['fields'][name]])
            entry = report['frame_index'][index]
            fragment = observed[1][entry['byte_offset']:entry['byte_offset'] + entry['byte_length']]
            self.assertEqual(hashlib.sha256(fragment).hexdigest(), entry['sha256'])
        self.workbench.save(rows[0]['id'], dict(rows[0], annotation={'note': 'New current review note.'}, review='human_reviewed'))
        self.assertEqual(sequence_release.validate_release(self.path), result)
        # The cold CLI uses no database and remains valid under Python -O.
        child = subprocess.run([sys.executable, '-O', 'sequence_release.py', str(self.path)],
                               capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(child.stdout), result)

    def test_frozen_review_revision_source_projection_and_bounds_rejections(self):
        raw, _ = self.freeze()
        mutations = [
            (lambda m: m['records'][0].update(review='draft'), 'human-reviewed'),
            (lambda m: m['records'][0].update(revision=True), 'revision'),
            (lambda m: m['records'][0].update(source_available=False), 'available'),
            (lambda m: m['records'][0].update(asset_sha256='0' * 64), 'hash mismatch'),
            (lambda m: m['records'][0]['sequence']['frame_index'][1].update(time_s=99), 'metadata differs'),
            (lambda m: m['records'][0]['sequence']['manifest']['units'].update(time='ms'), 'metadata differs'),
            (lambda m: m['records'][0].update(groups=['unrelated']), 'family is missing'),
            (lambda m: m['split_report']['actual_counts'].update(train=2), 'counts disagree'),
            (lambda m: m['records'][0].update(asset='../outside.zip'), 'archive paths'),
        ]
        for mutate, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(WorkbenchError, message):
                sequence_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, mutate)))
        with self.assertRaisesRegex(WorkbenchError, 'JSONL differs'):
            sequence_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, lambda m: m['records'][0].update(name='Changed'), False)))
        with self.assertRaisesRegex(WorkbenchError, 'SHA256 differs'):
            sequence_release.validate_bytes(raw, '0' * 64)
        with patch.object(canonical_release, 'MAX_RELEASE_BYTES', len(raw) - 1), self.assertRaises(WorkbenchError):
            sequence_release.validate_bytes(raw)
        with self.assertRaises(WorkbenchError) as failure:
            sequence_release.validate_release(self.path.parent / 'absent.zip')
        self.assertEqual(failure.exception.code, 'unavailable')

    def test_selected_initial_family_cannot_cross_splits(self):
        raw, rows = self.freeze(also_synthetic=True)
        self.assertEqual(rows[0]['groups'][1], rows[1]['groups'][1])
        self.assertEqual(sequence_release.validate_bytes(raw)['sequence_count'], 2)
        def split(manifest):
            manifest['records'][1]['split'] = 'validation'
            manifest['split_report']['actual_counts'] = {'train': 1, 'validation': 1}
        with self.assertRaisesRegex(WorkbenchError, 'cross frozen splits'):
            sequence_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, split)))

    def test_native_corruption_rejected_even_after_rehashing_outer_custody(self):
        raw, _ = self.freeze()
        def corrupt(entries, mutation):
            manifest = json.loads(entries['manifest.json'])
            row = manifest['records'][0]
            with zipfile.ZipFile(io.BytesIO(entries[row['asset']])) as bundle:
                run = json.loads(bundle.read('run.json'))
                frames = [json.loads(line) for line in bundle.read('frames.jsonl').splitlines()]
            mutation(run, frames)
            frame_raw = b''.join(encode(frame).encode() + b'\n' for frame in frames)
            run.update(frames_bytes=len(frame_raw), frames_sha256=hashlib.sha256(frame_raw).hexdigest())
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as bundle:
                bundle.writestr('run.json', encode(run))
                bundle.writestr('frames.jsonl', frame_raw)
            value = stream.getvalue()
            entries[row['asset']] = value
            digest = hashlib.sha256(value).hexdigest()
            def update(current):
                current['records'][0].update(asset_sha256=digest, content_hash=digest, source_sha256=digest)
            change_manifest(entries, update)
        mutations = [
            lambda run, frames: run['geometry']['axis_order'].reverse(),
            lambda run, frames: frames[1].update(time_s=0.2),
            lambda run, frames: frames[1]['fields']['velocity_x'].pop(),
            lambda run, frames: frames[1]['fields']['fraction'].__setitem__(0, 9),
            lambda run, frames: frames[1]['carrier_stamp'].update(version='999'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaisesRegex(WorkbenchError, 'Invalid completed Rheon sequence'):
                sequence_release.validate_bytes(rewrite(raw, lambda entries: corrupt(entries, mutation)))

    def test_archive_envelopes_and_unsupported_kinds(self):
        raw, _ = self.freeze()
        for value in (b'prefix' + raw, raw + b'trailing', raw[:-10]):
            with self.assertRaises(WorkbenchError):
                sequence_release.validate_bytes(value)
        with self.assertRaisesRegex(WorkbenchError, 'archive paths'):
            sequence_release.validate_bytes(rewrite(raw, lambda entries: entries.update(extra=b'unclaimed')))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = [(name, archive.read(name)) for name in archive.namelist()]
        for compressed, duplicate in ((True, False), (False, True)):
            output = io.BytesIO()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED) as archive:
                    for name, value in entries + (entries[:1] if duplicate else []):
                        archive.writestr(name, value)
            with self.assertRaises(WorkbenchError):
                sequence_release.validate_bytes(output.getvalue())
        with self.assertRaises(WorkbenchError) as failure:
            sequence_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, lambda m: m['records'][0].update(kind='mesh'))))
        self.assertEqual(failure.exception.code, 'unsupported')
