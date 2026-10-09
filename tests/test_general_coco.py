"""Real canonical owners and strict independent COCO association checks."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent/'fixtures')]
from app import Dataset,make_handler
from general_coco_fixture import populate,body,freeze,BOXES
from check_general_coco import inspect_archive,native_roundtrip
from workbench import WorkbenchError,encode,validate_annotation


class GeneralCocoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.dataset=Dataset(self.path/'source');self.addCleanup(self.dataset.close)
        self.rows=populate(self.dataset)

    def test_multibox_fractional_subpixel_labels_negatives_and_category_preview(self):
        preview=self.dataset.releases.preview(body(self.rows));self.assertTrue(preview['eligible'])
        raw=freeze(self.dataset,self.rows);checked=inspect_archive(raw,self.rows)
        self.assertEqual(preview['coco_categories'],checked['categories'])
        self.assertEqual([c['name'] for c in checked['categories']],sorted({b['label'] for b in BOXES}))
        self.assertEqual(checked['objects'],12)
        self.assertTrue(all(s==dict(images=2,objects=4,negatives=1) for s in checked['split_counts'].values()))
        records=checked['manifest']['records']
        self.assertEqual(checked['manifest']['split_report']['independent_components'],3)
        for family in {g for r in records for g in r['groups'] if g.startswith('coco-qa-family-')}:
            self.assertEqual(len({r['split'] for r in records if family in r['groups']}),1)

    def test_reversed_selection_is_identical_but_subset_label_ids_are_release_local(self):
        first=freeze(self.dataset,self.rows);self.assertEqual(first,freeze(self.dataset,list(reversed(self.rows))))
        original=inspect_archive(first,self.rows)['categories']
        changed=[]
        for row in self.rows:
            boxes=[b for b in row['annotation']['boxes'] if b['label']=='Object']
            changed.append(self.dataset.workbench.save(row['id'],dict(row,annotation={'boxes':boxes},review='human_reviewed')))
        table=inspect_archive(freeze(self.dataset,changed),changed)['categories']
        self.assertEqual(table,[dict(id=1,name='Object')]);self.assertNotEqual(next(c['id'] for c in original if c['name']=='Object'),1)

    def test_all_negative_canonical_has_empty_vocabulary_and_permitted_empty_splits(self):
        rows=[self.dataset.workbench.save(r['id'],dict(r,annotation={'boxes':[]},review='human_reviewed')) for r in self.rows[:2]]
        request=body(rows);request['ratios']=dict(train=100,validation=0,test=0)
        preview=self.dataset.releases.preview(request);self.assertTrue(preview['eligible']);self.assertEqual(preview['coco_categories'],[])
        release=self.dataset.releases.create(dict(request,preview_token=preview['preview_token']))
        checked=inspect_archive(self.dataset.releases.locate(release['id']).read_bytes(),rows)
        self.assertEqual(checked['objects'],0);self.assertEqual(checked['categories'],[])
        self.assertEqual(checked['split_counts']['train'],dict(images=2,objects=0,negatives=2))
        self.assertEqual(checked['split_counts']['validation'],dict(images=0,objects=0,negatives=0))

    def test_actual_native_roundtrip_preserves_multibox_targets_splits_category_evidence(self):
        original=freeze(self.dataset,self.rows)
        second,reviewed,result=native_roundtrip(original,self.rows,self.path)
        self.assertEqual(result['result'],'PASS');self.assertEqual(result['records'],6)
        self.assertEqual(inspect_archive(original,self.rows)['split_counts'],inspect_archive(second,reviewed)['split_counts'])

    def test_invalid_geometry_refuses_without_target_history_or_publication_changes(self):
        row=self.rows[0];before=list(self.dataset.db.iterdump())
        bad=[dict(BOXES[0],x=True),dict(BOXES[0],width=0),dict(BOXES[0],width=-1),dict(BOXES[0],x=-0.5),
             dict(BOXES[0],x=float('nan')),dict(BOXES[0],height=float('inf')),dict(BOXES[0],width=16),
             dict(BOXES[0],polygon=[[0,0],[1,1]]),dict(BOXES[0],x=10**1000),dict(BOXES[0],width=10**1000)]
        for box in bad:
            with self.subTest(box=str(box)[:100]),self.assertRaises(WorkbenchError):
                self.dataset.workbench.save(row['id'],dict(row,annotation={'boxes':[box]},review='human_reviewed'))
        for boxes in ([BOXES[0],BOXES[0]],[dict(BOXES[0],x=0,width=1)]*501):
            with self.assertRaises(WorkbenchError):validate_annotation('image_detection',{'boxes':boxes},row)
        self.assertEqual(list(self.dataset.db.iterdump()),before)
        self.assertEqual(list(self.dataset.releases.path.iterdir()),[])

    def test_huge_integer_pure_and_mixed_geometry_returns_HTTP400_atomically(self):
        row=self.rows[0];held=freeze(self.dataset,self.rows);before=list(self.dataset.db.iterdump())
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        variants=[dict(label='QA',x=10**1000,y=0,width=1,height=1)]
        variants.extend(dict(dict(label='QA',x=0.5,y=0.5,width=1.5,height=1.5),**{key:10**1000}) for key in ('x','y','width','height'))
        for box in variants:
            payload=dict(revision=row['revision'],source_revision=row['source_revision'],task='image_detection',
                annotation={'boxes':[box]},groups=row['groups'],review='human_reviewed')
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/records/'+row['id'],
                data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request,timeout=5)
            self.assertEqual(caught.exception.code,400)
            self.assertIn('finite',json.loads(caught.exception.read())['error'])
        self.assertEqual(list(self.dataset.db.iterdump()),before)
        self.assertEqual(len(list(self.dataset.releases.path.iterdir())),1)
        self.assertEqual(next(self.dataset.releases.path.iterdir()).read_bytes(),held)

    def test_corrupted_huge_integer_preview_and_freeze_refuse_atomically(self):
        held=freeze(self.dataset,self.rows);request=body(self.rows);old=self.dataset.releases.preview(request)
        row=self.rows[0]
        for key in ('x','y','width','height'):
            box=dict(label='QA',x=0.5,y=0.5,width=1.5,height=1.5);box[key]=10**1000
            self.dataset.db.execute('UPDATE workbench_records SET annotation_json=? WHERE id=?',(encode(dict(boxes=[box])),row['id']));self.dataset.db.commit()
            before=list(self.dataset.db.iterdump());preview=self.dataset.releases.preview(request)
            self.assertFalse(preview['eligible']);self.assertTrue(any('finite' in b['message'] for b in preview['blockers']))
            with self.assertRaises(WorkbenchError):self.dataset.releases.create(dict(request,preview_token=old['preview_token']))
            self.assertEqual(list(self.dataset.db.iterdump()),before)
            self.assertEqual(len(list(self.dataset.releases.path.iterdir())),1)
            self.assertEqual(next(self.dataset.releases.path.iterdir()).read_bytes(),held)

    def test_unselected_bridge_fixed_split_conflict_blocks_general_coco(self):
        bridge=self.dataset.workbench.import_asset(dict(kind='text',name='QA bridge',text='Authored lineage bridge only',
            groups=['bridge'],parents=[self.rows[0]['id'],self.rows[2]['id']],rights='Authored fixture'))
        preview=self.dataset.releases.preview(body(self.rows));self.assertFalse(preview['eligible'])
        self.assertTrue(preview['blockers'])
        self.assertTrue(any(set(family['fixed_splits'])=={'train','validation'} for family in preview['lineage']))
        self.assertTrue(any(bridge['id'] in family['member_ids'] for family in preview['lineage']))
        with self.assertRaises(WorkbenchError):self.dataset.releases.create(dict(body(self.rows),preview_token='a'*64))
        self.assertEqual(list(self.dataset.releases.path.iterdir()),[])

    def test_atomic_writer_failure_keeps_existing_release_and_cleans_temporary(self):
        held=freeze(self.dataset,self.rows)
        with patch('dataset_releases.archive_asset',side_effect=OSError('Controlled authored-fixture writer failure')):
            with self.assertRaises(OSError):freeze(self.dataset,self.rows)
        self.assertEqual(len(list(self.dataset.releases.path.iterdir())),1)
        self.assertEqual(next(self.dataset.releases.path.iterdir()).read_bytes(),held)

    def test_strict_oracle_rejects_malformed_coco_associations_before_permissive_index(self):
        raw=freeze(self.dataset,self.rows)
        def rewrite(change):
            output=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as target:
                for name in source.namelist():
                    value=source.read(name)
                    if name=='train/coco.json':
                        coco=json.loads(value);change(coco);value=json.dumps(coco).encode()
                    target.writestr(name,value)
            return output.getvalue()
        mutations=[lambda c:c['annotations'][0].update(category_id=999),lambda c:c['annotations'][0].update(image_id=999),
                   lambda c:c['annotations'][0].update(bbox=[0,0,1,1]),lambda c:c['annotations'][0].update(area=0),
                   lambda c:c['annotations'].append(dict(c['annotations'][0])),lambda c:c['images'].append(dict(c['images'][0])),
                   lambda c:c['categories'][1].update(name='object'),lambda c:c['annotations'][0].update(iscrowd=False)]
        for mutation in mutations:
            with self.assertRaises(AssertionError):inspect_archive(rewrite(mutation),self.rows)


if __name__=='__main__':unittest.main()
