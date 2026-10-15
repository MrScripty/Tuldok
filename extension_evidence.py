"""Bounded declarative external field evidence; never executes or loads model state.

Pipeline supplies retained composition, Runs supplies attempt identity and custody.
The author owns numerical meaning. Verified here means complete structural and
identity closure; numerical/physical acceptance remains separate task evidence.
"""
import copy
import hashlib
from functools import wraps
import json
import math
import os
from pathlib import Path
import re
import stat
import struct

from workbench import WorkbenchError, encode

RECIPE_FORMAT = 'external_model_evidence_recipe_v1'
POLICY_FORMAT = 'extension_field_policy_v1'
CONTEXT_FORMAT = 'extension_evidence_context_v1'
CONTEXT_PATH = 'runtime-bootstrap/model-evidence-context.json'
MAX_CONTEXT_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_SHARD_BYTES = 8 * 1024 * 1024
MAX_INTEGER = 2**53 - 1
SHA = re.compile(r'[a-f0-9]{64}')
ID = re.compile(r'[a-f0-9]{32}')
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
FILENAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}')
CAPABILITIES = ['checkpoints', 'fixed_validation_predictions', 'scalar_history', 'field_pairs']
COMMON_FILES = {'execution-context.json','model-evidence.json','model-definition.json','profile.json','probe.json',
                'metric-definitions.json','checkpoints.json','observations.json','field-index.json',
                'fitted-transform.json','output-policy.json'}


def boundary(function):
    """Malformed documents refuse through one typed domain boundary."""
    @wraps(function)
    def checked_call(*args,**kwargs):
        try:return function(*args,**kwargs)
        except WorkbenchError:raise
        except ImportError:raise WorkbenchError('Canonical extension evidence dependency is unavailable.','unavailable',409) from None
        except (KeyError,TypeError,ValueError,OverflowError,RecursionError,UnicodeError):
            raise WorkbenchError('Malformed extension evidence document.','invalid',400) from None
    return checked_call


def require(condition, reason, code='invalid'):
    if not condition:raise WorkbenchError('Extension evidence: '+reason,code,409 if code in ('stale','unavailable','unsupported') else 400)


def closed(value, keys, label):
    require(type(value) is dict and set(value)==set(keys),label+' fields differ.')


def natural(value, label, minimum=0, maximum=MAX_INTEGER):
    require(type(value) is int and minimum<=value<=maximum,label+' exceeds its integer domain.')
    return value


def text(value, label, maximum=120):
    require(type(value) is str and value.strip() and len(value)<=maximum and
            not any(ord(c)<32 or 127<=ord(c)<=159 or 0xD800<=ord(c)<=0xDFFF for c in value),label+' is invalid.')
    return value


def sha(value):
    require(type(value) is str and SHA.fullmatch(value),'Expected exact SHA256.')
    return value


def canonical(value):
    try:return encode(value).encode()
    except (ValueError,TypeError,RecursionError):raise WorkbenchError('Extension evidence requires finite JSON.') from None


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def identical(left,right):return canonical(left)==canonical(right)


def decode(raw, maximum=MAX_SHARD_BYTES):
    require(type(raw) is bytes and len(raw)<=maximum,'JSON exceeds its byte bound.')
    import agent_api
    try:return agent_api.decode(raw)
    except agent_api.AgentAPIError:raise WorkbenchError('Extension evidence requires bounded strict JSON.') from None


def checked(value, maximum=MAX_CONTEXT_BYTES):
    return decode(canonical(value),maximum)


def name(value):
    require(type(value) is str and FILENAME.fullmatch(value) and value not in ('artifact-manifest.json','custody-receipt.json'),'Blob name must be flat and declared.')
    return value


def reference(value, kind, catalog_id):
    keys={'kind','catalog_id','id','sha256'}|({'revision'} if kind in ('task','model','profile') else set())
    closed(value,keys,kind+' reference');sha(value['sha256'])
    require(value['kind']==kind and value['catalog_id']==catalog_id,'Reference owner differs.')
    if kind in ('model','evidence'):require(type(value['id']) is str and ID.fullmatch(value['id']),'Reference ID differs.')
    elif kind=='recipe_material':require(value['id']==value['sha256'],'Composition content identity differs.')
    else:text(value['id'],'Definition ID',64)
    if 'revision' in keys:natural(value['revision'],'Definition revision',1)
    return value


def source_reference(value, split):
    closed(value,('input','sha256','member_id','split'),'Frozen authored input reference')
    require(type(value['input']) is str and TOKEN.fullmatch(value['input']),'Input name differs.')
    sha(value['sha256']);text(value['member_id'],'Member ID',64)
    require(value['split']==split and split in ('train','validation'),'Test and unknown populations are unsupported.','unsupported')
    return value


