"""Actual pinned plyfile file reads, byte-exact releases and fresh-owner transfer.

This is a bounded QA consumer, not a trainer. Review transitions are simulated
test workflow; declared source splits/families are claims, not independence proof.
"""
import argparse
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import plyfile
from app import Dataset
from native_sequence_dataset import bounded_zip
from workbench import encode, WorkbenchError
import pointclouds
from test_pointclouds import fixture, body, review, selection

MAX_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 64
DTYPES = {'float': '<f4', 'double': '<f8', 'uchar': 'u1'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    raw = Path(path).read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def pins():
    pin = json.loads((ROOT / 'tests/pointcloud-consumer-pins.json').read_text())
    assert importlib.metadata.version('plyfile') == pin['plyfile']['version']
    assert np.__version__ == pin['numpy']
    assert sha(Path(plyfile.__file__).read_bytes()) == pin['plyfile']['module_sha256']
    return dict(pin, module=identity(plyfile.__file__))


def read_actual(raw, sidecar, folder):
    prepared = pointclouds.prepare(raw, sidecar)  # Strict bounds/hash/policy before broad reader.
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'points.ply'; path.write_bytes(raw)
    (folder / 'points.json').write_bytes(sidecar)
    with path.open('rb') as source:
        actual = plyfile.PlyData.read(source, mmap=False)
    assert [element.name for element in actual.elements] == ['vertex']
    vertices = actual['vertex'].data
    geometry = prepared['geometry']
    assert vertices.dtype.names == tuple(prop['name'] for prop in geometry['properties'])
    assert len(vertices) == len(geometry['points'])
    attributes = []
    for index, prop in enumerate(geometry['properties']):
        dtype = np.dtype(DTYPES[prop['dtype']])
        assert vertices.dtype[prop['name']] == dtype
        oracle = np.array([point[index] for point in geometry['points']], dtype=dtype)
        assert vertices[prop['name']].tobytes() == oracle.tobytes()
        attributes.append(dict(prop, numpy_dtype=dtype.str, native_sha256=sha(oracle.tobytes()),
                               values=oracle.tolist() if len(oracle) <= 8 else None))
    return {'file': identity(path), 'sidecar': identity(folder / 'points.json'),
            'point_count': len(vertices), 'attributes': attributes, 'status': 'PASS'}


def analytic_originals(output):
    reports = []
    for name in ('colored', 'xyz'):
        raw, sidecar = fixture(name)
        reports.append(read_actual(raw, sidecar, output / 'analytic-originals' / name))
        with (output / 'analytic-originals' / name / 'points.ply').open('rb') as source:
            vertex = plyfile.PlyData.read(source, mmap=False)['vertex'].data
        if name == 'colored':
            expected = {'x':[-0.,1.,2.,.1], 'y':[0.,2.,0.,2.], 'z':[0.,0.,3.,1.],
                        'nx':[0.]*4, 'ny':[0.]*4, 'nz':[2.]*4,
                        'red':[255,0,0,127], 'green':[0,255,0,128], 'blue':[0,0,255,255]}
            assert vertex['x'][0].tobytes() == struct.pack('<I', 0x80000000)
            assert vertex['x'][3].tobytes() == struct.pack('<I', 0x3dcccccd)
        else:
            expected = {'x':[10.,11.,11.], 'y':[0.,1.,1.], 'z':[-0.,2.,2.]}
            assert vertex['z'][0].tobytes() == struct.pack('<Q', 0x8000000000000000)
        for key, values in expected.items():
            assert vertex[key].tobytes() == np.array(values, dtype=vertex.dtype[key]).tobytes()
    return reports


def freeze(dataset, rows, output):
    request = dict(items=selection(rows), ratios=dict(train=50,validation=50,test=0), seed=12)
    preview = dataset.releases.preview(request); assert preview['eligible'], preview
    release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
    shutil.copyfile(dataset.releases.locate(release['id']), output)
    return output


def inspect_release(path, output, expected=None):
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    assert 0 < len(raw) <= MAX_BYTES
    archive = bounded_zip(raw, MAX_RECORDS + 8, MAX_BYTES)
    with archive:
        assert archive.getinfo('manifest.json').file_size <= 8 * 1024 * 1024
        manifest = json.loads(archive.read('manifest.json'))
        records = manifest['records']; assert 1 <= len(records) <= MAX_RECORDS
        assert all(row['kind'] == 'pointcloud' and row['review'] == 'human_reviewed' and row['annotation']['note'].strip() for row in records)
        if expected is not None:
            assert {r['id'] for r in expected} == {r['id'] for r in records}
        typed = [json.loads(line) for split in ('train','validation','test') for line in archive.read(split+'/records.jsonl').splitlines()]
        assert sorted(typed,key=lambda r:r['id']) == sorted(records,key=lambda r:r['id'])
        checks, pairs, families = [], [], {}
        for row in records:
            if expected is not None:
                original = next(r for r in expected if r['id'] == row['id'])
                assert all(row[key] == value for key,value in original.items())
            asset = archive.read(row['asset']); assert sha(asset) == row['content_hash'] == row['asset_sha256']
            assert len(asset) == row['pointcloud']['bundle_bytes']
            pair = bounded_zip(asset, 2, pointclouds.BUNDLE_LIMIT)
            with pair:
                assert pair.namelist() == list(pointclouds.FILES)
                assert pair.getinfo('points.ply').file_size <= pointclouds.PLY_LIMIT
                assert pair.getinfo('points.json').file_size <= pointclouds.MANIFEST_LIMIT
                geometry, sidecar = pair.read('points.ply'), pair.read('points.json')
            prepared = pointclouds.prepare(geometry, sidecar)
            assert prepared['metadata'] == {k:v for k,v in row['pointcloud'].items() if k!='bundle_bytes'}
            lineage = prepared['metadata']['manifest']['lineage']
            assert row['source_split'] == lineage['split']
            if lineage['split'] != 'unassigned': assert row['split'] == lineage['split']
            for group in row['pointcloud']['protected_groups']:
                assert group in row['groups']
                assert group not in families or families[group] == row['split']
                families[group] = row['split']
            checks.append(dict(record_id=row['id'],split=row['split'],lineage=lineage,
                               external=read_actual(geometry,sidecar,output / row['id'])))
            pairs.append((row, geometry, sidecar, asset))
    return dict(archive=identity(path), records=checks, status='PASS'), pairs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--expected',type=Path)
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    result=dict(parser=pins(),analytic_originals=analytic_originals(out),scope='Actual ASCII native point reader and dataset transport only; no inference/training.',consumer_limits=dict(release_bytes=MAX_BYTES,records=MAX_RECORDS))
    if args.archive:
        path=args.archive
        expected=json.loads(args.expected.read_text()) if args.expected else None
    else:
        first=Dataset(str(out/'owner-1'))
        try:
            rows=[pointclouds.admit(first.workbench,body(*fixture(name))) for name in ('colored','xyz')]
            rows.append(pointclouds.admit(first.workbench,body(*fixture(change=lambda m:m['provenance'].update(revision='QA-sidecar-variant')))))
            assert all(r['review']=='draft' and r['annotation'] is None and r['provenance']['rights']=='unknown' for r in rows)
            rows=[review(first.workbench,r) for r in rows]
            expected=rows;path=freeze(first,rows,out/'first-release.zip')
        finally:first.close()
    result['first'],pairs=inspect_release(path,out/'first-extracted',expected)
    second=Dataset(str(out/'owner-2'))
    try:
        rows=[]
        for original,raw,sidecar,asset in pairs:
            row=pointclouds.admit(second.workbench,body(raw,sidecar))
            assert row['id']!=original['id'] and row['review']=='draft' and row['annotation'] is None and row['provenance']['rights']=='unknown'
            assert row['pointcloud']==original['pointcloud'] and row['source_split']==original['source_split']
            assert second.workbench.asset(row['id'])[0]==asset
            rows.append(row)
        request=dict(items=selection(rows),ratios=dict(train=50,validation=50,test=0),seed=99)
        assert not second.releases.preview(request)['eligible']
        rows=[review(second.workbench,r,review='draft') for r in rows]
        rows=[second.workbench.get(r['id']) for r in rows]
        assert all(r['review']=='draft' for r in rows)
        rows=[review(second.workbench,r) for r in rows]
        second_path=freeze(second,rows,out/'second-release.zip')
        result['second'],_=inspect_release(second_path,out/'second-extracted',rows)
        result['transfer']={'byte_exact_raw_pairs':True,'native_attribute_bits':True,'source_lineage_and_declared_fixed_splits':True,
                            'new_ids_draft_unknown_rights':True,'separate_QA_draft_save_reopen_review':True,
                            'unassigned_caveat':'Raw pairs do not transfer sender-local assignments, local IDs/groups/parents/notes/review.'}
    finally:second.close()
    result['numeric_controls']=[]
    raw,_=fixture()
    for token,bits in [('1.0000000596046448',None),('1.0000001788139343',None),('-1.0000000596046448',None),('-1.0000001788139343',None),
                       ('1.000000059604644775390625',0x3f800000),('1.000000178813934326171875',0x3f800002),('-1.000000059604644775390625',0xbf800000),('-1.000000178813934326171875',0xbf800002)]:
        control=fixture(raw=raw.replace(b'1 2 0 ',token.encode()+b' 2 0 '))
        if bits is None:
            try:pointclouds.prepare(*control)
            except WorkbenchError as error:assert 'incompatible' in str(error)
            else:raise AssertionError('Lossy float32 control admitted')
            result['numeric_controls'].append(dict(token=token,status='REJECTED_BEFORE_PUBLICATION'))
        else:
            report=read_actual(*control,out/'numeric-controls'/token)
            with (out/'numeric-controls'/token/'points.ply').open('rb') as source:
                observed=plyfile.PlyData.read(source,mmap=False)['vertex'].data['x'][1].tobytes()
            assert observed==struct.pack('<I',bits)
            result['numeric_controls'].append(dict(token=token,status='PASS',expected_bits=format(bits,'08x'),external=report))
    result['status']='PASS'
    (out/'pointcloud-consumer-report.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Point-cloud actual pinned parser and second-owner raw/native/lineage/fixed-split roundtrip PASS: '+str(out))


if __name__=='__main__':main()
