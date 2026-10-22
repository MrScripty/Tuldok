"""Fixed M2 public-to-owner dispatch for one already bound project projection.

The workspace validates selection, binding, checkpoint and the HTTP envelope.
This module projects bounded pages and calls existing domain methods. It neither
constructs live owners nor interprets scientific records or imported authority.
"""
import base64
import binascii
import copy

from workbench import WorkbenchError


_BOUND_FIELDS = frozenset(('binding', 'checkpoint', 'expected_checkpoint', 'request_key'))
_DATA_ACTIONS = frozenset(('data_query', 'data_get', 'data_availability', 'data_history',
    'data_responses', 'data_response_history', 'data_preferences', 'data_preference_history',
    'data_import_text', 'data_import_image', 'data_import_audio', 'data_import_mesh',
    'data_import_pointcloud', 'data_import_volume', 'data_import_sequence', 'data_import_scientific',
    'data_annotate', 'data_rights', 'data_source_save', 'data_source_delete', 'data_response_save',
    'data_preference_save', 'data_preference_delete', 'selections', 'selection_get', 'selection_create',
    'selection_rename', 'selection_delete', 'searches', 'search_create', 'search_rename',
    'search_delete', 'release_preview', 'release_freeze'))
_MATERIAL_ACTIONS = frozenset(('definitions', 'models', 'model_get', 'model_create', 'model_save',
    'model_publish', 'graphs', 'graph_get', 'graph_create', 'graph_create_external', 'graph_save', 'graph_clone', 'recipes',
    'recipe_get', 'recipe_create', 'recipe_save', 'recipe_prepare', 'model_material',
    'recipe_material', 'runtime_material', 'snapshot', 'materials'))
_HISTORY_ACTIONS = frozenset(('studies', 'study', 'study_create', 'study_save', 'trial', 'trial_prepare',
    'lineage', 'lineage_record', 'run', 'runs', 'candidate', 'candidate_select', 'evidence',
    'retained_analysis', 'retained_analysis_export', 'policies', 'policy', 'dependencies',
    'publication_result', 'package_state', 'expose_holdout', 'run_document_segment'))
_OTHER_ACTIONS = frozenset(('artifacts', 'artifact_status', 'artifact_resolve', 'producers', 'producer', 'source_register', 'source_references'))
SUPPORTED_OPERATIONS = frozenset('project_files.' + action for action in
    _DATA_ACTIONS | _MATERIAL_ACTIONS | _HISTORY_ACTIONS | _OTHER_ACTIONS)


def _body(arguments, *omit):
    return {key: copy.deepcopy(value) for key, value in arguments.items()
            if key not in _BOUND_FIELDS and key not in omit}


def _page(items, arguments, *, default=40):
    offset, limit = arguments.get('offset', 0), arguments.get('limit', default)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= (4 if default == 1 else 40):
        raise WorkbenchError('Invalid project page bounds.')
    return dict(items=copy.deepcopy(items[offset:offset + limit]), total=len(items), offset=offset, limit=limit)


def _origin_items(items, arguments):
    origin = arguments.get('origin_catalog_id')
    return [item for item in items if origin is None or item['origin_catalog_id'] == origin]


def _declarations(projection):
    return {item['id']: item['document'] for item in projection.session.snapshot['records']
            if item['family'] == 'project_artifact'}


def _artifact(projection, sha):
    declaration = _declarations(projection).get(sha)
    if declaration is None:
        raise WorkbenchError('Project artifact declaration is unavailable.', 'unavailable', 404)
    return declaration