def clocks(value, clock):
    closed(value,('optimizer_update','epoch','fit_pass','physical_time','wall_elapsed_ms'),'Clocks')
    natural(value['wall_elapsed_ms'],'Wall elapsed milliseconds')
    require(value['physical_time'] is None,'Standalone field evidence has no physical timeline.','unsupported')
    for key in ('optimizer_update','epoch','fit_pass'):
        if value[key] is not None:natural(value[key],key,0 if key=='optimizer_update' else 1)
    require(value[clock] is not None,'Applicable progress clock is missing.')
    return value[clock]


@boundary
def validate_policy(value, definition):
    """Closed authored declarations selected only by the explicit schema2 recipe."""
    value=checked(value)
    closed(value,('format','task','adapter_sha256','profile','probe','fit_members','fields','field_outputs',
                  'metric_definitions','model_specification','preprocessing_policy','output_policy','probe_inputs'),'Policy')
    require(value['format']==POLICY_FORMAT,'Unsupported policy.','unsupported')
    require(definition['format']==RECIPE_FORMAT and definition['schema_version']==2,'Policy requires the selected model-evidence recipe.','unsupported')
    require(value['adapter_sha256']==digest(sorted(definition['sources'],key=lambda item:item['path'])),'Adapter source closure differs.')
    task=value['task'];closed(task,('id','revision','definition'),'Task declaration')
    text(task['id'],'Task ID',64);natural(task['revision'],'Task revision',1)
    require(type(task['definition']) is dict and task['definition'],'Task definition is required.')
    for key in ('model_specification','preprocessing_policy','output_policy'):
        require(type(value[key]) is dict and value[key],key+' requires an explicit definition.')
    profile=value['profile'];closed(profile,('id','revision','probe_selection','capture','required_capabilities','optional_capabilities','limits'),'Profile declaration')
    text(profile['id'],'Profile ID',64);natural(profile['revision'],'Profile revision',1)
    selection=profile['probe_selection'];closed(selection,('role','algorithm','namespace','seed','count'),'Probe selection')
    require(selection['role']=='validation' and selection['algorithm']=='sha256_rank_v1','Only fixed validation probes are supported.','unsupported')
    text(selection['namespace'],'Probe namespace',64);natural(selection['seed'],'Probe seed');natural(selection['count'],'Probe count',1,8)
    capture=profile['capture'];closed(capture,('clock','interval','retain_selected','max_snapshots'),'Capture policy')
    require(capture['clock'] in ('optimizer_update','epoch','fit_pass') and capture['retain_selected'] is True,'Unsupported capture policy.','unsupported')
    natural(capture['interval'],'Capture interval',1);natural(capture['max_snapshots'],'Snapshot count',1,8)
    require(profile['required_capabilities']==CAPABILITIES and profile['optional_capabilities']==[],'Required field capabilities cannot be downgraded.','unsupported')
    limits=profile['limits'];closed(limits,('manifest_bytes','shard_bytes','total_output_bytes'),'Profile limits')
    natural(limits['manifest_bytes'],'Manifest bound',1,MAX_MANIFEST_BYTES)
    natural(limits['shard_bytes'],'Shard bound',1,MAX_SHARD_BYTES)
    natural(limits['total_output_bytes'],'Output bound',1,definition['resources']['max_output_bytes'])
    probe=value['probe'];closed(probe,('data_input','candidates'),'Probe declaration')
    require(type(probe['data_input']) is str and probe['data_input'] in definition['inputs'],'Probe data must be an actual captured input.')
    candidates=probe['candidates'];require(type(candidates) is list and len(candidates)==selection['count'],'Initial profile retains the complete declared validation population.','unsupported')
    seen=set()
    for member in candidates:
        closed(member,('frozen_reference','input_sha256','target_sha256'),'Probe member')
        ref=source_reference(member['frozen_reference'],'validation');sha(member['input_sha256']);sha(member['target_sha256'])
        require(ref['input']==probe['data_input'] and ref['member_id'] not in seen,'Probe membership differs or is repeated.')
        seen.add(ref['member_id'])
    fit=value['fit_members'];require(type(fit) is list and 1<=len(fit)<=256,'Training membership must be bounded and explicit.')
    fit_ids=set()
    for member in fit:
        source_reference(member,'train');key=(member['input'],member['member_id'])
        require(member['input'] in definition['inputs'] and key not in fit_ids and
                not any(member['input']==row['frozen_reference']['input'] and member['member_id']==row['frozen_reference']['member_id'] for row in candidates),'Fit/probe membership overlaps or repeats.')
        fit_ids.add(key)
    import field_evidence
    import scientific_fields
    fields=value['fields'];require(type(fields) is list and 1<=len(fields)<=4,'Declare1..4 bounded field stages.')
    field_ids=set()
    for field in fields:
        closed(field,('id','contract','geometry','gauge_policy'),'Field stage')
        require(type(field['id']) is str and TOKEN.fullmatch(field['id']) and field['id'] not in field_ids,'Field stage IDs must be unique.')
        field_ids.add(field['id']);field_evidence.validate_contract(field['contract']);scientific_fields.grid_contract(field['geometry'])
        natural(field['contract']['adapter']['version'],'Field adapter version',1)
        require(field['contract']['source_sha256']==value['adapter_sha256'] and field['contract']['time_mode']=='standalone','Field adapter source/time differs.')
        require(type(field['gauge_policy']) is dict and field['gauge_policy'] and
                digest(field['gauge_policy'])==field['contract']['output']['gauge_policy_sha256'],'Explicit gauge identity differs.')
        for input_field in field['contract']['inputs']:
            require(input_field['shape_zyx']==scientific_fields.shape_for(field['geometry'],input_field),
                    'Probe input shape differs from explicit field geometry.')
        output=field['contract']['output']
        require(output['dtype']=='<f8' and output['centering']=='cell' and
                output['shape_zyx']==scientific_fields.shape_for(field['geometry'],output),'Initial field pair requires exact float64 cell geometry.','unsupported')
        require(math.prod(output['shape_zyx'])*8+4096<=limits['shard_bytes'],'Field array cannot fit the admitted shard bound.','unsupported')
    require(all(identical(item['contract']['inputs'],fields[0]['contract']['inputs']) and identical(item['geometry'],fields[0]['geometry']) for item in fields),
            'All field stages must bind the same explicit probe input fields.')
    outputs={item['path']:item for item in definition['outputs']}
    require(COMMON_FILES<=set(outputs) and all(outputs[key]['required'] for key in COMMON_FILES),'Every common evidence file must be declared required.')
    probe_inputs=value['probe_inputs'];require(type(probe_inputs) is list and len(probe_inputs)==len(candidates),'Every probe input field must be retained.')
    input_members=set()
    for row in probe_inputs:
        closed(row,('member_id','fields'),'Probe input inventory')
        require(row['member_id'] in seen and row['member_id'] not in input_members,'Probe input member differs or repeats.');input_members.add(row['member_id'])
        require(type(row['fields']) is list and len(row['fields'])==len(fields[0]['contract']['inputs']),'Required probe input field is missing.')
        for item,expected_input in zip(row['fields'],fields[0]['contract']['inputs'],strict=True):
            closed(item,('field_id','artifact'),'Probe input field')
            require(item['field_id']==expected_input['field_id'],'Probe input field order/identity differs.')
            name(item['artifact']);require(item['artifact'] in outputs and outputs[item['artifact']]['required'],'Probe input must be a declared required artifact.')
    bindings=value['field_outputs'];require(type(bindings) is list and len(bindings)==len(fields)*len(candidates)*capture['max_snapshots'],'Field output coverage differs.')
    expected={(capture['interval']*step,field_id,member_id) for step in range(1,capture['max_snapshots']+1) for field_id in field_ids for member_id in seen}
    actual=set()
    for binding in bindings:
        closed(binding,('clock','field_id','member_id','prediction','reference'),'Field output binding')
        natural(binding['clock'],'Output clock',1)
        require(type(binding['field_id']) is str and type(binding['member_id']) is str,'Field output identities must be text.')
        key=(binding['clock'],binding['field_id'],binding['member_id'])
        require(key in expected and key not in actual,'Field output binding is missing/repeated or differs.')
        actual.add(key)
        for key in ('prediction','reference'):
            name(binding[key]);require(binding[key] in outputs and outputs[binding[key]]['required'],'Bound field output is not declared required.')
    require(actual==expected,'Field output coverage differs.')
    definitions=value['metric_definitions'];require(type(definitions) is list and 1<=len(definitions)<=16,'Declare bounded metric meanings.')
    metric_ids=set();population=digest(sorted([item['frozen_reference'] for item in candidates],key=canonical))
    for metric in definitions:
        closed(metric,('id','semantic_version','split','units','direction','reduction','population_sha256','domain','undefined_rule','evaluator_sha256','preprocessing_sha256'),'Metric definition')
        text(metric['id'],'Metric ID',64);require(metric['id'] not in metric_ids,'Repeated metric ID.');metric_ids.add(metric['id'])
        natural(metric['semantic_version'],'Metric semantic version',1)
        require(metric['split']=='validation' and metric['direction'] in ('minimize','maximize'),'Unsupported metric population/direction.','unsupported')
        for key in ('units','reduction','undefined_rule'):text(metric[key],key,120)
        require(metric['population_sha256']==population and metric['evaluator_sha256']==value['adapter_sha256'] and
                metric['preprocessing_sha256']==digest(value['preprocessing_policy']),'Metric evaluator/population/preprocessing identity differs.')
        domain=metric['domain'];closed(domain,('minimum','maximum'),'Metric domain')
        require(all(type(domain[k]) in (int,float) and math.isfinite(domain[k]) for k in domain) and domain['minimum']<=domain['maximum'],'Metric domain must be finite/ordered.')
    return value


