"""Independent strict polygon archive oracle plus actual pinned mask/image readers."""
import argparse
import base64
from contextlib import ExitStack
from fractions import Fraction
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from unittest.mock import patch
import uuid
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests/fixtures')]
if os.environ.get('COCO_CONSUMER_PATH'):sys.path.append(os.environ['COCO_CONSUMER_PATH'])
from app import Dataset
from PIL import Image
from check_general_coco import decode,sha
from native_text_import import RECORD_KEYS,MANIFEST_KEYS
from polygon_fixture import populate,body,freeze,expected_bitmap
PINS=decode((ROOT/'tests/fixtures/polygon-consumer-pins.json').read_bytes())
SPLITS=('train','validation','test')
BASE_COORDINATES=('Oriented image pixel-edge xywh; text spans are NFC/LF Unicode code-point [start,end). '
    'Sequence bundles preserve original named staggered fields and accepted intervals; each whole trajectory is indivisible. '
    'Static mesh bundles preserve native xyz/topology and declared units/frame; each whole mesh is indivisible.')
POLYGON_COORDINATES=BASE_COORDINATES+(' Polygon instances retain single simple implicitly closed pixel-edge rings; '
    'bbox and area are continuous bounds and shoelace area, separate from consumer raster quantization.')


def canonical(value):
    """Preserve int/float, signed zero, nested values and list order in proofs."""
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')


def ring(points,width,height):
    """Separate exact geometry oracle; never invokes the production validator."""
    assert isinstance(points,list) and 3<=len(points)<=128
    for point in points:
        assert isinstance(point,list) and len(point)==2
        assert all(type(v) in (int,float) and math.isfinite(v) for v in point)
        assert 0<=point[0]<=width and 0<=point[1]<=height
    vertices=[tuple(Fraction(v) for v in point) for point in points]
    assert len(set(vertices))==len(vertices)
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def lies(a,b,c):return orient(a,b,c)==0 and min(a[0],b[0])<=c[0]<=max(a[0],b[0]) and min(a[1],b[1])<=c[1]<=max(a[1],b[1])
    n=len(vertices)
    for i in range(n):
        a,b,c=vertices[i-1],vertices[i],vertices[(i+1)%n]
        assert orient(a,b,c)!=0 or (a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])<0
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1):continue
            p,q,r,s=vertices[i],vertices[(i+1)%n],vertices[j],vertices[(j+1)%n]
            assert not any((lies(p,q,r),lies(p,q,s),lies(r,s,p),lies(r,s,q)))
            assert not (orient(p,q,r)*orient(p,q,s)<0 and orient(r,s,p)*orient(r,s,q)<0)
    area=float(abs(sum(vertices[i][0]*vertices[(i+1)%n][1]-vertices[(i+1)%n][0]*vertices[i][1] for i in range(n)))/2)
    assert math.isfinite(area) and area>0
    xs,ys=zip(*points)
    identity=min(tuple(vertices[i:]+vertices[:i]) for i in range(n))
    backwards=list(reversed(vertices))
    identity=min(identity,min(tuple(backwards[i:]+backwards[:i]) for i in range(n)))
    return [min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)],area,identity


