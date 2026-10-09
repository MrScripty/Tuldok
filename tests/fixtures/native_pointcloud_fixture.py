"""Authored actual point files plus one known deleted text parent; no scans."""
import base64
import json
from pathlib import Path

FILES=Path(__file__).parent/'pointclouds'


def ref(row):
    return {k:row[k] for k in ('id','revision','source_revision')}


def pair(name='colored',variant=False):
    raw=(FILES/(name+'.ply')).read_bytes();sidecar=(FILES/(name+'.json')).read_bytes()
    if variant:
        value=json.loads(sidecar);value['provenance']['revision']='native-consumer-QA-sidecar-variant'
        sidecar=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return raw,sidecar


def admit(workbench,raw,sidecar,parents=()):
    import pointclouds
    return pointclouds.admit(workbench,dict(files={'points.ply':base64.b64encode(raw).decode(),
        'points.json':base64.b64encode(sidecar).decode()},parents=list(parents)))


def review(workbench,row,status='human_reviewed'):
    return workbench.save(row['id'],dict(ref(row),task='pointcloud_geometry',groups=row['groups'],
        annotation={'note':'Authored native point transport QA; no geometric/training qualification.'},review=status))


def populate(dataset):
    w=dataset.workbench
    bridge=w.import_asset(dict(kind='text',name='Retained geometry parent',text='Authored unselected point-cloud lineage bridge.\n',groups=['native-pointcloud-retained-parent']))
    rows=[admit(w,*pair('colored'),parents=[bridge['id']]),admit(w,*pair('xyz')),
          admit(w,*pair('colored',True),parents=[bridge['id']])]
    assert all(r['review']=='draft' and r['annotation'] is None and r['provenance']['rights']=='unknown' for r in rows)
    rows=[review(w,r) for r in rows]
    deleted=w.delete_text(bridge['id'],{k:bridge[k] for k in ('revision','source_revision')})['record']
    assert not deleted['source_available'] and deleted['source_lineage_known']
    return rows,deleted


def freeze(dataset,rows):
    request=dict(items=[ref(r) for r in rows],ratios=dict(train=50,validation=50,test=0),seed=87)
    preview=dataset.releases.preview(request);assert preview['eligible'],preview
    release=dataset.releases.create(dict(request,preview_token=preview['preview_token']))
    return dataset.releases.locate(release['id']).read_bytes(),preview