@boundary
def resolve(policy, model_material, execution_material):
    """Bind authored declarations to published Model and actual captured data."""
    policy=validate_policy(policy,execution_material['recipe'])
    model=model_material['material'];ref=model_material['ref'];catalog_id=execution_material['catalog_id']
    reference(ref,'model',catalog_id)
    require(type(execution_material['inputs']) is dict and
            all(type(item) is dict and 'kind' not in item for item in execution_material['inputs'].values()),
            'Authored input mode rejects every unsupported receipt, including unused inputs.','unsupported')
    task={'kind':'task','catalog_id':catalog_id,'id':policy['task']['id'],'revision':policy['task']['revision'],'sha256':digest(policy['task']['definition'])}
    require(identical(model['task'],task),'Published model Task differs from selected policy.','stale')
    for key,policy_key in (('specification','model_specification'),('preprocessing_policy','preprocessing_policy'),('output_policy','output_policy')):
        require(model[key]['sha256']==digest(policy[policy_key]),'Published model '+key+' differs from selected policy.','stale')
    for source in [*policy['fit_members'],*[item['frozen_reference'] for item in policy['probe']['candidates']]]:
        captured=execution_material['inputs'].get(source['input'])
        require(type(captured) is dict and 'kind' not in captured and captured.get('measured_sha256')==source['sha256'],
                'Initial field evidence requires exact authored project input receipts; protected/frozen/Run populations are unsupported.','unsupported')
    profile=copy.deepcopy(policy['profile']);profile.pop('id');profile.pop('revision')
    profile.update(format='resolved_profile_v1',definition={'kind':'profile','catalog_id':catalog_id,'id':policy['profile']['id'],
                   'revision':policy['profile']['revision'],'sha256':digest(policy['profile'])},
                   task_sha256=task['sha256'],trainer_sha256=digest(execution_material['recipe']),model_sha256=ref['sha256'])
    data_sha=execution_material['inputs'][policy['probe']['data_input']]['measured_sha256']
    selection=profile['probe_selection'];members=copy.deepcopy(policy['probe']['candidates'])
    members.sort(key=lambda item:(digest([selection['namespace'],data_sha,item['frozen_reference'],selection['seed']]),canonical(item['frozen_reference'])))
    probe={'format':'probe_v1','task_sha256':task['sha256'],'data_sha256':data_sha,'split':'validation',
           'selection_policy_sha256':digest(selection),'members':[dict(item,ordinal=i) for i,item in enumerate(members)]}
    return checked({'format':'extension_evidence_static_v1','catalog_id':catalog_id,'model':ref,'task':task,
                    'profile':profile,'probe':probe,'policy':policy,'inputs':execution_material['inputs'],'parameters':execution_material['parameters'],
                    'execution_material_sha256':digest(execution_material)})