def inspect_archive(raw,expected_records=None):
    assert 0<len(raw)<=PINS['reader_limits']['archive_bytes']
    with zipfile.ZipFile(io.BytesIO(raw)) as packet:
        infos=packet.infolist();names=[i.filename for i in infos]
        assert len(names)==len(set(names))<=108
        assert sum(i.file_size for i in infos)<=PINS['reader_limits']['expanded_bytes']
        assert all(i.compress_type==zipfile.ZIP_STORED and not i.flag_bits&1 and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG) for i in infos)
        manifest=decode(packet.read('manifest.json'));assert set(manifest)==MANIFEST_KEYS and type(manifest['schema_version']) is int and manifest['schema_version']==1
        rows=manifest['records'];assert 1<=len(rows)<=100 and len({r['id'] for r in rows})==len(rows)
        assert manifest['coordinate_contract']==(POLYGON_COORDINATES if any(r['task']=='image_segmentation' for r in rows) else BASE_COORDINATES)
        expected={r['id']:r for r in expected_records} if expected_records is not None else None
        if expected is not None:assert set(expected)=={r['id'] for r in rows}
        assert rows==sorted(rows,key=lambda r:r['id'])
        files={'manifest.json','README.txt'}|{f'{split}/{name}' for split in SPLITS for name in ('coco.json','records.jsonl')}
        total_pixels=0;work_pixels=0;payloads={};targets={};identities={};negatives=0
        for row in rows:
            assert set(row)==RECORD_KEYS and re.fullmatch('[a-f0-9]{32}',row['id'])
            assert row['kind']=='image' and row['task'] in ('image_detection','image_segmentation')
            assert row['review']=='human_reviewed' and row['source_available'] is True and row['source_lineage_known'] is True
            assert row['split'] in SPLITS and row['source_split'] in ('unassigned',row['split'])
            assert all(type(row[k]) is int and row[k]>0 for k in ('revision','source_revision','width','height'))
            assert row['width']<=4096 and row['height']<=4096
            pixels=row['width']*row['height'];assert pixels<=40000000;total_pixels+=pixels;assert total_pixels<=100000000
            assert row['asset']=='assets/'+row['id']+'.png'
            if expected is not None:
                for key in expected[row['id']]:assert canonical(row[key])==canonical(expected[row['id']][key]),key
            annotation=row['annotation'];segmented=row['task']=='image_segmentation';key='instances' if segmented else 'boxes'
            assert set(annotation)=={key} and isinstance(annotation[key],list) and len(annotation[key])<=(100 if segmented else 500)
            work_pixels+=2*pixels*len(annotation[key]) if segmented else 0
            assert work_pixels<=PINS['reader_limits']['counted_decoded_pixels']
            computed=[];seen=set();vertices=0
            for target in annotation[key]:
                label=target['label'];assert isinstance(label,str) and 0<len(label)<=80 and label==label.strip()
                assert not any(0xD800<=ord(c)<=0xDFFF for c in label)
                if segmented:
                    assert set(target)=={'label','points'}
                    bbox,area,identity=ring(target['points'],row['width'],row['height']);vertices+=len(target['points']);assert vertices<=1024
                    assert (label,identity) not in seen;seen.add((label,identity))
                    computed.append(dict(label=label,bbox=bbox,area=area,segmentation=[[v for p in target['points'] for v in p]]))
                else:
                    assert set(target)=={'label','x','y','width','height'}
                    bbox=[target[k] for k in ('x','y','width','height')];assert all(type(v) in (int,float) and math.isfinite(v) for v in bbox)
                    x,y,w,h=bbox;assert x>=0 and y>=0 and w>0 and h>0 and x+w<=row['width'] and y+h<=row['height']
                    computed.append(dict(label=label,bbox=bbox,area=w*h))
            negatives+=not annotation[key];targets[row['id']]=computed
            asset=packet.read(row['asset']);assert sha(asset)==row['asset_sha256']==row['content_hash'];files.add(row['asset']);payloads[row['asset']]=asset
            # Preflight all declared raster-work before the actual mask calls.
            with Image.open(io.BytesIO(asset)) as image:assert image.format=='PNG' and image.mode=='RGB' and image.size==(row['width'],row['height']) and image.getexif().get(274,1)==1
        assert set(names)==files
        for row in rows:
            with Image.open(io.BytesIO(payloads[row['asset']])) as image:
                image.load();assert sha(str(image.size).encode()+image.tobytes())==row['pixel_hash']
        vocabulary=sorted({target['label'] for items in targets.values() for target in items});table=[dict(id=i+1,name=label) for i,label in enumerate(vocabulary)]
        assert manifest['vocabulary']==vocabulary;mapping={c['name']:c['id'] for c in table}
        objects=0;split_counts={}
        for split in SPLITS:
            assert packet.read(split+'/records.jsonl')==b''
            coco_raw=packet.read(split+'/coco.json');coco=decode(coco_raw);payloads[split+'/coco.json']=coco_raw
            images=[];annotations=[]
            for index,row in enumerate(rows,1):
                if row['split']!=split:continue
                images.append(dict(id=index,file_name=row['asset'],width=row['width'],height=row['height']))
                for computed in targets[row['id']]:
                    target={k:v for k,v in computed.items() if k!='label'}
                    annotations.append(dict(target,id=len(annotations)+1,image_id=index,category_id=mapping[computed['label']],iscrowd=0))
            # Primitive types matter: bool must not alias int in IDs or geometry.
            assert canonical(coco)==canonical(dict(info=dict(description='Tuldok detection release',version='1'),licenses=[],images=images,annotations=annotations,categories=table))
            objects+=len(annotations);split_counts[split]=dict(images=len(images),instances=sum(len(targets[r['id']]) for r in rows if r['split']==split and r['task']=='image_segmentation'))
        # Independently check the complete supplied selected graph, including
        # external parent keys. This cannot prove unavailable upstream closure.
        parents={}
        def root(key):
            parents.setdefault(key,key)
            while parents[key]!=key:key=parents[key]
            return key
        for row in rows:
            identifier='id:'+row['id'];root(identifier)
            for key in ([*('group:'+g for g in row['groups']),*('id:'+p for p in row['parents']),
                         'content:'+row['kind']+':'+row['content_hash'],'pixels:'+row['pixel_hash'],
                         'legacy:'+('book:'+row['book_id'] if row['book_id'] else 'session:'+row['session_id'])]):parents[root(key)]=root(identifier)
        family_splits={}
        for row in rows:
            family=root('id:'+row['id']);assert family not in family_splits or family_splits[family]==row['split'];family_splits[family]=row['split']
        counts={split:sum(r['split']==split for r in rows) for split in SPLITS}
        assert manifest['split_report']['actual_counts']=={s:n for s,n in counts.items() if n}
        return dict(manifest=manifest,payloads=payloads,categories=table,objects=objects,negatives=negatives,split_counts=split_counts,mask_decode_pixel_work=work_pixels,declared_selected_families=len(family_splits))


