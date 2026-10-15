"""Author a NEW private canonical/catalog scalar A project; never execute it.

The caller first creates real reviewed canonical source with the explicit author
compiler. This finite transformation pins that actual Release/member closure.
Runtime provisioning, shared schema3 support, owner grant and SDK admission are
separate normal workflows. Historical v2 files are read only.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import extension_canonical
import extension_contract
import extension_evidence as evidence
import field_evidence
from tuldok_extension_sdk.manifest import validate

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT/'examples/extensions/field-surrogate/v3-canonical'
ORIGINAL = ROOT/'examples/extensions/field-surrogate/v2'
RUNTIME_SHA = '0b15b611ead55bd5fa6f2f7bbcc56870f6e9f9f60f2192d989e7473ef8af1826'
MODEL_CONFIGURATION = dict(type='object',properties={key:dict(type='number',minimum=-1,maximum=1)
    for key in ('initial_scale','initial_offset')},required=['initial_scale','initial_offset'],additionalProperties=False)
MODEL_DEFAULTS = dict(initial_scale=0.0,initial_offset=0.0)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def prepare(result, destination, *, runtime_sha256=RUNTIME_SHA):
    """Compile source/recipe/provider declarations, with no catalog or runtime hook."""
    evidence.sha(runtime_sha256)
    fixture.verify_source_arrays(result['compilation'],result['releases'])
    destination = Path(destination)
    if destination.exists(): raise ValueError('Select an absent canonical project directory')
    shutil.copytree(PACKAGE,destination,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    def write(name,value):
        raw=evidence.canonical(value)+b'\n';(destination/name).write_bytes(raw);return raw
    recipe=json.loads((ORIGINAL/'recipe.json').read_bytes());policy=recipe['model_evidence']
    recipe.update(schema_version=3,format='external_model_evidence_recipe_v2',id='scalar-a-canonical-v3',
                  name='Private QA canonical scalar A with captured SDK',runtime_snapshot_sha256=runtime_sha256)
    policy['format']=extension_canonical.POLICY_FORMAT
    policy['model_specification'].update(format='canonical_affine_scalar_v3',configuration=MODEL_DEFAULTS)
    policy['output_policy']['stage']='train'
    task=copy.deepcopy(policy['task']['definition']);task.update(version='3.0.0',label='Canonical private QA standalone scalar mapping')
    for port in task['ports']:port['contract']['version']='3.0.0'
    task['stages'][0]['version']='3.0.0'
    policy['task'].update(revision=3,definition=task)
    policy['profile'].update(id='example.scalar-a.canonical-validation',revision=3)
    policy['probe']['data_input']='canonical'
    release_sha,release_raw=next(iter(result['releases'].items()))
    evidence.require(len(result['releases'])==1,'Author template supports one complete canonical Release.')
    derivation=copy.deepcopy(result['receipt']['derivation'])
    native={}
    for case in derivation['cases']:
        for row in case['arrays']:
            original_name=row['output']['name']
            name=('input-initial.npy' if row['field_id']=='initial' else 'reference.npy') if case['split']=='validation' else original_name
            row['output']['name']=name;native[name]=result['outputs'][original_name]
            if case['split']=='train':recipe['outputs'].append(dict(path=name,role='model_evidence',max_bytes=8192,required=True))
    recipe['outputs'].append(dict(path='canonical-derivation.json',role='field_derivation',max_bytes=65536,required=True))
    prediction_names={row['prediction'] for row in policy['field_outputs']}
    points=[policy['profile']['capture']['interval']*step for step in range(1,policy['profile']['capture']['max_snapshots']+1)]
    checkpoint_names={f'checkpoint-{point}.json' for point in points}
    state_names={'transform.npy'} | {f'weights-{point}.npy' for point in points}
    for rule in recipe['outputs']:
        if rule['path'] in native:rule['role']='field_source'
        elif rule['path'] in prediction_names:rule['role']='field_prediction'
        elif rule['path'] in checkpoint_names:rule['role']='model_checkpoint'
        elif rule['path'] in state_names:rule['role']='model_state'
    derivation_raw=write('canonical-derivation.json',derivation)
    provenance_raw=write('canonical-source.json',result['receipt'])
    (destination/'canonical-release.zip').write_bytes(release_raw)
    members=[dict(case_id=case['id'],record_id=result['records'][case['id']]['id'],revision=result['records'][case['id']]['revision'],
                  source_revision=result['records'][case['id']]['source_revision'],split=case['split']) for case in derivation['cases']]
    canonical=dict(format=extension_canonical.FORMAT,release=dict(input='canonical',sha256=release_sha),
        derivation=dict(input='derivation',sha256=sha(derivation_raw),output='canonical-derivation.json'),
        provenance=dict(input='provenance',sha256=sha(provenance_raw)),contract=result['receipt']['contract'],members=members,
        mapping=dict(inputs=[dict(source_field_id='initial',model_field_id='initial')],target=dict(source_field_id='reference')))
    policy['canonical']=canonical
    old_targets={row['frozen_reference']['member_id']:row['target_sha256'] for row in policy['probe']['candidates']}
    policy['field_targets']=[dict(member_id=member['case_id'],field_id=field['id'],payload_sha256=old_targets[member['case_id']])
        for member in members if member['split']=='validation' for field in policy['fields']]
    for candidate in policy['probe']['candidates']:
        candidate['target_sha256']=evidence.digest([dict(field_id=row['field_id'],payload_sha256=row['payload_sha256'])
            for row in policy['field_targets'] if row['member_id']==candidate['frozen_reference']['member_id']])
    for ref in [*policy['fit_members'],*[row['frozen_reference'] for row in policy['probe']['candidates']]]:
        ref.update(input='canonical',sha256=release_sha)
    recipe['inputs']=dict(canonical=dict(max_bytes=1048576),derivation=dict(max_bytes=65536),provenance=dict(max_bytes=65536))
    recipe['arguments']=[dict(input='canonical'),dict(input='derivation'),dict(input='provenance'),dict(model_evidence_context=True),dict(output_dir=True)]
    for field in policy['fields']:
        field['contract']['adapter'].update(name='canonical_affine_scalar_a',version=3)
        field['contract']['output']['stage']='train'
    for metric in policy['metric_definitions']:
        metric['population_sha256']=evidence.digest(sorted([row['frozen_reference'] for row in policy['probe']['candidates']],key=evidence.canonical))
    ports=task['ports'];docs={'task':task}
    for kind,directions in [('model',('input','output')),('trainer',('input','target','output')),('evaluator',('target','output'))]:
        doc=dict(format='tuldok_contribution_v1',id='example.scalar-a:'+kind,version='3.0.0',kind=kind,
                 label='Canonical scalar A '+kind,requires=[],ports=[copy.deepcopy(port) for port in ports if port['direction'] in directions],
                 implementation=dict(source='producer.py',entrypoint='main'))
        if kind=='model':doc.update(parameters=MODEL_CONFIGURATION,defaults=MODEL_DEFAULTS)
        if kind=='trainer':
            schema=dict(type='object',properties={key:{'type':row['type'],'minimum':row['min'],'maximum':row['max']} for key,row in recipe['parameters'].items()},
                        required=list(recipe['parameters']),additionalProperties=False)
            doc.update(parameters=schema,defaults={key:row['default'] for key,row in recipe['parameters'].items()},stages=task['stages'])
        docs[kind]=doc
    docs['view']=dict(format='tuldok_contribution_v1',id='example.scalar-a:view',version='3.0.0',kind='view',
        label='Canonical scalar native field view',requires=[],view=dict(primitive='orthogonal_slices',
        query=dict(id='tuldok:runs.model_evidence',version='2.0.0'),label='Fixed canonical validation fields'))
    contributions=[]
    for kind,doc in docs.items():
        raw=write(kind+'.json',doc);extension_contract.declaration(raw,'contribution')
        contributions.append(dict(id=doc['id'],version=doc['version'],kind=kind,path=kind+'.json',sha256=sha(raw),bytes=len(raw)))
    author_sources=['producer.py','cold_oracle.py','authored-source.json','tuldok_extension_sdk/evidence.py','tuldok_extension_sdk/__init__.py']
    source_refs=[dict(path=name,sha256=sha((destination/name).read_bytes()),bytes=(destination/name).stat().st_size) for name in author_sources]
    extension=json.loads((ORIGINAL/'extension.json').read_bytes())
    extension.update(package=dict(id='example.scalar-a',version='3.0.0'),label='Private QA canonical scalar A with captured SDK',
                     sources=source_refs,contributions=contributions)
    extension['runtime']['snapshot_sha256']=runtime_sha256
    extension['resources']['source_bytes']=262144
    extension_raw=write('extension.json',extension)
    checked=validate(destination,'extension.json')
    evidence.require(checked['packages'][0]['state']=='valid','New author extension declarations are invalid.')
    recipe['extension_selection']=dict(selections={row['kind']:{key:row[key] for key in ('id','version','sha256')} for row in contributions})
    recipe_sources=author_sources+[kind+'.json' for kind in docs]+['extension.json','NOTICE.txt']
    recipe['sources']=[dict(path=name,sha256=sha((destination/name).read_bytes())) for name in recipe_sources]
    closure=evidence.digest(sorted(recipe['sources'],key=lambda row:row['path']))
    policy['adapter_sha256']=closure
    for field in policy['fields']:field['contract']['source_sha256']=closure
    for metric in policy['metric_definitions']:metric['evaluator_sha256']=closure
    recipe_raw=write('recipe.json',recipe)
    project=dict(schema_version=2,id=uuid.uuid4().hex,name='New private canonical scalar A v3',
        data=[dict(id=key,label='Canonical '+key,path=name,sha256=sha((destination/name).read_bytes()))
              for key,name in [('derivation','canonical-derivation.json'),('provenance','canonical-source.json')]],
        recipes=[dict(id=recipe['id'],label=recipe['name'],path='recipe.json',sha256=sha(recipe_raw))],evidence=[],requirements=[],
        extensions=[dict(id='scalar-a',label=extension['label'],path='extension.json',sha256=sha(extension_raw))])
    project_raw=write('project.json',project)
    captured={'input/canonical':release_raw,'input/derivation':derivation_raw,'input/provenance':provenance_raw}
    material=dict(catalog_id=result['receipt']['catalog_id'],inputs=dict(
        canonical=dict(kind='frozen_release',catalog_id=result['receipt']['catalog_id'],release_id=release_sha,measured_sha256=release_sha,bytes=len(release_raw)),
        derivation=dict(measured_sha256=sha(derivation_raw)),provenance=dict(measured_sha256=sha(provenance_raw))))
    extension_canonical.validate_captured(canonical,policy,recipe,material,captured)
    field_evidence.validate_derivation(derivation,canonical['contract'],result['releases'],native)
    return dict(project=project,project_sha256=sha(project_raw),recipe=recipe,recipe_sha256=sha(recipe_raw),
                binding_selection=recipe['extension_selection'],canonical=canonical,
                limitation='New inert author declaration; shared schema3/canonical activation and normal SDK admission remain required.')


# Import the explicit author-side compiler only; no application startup here.
import extension_canonical_fixture as fixture
