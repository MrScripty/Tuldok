"""D2 evidence capture for the explicitly selected text/audio one-fit adapters.

These functions own the shared representation, not Runs publication or grants.
The selected task supplies canonical inputs and verifies frozen reconstruction.
Legacy schema-1 jobs retain their original closed output inventory.
"""
import hashlib
import json
import math
from pathlib import Path
import re

from image_training import TrainingError, _invalid, _write_json
from model_evidence import read_binary, read_document
from workbench import encode

HASH = re.compile(r'^[a-f0-9]{64}$')
ID = re.compile(r'^[a-f0-9]{32}$')
SAFE = 2**53 - 1
CAPTURE_NAMES = frozenset(('model-evidence.json', 'probe.json', 'checkpoints.json',
                          'checkpoint-fit-0001.json', 'probes-fit-0001.json',
                          'observations.json', 'metric-definitions.json',
                          'fitted-transform.json', 'model-definition.json', 'probe-inputs.json',
                          'profile.json', 'output-policy.json'))
OUTPUT_POLICY = {'kind': 'class_probabilities', 'class_order': 'frozen_vocabulary'}


class Contract:
    """Bind shared one-fit representation to one existing task owner."""
    OUTPUT_POLICY = OUTPUT_POLICY

    def __init__(self, adapter):
        self.adapter = adapter
        self.task = 'text_classification' if adapter.ADAPTER['name'] == 'tfidf_multinomial_nb_cpu' else 'audio_classification'
        self.template = 'tfidf_multinomial_nb_v2' if self.task == 'text_classification' else 'audio_features_logistic_v2'
        self.TASK = dict(format='one_fit_task_v1', id=self.task, semantic_version=2,
                         input='canonical_text' if self.task == 'text_classification' else 'source_channel_interval_features',
                         target='frozen_class_index', output='class_probabilities', clock='fit_pass', clock_convention='fit_completed')

    def task_ref(self, catalog_id):
        return dict(kind='task', catalog_id=catalog_id, id=self.task, revision=2, sha256=digest(self.TASK))

    def model_definition(self, parameters):
        parameters = self.adapter.validate_parameters(parameters)
        return dict(format='one_fit_model_definition_v1', specification=dict(template=self.template, **parameters),
                    preprocessing_policy=json.loads(encode(self.adapter.TRANSFORM)), output_policy=dict(OUTPUT_POLICY), parameters=parameters)

    def profile(self, catalog_id, model_sha256, parameters, validation_count):
        self.adapter.validate_parameters(parameters)
        definition = dict(name=self.task + '_one_fit_full_validation_v1', version=1)
        return dict(format='resolved_profile_v1', definition=dict(kind='profile', catalog_id=catalog_id,
                    id=definition['name'], revision=1, sha256=digest(definition)),
                    task_sha256=digest(self.TASK), trainer_sha256=digest(dict(self.adapter.ADAPTER, version=2)), model_sha256=model_sha256,
                    probe_selection=dict(role='validation', algorithm='frozen_order_all_v1', namespace=self.task + '_validation_v1', seed=0, count=validation_count),
                    capture=dict(clock='fit_pass', interval=1, retain_selected=True, max_snapshots=1),
                    required_capabilities=['checkpoints', 'fixed_validation_predictions', 'single_fit_metrics'], optional_capabilities=[],
                    limits=dict(manifest_bytes=1024**2, shard_bytes=8*1024**2, total_output_bytes=64*1024**2))

    def metric_definitions(self, context, manifest):
        references = [_frozen_reference(row, self.adapter.REFERENCE_KEYS) for row in manifest['records'] if row['split'] == 'validation']
        population = digest(sorted(references, key=encode))
        return [dict(id=key, semantic_version=1, split='validation', units='dimensionless', direction=direction,
                     reduction=reduction, population_sha256=population, domain=dict(minimum=0, maximum=maximum),
                     undefined_rule='not_applicable', evaluator_sha256=context['adapter_sha256'],
                     preprocessing_sha256=digest(self.adapter.TRANSFORM), class_order_sha256=digest(manifest['class_vocabulary']))
                for key, direction, reduction, maximum in (('loss', 'minimize', 'mean_cross_entropy', 1e12),
                    ('accuracy', 'maximize', 'diagonal_over_population', 1),
                    ('macro_f1', 'maximize', 'macro_over_frozen_vocabulary_zero_division_0', 1))]