def verify(path,output,expected_records=None):
    checked=inspect_archive(path.read_bytes(),expected_records)
    import pycocotools.coco as coco_module
    import pycocotools.mask as mask_module
    import pycocotools._mask as compiled
    import torchvision.datasets.coco as tv_module
    import numpy as np
    import torch
    assert importlib.metadata.version('pycocotools')==PINS['pycocotools_version']
    assert importlib.metadata.version('torchvision').split('+')[0]==PINS['torchvision_version']
    identities={}
    for name,module,pin in [('coco',coco_module,'coco_sha256'),('mask',mask_module,'mask_sha256'),('compiled',compiled,'compiled_extension_sha256'),('torchvision',tv_module,'torchvision_coco_sha256')]:
        raw=Path(module.__file__).read_bytes();assert sha(raw)==PINS[pin];identities[name]=dict(path=str(Path(module.__file__).resolve()),bytes=len(raw),sha256=sha(raw))
    assert identities['compiled']['bytes']==PINS['compiled_extension_bytes']
    rows={r['asset']:r for r in checked['manifest']['records']};loaded=0;masks=[];bitmap_checks=0
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='actual-polygon-reader-',dir=output) as temporary,ExitStack() as guards:
        folder=Path(temporary)
        for name,raw in checked['payloads'].items():
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        guards.enter_context(patch.object(torch.nn.Module,'__init__',side_effect=AssertionError('Model construction forbidden')))
        guards.enter_context(patch.object(torch.optim.Optimizer,'__init__',side_effect=AssertionError('Optimizer forbidden')))
        for name in ('loadRes','download'):guards.enter_context(patch.object(coco_module.COCO,name,side_effect=AssertionError('Evaluation/download forbidden')))
        guards.enter_context(patch.object(mask_module,'iou',side_effect=AssertionError('Evaluation forbidden')))
        for split in SPLITS:
            api=coco_module.COCO(str(folder/split/'coco.json'));reader=tv_module.CocoDetection(folder,str(folder/split/'coco.json'))
            assert len(reader)==checked['split_counts'][split]['images']
            for index,image_id in enumerate(reader.ids):
                info=api.loadImgs(image_id)[0];row=rows[info['file_name']];image,annotations=reader[index]
                assert image.mode=='RGB' and image.size==(row['width'],row['height']) and sha(str(image.size).encode()+image.tobytes())==row['pixel_hash']
                assert annotations==api.loadAnns(api.getAnnIds(imgIds=[image_id]));loaded+=1
                if row['task']!='image_segmentation':
                    assert all('segmentation' not in target for target in annotations);continue
                assert len(annotations)==len(row['annotation']['instances'])
                for instance,target in zip(row['annotation']['instances'],annotations):
                    assert api.loadCats(target['category_id'])[0]['name']==instance['label']
                    direct_rle=mask_module.merge(mask_module.frPyObjects(target['segmentation'],row['height'],row['width']))
                    direct=mask_module.decode(direct_rle);mask=api.annToMask(target)
                    assert mask.dtype==np.uint8 and mask.shape==(row['height'],row['width']) and np.array_equal(mask,direct)
                    assert set(np.unique(mask))<={0,1}
                    expected=expected_bitmap(instance['points'],row['width'],row['height'])
                    if expected is not None:assert np.array_equal(mask,np.asarray(expected,dtype=np.uint8));bitmap_checks+=1
                    area=int(mask_module.area(direct_rle));assert area==int(mask.sum())
                    masks.append(dict(record_id=row['id'],annotation_id=target['id'],split=split,label=instance['label'],continuous_bbox=target['bbox'],continuous_area=target['area'],raster_bbox=mask_module.toBbox(direct_rle).tolist(),raster_area=area,raster_sha256=sha(mask.tobytes()),independent_authored_bitmap_checked=expected is not None))
    result=dict(result='PASS',release_sha256=sha(path.read_bytes()),reader_records=loaded,objects=checked['objects'],polygon_instances=len(masks),explicit_negative_images=checked['negatives'],positive_instances_with_empty_raster=sum(m['raster_area']==0 for m in masks),independent_authored_bitmap_checks=bitmap_checks,masks=masks,categories=checked['categories'],split_counts=checked['split_counts'],supplied_selected_families=checked['declared_selected_families'],supplied_graph_not_upstream_authenticity=True,mask_decode_pixel_work=checked['mask_decode_pixel_work'],reader_limits=PINS['reader_limits'],consumer_pins=PINS,installed_consumer_files=identities,actual_pycocotools_mask_and_CocoDetection=True,production_validator_not_oracle=True,model_instantiated=False,optimizer_instantiated=False,training=False,evaluation=False,downloads=False,basis=PINS['fixture_scope'])
    (output/'polygon-reader-report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');return result


