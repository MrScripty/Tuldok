"""The operations a served project folder offers, as data: names, who may call them, arguments and results.

Owns the table of section 2 of docs/plans/definition-first-projects/spec-m7.md, with the three
rows of section 2 of spec-w1.md (map, note, recipe_results) and the two of
section 2 of spec-w3.md (draft_branch, revert_definition), the five of
section 3 of spec-d1.md (records, record, inside, array_slice, array_summary),
the three of section 3 of spec-d2.md (weights, weights_compare,
array_tiles), the two of section 2 of spec-d6.md (fields, field_compare), the three of
section 3 of docs/plans/training-and-curation/spec-t2.md (model_graph,
model_graph_overlay, model_graph_compare),
the five of section 4 of docs/plans/training-and-curation/spec-t1.md
(training, training_series, training_histograms, training_samples,
training_sample), the three of section 4 of
spec-t3.md (model_compare, benchmark_axes, intervals),
the five of section 5 of spec-d4.md (annotation_tasks,
annotated_records, annotation, set_annotation, revert_annotations) and the
five of sections 2 and 4 of spec-d5.md (endpoint, set_endpoint,
find_endpoints, suggestion_models, suggest_annotation).
Each Operation names one operation project.<name>, the rule its caller must
satisfy (who), whether it changes anything (mutation), a closed JSON Schema of
its arguments and the result keys that are always present. service.py checks
calls against it and agent_api.py publishes it; neither restates it. This
module imports only the standard library.
"""
from dataclasses import dataclass

WHO = ('inspect', 'edit', 'cancel', 'request', 'owner')
REQUEST_STATES = ('awaiting-approval', 'queued', 'running', 'succeeded', 'failed', 'cancelled', 'declined', 'expired')
KINDS = ('dataset', 'model', 'recipe', 'benchmark', 'step', 'environment', 'chart', 'annotation')
CHANGES = ('training-policy', 'architecture', 'refinement', 'component')   # a recipe's kind of change
RECORD_KINDS = ('text', 'image', 'audio', 'pointcloud', 'mesh', 'array', 'file')   # the kinds of a product's record
TARGET_LIMIT = 50
REASON_CHARACTERS = 400
ANNOTATION_STATES = ('draft', 'accepted', 'needs-work', 'rejected')    # annotations.STATES
# The counts of annotation_tasks, and the filters of annotated_records.
ANNOTATION_COUNTS = ('unannotated', 'draft', 'accepted', 'needs-work', 'rejected', 'stale', 'invalid')
ANNOTATION_ITEMS = 200      # items of one set_annotation
REVERT_RECORDS = 10_000     # records named by one revert_annotations
ENDPOINT_CHARACTERS = 2048  # an address of a Pumas endpoint (local.ENDPOINT_LIMIT)
INSTRUCTION_CHARACTERS = 4000
GRAPH_MODULES = 2000        # modules named open or closed by one model_graph (spec-t2.md section 3)
GRAPH_OVERLAYS = ('parameters', 'outputs', 'operations', 'change')
COMPARED_MOST = 4           # recipes of one model_compare (spec-t3.md section 4)


@dataclass(frozen=True)
class Operation:
    """One row of the table. arguments is a closed JSON Schema object; result is the tuple of required result keys."""
    name: str
    summary: str
    who: str
    mutation: bool
    arguments: dict
    result: tuple


# ----------------------------------------------------------- argument schemas

_REFERENCE = {'type': 'string', 'minLength': 1, 'maxLength': 200}
_NAME = {'type': 'string', 'minLength': 1, 'maxLength': 200}   # a bare name or a <directory>/<name> reference
_RUN = {'type': 'string', 'minLength': 6, 'maxLength': 128}
_REQUEST = {'type': 'string', 'minLength': 6, 'maxLength': 128}
_TEXT = {'type': 'string'}
_FLAG = {'type': 'boolean'}
_OFFSET = {'type': 'integer', 'minimum': 0}
_THEME = {'type': 'string', 'enum': ['light', 'dark']}
_TARGETS = {'type': 'array', 'items': _REFERENCE, 'maxItems': TARGET_LIMIT}
_ADDRESS = {'type': 'string', 'minLength': 1, 'maxLength': 4096}   # a path in a product; '!' names an archive member
_ARRAY = {'type': 'string', 'minLength': 1, 'maxLength': 1024}
_AXIS = {'type': 'integer', 'minimum': 0, 'maximum': 63}
_RECORD_ID = {'type': 'string', 'minLength': 1, 'maxLength': 600}     # an annotation's record (spec-d4.md section 2)
_SET_ITEM = {'type': 'object', 'properties': {'record': _RECORD_ID,
                                              'state': {'type': 'string', 'enum': list(ANNOTATION_STATES)},
                                              'value': {}, 'note': {'type': 'string', 'maxLength': 4000}},
             'required': ['record', 'state'], 'additionalProperties': False}
