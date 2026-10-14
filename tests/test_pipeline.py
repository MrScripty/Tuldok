"""Real PostgreSQL graph identity, editable drafts and admission contracts."""
from auth_helpers import bind_owner
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
from pipeline import decode_graph, execution_digest
from workbench import WorkbenchError


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(lambda: self.dataset.close())
        self.pipelines = self.dataset.pipelines
        self.rows = []
        for index, (split, label) in enumerate((split, label) for split in ('train', 'validation', 'test') for label in ('circle', 'square')):
            output = io.BytesIO()
            Image.new('RGB', (16, 16), (20 + index * 30, 40, 160 - index * 10)).save(output, 'PNG')
            row = self.dataset.workbench.import_asset({'kind': 'image', 'image': base64.b64encode(output.getvalue()).decode(),
                'name': f'owned-synthetic-{index}.png', 'groups': [f'independent-{index}'], 'parents': [],
                'rights': 'Owned generated pixels for automated contract testing.'}, source_split=split)
            row = self.dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
                task='image_classification', annotation={'label': label}, groups=row['groups'], review='human_reviewed'))
            self.rows.append(row)
        body = {'format': 'image_classification_v1', 'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in self.rows],
                'ratios': {'train': 34, 'validation': 33, 'test': 33}, 'seed': 42}
        preview = self.dataset.releases.preview(body)
        self.assertTrue(preview['eligible'], preview['blockers'])
        self.release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        self.graph = self.pipelines.create({'name': 'Owned image CPU recipe', 'release_id': self.release['id']})

    def ready(self):
        return {'schema_version': 1, 'available': True, 'adapter': {'name': 'tinycnn_cpu', 'version': 1},
                'runtime': {'python': 'contract-only', 'device': 'cpu'}, 'problems': [],
                **self.pipelines.definition_identity()}

    def validate(self, graph=None):
        graph = graph or self.graph
        with patch.object(self.pipelines, 'probe', return_value=self.ready()):
            return self.pipelines.validate(graph['id'], {'revision': graph['revision']})


class PipelineTests(WorkspaceCase):
    def test_graph_cas_clone_and_presentation_digest(self):
        graph = copy.deepcopy(self.graph)
        original = execution_digest(graph)
        graph['layout'] = {'train': {'x': 80, 'y': 140}}
        graph['name'] = 'Renamed recipe'
        saved = self.pipelines.save(graph['id'], {'revision': 1, 'document': graph})
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(execution_digest(saved), original)
        with self.assertRaises(WorkbenchError) as failure:
            self.pipelines.save(graph['id'], {'revision': 1, 'document': graph})
        self.assertEqual(failure.exception.code, 'stale')
        clone = self.pipelines.clone(graph['id'], {'name': 'Independent recipe'})
        self.assertNotEqual(clone['id'], graph['id'])
        self.assertEqual(clone['revision'], 1)
        self.assertEqual(execution_digest(clone), original)
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.pipelines.get(saved['id']), saved)

    def test_invalid_disconnected_and_fixture_graphs_never_admit(self):
        graph = copy.deepcopy(self.graph)
        graph['edges'].pop()
        saved = self.pipelines.save(graph['id'], {'revision': 1, 'document': graph})
        result = self.validate(saved)
        self.assertFalse(result['valid'])
        self.assertEqual(result['errors'][0]['path'], 'edges')
        graph = copy.deepcopy(saved)
        graph['mode'] = 'fixture'
        with self.assertRaises(WorkbenchError):
            self.pipelines.save(graph['id'], {'revision': 2, 'document': graph})
        graph = copy.deepcopy(saved)
        graph['nodes'][2]['type'] = 'audio_transcription'
        saved = self.pipelines.save(graph['id'], {'revision': 2, 'document': graph})
        result = self.validate(saved)
        self.assertEqual(result['status'], 'unsupported')

    def test_parameters_definition_runtime_and_release_fail_closed(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'][2]['parameters']['epochs'] = 6
        saved = self.pipelines.save(graph['id'], {'revision': 1, 'document': graph})
        self.assertFalse(self.validate(saved)['valid'])

        graph['revision'] = 2
        graph['nodes'][2]['parameters']['epochs'] = 1
        graph['nodes'][2]['definition_version'] = 2
        saved = self.pipelines.save(graph['id'], {'revision': 2, 'document': graph})
        self.assertEqual(self.validate(saved)['status'], 'stale')
        graph['revision'] = 3
        graph['nodes'][2]['definition_version'] = 1
        saved = self.pipelines.save(graph['id'], {'revision': 3, 'document': graph})
        with patch.object(self.pipelines, 'probe', return_value=dict(self.ready(), available=False)):
            self.assertEqual(self.pipelines.validate(saved['id'], {'revision': 4})['status'], 'unavailable')
        path = self.dataset.releases.locate(self.release['id'])
        path.write_bytes(path.read_bytes() + b'changed')
        self.assertFalse(self.validate(saved)['valid'])

    def test_giant_layout_coordinate_returns_typed_error(self):
        graph = copy.deepcopy(self.graph)
        graph['layout'] = {'train': {'x': 10**1000, 'y': 0}}
        with self.assertRaises(WorkbenchError):
            decode_graph(graph)

    def test_validation_token_binds_runtime_and_saved_revision(self):
        validation = self.validate()
        self.assertTrue(validation['valid'])
        with patch.object(self.pipelines, 'probe', return_value=self.ready()):
            graph, result, release = self.pipelines.snapshot(self.graph['id'], 1, validation['validation_token'])
        self.assertEqual(release['sha256'], self.release['id'])
        with patch.object(self.pipelines, 'probe', return_value=dict(self.ready(), runtime={'python': 'changed'})):
            with self.assertRaises(WorkbenchError) as failure:
                self.pipelines.snapshot(self.graph['id'], 1, validation['validation_token'])
        self.assertEqual(failure.exception.code, 'stale')
        saved = self.pipelines.save(self.graph['id'], {'revision': 1, 'document': self.graph})
        with self.assertRaises(WorkbenchError):
            self.pipelines.snapshot(saved['id'], 1, validation['validation_token'])

    def test_release_inspection_uses_frozen_bytes_and_honest_exposure(self):
        release = self.pipelines.inspect_release(self.release['id'])
        self.assertEqual(release['split_counts'], {'train': 2, 'validation': 2, 'test': 2})
        self.assertFalse(release['prior_test_exposure']['exposed'])
        row = self.rows[0]
        self.dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_classification', annotation={'label': 'corrected'}, groups=row['groups'], review='draft'))
        self.assertEqual(self.pipelines.inspect_release(self.release['id']), release)


if __name__ == '__main__':
    unittest.main()
