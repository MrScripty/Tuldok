"""Read the adopted measurement family without cloning unrelated retained facts.

Real canonical files and real session freshness guards; no SQL reconstruction
or packet import is claimed by this focused fixture.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import project_measurements
import project_session
from project_projection import validate_project_records
from project_store import ProjectStore, ProjectStoreError
from test_project_receipt_validation import candidate, PROJECT


class MeasurementReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-measurement-read-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)/'project'
        self.store = ProjectStore.create(self.root, 'Measurement read fixture', 'new', 'a'*64)
        self.addCleanup(self.store.close)
        self.records = candidate()
        self.records.append(dict(family='project_artifact', id='f'*64,
            document=dict(format='project_artifact_v1', sha256='f'*64, bytes=7)))
        validate_project_records(self.records, project_id=PROJECT, artifacts=None)
        snapshot = self.store.commit(self.records, self.store.summary()['checkpoint'], 'seed', 'b'*64)
        self.session = object.__new__(project_session.ProjectSession)
        self.session.store, self.session.available = self.store, True
        self.session._snapshot, self.session.lock = copy.deepcopy(snapshot), threading.RLock()
        self.owner = object.__new__(project_measurements.ProjectMeasurements)
        self.owner.session = self.session
        self.expected = {r['id']: copy.deepcopy(r['document']) for r in self.records
                         if r['family'] == project_measurements.FAMILY}

    def test_documents_are_literal_independent_and_do_not_copy_unrelated_graph(self):
        original = project_session.copy_validated_json
        unrelated = []
        def observe(value):
            if isinstance(value, dict) and 'records' in value:
                unrelated.extend(r['id'] for r in value['records'] if r['id'] == 'f'*64)
            return original(value)
        with patch.object(project_session, 'copy_validated_json', observe):
            result = self.owner._documents()
        self.assertEqual(result, self.expected)
        self.assertEqual(unrelated, [], 'Measurement read copied an unrelated retained envelope')
        next(iter(result.values()))['source']['path'] = 'caller-edited.json'
        self.assertEqual(self.owner._documents(), self.expected)
        self.assertEqual(self.session._snapshot, self.store.snapshot())

    def test_lookup_reads_every_canonical_file_without_redecoding_adopted_material(self):
        with patch.object(self.store, '_record_file', wraps=self.store._record_file) as reads, \
                patch.object(project_measurements, 'material_records',
                    side_effect=AssertionError('Read-only lookup redecoded adopted material')):
            self.assertEqual(self.owner._documents(), self.expected)
        self.assertEqual(reads.call_count, len(self.records), 'All current files must still be read and hashed')

    def test_unavailable_projection_fails_before_any_store_read(self):
        self.session.available = False
        with patch.object(self.store, 'summary', side_effect=AssertionError('Unavailable store read')):
            with self.assertRaises(project_session.ProjectSessionError) as caught:
                self.owner._documents()
        self.assertEqual(caught.exception.code, 'projection_unavailable')

    def test_other_family_publication_requires_reopen(self):
        changed = copy.deepcopy(self.records)
        changed[-1]['document']['bytes'] = 8
        self.store.commit(changed, self.store.summary()['checkpoint'], 'other', 'c'*64)
        with self.assertRaises(project_session.ProjectSessionError) as caught:
            self.owner._documents()
        self.assertEqual(caught.exception.code, 'stale_project')

    def test_same_length_unselected_corruption_with_restored_mtime_is_rejected(self):
        inventory = json.loads((self.root/'.tuldok/project.json').read_bytes())['inventory']
        entry = next(r for r in inventory if r['id'] == 'f'*64)
        path = self.root/'.tuldok'/entry['path']
        before, info = path.read_bytes(), path.stat()
        changed = before.replace(b'"bytes": 7', b'"bytes": 8')
        self.assertNotEqual(changed, before)
        self.assertEqual(len(changed), len(before))
        path.chmod(0o600)
        path.write_bytes(changed)
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaises(ProjectStoreError) as caught:
            self.owner._documents()
        self.assertEqual(caught.exception.code, 'stale')

    def test_family_can_be_empty_and_returned_snapshot_contract_stays_complete(self):
        records = [r for r in self.records if r['family'] not in (project_measurements.FAMILY,'project_operation')]
        validate_project_records(records, project_id=PROJECT, artifacts=None)
        self.session._snapshot = self.store.commit(records, self.store.summary()['checkpoint'], 'empty', 'd'*64)
        self.assertEqual(self.owner._documents(), {})
        snapshot = self.session.snapshot
        self.assertEqual(snapshot, self.store.snapshot())
        snapshot['records'].clear()
        self.assertEqual(self.session.snapshot, self.store.snapshot())


if __name__ == '__main__':
    unittest.main()
