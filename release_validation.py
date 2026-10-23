"""Closed export workflows; frozen integrity remains with existing native readers."""
import ast
import hashlib
import io
from pathlib import Path
import platform
import zipfile

import mesh_release
import sequence_release
import spatial_release
import canonical_release
import copy
import image_training
import text_training
import audio_training
from workbench import WorkbenchError, encode, text_value

RECIPE = 'mesh_validate_export'
SEQUENCE_RECIPE = 'sequence_validate_export'
CLASSIFICATION_RECIPES = {'image_validate_export': image_training,
                          'text_validate_export': text_training, 'audio_validate_export': audio_training}
POINTCLOUD_RECIPE = 'pointcloud_validate_export'
VOLUME_RECIPE = 'volume_validate_export'
RECIPES = (RECIPE, SEQUENCE_RECIPE, POINTCLOUD_RECIPE, VOLUME_RECIPE, *CLASSIFICATION_RECIPES)
KINDS = {'mesh': RECIPE, 'sequence': SEQUENCE_RECIPE, 'pointcloud': POINTCLOUD_RECIPE, 'volume': VOLUME_RECIPE}
ADAPTER = {'id': RECIPE, 'version': 1}
PARAMETER_BOUNDS = {}
TYPES = ('release', 'validate', 'publish')
PORTS = {'release': (None, 'frozen_release'),
         'validate': ('frozen_release', 'validated_release'),
         'publish': ('validated_release', None)}
PAYLOADS = {'validation-report.json'}


def adapter_identity(recipe=RECIPE):
    if recipe not in RECIPES:
        raise WorkbenchError('Unsupported integrity recipe.', 'unsupported', 400)
    return {'id': recipe, 'version': 1}


def inspect_release(path, release_id, recipe=RECIPE):
    """Read once, validate exact captured bytes, then expose the validated manifest."""
    adapter_identity(recipe)
    if recipe in CLASSIFICATION_RECIPES:
        manifest = CLASSIFICATION_RECIPES[recipe].inspect_release(path, release_id)
        records = manifest['records']
        summary = {'schema_version': 1, 'format': manifest['format'], 'kind': recipe.split('_')[0],
                   'record_count': len(records), 'class_vocabulary': manifest['class_vocabulary'],
                   'split_counts': {split: sum(row['split'] == split for row in records)
                                    for split in ('train', 'validation', 'test')},
                   'scope': 'Frozen classification export integrity only; no model training, predictions or quality qualification.'}
        return manifest, decode_summary(summary,recipe,manifest=manifest,release_id=release_id)
    reader = sequence_release if recipe == SEQUENCE_RECIPE else mesh_release
    try:
        with Path(path).open('rb') as source:
            raw = source.read(canonical_release.MAX_RELEASE_BYTES + 1)
    except OSError:
        raise WorkbenchError('Frozen release is unavailable.', 'unavailable', 409) from None
    if recipe in (POINTCLOUD_RECIPE, VOLUME_RECIPE):
        kind = 'pointcloud' if recipe == POINTCLOUD_RECIPE else 'volume'
        summary = spatial_release.validate_bytes(raw, release_id, kind=kind)
    else:
        summary = reader.validate_bytes(raw, release_id)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = canonical_release.decode(archive.read('manifest.json'))
    return manifest, decode_summary(summary,recipe,manifest=manifest,release_id=release_id)


def decode_class_vocabulary(value,recipe,*,manifest=None):
    """The existing export mapping remains data, including opaque image folders."""
    require=canonical_release.require
    selected=None
    for kind,adapter in (('image',image_training),('text',text_training),('audio',audio_training)):
        if recipe in (kind+'_classification',kind+'_validate_export',adapter.MODEL_RECIPE):selected=kind
    require(selected is not None,'classification vocabulary has no supported recipe.')
    maximum=(image_training.MAX_CLASSES if selected=='image' else
             text_training.projection.MAX_CLASSES if selected=='text' else audio_training.projection.MAX_CLASSES)
    require(type(value) is list and 2<=len(value)<=maximum,'invalid classification vocabulary.')
    for index,item in enumerate(value):
        fields={'label','index','folder'} if selected=='image' else {'label','index'}
        require(type(item) is dict and set(item)==fields,'unexpected class mapping fields.')
        text_value(item['label'],'Class label',80)
        require(type(item['index']) is int and item['index']==index,'class mapping index differs.')
        if selected=='image':require(item['folder']==f'class_{index:06d}','opaque image class folder differs.')
    if manifest is not None:
        import image_classification_export
        projection=image_classification_export if selected=='image' else (
            text_training.projection if selected=='text' else audio_training.projection)
        rows=manifest['records'];expected,_coverage,_blockers=projection.inspect_projection(rows,{r['id']:r['split'] for r in rows})
        require(encode(value)==encode(expected),'class mapping differs from exact frozen labels.')
    return copy.deepcopy(value)