@boundary
def context(static_context, composition_ref, run_id, request_sha256):
    static_context=checked(static_context);catalog_id=static_context['catalog_id']
    reference(composition_ref,'recipe_material',catalog_id)
    require(type(run_id) is str and ID.fullmatch(run_id),'Runs must supply the exact attempt ID.')
    sha(request_sha256)
    return checked({'format':CONTEXT_FORMAT,'static':static_context,'composition':composition_ref,
                    'run_id':run_id,'request_sha256':request_sha256})


@boundary
def validate_context(value, run, composition, static_context):
    expected=context(static_context,composition['ref'],run['id'],run['request_sha256'])
    require(identical(value,expected) and identical(composition['material']['model'],static_context['model']) and
            composition['material']['executable_sha256']==static_context['execution_material_sha256'] and
            run.get('approval_material_sha256')==composition['ref']['sha256'],
            'Attempt context differs from retained full composition.','unavailable')
    return expected


def file_identity(value):
    return (value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_uid,
            value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def retained_directory(function):
    """Hold one decoder root and recheck the current path before success."""
    @wraps(function)
    def anchored(directory,*args,**kwargs):
        descriptor=None
        try:
            descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            before=os.fstat(descriptor)
            result=function(descriptor,*args,**kwargs)
            require(file_identity(before)==file_identity(os.fstat(descriptor))==
                    file_identity(os.stat(directory,follow_symlinks=False)),
                    'Evidence directory identity changed during decoding.','unavailable')
            return result
        except OSError:
            raise WorkbenchError('Extension evidence directory is unavailable.','unavailable',409) from None
        finally:
            if descriptor is not None:os.close(descriptor)
    return anchored


def read_regular(directory, filename, maximum):
    name(filename);root=fd=None
    try:
        root=os.dup(directory) if type(directory) is int else os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        root_before=os.fstat(root)
        fd=os.open(filename,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=root)
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1 and before.st_size<=maximum,'Evidence requires a bounded owned regular file.','unavailable')
        chunks=[];remaining=maximum+1
        while remaining:
            raw=os.read(fd,min(remaining,65536))
            if not raw:break
            chunks.append(raw);remaining-=len(raw)
        after=os.fstat(fd);raw=b''.join(chunks)
        current=os.stat(filename,dir_fd=root,follow_symlinks=False)
        require(file_identity(before)==file_identity(after)==file_identity(current) and
                file_identity(root_before)==file_identity(os.fstat(root)) and
                (type(directory) is int or file_identity(root_before)==file_identity(os.stat(directory,follow_symlinks=False))) and
                len(raw)==after.st_size and len(raw)<=maximum,'Evidence path or file changed while reading.','unavailable')
        return raw
    except OSError:raise WorkbenchError('Extension evidence file is unavailable.','unavailable',409) from None
    finally:
        if fd is not None:os.close(fd)
        if root is not None:os.close(root)


