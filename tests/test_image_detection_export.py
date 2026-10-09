"""Authored QA labels simulate review states; no actual human-labelled corpus.

Consumer-specific custody, limits, target transport and atomic publication.
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import struct
import zlib
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures'))
from app import Dataset
import image_detection_export as projection
from image_detection_fixture import populate, LABEL
from workbench import WorkbenchError, encode


class DetectionReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(self.dataset.close)
        self.w = self.dataset.workbench
        self.rows = populate(self.dataset)

    def body(self):
        return dict(format=projection.FORMAT, items=[{k: r[k] for k in ('id', 'revision', 'source_revision')}
                    for r in self.rows], ratios={'train':34, 'validation':33, 'test':33}, seed=42)

    def freeze(self):
        body = self.body()
        preview = self.dataset.releases.preview(body)
        self.assertTrue(preview['eligible'], preview)
        return self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))

    def blocked(self, text):
        before = '\n'.join(self.dataset.db.iterdump())
        p = self.dataset.releases.preview(self.body())
        self.assertFalse(p['eligible'], p)
        self.assertIsNone(p['preview_token'])
        self.assertIn(text, str(p['blockers']))
        with self.assertRaises(WorkbenchError):
            self.dataset.releases.create(dict(self.body(), preview_token='a'*64))
        self.assertEqual(before, '\n'.join(self.dataset.db.iterdump()))
        self.assertEqual(list(self.dataset.releases.path.iterdir()), [])

    def stored(self, key, value, index=0):
        self.dataset.db.execute(f'UPDATE workbench_records SET {key}=? WHERE id=?', (value, self.rows[index]['id']))
        self.dataset.db.commit()

    def test_roundtrip_hashes_original_annotations_rectangles_and_negatives(self):
        release = self.freeze()
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as z:
            m = json.loads(z.read('manifest.json'))
            self.assertEqual(m['max_objects'], 1)
            self.assertEqual(m['foreground_label'], LABEL)
            self.assertEqual(m['consumer'], projection.CONSUMER)
            self.assertEqual(len(z.namelist()), 14)
            originals = {r['id']:r for r in self.rows}
            for r in m['records']:
                for key in ('annotation','review','provenance','revision','source_revision','groups','parents','pixel_hash'):
                    self.assertEqual(r[key], originals[r['id']][key])
                self.assertEqual(hashlib.sha256(z.read(r['asset'])).hexdigest(), r['content_hash'])
                self.assertEqual(hashlib.sha256(z.read(r['mask_asset'])).hexdigest(), r['mask_sha256'])
                image = Image.open(io.BytesIO(z.read(r['mask_asset'])))
                self.assertEqual(image.size, (16,12))
                self.assertEqual(image.mode, 'L')
                self.assertLessEqual(set(image.tobytes()), {0,255})
                self.assertEqual(image.getbbox(), tuple(r['derived_target']['pixel_xyxy']) if r['annotation']['boxes'] else None)
                self.assertIn(r['export_group'], m['protected_components'])
                self.assertNotIn(LABEL, r['asset'])
            self.assertEqual(m['detection_counts'], {s:{'positive':1,'negative':1} for s in projection.SPLIT_MAPPING})
        self.assertEqual(release['artifact_bytes'], sum(i.file_size for i in z.infolist()))

    def test_preview_readonly_order_deterministic_and_old_release_immutable(self):
        before = '\n'.join(self.dataset.db.iterdump())
        self.dataset.releases.preview(self.body())
        self.assertEqual(before, '\n'.join(self.dataset.db.iterdump()))
        result = self.freeze()
        data = self.dataset.releases.locate(result['id']).read_bytes()
        self.rows.reverse()
        self.assertEqual(result['id'], self.freeze()['id'])
        self.stored('review', 'draft')
        self.assertEqual(data, self.dataset.releases.locate(result['id']).read_bytes())

    def test_review_and_task_requirements(self):
        for key,value,text in [('review','draft','human-reviewed'),('review','programmatically_verified','human-reviewed'),('task','image_caption','human-reviewed')]:
            with self.subTest(value=value):
                self.stored(key,value)
                self.blocked(text)
                self.stored(key,self.rows[0][key])

    def test_malformed_coordinates_targets_and_labels_block_before_analysis(self):
        original = self.rows[0]['annotation']
        box = original['boxes'][0]
        for annotation,text in [({'boxes':[dict(box,x=0.5,width=1)]},'integer'),
            ({'boxes':[dict(box,x=True)]},'finite'),({'boxes':[dict(box,x=10**400)]},'finite'),({'boxes':[dict(box,x=float('nan'))]},'finite'),
            ({'boxes':[dict(box,width=2)]},'fit'),({'boxes':[box,dict(box,x=0,y=0)]},'at most one'),
            ({'boxes':[dict(box,label=' padded ')]},'canonical'),({'boxes':'bad'},'Provide')]:
            with self.subTest(annotation=annotation):
                self.stored('annotation_json',json.dumps(annotation))
                self.blocked(text)
        self.stored('annotation_json',encode(original))

    def test_integral_float_edges_remain_unmodified(self):
        annotation = {'boxes':[dict(self.rows[0]['annotation']['boxes'][0],x=15.0,y=11.0,width=1.0,height=1.0)]}
        self.stored('annotation_json',encode(annotation))
        result = self.freeze()
        with zipfile.ZipFile(self.dataset.releases.locate(result['id'])) as z:
            row = next(r for r in json.loads(z.read('manifest.json'))['records'] if r['id']==self.rows[0]['id'])
            self.assertEqual(row['annotation'], annotation)
            self.assertIsInstance(row['annotation']['boxes'][0]['x'],float)

    def test_multilabel_and_all_negative_selections(self):
        annotation = self.rows[2]['annotation']
        self.stored('annotation_json',encode({'boxes':[dict(annotation['boxes'][0],label='other')]}),2)
        self.blocked('exactly one foreground')
        for i in range(6):
            self.stored('annotation_json',encode({'boxes':[]}),i)
        self.blocked('at least one positive')

    def test_empty_split_and_unbalanced_splits(self):
        # Consumer accepts no positives in one split; do not silently rebalance.
        self.stored('annotation_json',encode({'boxes':[]}),0)
        p=self.dataset.releases.preview(self.body())
        self.assertTrue(p['eligible'],p)
        self.assertTrue(any('train has no positives' in w for w in p['warnings']))
        self.rows=self.rows[:4]
        self.blocked('populate all requested splits')

    def test_count_and_snapshot_caps_before_selection_or_raster(self):
        body=self.body();body['items']=[body['items'][0]]*101
        with patch.object(self.w,'selection',side_effect=AssertionError('must preflight')):
            p=self.dataset.releases.preview(body)
        self.assertIn('1–100',str(p['blockers']))
        with patch.object(projection,'MAX_BYTES',100):
            self.blocked('40 MiB')

    def test_raster_caps_before_asset_lookup(self):
        for key,limit in [('MAX_PIXELS',191),('MAX_TOTAL_PIXELS',1000)]:
            with self.subTest(key=key),patch.object(projection,key,limit),patch.object(self.w,'asset',side_effect=AssertionError('no raster access')):
                self.blocked('raster bounds')

    def test_logical_archive_includes_masks_metadata_and_readme(self):
        p=self.dataset.releases.preview(self.body())
        total=p['artifact_bytes']
        with patch.object(projection,'MAX_BYTES',total-1000):
            self.blocked('including masks and metadata')
        with patch.object(projection,'MAX_BYTES',total+1000):
            self.freeze()

    def test_unknown_fields_missing_token_and_changed_settings(self):
        p=self.dataset.releases.preview(dict(self.body(),surprise=True))
        self.assertIn('Unknown detection',str(p['blockers']))
        with self.assertRaises(WorkbenchError):self.dataset.releases.create(self.body())
        p=self.dataset.releases.preview(self.body())
        with self.assertRaises(WorkbenchError):self.dataset.releases.create(dict(self.body(),seed=43,preview_token=p['preview_token']))

    def test_source_byte_pixel_and_geometry_mismatch(self):
        path,_=self.w.asset(self.rows[0]['id']);data=path.read_bytes()
        path.write_bytes(b'truncated')
        self.blocked('unreadable')
        path.write_bytes(data)
        self.stored('pixel_hash','f'*64)
        self.blocked('pixels changed')
        self.stored('pixel_hash',self.rows[0]['pixel_hash'])
        self.dataset.db.execute('UPDATE samples SET width=17 WHERE id=?',(self.rows[0]['id'],))
        self.dataset.db.commit()
        self.blocked('dimensions changed')

    def test_stale_record_and_family_proof(self):
        p=self.dataset.releases.preview(self.body())
        self.stored('revision',self.rows[0]['revision']+1)
        with self.assertRaises(WorkbenchError):self.dataset.releases.create(dict(self.body(),preview_token=p['preview_token']))
        self.stored('revision',self.rows[0]['revision'])
        # A negative same-split unselected bridge contributes to proof and custody.
        original=self.rows[1]
        row=self.w.save(original['id'],dict(revision=original['revision'],source_revision=original['source_revision'],
            task='image_detection',annotation=original['annotation'],groups=self.rows[0]['groups'],review='human_reviewed'))
        self.rows[1]=row
        p=self.dataset.releases.preview(self.body())
        self.rows=self.rows[:1]+self.rows[2:]
        p=self.dataset.releases.preview(self.body())
        self.w.save(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],task=row['task'],
            annotation=row['annotation'],groups=row['groups']+['new bridge'],review='human_reviewed'))
        with self.assertRaises(WorkbenchError):self.dataset.releases.create(dict(self.body(),preview_token=p['preview_token']))

    def test_huge_replacement_png_header_is_typed_without_decode(self):
        path,_=self.w.asset(self.rows[0]['id'])
        raw=path.read_bytes()
        # Rewrite IHDR dimensions and CRC, without allocating any large raster.
        payload=struct.pack('>II',100_000,100_000)+raw[24:29]
        broken=raw[:16]+payload+struct.pack('>I',zlib.crc32(b'IHDR'+payload)&0xffffffff)+raw[33:]
        with self.assertRaises(Image.DecompressionBombError):Image.open(io.BytesIO(broken))
        path.write_bytes(broken)
        with patch.object(Image.Image,'load',side_effect=AssertionError('no raster decode')):
            self.blocked('unreadable')

    def test_cross_split_family_link_rejected_without_reassignment(self):
        row=self.rows[4]
        self.rows[4]=self.w.save(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],
            task=row['task'],annotation=row['annotation'],groups=self.rows[0]['groups'],review='human_reviewed'))
        self.blocked('conflicting existing splits')

    def test_changed_png_bytes_even_with_same_geometry_rejected(self):
        path,_=self.w.asset(self.rows[0]['id'])
        Image.new('RGB',(16,12),(250,1,2)).save(path,'PNG')
        self.blocked('bytes changed')

    def test_valid_token_entry_change_during_final_writer_is_atomic(self):
        body=self.body();preview=self.dataset.releases.preview(body)
        actual=projection.entries
        calls=0
        def changed(*args):
            nonlocal calls
            calls+=1
            for name,value,expected in actual(*args):
                if calls==2 and name.endswith('/masks/'+self.rows[0]['id']+'.png'):
                    value+=b'changed after proof'
                yield name,value,expected
        with patch.object(projection,'entries',side_effect=changed),self.assertRaises(WorkbenchError):
            self.dataset.releases.create(dict(body,preview_token=preview['preview_token']))
        self.assertEqual(list(self.dataset.releases.path.iterdir()),[])

    def test_atomic_failure_retains_previous_release_database_and_no_temp(self):
        result=self.freeze();previous=self.dataset.releases.locate(result['id']).read_bytes()
        body=self.body();p=self.dataset.releases.preview(body)
        before='\n'.join(self.dataset.db.iterdump())
        import dataset_releases
        actual=dataset_releases.archive_asset
        calls=0
        def fail(*args):
            nonlocal calls
            calls+=1
            if calls==3:raise OSError('injected after two archive entries')
            return actual(*args)
        with patch.object(dataset_releases,'archive_asset',side_effect=fail),self.assertRaises(OSError):
            self.dataset.releases.create(dict(body,preview_token=p['preview_token']))
        self.assertEqual(before,'\n'.join(self.dataset.db.iterdump()))
        self.assertEqual(previous,self.dataset.releases.locate(result['id']).read_bytes())
        self.assertEqual(list(self.dataset.releases.path.glob('.building-*')),[])
        self.assertEqual(len(list(self.dataset.releases.path.glob('*.zip'))),1)

    def test_bounded_capture_rejects_stream_growth_before_raster(self):
        path,_=self.w.asset(self.rows[0]['id'])
        actual=Path.open
        reads=[]
        class Growing:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,count):
                self.assert_bound(count)
                reads.append(count)
                return b'x'*count
            @staticmethod
            def assert_bound(count):assert 0<count<=20001,'unbounded read'
        def opened(target,*args,**kwargs):
            return Growing() if target==path and args==('rb',) else actual(target,*args,**kwargs)
        with patch.object(projection,'MAX_BYTES',20000),patch.object(Path,'open',opened),patch.object(Image,'open',side_effect=AssertionError('must reject before header/raster')):
            self.blocked('40 MiB')
        self.assertTrue(reads)

    def test_all_captured_headers_preflight_before_first_decode(self):
        path,_=self.w.asset(self.rows[1]['id'])
        Image.new('RGB',(17,12),(10,20,30)).save(path,'PNG')
        with patch.object(Image.Image,'load',side_effect=AssertionError('all headers must pass before decode')):
            self.blocked('dimensions changed')

    def test_final_projection_never_reopens_replaced_source(self):
        body=self.body();preview=self.dataset.releases.preview(body)
        path,_=self.w.asset(self.rows[0]['id']);original=path.read_bytes()
        actual=projection.entries
        calls=0
        def changed(*args):
            nonlocal calls
            calls+=1
            # _checked has captured and validated all bytes before projection.
            if calls==1:path.write_bytes(b'replaced after immutable capture')
            yield from actual(*args)
        with patch.object(projection,'entries',side_effect=changed):
            release=self.dataset.releases.create(dict(body,preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as packet:
            row=next(r for r in json.loads(packet.read('manifest.json'))['records'] if r['id']==self.rows[0]['id'])
            self.assertEqual(packet.read(row['asset']),original)
        self.assertNotEqual(path.read_bytes(),original)

    def test_mask_mapping_separates_consumer_index_and_presence(self):
        release=self.freeze()
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as packet:
            m=json.loads(packet.read('manifest.json'))
        self.assertEqual(m['label_mapping'],dict(annotation_label=LABEL,consumer_label='foreground object',
            consumer_class_index=0,positive_presence=1,negative_presence=0))
        self.assertEqual(m['native_category_evidence'],dict(retained=0,unavailable=0,not_native=6))


if __name__=='__main__':unittest.main()