def _bundle(projection, kind, arguments):
    """Existing native parsers alone assign bundle meaning, before publication."""
    body = _body(arguments)
    files = body['files']
    try:
        if kind == 'mesh':
            import meshes
            prepared = meshes.prepare(meshes.decode_file(files['mesh.ply'], meshes.PLY_LIMIT, 'mesh.ply'),
                meshes.decode_file(files['mesh.json'], meshes.MANIFEST_LIMIT, 'mesh.json'))
        elif kind in ('pointcloud', 'volume'):
            import spatial_assets
            parser, names, caps = spatial_assets.profile(kind)
            raw = []
            for name, cap in zip(names, caps):
                value = base64.b64decode(files[name], validate=True)
                if not 0 < len(value) <= cap:
                    raise ValueError()
                raw.append(value)
            prepared = parser.prepare(*raw)
        elif kind == 'sequence':
            prepared = projection.data.workbench.sequences.prepare_project_files(files)
        else:
            raise WorkbenchError('Unsupported native project import.', 'unsupported', 409)
    except WorkbenchError:
        raise
    except (ValueError, binascii.Error, KeyError, TypeError):
        raise WorkbenchError('Invalid native project import bundle.') from None
    return projection.data.import_bundle(kind, prepared, body, arguments['expected_checkpoint'], arguments['request_key'])


def _data(projection, action, a):
    data = projection.data
    if action == 'data_query': return data.query(_body(a))
    if action == 'data_get': return data.get(a['record_id'])
    if action == 'data_availability': return data.availability(a['record_id'])
    if action == 'data_history': return _page(data.history(a['record_id']), a, default=1)
    if action == 'data_responses': return _page(data.responses(a['record_id'])['responses'], a)
    if action == 'data_response_history':
        return _page(sorted(data.response_history(a['record_id'])['history'], key=lambda item: item['revision'], reverse=True), a, default=1)
    if action == 'data_preferences': return _page(data.preferences(a['record_id'])['judgments'], a)
    if action == 'data_preference_history':
        return _page(sorted(data.preference_history(a['record_id'])['history'], key=lambda item: item['revision'], reverse=True), a, default=1)
    if action == 'selections': return _page(sorted(data.list_selections()['selections'], key=lambda item: item['id']), a)
    if action == 'searches': return _page(sorted(data.list_searches()['searches'], key=lambda item: item['id']), a)
    if action == 'selection_get': return data.load_selection(a['selection_id'])
    if action == 'release_preview': return data.preview_release(_body(a))
    cp, key = a['expected_checkpoint'], a['request_key']
    if action == 'data_import_text': return data.import_text(_body(a), cp, key)
    if action == 'data_import_image': return data.import_image(_body(a), cp, key)
    if action == 'data_import_audio': return data.import_audio(_body(a), cp, key)
    if action == 'data_import_mesh': return _bundle(projection, 'mesh', a)
    if action == 'data_import_pointcloud': return _bundle(projection, 'pointcloud', a)
    if action == 'data_import_volume': return _bundle(projection, 'volume', a)
    if action == 'data_import_sequence': return _bundle(projection, 'sequence', a)
    if action == 'data_import_scientific': return projection.source_adapter.import_scientific(_body(a), cp, key)
    if action == 'data_annotate': return data.annotate(a['record_id'], _body(a, 'record_id'), cp, key)
    if action == 'data_rights': return data.correct_rights_note(a['record_id'], _body(a, 'record_id'), cp, key)
    if action == 'data_source_save': return data.save_image_source(a['record_id'], a['document'], cp, key)
    if action == 'data_source_delete': return data.delete_image_source(a['record_id'], a['document'], cp, key)
    if action == 'data_response_save': return data.save_response(a['document'], cp, key)
    if action == 'data_preference_save': return data.save_preference(a['document'], cp, key)
    if action == 'data_preference_delete': return data.delete_preference(a['document'], cp, key)
    if action == 'selection_create': return data.create_selection(a['document'], cp, key)
    if action == 'selection_rename': return data.rename_selection(a['selection_id'], _body(a, 'selection_id'), cp, key)
    if action == 'selection_delete': return data.delete_selection(a['selection_id'], _body(a, 'selection_id'), cp, key)
    if action == 'search_create': return data.create_search(a['document'], cp, key)
    if action == 'search_rename': return data.rename_search(a['search_id'], _body(a, 'search_id'), cp, key)
    if action == 'search_delete': return data.delete_search(a['search_id'], _body(a, 'search_id'), cp, key)
    if action == 'release_freeze': return data.freeze_release(_body(a), cp, key)
    raise AssertionError('Closed data dispatch is incomplete.')


