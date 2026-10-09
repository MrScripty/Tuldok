import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

import ai
import ai_codex
import ai_openrouter
from app import Dataset, Conflict
from fake_ai import start, RESULT


class AITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=Dataset(self.tmp.name);self.addCleanup(self.data.close)
        image=io.BytesIO();Image.new('RGB',(200,100),'beige').save(image,'PNG')
        self.sample=self.data.add(dict(image=base64.b64encode(image.getvalue()).decode(),session_id='s',book_id='b'))
        self.server,self.url,self.requests=start();self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.body=dict(provider='llamacpp',model='corners-test',server_url=self.url,sample_id=self.sample['id'],revision=1)

    def test_llamacpp_suggestion_is_not_saved_until_review(self):
        response=self.data.suggest(self.body)
        self.assertIsNone(self.data.sample(self.sample['id'])['annotation'])
        self.assertEqual(response['annotation']['corners'],RESULT['corners'])
        path,body,headers=self.requests[-1]
        self.assertEqual(path,'/v1/chat/completions')
        self.assertNotIn('Authorization',headers)
        self.assertIn('schema',body['response_format'])
        encoded=body['messages'][0]['content'][1]['image_url']['url']
        self.assertTrue(base64.b64decode(encoded.split(',')[1]).startswith(b'\xff\xd8'))
        saved=self.data.save(self.sample['id'],dict(book_id='b',session_id='s',revision=1,annotation=response['annotation']))
        self.assertEqual(saved['annotation']['suggested_by']['provider'],'llamacpp')

    def test_pumas_gateway_models_and_suggestion(self):
        body=dict(self.body,provider='pumas')
        catalog=ai.models(body)
        self.assertIn('corners-test',[item['id'] for item in catalog['models']])
        response=self.data.suggest(body)
        self.assertEqual(response['annotation']['corners'],RESULT['corners'])
        self.assertEqual(response['annotation']['suggested_by']['provider'],'pumas')
        self.assertEqual(self.requests[-1][0],'/v1/chat/completions')

    def test_ai_corner_identity_follows_book_rotation(self):
        for start in range(4):
            with self.subTest(start=start):
                response=self.data.suggest(dict(self.body,model='rotation-'+str(start)))
                corners=response['annotation']['corners']
                self.assertEqual([c['name'] for c in corners],[c['name'] for c in RESULT['corners']])
                expected=RESULT['corners'][start:]+RESULT['corners'][:start]
                self.assertEqual([(c['x'],c['y']) for c in corners],[(c['x'],c['y']) for c in expected])
                self.assertEqual(response['annotation']['corner_reference'],'book')
        self.assertIsNone(self.data.sample(self.sample['id'])['annotation'])

    def test_ambiguous_book_orientation_does_not_replace_label(self):
        with self.assertRaisesRegex(ValueError,'orientation'):
            self.data.suggest(dict(self.body,model='unknown-orientation'))
        self.assertIsNone(self.data.sample(self.sample['id'])['annotation'])

    def test_server_error_explains_missing_projector(self):
        with self.assertRaisesRegex(ai_codex.CodexError, 'HTTP 500.*mmproj'):
            self.data.suggest(dict(self.body,model='missing-projector'))
        self.assertIsNone(self.data.sample(self.sample['id'])['annotation'])

    def test_openrouter_catalog_and_auth(self):
        with patch.object(ai_openrouter,'BASE_URL',self.url):
            catalog=ai.models(dict(provider='openrouter',api_key='test-key'))
            self.assertEqual([m['id'] for m in catalog['models']],['corners-test'])
            response=self.data.suggest(dict(self.body,provider='openrouter',api_key='test-key'))
        path,body,headers=self.requests[-1]
        self.assertEqual(path,'/api/v1/chat/completions')
        self.assertEqual(headers['Authorization'],'Bearer test-key')
        self.assertEqual(headers['X-Title'],'Tuldok')
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertNotIn('test-key',json.dumps(response))

    def test_invalid_truncated_and_stale_results_do_not_change_labels(self):
        for model in ['invalid-corners','truncated']:
            with self.assertRaises((ValueError,ai_codex.CodexError)):
                self.data.suggest(dict(self.body,model=model))
        self.assertIsNone(self.data.sample(self.sample['id'])['annotation'])
        with self.assertRaises(Conflict):self.data.suggest(dict(self.body,revision=0))
        def changed(*args):
            self.data.save(self.sample['id'],dict(book_id='b',session_id='s',revision=1,annotation=RESULT))
            return RESULT,dict(provider='codex',model='corners-test',suggested_at='2026-09-12T00:00:00+00:00')
        with patch.object(ai,'suggest',side_effect=changed):
            with self.assertRaises(Conflict):self.data.suggest(self.body)

    def test_no_book_and_key_redaction(self):
        result=self.data.suggest(dict(self.body,model='no-book'))['annotation']
        self.assertFalse(result['book_present']);self.assertEqual(result['corners'],[])
        self.assertEqual(ai.safe_error(ValueError('secret'),{'api_key':'secret'}),'<redacted>')
        self.assertIsInstance(ai.safe_error(ValueError('bad'),[]),str)
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'env-secret'}):
            self.assertNotIn('env-secret',json.dumps(ai.codex_models()))

    def test_codex_protocol_and_tool_rejection(self):
        folder=Path(self.tmp.name)/'bin';folder.mkdir()
        executable=folder/'codex'
        script=Path(__file__).with_name('fake_ai_codex.py')
        executable.write_text('#!/usr/bin/env python3\nimport sys, runpy\nsys.path.insert(0,'+repr(str(script.parent))+')\nrunpy.run_path('+repr(str(script))+',run_name="__main__")\n')
        executable.chmod(0o755)
        with patch.dict(os.environ,{'PATH':str(folder)+os.pathsep+os.environ['PATH']}):
            result=self.data.suggest(dict(self.body,provider='codex',effort='high'))
            self.assertEqual(result['annotation']['corners'],RESULT['corners'])
            with self.assertRaises(ai_codex.CodexError):
                self.data.suggest(dict(self.body,provider='codex',model='tools'))
