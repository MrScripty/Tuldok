"""Existing admission authority reused by the proposed structured bulk importer."""
from auth_helpers import bind_owner, ExplicitOwnerFixture
from postgres_helpers import drop_failure_trigger, install_failure_trigger
import base64
import hashlib
import io
import psycopg
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from app import Dataset


class RealImportFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dataset = Dataset(self.temp.name); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        image = io.BytesIO()
        Image.new('RGB', (24, 18), '#467e9a').save(image, 'PNG')
        self.image = image.getvalue()

    def payload(self, kind):
        body = dict(kind=kind, name='Local source', groups=['owned-source'], rights='Authored fixture')
        body.update(image=base64.b64encode(self.image).decode()) if kind == 'image' else body.update(text='cafe\u0301\r\n')
        return body

    def assert_source(self, record, kind):
        if kind == 'image':
            raw = (Path(self.temp.name) / 'images' / record['id'] / 'source').read_bytes()
            self.assertEqual(raw, self.image)
            self.assertEqual(record['provenance']['source_sha256'], hashlib.sha256(raw).hexdigest())
        else:
            self.assertEqual(self.dataset.db.execute('SELECT original_text FROM workbench_records WHERE id=%s', (record['id'],)).fetchone()[0], 'cafe\u0301\r\n')
            self.assertEqual(record['text'], 'café\n')

    def test_import_cannot_grant_review_or_replace_verified_source_facts(self):
        for kind in ('image', 'text'):
            for review in ('human_reviewed', 'programmatically_verified'):
                with self.subTest(kind=kind, review=review):
                    # Each case uses fresh storage; duplicate rejection is tested separately.
                    with tempfile.TemporaryDirectory() as folder:
                        dataset = Dataset(folder)
                        with ExplicitOwnerFixture.bootstrap(dataset).bound(dataset):
                            try:
                                body = self.payload(kind)
                                body.update(review=review, annotation={'label': 'approved'},
                                            provenance={'method': 'verified', 'source_sha256': 'forged', 'verifier': 'caller'})
                                record = dataset.workbench.import_asset(body)
                                self.assertEqual(record['review'], 'draft')
                                self.assertIsNone(record['annotation'])
                                self.assertEqual(record['groups'], ['owned-source'])
                                self.assertEqual(record['provenance']['method'], 'import')
                                self.assertNotIn('verifier', record['provenance'])
                                if kind == 'image':
                                    raw = (Path(folder) / 'images' / record['id'] / 'source').read_bytes()
                                    self.assertEqual(raw, self.image)
                                    self.assertEqual(record['provenance']['source_sha256'], hashlib.sha256(raw).hexdigest())
                                else:
                                    self.assertEqual(dataset.db.execute('SELECT original_text FROM workbench_records WHERE id=%s', (record['id'],)).fetchone()[0], 'cafe\u0301\r\n')
                                    self.assertEqual(record['text'], 'café\n')
                            finally:
                                dataset.close()

    def test_repeated_import_cannot_overwrite_review_groups_or_source_provenance(self):
        for kind in ('image', 'text'):
            with self.subTest(kind=kind):
                record = self.dataset.workbench.import_asset(self.payload(kind))
                saved = self.dataset.workbench.save(record['id'], dict(
                    revision=record['revision'], source_revision=record['source_revision'],
                    task=kind+'_classification', annotation={'label': 'human decision'},
                    review='human_reviewed', groups=record['groups']))
                repeated = dict(self.payload(kind), groups=['different-source'], rights='Changed claim')
                with self.assertRaises(ValueError) as error:
                    self.dataset.workbench.import_asset(repeated)
                self.assertIn('already', str(error.exception))
                self.assertEqual(self.dataset.workbench.get(saved['id']), saved)
                self.assert_source(saved, kind)
        self.assertEqual(self.dataset.workbench.query({})['total'], 2)

    def test_image_enrollment_storage_failure_leaves_no_partial_row_or_asset(self):
        # Exercise real PostgreSQL rollback after original image acquisition, before
        # Workbench source metadata is admitted. This is a system failure, not
        # a bad user row that a future bulk loop may silently skip.
        with self.dataset.db.transaction():
            install_failure_trigger(self.dataset.db, 'workbench_records', 'reject_import_metadata', 'injected enrollment failure', event='UPDATE OF groups_json')
        with self.assertRaisesRegex(psycopg.IntegrityError, 'injected enrollment failure'):
            self.dataset.workbench.import_asset(self.payload('image'))
        self.assertEqual(self.dataset.rows(), [])
        self.assertEqual(self.dataset.db.execute('SELECT COUNT(*) FROM workbench_records').fetchone()[0], 0)
        self.assertEqual(self.dataset.db.execute('SELECT COUNT(*) FROM workbench_history').fetchone()[0], 0)
        self.assertEqual(list((Path(self.temp.name) / 'images').iterdir()), [])
        with self.dataset.db.transaction():
            drop_failure_trigger(self.dataset.db, 'workbench_records', 'reject_import_metadata')
        admitted = self.dataset.workbench.import_asset(self.payload('image'))
        self.assertEqual(admitted['review'], 'draft')
        self.assertEqual(admitted['groups'], ['owned-source'])
        self.assert_source(admitted, 'image')

    def test_image_enrollment_history_failure_rolls_back_source_metadata_and_files(self):
        with self.dataset.db.transaction():
            install_failure_trigger(self.dataset.db, 'workbench_history', 'reject_import_history', 'injected initial history failure', condition="NEW.snapshot LIKE '%Authored fixture%'")
        with self.assertRaisesRegex(psycopg.IntegrityError, 'injected initial history failure'):
            self.dataset.workbench.import_asset(self.payload('image'))
        self.assertEqual(self.dataset.rows(), [])
        self.assertEqual(self.dataset.db.execute('SELECT COUNT(*) FROM workbench_records').fetchone()[0], 0)
        self.assertEqual(self.dataset.db.execute('SELECT COUNT(*) FROM workbench_history').fetchone()[0], 0)
        self.assertEqual(list((Path(self.temp.name) / 'images').iterdir()), [])