def _definitions(projection, family, a):
    docs = projection.materials._documents()
    values = [doc['current'] for (kind, _), doc in docs.items()
              if kind == family and doc['origin_catalog_id'] == projection.session.snapshot['project_id']]
    return _page(sorted(values, key=lambda item: item['id']), a)


def _material(projection, action, a):
    materials, models, pipelines = projection.materials, projection.context.models, projection.context.pipelines
    if action == 'definitions': return pipelines.definitions()
    if action == 'models': return _definitions(projection, 'model_definition', a)
    if action == 'graphs': return _definitions(projection, 'pipeline_graph', a)
    if action == 'recipes': return _definitions(projection, 'recipe_definition', a)
    if action == 'model_get': return models.get(a['model_id'])
    if action == 'graph_get': return pipelines.get(a['graph_id'])
    if action == 'recipe_get': return pipelines.get_recipe(a['recipe_id'])
    if action == 'model_material': return materials.model(a['ref'], verify=a.get('verify', False))
    if action == 'recipe_material': return materials.recipe(a['ref'], verify=a.get('verify', False))
    if action == 'runtime_material': return materials.runtime(a['ref'], verify=a.get('verify', False))
    if action == 'snapshot': return materials.snapshot_ref(a['project_id'], a['manifest_sha256'],
        catalog_id=a['origin_catalog_id'], verify=a.get('verify', False))
    if action == 'materials':
        items = []
        for (family, _), doc in materials._documents().items():
            if family not in ('model_material', 'recipe_material', 'runtime_material', 'project_snapshot'): continue
            value = doc['value']
            identity = value.get('ref', {}).get('id', value.get('id'))
            item = dict(family=family, origin_catalog_id=doc['origin_catalog_id'], id=identity,
                        format=value.get('material', value).get('format'))
            if 'ref' in value: item['ref'] = copy.deepcopy(value['ref'])
            else: item['manifest_sha256'] = value['manifest_sha256']
            items.append(item)
        return _page(sorted(_origin_items(items, a), key=lambda item: (item['origin_catalog_id'], item['family'], item['id'])), a)
    cp, key = a['expected_checkpoint'], a['request_key']
    if action == 'model_create':
        body = _body(a)
        return materials.mutate_definition('model_definition', 'models.create', None, body, cp, key, lambda: models.create(body))
    if action == 'model_save':
        body = _body(a, 'model_id')
        return materials.mutate_definition('model_definition', 'models.save', a['model_id'], body, cp, key, lambda: models.save(a['model_id'], body))
    if action == 'model_publish': return materials.publish_model(models, a['model_id'], _body(a, 'model_id'), cp, key)
    if action == 'graph_create':
        body = _body(a)
        return materials.mutate_definition('pipeline_graph', 'graphs.create', None, body, cp, key, lambda: pipelines.create(body))
    if action == 'graph_create_external':
        body = _body(a)
        return materials.mutate_definition('pipeline_graph', 'graphs.create_external', None, body, cp, key, lambda: pipelines.create_external(body))
    if action == 'graph_save':
        body = _body(a, 'graph_id')
        return materials.mutate_definition('pipeline_graph', 'graphs.save', a['graph_id'], body, cp, key, lambda: pipelines.save(a['graph_id'], body))
    if action == 'graph_clone':
        body = _body(a, 'graph_id')
        return materials.mutate_definition('pipeline_graph', 'graphs.clone', a['graph_id'], body, cp, key, lambda: pipelines.clone(a['graph_id'], body))
    if action == 'recipe_create':
        body = _body(a)
        return materials.mutate_definition('recipe_definition', 'recipes.create', None, body, cp, key, lambda: pipelines.create_recipe(body))
    if action == 'recipe_save':
        body = _body(a, 'recipe_id')
        return materials.mutate_definition('recipe_definition', 'recipes.save', a['recipe_id'], body, cp, key, lambda: pipelines.save_recipe(a['recipe_id'], body))
    if action == 'recipe_prepare':
        return materials.prepare_recipe(pipelines, a['graph_id'], a['revision'], a['model'], cp, key,
            builtin=a.get('builtin', False), reconcile_capture=a.get('reconcile_capture', False),
            runtime_manifest=projection.runtime_manifest)
    raise AssertionError('Closed material dispatch is incomplete.')