@boundary
@retained_directory
def verify(directory, run, admitted_context):
    """Verify structural closure after custody. Caller rederives authoritative context.

    The returned private array bytes are only for the bounded query below; they
    never become a transport document or authority for another Run.
    """
    admitted_context=checked(admitted_context)
    closed(admitted_context,('format','static','composition','run_id','request_sha256'),'Admitted context')
    context_raw=canonical(admitted_context)
    proof=run['spec'].get('model_evidence_context')
    require(type(proof) is dict and proof.get('sha256')==hashlib.sha256(context_raw).hexdigest() and
            proof.get('bytes')==len(context_raw) and identical(run.get('extension_context'),admitted_context),
            'Context is not the exact custody-bound admitted document.','unavailable')
    require(admitted_context['format']==CONTEXT_FORMAT and admitted_context['run_id']==run['id'] and
            admitted_context['request_sha256']==run['request_sha256'] and
            admitted_context['static']['catalog_id']==run['dataset_id'] and
            admitted_context['composition']['sha256']==run.get('approval_material_sha256') and
            admitted_context['static']['execution_material_sha256']==run['material_sha256'],'Run/context binding differs.','unavailable')
    static=admitted_context['static'];policy=validate_policy(static['policy'],run['material']['recipe'])
    limits=static['profile']['limits'];outputs={item['path']:item for item in run['outputs']}
    require(COMMON_FILES<=set(outputs),'Missing evidence declaration.')
    inventory=run['artifacts']
    require(type(inventory) is list and len(inventory)<=len(outputs),'Retained artifact inventory differs.','unavailable')
    retained={}
    for item in inventory:
        closed(item,('name','role','bytes','sha256','media_type'),'Retained artifact')
        require(item['name'] in outputs and item['name'] not in retained,'Retained artifact membership differs.','unavailable')
        sha(item['sha256']);natural(item['bytes'],'Retained artifact bytes',0,outputs[item['name']]['max_bytes'])
        require(item['role']==outputs[item['name']]['role'] and item['media_type']=='application/octet-stream','Retained artifact contract differs.','unavailable')
        retained[item['name']]=item
    require(all(not rule['required'] or filename in retained for filename,rule in outputs.items()),'Retained artifact inventory is incomplete.','unavailable')
    payloads={};total=0
    for filename,rule in outputs.items():
        try:raw=read_regular(directory,filename,min(rule['max_bytes'],limits['shard_bytes']))
        except WorkbenchError:
            if rule['required']:raise
            try:os.stat(filename,dir_fd=directory,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise
            continue
        item=retained.get(filename)
        require(item is not None and item['bytes']==len(raw) and item['sha256']==hashlib.sha256(raw).hexdigest(),
                'Exact decoder payload differs from authoritative retained artifact identity.','unavailable')
        total+=len(raw);require(total<=limits['total_output_bytes'],'Evidence exceeds the admitted aggregate bound.')
        payloads[filename]=raw
    require(set(payloads)==set(retained),'Consumed artifact inventory differs from authoritative retained inventory.','unavailable')
    require(payloads.get('execution-context.json')==context_raw,'Published context differs from exact admitted bytes.')
    def document(filename):return decode(payloads[filename],limits['manifest_bytes'] if filename=='model-evidence.json' else limits['shard_bytes'])
    def blob(item):
        closed(item,('name','sha256','bytes','media_type'),'Blob');name(item['name']);sha(item['sha256']);natural(item['bytes'],'Blob size',1,limits['shard_bytes']);text(item['media_type'],'Blob media type',80)
        raw=payloads.get(item['name']);require(type(raw) is bytes and len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256'],'Blob differs from declared retained inventory.')
        return raw
    manifest=document('model-evidence.json')
    closed(manifest,('format','schema_version','producer','task','model_sha256','data_sha256','profile_sha256','probe','metric_definitions','checkpoints','observations','field_index','coverage','inference'),'Evidence manifest')
    require(manifest['format']=='model_evidence_v1' and type(manifest['schema_version']) is int and manifest['schema_version']==1,'Unsupported evidence envelope.','unsupported')
    require(manifest['producer']=={'catalog_id':run['dataset_id'],'run_id':run['id'],'material_sha256':admitted_context['composition']['sha256'],'adapter_sha256':policy['adapter_sha256']} and
            identical(manifest['task'],static['task']) and manifest['model_sha256']==static['model']['sha256'] and
            manifest['data_sha256']==static['probe']['data_sha256'] and manifest['profile_sha256']==digest(static['profile']) and
            manifest['coverage']=={'required':CAPABILITIES,'optional':[],'omitted':[]},'Evidence differs from admitted model/task/profile/source.')
    for key,filename,expected in (('probe','probe.json',static['probe']),('metric_definitions','metric-definitions.json',policy['metric_definitions'])):
        require(manifest[key]['name']==filename and identical(decode(blob(manifest[key])),expected),key+' identity differs.')
    require(identical(document('model-definition.json'),policy['model_specification']) and identical(document('profile.json'),static['profile']) and
            identical(document('output-policy.json'),policy['output_policy']),'Retained definition/profile/output policy differs.')
    transform=document('fitted-transform.json')
    closed(transform,('format','fit_scope','fit_members','state'),'Fitted transform')
    require(transform['format']=='fitted_transform_v1' and transform['fit_scope']=='train' and identical(transform['fit_members'],policy['fit_members']),'Fitted transform must bind only admitted training members.')
    blob(transform['state'])
    transform_sha=hashlib.sha256(payloads['fitted-transform.json']).hexdigest()
    inference=manifest['inference'];closed(inference,('mode','fitted_transforms','output_policy_sha256'),'Inference policy')
    require(inference['mode']=='eval_no_grad' and inference['output_policy_sha256']==digest(policy['output_policy']) and
            type(inference['fitted_transforms']) is list and len(inference['fitted_transforms'])==1 and
            inference['fitted_transforms'][0]['name']=='fitted-transform.json' and blob(inference['fitted_transforms'][0])==payloads['fitted-transform.json'],'Inference transform/output policy differs.')
    require(manifest['checkpoints']['name']=='checkpoints.json','Checkpoint index name differs.')
    index=decode(blob(manifest['checkpoints']));closed(index,('format','run_id','entries'),'Checkpoint index')
    capture=static['profile']['capture'];clock=capture['clock']
    require(index['format']=='checkpoint_index_v1' and index['run_id']==run['id'] and type(index['entries']) is list and
            len(index['entries'])==capture['max_snapshots'],'Required checkpoint cadence is incomplete.')
    checkpoints={};previous_wall=0;selected=[]
    for ordinal,entry in enumerate(index['entries'],1):
        closed(entry,('checkpoint','model_sha256','fitted_transform_sha256','clocks','selected','state'),'Checkpoint entry')
        point=clocks(entry['clocks'],clock)
        require(point==ordinal*capture['interval'] and entry['clocks']['wall_elapsed_ms']>=previous_wall and
                entry['model_sha256']==static['model']['sha256'] and entry['fitted_transform_sha256']==transform_sha and
                entry['state']=='retained' and type(entry['selected']) is bool,'Checkpoint clock/model/transform differs.')
        previous_wall=entry['clocks']['wall_elapsed_ms']
        descriptor=decode(blob(entry['checkpoint']));closed(descriptor,('format','run_id','model_sha256','weights','fitted_transform_sha256','clocks'),'Checkpoint descriptor')
        clocks(descriptor['clocks'],clock)
        require(descriptor['format']=='checkpoint_state_v1' and descriptor['run_id']==run['id'] and
                all(identical(descriptor[key],entry[key]) for key in ('model_sha256','fitted_transform_sha256','clocks')),'Checkpoint descriptor binding differs.')
        blob(descriptor['weights']);key=entry['checkpoint']['sha256'];require(key not in checkpoints,'Repeated checkpoint descriptor.')
        checkpoints[key]={'entry':entry,'descriptor':descriptor,'point':point}
        if entry['selected']:selected.append(key)
    require(len(selected)==1,'Exactly one retained checkpoint must be selected.')
    require(type(manifest['observations']) is list and len(manifest['observations'])==1 and manifest['observations'][0]['name']=='observations.json','Observation shards differ.')
    observations=decode(blob(manifest['observations'][0]));require(type(observations) is list and len(observations)==len(checkpoints)*len(policy['metric_definitions']),'Metric coverage differs.')
    metric_by_id={item['id']:item for item in policy['metric_definitions']};seen=set()
    for row in observations:
        require(type(row) is dict,'Observation must be an object.')
        state=row.get('state');keys=('value','sample_count') if state=='observed' else ('reason',) if state=='undefined' else ()
        require(keys,'Unknown observation outcome.')
        closed(row,('run_id','checkpoint_sha256','probe_sha256','metric_id','split','clocks','state',*keys),'Observation')
        key=(row['checkpoint_sha256'],row['metric_id']);require(key not in seen and key[0] in checkpoints and key[1] in metric_by_id,'Observation membership differs.');seen.add(key)
        clocks(row['clocks'],clock)
        require(row['run_id']==run['id'] and row['probe_sha256']==manifest['probe']['sha256'] and row['split']=='validation' and identical(row['clocks'],checkpoints[key[0]]['entry']['clocks']),'Observation context differs.')
        if state=='observed':
            domain=metric_by_id[key[1]]['domain'];require(type(row['value']) in (int,float) and math.isfinite(row['value']) and domain['minimum']<=row['value']<=domain['maximum'],'Observation is outside the metric domain.')
            require(type(row['sample_count']) is int and row['sample_count']==len(static['probe']['members']),'Observation population differs.')
        else:
            text(row['reason'],'Undefined arithmetic reason',64)
            require(metric_by_id[key[1]]['undefined_rule']!='not_applicable' and row['reason']==metric_by_id[key[1]]['undefined_rule'],
                    'Undefined observation differs from admitted arithmetic rule.')
    require(manifest['field_index']['name']=='field-index.json','Field index name differs.')
    field_index=decode(blob(manifest['field_index']));fields=policy['fields'];members=static['probe']['members']
    require(type(field_index) is list and len(field_index)==len(checkpoints)*len(fields),'Field checkpoint/stage coverage differs.')
    import field_evidence
    import scientific_fields
    input_bindings={row['member_id']:row['fields'] for row in policy['probe_inputs']}
    for member in members:
        hashes=[]
        for source,field in zip(input_bindings[member['frozen_reference']['member_id']],fields[0]['contract']['inputs'],strict=True):
            payload,_=scientific_fields.npy_payload(payloads[source['artifact']],field,fields[0]['geometry'])
            hashes.append({'field_id':field['field_id'],'payload_sha256':hashlib.sha256(payload).hexdigest()})
        require(digest(hashes)==member['input_sha256'],'Retained probe input payload differs from admitted identity.')
    arrays={};field_records=[];position=0
    bindings={(item['clock'],item['field_id'],item['member_id']):item for item in policy['field_outputs']}
    for checkpoint_sha,checkpoint in checkpoints.items():
        for field in fields:
            group=field_index[position];position+=1
            closed(group,('run_id','checkpoint_sha256','probe_sha256','cases'),'Field index entry')
            require(group['run_id']==run['id'] and group['checkpoint_sha256']==checkpoint_sha and group['probe_sha256']==manifest['probe']['sha256'] and
                    type(group['cases']) is list and len(group['cases'])==len(members),'Field index context/membership differs.')
            for member,row in zip(members,group['cases'],strict=True):
                closed(row,('member_ordinal','predicted','reference','mask','geometry_sha256','time_units','gauge_policy_sha256'),'Field case')
                binding=bindings[(checkpoint['point'],field['id'],member['frozen_reference']['member_id'])]
                output=field['contract']['output']
                require(type(row['member_ordinal']) is int and row['member_ordinal']==member['ordinal'] and row['geometry_sha256']==digest(field['geometry']) and
                        row['gauge_policy_sha256']==output['gauge_policy_sha256'] and row['time_units']=='not_applicable' and row['mask'] is None and
                        row['predicted']['name']==binding['prediction'] and row['reference']['name']==binding['reference'],'Field stage/geometry/gauge/output context differs.')
                blob(row['predicted']);blob(row['reference'])
                pair={key:output[key] for key in ('dtype','shape_zyx','centering','stage','units','gauge_policy_sha256')}
                pair.update(geometry=field['geometry'],prediction=row['predicted'],reference=row['reference'],mask=None)
                field_evidence.validate_pair(pair,field['contract'],payloads)
                reference_payload,_=scientific_fields.npy_payload(payloads[row['reference']['name']],output,field['geometry'])
                require(hashlib.sha256(reference_payload).hexdigest()==member['target_sha256'],
                        'Retained reference payload differs from admitted target identity.')
                key=(checkpoint_sha,member['ordinal'],field['id']);arrays[key]={'pair':pair,'prediction':payloads[row['predicted']['name']],'reference':payloads[row['reference']['name']],
                                                                               'gauge_policy':field['gauge_policy']}
                field_records.append({'checkpoint_sha256':checkpoint_sha,'member_ordinal':member['ordinal'],'field_id':field['id'],'stage':output['stage'],'shape_zyx':output['shape_zyx'],'units':output['units']})
    return {'state':'verified','validation':'structural_and_identity_closure; numerical_acceptance_is_separate',
            'manifest':manifest,'checkpoint_index':index,'probe':static['probe'],'metric_definitions':policy['metric_definitions'],
            'observations':observations,'model_definition':policy['model_specification'],'fields':field_records,
            'metric_definition_hashes':{item['id']:digest(item) for item in policy['metric_definitions']},
            'checkpoints':[item['descriptor'] for item in checkpoints.values()], '_arrays':arrays}


@boundary
def query(verified, selectors=None):
    """Pure bounded projections; no filesystem, runtime, checkpoint load or inference."""
    selectors={} if selectors is None else checked(selectors)
    require(type(selectors) is dict and not set(selectors)-{'checkpoint_sha256','member_ordinal','field_id','axis','index','split'},'Unknown field selector.')
    require(selectors.get('split','validation')=='validation','Test field access is unsupported at every accessor.','unsupported')
    public=copy.deepcopy({key:value for key,value in verified.items() if not key.startswith('_')})
    if not selectors or set(selectors)<= {'split'}:return public
    selected=selectors.get('checkpoint_sha256');sha(selected)
    checkpoint=next((item for entry,item in zip(verified['checkpoint_index']['entries'],verified['checkpoints'],strict=True) if entry['checkpoint']['sha256']==selected),None)
    require(checkpoint is not None,'Checkpoint does not belong to this evidence.','stale')
    public['checkpoint']=copy.deepcopy(checkpoint)
    if set(selectors)<= {'checkpoint_sha256','split'}:return public
    require(set(selectors)-{'split'}=={'checkpoint_sha256','member_ordinal','field_id','axis','index'},'A field query requires the complete exact selector.')
    ordinal=natural(selectors['member_ordinal'],'Probe member ordinal');field_id=selectors['field_id'];text(field_id,'Field ID',64)
    item=verified['_arrays'].get((selected,ordinal,field_id));require(item is not None,'Field/member does not belong to this checkpoint.','stale')
    axis=selectors['axis'];require(axis in ('x','y','z'),'Unknown orthogonal axis.')
    import scientific_fields
    pair=item['pair'];grid=pair['geometry'];field={'dtype':pair['dtype'],'centering':pair['centering']}
    predicted,shape=scientific_fields.npy_payload(item['prediction'],field,grid)
    reference_values,_=scientific_fields.npy_payload(item['reference'],field,grid)
    xyz=list(reversed(shape));fixed='xyz'.index(axis);index=natural(selectors['index'],'Slice index',0,xyz[fixed]-1)
    row_axis,column_axis={'z':('y','x'),'y':('z','x'),'x':('z','y')}[axis];ri='xyz'.index(row_axis);ci='xyz'.index(column_axis)
    coordinates=[0,0,0];coordinates[fixed]=index;prediction=[];reference=[]
    for row in range(xyz[ri]):
        coordinates[ri]=row;predicted_row=[];reference_row=[]
        for column in range(xyz[ci]):
            coordinates[ci]=column;x,y,z=coordinates;offset=(x+xyz[0]*(y+xyz[1]*z))*8
            predicted_row.append(struct.unpack_from('<d',predicted,offset)[0]);reference_row.append(struct.unpack_from('<d',reference_values,offset)[0])
        prediction.append(predicted_row);reference.append(reference_row)
    sample=[.5,.5,.5];sample[fixed]+=index
    physical=[grid['origin_xyz'][i]+math.fsum(grid['orientation'][i][j]*grid['spacing_xyz'][j]*sample[j] for j in range(3)) for i in range(3)]
    step=lambda component:[grid['orientation'][i][component]*grid['spacing_xyz'][component] for i in range(3)]
    public['field']={'checkpoint_sha256':selected,'member_ordinal':ordinal,'field_id':field_id,'axis':axis,'index':index,
                     'shape_zyx':shape,'grid':grid,'stage':pair['stage'],'units':pair['units'],'dtype':pair['dtype'],'centering':pair['centering'],
                     'gauge_policy_sha256':pair['gauge_policy_sha256'],'gauge_policy':copy.deepcopy(item['gauge_policy']),'time_units':'not_applicable',
                     'prediction':prediction,'reference':reference,'row_axis':row_axis,'column_axis':column_axis,
                     'physical_origin':physical,'physical_row_step':step(ri),'physical_column_step':step(ci)}
    require(len(canonical(public))<=2*1024**2,'Field projection exceeds its transport bound.')
    return public
