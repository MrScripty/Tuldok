"""Pure, finite reconstruction of editable materials for an independent fork.

Original definitions and hash-bearing materials remain unchanged in the archive.
Unresolved bindings are retained as inert, inspectable intents, never SQL drafts.
"""
import copy
from datetime import datetime

from workbench import WorkbenchError

INTENT_FORMAT = 'project_material_fork_intent_v1'
OWNED = ('model_definition', 'pipeline_graph', 'recipe_definition')


def _fail(message):
    raise WorkbenchError(message, 'invalid', 400)


def _date(value):
    if type(value) is not str or len(value) > 80:
        _fail('Fork creation requires an offset timestamp.')
    try:
        instant = datetime.fromisoformat(value)
        if instant.utcoffset() is None: raise ValueError()
    except ValueError:
        _fail('Fork creation requires an offset timestamp.')


def is_intent(value):
    return type(value) is dict and value.get('format') == INTENT_FORMAT


def _model_bindings(value, destination):
    """Qualify only exact pure templates accepted by the existing task owners."""
    import image_training
    import model_evidence
    import one_fit_evidence
    import text_training
    import audio_training
    task = value['task']
    owners = [(model_evidence, image_training),
              (one_fit_evidence.contract(text_training), text_training),
              (one_fit_evidence.contract(audio_training), audio_training)]
    for owner, adapter in owners:
        if task != owner.task_ref(task['catalog_id']): continue
        required = []
        definition = None
        specification = value['specification']
        try:
            if adapter is image_training:
                if specification.get('template') != 'tinycnn_v2': raise ValueError()
                architecture = image_training.validate_architecture(
                    {k:v for k,v in specification.items() if k != 'template'})
                definition = dict(specification=dict(template='tinycnn_v2', **architecture),
                    preprocessing_policy=image_training.transform_for_parameters(architecture),
                    output_policy=model_evidence.OUTPUT_POLICY)
            else:
                if specification.get('template') != owner.template: raise ValueError()
                definition = owner.model_definition({k:v for k,v in specification.items() if k != 'template'})
        except ValueError:
            required.append('specification')
        if definition is not None:
            required.extend(field for field in ('specification','preprocessing_policy','output_policy')
                            if value[field] != definition[field])
        elif value['output_policy'] != owner.OUTPUT_POLICY:
            required.append('output_policy')
        return owner.task_ref(destination), sorted(set(required))
    return None, ['task']


def _construct(family, source, identity, catalog):
    """Rebuild only explicitly understood bindings; retain every other field."""
    from project_material import _definition
    original = copy.deepcopy(source['definition'] if is_intent(source) else source)
    required = []
    if family == 'model_definition':
        task, required = _model_bindings(original, catalog)
        if original['kind'] != 'template': required.append('source_selector')
        if not required:
            value = dict(original, id=identity, revision=1, task=task)
            return _definition(family, value, catalog)
    elif family == 'pipeline_graph':
        if original.get('recipe') == 'external_recipe':
            required = ['recipe_source', 'inputs', 'runtime']
        elif any(node['type'] == 'release' for node in original['nodes']):
            required = ['release']
        elif any(node['type'] not in ('train', 'evaluate', 'validate', 'publish') or
                 node['type'] != 'train' and node['parameters'] for node in original['nodes']):
            required = ['nodes']
        else:
            # The graph owner owns its closed structure and adapter selection.
            # No release, recipe-source or external input binding is adopted.
            from pipeline import adapter_for_graph, types_for_graph
            import image_training
            adapter = adapter_for_graph(original)
            try:
                for node in original['nodes']:
                    if node['type'] not in types_for_graph(original): raise ValueError()
                    if node['type'] == 'train':
                        validate = (image_training.validate_model_parameters if original.get('recipe') == image_training.MODEL_RECIPE
                                    else adapter.validate_parameters)
                        validate(node['parameters'])
            except ValueError:
                required = ['nodes']
            else:
                return _definition(family, dict(original, id=identity, revision=1), catalog)
    elif family == 'recipe_definition':
        required = ['data', 'evaluation_profile', 'model', 'runtime', 'task', 'trainer']
    else:
        _fail('Unsupported editable material fork family.')
    return dict(format=INTENT_FORMAT, catalog_id=catalog, id=identity, revision=1,
                name=original['name'], definition_family=family, definition=original,
                required_reselection=sorted(required))


