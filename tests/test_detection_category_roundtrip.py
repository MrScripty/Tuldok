"""Actual exporters/importer; authored QA targets simulate explicit review.

This tests custody and interoperability, not a human-labelled training corpus.
"""
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
sys.path.insert(0,str(Path(__file__).resolve().parent/'fixtures'))
from app import Dataset
from image_detection_fixture import populate,LABEL
from workbench import encode,WorkbenchError
import image_detection_export as projection

OTHER='! Other authored QA label'


class DetectionCategoryRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.source=Dataset(str(self.path/'source'));self.addCleanup(self.source.close)
        self.destination=Dataset(str(self.path/'destination'));self.addCleanup(self.destination.close)
        self.rows=populate(self.source)
        row=self.rows[2]
        self.rows[2]=self.source.workbench.save(row['id'],dict(row,
            annotation={'boxes':[dict(row['annotation']['boxes'][0],label=OTHER)]},review='human_reviewed'))
        self.raw=self.freeze(self.source,self.rows,'canonical_v1')
        with zipfile.ZipFile(io.BytesIO(self.raw)) as packet:
            self.original_manifest=json.loads(packet.read('manifest.json'))
            self.table=json.loads(packet.read('train/coco.json'))['categories']
        self.assertEqual(self.table,[dict(id=1,name=OTHER),dict(id=2,name=LABEL)])
        prepared=self.destination.native_detection_imports.prepare(dict(source_name='fixture.zip',archive=base64.b64encode(self.raw).decode()))
        self.imported=[]
        for row in prepared['rows']:
            result=self.destination.native_detection_imports.admit(dict(token=row['token'],request_id=uuid.uuid4().hex))
            self.imported.append(self.destination.workbench.get(result['record_id']))

    def body(self,rows,format_name):
        return dict(format=format_name,seed=42,ratios=dict(train=34,validation=33,test=33),
            items=[{k:row[k] for k in ('id','revision','source_revision')} for row in rows])

    def freeze(self,dataset,rows,format_name):
        body=self.body(rows,format_name);preview=dataset.releases.preview(body)
        self.assertTrue(preview['eligible'],preview)
        release=dataset.releases.create(dict(body,preview_token=preview['preview_token']))
        return dataset.releases.locate(release['id']).read_bytes()

    def selected_reviewed(self,relabel=None):
        rows=[]
        for row in self.imported:
            boxes=row['annotation']['boxes']
            if any(box['label']==OTHER for box in boxes):continue
            if relabel:boxes=[dict(box,label=relabel) for box in boxes]
            rows.append(self.destination.workbench.save(row['id'],dict(row,
                annotation={'boxes':boxes},review='human_reviewed')))
        return rows

    def test_category2_native_drafts_then_subset_projection_and_canonical_roundtrip(self):
        for row in self.imported:
            self.assertEqual(row['review'],'draft')
            evidence=row['provenance']['acquisition'];origin=evidence['declared']['upstream']
            self.assertEqual(origin['category_table'],self.table)
            self.assertEqual(origin['annotation_category_ids'],[2 if box['label']==LABEL else 1 for box in origin['record']['annotation']['boxes']])
            self.assertEqual(evidence['archive_sha256'],hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(row['source_split'],origin['record']['split'])
            self.assertEqual(row['annotation'],origin['record']['annotation'])
        self.assertFalse(self.destination.releases.preview(self.body(self.imported,projection.FORMAT))['eligible'])
        selected=self.selected_reviewed()
        mask_packet=self.freeze(self.destination,selected,projection.FORMAT)
        with zipfile.ZipFile(io.BytesIO(mask_packet)) as packet:
            manifest=json.loads(packet.read('manifest.json'))
            self.assertEqual(manifest['label_mapping']['consumer_class_index'],0)
            self.assertEqual(manifest['native_category_evidence'],dict(retained=5,unavailable=0,not_native=0))
            for row in manifest['records']:
                origin=row['provenance']['acquisition']['declared']['upstream']
                self.assertEqual(origin['category_table'],self.table)
                self.assertEqual(origin['annotation_category_ids'],[2] if row['annotation']['boxes'] else [])
                self.assertEqual(row['split'],row['source_split'])
        # Canonical release-local category1 is distinct from retained source category2.
        canonical=self.freeze(self.destination,selected,'canonical_v1')
        with zipfile.ZipFile(io.BytesIO(canonical)) as packet:
            manifest=json.loads(packet.read('manifest.json'))
            for split in ('train','validation','test'):
                coco=json.loads(packet.read(split+'/coco.json'))
                self.assertEqual(coco['categories'],[dict(id=1,name=LABEL)])
                self.assertTrue(all(box['category_id']==1 for box in coco['annotations']))
            self.assertTrue(all(row['provenance']['acquisition']['declared']['upstream']['category_table']==self.table for row in manifest['records']))
        third=Dataset(str(self.path/'third'));self.addCleanup(third.close)
        prepared=third.native_detection_imports.prepare(dict(source_name='roundtrip.zip',archive=base64.b64encode(canonical).decode()))
        for item in prepared['rows']:
            receipt=third.native_detection_imports.admit(dict(token=item['token'],request_id=uuid.uuid4().hex))
            row=third.workbench.get(receipt['record_id']);origin=row['provenance']['acquisition']['declared']['upstream']
            self.assertEqual(row['review'],'draft')
            self.assertEqual(origin['category_table'],[dict(id=1,name=LABEL)])
            self.assertEqual(origin['record']['provenance']['acquisition']['declared']['upstream']['category_table'],self.table)
            self.assertEqual(row['annotation'],origin['record']['annotation'])
            self.assertEqual(row['source_split'],origin['record']['split'])
            self.assertEqual(row['pixel_hash'],origin['record']['pixel_hash'])

    def test_relabel_does_not_reassign_original_category_ids(self):
        label='Changed current reviewed QA target'
        selected=self.selected_reviewed(relabel=label)
        raw=self.freeze(self.destination,selected,projection.FORMAT)
        with zipfile.ZipFile(io.BytesIO(raw)) as packet:
            manifest=json.loads(packet.read('manifest.json'))
        self.assertEqual(manifest['label_mapping']['annotation_label'],label)
        for row in manifest['records']:
            origin=row['provenance']['acquisition']['declared']['upstream']
            self.assertEqual(origin['category_table'],self.table)
            self.assertEqual(origin['annotation_category_ids'],[2] if row['annotation']['boxes'] else [])
            for box in row['annotation']['boxes']:self.assertEqual(box['label'],label)
            for box in origin['record']['annotation']['boxes']:self.assertEqual(box['label'],LABEL)

    def test_legacy_missing_category_ids_are_explicit_and_never_guessed(self):
        for row in self.imported:
            provenance=row['provenance'];upstream=provenance['acquisition']['declared']['upstream']
            del upstream['category_table'];del upstream['annotation_category_ids']
            self.destination.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?',(encode(provenance),row['id']))
        self.destination.db.commit()
        self.imported=[self.destination.workbench.get(row['id']) for row in self.imported]
        selected=self.selected_reviewed()
        preview=self.destination.releases.preview(self.body(selected,projection.FORMAT))
        self.assertEqual(preview['native_category_evidence'],dict(retained=0,unavailable=5,not_native=0))
        self.assertTrue(any('unavailable' in warning for warning in preview['warnings']))
        raw=self.freeze(self.destination,selected,projection.FORMAT)
        with zipfile.ZipFile(io.BytesIO(raw)) as packet:
            manifest=json.loads(packet.read('manifest.json'))
        self.assertTrue(all(row['native_category_id_status']=='unavailable' for row in manifest['records']))

    def test_invalid_original_category_evidence_blocks_without_publication(self):
        selected=self.selected_reviewed();row=next(row for row in selected if row['annotation']['boxes'])
        provenance=row['provenance'];provenance['acquisition']['declared']['upstream']['annotation_category_ids']=[True]
        self.destination.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?',(encode(provenance),row['id']));self.destination.db.commit()
        preview=self.destination.releases.preview(self.body(selected,projection.FORMAT))
        self.assertFalse(preview['eligible']);self.assertIn('category evidence',str(preview['blockers']))
        with self.assertRaises(WorkbenchError):self.destination.releases.create(dict(self.body(selected,projection.FORMAT),preview_token='a'*64))
        self.assertEqual(list(self.destination.releases.path.iterdir()),[])


if __name__=='__main__':unittest.main()
