"""Task-owned automatic classifier capture and inert, bounded evidence verification.

Runs owns publication and byte custody. This module never queues work or loads a
checkpoint during a query. The isolated adapter alone reconstructs fitted state.
"""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import time

from image_training import TrainingError, _json, _write_json, transform_for_parameters, validate_model_parameters

FORMAT = 'model_evidence_v1'
MAX_SHARD_BYTES = 8 * 1024**2
MAX_MANIFEST_BYTES = 1024**2
BASE_PAYLOADS = {'metrics.json', 'test-metrics.json', 'predictions-validation.json',
                 'predictions-test.json', 'checkpoint.pt'}
COMMON_PAYLOADS = {'model-evidence.json', 'model-definition.json', 'profile.json', 'probe.json',
                   'metric-definitions.json', 'checkpoints.json', 'observations.json',
                   'fitted-transform.json', 'output-policy.json', 'validation-logits.json'}
OUTPUT_POLICY = {'kind': 'class_probabilities', 'class_order': 'frozen_vocabulary'}
EMPTY_FITTED_TRANSFORM = {'format': 'fitted_transform_v1', 'fit_scope': 'none', 'statistics': []}
TASK = {'format': 'classifier_task_v1', 'id': 'image_classification_v1', 'semantic_version': 1,
        'input': 'rgb_image', 'target': 'frozen_class_index', 'output': 'class_probabilities',
        'clock': 'epoch', 'clock_convention': 'post_update_end_epoch'}


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_binary(path, maximum=64*1024**2):
    if path.is_symlink():raise ValueError('Evidence symlink is invalid.')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as handle:
        before=os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>maximum:
            raise ValueError('Evidence requires a bounded single-link regular file.')
        raw=handle.read(maximum+1);after=os.fstat(handle.fileno())
    identity=lambda value:(value.st_dev,value.st_ino,value.st_mode,value.st_nlink,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
    if identity(before)!=identity(after) or len(raw)>maximum:raise ValueError('Evidence changed while reading.')
    return raw


def blob(path):
    raw = read_binary(path)
    return {'name': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'media_type': 'application/json' if path.suffix == '.json' else 'application/octet-stream'}


def fitted_transform_sha256():
    return hashlib.sha256(canonical(EMPTY_FITTED_TRANSFORM)+b'\n').hexdigest()


def task_ref(catalog_id):
    return {'kind': 'task', 'catalog_id': catalog_id, 'id': TASK['id'], 'revision': 1, 'sha256': digest(TASK)}


def model_definition(parameters):
    parameters = validate_model_parameters(parameters)
    return {'format': 'tinycnn_definition_v2',
            'specification': {'template': 'tinycnn_v2', **{key: parameters[key] for key in ('widths', 'input_size', 'head')}},
            'preprocessing_policy': transform_for_parameters(parameters), 'output_policy': OUTPUT_POLICY,
            'parameters': parameters}


def profile(catalog_id, model_sha256, parameters, validation_count):
    definition = {'name': 'tinycnn_epoch_full_validation_v1', 'version': 1}
    return {'format': 'resolved_profile_v1',
            'definition': {'kind': 'profile', 'catalog_id': catalog_id, 'id': definition['name'], 'revision': 1, 'sha256': digest(definition)},
            'task_sha256': digest(TASK), 'trainer_sha256': digest({'name': 'tinycnn_cpu', 'version': 2}),
            'model_sha256': model_sha256,
            'probe_selection': {'role': 'validation', 'algorithm': 'sha256_rank_v1', 'namespace': 'tinycnn-validation-v1', 'seed': 0, 'count': validation_count},
            'capture': {'clock': 'epoch', 'interval': 1, 'retain_selected': True, 'max_snapshots': parameters['epochs']},
            'required_capabilities': ['checkpoints', 'fixed_validation_predictions', 'scalar_history'],
            'optional_capabilities': [],
            'limits': {'manifest_bytes': MAX_MANIFEST_BYTES, 'shard_bytes': MAX_SHARD_BYTES, 'total_output_bytes': 64 * 1024**2}}


def payload_names(epochs):
    return BASE_PAYLOADS | COMMON_PAYLOADS | {f'{prefix}-epoch-{epoch:04d}.{suffix}'
        for epoch in range(1, epochs + 1) for prefix, suffix in
        (('weights', 'pt'), ('checkpoint', 'json'), ('probes', 'json'))}


def frozen_reference(row):
    return {key: row[key] for key in ('id', 'revision', 'source_revision', 'source_sha256', 'asset_sha256', 'exported_pixel_sha256')}


def probe_manifest(manifest, data_sha, resolved):
    selection = resolved['probe_selection']
    rows = [row for row in manifest['records'] if row['split'] == 'validation']
    rows.sort(key=lambda row: (digest([selection['namespace'], data_sha, frozen_reference(row), selection['seed']]), canonical(frozen_reference(row))))
    return {'format': 'probe_v1', 'task_sha256': digest(TASK), 'data_sha256': data_sha,
            'split': 'validation', 'selection_policy_sha256': digest(selection),
            'members': [{'ordinal': i, 'frozen_reference': frozen_reference(row),
                         'input_sha256': row['asset_sha256'], 'target_sha256': digest(row['class_index'])}
                        for i, row in enumerate(rows[:selection['count']])]}



def stable_cross_entropy(logits, truth_index):
    """Float64 logsumexp oracle over retained raw float32 logits.

    Rounded softmax probabilities may be exactly zero for a valid finite logit.
    They cannot reconstruct cross entropy, so loss never clamps probabilities.
    """
    if (type(logits) is not list or not logits or type(truth_index) is not int
            or not 0 <= truth_index < len(logits)
            or any(type(value) not in (int,float) or not math.isfinite(value) for value in logits)):
        raise ValueError('Invalid validation logits or target.')
    maximum=max(logits)
    exponentials=[math.exp(value-maximum) for value in logits]
    denominator=math.fsum(exponentials)
    loss=(maximum-logits[truth_index])+math.log(denominator)
    if not math.isfinite(loss):raise ValueError('Nonfinite validation cross entropy.')
    return loss,[value/denominator for value in exponentials]

def capture_epoch(output, checkpoint, validation, rows, manifest, torch, context, clocks):
    """Write real post-update state and predictions from that state, never stdout."""
    epoch = checkpoint['epoch']; suffix = f'epoch-{epoch:04d}'
    weights = output / f'weights-{suffix}.pt'
    torch.save(checkpoint, weights)
    descriptor = {'format': 'checkpoint_state_v1', 'run_id': checkpoint['source_identity']['run_id'],
                  'model_sha256': context['model_sha256'], 'weights': blob(weights),
                  'fitted_transform_sha256': fitted_transform_sha256(), 'clocks': clocks}
    # Descriptor identity is canonical bytes including its newline, as every Blob.
    descriptor_path = output / f'checkpoint-{suffix}.json'; _write_json(descriptor_path, descriptor)
    descriptor_blob = blob(descriptor_path)
    selected_probe = probe_manifest(manifest, checkpoint['source_identity']['release_sha256'], context['profile'])
    probe_path = output / 'probe.json'
    if not probe_path.exists(): _write_json(probe_path, selected_probe)
    probe_blob = blob(probe_path)
    by_id = {row['id']: row for row in rows}
    prediction_rows = []
    for member in selected_probe['members']:
        row = by_id[member['frozen_reference']['id']]
        prediction_rows.append({'ordinal': member['ordinal'], 'truth_index': row['truth_index'],
                                'predicted_index': row['predicted_index'], 'probabilities': row['probabilities']})
    logit_path=output/'validation-logits.json'
    logit_document=(read_document(output,'validation-logits.json') if logit_path.exists() else
        {'format':'classifier_validation_logits_v1','run_id':descriptor['run_id'],
         'probe_sha256':probe_blob['sha256'],'entries':[]})
    logit_document['entries'].append({'checkpoint_sha256':descriptor_blob['sha256'],'clocks':clocks,
        'rows':[{'ordinal':member['ordinal'],'logits':by_id[member['frozen_reference']['id']]['logits']}
                for member in selected_probe['members']]})
    temporary=output/'.validation-logits.tmp'
    _write_json(temporary,logit_document);os.replace(temporary,logit_path)
    _write_json(output / f'probes-{suffix}.json', {'run_id': descriptor['run_id'],
        'checkpoint_sha256': descriptor_blob['sha256'], 'probe_sha256': probe_blob['sha256'], 'rows': prediction_rows})
    return {'checkpoint': descriptor_blob, 'model_sha256': descriptor['model_sha256'],
            'fitted_transform_sha256': descriptor['fitted_transform_sha256'], 'clocks': clocks,
            'selected': False, 'state': 'retained'}


def metric_definitions(context, manifest):
    population=digest(sorted([frozen_reference(row) for row in manifest['records'] if row['split']=='validation'],key=canonical))
    return [{'id': key, 'semantic_version': 1, 'split': 'validation', 'units': 'dimensionless',
                    'direction': direction, 'reduction': reduction, 'population_sha256': population,
                    'domain': {'minimum': 0, 'maximum': maximum}, 'undefined_rule': 'not_applicable',
                    'evaluator_sha256': context['adapter_sha256'],
                    'preprocessing_sha256':digest(context['model_definition']['preprocessing_policy']),
                    'class_order_sha256':digest(manifest['class_vocabulary'])}
                   for key, direction, reduction, maximum in (
                       ('loss', 'minimize', 'mean_cross_entropy', 1e12),
                       ('accuracy', 'maximize', 'diagonal_over_population', 1),
                       ('macro_f1', 'maximize', 'macro_over_frozen_vocabulary_zero_division_0', 1))]


def finish_capture(output, envelope, checkpoints, best_epoch, context):
    for entry in checkpoints: entry['selected'] = entry['clocks']['epoch'] == best_epoch
    run_id = envelope['source_identity']['run_id']
    _write_json(output / 'checkpoints.json', {'format': 'checkpoint_index_v1', 'run_id': run_id, 'entries': checkpoints})
    _write_json(output / 'model-definition.json', context['model_definition'])
    _write_json(output / 'profile.json', context['profile'])
    _write_json(output / 'fitted-transform.json', EMPTY_FITTED_TRANSFORM)
    _write_json(output / 'output-policy.json', OUTPUT_POLICY)
    probe_sha = blob(output / 'probe.json')['sha256']
    population = digest(sorted([row['frozen_reference'] for row in _json((output/'probe.json').read_bytes(), 'Probe')['members']], key=canonical))
    definitions=context['metric_definitions']
    _write_json(output / 'metric-definitions.json', definitions)
    history = _json((output / 'metrics.json').read_bytes(), 'Metrics')['history']
    observations = []
    for entry, step in zip(checkpoints, history, strict=True):
        for definition in definitions:
            observations.append({'run_id': run_id, 'checkpoint_sha256': entry['checkpoint']['sha256'],
                'probe_sha256': probe_sha, 'metric_id': definition['id'], 'split': 'validation',
                'clocks': entry['clocks'], 'state': 'observed', 'value': step['validation'][definition['id']],
                'sample_count': step['validation']['examples']})
    _write_json(output / 'observations.json', observations)
    _write_json(output / 'model-evidence.json', {'format': FORMAT, 'schema_version': 1,
        'producer': {'catalog_id': envelope['source_identity']['dataset_id'], 'run_id': run_id,
                     'material_sha256': context['material_sha256'], 'adapter_sha256': context['adapter_sha256']},
        'task': task_ref(envelope['source_identity']['dataset_id']), 'model_sha256': context['model_sha256'],
        'data_sha256': envelope['source_identity']['release_sha256'], 'profile_sha256': digest(context['profile']),
        'probe': blob(output/'probe.json'), 'metric_definitions': blob(output/'metric-definitions.json'),
        'checkpoints': blob(output/'checkpoints.json'), 'observations': [blob(output/'observations.json'),blob(output/'validation-logits.json'), *[blob(output/f'probes-epoch-{entry["clocks"]["epoch"]:04d}.json') for entry in checkpoints]],
        'field_index': None, 'coverage': {'required': context['profile']['required_capabilities'], 'optional': [], 'omitted': []},
        'inference': {'mode': 'eval_no_grad', 'fitted_transforms': [blob(output/'fitted-transform.json')],
                      'output_policy_sha256': digest(OUTPUT_POLICY)}})


def read_document(directory, name, maximum=MAX_SHARD_BYTES):
    return _json(read_binary(directory/name,maximum),name)


def verify(directory, run, metrics):
    """Validate task semantics before publication and again on every evidence read."""
    directory = Path(directory)
    manifest = read_document(directory, 'model-evidence.json', MAX_MANIFEST_BYTES)
    keys = {'format','schema_version','producer','task','model_sha256','data_sha256','profile_sha256','probe',
            'metric_definitions','checkpoints','observations','field_index','coverage','inference'}
    if set(manifest) != keys or manifest['format'] != FORMAT or manifest['schema_version'] != 1:
        raise ValueError('Invalid model evidence envelope.')
    context = run['evidence_context']
    producer = {'catalog_id':run['dataset_id'],'run_id':run['id'],'material_sha256':context['material_sha256'],
                'adapter_sha256':context['adapter_sha256']}
    if (manifest['producer'] != producer or manifest['task'] != task_ref(run['dataset_id'])
            or manifest['data_sha256'] != run['release_sha256'] or manifest['model_sha256'] != context['model_sha256']
            or manifest['profile_sha256'] != digest(context['profile']) or manifest['field_index'] is not None
            or manifest['coverage'] != {'required':context['profile']['required_capabilities'],'optional':[],'omitted':[]}
            or read_document(directory,'model-definition.json') != context['model_definition']
            or read_document(directory,'profile.json') != context['profile']
            or read_document(directory,'fitted-transform.json') != EMPTY_FITTED_TRANSFORM
            or read_document(directory,'output-policy.json') != OUTPUT_POLICY):
        raise ValueError('Evidence differs from admitted model/profile/task/source.')
    def checked_blob(item):
        if type(item) is not dict or set(item) != {'name','sha256','bytes','media_type'} or item['name'] not in payload_names(run['parameters']['epochs']):
            raise ValueError('Invalid evidence blob reference.')
        if blob(directory/item['name']) != item: raise ValueError('Evidence blob checksum differs.')
        return read_document(directory,item['name']) if item['name'].endswith('.json') else None
    probe = checked_blob(manifest['probe'])
    expected_probe = probe_manifest({'records':run['source_records']}, run['release_sha256'], context['profile'])
    if probe != expected_probe: raise ValueError('Fixed validation membership differs.')
    index = checked_blob(manifest['checkpoints'])
    if set(index) != {'format','run_id','entries'} or index['format'] != 'checkpoint_index_v1' or index['run_id'] != run['id']:
        raise ValueError('Invalid checkpoint index.')
    if len(index['entries']) != run['parameters']['epochs']: raise ValueError('Missing required epoch checkpoint.')
    logit_document=read_document(directory,'validation-logits.json')
    if (set(logit_document)!={'format','run_id','probe_sha256','entries'}
            or logit_document['format']!='classifier_validation_logits_v1' or logit_document['run_id']!=run['id']
            or logit_document['probe_sha256']!=manifest['probe']['sha256']
            or type(logit_document['entries']) is not list or len(logit_document['entries'])!=len(index['entries'])):
        raise ValueError('Full validation logits binding differs.')
    selected = []; previous_update = 0; previous_wall = 0; descriptors = []; predictions = []
    by_id = {row['id']:row for row in run['source_records']}
    for epoch, entry in enumerate(index['entries'], 1):
        if set(entry) != {'checkpoint','model_sha256','fitted_transform_sha256','clocks','selected','state'} or entry['state'] != 'retained' or type(entry['selected']) is not bool:
            raise ValueError('Invalid checkpoint entry.')
        descriptor = checked_blob(entry['checkpoint']); clocks = entry['clocks']
        if (set(clocks) != {'optimizer_update','epoch','fit_pass','physical_time','wall_elapsed_ms'}
                or clocks['epoch'] != epoch or type(clocks['epoch']) is not int
                or type(clocks['optimizer_update']) is not int or clocks['optimizer_update'] <= previous_update
                or clocks['optimizer_update'] != epoch * math.ceil(sum(row['split']=='train' for row in run['source_records']) / run['parameters']['batch_size'])
                or type(clocks['wall_elapsed_ms']) is not int or clocks['wall_elapsed_ms'] < previous_wall
                or clocks['fit_pass'] is not None or clocks['physical_time'] is not None):
            raise ValueError('Checkpoint clocks differ from actual admitted progress.')
        expected = {'format':'checkpoint_state_v1','run_id':run['id'],'model_sha256':context['model_sha256'],
                    'weights':blob(directory/f'weights-epoch-{epoch:04d}.pt'),
                    'fitted_transform_sha256':fitted_transform_sha256(),'clocks':clocks}
        if descriptor != expected or any(entry[key] != descriptor[key] for key in ('model_sha256','fitted_transform_sha256','clocks')):
            raise ValueError('Checkpoint descriptor binding differs.')
        checked_blob(descriptor['weights'])
        prediction = read_document(directory,f'probes-epoch-{epoch:04d}.json')
        if (set(prediction) != {'run_id','checkpoint_sha256','probe_sha256','rows'} or prediction['run_id'] != run['id']
                or prediction['checkpoint_sha256'] != entry['checkpoint']['sha256'] or prediction['probe_sha256'] != manifest['probe']['sha256']
                or len(prediction['rows']) != len(probe['members'])):
            raise ValueError('Checkpoint prediction binding differs.')
        for member,row in zip(probe['members'],prediction['rows'],strict=True):
            if set(row) != {'ordinal','truth_index','predicted_index','probabilities'}: raise ValueError('Invalid probe row.')
            scores = row['probabilities']; count = len(metrics['class_vocabulary'])
            if (row['ordinal'] != member['ordinal'] or type(row['ordinal']) is not int
                    or row['truth_index'] != by_id[member['frozen_reference']['id']]['class_index'] or type(row['truth_index']) is not int
                    or type(scores) is not list or len(scores) != count
                    or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in scores)
                    or abs(sum(scores)-1)>1e-4 or type(row['predicted_index']) is not int
                    or row['predicted_index'] != max(range(count),key=lambda i:scores[i])):
                raise ValueError('Invalid fixed probe prediction.')
        # The profile probes the full validation population. Independently
        # re-tally every epoch instead of trusting scalar writer consistency.
        matrix=[[0]*len(metrics['class_vocabulary']) for _ in metrics['class_vocabulary']]
        logit_entry=logit_document['entries'][epoch-1]
        if (set(logit_entry)!={'checkpoint_sha256','clocks','rows'} or logit_entry['checkpoint_sha256']!=entry['checkpoint']['sha256']
                or logit_entry['clocks']!=clocks or type(logit_entry['rows']) is not list
                or len(logit_entry['rows'])!=len(prediction['rows'])):
            raise ValueError('Validation logits checkpoint binding differs.')
        loss=0.0
        for row,logit_row in zip(prediction['rows'],logit_entry['rows'],strict=True):
            if (set(logit_row)!={'ordinal','logits'} or logit_row['ordinal']!=row['ordinal']
                    or type(logit_row['ordinal']) is not int or type(logit_row['logits']) is not list
                    or len(logit_row['logits'])!=len(metrics['class_vocabulary'])):
                raise ValueError('Validation logits membership differs.')
            cross_entropy,probabilities=stable_cross_entropy(logit_row['logits'],row['truth_index'])
            if not all(math.isclose(actual,expected,abs_tol=1e-6,rel_tol=1e-5)
                       for actual,expected in zip(probabilities,row['probabilities'],strict=True)):
                raise ValueError('Raw logits disagree with retained probabilities.')
            matrix[row['truth_index']][row['predicted_index']]+=1
            loss+=cross_entropy
        count=len(prediction['rows']); accuracy=sum(matrix[i][i] for i in range(len(matrix)))/count
        f1=[]
        for i in range(len(matrix)):
            denominator=sum(matrix[i])+sum(line[i] for line in matrix)
            f1.append(2*matrix[i][i]/denominator if denominator else 0.0)
        actual=metrics['history'][epoch-1]['validation']
        if (actual['confusion_matrix']!=matrix or actual['examples']!=count
                or abs(actual['accuracy']-accuracy)>1e-7 or abs(actual['macro_f1']-sum(f1)/len(f1))>1e-7
                or not math.isclose(actual['loss'],loss/count,abs_tol=1e-6,rel_tol=1e-5)):
            raise ValueError('Full validation probe predictions disagree with scalar metrics.')
        if entry['selected']: selected.append(epoch)
        previous_update=clocks['optimizer_update'];previous_wall=clocks['wall_elapsed_ms']
        descriptors.append(descriptor);predictions.append(prediction)
    best = min(range(len(metrics['history'])),key=lambda i:metrics['history'][i]['validation']['loss'])+1
    if selected != [metrics['best_epoch']] or metrics['best_epoch'] != best:
        raise ValueError('Selected checkpoint differs from validation selection.')
    if read_binary(directory/'checkpoint.pt') != read_binary(directory/f'weights-epoch-{best:04d}.pt'):
        # torch serialization has filename metadata: trainer copies exact selected bytes below.
        raise ValueError('Selected weight bytes differ.')
    selected_rows=read_document(directory,'predictions-validation.json')['rows']
    by_selected_id={row['id']:row for row in selected_rows}
    for member,row in zip(probe['members'],predictions[best-1]['rows'],strict=True):
        original=by_selected_id[member['frozen_reference']['id']]
        if any(original[key]!=row[key] for key in ('truth_index','predicted_index','probabilities')):
            raise ValueError('Selected full predictions differ from retained checkpoint probes.')
    definitions = checked_blob(manifest['metric_definitions'])
    observations=[]
    expected_observation_blobs=[blob(directory/'observations.json'),blob(directory/'validation-logits.json'), *[blob(directory/f'probes-epoch-{epoch:04d}.json') for epoch in range(1,run['parameters']['epochs']+1)]]
    if manifest['observations']!=expected_observation_blobs:raise ValueError('Observation inventory differs.')
    for item in manifest['observations']:
        value=checked_blob(item)
        if item['name']=='observations.json':observations.extend(value)
    if len(definitions)!=3 or len(observations)!=len(index['entries'])*3:
        raise ValueError('Metric observation coverage differs.')
    expected_population=digest(sorted([item['frozen_reference'] for item in probe['members']], key=canonical))
    if definitions!=metric_definitions(context,{'records':run['source_records'],'class_vocabulary':metrics['class_vocabulary']}):
        raise ValueError('Metric definitions differ from selected evaluator semantics.')
    for definition in definitions:
        if definition['population_sha256']!=expected_population or definition['evaluator_sha256']!=context['adapter_sha256']:
            raise ValueError('Metric population or evaluator differs.')
    for entry,step in zip(index['entries'],metrics['history'],strict=True):
        for metric in ('loss','accuracy','macro_f1'):
            match=[value for value in observations if value['checkpoint_sha256']==entry['checkpoint']['sha256'] and value['metric_id']==metric]
            expected={'run_id':run['id'],'checkpoint_sha256':entry['checkpoint']['sha256'],
                'probe_sha256':manifest['probe']['sha256'],'metric_id':metric,'split':'validation','clocks':entry['clocks'],
                'state':'observed','value':step['validation'][metric],'sample_count':step['validation']['examples']}
            if match != [expected]:raise ValueError('Scalar observation differs from actual validation.')
    expected_inference={'mode':'eval_no_grad','fitted_transforms':[blob(directory/'fitted-transform.json')],
                        'output_policy_sha256':digest(OUTPUT_POLICY)}
    if manifest['inference'] != expected_inference:raise ValueError('Inference transform differs.')
    return {'state':'verified','manifest':manifest,'checkpoint_index':index,'probe':probe,
            'metric_definitions':definitions,'observations':observations,'model_definition':context['model_definition']},descriptors,predictions


