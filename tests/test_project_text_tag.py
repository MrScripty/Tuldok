"""The scalar text response tag must not copy unrelated project metadata."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import project_fork

from project_projection import _TextView


class TextTagTests(unittest.TestCase):
    def test_text_records_does_not_clone_unrelated_active_documents(self):
        unrelated = dict(family='project_artifact', id='c' * 64,
                         document=dict(format='project_artifact_v1', sha256='c' * 64, bytes=4))
        note = dict(family='workbench_text', id='d' * 32,
                    document=dict(current=dict(kind='text', text='Unique note 山')))
        summary = dict(project_id='a' * 32, checkpoint='b' * 64)
        session = SimpleNamespace(summary=summary,
                                  snapshot=dict(summary, records=[unrelated, note]),
                                  check_current=lambda: None)
        copied = []
        original = project_fork.copy.deepcopy

        def observe(value):
            if value is unrelated:
                copied.append(value['id'])
            return original(value)

        with patch.object(project_fork, 'copy', SimpleNamespace(deepcopy=observe)):
            result = _TextView(SimpleNamespace(session=session)).records()
        self.assertEqual(result, dict(summary, items=[dict(kind='text', text='Unique note 山')]))
        self.assertEqual(copied, [], 'Text list cloned an unrelated active document')
        result['items'][0]['text'] = 'Caller mutation'
        self.assertEqual(note['document']['current']['text'], 'Unique note 山')

    def test_text_tag_reads_scalar_summary_without_a_record_snapshot(self):
        class Session:
            summary = dict(project_id='a' * 32, name='Owned project', checkpoint='b' * 64)

            @property
            def snapshot(self):
                raise AssertionError('Text response tag copied the full record graph')

        session = Session()
        view = _TextView(SimpleNamespace(session=session))
        original = dict(items=[dict(text='Authored note 漢字')])
        result = view._tag(original)
        self.assertEqual(result, dict(original, project_id='a' * 32, checkpoint='b' * 64))
        self.assertNotIn('name', result)
        self.assertEqual(original, dict(items=[dict(text='Authored note 漢字')]))
        result['project_id'] = 'caller edit'
        self.assertEqual(session.summary['project_id'], 'a' * 32)