def native_roundtrip(raw,source_rows,root):
    first_check=inspect_archive(raw,source_rows)
    destination=Dataset(root/'native-destination')
    try:
        prepared=destination.native_detection_imports.prepare(dict(source_name='polygon.zip',archive=base64.b64encode(raw).decode()));reviewed=[]
        for item in prepared['rows']:
            receipt=destination.native_detection_imports.admit(dict(token=item['token'],request_id=uuid.uuid4().hex));row=destination.workbench.get(receipt['record_id'])
            assert row['review']=='draft' and row['provenance']['rights']=='unknown'
            upstream=row['provenance']['acquisition']['declared']['upstream'];before=next(r for r in source_rows if r['id']==upstream['record']['id'])
            assert row['id']!=before['id'] and canonical(row['annotation'])==canonical(before['annotation']) and row['task']==before['task']
            assert canonical(upstream['record'])==canonical(next(r for r in first_check['manifest']['records'] if r['id']==before['id']))
            assert all(row[k]==before[k] for k in ('content_hash','pixel_hash','width','height')) and row['source_split']==before['source_split']
            reviewed.append(destination.workbench.save(row['id'],dict(row,review='human_reviewed')))
        second=freeze(destination,reviewed)
        second_check=inspect_archive(second,reviewed)
        assert second_check['categories']==first_check['categories'] and second_check['split_counts']==first_check['split_counts']
        return second,reviewed,dict(result='PASS',new_ids=True,local_draft_and_unknown_rights=True,exact_polygon_numeric_primitives_categories_pixels_splits=True)
    finally:destination.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--archive',type=Path);parser.add_argument('--expected',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.archive:
        result=verify(args.archive,args.output,decode(args.expected.read_bytes()) if args.expected else None)
    else:
        with tempfile.TemporaryDirectory(prefix='polygon-coco-',dir=args.output) as temporary:
            folder=Path(temporary);source=Dataset(folder/'source')
            try:rows=populate(source);raw=freeze(source,rows)
            finally:source.close()
            archive=args.output/'canonical-polygon.zip';archive.write_bytes(raw);first=verify(archive,args.output/'source-reader',rows)
            assert first['polygon_instances']==12 and first['positive_instances_with_empty_raster']==3 and first['independent_authored_bitmap_checks']==12
            second,reviewed,roundtrip=native_roundtrip(raw,rows,folder);archive=args.output/'roundtrip-polygon.zip';archive.write_bytes(second);second_result=verify(archive,args.output/'roundtrip-reader',reviewed)
            source=Dataset(folder/'source')
            try:
                mixed=[]
                for index,old in enumerate(rows):
                    row=source.workbench.get(old['id'])
                    if index==1:row=source.workbench.save(row['id'],dict(row,task='image_detection',annotation={'boxes':[dict(label='Object',x=1,y=1,width=4,height=4)]},review='human_reviewed'))
                    mixed.append(row)
                mixed_raw=freeze(source,mixed)
            finally:source.close()
            archive=args.output/'mixed-box-polygon.zip';archive.write_bytes(mixed_raw);mixed_result=verify(archive,args.output/'mixed-reader',mixed)
            assert mixed_result['polygon_instances']==12 and mixed_result['objects']==13
            result=dict(result='PASS',source_reader=first,roundtrip_reader=second_result,native_roundtrip=roundtrip,mixed_reader=mixed_result,training=False)
    (args.output/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(dict(result='PASS',training=False)))


if __name__=='__main__':main()
