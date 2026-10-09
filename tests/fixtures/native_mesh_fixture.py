"""Tiny authored analytic mesh fixtures; no scanned/physical/training data."""
import base64
import json
from pathlib import Path
from workbench import encode
import hashlib

FILES = Path(__file__).parent / 'meshes'


def ref(row):
    return {key: row[key] for key in ('id', 'revision', 'source_revision')}


def pair(name='midpoint', variant=False, token='1.0000000596046448'):
    if name == 'midpoint':
        raw = ("ply\nformat ascii 1.0\ncomment authored exact-decimal mixed-native triangle QA\n"
               "element vertex 3\nproperty float x\nproperty double y\nproperty float z\n"
               "property double nx\nproperty float ny\nproperty double nz\n"
               "element face 1\nproperty list uchar int vertex_indices\nend_header\n"
               + token + " -0.0 0 0 1.0000001788139343 2\n"
               "0 1 0 0 -0.0 2\n0 0 1 0 0 2\n3 0 2 1\n").encode()
        value = json.loads((FILES / 'tetrahedron.json').read_bytes())
        value['provenance'].update(source='Authored exact-decimal triangle control', revision='mesh-native-QA',
                                  description='Mixed native types, midpoint neighbors, non-unit normals; source-derived analytic fixture')
    else:
        raw = (FILES / (name + '.ply')).read_bytes()
        value = json.loads((FILES / (name + '.json')).read_bytes())
    if variant:
        value['provenance']['revision'] += '-variant'
    value.update(geometry_bytes=len(raw), geometry_sha256=hashlib.sha256(raw).hexdigest())
    return raw, encode(value).encode()


def admit(workbench, raw, sidecar, parents=()):
    import meshes
    return meshes.admit(workbench, dict(files={'mesh.ply': base64.b64encode(raw).decode(),
        'mesh.json': base64.b64encode(sidecar).decode()}, parents=list(parents)))


def review(workbench, row):
    return workbench.save(row['id'], dict(ref(row), task='mesh_geometry', groups=row['groups'],
        annotation={'note': 'Authored native mesh transport QA; no simulation or training qualification.'}, review='human_reviewed'))


def populate(dataset):
    w = dataset.workbench
    bridge = w.import_asset(dict(kind='text', name='Retained mesh parent', text='Authored unselected mesh lineage bridge.', groups=['native-mesh-parent']))
    rows = [admit(w, *pair(), parents=[bridge['id']]), admit(w, *pair('tetrahedron')),
            admit(w, *pair(variant=True), parents=[bridge['id']])]
    assert all(row['review'] == 'draft' and row['annotation'] is None and row['provenance']['rights'] == 'unknown' for row in rows)
    rows = [review(w, row) for row in rows]
    deleted = w.delete_text(bridge['id'], {key: bridge[key] for key in ('revision', 'source_revision')})['record']
    return rows, deleted


def freeze(dataset, rows, ratios=None):
    request = dict(items=[ref(row) for row in rows], ratios=ratios or dict(train=50, validation=50, test=0), seed=87)
    preview = dataset.releases.preview(request); assert preview['eligible'], preview
    release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
    return dataset.releases.locate(release['id']).read_bytes(), preview