def _frozen_reference(row, reference_keys):
    return {key: row['content_hash'] if key == 'content_sha256' else row[key] for key in reference_keys}


def contract(adapter):
    if type(adapter) is dict:
        if adapter['name'] == 'tfidf_multinomial_nb_cpu':
            import text_training
            adapter = text_training
        else:
            import audio_training
            adapter = audio_training
    return Contract(adapter)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        _invalid(label + ' fields differ from the one-fit contract.')


def _same(value, expected):
    """JSON contract identity distinguishes booleans from integer coordinates."""
    try:
        return encode(value) == encode(expected)
    except (ValueError, TypeError, RecursionError):
        _invalid('One-fit evidence must contain bounded finite JSON values.')


def _hash(value):
    if type(value) is not str or not HASH.fullmatch(value):
        _invalid('One-fit material requires canonical SHA-256 identities.')


def validate_job_selection(job, adapter):
    """Called before fitting; no unsupported adapter silently falls back to v1."""
    _exact(job['adapter'], ('name', 'version'), 'Selected adapter')
    if job['adapter'] != dict(adapter, version=2) or type(job['adapter']['version']) is not int:
        raise TrainingError('unsupported', 'Select the exact version 2 one-fit adapter.')
    context = job['evidence']
    _exact(context, ('catalog_id', 'material_sha256', 'adapter_sha256', 'model_sha256', 'task', 'profile_sha256',
                     'selection_policy_sha256', 'output_policy_sha256'), 'Evidence context')
    if type(context['catalog_id']) is not str or not ID.fullmatch(context['catalog_id']):
        _invalid('One-fit catalog identity must be canonical.')
    for key in ('material_sha256', 'adapter_sha256', 'model_sha256', 'profile_sha256', 'selection_policy_sha256', 'output_policy_sha256'):
        _hash(context[key])
    task = context['task']
    _exact(task, ('kind', 'catalog_id', 'id', 'revision', 'sha256'), 'Task reference')
    expected = 'text_classification' if adapter['name'] == 'tfidf_multinomial_nb_cpu' else 'audio_classification'
    if (task['kind'] != 'task' or task['catalog_id'] != context['catalog_id'] or task['id'] != expected
            or type(task['revision']) is not int or task['revision'] != 2):
        _invalid('One-fit task reference differs from the selected adapter.')
    _hash(task['sha256'])
    return context


def fit_clocks(elapsed_seconds):
    if type(elapsed_seconds) not in (int, float) or not math.isfinite(elapsed_seconds) or elapsed_seconds < 0:
        _invalid('One-fit elapsed time must be a measured nonnegative duration.')
    milliseconds = int(elapsed_seconds * 1000)
    if milliseconds > SAFE:
        _invalid('One-fit elapsed time exceeds the safe integer bound.')
    return dict(optimizer_update=None, epoch=None, fit_pass=1, physical_time=None, wall_elapsed_ms=milliseconds)


def payload_names():
    return set(CAPTURE_NAMES) | {'model.json', 'metrics.json', 'test-metrics.json',
                                  'predictions-validation.json', 'predictions-test.json'}


def _ref(path):
    raw = read_binary(path, 8 * 1024**2)
    return dict(name=path.name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), media_type='application/json')


def _members(manifest, reference_keys):
    return [dict(ordinal=index, frozen_reference=_frozen_reference(row, reference_keys),
                 input_sha256=row['asset_sha256'], target_sha256=digest({'class_index': row['class_index']}))
            for index, row in enumerate(row for row in manifest['records'] if row['split'] == 'validation')]


