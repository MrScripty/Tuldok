import base64
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from PIL import Image
from app import Dataset, make_handler
from workbench import WorkbenchError, validate_annotation
from dataset_recipes import candidates, generate


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.workbench = self.dataset.workbench

    def text(self, text='Hello 😀 café', group='source-a', parents=None):
        return self.workbench.import_asset(dict(kind='text', text=text, name='Note', groups=[group], parents=parents or []))

    def review(self, row, task='text_classification', annotation=None):
        return self.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task=task, annotation=annotation or {'label':'greeting'}, groups=row['groups'], review='human_reviewed'))

    def release(self, rows, ratios=None):
        return self.dataset.releases.create(dict(items=[{k:r[k] for k in ('id','revision','source_revision')} for r in rows],
            ratios=ratios or dict(train=100,validation=0,test=0), seed=42))

    def test_normalized_unicode_revisions_and_reopen(self):
        row = self.text('Hello 😀 cafe\u0301\r\n')
        self.assertEqual(row['text'], 'Hello 😀 café\n')
        saved = self.review(row, 'text_entities', {'spans':[dict(label='emoji',start=6,end=7)]})
        self.assertEqual(saved['revision'], 2)
        with self.assertRaises(WorkbenchError): self.review(row)
        with self.assertRaises(WorkbenchError): self.text('Hello 😀 café\n')
        self.dataset.close(); self.dataset = Dataset(self.tmp.name); self.workbench = self.dataset.workbench
        self.assertEqual(len(self.workbench.history(row['id'])), 2)
        self.assertEqual(self.workbench.get(row['id'])['annotation'], saved['annotation'])

    def test_real_image_import_oriented_bounds_and_source_conflict(self):
        source=io.BytesIO(); exif=Image.Exif(); exif[274]=6
        Image.new('RGB',(80,60),'beige').save(source,'JPEG',exif=exif)
        row=self.workbench.import_asset(dict(kind='image',image=base64.b64encode(source.getvalue()).decode(),
            name='portrait.jpg',groups=['shoot-one'],rights='User-owned fixture'))
        self.assertEqual((row['width'],row['height']),(60,80))
        self.assertEqual((Path(self.tmp.name)/'images'/row['id']/'source').read_bytes(),source.getvalue())
        row=self.review(row,'image_detection',{'boxes':[dict(label='frame',x=0,y=0,width=60,height=80)]})
        for box in (dict(label='bad',x=0,y=0,width=61,height=80),dict(label='bad',x=True,y=0,width=2,height=3)):
            with self.assertRaises(WorkbenchError):validate_annotation('image_detection',{'boxes':[box]},row)
        sample=self.dataset.sample(row['id'])
        self.dataset.save(sample['id'],dict(revision=sample['revision'],book_id='',session_id=sample['session_id'],
            split='train',annotation=dict(book_present=False,crop_suitable=False,corners=[])))
        with self.assertRaises(WorkbenchError):self.review(row,'image_classification',{'label':'frame'})
        with self.assertRaises(WorkbenchError):self.release([row])

    def test_intent_recipe_labels_and_template_lineage(self):
        rows=list(candidates('intent-requests-v1',73,9))
        for index,(payload,target,provenance) in enumerate(rows):
            self.assertEqual(target['label'], ('create','reschedule','cancel')[index//3])
            self.assertEqual(payload['groups'],[f'intent-template:{index}'])
            self.assertEqual(provenance['factors']['template'],index)
            self.assertTrue(payload['text'].strip())
        result=generate(self.workbench,dict(recipe='intent-requests-v1',seed=73,count=9))
        self.assertEqual(len(result['created']),9)
        self.assertEqual(len(generate(self.workbench,dict(recipe='intent-requests-v1',seed=73,count=9))['rejected']),9)

    def test_invalid_targets_and_programmatic_forgery(self):
        row = self.text()
        for span in [dict(label='x',start=True,end=2), dict(label='x',start=0,end=100), dict(label='x',start=2,end=1)]:
            with self.assertRaises(WorkbenchError): validate_annotation('text_entities', {'spans':[span]}, row)
        with self.assertRaises(WorkbenchError):
            self.workbench.save(row['id'], dict(revision=1,source_revision=1,task='text_classification',annotation={'label':'x'},groups=['a'],review='programmatically_verified'))
        with self.assertRaises(WorkbenchError): self.release([row])

    def test_search_filter_sort_pagination(self):
        self.review(self.text('first', 'group-one')); self.text('second', 'group-two')
        result=self.workbench.query(dict(q='greeting',review='human_reviewed',kind='text',sort='name',limit='1'))
        self.assertEqual(result['total'],1); self.assertEqual(result['analysis']['labels'],{'greeting':1})
        self.assertNotIn('text',result['items'][0])
        for options in ({'limit':0},{'offset':-1},{'kind':'video'},{'sort':'random'}):
            with self.assertRaises(WorkbenchError):self.workbench.query(options)

    def test_seeded_pixels_match_targets_and_duplicates_rejected(self):
        batch=list(candidates('rectangles-v1',42,8))
        self.assertEqual(batch,list(candidates('rectangles-v1',42,8)))
        colors={'red':(235,70,70),'blue':(60,140,235),'yellow':(235,205,60)}
        for payload, annotation, provenance in batch:
            with Image.open(io.BytesIO(base64.b64decode(payload['image']))) as image:
                for box in annotation['boxes']:
                    x,y,w,h=(box[k] for k in ('x','y','width','height'))
                    self.assertEqual(image.getpixel((x,y)),colors[box['label']])
                    self.assertEqual(image.getpixel((x+w-1,y+h-1)),colors[box['label']])
                    self.assertNotEqual(image.getpixel((x+w,y+h)),colors[box['label']])
        result=generate(self.workbench,dict(recipe='rectangles-v1',seed=42,count=8))
        self.assertEqual(len(result['created']),8)
        repeat=generate(self.workbench,dict(recipe='rectangles-v1',seed=42,count=8))
        self.assertEqual(len(repeat['rejected']),8)
        for item in result['created']: self.assertEqual(self.workbench.get(item['id'])['review'],'programmatically_verified')

    def test_frozen_mixed_release_consumer_and_tamper(self):
        generated=generate(self.workbench,dict(recipe='rectangles-v1',seed=21,count=3))
        rows=[self.workbench.get(r['id']) for r in generated['created']]
        rows.append(self.review(self.text(), 'text_entities', {'spans':[dict(label='emoji',start=6,end=7)]}))
        release=self.release(rows)
        path=self.dataset.releases.locate(release['id']); original=path.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),release['id'])
        self.assertEqual(self.release(rows)['id'],release['id'])
        with zipfile.ZipFile(path) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            coco=json.loads(archive.read('train/coco.json'))
            self.assertEqual(len(coco['images']),3)
            self.assertEqual(len(manifest['records']),4)
            for record in manifest['records']:
                data=archive.read(record['asset'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),record['asset_sha256'])
                if record['kind']=='image':
                    with Image.open(io.BytesIO(data)) as image:self.assertEqual(image.size,(record['width'],record['height']))
                else:self.assertEqual(data.decode()[6:7],'😀')
            category_ids={c['id'] for c in coco['categories']}
            for target in coco['annotations']:self.assertIn(target['category_id'],category_ids)
        self.review(rows[-1])
        with self.assertRaises(WorkbenchError):self.release(rows)
        sample=self.dataset.sample(rows[0]['id']); self.dataset.delete(sample['id'], {'revision':sample['revision']})
        self.assertEqual(path.read_bytes(),original)
        self.dataset.close(); self.dataset=Dataset(self.tmp.name); self.workbench=self.dataset.workbench
        self.assertEqual(self.dataset.releases.locate(release['id']).read_bytes(),original)
        with self.assertRaises(WorkbenchError):self.release([rows[0]])
        (Path(self.tmp.name)/'images'/rows[1]['id']/'image.png').write_bytes(b'tampered')
        with self.assertRaises(WorkbenchError):self.release([rows[1]])
        self.assertEqual(list((Path(self.tmp.name)/'releases').glob('.building-*')),[])

    def test_unselected_lineage_bridge_and_impossible_splits(self):
        a=self.review(self.text('a','a')); b=self.review(self.text('b','b'))
        self.text('bridge','bridge',[a['id'],b['id']])
        c=self.review(self.text('c','c')); d=self.review(self.text('d','d'))
        result=self.release([a,b,c,d],dict(train=50,validation=25,test=25))
        with zipfile.ZipFile(self.dataset.releases.locate(result['id'])) as archive:
            rows=json.loads(archive.read('manifest.json'))['records']; splits={r['id']:r['split'] for r in rows}
        self.assertEqual(splits[a['id']],splits[b['id']]); self.assertEqual(len(set(splits.values())),3)
        with self.assertRaises(WorkbenchError):self.release([a,b],dict(train=50,validation=50,test=0))

    def test_deleted_source_retains_live_legacy_lineage_after_reopen(self):
        created=generate(self.workbench,dict(recipe='rectangles-v1',seed=901,count=2))['created']
        first,second=[self.workbench.get(item['id']) for item in created]
        child=self.review(self.text('derived from first','child',[first['id']]))
        for image in (first,second):
            sample=self.dataset.sample(image['id'])
            self.dataset.save(sample['id'],dict(revision=sample['revision'],book_id='shared-book',
                session_id=sample['session_id'],split='test',
                annotation=dict(book_present=False,crop_suitable=False,corners=[])))
        sample=self.dataset.sample(first['id'])
        self.dataset.delete(first['id'],dict(revision=sample['revision']))
        self.dataset.close();self.dataset=Dataset(self.tmp.name);self.workbench=self.dataset.workbench
        retained=self.workbench.get(first['id'])
        self.assertFalse(retained['source_available']);self.assertTrue(retained['source_lineage_known'])
        self.assertEqual((retained['book_id'],retained['source_split']),('shared-book','test'))
        second=self.workbench.get(second['id'])
        with self.assertRaises(WorkbenchError):self.release([child,second],dict(train=50,validation=0,test=50))
        unrelated=self.review(self.text('independent','independent'))
        result=self.release([child,second,unrelated],dict(train=50,validation=0,test=50))
        with zipfile.ZipFile(self.dataset.releases.locate(result['id'])) as archive:
            rows=json.loads(archive.read('manifest.json'))['records']
        splits={record['id']:record['split'] for record in rows}
        self.assertEqual(splits[child['id']],'test');self.assertEqual(splits[second['id']],'test')
        self.assertEqual(splits[unrelated['id']],'train')
        # A pre-fix deletion cannot have its latest relationships reconstructed.
        # Removing the fixture tombstone simulates that persisted migration state.
        with self.dataset.db:self.dataset.db.execute('DELETE FROM workbench_deleted_sources WHERE id=?',(first['id'],))
        with self.assertRaises(WorkbenchError):self.release([child],dict(train=100,validation=0,test=0))

    def test_http_static_export_and_errors(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        root=f'http://127.0.0.1:{server.server_port}'
        for route in ('/workbench','/workbench.js','/workbench.css'):
            with urllib.request.urlopen(root+route) as response:self.assertEqual(response.status,200)
        release=self.release([self.review(self.text())])
        with urllib.request.urlopen(root+release['url']) as response:self.assertTrue(response.read().startswith(b'PK'))
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(root+'/api/workbench/releases/invalid.zip')
        self.assertEqual(error.exception.code,400)
