"""Real authenticated note transport/cold reload; no model or recipe execution."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import project_workspace
import test_project_files_http as m1
import test_project_files_m2_http as m2

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ModelPortfolioHTTP(unittest.TestCase):
    cleanup_owned = m1.ProjectFilesHTTP.cleanup_owned
    select_host = m1.ProjectFilesHTTP.select_host
    request = m1.ProjectFilesHTTP.request
    state = m1.ProjectFilesHTTP.state
    envelope = m1.ProjectFilesHTTP.envelope
    action = m1.ProjectFilesHTTP.action
    create = m1.ProjectFilesHTTP.create
    arguments = m2.ProjectFilesM2HTTP.arguments
    transport = m2.ProjectFilesM2HTTP.transport
    call = m2.ProjectFilesM2HTTP.call

    def setUp(self):
        self.operations = []
        m1.ProjectFilesHTTP.setUp(self)
        gate = patch.object(project_workspace, 'M4_ENABLED', True)
        gate.start()
        self.addCleanup(gate.stop)

    def test_native_static_module_exact_note_revision_and_cold_reload(self):
        status, html = self.request('/project-files')
        self.assertEqual(status, 200)
        self.assertIn(b'/project-model-portfolio.js', html)
        self.assertIn(b'id="project-model-portfolio"', html)
        status, script = self.request('/project-model-portfolio.js')
        self.assertEqual(status, 200)
        self.assertEqual(script, (ROOT/'static/project-model-portfolio.js').read_bytes())
        opened = self.create()
        root = self.external/'alpha'
        (root/'notes').mkdir()
        paragraphs = {key: 'Literal retained '+key+' paragraph.' for key in
                      ('method','purpose','experiment','outcome','lesson','reproduction')}
        card_text = '\n\n'.join(paragraphs.values())+'\nOriginal evidence remains.\n'
        (root/'notes/model.md').write_text(card_text)
        card = self.call('file_adopt',kind='note',path='notes/model.md',expected_revision=0,
                         expected_sha256=hashlib.sha256(card_text.encode()).hexdigest())
        guide = dict(format='project_model_portfolio_v1',project_id=opened['project']['project_id'],
            title='Authored retained fixture',description='Synthetic presentation fixture; no scientific quality claim.',
            authorship='retrospective',groups=[dict(id='pressure',label='Pressure methods',parent=None,description='An authored group.')],
            models=[dict(id='fixture-fit',label='One retained fit',group_id='pressure',aliases=['Fixture'],review='source_reviewed',
                card=dict(file_id=card['id'],path='notes/model.md',revision=1,sha256=card['sha256']),summary=paragraphs)],relationships=[])
        raw=(json.dumps(guide,ensure_ascii=False)+'\n').encode()
        (root/'notes/00-fixture.portfolio.json').write_bytes(raw)
        saved=self.call('file_adopt',kind='note',path='notes/00-fixture.portfolio.json',expected_revision=0,
                        expected_sha256=hashlib.sha256(raw).hexdigest())
        observed=self.call('file_get',file_id=saved['id'],revision=1)
        self.assertEqual(observed['version']['text'].encode(),raw)
        self.assertEqual(json.loads(observed['version']['text']),guide)
        changed='A later authored card revision.\n'
        (root/'notes/model.md').write_text(changed)
        self.call('file_adopt',kind='note',path='notes/model.md',expected_revision=1,
                  expected_sha256=hashlib.sha256(changed.encode()).hexdigest())
        self.assertEqual(self.call('file_get',file_id=card['id'],revision=1)['version']['text'],card_text)
        self.assertEqual(self.call('file_get',file_id=card['id'])['version']['text'],changed)
        self.action('save')
        expected=(root/'.tuldok/project.json').read_bytes()
        self.action('close')
        cold=os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL')
        self.assertTrue(cold,'Independent cold role required for retained-note acceptance')
        self.select_host(self.path/'cold-control',{'fixture':self.external},cold)
        self.action('open',root='fixture',directory='alpha')
        self.assertEqual((root/'.tuldok/project.json').read_bytes(),expected)
        self.assertEqual(self.call('file_get',file_id=saved['id'],revision=1)['version']['text'].encode(),raw)
        retained=self.call('file_get',file_id=card['id'],revision=1)
        self.assertEqual(retained['version']['text'],card_text)
        self.assertEqual(retained['project_id'],guide['project_id'])
        self.assertEqual(self.call('file_get',file_id=card['id'])['version']['text'],changed)
        self.action('close')