def decode_summary(value,recipe,*,manifest,release_id):
    """Bind a finite integrity DTO to its validated frozen source metadata.

    Native byte parsers remain the scientific/numeric owners. This projection
    neither reads assets nor invents geometry, frames or voxels. Historical
    explanatory text is preserved rather than rewritten to current wording.
    """
    adapter_identity(recipe)
    from workbench import text_value
    require=canonical_release.require
    require(type(value) is dict and type(manifest) is dict and type(manifest.get('records')) is list,
            'integrity summary needs its exact frozen manifest.')
    rows=manifest['records']
    if recipe in CLASSIFICATION_RECIPES:
        fields={'schema_version','format','kind','record_count','class_vocabulary','split_counts','scope'}
        require(set(value)==fields,'unexpected classification integrity summary fields.')
        text_value(value['scope'],'Integrity scope',2000)
        decode_class_vocabulary(value['class_vocabulary'],recipe,manifest=manifest)
        expected=dict(schema_version=1,format=manifest['format'],kind=recipe.split('_')[0],record_count=len(rows),
            class_vocabulary=manifest['class_vocabulary'],split_counts={s:sum(row['split']==s for row in rows)
                for s in canonical_release.SPLITS},scope=value['scope'])
    else:
        kind={RECIPE:'mesh',SEQUENCE_RECIPE:'sequence',POINTCLOUD_RECIPE:'pointcloud',VOLUME_RECIPE:'volume'}[recipe]
        collection='meshes' if kind=='mesh' else kind+'s'
        count_fields={'mesh':('vertex_count','triangle_count'),'sequence':('frame_count',),
                      'pointcloud':('point_count',),'volume':('voxel_count',)}[kind]
        fields={'schema_version','validation','release_sha256',kind+'_count','split_counts','family_scope','limitations',collection,*count_fields}
        require(set(value)==fields,'unexpected whole-asset integrity summary fields.')
        require(type(value['limitations']) is list and len(value['limitations'])<=100,'invalid integrity limitations.')
        for limitation in value['limitations']:text_value(limitation,'Integrity limitation',4000)
        summaries=[]
        for row in rows:
            require(row.get('kind')==kind,'integrity summary modality differs from its frozen source.')
            metadata=row[kind];declared=metadata['manifest']
            if kind=='mesh':
                from meshes import MeshAssets
                MeshAssets.validate_project_metadata(metadata)
            elif kind=='sequence':
                from sequence_assets import SequenceAssets
                SequenceAssets.validate_project_metadata(metadata)
            else:
                from spatial_assets import SpatialAssets
                SpatialAssets.validate_project_metadata(kind,metadata)
            item={key:row[key] for key in ('id','name','revision','source_revision','split','review')}
            item.update(asset_sha256=row['asset_sha256'],units=declared['units'],provenance=declared['provenance'],
                        rights=row['provenance']['rights'])
            if kind=='sequence':
                item.update(run_sha256=metadata['run_sha256'],frames_sha256=declared['frames_sha256'],
                    frame_count=declared['frame_count'],geometry=declared['geometry'],field_types=declared['field_types'],
                    frame_index=metadata['frame_index'],technical_validation=metadata['technical_validation'],
                    pressure_semantics=declared['pressure_semantics'])
            else:
                item['manifest_sha256']=metadata['manifest_sha256']
                if kind in ('mesh','pointcloud'):
                    item.update(geometry_sha256=declared['geometry_sha256'],coordinate_system=declared['coordinate_system'],
                        **{key:metadata[key] for key in ('properties','bounds',*count_fields)})
                    if kind=='pointcloud':
                        item.update(lineage=declared['lineage'],provided_normals=metadata['provided_normals'],provided_colors=metadata['provided_colors'])
                else:
                    item.update(volume_sha256=declared['volume_sha256'],affine=declared['affine'],value_semantics=declared['value_semantics'],
                        array_axes=['z','y','x'],coordinate_contract='Affine maps voxel-center [x,y,z,1] to physical coordinates in declared units.',
                        **{key:metadata[key] for key in ('shape','dtype','order','voxel_count','spacing_xyz')})
            summaries.append(item)
        expected=dict(schema_version=1,validation=kind+'_release_integrity',release_sha256=release_id,
            split_counts={s:sum(row['split']==s for row in rows) for s in canonical_release.SPLITS},
            family_scope='selected_records_only',limitations=value['limitations'],**{kind+'_count':len(rows),collection:summaries})
        expected.update({key:sum(row[key] for row in summaries) for key in count_fields})
    # Existing canonical JSON bounds and scalar checks apply to both operands;
    # exact comparison rejects unknown nested DTO fields without interpreting
    # the source arrays a second time.
    actual=canonical_release.decode(encode(value).encode())
    require(encode(actual)==encode(expected),'integrity summary differs from its exact frozen source metadata.')
    return copy.deepcopy(actual)


