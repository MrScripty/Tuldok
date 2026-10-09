"""Reconciled native detection changes the actual corpus family proof, not targets."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import zipfile

from PIL import Image
from app import Dataset
from workbench import WorkbenchError
from test_native_detection_import import native_fixture


class DetectionStackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.raw = native_fixture(self.path/'native-source', count=1, name_prefix='Combined family')
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            self.origin = json.loads(archive.read('manifest.json'))['records'][0]
        self.link = 'native-text-origin:'+hashlib.sha256(self.origin['id'].encode()).hexdigest()
        self.dataset = Dataset(self.path/'destination'); self.addCleanup(self.dataset.close)
        self.w = self.dataset.workbench
        self.documents = []
        for index in range(3):
            row = self.w.import_asset(dict(kind='text', name=f'Combined corpus {index}',
                text=(f'Combined document {index}: café 🙂 山. Preserve canonical text and final newlines.\n'*4)+'\n',
                groups=[self.link if index == 0 else f'combined-corpus-{index}'], rights='Authored compatibility fixture'))
            self.documents.append(self.w.save(row['id'], dict(row, task='text_corpus',
                annotation={'note':'Reviewed authored compatibility document.'}, review='human_reviewed')))
        self.body = dict(format='text_corpus_v1', items=[{key:row[key] for key in ('id','revision','source_revision')} for row in self.documents],
            ratios=dict(train=34,validation=33,test=33), seed=42)

    def prepared(self):
        return self.dataset.native_detection_imports.prepare(dict(source_name='native.zip', archive=base64.b64encode(self.raw).decode()))['rows'][0]

    def test_native_admission_preserves_targets_sets_searches_and_revokes_corpus_family_proof(self):
        saved = self.dataset.selections.create(dict(name='Fixed combined documents',items=self.body['items']))
        search = self.dataset.searches.create(dict(name='Dynamic corpus',criteria=dict(q='',kind='text',task='text_corpus',review='human_reviewed',sort='',label='',group='',rights='')))
        sys.path.insert(0,str(Path(__file__).parent/'fixtures'))
        from image_classification_fixture import populate
        classifiers = populate(self.dataset)
        classification = dict(format='image_classification_v1',items=[{key:r[key] for key in ('id','revision','source_revision')} for r in classifiers],ratios=self.body['ratios'],seed=42)
        cp = self.dataset.releases.preview(classification); self.assertTrue(cp['eligible'],cp)
        frozen = self.dataset.releases.create(dict(classification,preview_token=cp['preview_token']))
        classifier_zip = self.dataset.releases.locate(frozen['id']).read_bytes()
        preview = self.dataset.releases.preview(self.body); self.assertTrue(preview['eligible'],preview)
        row = self.prepared();receipt = self.dataset.native_detection_imports.admit(dict(token=row['token'],request_id=uuid.uuid4().hex))
        imported = self.w.get(receipt['record_id'])
        self.assertEqual((imported['review'],imported['provenance']['rights'],imported['source_split']),('draft','unknown','train'))
        for document in self.documents:self.assertEqual(self.w.get(document['id']),document)
        loaded = self.dataset.selections.load(saved['id'])
        self.assertTrue(loaded['current'])
        self.assertEqual(loaded['selection'],saved)
        self.assertEqual(self.dataset.searches.get(search['id']),search)
        with self.assertRaises(WorkbenchError) as error:
            self.dataset.releases.create(dict(self.body,preview_token=preview['preview_token']))
        self.assertEqual(error.exception.status,409)
        fresh = self.dataset.releases.preview(self.body);self.assertTrue(fresh['eligible'],fresh)
        self.assertNotEqual(preview['preview_token'],fresh['preview_token'])
        self.assertEqual(fresh['assignments'][self.documents[0]['id']],'train')
        self.assertEqual(self.dataset.releases.locate(frozen['id']).read_bytes(),classifier_zip)
        self.assertEqual(self.dataset.releases.preview(classification)['preview_token'],cp['preview_token'])
        release = self.dataset.releases.create(dict(self.body,preview_token=fresh['preview_token']))
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            members = [member for family in manifest['protected_components'].values() for member in family]
            self.assertIn(imported['id'],[member['id'] for member in members])
            for split in ('train','validation','test'):
                expected = b''.join(document['text'].encode()+b'\n\n' for document in sorted(self.documents,key=lambda r:r['id']) if fresh['assignments'][document['id']]==split)
                self.assertEqual(archive.read(split+'.txt'),expected)

    def test_conflicting_native_admission_preserves_existing_corpus_preview_and_sources(self):
        image = Image.new('RGB',(3,3),'orange');data=io.BytesIO();image.save(data,'PNG')
        fixed = self.w.import_asset(dict(kind='image',image=base64.b64encode(data.getvalue()).decode(),
            name='Existing validation family',groups=[self.link],rights='Retained existing fixture'),source_split='validation')
        preview = self.dataset.releases.preview(self.body);self.assertTrue(preview['eligible'],preview)
        before = list(self.dataset.db.iterdump());source = self.w.get(fixed['id']);row = self.prepared()
        with self.assertRaises(WorkbenchError) as error:
            self.dataset.native_detection_imports.admit(dict(token=row['token'],request_id=uuid.uuid4().hex))
        self.assertEqual(error.exception.status,409)
        self.assertEqual(list(self.dataset.db.iterdump()),before)
        self.assertEqual(self.w.get(fixed['id']),source)
        self.assertEqual(self.dataset.releases.preview(self.body)['preview_token'],preview['preview_token'])


if __name__ == '__main__':unittest.main()