def capture(directory, *, job, adapter, manifest, reference_keys, saved, inputs, validation, rows, clocks):
    """Write one retained fit checkpoint and fixed validation observations."""
    context = validate_job_selection(job, adapter)
    root = Path(directory)
    run = job['run_id']
    def write(name, body):
        _write_json(root / name, body)
        return _ref(root / name)
    task = context['task']
    owner = contract(adapter)
    definition = owner.model_definition(saved['parameters'])
    write('model-definition.json', definition)
    resolved = owner.profile(context['catalog_id'], context['model_sha256'], saved['parameters'], len(rows))
    if (context['task'] != owner.task_ref(context['catalog_id']) or context['profile_sha256'] != digest(resolved)
            or context['selection_policy_sha256'] != digest(resolved['probe_selection']) or context['output_policy_sha256'] != digest(OUTPUT_POLICY)):
        _invalid('One-fit resolved policies differ from admitted material.')
    write('profile.json', resolved)
    write('output-policy.json', OUTPUT_POLICY)
    state_keys = ('vocabulary', 'idf') if task['id'] == 'text_classification' else ('mean', 'scale')
    fitted = write('fitted-transform.json', dict(format='one_fit_transform_v1', transform=saved['transform'],
                   fit_scope='train', fit_members=[_frozen_reference(row, reference_keys)
                       for row in manifest['records'] if row['split'] == 'train'],
                   statistics={key: saved[key] for key in state_keys}))
    probe = write('probe.json', dict(format='probe_v1', task_sha256=task['sha256'], data_sha256=job['release_sha256'],
                  split='validation', selection_policy_sha256=context['selection_policy_sha256'], members=_members(manifest, reference_keys)))
    write('probe-inputs.json', dict(format='one_fit_probe_inputs_v1', probe_sha256=probe['sha256'], inputs=inputs))
    checkpoint_body = dict(format='checkpoint_state_v1', run_id=run, model_sha256=context['model_sha256'],
                           weights=_ref(root / 'model.json'), fitted_transform_sha256=fitted['sha256'], clocks=clocks)
    checkpoint = write('checkpoint-fit-0001.json', checkpoint_body)
    index = write('checkpoints.json', dict(format='checkpoint_index_v1', run_id=run, entries=[dict(checkpoint=checkpoint,
                       model_sha256=context['model_sha256'], fitted_transform_sha256=fitted['sha256'], clocks=clocks,
                       selected=True, state='retained')]))
    observations = write('observations.json', [dict(run_id=run, checkpoint_sha256=checkpoint['sha256'], probe_sha256=probe['sha256'],
                          metric_id=key, split='validation', clocks=clocks, state='observed', value=validation[key],
                          sample_count=validation['examples']) for key in ('loss', 'accuracy', 'macro_f1')])
    predictions = write('probes-fit-0001.json', dict(run_id=run, checkpoint_sha256=checkpoint['sha256'], probe_sha256=probe['sha256'],
                rows=[dict(ordinal=index, truth_index=row['truth_index'], predicted_index=row['predicted_index'], probabilities=row['probabilities'])
                      for index, row in enumerate(rows)]))
    definitions = write('metric-definitions.json', owner.metric_definitions(context, manifest))
    body = dict(format='model_evidence_v1', schema_version=1,
                producer=dict(catalog_id=context['catalog_id'], run_id=run, material_sha256=context['material_sha256'], adapter_sha256=context['adapter_sha256']),
                task=task, model_sha256=context['model_sha256'], data_sha256=job['release_sha256'], profile_sha256=context['profile_sha256'],
                probe=probe, metric_definitions=definitions, checkpoints=index, observations=[observations, predictions], field_index=None,
                coverage=dict(required=resolved['required_capabilities'], optional=[], omitted=[]),
                inference=dict(mode='eval_no_grad', fitted_transforms=[fitted], output_policy_sha256=context['output_policy_sha256']))
    write('model-evidence.json', body)
    return body


