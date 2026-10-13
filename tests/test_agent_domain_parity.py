"""Real agent HTTP parity over bounded authored data, never model acceptance.

Every import/save traverses AgentClient and the authenticated HTTP/domain owner.
Only the explicit local owner bootstrap and immutable fixture construction are
local. Sequence fixtures are synthetic transport bytes, not producer evidence.
"""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

from PIL import Image
from app import Dataset, make_handler
from auth_helpers import ExplicitOwnerFixture
from fixtures.rheon_controls_authored import fixture as controls_fixture
from fixtures.rheon_source_derived import synthetic_frames, synthetic_manifest
from qualify_scientific_fields import neutral_bundle

FIXTURES = Path(__file__).with_name('fixtures')


def b64(raw):
    return base64.b64encode(raw).decode('ascii')


@unittest.skipUnless(importlib.util.find_spec('jsonschema'),
                     'Requires the explicitly installed optional agent environment.')
class AgentDomainParityTests(unittest.TestCase):
    def setUp(self):
        import agent_api
        directory = tempfile.TemporaryDirectory(prefix='agent-owner-parity-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.project = self.path / 'project'
        self.project.mkdir()
        self.dataset = Dataset(self.path / 'catalog', project_roots={'fixture': self.project})
        self.addCleanup(lambda: self.dataset.close())
        self.owner = ExplicitOwnerFixture.bootstrap(self.dataset)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.endpoint = f'http://127.0.0.1:{self.server.server_port}'
        credential = self.issue(['inspect', 'edit'])
        self.agent = credential
        self.client = agent_api.AgentClient(self.endpoint, credential['token'], self.owner.catalog_id)
        self.client.bootstrap()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def http(self, path, body=None, *, token=None, binary=False, status=200):
        request = Request(self.endpoint + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + (token or self.owner.token),
                     'Content-Type': 'application/json'})
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            value = raw if binary else json.loads(raw)
            self.assertEqual(response.status, status, value if not binary else raw[:200])
            return value

    def issue(self, scopes):
        return self.http('/api/access/credentials',
                         {'label': 'Authored domain parity', 'scopes': scopes}, status=201)

    def call(self, operation, args, status=200, client=None):
        result = (client or self.client).call(operation, args)
        self.assertEqual(result['status'], status, {'operation': operation, 'result': result})
        return result['result']

    def import_files(self, kind, members):
        self.assertLessEqual(sum(map(len, members.values())), 512 * 1024)
        return self.call('data.import_' + kind,
            {'files': {name: b64(raw) for name, raw in members.items()},
             'name': 'Authored ' + kind, 'groups': ['authored-' + kind],
             'rights': 'Bounded authored transport fixture; no scientific acceptance.'}, 201)

    def save_and_refuse_stale(self, record, task, annotation, expected):
        before = self.http('/api/workbench/asset/' + record['id'],
                           token=self.agent['token'], binary=True)
        body = {'record_id': record['id'], 'revision': record['revision'],
                'source_revision': record['source_revision'], 'groups': record['groups'],
                'task': task, 'annotation': annotation, 'review': 'draft'}
        saved = self.call('data.save_draft', body)
        self.assertEqual(saved['task'], task)
        self.assertEqual(saved['annotation'], expected)
        self.assertEqual(saved['review'], 'draft')
        self.assertEqual(saved['revision'], record['revision'] + 1)
        self.assertEqual(saved['source_revision'], record['source_revision'])
        self.assertEqual(saved['content_hash'], record['content_hash'])
        self.call('data.save_draft', body, 409)
        current = dict(body, revision=saved['revision'])
        self.call('data.save_draft', dict(current, source_revision=saved['source_revision'] + 1), 409)
        if record['kind'] not in ('image', 'text'):
            self.call('data.save_draft', dict(current, groups=['removed-protected-family']), 400)
        self.assertEqual(self.call('data.get', {'record_id': record['id']}), saved)
        after = self.http('/api/workbench/asset/' + record['id'],
                          token=self.agent['token'], binary=True)
        self.assertEqual(after, before)
        return saved

    def test_all_twelve_annotations_and_native_import_variants_reach_domain_owner(self):
        seen = set()
        stream = io.BytesIO()
        Image.new('RGB', (16, 16), (20, 40, 160)).save(stream, 'PNG')
        image = self.call('data.import_image', {'image': b64(stream.getvalue()),
                                               'groups': ['authored-image']}, 201)
        boxes = {'boxes': [{'label': ' patch ', 'x': 1, 'y': 2, 'width': 3, 'height': 4}]}
        expected_boxes = {'boxes': [dict(boxes['boxes'][0], label='patch')]}
        for task, annotation, expected in [
            ('image_detection', boxes, expected_boxes),
            ('image_classification', {'label': ' blue '}, {'label': 'blue'}),
            ('image_caption', {'caption': ' Authored pixels '}, {'caption': 'Authored pixels'})]:
            image = self.save_and_refuse_stale(image, task, annotation, expected)
            seen.add(task)
        text = self.call('data.import_text', {'text': 'Cafe\u0301 λ\r\n', 'groups': ['authored-text']}, 201)
        self.assertEqual(text['text'], 'Café λ\n')
        for task, annotation, expected in [
            ('text_classification', {'label': ' greeting '}, {'label': 'greeting'}),
            ('text_entities', {'spans': [{'label': ' word ', 'start': 0, 'end': 4}]},
                              {'spans': [{'label': 'word', 'start': 0, 'end': 4}]}),
            ('text_corpus', {'note': ' Authored corpus '}, {'note': 'Authored corpus'})]:
            text = self.save_and_refuse_stale(text, task, annotation, expected)
            seen.add(task)
        audio_raw = (FIXTURES / 'workspaces/audio/stereo-impulses.wav').read_bytes()
        audio = self.call('data.import_audio', {'wav': b64(audio_raw), 'groups': ['authored-audio']}, 201)
        segments = {'segments': [{'start_frame': 4000, 'end_frame': 8001, 'channel': 1,
                                 'transcript': '', 'label': 'impulse', 'speaker': ''}]}
        audio = self.save_and_refuse_stale(audio, 'audio_timed', segments, segments)
        seen.add('audio_timed')
        self.assertEqual(self.call('data.audio', {'record_id': audio['id']})['id'], audio['id'])
        native = []
        for kind, directory, stem, filenames in [
            ('mesh', 'meshes', 'tetrahedron', ('mesh.ply', 'mesh.json')),
            ('pointcloud', 'pointclouds', 'ordered', ('points.ply', 'points.json')),
            ('volume', 'volumes', 'oriented', ('volume.npy', 'volume.json'))]:
            members = {name: (FIXTURES / directory / (stem + Path(name).suffix)).read_bytes()
                       for name in filenames}
            native.append(self.import_files(kind, members))
        frames = b''.join(json.dumps(row, separators=(',', ':')).encode() + b'\n'
                          for row in synthetic_frames())
        native.append(self.import_files('sequence',
            {'run.json': json.dumps(synthetic_manifest(frames)).encode(), 'frames.jsonl': frames}))
        run, frames, controls = controls_fixture()
        native.append(self.import_files('sequence',
            {'run.json': run, 'frames.jsonl': frames, 'controls.json': controls}))
        source = neutral_bundle()
        (self.project / 'fields.zip').write_bytes(source)
        manifest = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Authored generic fields',
                    'data': [{'id': 'fields', 'label': 'Authored fixture', 'path': 'fields.zip'}],
                    'recipes': [], 'evidence': [], 'requirements': []}
        (self.project / 'project.json').write_text(json.dumps(manifest))
        project = self.call('projects.open', {'root': 'fixture', 'manifest_path': 'project.json'}, 201)
        native.append(self.call('data.import_project_scientific',
            {'project_id': project['id'], 'reference_id': 'fields',
             'expected_sha256': hashlib.sha256(source).hexdigest(), 'groups': ['authored-fields']}, 201))
        tasks = {'mesh': 'mesh_geometry', 'pointcloud': 'pointcloud_geometry', 'volume': 'volume_grid',
                 'sequence': 'sequence_transport', 'field_sequence': 'field_sequence_fields'}
        for record in native:
            task = tasks[record['kind']]
            with self.subTest(kind=record['kind'], id=record['id']):
                saved = self.save_and_refuse_stale(record, task,
                    {'note': ' Inspected authored source '}, {'note': 'Inspected authored source'})
                seen.add(task)
                operation = {'field_sequence': 'scientific'}.get(record['kind'], record['kind'])
                if operation != 'sequence':
                    projection = self.call('data.' + operation, {'record_id': saved['id']})
                    self.assertEqual(projection['id'], saved['id'])
        self.assertEqual(seen, {'image_detection', 'image_classification', 'image_caption',
            'text_classification', 'text_entities', 'text_corpus', 'audio_timed', 'mesh_geometry',
            'pointcloud_geometry', 'volume_grid', 'sequence_transport', 'field_sequence_fields'})

    @unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'),
                         'Requires an explicitly selected real classifier runtime.')
    def test_scoped_agent_exposes_actual_completed_authored_classifier_holdout(self):
        import agent_api
        rows = []
        for index in range(18):
            label = 'schedule' if index % 2 else 'cancel'
            text = ('Arrange meeting schedule tomorrow' if index % 2 else 'Cancel appointment reservation tomorrow')
            row = self.call('data.import_text', {'text': text + f' authoredmarker{index}',
                            'groups': [f'independent-text-{index}']}, 201)
            rows.append(self.http('/api/workbench/records/' + row['id'],
                {'revision': row['revision'], 'source_revision': row['source_revision'],
                 'task': 'text_classification', 'annotation': {'label': label},
                 'groups': row['groups'], 'review': 'human_reviewed'}))
        body = {'format': 'text_classification_v1',
                'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                'ratios': {'train': 50, 'validation': 25, 'test': 25}, 'seed': 42}
        for seed in range(42, 100):
            body['seed'] = seed
            preview = self.http('/api/workbench/releases/preview', body)
            if preview['eligible']:
                break
        self.assertTrue(preview['eligible'], preview['blockers'])
        release = self.http('/api/workbench/releases', dict(body, preview_token=preview['preview_token']), status=201)
        graph = self.http('/api/workspace/graphs', {'name': 'Authored holdout transport',
                          'recipe': 'text_classification', 'release_id': release['id']}, status=201)
        validation = self.http('/api/workspace/graphs/' + graph['id'] + '/validate', {'revision': graph['revision']})
        self.assertTrue(validation['valid'], validation)
        run = self.http('/api/workspace/runs', {'request_key': 'parity-' + uuid.uuid4().hex,
            'graph_id': graph['id'], 'graph_revision': graph['revision'],
            'validation_token': validation['validation_token']}, status=201)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            result = self.call('runs.get', {'run_id': run['id']})
            if result['state'] in ('completed', 'failed', 'unknown', 'interrupted'):
                break
            time.sleep(.05)
        self.assertEqual(result['state'], 'completed', {key: result.get(key) for key in ('id', 'state', 'error')})
        self.assertFalse(result['test_exposure']['exposed'])
        self.call('runs.expose_test', {'run_id': run['id'], 'reason': 'Authored holdout transport check'}, 403)
        self.http('/api/workspace/runs/' + run['id'] + '/predictions?split=test',
                  token=self.agent['token'], status=409)
        credential = self.issue(['inspect', 'expose-holdout'])
        scoped = agent_api.AgentClient(self.endpoint, credential['token'], self.owner.catalog_id)
        scoped.bootstrap()
        event = self.call('runs.expose_test', {'run_id': run['id'],
            'reason': 'Explicit authored classifier holdout inspection; no model quality claim.'}, client=scoped)
        self.assertTrue(event['test_exposure']['exposed'])
        predictions = self.http('/api/workspace/runs/' + run['id'] + '/predictions?split=test', token=credential['token'])
        self.assertGreater(len(predictions['rows']), 0)
        self.http('/api/access/credentials/' + credential['identity']['credential_id'] + '/revoke', {})
        self.call('runs.get', {'run_id': run['id']}, 401, client=scoped)


if __name__ == '__main__':
    unittest.main()
