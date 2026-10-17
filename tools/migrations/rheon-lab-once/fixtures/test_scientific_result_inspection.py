"""Frozen historical scientific-result visibility regression; explicit offline use."""
from pathlib import Path
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

# The archived fixture and current app remain separate explicit import roots.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires explicitly isolated PostgreSQL')
class HistoricalResultInspection(unittest.TestCase):
    def test_large_archived_run_keeps_its_scientific_result_inspectable(self):
        import test_rheon_lab_migration as fixture
        from access import Access
        from metadata import Metadata
        from projects import Projects
        from workbench import WorkbenchError, encode

        case = fixture.PostgreSQLConversion('test_original_facts_archive_accounting_and_current_cold_read')
        self.addCleanup(case.doCleanups)
        original_backup = fixture.backup_catalog
        marker = 'independent-scientific-result-retained'

        def backup_large_history(catalog, archive, **kwargs):
            case.old_run['material']['opaque_source_description'] = 'M' * 70000
            case.old_run['result']['review_marker'] = marker
            source = Metadata(catalog, create=False, schema_version=8)
            try:
                with source.transaction():
                    source.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',
                                   (encode(case.old_run), case.run_id))
            finally:
                source.close()
            return original_backup(catalog, archive, **kwargs)

        with patch.object(fixture, 'backup_catalog', side_effect=backup_large_history):
            case.setUp()
        identity = case.prepare()
        prepared = fixture.converter._verify_stage(case.stage, identity)
        case.publish(identity)
        access = Access(case.metadata, case.catalog)
        owner = Projects(SimpleNamespace(db=case.metadata, lock=case.metadata.lock, access=access), prepared['roots'])
        self.addCleanup(owner.close)
        previews = []
        with access.bind(case.token):
            for saved in prepared['projects']:
                for reference in saved['manifest']['evidence']:
                    try:
                        previews.append(owner.evidence(saved['id'], reference['id'])['text'])
                    except WorkbenchError:
                        # Original large/binary evidence may stay opaque; a current
                        # readable representation must still expose scientific facts.
                        continue
        self.assertTrue(any(marker in text for text in previews),
                        'Converted publication hid original Run result behind the evidence preview limit')


if __name__ == '__main__':
    unittest.main()