def verify_directory(directory, *, job, adapter, manifest, reference_keys, expected_inputs, reconstruct=True):
    """Task-owned checks after custody; accepts no source paths from evidence.

    `manifest` and `expected_inputs` come from the selected frozen task reader,
    never from producer declarations. Runs remains responsible for authority,
    exact output inventory/outer hashes and atomic publication.
    """
    context = validate_job_selection(job, adapter)
    root = Path(directory)
    def read(name):
        maximum = 1024**2 if name == 'model-evidence.json' else 8 * 1024**2
        return read_document(root, name, maximum)
    evidence = read('model-evidence.json')
    _exact(evidence, ('format', 'schema_version', 'producer', 'task', 'model_sha256', 'data_sha256', 'profile_sha256', 'probe',
                     'metric_definitions', 'checkpoints', 'observations', 'field_index', 'coverage', 'inference'), 'Evidence manifest')
    if (evidence['format'] != 'model_evidence_v1' or type(evidence['schema_version']) is not int or evidence['schema_version'] != 1
            or evidence['producer'] != dict(catalog_id=context['catalog_id'], run_id=job['run_id'], material_sha256=context['material_sha256'], adapter_sha256=context['adapter_sha256'])
            or evidence['task'] != context['task'] or evidence['model_sha256'] != context['model_sha256']
            or evidence['data_sha256'] != job['release_sha256'] or evidence['profile_sha256'] != context['profile_sha256']):
        _invalid('One-fit evidence material differs from the admitted job.')
    def reference(ref, name):
        if not _same(ref, _ref(root / name)):
            _invalid('One-fit evidence blob differs from retained bytes.')
        return read(name)
    index = reference(evidence['checkpoints'], 'checkpoints.json')
    _exact(index, ('format', 'run_id', 'entries'), 'Checkpoint index')
    if index['format'] != 'checkpoint_index_v1' or index['run_id'] != job['run_id'] or type(index['entries']) is not list or len(index['entries']) != 1:
        _invalid('One-fit evidence must retain exactly one actual fit checkpoint.')
    entry = index['entries'][0]
    _exact(entry, ('checkpoint', 'model_sha256', 'fitted_transform_sha256', 'clocks', 'selected', 'state'), 'Checkpoint entry')
    clocks = entry['clocks']
    _exact(clocks, ('optimizer_update', 'epoch', 'fit_pass', 'physical_time', 'wall_elapsed_ms'), 'Fit clocks')
    if (type(clocks['wall_elapsed_ms']) is not int or not 0 <= clocks['wall_elapsed_ms'] <= SAFE
            or clocks != dict(optimizer_update=None, epoch=None, fit_pass=1, physical_time=None, wall_elapsed_ms=clocks['wall_elapsed_ms'])
            or type(clocks['fit_pass']) is not int):
        _invalid('One-fit evidence cannot invent epoch, update or physical clocks.')
    checkpoint = reference(entry['checkpoint'], 'checkpoint-fit-0001.json')
    _exact(evidence['inference'], ('mode', 'fitted_transforms', 'output_policy_sha256'), 'Inference')
    if (evidence['inference']['mode'] != 'eval_no_grad' or evidence['inference']['output_policy_sha256'] != context['output_policy_sha256']
            or type(evidence['inference']['fitted_transforms']) is not list or len(evidence['inference']['fitted_transforms']) != 1):
        _invalid('One-fit inference policy differs from admitted material.')
    fitted = reference(evidence['inference']['fitted_transforms'][0], 'fitted-transform.json')
    if (type(entry['selected']) is not bool or entry != dict(checkpoint=entry['checkpoint'], model_sha256=context['model_sha256'], fitted_transform_sha256=digest_bytes(root / 'fitted-transform.json'),
                      clocks=clocks, selected=True, state='retained')
            or not _same(checkpoint, dict(format='checkpoint_state_v1', run_id=job['run_id'], model_sha256=context['model_sha256'],
                         weights=_ref(root / 'model.json'), fitted_transform_sha256=entry['fitted_transform_sha256'], clocks=clocks))):
        _invalid('One-fit descriptor/index binding differs.')
    saved = read('model.json')
    if saved.get('adapter') != job['adapter'] or saved.get('source_identity') != {key: job[key] for key in ('dataset_id', 'run_id', 'graph_sha256', 'release_id', 'release_sha256')}:
        _invalid('Frozen one-fit weights differ from the admitted source/adapter.')
    owner = contract(adapter)
    definition = owner.model_definition(saved['parameters'])
    if not _same(read('model-definition.json'), definition) or saved['parameters'] != job['parameters']:
        _invalid('Frozen one-fit model definition differs from admitted parameters.')
    resolved = owner.profile(context['catalog_id'], context['model_sha256'], saved['parameters'], sum(row['split'] == 'validation' for row in manifest['records']))
    if (context['task'] != owner.task_ref(context['catalog_id']) or not _same(read('profile.json'), resolved)
            or context['profile_sha256'] != digest(resolved) or context['selection_policy_sha256'] != digest(resolved['probe_selection'])
            or context['output_policy_sha256'] != digest(OUTPUT_POLICY) or read('output-policy.json') != OUTPUT_POLICY):
        _invalid('One-fit resolved profile or output policy differs.')
    expected_fit = [_frozen_reference(row, reference_keys) for row in manifest['records'] if row['split'] == 'train']
    state_keys = ('vocabulary', 'idf') if context['task']['id'] == 'text_classification' else ('mean', 'scale')
    if not _same(fitted, dict(format='one_fit_transform_v1', transform=saved['transform'], fit_scope='train', fit_members=expected_fit,
                       statistics={key: saved[key] for key in state_keys})):
        _invalid('Fitted transform does not name exactly the training population/state.')
    probe = reference(evidence['probe'], 'probe.json')
    if not _same(probe, dict(format='probe_v1', task_sha256=context['task']['sha256'], data_sha256=job['release_sha256'], split='validation',
                     selection_policy_sha256=context['selection_policy_sha256'], members=_members(manifest, reference_keys))):
        _invalid('Fixed probe membership differs from the frozen validation population.')
    inputs = read('probe-inputs.json')
    if not _same(inputs, dict(format='one_fit_probe_inputs_v1', probe_sha256=evidence['probe']['sha256'], inputs=expected_inputs)):
        _invalid('Probe inputs differ from the frozen task reader.')
    actual = read('probes-fit-0001.json')
    _exact(actual, ('run_id', 'checkpoint_sha256', 'probe_sha256', 'rows'), 'Classifier probes')
    members = [row for row in manifest['records'] if row['split'] == 'validation']
    if type(actual['rows']) is not list or len(actual['rows']) != len(members):
        _invalid('Fixed probe rows differ from complete validation membership.')
    if reconstruct and context['task']['id'] == 'text_classification':
        from text_training import predict_model
        probabilities = predict_model(saved, expected_inputs).tolist()
    elif reconstruct:
        from audio_training import predict_features
        probabilities = predict_features(saved, expected_inputs)
    else:
        probabilities = [row.get('probabilities') if type(row) is dict else None for row in actual['rows']]
    expected_rows = []
    for index, (source, scores) in enumerate(zip(members, probabilities, strict=True)):
        if (type(scores) is not list or len(scores) != len(saved['class_vocabulary'])
                or any(type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value) for value in scores)
                or abs(sum(scores) - 1) > 1e-4):
            _invalid('One-fit probe probabilities are invalid.')
        expected_rows.append(dict(ordinal=index, truth_index=source['class_index'], predicted_index=max(range(len(scores)), key=scores.__getitem__), probabilities=scores))
    if not _same(actual, dict(run_id=job['run_id'], checkpoint_sha256=entry['checkpoint']['sha256'], probe_sha256=evidence['probe']['sha256'], rows=expected_rows)):
        _invalid('Frozen checkpoint reconstruction differs from retained probes.')
    metrics = read('metrics.json')
    if metrics.get('clocks') != clocks or 'history' in metrics or 'best_epoch' in metrics:
        _invalid('One-fit metrics cannot publish an artificial training curve.')
    if not _same(evidence['observations'], [_ref(root / 'observations.json'), _ref(root / 'probes-fit-0001.json')]):
        _invalid('One-fit observations differ from retained bytes.')
    observations = read('observations.json')
    expected_observations = [dict(run_id=job['run_id'], checkpoint_sha256=entry['checkpoint']['sha256'], probe_sha256=evidence['probe']['sha256'],
                          metric_id=key, split='validation', clocks=clocks, state='observed', value=metrics['validation'][key],
                          sample_count=len(members)) for key in ('loss', 'accuracy', 'macro_f1')]
    if not _same(observations, expected_observations) or metrics['validation']['examples'] != len(members):
        _invalid('One-fit scalar observations differ from full validation metrics.')
    # Independent tally from reconstructed probabilities; producer aggregates
    # cannot impersonate a full validation observation.
    confusion = [[0] * len(saved['class_vocabulary']) for _ in saved['class_vocabulary']]
    losses = []
    for row in expected_rows:
        confusion[row['truth_index']][row['predicted_index']] += 1
        losses.append(-math.log(max(2.220446049250313e-16, min(1 - 2.220446049250313e-16, row['probabilities'][row['truth_index']]))))
    accuracy = sum(confusion[i][i] for i in range(len(confusion))) / len(members)
    f1 = sum((2 * confusion[i][i] / (sum(confusion[i]) + sum(row[i] for row in confusion)))
             if sum(confusion[i]) + sum(row[i] for row in confusion) else 0 for i in range(len(confusion))) / len(confusion)
    for key, expected in (('loss', sum(losses) / len(losses)), ('accuracy', accuracy), ('macro_f1', f1)):
        value = metrics['validation'][key]
        if type(value) not in (int, float) or not math.isfinite(value) or not math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-12):
            _invalid('One-fit validation metric differs from frozen predictions.')
    if metrics['validation']['confusion_matrix'] != confusion:
        _invalid('One-fit confusion matrix differs from frozen predictions.')
    definitions = reference(evidence['metric_definitions'], 'metric-definitions.json')
    expected_definitions = owner.metric_definitions(context, manifest)
    if not _same(definitions, expected_definitions):
        _invalid('One-fit metric semantics differ from the selected task.')
    if (evidence['field_index'] is not None or evidence['coverage'] != dict(required=resolved['required_capabilities'], optional=[], omitted=[])):
        _invalid('One-fit required evidence coverage differs.')
    return evidence