def decode_intent(value, family, catalog):
    from project_material import _closed, _catalog, _definition, ID
    _closed(value, ('format', 'catalog_id', 'id', 'revision', 'name',
                    'definition_family', 'definition', 'required_reselection'), 'fork intent')
    if (value['format'] != INTENT_FORMAT or value['catalog_id'] != catalog or
            value['definition_family'] != family or type(value['id']) is not str or
            not ID.fullmatch(value['id']) or type(value['revision']) is not int or value['revision'] != 1):
        _fail('Invalid material fork intent identity.')
    old = value['definition']
    origin = old['task']['catalog_id'] if family != 'pipeline_graph' else catalog
    _catalog(origin)
    _definition(family, old, origin)
    if _construct(family, old, value['id'], catalog) != value:
        _fail('Material fork intent differs from its exact unresolved definition.')
    return copy.deepcopy(value)


def fork_records(records, source_project_id, source_checkpoint, destination_project_id, *, id_factory, created_at):
    from project_material import decode_records, FAMILIES, _catalog, SHA, ID
    from project_fork import active_records
    _catalog(source_project_id); _catalog(destination_project_id); _date(created_at)
    if source_project_id == destination_project_id or type(source_checkpoint) is not str or not SHA.fullmatch(source_checkpoint):
        _fail('Independent material fork requires a distinct identity and source checkpoint.')
    decode_records(records)
    active = active_records(records, project_id=source_project_id)
    existing = {r['document']['current']['id'] for r in records if r['family'] in OWNED}
    fresh, mapping = [], []
    for envelope in sorted(active, key=lambda r: (r['family'], r['id'])):
        family = envelope['family']
        if family not in OWNED: continue
        old = envelope['document']['current']
        identity = id_factory(family, envelope['id'], old['revision'])
        if type(identity) is not str or not ID.fullmatch(identity) or identity in existing:
            _fail('Material fork allocator must supply a fresh editable UUID.')
        existing.add(identity)
        value = _construct(family, old, identity, destination_project_id)
        locator = destination_project_id + '.' + identity
        fresh.append(dict(family=family, id=locator, document=dict(format=FAMILIES[family],
            origin_catalog_id=destination_project_id, current=value, revisions=[copy.deepcopy(value)], audit=[],
            fork_origin=dict(project_id=source_project_id, checkpoint=source_checkpoint, family=family,
                             id=envelope['id'], revision=old['revision'], created_at=created_at))))
        mapping.append(dict(family=family, source_id=envelope['id'], source_revision=old['revision'], destination_id=locator))
    mapping.sort(key=lambda m: (m['family'],m['source_id'],m['source_revision'],m['destination_id']))
    return dict(records=fresh, mapping=mapping)


def validate_records(records):
    """Prove each fork's unaudited initial revision from exact retained owners."""
    from project_material import _closed, _catalog, SHA
    from project_fork import decode_fork
    if not any(r.get('family') == 'project_fork' or
               r.get('family') in OWNED and 'fork_origin' in r.get('document', {}) for r in records):
        return
    decode_fork(records)
    indexed = {(r['family'],r['id']):r for r in records}
    overlays = [r['document'] for r in records if r['family'] == 'project_fork']
    mapped = {}
    for overlay in overlays:
        for mapping in overlay['mapping']:
            if mapping['family'] in OWNED:
                key = mapping['family'],mapping['destination_id']
                if key in mapped: _fail('Material fork target repeats across origin overlays.')
                mapped[key] = (overlay, mapping)
    for record in records:
        if record['family'] not in OWNED: continue
        doc = record['document']; key = record['family'],record['id']
        origin = doc.get('fork_origin')
        if origin is None:
            if key in mapped: _fail('Mapped material draft lacks its explicit fork origin.')
            continue
        _closed(origin, ('project_id','checkpoint','family','id','revision','created_at'), 'material fork origin')
        _catalog(origin['project_id']); _date(origin['created_at'])
        if type(origin['checkpoint']) is not str or not SHA.fullmatch(origin['checkpoint']):
            _fail('Invalid material fork source checkpoint.')
        if key not in mapped: _fail('Material fork origin lacks a retained mapping.')
        overlay, mapping = mapped[key]
        expected = dict(project_id=overlay['source']['project_id'], checkpoint=overlay['source']['checkpoint'],
                        family=mapping['family'], id=mapping['source_id'], revision=mapping['source_revision'],
                        created_at=origin['created_at'])
        if origin != expected or doc['origin_catalog_id'] != overlay['destination_project_id']:
            _fail('Material fork origin differs from its archived source mapping.')
        original = indexed[(mapping['family'],mapping['source_id'])]['document']['current']
        if original['revision'] != origin['revision']:
            _fail('Material fork source revision differs from its archived current value.')
        initial = _construct(record['family'], original, doc['current']['id'], doc['origin_catalog_id'])
        if doc['revisions'][0] != initial:
            _fail('Material fork initial revision differs from its owner reconstruction.')
