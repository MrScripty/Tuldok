"""Pure pre-target driver guards, never an actual restore or training pass."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import qualify_extension_restored_classifier as driver


class RestoredClassifierGuards(unittest.TestCase):
    def test_only_a_passed_actual_rootless_restore_with_new_destination_is_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);output=root/'output';destination=output/'restored-catalog'
            destination.mkdir(parents=True);(destination/'.restore-receipt-fixture.json').write_text('{}')
            document=dict(format='extension_ab_retention_qualification_v1',state='rootless_retention_verified_disable_pending',
                source_unchanged=True,restored_database_retained=True,source=str(root/'source'),output=str(output),
                restored_database='tuldok_ab_retention_'+'a'*32)
            path=root/'report.json'
            def read(value):path.write_text(json.dumps(value));return driver.read_report(path)
            selected,actual,db,sha=read(document)
            self.assertEqual(actual,destination);self.assertEqual(len(sha),64)
            for change in (dict(state='in_progress'),dict(state='failed'),dict(source_unchanged=False),
                           dict(restored_database_retained=False),dict(restored_database='tuldok_test'),
                           dict(source=str(destination))):
                value=copy.deepcopy(document);value.update(change)
                with self.subTest(change=change),self.assertRaises(RuntimeError):read(value)
            (destination/'.restore-receipt-fixture.json').unlink()
            with self.assertRaises(RuntimeError):read(document)
