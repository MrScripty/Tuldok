"""Real text export/reader/trainer and durable graph/run custody contracts."""
import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
from workbench import WorkbenchError, encode
import text_training as training


class TextCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-text-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.rows = []
        for index in range(18):
            label = 'schedule' if index % 2 else 'cancel'
            text = (('Arrange meeting schedule tomorrow' if label == 'schedule' else 'Cancel appointment reservation tomorrow')
                    + f' authoredmarker{index} cafe\u0301\r\n')
            row = self.dataset.workbench.import_asset({'kind': 'text', 'text': text,
                'name': f'Authored intent {index}', 'groups': [f'independent-text-{index}'], 'parents': [],
                'rights': 'CC0 authored test text; no accuracy or semantic independence claim.'})
            row = self.dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
                task='text_classification', annotation={'label': label}, groups=row['groups'], review='human_reviewed'))
            self.rows.append(row)
        self.body = {'format': 'text_classification_v1',
                     'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in self.rows],
                     'ratios': {'train': 50, 'validation': 25, 'test': 25}, 'seed': 42}
        for seed in range(42, 100):
            self.body['seed'] = seed
            preview = self.dataset.releases.preview(self.body)
            if preview['eligible']:
                break
        self.assertTrue(preview['eligible'], preview['blockers'])
        self.release = self.dataset.releases.create(dict(self.body, preview_token=preview['preview_token']))
        self.release_id = self.release['id']
        self.release_path = self.dataset.releases.locate(self.release_id)
        with zipfile.ZipFile(self.release_path) as archive:
            self.members = {name: archive.read(name) for name in archive.namelist()}
        self.manifest = json.loads(self.members['manifest.json'])
        self.graph = self.dataset.pipelines.create({'name': 'Authored text baseline', 'recipe': 'text_classification', 'release_id': self.release_id})

    def mutated(self, mutate=None, member_mutation=None, *, sync_jsonl=True):
        manifest, members = copy.deepcopy(self.manifest), dict(self.members)
        if mutate:
            mutate(manifest)
        members['manifest.json'] = encode(manifest).encode()
        if sync_jsonl:
            for split in ('train', 'validation', 'test'):
                members[split + '/records.jsonl'] = ''.join(encode(row) + '\n' for row in manifest['records'] if row['split'] == split).encode()
        if member_mutation:
            member_mutation(members)
        path = Path(self.tmp.name) / ('mutation-' + uuid.uuid4().hex + '.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, raw in members.items():
                archive.writestr(name, raw)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def rejected(self, message, mutate=None, member_mutation=None, **kwargs):
        path, digest = self.mutated(mutate, member_mutation, **kwargs)
        with self.assertRaises(training.TrainingError) as caught:
            training.inspect_release(path, digest)
        self.assertEqual(caught.exception.outcome, 'invalid')
        self.assertEqual(str(caught.exception), message)


class TextContractTests(TextCase):
    def test_real_unselected_audio_bridge_preserves_text_split_custody(self):
        wav = Path(__file__).parent / 'fixtures/workspaces/audio/stereo-impulses.wav'
        parents = [row['id'] for row in self.rows[:2]]
        audio = self.dataset.workbench.audio.admit({
            'wav': base64.b64encode(wav.read_bytes()).decode(),
            'name': 'Authored audio lineage bridge', 'groups': ['audio-bridge'],
            'parents': parents, 'rights': 'CC0 authored PCM test fixture.'})
        for seed in range(42, 100):
            body = dict(self.body, seed=seed)
            preview = self.dataset.releases.preview(body)
            if preview['eligible']:
                break
        self.assertTrue(preview['eligible'], preview['blockers'])
        release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        frozen = training.inspect_release(self.dataset.releases.locate(release['id']), release['id'])
        family = next(members for members in frozen['protected_components'].values()
                      if any(member['id'] == audio['id'] for member in members))
        self.assertEqual({member['id'] for member in family}, {*parents, audio['id']})
        self.assertEqual(next(member for member in family if member['id'] == audio['id'])['kind'], 'audio')
        self.assertEqual({row['id'] for row in frozen['records']}, {row['id'] for row in self.rows})
        self.assertEqual(len({row['split'] for row in frozen['records'] if row['id'] in parents}), 1)
        self.assertEqual(self.dataset.workbench.get(audio['id'])['review'], 'draft')

    def test_actual_release_preserves_canonical_and_original_source_identity(self):
        result = training.inspect_release(self.release_path, self.release_id)
        self.assertEqual(result, self.manifest)
        self.assertEqual(result['format'], 'text_classification_v1')
        self.assertEqual({row['id'] for row in result['records']}, {row['id'] for row in self.rows})
        for row in result['records']:
            self.assertNotEqual(row['source_sha256'], row['content_hash'])
            self.assertEqual(row['asset_sha256'], hashlib.sha256(row['text'].encode()).hexdigest())
            self.assertNotIn('\r', row['text'])
        self.assertNotIn('sklearn', sys.modules)

    def test_changed_bytes_and_original_hash_are_not_silently_adopted(self):
        with self.assertRaisesRegex(training.TrainingError, 'SHA-256 does not match'):
            training.inspect_release(self.release_path, '0' * 64)
        asset = self.manifest['records'][0]['asset']
        self.rejected('Frozen text asset bytes differ from the manifest.', member_mutation=lambda m: m.update({asset: b'changed'}))
        self.rejected('Frozen text source reference differs from its family snapshot.',
                      lambda m: m['records'][0].update(source_sha256='0' * 64))

    def test_review_resource_and_unknown_parameter_boundaries(self):
        self.rejected('Every frozen text requires available, human-reviewed classification and known lineage.', lambda m: m['records'][0].update(review='draft'))
        self.rejected('Frozen text revisions must be positive integers.', lambda m: m['records'][0].update(revision=True))
        with patch.object(training, 'MAX_ZIP_BYTES', 1):
            with self.assertRaisesRegex(training.TrainingError, '8 MiB archive limit'):
                training.inspect_release(self.release_path, self.release_id)
        for parameters in ({'max_features': 64, 'alpha': 0}, {'max_features': True, 'alpha': 1},
                           {'max_features': 4097, 'alpha': 1}, {'max_features': 64, 'alpha': 1, 'command': 'x'}):
            with self.assertRaises(training.TrainingError):
                training.validate_parameters(parameters)

    def test_unsafe_archive_and_jsonl_binding(self):
        self.rejected('Text release contains an unsafe ZIP entry.', member_mutation=lambda m: m.update({'../outside': b'bad'}))
        self.rejected('Frozen text JSONL differs from its manifest mapping.', member_mutation=lambda m: m.update({'validation/records.jsonl': b''}))
        self.rejected('Text release contains undeclared or missing files.', member_mutation=lambda m: m.update({'extra.txt': b'extra'}))

    def test_frozen_bridge_leakage_is_detected_independently_of_split_owner(self):
        train = next(row for row in self.manifest['records'] if row['split'] == 'train')
        test = next(row for row in self.manifest['records'] if row['split'] == 'test')
        def bridge(manifest):
            first = manifest['protected_components'][train['export_group']][0]
            second = manifest['protected_components'][test['export_group']][0]
            # An unselected bridge participates in both declared components.
            first['parents'].append('a' * 32)
            second['parents'].append('a' * 32)
        self.rejected('Frozen protected family bridge crosses declared components.', bridge)

    def test_unknown_lineage_cannot_certify_frozen_split_independence(self):
        group = self.manifest['records'][0]['export_group']
        def unavailable_selected(manifest):
            manifest['records'][0]['source_available'] = False
            manifest['protected_components'][group][0]['source_available'] = False
        self.rejected('Every frozen text requires available, human-reviewed classification and known lineage.', unavailable_selected)
        self.rejected('Frozen family metadata is invalid or unavailable.',
                      lambda m: m['protected_components'][group][0].update(source_lineage_known=False, source_available=False))
        self.rejected('Frozen text source reference differs from its family snapshot.',
                      lambda m: m['protected_components'][group][0].update(source_available=False))
        self.rejected('Frozen family metadata is invalid or unavailable.',
                      lambda m: m['protected_components'][group][0].update(source_available=1))

    def test_known_deleted_unselected_member_keeps_its_family_custody(self):
        def add_deleted(manifest):
            row = manifest['records'][0]
            members = manifest['protected_components'].pop(row['export_group'])
            deleted = copy.deepcopy(members[0])
            deleted.update(id='f' * 32, source_revision=None, source_available=False, source_lineage_known=True)
            members.append(deleted)
            component = 'component:' + hashlib.sha256(encode(sorted(member['id'] for member in members)).encode()).hexdigest()
            manifest['protected_components'][component] = members
            row['export_group'] = component
        path, digest = self.mutated(add_deleted)
        frozen = training.inspect_release(path, digest)
        self.assertTrue(any(not row['source_available'] and row['source_lineage_known']
                            for family in frozen['protected_components'].values() for row in family))

    def test_split_label_coverage_and_index_are_consumer_requirements(self):
        def remove_coverage(manifest):
            for row in manifest['records']:
                if row['split'] == 'test':
                    row.update(annotation={'label': 'cancel'}, class_index=0)
        self.rejected('Every frozen text split must contain every class; no examples are dropped or reassigned.', remove_coverage)
        self.rejected('Frozen text class indices differ from their labels.', lambda m: m['records'][0].update(class_index=True))

    def test_preflight_and_freshness_do_not_change_the_catalog(self):
        previous = self.dataset.workbench.get(self.rows[0]['id'])
        body = copy.deepcopy(self.body)
        body['ratios'] = {'train': 100, 'validation': 0, 'test': 0}
        self.assertFalse(self.dataset.releases.preview(body)['eligible'])
        self.assertEqual(self.dataset.workbench.get(previous['id']), previous)
        preview = self.dataset.releases.preview(self.body)
        self.dataset.workbench.save(previous['id'], dict(revision=previous['revision'], source_revision=previous['source_revision'],
            task=previous['task'], annotation={'label': 'changed'}, groups=previous['groups'], review='human_reviewed'))
        with self.assertRaises(WorkbenchError):
            self.dataset.releases.create(dict(self.body, preview_token=preview['preview_token']))

    def test_unsupported_zip_sibling_does_not_break_release_listing(self):
        raw = bytearray(self.release_path.read_bytes())
        # Unsupported compression is an archive-reader boundary, before dispatch.
        raw[8:10] = (99).to_bytes(2, 'little')
        central = raw.index(b'PK\x01\x02')
        raw[central + 10:central + 12] = (99).to_bytes(2, 'little')
        release_id = hashlib.sha256(raw).hexdigest()
        (self.dataset.releases.path / (release_id + '.zip')).write_bytes(raw)
        releases = {item['id']: item for item in self.dataset.pipelines.releases()}
        self.assertEqual(releases[self.release_id]['status'], 'available')
        self.assertEqual(releases[release_id]['status'], 'unavailable')
        self.assertEqual(releases[release_id]['message'], 'Frozen release manifest is unavailable.')

    def test_hostile_inherited_native_thread_settings_are_overridden_and_observed(self):
        with patch.dict(os.environ, {'OPENBLAS_NUM_THREADS': '8', 'OMP_NUM_THREADS': '8', 'MKL_NUM_THREADS': '8'}):
            probe = self.dataset.pipelines.probe('text_classification')
        self.assertTrue(probe['available'], probe)
        self.assertEqual(probe['runtime']['threads'], 1)
        # Independent observation occurs in the actual child after its real fit.
        from pipeline import training_environment
        command = ('import json,text_training; from threadpoolctl import threadpool_info; '
                   'probe=text_training.probe_runtime(); '
                   'print(json.dumps({"probe":probe,"counts":[p["num_threads"] for p in threadpool_info()]}))')
        with patch.dict(os.environ, {'OPENBLAS_NUM_THREADS': '8'}):
            result = subprocess.run([os.environ['TULDOK_TRAINING_PYTHON'], '-c', command],
                capture_output=True, text=True, check=True, timeout=30, env=training_environment())
        observed = json.loads(result.stdout)
        self.assertTrue(observed['probe']['available'], observed)
        self.assertTrue(observed['counts'])
        self.assertEqual(set(observed['counts']), {1})

    def test_text_graph_has_typed_ports_and_cannot_switch_to_image_by_release(self):
        graph = self.graph
        self.assertEqual(graph['recipe'], 'text_classification')
        self.assertEqual(graph['edges'][1]['output'], 'text_export')
        self.assertEqual(graph['nodes'][2]['parameters'], {'max_features': 1024, 'alpha': 1})
        bad = copy.deepcopy(graph)
        bad.pop('recipe')
        result = self.dataset.pipelines.validate_graph(bad)
        self.assertFalse(result['valid'])
        self.assertIsNone(result['runtime'])
        clone = self.dataset.pipelines.clone(graph['id'], {'name': 'Text clone'})
        self.assertEqual(clone['recipe'], graph['recipe'])


class TextExecutionTests(TextCase):
    def test_real_fit_results_restart_exposure_and_frozen_correction(self):
        validation = self.dataset.pipelines.validate(self.graph['id'], {'revision': 1})
        self.assertTrue(validation['valid'], validation)
        body = {'request_key': 'text-real-request-001', 'graph_id': self.graph['id'], 'graph_revision': 1,
                'validation_token': validation['validation_token']}
        run = self.dataset.runs.submit(body)
        self.assertEqual(self.dataset.runs.submit(body)['id'], run['id'])
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            result = self.dataset.runs.get(run['id'])
            if result['state'] in ('completed', 'failed', 'unknown'):
                break
            time.sleep(.05)
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['adapter'], training.ADAPTER)
        self.assertEqual(result['metrics']['transform']['fit_scope'], 'train')
        model, media = self.dataset.runs.artifact(run['id'], 'model.json')
        self.assertEqual(media, 'application/json')
        model = json.loads(model)
        train_ids = {row['id'] for row in self.manifest['records'] if row['split'] == 'train'}
        for row in self.manifest['records']:
            marker = next(word for word in row['text'].split() if word.startswith('authoredmarker'))
            self.assertEqual(marker in model['vocabulary'], row['id'] in train_ids)
        import math, re
        train_texts = [row['text'] for row in self.manifest['records'] if row['split'] == 'train']
        tokens = [set(re.findall(r'(?u)\b\w\w+\b', text.lower())) for text in train_texts]
        for token, index in model['vocabulary'].items():
            expected = math.log((1 + len(tokens)) / (1 + sum(token in words for words in tokens))) + 1
            self.assertAlmostEqual(model['idf'][index], expected, places=12)
        predictions = self.dataset.runs.predictions(run['id'])
        self.assertEqual(len(predictions['rows']), validation['release']['split_counts']['validation'])
        self.assertNotIn('exported_pixel_sha256', predictions['rows'][0])
        self.assertIn('content_sha256', predictions['rows'][0])
        with self.assertRaises(WorkbenchError) as refused:
            self.dataset.runs.artifact(run['id'], 'test-metrics.json')
        self.assertEqual(refused.exception.code, 'conflict')
        self.dataset.runs.expose_test(run['id'], {'reason': 'Explicit authored test holdout inspection.'})
        self.assertTrue(self.dataset.runs.get(run['id'])['test_exposure']['exposed'])
        source = self.dataset.workbench.get(predictions['rows'][0]['id'])
        old_bytes = self.release_path.read_bytes()
        self.dataset.workbench.save(source['id'], dict(revision=source['revision'], source_revision=source['source_revision'],
            task=source['task'], annotation={'label': 'corrected draft'}, groups=source['groups'], review='draft'))
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name)
        restored = self.dataset.runs.get(run['id'])
        self.assertEqual(restored['state'], 'completed')
        self.assertEqual(len(self.dataset.runs.list()), 1)
        self.assertEqual(old_bytes, self.release_path.read_bytes())
        current = self.dataset.runs.predictions(run['id'])
        self.assertEqual([row['frozen_reference'] for row in current['rows']], [row['frozen_reference'] for row in predictions['rows']])
        self.assertTrue(current['rows'][0]['current_record']['changed'])
        self.assertTrue(self.dataset.pipelines.inspect_release(self.release_id)['prior_test_exposure']['exposed'])
        # Executable serialization is absent; reject malformed JSON models at the result owner.
        bad_model = copy.deepcopy(model)
        bad_model['feature_log_prob'][0][0] = float('nan')
        with self.assertRaises(training.TrainingError):
            training.validate_model(bad_model)
