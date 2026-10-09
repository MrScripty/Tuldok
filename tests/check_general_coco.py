"""Actual COCO/CocoDetection reader oracle; authored boxes, never training."""
import argparse
import base64
from contextlib import ExitStack
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
from general_coco_fixture import populate,freeze,body
PINS=json.loads((ROOT/'tests/fixtures/coco-consumer-pins.json').read_text())
SPLITS=('train','validation','test')
MAX_ARCHIVE=8*1024*1024
MAX_EXPANDED=16*1024*1024


def sha(raw):return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result={}
        for key,value in items:
            assert key not in result,'Duplicate JSON key'
            result[key]=value
        return result
    def invalid(value):raise AssertionError('Nonfinite JSON constant '+value)
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def inspect_archive(raw,expected_records=None):
    """Independent strict oracle before COCO's permissive index construction."""
    assert 0<len(raw)<=MAX_ARCHIVE
    with zipfile.ZipFile(io.BytesIO(raw)) as packet:
        infos=packet.infolist();names=[i.filename for i in infos]
        assert len(names)==len(set(names))<=108
        assert sum(i.file_size for i in infos)<=MAX_EXPANDED
        assert all(i.compress_type==zipfile.ZIP_STORED and not i.flag_bits&1
                   and stat.S_IFMT(i.external_attr>>16) in (0,stat.S_IFREG) for i in infos)
        manifest=decode(packet.read('manifest.json'));rows=manifest['records']
        assert 1<=len(rows)<=100 and len({r['id'] for r in rows})==len(rows)
        expected={r['id']:r for r in expected_records} if expected_records is not None else None
        if expected is not None:assert set(expected)=={r['id'] for r in rows}
        vocabulary=sorted({b['label'] for r in rows for b in r['annotation']['boxes']})
        table=[dict(id=i+1,name=label) for i,label in enumerate(vocabulary)]
        mapping={c['name']:c['id'] for c in table}
        assert manifest['vocabulary']==vocabulary
        files={'manifest.json','README.txt'}|{f'{s}/{f}' for s in SPLITS for f in ('coco.json','records.jsonl')}
        total_pixels=0;payloads={};by_split={}
        for index,row in enumerate(rows,1):
            assert re.fullmatch('[a-f0-9]{32}',row['id'])
            assert row['kind']=='image' and row['task']=='image_detection' and row['review']=='human_reviewed'
            assert row['source_available'] is True and row['source_lineage_known'] is True
            assert type(row['revision']) is int and row['revision']>0
            assert type(row['source_revision']) is int and row['source_revision']>0
            assert row['split'] in SPLITS and row['source_split'] in ('unassigned',row['split'])
            assert row['asset']=='assets/'+row['id']+'.png'
            assert all(type(row[k]) is int and row[k]>0 for k in ('width','height'))
            pixels=row['width']*row['height'];assert pixels<=40000000;total_pixels+=pixels
            assert total_pixels<=100000000
            assert set(row['annotation'])=={'boxes'} and len(row['annotation']['boxes'])<=500
            if expected is not None:
                before=expected[row['id']]
                for key in ('id','revision','source_revision','annotation','provenance','groups','parents','source_split',
                            'source_sha256','content_hash','pixel_hash','width','height','review','task'):
                    assert row[key]==before[key],key
            raw_image=packet.read(row['asset']);payloads[row['asset']]=raw_image;files.add(row['asset'])
            assert sha(raw_image)==row['asset_sha256']==row['content_hash']
            # All headers checked before any complete raster decoding.
            with Image.open(io.BytesIO(raw_image)) as image:
                assert image.format=='PNG' and image.size==(row['width'],row['height']) and image.getexif().get(274,1)==1
            by_split[index]=row
        assert set(names)==files
        for row in rows:
            with Image.open(io.BytesIO(payloads[row['asset']])) as image:
                rgb=image.convert('RGB');rgb.load()
                assert sha(str(rgb.size).encode()+rgb.tobytes())==row['pixel_hash']
        split_counts={};objects=0
        for split in SPLITS:
            assert packet.read(split+'/records.jsonl')==b''
            coco=decode(packet.read(split+'/coco.json'));payloads[split+'/coco.json']=packet.read(split+'/coco.json')
            assert coco['categories']==table
            assert all(type(c['id']) is int and type(c['name']) is str for c in coco['categories'])
            # IDs/associations/geometry derived from canonical rows, not emitted COCO.
            images=[];annotations=[]
            for index,row in by_split.items():
                if row['split']!=split:continue
                images.append(dict(id=index,file_name=row['asset'],width=row['width'],height=row['height']))
                for box in row['annotation']['boxes']:
                    assert set(box)=={'label','x','y','width','height'}
                    assert isinstance(box['label'],str) and 0<len(box['label'])<=80
                    coords=[box[k] for k in ('x','y','width','height')]
                    assert all(type(v) in (int,float) and math.isfinite(v) for v in coords)
                    x,y,width,height=coords
                    assert x>=0 and y>=0 and width>0 and height>0 and x+width<=row['width'] and y+height<=row['height']
                    annotations.append(dict(id=len(annotations)+1,image_id=index,category_id=mapping[box['label']],
                        bbox=coords,area=width*height,iscrowd=0))
            assert coco['images']==images and coco['annotations']==annotations
            assert all(type(v['id']) is int for v in coco['images']+coco['annotations'])
            assert all(type(i['width']) is int and type(i['height']) is int for i in coco['images'])
            assert all(type(a['area']) in (int,float) and all(type(v) in (int,float) for v in a['bbox']) for a in coco['annotations'])
            assert all(type(a['image_id']) is int and type(a['category_id']) is int and type(a['iscrowd']) is int for a in coco['annotations'])
            split_counts[split]=dict(images=len(images),objects=len(annotations),negatives=sum(not r['annotation']['boxes'] for r in rows if r['split']==split))
            objects+=len(annotations)
        return dict(manifest=manifest,payloads=payloads,categories=table,split_counts=split_counts,objects=objects)


