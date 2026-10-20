"""Run unchanged canonical test methods with preregistered disposable catalogs."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import psycopg
from psycopg import sql
import test_extension_canonical_author as canonical
from metadata import Metadata

LEDGER = Path(__file__).with_name('owned-schemas.jsonl')

class OwnedCanonicalAuthorTests(canonical.CanonicalAuthorTests):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='pr108-canonical-ci-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = self.root / 'source'
        source.mkdir()
        identity = uuid.uuid4().hex
        schema = 'catalog_' + identity
        with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as conn:
            self.assertIsNone(conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone())
        with LEDGER.open('a') as handle:
            handle.write(json.dumps(dict(schema=schema, state='reserved', test=self.id())) + '\n')
        def cleanup():
            with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as conn:
                conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
                self.assertIsNone(conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone())
            with LEDGER.open('a') as handle:
                handle.write(json.dumps(dict(schema=schema, state='removed', test=self.id())) + '\n')
        self.addCleanup(cleanup)
        metadata = Metadata(self.root / 'catalog', dataset_id=identity)
        self.assertEqual(metadata.schema, schema)
        metadata.close()
        self.dataset = canonical.Dataset(self.root / 'catalog', project_roots={'canonical-fixture': source})
        self.addCleanup(self.dataset.close)
        self.owner = canonical.bind_owner(self, self.dataset)
        self.result = canonical.fixture.build_canonical_fixture(self.dataset, source)

loader = unittest.TestLoader()
suite = unittest.TestSuite()
if '--reproduce' in sys.argv:
    suite.addTest(OwnedCanonicalAuthorTests('test_new_project_exact_sources_full_catalog_and_model_controls_are_inert'))
else:
    suite.addTests(loader.loadTestsFromTestCase(OwnedCanonicalAuthorTests))
    suite.addTests(loader.loadTestsFromTestCase(canonical.CanonicalOracleBoundsTests))
    import test_canonical_candidate_packages as packages
    suite.addTests(loader.loadTestsFromTestCase(packages.CanonicalCandidatePackageTests))
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
