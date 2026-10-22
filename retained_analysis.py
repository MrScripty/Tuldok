"""Inert, exact-result classifier curve and example query.

Runs owns artifact verification. PostgreSQL owns the existing Run facts; this
query creates only disposable projections, never a second retained authority.
No caller-controlled SQL, identifiers, expressions, files or computation.
"""
from contextlib import contextmanager
import json
import math
import re
import time

from psycopg.pq import TransactionStatus

from model_evidence import canonical, digest
from pipeline import closed, identifier
from retained_analysis_schema import QUERY_ID, QUERY_VERSION, FIELDS
from workbench import WorkbenchError

MAX_PAGE = 100
MAX_OFFSET = 10000
MAX_EXAMPLES = 10000
MAX_CHECKPOINTS = 128
MAX_RESPONSE_BYTES = 256 * 1024
MAX_PROJECTION_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
SQL_TIMEOUT_MS = 2000
LOCK_SECONDS = 2
METRICS = ('accuracy', 'loss', 'macro_f1')
HASH = re.compile(r'^[a-f0-9]{64}$')

# The metric name is a bound JSON lookup key, not SQL text. Checkpoint mapping
# comes from the verified retained index, while values come from catalog facts.
CURVE_SQL = '''
WITH checkpoints AS (
    SELECT * FROM jsonb_to_recordset(%s::jsonb)
    AS c(checkpoint_sha256 text, epoch integer)
)
SELECT c.checkpoint_sha256, c.epoch,
       (h->'validation'->>%s)::double precision AS value,
       (h->'validation'->>'examples')::integer AS support
FROM workspace_runs r
CROSS JOIN LATERAL jsonb_array_elements(r.document::jsonb->'metrics'->'history') h
JOIN checkpoints c ON c.epoch=(h->>'epoch')::integer
WHERE r.id=%s
ORDER BY c.epoch
LIMIT %s
'''

# Both readers share the exact curve expression and verification. The historical
# variant supplies bounded origin JSON and cannot insert a runnable Run row.
HISTORY_CURVE_SQL = CURVE_SQL.replace(
    "FROM workspace_runs r\nCROSS JOIN LATERAL jsonb_array_elements(r.document::jsonb->'metrics'->'history') h",
    "FROM jsonb_array_elements(%s::jsonb->'metrics'->'history') h").replace('WHERE r.id=%s\n','')

# Only bounded scalar rows enter this projection. Large probability arrays and
# all original hash-bound bytes stay in managed evidence artifacts.
EXAMPLES_SQL = '''
WITH examples AS (
    SELECT * FROM jsonb_to_recordset(%s::jsonb)
    AS e(ordinal integer, example_id text, truth_index integer,
         predicted_index integer, confidence double precision, error boolean,
         frozen_reference jsonb)
), filtered AS (
    SELECT * FROM examples WHERE (NOT %s OR error)
), page AS (
    SELECT * FROM filtered ORDER BY ordinal LIMIT %s OFFSET %s
)
SELECT (SELECT count(*) FROM filtered) AS filtered_support,
       coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.ordinal) FROM page p), '[]'::jsonb) AS rows
'''


def validate_request(body):
    """Decode a complete closed variant before any evidence or catalog read."""
    closed(body, ('query_id', 'query_version', 'run_id', 'evaluation_sha256',
                  'checkpoint_sha256', 'metric_id', 'metric_definition_sha256'),
           ('fields', 'errors_only', 'limit', 'offset'))
    if (body['query_id'] != QUERY_ID or type(body['query_version']) is not int
            or body['query_version'] != QUERY_VERSION):
        raise WorkbenchError('Unsupported retained analysis query.', 'unsupported', 409)
    identifier(body['run_id'], 'Run ID')
    for key in ('evaluation_sha256', 'checkpoint_sha256', 'metric_definition_sha256'):
        if type(body[key]) is not str or not HASH.fullmatch(body[key]):
            raise WorkbenchError('Retained analysis requires exact SHA256 identities.')
    if type(body['metric_id']) is not str or body['metric_id'] not in METRICS:
        raise WorkbenchError('Choose a declared validation metric.')
    fields = body.get('fields', list(FIELDS))
    if (type(fields) is not list or not fields or len(fields) > len(FIELDS)
            or any(type(field) is not str or field not in FIELDS for field in fields)
            or len(set(fields)) != len(fields) or 'example_id' not in fields):
        raise WorkbenchError('Choose unique declared fields including example_id.')
    limit, offset = body.get('limit', 50), body.get('offset', 0)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise WorkbenchError('Retained analysis page limit must be 1–100.')
    if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise WorkbenchError('Retained analysis offset must be 0–10000.')
    errors_only = body.get('errors_only', False)
    if type(errors_only) is not bool:
        raise WorkbenchError('errors_only must be a boolean.')
    return dict(body, fields=list(fields), limit=limit, offset=offset, errors_only=errors_only)


def _refuse(message, code='invalid', status=409):
    raise WorkbenchError(message, code, status)