_REMOVE_ITEM = {'type': 'object', 'properties': {'record': _RECORD_ID, 'remove': {'const': True}},
                'required': ['record', 'remove'], 'additionalProperties': False}


def _limit(most):
    return {'type': 'integer', 'minimum': 1, 'maximum': most}


def _arguments(required=(), **properties):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


# --------------------------------------------------------------- result keys

SUMMARY = ('project_id', 'name', 'folder', 'code_root', 'kinds', 'states', 'worker')
STATUS = ('unsaved', 'removed', 'added', 'changed', 'missing', 'irregular', 'results_unsaved', 'results_changed',
          'annotations_unsaved', 'annotations_changed')
DEFINITION = ('reference', 'kind', 'title', 'text', 'document', 'state', 'unsaved', 'removed', 'uses', 'used_by')
PLAN = ('targets', 'every', 'buildable', 'blocked_targets', 'counts', 'gpu_steps', 'disk_gb', 'disk_unknown',
        'wall_hours', 'wall_unknown', 'estimated_disk_gb', 'estimated_disk_steps', 'estimated_wall_hours',
        'estimated_wall_steps', 'notes', 'steps')
ENVIRONMENT = ('reference', 'title', 'state', 'python', 'device', 'packages', 'installable', 'origin', 'interpreter',
               'recorded_at', 'checked_at', 'ok', 'found', 'problems')
RUN = ('id', 'reference', 'subject', 'plan_id', 'state', 'scratch', 'commit', 'inputs', 'environment', 'argv',
       'directory', 'owner_pid', 'owner_boot', 'queued_at', 'started_at', 'finished_at', 'exit_status', 'seconds',
       'bytes', 'strays', 'problem', 'definition', 'settings', 'env_names', 'product', 'builder_alive')
REQUEST = ('id', 'state', 'targets', 'every', 'scratch', 'covers', 'requested_at', 'requested_by', 'decided_at',
           'decided_by', 'started_at', 'finished_at', 'plan_id', 'cancel_requested', 'result', 'problem',
           'expires_at')
SLICE = ('shape', 'dtype', 'axes', 'index', 'rows', 'columns', 'stride', 'values_f32', 'min', 'max', 'nonfinite')
SUMMARY_OF_ARRAY = ('shape', 'dtype', 'count', 'min', 'max', 'mean', 'std', 'zeros', 'nonfinite', 'histogram',
                    'stride')
TILES = ('shape', 'dtype', 'across', 'axes', 'index', 'first', 'tiles', 'rows', 'columns', 'stride', 'values_f32',
         'min', 'max', 'nonfinite')
FIELD_COMPARE = ('entry', 'case', 'shape', 'dtype', 'axes', 'axis', 'index', 'rows', 'columns', 'stride',
                 'mean_free', 'reference_f32', 'predicted_f32', 'error_f32', 'range', 'error_limit', 'figures')
TRAINING = ('run', 'present', 'started_at', 'series', 'lines', 'last_step', 'last_time', 'other_keys', 'histograms',
            'histogram_lines', 'samples', 'sample_lines', 'checkpoints', 'problems', 'bad_lines', 'truncated')
TRAINING_HISTOGRAMS = ('name', 'kind', 'rows', 'stride', 'low', 'high', 'bins', 'counts', 'totals', 'nonfinite')
TRAINING_SERIES = 16       # series of one training_series
COMPARE = ('tensors', 'total', 'only_here', 'only_there', 'reshaped', 'unread')
SAVE = ('written', 'deleted', 'results_written', 'results_deleted', 'annotations_written', 'annotations_deleted')
CANCEL_RUN = ('id', 'reference', 'subject', 'state', 'cancel_file', 'already_asked')
STOP_RUN = ('id', 'reference', 'subject', 'was', 'state', 'killed', 'remaining', 'marked_unknown')
ENDPOINT = ('address', 'answered', 'version', 'models', 'problem')
MODEL_GRAPH = ('path', 'format', 'complete', 'reason', 'method', 'torch', 'model', 'inputs', 'notes', 'counts',
               'modules', 'tensors', 'depth', 'open', 'nodes', 'edges')
