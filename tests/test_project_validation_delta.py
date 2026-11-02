"""Edit-scoped validation re-checks exactly what an edit can affect."""
import unittest

from project_projection import validate_project_records
from project_validation_delta import COMPONENTS, ValidationDelta, edit_delta
from workbench import WorkbenchError

PROJECT = 'a' * 32
BROKEN_TEXT = dict(family='workbench_text', id='broken', document=dict(format='workbench_text_v1', text=17))


class DeltaRules(unittest.TestCase):
    def test_new_artifact_declarations_touch_no_component(self):
        delta = ValidationDelta(frozenset({('project_artifact', 'b' * 64)}), added=frozenset({('project_artifact', 'b' * 64)}))
        self.assertEqual(delta.families, frozenset())
        self.assertFalse(any(delta.touches(component) for component in COMPONENTS))
        changed = ValidationDelta(frozenset({('project_artifact', 'b' * 64)}))
        self.assertTrue(changed.touches('history'), 'A changed existing declaration is re-checked')

    def test_receipt_rules(self):
        delta = ValidationDelta(frozenset({('workbench_record', 'r'), ('project_operation', 'new')}),
                                frozenset({'data.import_text'}))
        self.assertTrue(delta.receipt_needed('data.annotate', ('project_operation', 'old')), 'Data receipts bind to changed data records')
        self.assertFalse(delta.receipt_needed('files.adopt', ('project_operation', 'old')))
        self.assertTrue(delta.receipt_needed('files.adopt', ('project_operation', 'new')), 'The new receipt is always checked')
        self.assertTrue(delta.receipt_needed('unclassified.operation', ('project_operation', 'old')), 'Unknown receipts are always checked')
        runtime = ValidationDelta(frozenset({('project_operation', 'new')}), frozenset({'runtime.capture'}))
        self.assertTrue(runtime.receipt_needed('runtime.abandon', ('project_operation', 'old')), 'Shared key spaces are re-checked')
        self.assertFalse(runtime.receipt_needed('studies.save', ('project_operation', 'old')))
        self.assertTrue(ValidationDelta(frozenset(), frozenset({'studies.save'})).history_receipt_added())


class ScopedValidation(unittest.TestCase):
    def validate(self, records, delta):
        with edit_delta(delta):
            validate_project_records(records, project_id=PROJECT, artifacts=None)

    def test_touched_component_still_rejects_an_invalid_change(self):
        with self.assertRaises(WorkbenchError):
            self.validate([BROKEN_TEXT], ValidationDelta(frozenset({('workbench_text', 'broken')})))
        with self.assertRaises(WorkbenchError):
            validate_project_records([BROKEN_TEXT], project_id=PROJECT, artifacts=None)

    def test_untouched_component_is_not_revalidated(self):
        # The base checkpoint is assumed validated; an unrelated edit skips data.
        self.validate([BROKEN_TEXT], ValidationDelta(frozenset({('project_file', 'other')})))

    def test_identity_and_claim_checks_always_run(self):
        duplicate = [BROKEN_TEXT, dict(BROKEN_TEXT)]
        with self.assertRaises(WorkbenchError):
            self.validate(duplicate, ValidationDelta(frozenset({('project_file', 'other')})))
        unknown = [dict(family='unclaimed_family', id='x', document={})]
        with self.assertRaises(WorkbenchError):
            self.validate(unknown, ValidationDelta(frozenset({('project_file', 'other')})))


if __name__ == '__main__':
    unittest.main()