def verify(path,output,expected_records=None):
    checked=inspect_archive(path.read_bytes(),expected_records)
    import pycocotools.coco as coco_module
    import torchvision.datasets.coco as tv_module
    import torch
    assert importlib.metadata.version('pycocotools')==PINS['pycocotools']['version']
    assert importlib.metadata.version('torchvision').split('+')[0]==PINS['torchvision']['version']
    assert sha(Path(coco_module.__file__).read_bytes())==PINS['pycocotools']['coco_sha256']
    assert sha(Path(tv_module.__file__).read_bytes())==PINS['torchvision']['source_sha256']
    records={r['asset']:r for r in checked['manifest']['records']};loaded=0
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='actual-coco-reader-',dir=output) as tmp,ExitStack() as guards:
        data=Path(tmp)
        for name,raw in checked['payloads'].items():
            target=data/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        guards.enter_context(patch.object(torch.nn.Module,'__init__',side_effect=AssertionError('Model construction forbidden')))
        guards.enter_context(patch.object(torch.optim.Optimizer,'__init__',side_effect=AssertionError('Optimizer forbidden')))
        for name in ('loadRes','download','annToRLE','annToMask'):
            guards.enter_context(patch.object(coco_module.COCO,name,side_effect=AssertionError('Only bbox reader operations permitted')))
        for split in SPLITS:
            api=coco_module.COCO(str(data/split/'coco.json'))
            assert api.loadCats(api.getCatIds())==checked['categories']
            corpus=tv_module.CocoDetection(data,str(data/split/'coco.json'))
            assert len(corpus)==checked['split_counts'][split]['images']
            for index,image_id in enumerate(corpus.ids):
                info=api.loadImgs(image_id)[0];row=records[info['file_name']]
                image,targets=corpus[index]
                assert image.mode=='RGB' and image.size==(row['width'],row['height'])
                assert sha(str(image.size).encode()+image.tobytes())==row['pixel_hash']
                assert targets==api.loadAnns(api.getAnnIds(imgIds=[image_id]))
                assert len(targets)==len(row['annotation']['boxes'])
                for box,target in zip(row['annotation']['boxes'],targets):
                    assert target['bbox']==[box[k] for k in ('x','y','width','height')]
                    assert api.loadCats([target['category_id']])[0]['name']==box['label']
                loaded+=1
    result=dict(result='PASS',reader_records=loaded,objects=checked['objects'],categories=checked['categories'],
        split_counts=checked['split_counts'],release_sha256=sha(path.read_bytes()),consumer=PINS,
        environment=dict(python=sys.version.split()[0],numpy=importlib.metadata.version('numpy'),Pillow=importlib.metadata.version('Pillow'),
            torch=torch.__version__,torchvision=importlib.metadata.version('torchvision'),pycocotools=importlib.metadata.version('pycocotools'),
            coco_module=str(Path(coco_module.__file__).resolve()),coco_source_sha256=sha(Path(coco_module.__file__).read_bytes()),
            torchvision_module=str(Path(tv_module.__file__).resolve()),torchvision_source_sha256=sha(Path(tv_module.__file__).read_bytes())),
        actual_pycocotools_and_torchvision=True,canonical_annotation_independent_oracle=True,
        source_and_pixel_hashes_verified=True,negative_images_retained=True,
        category_scope='Full exact selected vocabulary, deterministic release-local IDs shared by all splits; not global taxonomy IDs.',
        model_instantiated=False,training_executed=False,evaluation_executed=False,mask_conversion=False,downloads=False,
        basis='Retained authored compatibility pixels; automated review and authored QA boxes are not genuine human labels.')
    (output/'coco-reader-report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def native_roundtrip(raw,source_rows,root):
    destination=Dataset(root/'native-destination')
    try:
        prepared=destination.native_detection_imports.prepare(dict(source_name='actual-coco-export.zip',archive=base64.b64encode(raw).decode()))
        drafts=[];reviewed=[]
        for item in prepared['rows']:
            receipt=destination.native_detection_imports.admit(dict(token=item['token'],request_id=uuid.uuid4().hex))
            row=destination.workbench.get(receipt['record_id']);drafts.append(row)
            before=row['provenance']['acquisition']['declared']['upstream']['record']
            assert before['id']!=row['id'] and row['review']=='draft' and row['provenance']['rights']=='unknown'
            assert row['annotation']==before['annotation'] and row['source_split']==before['split']
            assert row['pixel_hash']==before['pixel_hash'] and row['content_hash']==before['content_hash']
            assert any(r['id']==before['id'] for r in source_rows)
            reviewed.append(destination.workbench.save(row['id'],dict(row,review='human_reviewed')))
        second=freeze(destination,reviewed);inspection=inspect_archive(second,reviewed)
        original=inspect_archive(raw,source_rows)
        assert inspection['categories']==original['categories'] and inspection['split_counts']==original['split_counts']
        by_origin={r['provenance']['acquisition']['declared']['upstream']['record']['id']:r for r in inspection['manifest']['records']}
        for before in original['manifest']['records']:
            after=by_origin[before['id']];upstream=after['provenance']['acquisition']['declared']['upstream']
            assert upstream['category_table']==original['categories']
            mapping={r['name']:r['id'] for r in original['categories']}
            assert upstream['annotation_category_ids']==[mapping[b['label']] for b in before['annotation']['boxes']]
            assert all(after[k]==before[k] for k in ('annotation','pixel_hash','content_hash','split'))
        return second,reviewed,dict(result='PASS',records=len(drafts),new_ids=True,initial_review='draft',initial_rights='unknown',
            exact_geometry_labels_pixels_splits=True,original_category_evidence_retained=True,review_scope='Separate automated QA review; no human corpus claim')
    finally:destination.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path);parser.add_argument('--expected',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    expected=decode(args.expected.read_bytes()) if args.expected else None
    if args.archive:
        result=verify(args.archive,args.output,expected)
    else:
        with tempfile.TemporaryDirectory(prefix='general-coco-',dir=args.output) as tmp:
            source=Dataset(Path(tmp)/'source')
            try:rows=populate(source);raw=freeze(source,rows)
            finally:source.close()
            archive=args.output/'canonical-coco.zip';archive.write_bytes(raw);result=verify(archive,args.output/'source-reader',rows)
            second,reviewed,roundtrip=native_roundtrip(raw,rows,Path(tmp))
            archive=args.output/'roundtrip-coco.zip';archive.write_bytes(second)
            second_result=verify(archive,args.output/'roundtrip-reader',reviewed)
            # Canonical permits explicitly reviewed negatives and zero-weight empty splits;
            # these are separate from the narrower Chapter9 positive/nonempty requirements.
            negative_source=Dataset(Path(tmp)/'source')
            try:
                negatives=[]
                for old in rows[:2]:
                    current=negative_source.workbench.get(old['id'])
                    negatives.append(negative_source.workbench.save(current['id'],dict(current,annotation={'boxes':[]},review='human_reviewed')))
                request=body(negatives);request['ratios']=dict(train=100,validation=0,test=0)
                preview=negative_source.releases.preview(request);assert preview['eligible']
                release=negative_source.releases.create(dict(request,preview_token=preview['preview_token']))
                negative_raw=negative_source.releases.locate(release['id']).read_bytes()
            finally:negative_source.close()
            archive=args.output/'all-negative-coco.zip';archive.write_bytes(negative_raw)
            negative_result=verify(archive,args.output/'all-negative-reader',negatives)
            assert negative_result['categories']==[] and negative_result['objects']==0 and negative_result['reader_records']==2
            result=dict(result='PASS',source_reader=result,roundtrip_reader=second_result,all_negative_reader=negative_result,native_roundtrip=roundtrip,training_executed=False)
    (args.output/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result='PASS',training_executed=False)))


if __name__=='__main__':main()