_STATISTIC = {'type': 'string', 'enum': ['mean', 'median', 'p10', 'p90', 'min', 'max']}
_MODULE_PATHS = {'type': 'array', 'items': {'type': 'string', 'maxLength': 1024}, 'maxItems': GRAPH_MODULES}


OPERATIONS = (
    Operation('summary', "Read the project's name, folder, counts of definitions by kind and state, and whether "
              'its build worker runs.', 'inspect', False, _arguments(), SUMMARY),
    Operation('status', 'List the unsaved and removed definitions and the files changed on disk since the last '
              'import or save.', 'inspect', False, _arguments(), STATUS),
    Operation('check', 'Check the project folder on disk and list its errors and warnings, even when it does not '
              'open.', 'inspect', False, _arguments(), ('ok', 'errors', 'warnings', 'problems')),
    Operation('definitions', 'List the definitions, optionally of one kind, with their states.', 'inspect', False,
              _arguments(kind={'type': 'string', 'enum': list(KINDS)}), ('definitions',)),
    Operation('definition', 'Read one definition: its text, document, state, what it uses and what uses it.',
              'inspect', False, _arguments(['reference'], reference=_REFERENCE), DEFINITION),
    Operation('graph', 'Read every definition with its kind and state, and the edges between them.', 'inspect',
              False, _arguments(), ('nodes', 'edges')),
    Operation('results_overview', 'List, per benchmark, how many subjects have results and whether they differ '
              'from the results file.', 'inspect', False, _arguments(), ('benchmarks',)),
    Operation('results', "Read one page of a benchmark's summary rows, optionally for one subject, metric or group.",
              'inspect', False,
              _arguments(['benchmark'], benchmark=_NAME, subject=_TEXT, metric=_TEXT, group=_TEXT, offset=_OFFSET,
                         limit=_limit(2000)), ('rows', 'total')),
    Operation('values', "Read one page of a benchmark subject's per-case values.", 'inspect', False,
              _arguments(['benchmark', 'subject'], benchmark=_NAME, subject=_TEXT, metric=_TEXT, offset=_OFFSET,
                         limit=_limit(1000)), ('rows', 'total')),
    Operation('chart', "Read a chart's data, and its SVG drawing when asked.", 'inspect', False,
              _arguments(['chart'], chart=_NAME, svg=_FLAG, theme=_THEME), ('data',)),
    Operation('report', 'Read the HTML report of the project: where it stands, every chart, the results and the '
              'definitions.', 'inspect', False, _arguments(theme=_THEME), ('html',)),
    Operation('plan', 'Plan building the targets (or every buildable definition) without running anything.',
              'inspect', False, _arguments(['targets'], targets=_TARGETS, every=_FLAG), PLAN),
    Operation('estimates', 'List the stored estimates of disk and time for the definitions as they now are.',
              'inspect', False, _arguments(), ('estimates',)),
    Operation('environments', 'List the environments with the interpreter recorded on this machine and their last '
              'check.', 'inspect', False, _arguments(), ('environments',)),
    Operation('environment', 'Read one environment with the interpreter recorded on this machine and its last check.',
              'inspect', False, _arguments(['reference'], reference=_REFERENCE), ENVIRONMENT),
    Operation('runs', 'List the runs, newest first, optionally of one definition.', 'inspect', False,
              _arguments(reference=_REFERENCE, limit=_limit(500)), ('runs',)),
    Operation('run', "Read one run's record, its product and whether its build is alive, without variable values.",
              'inspect', False, _arguments(['run'], run=_RUN), RUN),
    Operation('progress', "Read a run's latest progress event and its logs from the given offsets; to read on, pass each "
              "log's returned offset back as stdout_offset and stderr_offset.",
              'inspect', False, _arguments(['run'], run=_RUN, stdout_offset=_OFFSET, stderr_offset=_OFFSET),
              ('run', 'event', 'stdout', 'stderr', 'ended')),
    Operation('products', 'List the current products, optionally of one definition.', 'inspect', False,
              _arguments(reference=_REFERENCE), ('products',)),
    Operation('build_requests', 'List the build requests, newest first, optionally in one state.', 'inspect', False,
              _arguments(state={'type': 'string', 'enum': list(REQUEST_STATES)}, limit=_limit(500)), ('requests',)),
    Operation('build_request', 'Read one build request with what it covers and the runs of its build.', 'inspect',
              False, _arguments(['request'], request=_REQUEST), REQUEST + ('runs',)),
    Operation('activity', 'List the changes asked of this project through the interface, newest first, and how '
              'each ended.', 'inspect', False, _arguments(offset=_OFFSET, limit=_limit(500)), ('items', 'total')),
    Operation('map', 'Read the map of the project: its groups, every recipe as a model with its group, kind of '
              'change, state and track value, the lines between them and the comparisons.', 'inspect', False,
              _arguments(), ('groups', 'models', 'edges', 'comparisons', 'track')),
    Operation('note', 'Read one file under the notes directory of the project folder, given relative to it.',
              'inspect', False, _arguments(['path'], path={'type': 'string', 'minLength': 1, 'maxLength': 1024}),
              ('path', 'text')),
    Operation('recipe_results', "Read the summary rows of every benchmark subject made from one recipe, ungrouped "
              'or for one group.', 'inspect', False, _arguments(['recipe'], recipe=_REFERENCE, group=_TEXT),
              ('rows', 'benchmarks')),
    Operation('draft_branch', 'Write the text of a new recipe branched from one of the project\'s, with its name '
              'and what keeping it would find wrong; nothing is stored.', 'inspect', False,
              _arguments(['recipe', 'title'], recipe=_REFERENCE,
                         title={'type': 'string', 'minLength': 1, 'maxLength': 200},
                         name={'type': 'string', 'minLength': 1, 'maxLength': 120},
                         change={'type': 'string', 'enum': list(CHANGES)},
                         description={'type': 'string', 'maxLength': 4000}),
              ('reference', 'text', 'parent', 'inlined', 'problems')),
    Operation('records', "Read one page of the records of a finished run's product, optionally of one kind or split, "
              'with the counts by kind and split.', 'inspect', False,
              _arguments(['run'], run=_RUN, offset=_OFFSET, limit=_limit(200),
                         kind={'type': 'string', 'enum': list(RECORD_KINDS)}, split=_TEXT),
              ('records', 'total', 'source', 'kinds', 'splits', 'problems')),
    Operation('record', "Read one record of a finished run's product by its id, or any file in it by its path, "
              'with its content: text, image size, sound peaks, points, mesh or arrays.', 'inspect', False,
              dict(_arguments(['run'], run=_RUN, id={'type': 'string', 'minLength': 1, 'maxLength': 4096},
                              path={'type': 'string', 'minLength': 1, 'maxLength': 4096}),
                   oneOf=[{'required': ['id']}, {'required': ['path']}]),
              ('record', 'content')),
    Operation('inside', "List a directory, an archive or the arrays of an .npz in a finished run's product.",
              'inspect', False,
              _arguments(['run'], run=_RUN, path={'type': 'string', 'maxLength': 4096}, offset=_OFFSET,
                         limit=_limit(500)), ('entries', 'total')),
    Operation('array_slice', "Read a slice along two axes of an array in a finished run's product, as 32-bit floats.",
              'inspect', False,
              _arguments(['run', 'path'], run=_RUN, path=_ADDRESS, array=_ARRAY,
                         axes={'type': 'array', 'items': _AXIS, 'minItems': 2, 'maxItems': 2},
                         index={'type': 'array', 'items': {'type': 'integer', 'minimum': 0}, 'maxItems': 64},
                         most=_limit(512)), SLICE),
    Operation('array_summary', "Read the range, mean, deviation and histogram of an array in a finished run's "
              'product.', 'inspect', False,
              _arguments(['run', 'path'], run=_RUN, path=_ADDRESS, array=_ARRAY, bins=_limit(256)),
              SUMMARY_OF_ARRAY),
    Operation('weights', "List the weights files of a finished run's product, each with its size, the file it started "
              'from and, when Tuldok reads it, its layers and parameter count.', 'inspect', False,
              _arguments(['run'], run=_RUN), ('files',)),
    Operation('weights_compare', "Compare, array by array, a weights file of a finished run's product with one of "
              'the same or another finished run: norms, relative change, cosine and largest change.', 'inspect',
              False,
              _arguments(['run', 'path', 'other_run', 'other_path'], run=_RUN, path=_ADDRESS, other_run=_RUN,
                         other_path=_ADDRESS), COMPARE),
    Operation('array_tiles', "Read tiles of two axes of an array in a finished run's product, one per position along "
              'a third axis, as 32-bit floats.', 'inspect', False,
              _arguments(['run', 'path'], run=_RUN, path=_ADDRESS, array=_ARRAY, across=_AXIS,
                         axes={'type': 'array', 'items': _AXIS, 'minItems': 2, 'maxItems': 2},
                         index={'type': 'array', 'items': {'type': 'integer', 'minimum': 0}, 'maxItems': 64},
                         first=_OFFSET, most=_limit(64)), TILES),
    Operation('fields', "List the fields a finished run's product kept: each case's native and predicted files, its "
              'name, shape and whether the two can be compared, and the figures the run reported itself.', 'inspect',
              False, _arguments(['run'], run=_RUN), ('kept', 'cases', 'reported')),
    Operation('field_compare', "Read a slice of one kept case's native field, predicted field and signed error as "
              '32-bit floats, with the figures of the error over the whole field.', 'inspect', False,
              _arguments(['run', 'entry', 'case'], run=_RUN, entry=_OFFSET, case=_OFFSET,
                         axis={'type': 'integer', 'minimum': 0, 'maximum': 3},
                         index={'type': 'array', 'items': {'type': 'integer', 'minimum': 0}, 'maxItems': 4},
                         mean_free=_FLAG), FIELD_COMPARE),
    Operation('model_graph', "Read the structure a finished run's script recorded (model-graph.json): its "
              'operations and the edges between them, folded to a depth of the module tree with modules opened or '
              'closed by path, and the module tree.', 'inspect', False,
              _arguments(['run'], run=_RUN, depth={'type': 'integer', 'minimum': 0, 'maximum': 64},
                         open=_MODULE_PATHS, close=_MODULE_PATHS), MODEL_GRAPH),
    Operation('model_graph_overlay', "Read a number per module and per operation of a finished run's model graph: "
              'parameters, output values, operations, or the relative change of the weights under it against the '
              'weights it started from or another run\'s.', 'inspect', False,
              _arguments(['run', 'kind'], run=_RUN, kind={'type': 'string', 'enum': list(GRAPH_OVERLAYS)},
                         against={'type': 'string', 'enum': ['start', 'run']}, other_run=_RUN, path=_ADDRESS,
                         other_path=_ADDRESS), ('kind', 'unit', 'modules', 'nodes', 'low', 'high')),
    Operation('model_graph_compare', "Match the modules of two finished runs' model graphs by path: the same, "
              'changed (class or tensor shapes), added or missing.', 'inspect', False,
              _arguments(['run', 'other_run'], run=_RUN, other_run=_RUN), ('modules', 'counts')),
    Operation('training', "List what a run's training script logged, while it runs or after: its scalar series, the "
              'tensors whose histograms it kept, its samples and checkpoints, and the lines it could not read.',
              'inspect', False, _arguments(['run'], run=_RUN), TRAINING),
    Operation('training_series', "Read scalar series a run's training script logged, in buckets of a power of two "
              'points (mean, least and greatest), from the bucket the caller holds when its bucket size is the same.',
              'inspect', False,
              _arguments(['run', 'series'], run=_RUN,
                         series={'type': 'array', 'minItems': 1, 'maxItems': TRAINING_SERIES,
                                 'items': {'type': 'object',
                                           'properties': {'name': {'type': 'string', 'minLength': 1,
                                                                   'maxLength': 200},
                                                          'size': {'type': 'integer', 'minimum': 0},
                                                          'since': _OFFSET},
                                           'required': ['name'], 'additionalProperties': False}},
                         most=_limit(4000)), ('series', 'lines')),
    Operation('training_histograms', "Read one tensor's histograms of weights or gradients over the steps of a run's "
              'training, re-binned onto one grid.', 'inspect', False,
              _arguments(['run', 'name', 'kind'], run=_RUN, name={'type': 'string', 'minLength': 1, 'maxLength': 1000},
                         kind={'type': 'string', 'enum': ['weights', 'gradients']}, most=_limit(500),
                         bins=_limit(128)), TRAINING_HISTOGRAMS),
    Operation('training_samples', "List one page of the samples a run's training script kept, optionally of one "
              'name.', 'inspect', False,
              _arguments(['run'], run=_RUN, name={'type': 'string', 'minLength': 1, 'maxLength': 200},
                         offset=_OFFSET, limit=_limit(200)), ('samples', 'total')),
    Operation('training_sample', "Read one sample a run's training script kept: an image's size and address, or an "
              "array's slice as 32-bit floats.", 'inspect', False,
              _arguments(['run', 'index'], run=_RUN, index=_OFFSET), ('sample', 'content')),
    Operation('model_compare', 'Compare two to four recipes: the settings, data and parent that differ, their '
              'metrics on every benchmark that measures them with bootstrap intervals from per-case values, and '
              'where each sits on the frontier of its tradeoff charts.', 'inspect', False,
              _arguments(['recipes'], recipes={'type': 'array', 'items': _REFERENCE, 'minItems': 2,
                                               'maxItems': COMPARED_MOST}, statistic=_STATISTIC),
              ('statistic', 'resamples', 'level', 'seed', 'models', 'differs', 'same', 'more', 'benchmarks')),
    Operation('benchmark_axes', "Read a benchmark's subjects as lines through axes: its metrics and the numeric or "
              'categorical recipe settings that vary between them, the settings that go most with the first metric '
              'first.', 'inspect', False, _arguments(['benchmark'], benchmark=_NAME, statistic=_STATISTIC),
              ('benchmark', 'statistic', 'metrics', 'settings', 'left_out', 'subjects')),
    Operation('intervals', "Read bootstrap intervals of every statistic of a benchmark's subjects from the per-case "
              'values held here, and whether neighbours on the frontier of its tradeoff charts are told apart.',
              'inspect', False, _arguments(['benchmark'], benchmark=_NAME),
              ('benchmark', 'resamples', 'level', 'seed', 'intervals', 'frontiers')),
    Operation('annotation_tasks', 'List the annotation tasks, each with its dataset, current product and counts of '
              'its records by the state of their annotations.', 'inspect', False, _arguments(), ('tasks',)),
    Operation('annotated_records', "Read one page of the records of a task's dataset with their annotations, "
              'optionally in one state or of one kind, with the counts.', 'inspect', False,
              _arguments(['task'], task=_NAME, state={'type': 'string', 'enum': list(ANNOTATION_COUNTS)},
                         kind={'type': 'string', 'enum': list(RECORD_KINDS)}, offset=_OFFSET, limit=_limit(200)),
              ('task', 'run', 'records', 'total', 'counts')),
    Operation('annotation', "Read one record's annotation under a task as it now is and as it is in the file, "
              "whether it is unsaved or stale, and the hash of the record's content.", 'inspect', False,
              _arguments(['task', 'record'], task=_NAME, record=_RECORD_ID),
              ('task', 'record', 'annotation', 'saved', 'unsaved', 'stale', 'sha256')),
    Operation('set_annotation', "Check annotations of a task's records, or their removal, and keep them as unsaved "
              'edits; one item that does not check refuses them all.', 'edit', True,
              _arguments(['task', 'items'], task=_NAME,
                         items={'type': 'array', 'minItems': 1, 'maxItems': ANNOTATION_ITEMS,
                                'items': {'oneOf': [_SET_ITEM, _REMOVE_ITEM]}},
                         **{'from': {'type': 'object'}}),
              ('task', 'set', 'removed', 'unsaved')),
    Operation('revert_annotations', "Put back the saved annotations of a task's named records, or of all its "
              'records, in place of their unsaved edits.', 'edit', True,
              _arguments(['task'], task=_NAME,
                         records={'type': 'array', 'items': _RECORD_ID, 'minItems': 1, 'maxItems': REVERT_RECORDS}),
              ('task', 'reverted')),
    Operation('suggestion_models', "List, for each kind of record in the product of a task's dataset, the models "
              'the Pumas endpoint serves that can suggest a value of the task.', 'inspect', False,
              _arguments(['task'], task=_NAME), ('task', 'type', 'address', 'kinds', 'problem')),
    Operation('suggest_annotation', 'Ask a model the Pumas endpoint serves for a value of a task for one record; '
              'nothing is stored, and an answer that is not a value of the task is refused.', 'edit', False,
              _arguments(['task', 'record', 'model'], task=_NAME, record=_RECORD_ID,
                         model={'type': 'string', 'minLength': 1, 'maxLength': 256},
                         profile={'type': 'string', 'minLength': 1, 'maxLength': 128},
                         instruction={'type': 'string', 'minLength': 1, 'maxLength': INSTRUCTION_CHARACTERS}),
              ('task', 'record', 'suggestion')),
    Operation('set_definition', "Check a definition's text and keep it as an unsaved edit.", 'edit', True,
              _arguments(['reference', 'text'], reference=_REFERENCE, text=_TEXT), DEFINITION),
    Operation('remove_definition', 'Mark a definition that nothing uses as removed, until the project is saved.',
              'edit', True, _arguments(['reference'], reference=_REFERENCE), ('removed',)),
    Operation('revert_definition', 'Put back the file in the folder in place of a definition\'s unsaved edit or '
              'removal, or drop a definition the folder has no file for.', 'edit', True,
              _arguments(['reference'], reference=_REFERENCE), ('reference', 'dropped')),
    Operation('save', 'Write the unsaved edits and changed results files to the project folder.', 'edit', True,
              _arguments(), SAVE),
    Operation('resolve_conflict', 'Open a project whose files changed on disk where it has unsaved edits, keeping '
              'or discarding those edits.', 'edit', True,
              _arguments(['choice'], choice={'type': 'string', 'enum': ['keep', 'discard']}), SUMMARY),
    Operation('import_values', "Import one per-case values file, replacing that subject's values and summaries.",
              'edit', True, _arguments(['text'], text=_TEXT), ('benchmark', 'subject', 'values')),
    Operation('check_environment', "Check an environment's recorded interpreter against its definition and keep "
              'the result.', 'edit', True, _arguments(['reference'], reference=_REFERENCE), ENVIRONMENT),
    Operation('connect_environment', 'Record an existing interpreter for an environment on this machine and check '
              'it.', 'owner', True,
              _arguments(['reference', 'interpreter'], reference=_REFERENCE,
                         interpreter={'type': 'string', 'minLength': 1, 'maxLength': 4096}), ENVIRONMENT),
    Operation('disconnect_environment', "Forget an environment's recorded interpreter on this machine; nothing is "
              'deleted.', 'owner', True, _arguments(['reference'], reference=_REFERENCE), ('disconnected',)),
    Operation('endpoint', 'Read the Pumas endpoint this machine uses: its address, whether it answered, and each '
              'model and profile it serves with its modalities, its capabilities and what Tuldok can make with it.',
              'inspect', False, _arguments(), ENDPOINT),
    Operation('set_endpoint', 'Set the Pumas endpoint this machine uses once it has answered what it serves, or '
              'clear it with null.', 'owner', True,
              _arguments(['address'], address={'type': ['string', 'null'], 'minLength': 1,
                                               'maxLength': ENDPOINT_CHARACTERS}), ENDPOINT),
    Operation('find_endpoints', 'List the Pumas endpoints advertising themselves on this machine, for the owner to '
              'pick from.', 'owner', False, _arguments(), ('endpoints', 'rejected')),
    Operation('request_build', "Ask for a build of the targets: the owner's request is queued, an agent's waits for "
              "the owner's approval (read build_request for its state), and a queued request not started by "
              'its expires_at expires.', 'request', True,
              _arguments(['targets'], targets=_TARGETS, every=_FLAG, scratch=_FLAG), REQUEST),
    Operation('approve_build', 'Approve a build request awaiting approval, if what it covers is unchanged.', 'owner',
              True, _arguments(['request'], request=_REQUEST), REQUEST),
    Operation('decline_build', 'Decline a build request awaiting approval, with a reason.', 'owner', True,
              _arguments(['request'], request=_REQUEST,
                         reason={'type': 'string', 'maxLength': REASON_CHARACTERS}), REQUEST),
    Operation('cancel_build', 'Cancel a build request, stopping its build when it is running.', 'cancel', True,
              _arguments(['request'], request=_REQUEST), REQUEST),
    Operation('cancel_run', 'Ask a queued or running run to stop.', 'cancel', True, _arguments(['run'], run=_RUN),
              CANCEL_RUN),
    Operation('stop_run', 'Kill what a run whose build is gone left running, and mark it unknown.', 'cancel', True,
              _arguments(['run'], run=_RUN), STOP_RUN),
)

_BY_NAME = {operation.name: operation for operation in OPERATIONS}


def by_name(name):
    """The Operation called name (without the project. prefix), or None when there is none."""
    return _BY_NAME.get(name)


def error_status(code):
    """The HTTP status of a refusal with this ProjectError code."""
    return {'not-found': 404, 'invalid': 400, 'forbidden': 403}.get(code, 409)