@contextmanager
def _read_snapshot(db):
    with db.connection.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        db.execute("SELECT set_config('statement_timeout', %s, true)", (str(SQL_TIMEOUT_MS),))
        db.execute("SELECT set_config('lock_timeout', %s, true)", (str(SQL_TIMEOUT_MS),))
        yield


def _retained_run(db, request):
    # Refuse a stale result before the expensive existing artifact verifier.
    # Repeat this check inside the SQL snapshot to close the intervening gap.
    stored = db.execute('''SELECT CASE WHEN octet_length(document)<=%s THEN document ELSE NULL END AS document
                           FROM workspace_runs WHERE id=%s''',
                        (MAX_DOCUMENT_BYTES, request['run_id'])).fetchone()
    if stored is None:
        _refuse('Retained Run is unavailable.', 'not_found', 404)
    if stored['document'] is None:
        _refuse('Retained Run document exceeds this query budget.', 'limit', 413)
    try:
        run = json.loads(stored['document'])
    except (ValueError, TypeError):
        _refuse('Retained Run envelope is unavailable.', 'unavailable', 409)
    return validate_run_selection(run, request)


def validate_run_selection(run, request):
    """Exact saved result selection shared by live and inert readers."""
    try:
        artifact = [item for item in run['artifacts'] if item['name'] == 'model-evidence.json']
        state, run_id = run['state'], run['id']
        actual_hash = artifact[0]['sha256'] if len(artifact) == 1 else None
    except (ValueError, KeyError, TypeError):
        _refuse('Retained Run envelope is unavailable.', 'unavailable', 409)
    if actual_hash != request['evaluation_sha256']:
        _refuse('Retained evaluation snapshot differs.', 'stale')
    if state != 'completed' or run_id != request['run_id']:
        _refuse('Retained analysis requires a completed Run.', 'unavailable', 503)
    return run


def _projection(evidence, request):
    """Project the native verified variant; other task owners remain explicit."""
    if (evidence.get('state') != 'verified'
            or evidence.get('manifest', {}).get('format') != 'model_evidence_v1'):
        _refuse('Retained analysis requires verified native classifier evidence.', 'unsupported')
    definitions = [item for item in evidence['metric_definitions'] if item['id'] == request['metric_id']]
    if len(definitions) != 1 or digest(definitions[0]) != request['metric_definition_sha256']:
        _refuse('Retained analysis metric definition differs.', 'stale')
    definition = definitions[0]
    if definition['split'] != 'validation':
        _refuse('Retained analysis only supports frozen validation.', 'unsupported')
    entries = evidence['checkpoint_index']['entries']
    if not 1 <= len(entries) <= MAX_CHECKPOINTS:
        _refuse('Retained checkpoint count exceeds this query budget.', 'limit', 413)
    checkpoints = [{'checkpoint_sha256': item['checkpoint']['sha256'], 'epoch': item['clocks']['epoch']}
                   for item in entries]
    if any(type(item['epoch']) is not int or item['epoch'] < 1 for item in checkpoints):
        _refuse('Retained analysis requires epoch-based classifier evidence.', 'unsupported')
    if request['checkpoint_sha256'] not in {item['checkpoint_sha256'] for item in checkpoints}:
        _refuse('Checkpoint does not belong to this result.', 'not_found', 404)
    predictions = evidence['predictions']
    if (predictions is None or predictions['checkpoint_sha256'] != request['checkpoint_sha256']
            or predictions['probe_sha256'] != evidence['manifest']['probe']['sha256']):
        _refuse('Selected checkpoint predictions differ.', 'stale')
    members = evidence['probe']['members']
    if len(members) > MAX_EXAMPLES:
        _refuse('Frozen example population exceeds this query budget.', 'limit', 413)
    by_ordinal = {member['ordinal']: member for member in members}
    if len(by_ordinal) != len(members) or len(predictions['rows']) != len(members):
        _refuse('Frozen example membership differs.')
    rows = []
    seen = set()
    for row in predictions['rows']:
        ordinal = row['ordinal']
        if ordinal not in by_ordinal or ordinal in seen:
            _refuse('Frozen example ordinal differs.')
        seen.add(ordinal)
        frozen = by_ordinal[ordinal]['frozen_reference']
        confidence = row['probabilities'][row['predicted_index']]
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            _refuse('Frozen prediction confidence differs.')
        rows.append({'ordinal': ordinal, 'example_id': frozen['id'], 'frozen_reference': frozen,
                     'truth_index': row['truth_index'], 'predicted_index': row['predicted_index'],
                     'confidence': confidence, 'error': row['truth_index'] != row['predicted_index']})
    if len({row['example_id'] for row in rows}) != len(rows):
        _refuse('Frozen example IDs are ambiguous.')
    raw = canonical(rows)
    if len(raw) > MAX_PROJECTION_BYTES:
        _refuse('Frozen scalar projection exceeds this query budget.', 'limit', 413)
    return definition, checkpoints, raw.decode('ascii')