def _study_summary(study):
    summary = copy.deepcopy(study)
    trial_ids = summary.pop('trial_ids')
    summary['source_format'] = summary.pop('format')
    summary['format'] = 'project_study_summary_v1'
    summary['trial_count'] = len(trial_ids)
    return summary


def _study_page(history, arguments):
    value = history.study(arguments['study_id'], origin_catalog_id=arguments['origin_catalog_id'],
        offset=arguments.get('offset', 0), limit=arguments.get('limit', 40), revision=arguments.get('revision'))
    result = copy.deepcopy(value)
    result['study'] = _study_summary(value['study'])
    result['trials'] = _page([{'id': identity} for identity in value['study']['trial_ids']], arguments)
    return result


def _run_page(history, arguments):
    value = history.run(arguments['run_id'], origin_catalog_id=arguments['origin_catalog_id'],
        offset=arguments.get('offset', 0), limit=arguments.get('limit', 40))
    # The Run owner applies the shared disclosure projection first. Large
    # captured documents and collections remain exact through document segments.
    run = value['run']
    fields = ('mode', 'id', 'dataset_id', 'request_key', 'state', 'created_at', 'started_at',
              'finished_at', 'graph_revision', 'graph_sha256', 'attempt', 'parent_run_id',
              'quality_claim', 'execution_kind', 'result_kind', 'material_sha256',
              'approval_id', 'actor_id', 'custody_phase', 'release_id', 'release_sha256', 'release_bytes')
    summary = {key: copy.deepcopy(run[key]) for key in fields if key in run}
    summary.update(format='project_run_summary_v1', source_schema_version=run['schema_version'],
        available_fields=sorted(run),
        collection_counts={key: len(run[key]) for key in
            ('events', 'artifacts', 'node_attempts', 'exposure_events', 'prior_test_exposure', '_phase_timings')
            if isinstance(run.get(key), list)})
    result = {key: copy.deepcopy(item) for key, item in value.items() if key != 'run'}
    result['run'] = summary
    return result


