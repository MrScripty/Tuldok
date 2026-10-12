"""Real frozen WAV classification, exact coordinates and durable run contract."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import zipfile

from app import Dataset
from workbench import WorkbenchError, encode
import audio_training as training

spec = importlib.util.spec_from_file_location('audio_classification_fixture', Path(__file__).parent / 'fixtures/workspaces/audio/classification_fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class AudioCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-audio-classification-')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.rows, self.originals = [], {}
        for index in range(18):
            raw = fixture.wav(index)
            row = self.dataset.workbench.audio.admit(dict(wav=base64.b64encode(raw).decode(),
                name=f'Authored tone {index}', groups=[f'authored-audio-{index}'],
                rights='CC0 authored mathematical PCM; no quality or independence claim.'))
            row = self.dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
                task='audio_timed', annotation={'segments': [fixture.segment(index)]}, groups=row['groups'], review='human_reviewed'))
            self.rows.append(row); self.originals[row['id']] = raw
        self.body = dict(format='audio_classification_v1',
            items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in self.rows],
            ratios={'train': 50, 'validation': 25, 'test': 25}, seed=42)
        for seed in range(42, 100):
            self.body['seed'] = seed
            preview = self.dataset.releases.preview(self.body)
            if preview['eligible']:
                break
        self.assertTrue(preview['eligible'], preview['blockers'])
        self.release = self.dataset.releases.create(dict(self.body, preview_token=preview['preview_token']))
        self.release_path = self.dataset.releases.locate(self.release['id'])
        with zipfile.ZipFile(self.release_path) as archive:
            self.members = {name: archive.read(name) for name in archive.namelist()}
        self.manifest = json.loads(self.members['manifest.json'])
        self.graph = self.dataset.pipelines.create(dict(name='Authored audio baseline', recipe='audio_classification', release_id=self.release['id']))

    def altered(self, mutate=None, members_mutate=None):
        value, members = copy.deepcopy(self.manifest), dict(self.members)
        if mutate: mutate(value)
        members['manifest.json'] = encode(value).encode()
        for split in ('train', 'validation', 'test'):
            members[split + '/records.jsonl'] = ''.join(encode(row) + '\n' for row in value['records'] if row['split'] == split).encode()
        if members_mutate: members_mutate(members)
        path = Path(self.tmp.name) / (uuid.uuid4().hex + '.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, contents in members.items(): archive.writestr(name, contents)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()


class AudioReleaseTests(AudioCase):
    def test_originals_and_source_coordinates_survive_real_release(self):
        value = training.inspect_release(self.release_path, self.release['id'])
        self.assertEqual(value, self.manifest)
        for row in value['records']:
            self.assertEqual(self.members[row['asset']], self.originals[row['id']])
            self.assertEqual(row['start_frame'], 256); self.assertEqual(row['end_frame'], 1280)
            self.assertEqual(row['target_label'], row['annotation']['segments'][0]['label'])
        self.assertEqual(self.dataset.pipelines.inspect_release(self.release['id'])['recipe'], 'audio_classification')

    def test_source_coordinate_hash_and_family_tampering_is_refused(self):
        for field, bad in [('start_frame', 255), ('channel', True), ('sample_rate_hz', 16000),
                           ('asset_sha256', '0' * 64), ('pcm_sha256', '0' * 64), ('audio_family_sha256', '0' * 64)]:
            with self.subTest(field=field), self.assertRaises(training.TrainingError):
                training.inspect_release(*self.altered(lambda value: value['records'][0].update({field: bad})))
        def cross(value):
            a = next(r for r in value['records'] if r['split'] == 'train')
            b = next(r for r in value['records'] if r['split'] == 'test')
            value['protected_components'][a['export_group']][0]['parents'].append('f' * 32)
            value['protected_components'][b['export_group']][0]['parents'].append('f' * 32)
        with self.assertRaisesRegex(training.TrainingError, 'bridge crosses'):
            training.inspect_release(*self.altered(cross))

    def test_draft_multiple_intervals_and_transcript_only_remain_ineligible(self):
        for mutate in (lambda r: r.update(review='draft'),
                       lambda r: r['annotation']['segments'].append(dict(r['annotation']['segments'][0], end_frame=1500)),
                       lambda r: r['annotation']['segments'][0].update(label='', transcript='Human words')):
            with self.subTest(mutate=mutate), self.assertRaises(training.TrainingError):
                training.inspect_release(*self.altered(lambda v: mutate(v['records'][0])))

    def test_unsafe_archive_and_jsonl_mapping_are_refused(self):
        for mutation in (lambda m: m.update({'../outside': b'x'}),
                         lambda m: m.update({'validation/records.jsonl': b''}),
                         lambda m: m.update({self.manifest['records'][0]['asset']: b'not WAV'})):
            with self.subTest(mutation=mutation), self.assertRaises(training.TrainingError):
                training.inspect_release(*self.altered(members_mutate=mutation))

    def test_editable_graph_and_honest_first_checkpoint_unavailable(self):
        self.assertEqual(self.graph['edges'][1]['output'], 'audio_export')
        edited = copy.deepcopy(self.graph); edited['nodes'][2]['parameters']['C'] = .5
        saved = self.dataset.pipelines.save(edited['id'], {'revision': 1, 'document': edited})
        result = self.dataset.pipelines.validate(saved['id'], {'revision': 2})
        self.assertFalse(result['valid']); self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['release']['records'], 18)
        self.assertEqual(result['release']['audio_summary']['analyzed_frames'], 18 * 1024)
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(dict(request_key='audio-checkpoint-refused', graph_id=saved['id'], graph_revision=2, validation_token='no'))
        self.assertEqual(self.dataset.runs.list(), [])