def definition_files(source_path):
    """Pin the actual local import closure, without importing or executing discovered code."""
    pending = ['release_validation.py']
    files = {}
    while pending:
        name = pending.pop()
        if name in files:
            continue
        raw = (source_path / name).read_bytes()
        files[name] = hashlib.sha256(raw).hexdigest()
        for node in ast.walk(ast.parse(raw)):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else [])
            for module in modules:
                filename = module.split('.')[0] + '.py'
                if (source_path / filename).is_file() and filename not in files:
                    pending.append(filename)
    return files


def runtime(recipe=RECIPE):
    return {'schema_version': 1, 'available': True, 'adapter': adapter_identity(recipe),
            'runtime': {'python': platform.python_version(), 'execution': 'bounded_local_integrity'}, 'problems': []}


def report(identity, summary, recipe=RECIPE):
    return {'schema_version': 1, 'source_identity': identity, 'adapter': adapter_identity(recipe),
            'validation_summary': summary}


def write_report(directory, identity, summary, recipe=RECIPE):
    contents = encode(report(identity, summary, recipe)).encode()
    (directory / 'validation-report.json').write_bytes(contents)
    inventory = [{'name': 'validation-report.json', 'sha256': hashlib.sha256(contents).hexdigest(),
                  'bytes': len(contents), 'media_type': 'application/json', 'split': None}]
    (directory / 'artifact-manifest.json').write_text(encode(
        {'schema_version': 1, 'source_identity': identity, 'adapter': adapter_identity(recipe), 'artifacts': inventory}), encoding='utf-8')


def verify_directory(directory, identity, summary, recipe=RECIPE):
    """Closed report custody; the durable admission summary is the expected evidence."""
    try:
        paths = list(directory.iterdir())
        if directory.is_symlink() or {p.name for p in paths} != PAYLOADS | {'artifact-manifest.json'}:
            raise ValueError('Unexpected report directory.')
        if any(p.is_symlink() or not p.is_file() or p.stat().st_size > canonical_release.MAX_METADATA_BYTES for p in paths):
            raise ValueError('Report files exceed their bounds or are not regular files.')
        raw = (directory / 'validation-report.json').read_bytes()
        if canonical_release.decode(raw) != report(identity, summary, recipe):
            raise ValueError('Validation report differs from admitted evidence.')
        inventory = [{'name': 'validation-report.json', 'sha256': hashlib.sha256(raw).hexdigest(),
                      'bytes': len(raw), 'media_type': 'application/json', 'split': None}]
        manifest_raw = (directory / 'artifact-manifest.json').read_bytes()
        expected = {'schema_version': 1, 'source_identity': identity, 'adapter': adapter_identity(recipe), 'artifacts': inventory}
        if canonical_release.decode(manifest_raw) != expected:
            raise ValueError('Artifact identity or inventory differs.')
        return inventory + [{'name': 'artifact-manifest.json', 'sha256': hashlib.sha256(manifest_raw).hexdigest(),
                             'bytes': len(manifest_raw), 'media_type': 'application/json', 'split': None}], None
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise WorkbenchError('Validation artifact verification failed: ' + str(error)[:200], 'unavailable', 409) from None


# This adapter executes in process. Never admit disk definitions that differ from
# the application import snapshot; restart to load changed implementation files.
IMPORTED_DEFINITION_FILES = definition_files(Path(__file__).resolve().parent)