def _history(projection, action, a):
    history = projection.history
    origin = a.get('origin_catalog_id')
    if action == 'studies':
        return _page([dict(origin_catalog_id=item['origin_catalog_id'], study=_study_summary(item['study']))
            for item in _origin_items(history.studies()['studies'], a)], a)
    if action == 'study': return _study_page(history, a)
    if action == 'trial': return history.trial(a['trial_id'], origin_catalog_id=origin)
    if action == 'run': return _run_page(history, a)
    if action == 'run_document_segment': return history.run_document_segment(a['run_id'],
        origin_catalog_id=origin, expected_sha256=a['expected_sha256'], offset=a['offset'], limit=a['limit'])
    if action == 'candidate': return history.candidate(a['candidate_id'], origin_catalog_id=origin, verify=a.get('verify', False))
    if action == 'lineage': return _page(history.lineage(origin_catalog_id=origin)['records'], a)
    if action == 'policies': return _page(history.policies(origin_catalog_id=origin)['policies'], a)
    if action == 'policy': return history.policy(a['ref'])
    if action == 'runs':
        items = []
        for (catalog, identity), doc in sorted(history._facts().runs.items()):
            run = doc['run']
            summary = {key: copy.deepcopy(run[key]) for key in ('id', 'name', 'state', 'created_at', 'finished_at', 'execution_kind') if key in run}
            items.append(dict(origin_catalog_id=catalog, run=summary))
        return _page(_origin_items(items, a), a)
    if action == 'dependencies': return history.dependencies(a['run_id'], origin_catalog_id=origin,
        offset=a.get('offset', 0), limit=a.get('limit', 40))
    if action == 'publication_result': return history.publication_result(a['run_id'], origin_catalog_id=origin)
    if action == 'package_state': return history.package_state(a['candidate_id'], origin_catalog_id=origin)
    if action == 'evidence': return history.evidence(a['run_id'], a.get('selectors'), origin_catalog_id=origin)
    if action in ('retained_analysis', 'retained_analysis_export'):
        return history.retained_analysis(origin, _body(a, 'origin_catalog_id'), export=action == 'retained_analysis_export')
    cp, key = a['expected_checkpoint'], a['request_key']
    if action == 'study_create': return history.create_study(_body(a), cp, key)
    if action == 'study_save': return history.save_study(a['study_id'], _body(a, 'study_id'), cp, key)
    if action == 'trial_prepare': return history.prepare_trial_from_material(a['study_id'], _body(a, 'study_id'), cp, key)
    if action == 'candidate_select': return history.select_candidate(a['study_id'], _body(a, 'study_id'), cp, key)
    if action == 'lineage_record': return history.record_lineage(_body(a), cp, key)
    if action == 'expose_holdout': return projection.disclose(a['run_id'], _body(a, 'run_id'), cp, key)
    raise AssertionError('Closed historical dispatch is incomplete.')


def dispatch(projection, name, arguments):
    if name not in SUPPORTED_OPERATIONS:
        raise WorkbenchError('Unsupported external-project operation.', 'unsupported', 409)
    action = name.split('.')[1]
    projection.session.access.require('inspect', name)
    if action in _DATA_ACTIONS: return _data(projection, action, arguments)
    if action in _MATERIAL_ACTIONS: return _material(projection, action, arguments)
    if action in _HISTORY_ACTIONS: return _history(projection, action, arguments)
    if action == 'artifacts':
        items = [dict(copy.deepcopy(declaration), availability=projection.artifacts.inspect(declaration))
                 for _, declaration in sorted(_declarations(projection).items())]
        return _page(items, arguments)
    if action == 'artifact_status': return projection.artifacts.status(_artifact(projection, arguments['sha256']))
    if action == 'artifact_resolve':
        projection.session.access.require('edit', 'project_files.artifact_resolve', arguments['sha256'], owner_only=True)
        return projection.resolve_artifact(_body(arguments), arguments['expected_checkpoint'], arguments['request_key'])
    if action == 'producers': return projection.producers.list(arguments['family'],
        origin_catalog_id=arguments.get('origin_catalog_id'), offset=arguments.get('offset', 0), limit=arguments.get('limit', 40))
    if action == 'producer': return projection.producers.get(arguments['family'], arguments['producer_id'],
        origin_catalog_id=arguments['origin_catalog_id'], entries_offset=arguments.get('entries_offset', 0),
        entries_limit=arguments.get('entries_limit', 40))
    if action == 'source_references':
        return projection.source_adapter.references(
            {key: arguments[key] for key in ('origin_catalog_id', 'project_id', 'manifest_sha256')},
            offset=arguments.get('offset', 0), limit=arguments.get('limit', 40))
    if action == 'source_register':
        projection.session.access.require('edit', 'project_files.source_register', owner_only=True)
        return projection.source_adapter.register(_body(arguments), arguments['expected_checkpoint'], arguments['request_key'])
    raise AssertionError('Closed project dispatch is incomplete.')
