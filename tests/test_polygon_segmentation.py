"""Real annotation/release/native owners, malformed inputs and atomic failures."""
import base64
import copy
import io
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile
from PIL import Image
from http.server import ThreadingHTTPServer
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent/'fixtures')]
from app import Dataset,make_handler
from polygon_fixture import populate,body,freeze,INSTANCES
from check_polygon_coco import inspect_archive,native_roundtrip,ring,canonical
from workbench import WorkbenchError,encode,validate_annotation
import dataset_releases
import image_segmentation as polygons


def rewrite(raw,change):
    with zipfile.ZipFile(io.BytesIO(raw)) as source:entries={n:source.read(n) for n in source.namelist()}
    change(entries);output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as target:
        for name,value in entries.items():target.writestr(zipfile.ZipInfo(name),value)
    return output.getvalue()


class PolygonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.dataset=Dataset(self.path/'source');self.addCleanup(self.dataset.close);self.rows=populate(self.dataset)

    def snapshot(self,dataset=None):
        d=dataset or self.dataset
        return list(d.db.iterdump()),{str(p.relative_to(d.path)):p.read_bytes() for p in d.path.rglob('*') if p.is_file() and p.suffix not in ('.db','.sqlite','.sqlite3') and not p.name.endswith(('-wal','-shm'))}

    def save(self,row,annotation,**extra):
        return self.dataset.workbench.save(row['id'],dict(row,task=polygons.TASK,annotation=annotation,review='draft',**extra))

    def test_fractional_concave_tiny_orientation_and_boundary_points_stay_exact(self):
        row=self.rows[0];target=copy.deepcopy(INSTANCES)
        target.append(dict(label='Boundary',points=[[0,0],[8,0],[16,0],[16,12],[0,12]]))
        target.append(dict(label='Clockwise',points=list(reversed(INSTANCES[0]['points']))))
        saved=self.save(row,{'instances':target});self.assertEqual(saved['annotation'],{'instances':target});self.assertEqual(saved['review'],'draft')
        self.assertEqual(polygons.geometry(INSTANCES[1]['points'])[:2],([1.25,1.25,5.5,5.5],14.25))
        self.assertEqual(polygons.geometry(INSTANCES[3]['points'])[1],.015625)
        self.assertEqual(self.dataset.workbench.history(row['id'])[0],saved)

    def test_closed_malformed_nonfinite_boolean_overflow_and_degenerate_atomic_refusal(self):
        before=self.snapshot();row=self.rows[0]
        malformed=[{}, {'polygons':[]},{'instances':[],'mask':[]}, {'instances':{}},
            {'instances':[dict(INSTANCES[0],holes=[])]},{'instances':[dict(label='X',points=[])]}]
        for points in ([[0,0],[1,1]],[[0,0],[1,0],[2,0]],[[0,0],[2,0],[2,2],[0,0]],
                       [[0,0],[2,0],[2,2],[2,0]],[[False,0],[2,0],[2,2]],
                       [[float('nan'),0],[2,0],[2,2]],[[0,0],[float('inf'),0],[2,2]],
                       [[10**1000,0],[2,0],[2,2]],[[-.1,0],[2,0],[2,2]],
                       [[0,0],[17,0],[2,2]],[[0,0,0],[2,0],[2,2]],
                       [[0,0],[1e-300,0],[0,1e-300]]):
            malformed.append({'instances':[dict(label='X',points=points)]})
        for annotation in malformed:
            with self.subTest(annotation=str(annotation)[:100]),self.assertRaises(WorkbenchError):self.save(row,annotation)
        self.assertEqual(self.snapshot(),before)

    def test_nonzero_area_crossing_touch_and_backtracking_are_refused(self):
        shapes=[[[0,0],[5,4],[0,4],[4,0]],[[0,0],[4,0],[4,4],[2,0],[0,4]],[[0,0],[4,0],[2,0],[4,4],[0,4]]]
        self.assertEqual(polygons.geometry(shapes[0])[1],2)
        before=self.snapshot()
        for points in shapes:
            with self.assertRaises(WorkbenchError):self.save(self.rows[0],{'instances':[dict(label='X',points=points)]})
            with self.assertRaises(AssertionError):ring(points,16,12)
        self.assertEqual(self.snapshot(),before)

    def test_numeric_rotation_reversal_duplicates_and_signed_zero_not_extra_instances(self):
        points=[[0,0],[5,0],[5,5],[0,5]]
        variants=[points[1:]+points[:1],list(reversed(points)),[[-0.0,0.0],[5.0,0],[5,5.0],[0.0,5.0]]]
        for duplicate in variants:
            with self.assertRaises(WorkbenchError):self.save(self.rows[0],{'instances':[dict(label='same',points=points),dict(label='same',points=duplicate)]})
        saved=self.save(self.rows[0],{'instances':[dict(label='one',points=points),dict(label='two',points=variants[-1])]})
        self.assertIs(type(saved['annotation']['instances'][1]['points'][0][0]),float)
        self.assertEqual(math.copysign(1,saved['annotation']['instances'][1]['points'][0][0]),-1)

    def test_ring_instance_and_total_vertex_bounds_refuse_without_partial_history(self):
        row=self.rows[0];before=self.snapshot()
        circle=lambda n:[[8+3*math.cos(2*math.pi*i/n),6+3*math.sin(2*math.pi*i/n)] for i in range(n)]
        cases=[[dict(label='X',points=circle(129))], [dict(INSTANCES[0],label=str(i)) for i in range(101)],
               [dict(label=str(i),points=circle(128)) for i in range(8)]+[dict(INSTANCES[0],label='overflow')]]
        for instances in cases:
            with self.assertRaises(WorkbenchError):self.save(row,{'instances':instances})
        self.assertEqual(self.snapshot(),before)

    def test_human_review_only_including_empty_negative_and_no_verified_grant(self):
        row=self.rows[1];before=self.snapshot()
        with self.assertRaises(WorkbenchError):self.dataset.workbench.save(row['id'],dict(row,review='programmatically_verified'),verified_provenance=row['provenance'])
        self.assertEqual(self.snapshot(),before)
        draft=self.save(row,{'instances':[]});rows=[draft if r['id']==row['id'] else r for r in self.rows]
        self.assertFalse(self.dataset.releases.preview(body(rows))['eligible'])
        reviewed=self.dataset.workbench.save(draft['id'],dict(draft,review='human_reviewed'));self.assertEqual(reviewed['annotation'],{'instances':[]})
        self.dataset.db.execute("UPDATE workbench_records SET review='programmatically_verified' WHERE id=?",(reviewed['id'],));self.dataset.db.commit()
        self.assertFalse(self.dataset.releases.preview(body([self.dataset.workbench.get(r['id']) for r in self.rows]))['eligible'])

    def test_canonical_projection_budget_categories_and_deterministic_selection(self):
        preview=self.dataset.releases.preview(body(self.rows));self.assertTrue(preview['eligible']);raw=freeze(self.dataset,self.rows)
        checked=inspect_archive(raw,self.rows);self.assertEqual(checked['objects'],12);self.assertEqual(checked['negatives'],3)
        self.assertEqual(checked['categories'],preview['coco_categories'])
        self.assertEqual(preview['segmentation_bounds']['stored_zip_bytes'],len(raw))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:self.assertEqual(preview['segmentation_bounds']['logical_bytes'],sum(i.file_size for i in archive.infolist()))
        self.assertEqual(raw,freeze(self.dataset,list(reversed(self.rows))))

    def test_all_negative_train_only_retains_empty_coco_category_table(self):
        rows=[r for r in self.rows if not r['annotation']['instances']];request=body(rows);request['ratios']=dict(train=100,validation=0,test=0)
        # Fixed imported splits remain protected; choose only the train negative.
        request['items']=request['items'][:1]
        preview=self.dataset.releases.preview(request);self.assertTrue(preview['eligible'])
        release=self.dataset.releases.create(dict(request,preview_token=preview['preview_token']));checked=inspect_archive(self.dataset.releases.locate(release['id']).read_bytes())
        self.assertEqual(checked['categories'],[]);self.assertEqual(checked['objects'],0);self.assertEqual(checked['negatives'],1)

    def test_mixed_box_polygon_native_roundtrip_preserves_exact_targets_evidence(self):
        old=self.rows[1];changed=self.dataset.workbench.save(old['id'],dict(old,task='image_detection',annotation={'boxes':[dict(label='Object',x=.5,y=1,width=3.5,height=2)]},review='human_reviewed'))
        rows=[changed if r['id']==old['id'] else r for r in self.rows];raw=freeze(self.dataset,rows)
        second,reviewed,result=native_roundtrip(raw,rows,self.path);self.assertEqual(result['result'],'PASS')
        checked=inspect_archive(second,reviewed);self.assertEqual(checked['objects'],13)
        for row in reviewed:
            upstream=row['provenance']['acquisition']['declared']['upstream'];before=next(r for r in rows if r['id']==upstream['record']['id'])
            mapping={c['name']:c['id'] for c in checked['categories']};key='instances' if row['task']==polygons.TASK else 'boxes'
            self.assertEqual(upstream['annotation_category_ids'],[mapping[t['label']] for t in before['annotation'][key]])

    def test_native_malformed_hash_truncated_axes_projection_contract_and_nan_read_only(self):
        raw=freeze(self.dataset,self.rows);destination=Dataset(self.path/'destination');self.addCleanup(destination.close);before=self.snapshot(destination)
        def manifest(fn):
            def change(entries):
                value=json.loads(entries['manifest.json']);fn(value);entries['manifest.json']=json.dumps(value).encode()
            return change
        def projection(fn):
            def change(entries):
                value=json.loads(entries['train/coco.json']);fn(value);entries['train/coco.json']=json.dumps(value).encode()
            return change
        def swap_axis(entries):
            value=json.loads(entries['manifest.json']);row=next(r for r in value['records'] if r['annotation']['instances']);row['annotation']['instances'][-1]['points']=[[y,x] for x,y in row['annotation']['instances'][-1]['points']];entries['manifest.json']=json.dumps(value).encode()
        mutations=[manifest(lambda m:m['records'][0].update(asset_sha256='0'*64)),manifest(lambda m:m.update(coordinate_contract='unknown')),
            manifest(lambda m:m['records'][0]['provenance'].update(invalid=float('nan'))),swap_axis,
            projection(lambda c:c['annotations'][0].update(image_id=999)),projection(lambda c:c['annotations'][0].update(category_id=True)),
            projection(lambda c:c['annotations'][0].update(segmentation=[[1,1,5,1,5,5,1,5,1,1]])),
            projection(lambda c:c['annotations'][0].update(area=0)),projection(lambda c:c['annotations'][0].update(iscrowd=1)),
            lambda e:e.update({'manifest.json':b'{"schema_version":1,"schema_version":1}'}),lambda e:e.pop('test/coco.json')]
        packets=[rewrite(raw,change) for change in mutations]+[raw[:80]]
        for packet in packets:
            with self.assertRaises(WorkbenchError):destination.native_detection_imports.prepare(dict(source_name='bad.zip',archive=base64.b64encode(packet).decode()))
            self.assertEqual(before,self.snapshot(destination))

    def test_independent_oracle_refuses_malformed_associations_and_cross_split_family(self):
        raw=freeze(self.dataset,self.rows)
        def mutate(entries):
            value=json.loads(entries['manifest.json']);value['records'][0]['groups'].append('cross-split-bridge');different=next(r for r in value['records'] if r['split']!=value['records'][0]['split']);different['groups'].append('cross-split-bridge');entries['manifest.json']=json.dumps(value).encode()
        with self.assertRaises(AssertionError):inspect_archive(rewrite(raw,mutate))
        def alter(entries):
            value=json.loads(entries['train/coco.json']);value['annotations'][0]['segmentation'][0][0]+=.25;entries['train/coco.json']=json.dumps(value).encode()
        with self.assertRaises(AssertionError):inspect_archive(rewrite(raw,alter))

    def test_independent_contract_and_source_numeric_primitive_proofs(self):
        raw=freeze(self.dataset,self.rows)
        self.assertNotEqual(canonical({'v':[0.0]}),canonical({'v':[-0.0]}))
        for contract in ('unknown',polygons.BASE_COORDINATES):
            def alter(entries):
                value=json.loads(entries['manifest.json']);value['coordinate_contract']=contract;entries['manifest.json']=json.dumps(value).encode()
            with self.assertRaises(AssertionError):inspect_archive(rewrite(raw,alter))
        negative=next(r for r in self.rows if r['source_split']=='train' and not r['annotation']['instances'])
        request=body([negative]);request['ratios']=dict(train=100,validation=0,test=0)
        release=self.dataset.releases.create(request);packet=self.dataset.releases.locate(release['id']).read_bytes()
        with self.assertRaises(AssertionError):inspect_archive(rewrite(packet,alter))
        def primitive(entries):
            value=json.loads(entries['manifest.json']);row=next(r for r in value['records'] if r['split']=='train' and r['annotation']['instances']);row['annotation']['instances'][0]['points'][0][0]=1.0;entries['manifest.json']=json.dumps(value).encode()
            coco=json.loads(entries['train/coco.json']);annotation=coco['annotations'][0];annotation['segmentation'][0][0]=1.0;annotation['bbox'][0]=1.0;annotation['bbox'][2]=4.0;entries['train/coco.json']=json.dumps(coco).encode()
        changed=rewrite(raw,primitive);inspect_archive(changed)
        with self.assertRaises(AssertionError):inspect_archive(changed,self.rows)

    def test_actual_header_before_decode_and_byte_counted_stream_bounds(self):
        from workbench import file_hash
        from dataset_releases import archive_asset
        path=self.path/'growing.bin';path.write_bytes(b'abcdef')
        self.assertEqual(file_hash(path,6),__import__('hashlib').sha256(b'abcdef').hexdigest())
        with self.assertRaises(WorkbenchError):file_hash(path,5)
        with zipfile.ZipFile(io.BytesIO(),'w') as packet:
            with self.assertRaises(WorkbenchError):archive_asset(packet,path,'x.bin','0'*64,5)
        request=body(self.rows)
        class MismatchedHeader:
            format='PNG';size=(10000,10000);width=10000;height=10000
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def getexif(self):return {}
            def convert(self,*args):raise AssertionError('Decoded mismatched source before checking header')
        with patch('dataset_releases.Image.open',return_value=MismatchedHeader()):
            preview=self.dataset.releases.preview(request);self.assertFalse(preview['eligible']);self.assertTrue(any('before raster decoding' in b['message'] for b in preview['blockers']))
        held=freeze(self.dataset,self.rows);before=self.snapshot();original=dataset_releases.archive_asset
        def bounded(archive,asset,filename,expected_hash,max_bytes=None):
            self.assertIsNotNone(max_bytes)
            return original(archive,asset,filename,expected_hash,1)
        with patch('dataset_releases.archive_asset',side_effect=bounded):
            with self.assertRaises(WorkbenchError):freeze(self.dataset,self.rows)
        self.assertEqual(self.snapshot(),before)

    def test_actual_reader_axis_and_all_decode_work_caps_precede_mask_calls(self):
        image=io.BytesIO();Image.new('RGB',(4097,1),(5,6,7)).save(image,'PNG')
        row=self.dataset.workbench.import_asset(dict(kind='image',image=base64.b64encode(image.getvalue()).decode(),name='Thin authored QA source',groups=['thin-family'],rights='QA'))
        row=self.dataset.workbench.save(row['id'],dict(row,task=polygons.TASK,annotation={'instances':[dict(label='Thin',points=[[0,0],[4097,0],[4097,1],[0,1]])]},review='human_reviewed'))
        request=body([row]);request['ratios']=dict(train=100,validation=0,test=0);release=self.dataset.releases.create(request);raw=self.dataset.releases.locate(release['id']).read_bytes()
        with self.assertRaises(AssertionError):inspect_archive(raw)
        # Two full decodes per polygon, including the empty tiny raster.
        from check_polygon_coco import PINS
        with patch.dict(PINS['reader_limits'],counted_decoded_pixels=2*16*12*12-1):
            with self.assertRaises(AssertionError):inspect_archive(freeze(self.dataset,self.rows))

    def test_prepare_native_budget_checks_before_png_decode_and_no_truncation(self):
        raw=freeze(self.dataset,self.rows);destination=Dataset(self.path/'destination');self.addCleanup(destination.close)
        with patch('image_segmentation.MAX_PIXELS',1),patch('native_detection_import.png',side_effect=AssertionError('Raster decode before budget')):
            with self.assertRaises(WorkbenchError):destination.native_detection_imports.prepare(dict(source_name='input.zip',archive=base64.b64encode(raw).decode()))
        with patch('native_detection_import.MAX_PREPARED',1):
            with self.assertRaises(WorkbenchError):destination.native_detection_imports.prepare(dict(source_name='input.zip',archive=base64.b64encode(raw).decode()))
        self.assertEqual(destination.workbench.query({})['total'],0)

    def test_native_repeated_marker_tamper_lost_ack_and_atomic_storage_failure(self):
        raw=freeze(self.dataset,self.rows);destination=Dataset(self.path/'destination');self.addCleanup(destination.close)
        prepared=destination.native_detection_imports.prepare(dict(source_name='input.zip',archive=base64.b64encode(raw).decode()));first=prepared['rows'][0];marker=uuid.uuid4().hex
        request=dict(token=first['token'],request_id=marker);receipt=destination.native_detection_imports.admit(request);before=self.snapshot(destination)
        with self.assertRaises(WorkbenchError):destination.native_detection_imports.admit(request)
        from bulk_import import find_result
        self.assertEqual(find_result(destination.workbench,marker),dict(found=True,**receipt));self.assertEqual(before,self.snapshot(destination))
        with self.assertRaises(WorkbenchError):destination.native_detection_imports.admit(dict(token=first['token'][:-1]+'x',request_id=uuid.uuid4().hex))
        second=prepared['rows'][1];marker=uuid.uuid4().hex
        with patch.object(destination.workbench,'_history',side_effect=sqlite3.OperationalError('QA history failure')):
            with self.assertRaises(WorkbenchError):destination.native_detection_imports.admit(dict(token=second['token'],request_id=marker))
        self.assertEqual(before,self.snapshot(destination));self.assertEqual(find_result(destination.workbench,marker),dict(found=False))
        destination.native_detection_imports.admit(dict(token=second['token'],request_id=marker))

    def test_annotation_history_failure_rolls_back_review_targets_and_source(self):
        before=self.snapshot()
        with patch.object(self.dataset.workbench,'_history',side_effect=sqlite3.OperationalError('QA annotation history failure')):
            with self.assertRaises(sqlite3.OperationalError):self.save(self.rows[0],{'instances':[]})
        self.assertEqual(before,self.snapshot())

    def test_selection_record_pixel_and_exact_byte_bounds_before_raster_decode(self):
        request=body(self.rows)
        for target,value in [('MAX_RECORDS',5),('MAX_PIXELS',1),('MAX_BYTES',1)]:
            with patch.object(polygons,target,value),patch('dataset_releases.Image.open',side_effect=AssertionError('Expansion before bounds')):
                preview=self.dataset.releases.preview(request);self.assertFalse(preview['eligible'])
        self.assertEqual(list(self.dataset.releases.path.iterdir()),[])
        raw=freeze(self.dataset,self.rows)
        with patch.object(polygons,'MAX_BYTES',len(raw)-1):
            self.assertFalse(self.dataset.releases.preview(request)['eligible'])

    def test_atomic_projection_and_final_physical_bound_failure_preserve_old_archive(self):
        held=freeze(self.dataset,self.rows);before=self.snapshot();request=body(self.rows);original=dataset_releases.canonical_payloads;calls=0
        def changed(*args,**kwargs):
            nonlocal calls
            calls+=1;records,payloads=original(*args,**kwargs)
            if calls==2:payloads['README.txt']+=b'x'*64
            return records,payloads
        with patch.object(polygons,'MAX_BYTES',len(held)+32),patch('dataset_releases.canonical_payloads',side_effect=changed):
            with self.assertRaises(WorkbenchError):self.dataset.releases.create(request)
        self.assertEqual(self.snapshot(),before)
        with patch('dataset_releases.archive_asset',side_effect=OSError('QA file write failure')):
            with self.assertRaises(OSError):freeze(self.dataset,self.rows)
        self.assertEqual(self.snapshot(),before);self.assertEqual(len(list(self.dataset.releases.path.iterdir())),1)

    def test_unselected_and_deleted_bridge_preserves_fixed_family_conflict(self):
        bridge=self.dataset.workbench.import_asset(dict(kind='text',text='Polygon family bridge',name='Bridge',groups=['bridge'],parents=[self.rows[0]['id'],self.rows[2]['id']],rights='Authored QA'))
        self.dataset.workbench.delete_text(bridge['id'],dict(revision=bridge['revision'],source_revision=bridge['source_revision']))
        preview=self.dataset.releases.preview(body(self.rows));self.assertFalse(preview['eligible'])
        self.assertTrue(any(bridge['id'] in family['deleted_ids'] and set(family['fixed_splits'])=={'train','validation'} for family in preview['lineage']))
        self.assertEqual(list(self.dataset.releases.path.iterdir()),[])

    def test_stale_selection_draft_recovery_and_immutable_frozen_export(self):
        raw=freeze(self.dataset,self.rows);request=body(self.rows);preview=self.dataset.releases.preview(request);row=self.rows[0]
        changed=self.save(row,{'instances':copy.deepcopy(INSTANCES[:1])});self.assertFalse(self.dataset.releases.preview(request)['eligible'])
        current=[changed if r['id']==row['id'] else r for r in self.rows];self.assertFalse(self.dataset.releases.preview(body(current))['eligible'])
        with self.assertRaises(WorkbenchError):self.dataset.releases.create(dict(request,preview_token=preview['preview_token']))
        reviewed=self.dataset.workbench.save(changed['id'],dict(changed,review='human_reviewed'));current=[reviewed if r['id']==row['id'] else r for r in self.rows]
        self.assertTrue(self.dataset.releases.preview(body(current))['eligible']);self.assertEqual(next(self.dataset.releases.path.iterdir()).read_bytes(),raw)

    def test_typed_mixed_text_preserved_without_adding_segmentation_jsonl(self):
        row=self.dataset.workbench.import_asset(dict(kind='text',text='Exact Unicode α\n',name='Context',groups=['typed-family'],rights='QA'))
        row=self.dataset.workbench.save(row['id'],dict(row,task='text_entities',annotation={'spans':[]},review='human_reviewed'))
        rows=[*self.rows,row];raw=freeze(self.dataset,rows)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            manifest=json.loads(archive.read('manifest.json'));record=next(r for r in manifest['records'] if r['id']==row['id']);self.assertEqual(archive.read(record['asset']),row['text'].encode())
            typed=[json.loads(line) for split in ('train','validation','test') for line in archive.read(split+'/records.jsonl').splitlines()];self.assertEqual(len(typed),1);self.assertEqual(typed[0]['id'],row['id'])
        self.assertEqual(self.dataset.releases.preview(body(rows))['segmentation_bounds']['stored_zip_bytes'],len(raw))

    def test_HTTP_finite_and_large_integer_rejection_keeps_revision_history_and_publication(self):
        row=self.rows[0];before=self.snapshot();server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        for value in (float('nan'),float('inf'),True,10**1000):
            annotation={'instances':[dict(label='X',points=[[value,0],[2,0],[2,2]])]}
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/records/'+row['id'],data=json.dumps(dict(row,task=polygons.TASK,annotation=annotation,review='draft')).encode(),headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request,timeout=5)
            self.assertEqual(caught.exception.code,400)
        payload=json.dumps(dict(row,task=polygons.TASK,annotation={'instances':[dict(label='X',points=[[0,0],[2,0],[2,2]])]},review='draft')).replace('"label": "X"','"label": "first", "label": "X"').encode()
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/records/'+row['id'],data=payload,headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request,timeout=5)
        self.assertEqual(caught.exception.code,400)
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
