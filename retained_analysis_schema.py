"""Closed v1 retained classifier query schemas; standard-library-only discovery."""
QUERY_ID = 'retained_checkpoint_examples'
QUERY_VERSION = 1
FIELDS = ('example_id', 'truth_index', 'predicted_index', 'confidence', 'error')


def schemas(obj, text, integer, array, const, identifier, sha):
    """Use the operation registry's ordinary schema constructors without imports."""
    natural = integer(0, 2**53 - 1)
    support = integer(0, 10000)
    nullable_offset = {'oneOf': [integer(0, 10000), {'type': 'null'}]}
    metric_id = {'enum': ['accuracy', 'loss', 'macro_f1']}
    fields = dict(array({'enum': list(FIELDS)}, len(FIELDS), 1), uniqueItems=True,
                  contains=const('example_id'))
    request = obj({'query_id': const(QUERY_ID), 'query_version': const(QUERY_VERSION),
                   'run_id': identifier, 'evaluation_sha256': sha, 'checkpoint_sha256': sha,
                   'metric_id': metric_id, 'metric_definition_sha256': sha, 'fields': fields,
                   'errors_only': {'type': 'boolean'}, 'limit': integer(1, 100), 'offset': integer(0, 10000)},
                  ['query_id', 'query_version', 'run_id', 'evaluation_sha256', 'checkpoint_sha256',
                   'metric_id', 'metric_definition_sha256'])
    definition = obj({'id': metric_id, 'semantic_version': const(1), 'split': const('validation'),
                      'units': const('dimensionless'), 'direction': {'enum': ['minimize', 'maximize']},
                      'reduction': {'enum': ['mean_cross_entropy', 'diagonal_over_population',
                                            'macro_over_frozen_vocabulary_zero_division_0']},
                      'population_sha256': sha, 'domain': obj({'minimum': {'type': 'number'}, 'maximum': {'type': 'number'}}),
                      'undefined_rule': const('not_applicable'), 'evaluator_sha256': sha,
                      'preprocessing_sha256': sha, 'class_order_sha256': sha})
    frozen = obj({'id': identifier, 'revision': integer(1, 2**53 - 1),
                  'source_revision': integer(1, 2**53 - 1), 'source_sha256': sha,
                  'asset_sha256': sha, 'exported_pixel_sha256': sha})
    row = obj({'example_id': identifier, 'ordinal': integer(0, 9999), 'frozen_reference': frozen,
               'truth_index': natural, 'predicted_index': natural,
               'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'error': {'type': 'boolean'}},
              ['example_id', 'ordinal', 'frozen_reference'])
    columns = {'oneOf': [obj({'field': const(field), 'type': const(kind),
                             'units': const('dimensionless' if field == 'confidence' else None)})
                         for field, kind in zip(FIELDS, ('string', 'integer', 'integer', 'number', 'boolean'))]}
    result = obj({'state': const('verified'), 'query_id': const(QUERY_ID), 'query_version': const(QUERY_VERSION),
                  'mode': const('frozen'), 'provenance': obj({'catalog_id': identifier, 'run_id': identifier,
                    'evaluation_sha256': sha, 'checkpoint_sha256': sha, 'metric_definition_sha256': sha,
                    'population_sha256': sha, 'probe_sha256': sha, 'data_sha256': sha,
                    'producer': obj({'catalog_id': identifier, 'run_id': identifier,
                                     'material_sha256': sha, 'adapter_sha256': sha})}),
                  'metric': obj({'id': metric_id, 'units': const('dimensionless'),
                                 'definition': definition, 'support': support}),
                  'curve': array(obj({'checkpoint_sha256': sha, 'epoch': integer(1, 128),
                                      'value': {'type': 'number'}, 'support': support}), 128, 1),
                  'columns': array(columns, len(FIELDS), 1),
                  'examples': obj({'rows': array(row, 100), 'population_support': support,
                                    'filtered_support': support, 'offset': integer(0, 10000),
                                    'limit': integer(1, 100), 'next_offset': nullable_offset,
                                    'filters': obj({'errors_only': {'type': 'boolean'}})}),
                  'sampling': obj({'method': const('none'), 'population': const('frozen_validation_probe')}),
                  'selection_sha256': sha})
    return request, result