def digest_bytes(path):
    return hashlib.sha256(read_binary(path, 8 * 1024**2)).hexdigest()


def job_for_run(run, output_dir=None):
    """Project an admitted Run's owned context into the closed worker job."""
    context = run['evidence_context']
    owner = contract(run['adapter'])
    return dict(schema_version=2, dataset_id=run['dataset_id'], run_id=run['id'], graph_sha256=run['graph_sha256'],
                release_id=run['release_id'], release_sha256=run['release_sha256'], release_path=run['release_path'],
                output_dir=str(output_dir or run['id']), parameters=run['parameters'], parent_pid=1, adapter=run['adapter'],
                evidence=dict(catalog_id=run['dataset_id'], material_sha256=context['material_sha256'], adapter_sha256=context['adapter_sha256'],
                    model_sha256=context['model_sha256'], task=owner.task_ref(run['dataset_id']), profile_sha256=digest(context['profile']),
                    selection_policy_sha256=digest(context['profile']['probe_selection']), output_policy_sha256=digest(OUTPUT_POLICY)))


def verify(directory, run, metrics):
    """Inert query/publication semantics; executable replay belongs to the worker."""
    root = Path(directory)
    owner = contract(run['adapter'])
    records = run['source_records']
    manifest = dict(records=records, class_vocabulary=metrics['class_vocabulary'])
    inputs = read_document(root, 'probe-inputs.json')['inputs']
    if owner.task == 'text_classification':
        inputs = [row['text'] for row in records if row['split'] == 'validation']
    elif (type(inputs) is not list or len(inputs) != sum(row['split'] == 'validation' for row in records)
          or any(type(row) is not list or len(row) != 8 or any(type(value) not in (int, float) or not math.isfinite(value) for value in row) for row in inputs)):
        _invalid('Frozen audio probe measurements are invalid.')
    body = verify_directory(directory, job=job_for_run(run, directory), adapter=owner.adapter.ADAPTER, manifest=manifest,
                            reference_keys=owner.adapter.REFERENCE_KEYS, expected_inputs=inputs, reconstruct=False)
    read = lambda name: read_document(root, name)
    return dict(state='verified', manifest=body, checkpoint_index=read('checkpoints.json'), probe=read('probe.json'),
                metric_definitions=read('metric-definitions.json'), observations=read('observations.json'),
                model_definition=read('model-definition.json')), [read('checkpoint-fit-0001.json')], [read('probes-fit-0001.json')]