def _query_result(db, run, evidence, request, *, catalog_id, historical=False):
    validate_run_selection(run, request)
    run_id = run['id']
    definition, checkpoints, example_json = _projection(evidence, request)
    curve_sql = HISTORY_CURVE_SQL if historical else CURVE_SQL
    source = json.dumps(run,allow_nan=False) if historical else run_id
    curve = [dict(row) for row in db.execute(curve_sql,
        (canonical(checkpoints).decode('ascii'), request['metric_id'], source, MAX_CHECKPOINTS + 1))]
    expected = {item['checkpoint_sha256']: item for item in evidence['observations']
                if item['metric_id'] == request['metric_id'] and item['split'] == 'validation'}
    if len(curve) != len(checkpoints):
        _refuse('Catalog curve coverage differs from retained checkpoints.')
    for point in curve:
        observation = expected.get(point['checkpoint_sha256'])
        if (observation is None or observation['state'] != 'observed'
                or point['epoch'] != observation['clocks']['epoch']
                or point['value'] != observation['value'] or point['support'] != observation['sample_count']):
            _refuse('Catalog curve differs from retained metric observations.')
    page = db.execute(EXAMPLES_SQL, (example_json, request['errors_only'],
                                    request['limit'], request['offset'])).fetchone()
    selected_rows = [{key: row[key] for key in (*request['fields'], 'ordinal', 'frozen_reference')}
                     for row in page['rows']]
    provenance = {'catalog_id': catalog_id, 'run_id': run_id,
                  'evaluation_sha256': request['evaluation_sha256'],
                  'checkpoint_sha256': request['checkpoint_sha256'],
                  'metric_definition_sha256': request['metric_definition_sha256'],
                  'population_sha256': definition['population_sha256'],
                  'probe_sha256': evidence['manifest']['probe']['sha256'],
                  'data_sha256': evidence['manifest']['data_sha256'],
                  'producer': evidence['manifest']['producer']}
    count = page['filtered_support']
    result = {'state': 'verified', 'query_id': QUERY_ID, 'query_version': QUERY_VERSION,
              'mode': 'frozen', 'provenance': provenance,
              'metric': {'id': definition['id'], 'units': definition['units'],
                         'definition': definition, 'support': len(evidence['probe']['members'])},
              'curve': curve, 'columns': _columns(request['fields']),
              'examples': {'rows': selected_rows, 'population_support': len(evidence['probe']['members']),
                           'filtered_support': count, 'offset': request['offset'], 'limit': request['limit'],
                           'next_offset': request['offset'] + len(selected_rows)
                           if request['offset'] + len(selected_rows) < count else None,
                           'filters': {'errors_only': request['errors_only']}},
              'sampling': {'method': 'none', 'population': 'frozen_validation_probe'},
              'selection_sha256': digest(request)}
    if len(canonical(result)) > MAX_RESPONSE_BYTES:
        _refuse('Retained analysis response exceeds this query budget.', 'limit', 413)
    return result


def query(runs, body, *, export=False):
    """Current authorization surrounds exact retained reads and SQL projection."""
    request = validate_request(body)
    if type(export) is not bool:
        raise TypeError('export must be a host-owned boolean')
    action = 'runs.export_retained_analysis' if export else 'runs.retained_analysis'
    run_id = request['run_id']
    db = runs.db
    with db.lock.bounded(time.monotonic() + LOCK_SECONDS):
        runs.access.require('inspect', action, run_id)
        if db.connection.info.transaction_status != TransactionStatus.IDLE:
            _refuse('Retained analysis requires a standalone read.', 'unavailable', 503)
        with _read_snapshot(db):
            _retained_run(db, request)
        evidence = runs.model_evidence(run_id, {'checkpoint_sha256': request['checkpoint_sha256']},
                                       contract_version=1)
        with _read_snapshot(db):
            run = _retained_run(db, request)
            result = _query_result(db, run, evidence, request, catalog_id=db.dataset_id)
        runs.access.require('inspect', action, run_id)
        return result


def query_history(db, run, evidence, body, *, authorize, export=False):
    """Query supplied immutable origin facts without an active workspace_runs row."""
    request = validate_request(body)
    if type(export) is not bool:
        raise TypeError('export must be a host-owned boolean')
    action = 'runs.export_retained_analysis' if export else 'runs.retained_analysis'
    authorize('inspect', action, run['id'])
    with db.lock.bounded(time.monotonic() + LOCK_SECONDS):
        if db.connection.info.transaction_status != TransactionStatus.IDLE:
            _refuse('Retained analysis requires a standalone read.', 'unavailable', 503)
        with _read_snapshot(db):
            result = _query_result(db, run, evidence, request, catalog_id=run['dataset_id'],historical=True)
    authorize('inspect', action, run['id'])
    return result


def _columns(fields):
    types = {'example_id': 'string', 'truth_index': 'integer', 'predicted_index': 'integer',
             'confidence': 'number', 'error': 'boolean'}
    return [{'field': field, 'type': types[field],
             'units': 'dimensionless' if field == 'confidence' else None} for field in fields]