def replay_checkpoints(job_path):
    """CPU worker verification: reconstruct every retained state from exact release."""
    from image_training import _read_release, build_model, guard_parent
    import os
    job = read_document(Path(job_path).parent,Path(job_path).name)
    guard_parent(job['parent_pid'])
    import torch
    from torchvision import transforms
    from PIL import Image
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    manifest,assets = _read_release(job['release_path'],job['release_sha256'])
    directory=Path(job['output_dir']);params=validate_model_parameters(job['parameters'])
    transform=transforms.Compose([transforms.Resize(tuple(transform_for_parameters(params)['size'])),transforms.ToTensor()])
    probe=read_document(directory,'probe.json');by_id={row['id']:row for row in manifest['records']}
    x=torch.stack([transform(Image.open(io.BytesIO(assets[by_id[item['frozen_reference']['id']]['asset']])).convert('RGB')) for item in probe['members']])
    model=build_model(torch,params['widths'],len(manifest['class_vocabulary']))
    logit_history=read_document(directory,'validation-logits.json')['entries']
    for epoch in range(1,params['epochs']+1):
        checkpoint=torch.load(directory/f'weights-epoch-{epoch:04d}.pt',map_location='cpu',weights_only=True)
        if checkpoint['epoch']!=epoch or checkpoint['parameters']!=params:raise ValueError('Replayed checkpoint metadata differs.')
        model.load_state_dict(checkpoint['state_dict'],strict=True);model.eval()
        with torch.no_grad():
            logits=model(x);values=logits.softmax(1)
        expected_logits=torch.tensor([row['logits'] for row in logit_history[epoch-1]['rows']])
        if not torch.allclose(logits,expected_logits,rtol=1e-5,atol=1e-6):
            raise ValueError('Retained weights do not reproduce full validation logits.')
        expected=read_document(directory,f'probes-epoch-{epoch:04d}.json')['rows']
        if not torch.allclose(values,torch.tensor([row['probabilities'] for row in expected]),rtol=1e-5,atol=1e-6):
            raise ValueError('Retained weights do not reproduce fixed validation probes.')
