"""Benchmark results in the database: per-case values files, summary rows and their tables.

Owns sections 1 to 4 of docs/plans/definition-first-projects/spec-m3.md: the
check of a tuldok_results_v1 values file against its benchmark, the three
results tables of a project schema, and the SQL that fills and reads them.
Summaries are computed in Python with results.summarise, never in SQL, so the
numbers are exactly the ones the lab's build script writes; floats travel as
Python floats into double precision columns and back. A subject's summaries
come from its values when the database holds values for it (origin 'values'),
otherwise from results/<benchmark>.csv (origin 'file'). store.py calls these
functions inside its own transactions; nothing here reads a file.
"""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math

from psycopg import sql

from . import documents, results
from .documents import Problem

FORMAT = 'tuldok_results_v1'
VALUES_LIMIT = 64 * 1024 * 1024
ORIGINS = ('file', 'values')

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.results_files (
           benchmark text PRIMARY KEY,
           file_sha256 text NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS {schema}.result_summaries (
           benchmark text NOT NULL, subject text NOT NULL, metric text NOT NULL, grp text NOT NULL,
           count integer NOT NULL, unavailable integer NOT NULL,
           mean double precision, median double precision, p10 double precision,
           p90 double precision, min double precision, max double precision,
           commit text NOT NULL, produced text NOT NULL,
           origin text NOT NULL CHECK (origin IN ('file', 'values')),
           PRIMARY KEY (benchmark, subject, metric, grp))''',
    '''CREATE TABLE IF NOT EXISTS {schema}.result_values (
           benchmark text NOT NULL, subject text NOT NULL, case_id text NOT NULL,
           metric text NOT NULL, grp text NOT NULL,
           value double precision, reason text,
           PRIMARY KEY (benchmark, subject, case_id, metric, grp))''',
    'CREATE INDEX IF NOT EXISTS result_values_lookup ON {schema}.result_values (benchmark, metric, subject)',
)

_SUMMARY_COLUMNS = ('subject', 'metric', 'grp', 'count', 'unavailable', *results.STATISTICS, 'commit', 'produced')
_INSERT_SUMMARY = ('INSERT INTO {schema}.result_summaries (benchmark, ' + ', '.join(_SUMMARY_COLUMNS)
                   + ', origin) VALUES (' + ', '.join(['%s'] * (len(_SUMMARY_COLUMNS) + 2)) + ')')
_SELECT_SUMMARY = 'SELECT ' + ', '.join(_SUMMARY_COLUMNS) + ', origin FROM {schema}.result_summaries'
_ORDER = ' ORDER BY subject COLLATE "C", metric COLLATE "C", grp COLLATE "C"'

_TOP_FIELDS = ('format', 'benchmark', 'subject', 'commit', 'produced', 'values')
_VALUE_FIELDS = ('case', 'metric', 'value', 'reason', 'group')


@dataclass(frozen=True)
class Value:
    """One per-case value: value is a float, or None with a reason; group is 'k=v;k=v' with keys sorted."""
    case: str
    metric: str
    group: str
    value: float | None
    reason: str | None
    pairs: tuple = ()     # the group as ((key, text), ...), keys sorted


@dataclass(frozen=True)
class ValuesFile:
    """A values file that passed check_values."""
    benchmark: str
    subject: str
    commit: str
    produced: str
    values: tuple


@dataclass(frozen=True)
class StoredSummary:
    """One row of result_summaries: the results.SummaryRow and where it came from ('file' or 'values')."""
    row: results.SummaryRow
    origin: str


def _q(schema, template):
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ------------------------------------------------------ the values file (1)

def _group_text(value):
    """The stored text of a group value (strings as they are, true/false, numbers by repr), or None if not allowed."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return value
    return None


def _number(value):
    """value as a finite float, or None when it is not a finite number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def check_values(text, find_benchmark, *, path=''):
    """Check a values file; return (ValuesFile or None, [Problem]).

    text is the file's bytes or str. find_benchmark(name) returns that
    benchmark's decoded definition, or None when the project has none. Every
    problem is an error; the ValuesFile is returned only when there is none.
    """
    problems = []

    def add(pointer, message):
        problems.append(Problem('error', path, pointer, message))

    size = len(text) if isinstance(text, (bytes, bytearray)) else len(text.encode('utf-8'))
    if size > VALUES_LIMIT:
        add('', f'The file is {size} bytes; a values file is at most {VALUES_LIMIT} bytes.')
        return None, problems
    try:
        document = documents.decode(text)
    except documents.DocumentError as exc:
        add('', str(exc))
        return None, problems

    for key in sorted(set(document) - set(_TOP_FIELDS)):
        add(documents.pointer(key), f'The field {key!r} is not part of a values file; remove it.')
    for key in _TOP_FIELDS:
        if key not in document:
            add('', f'The field {key!r} is required.')
    if 'format' in document and document['format'] != FORMAT:
        add('/format', f'The format must be exactly {FORMAT}.')
    commit, produced = document.get('commit'), document.get('produced')
    if 'commit' in document and not (isinstance(commit, str) and (commit == '' or results._COMMIT.fullmatch(commit))):
        add('/commit', 'The commit must be 40 lowercase hexadecimal characters or empty.')
    if 'produced' in document and not (isinstance(produced, str) and results._produced_is_valid(produced)):
        add('/produced', 'The produced date must be YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ.')

    benchmark_name, subject = document.get('benchmark'), document.get('subject')
    benchmark = None
    if 'benchmark' in document:
        benchmark = find_benchmark(benchmark_name) if documents.is_name(benchmark_name) else None
        if benchmark is None:
            add('/benchmark', f'There is no benchmark {benchmark_name!r} in this project.')
    subjects, metrics, group_by, _ = results._benchmark_names(benchmark)
    if benchmark is not None and 'subject' in document and subject not in subjects:
        add('/subject', f'{subject!r} is not a subject of benchmarks/{benchmark_name}.')

    rows = document.get('values')
    if 'values' in document and not isinstance(rows, list):
        add('/values', 'The values must be a list.')
        rows = []
    elif 'values' in document and not rows:
        add('/values', 'The values list is empty; a values file holds at least one value.')
    values, seen = [], set()
    for index, row in enumerate(rows or []):
        found, found_problems = _check_value(row, index, metrics, group_by, benchmark is not None)
        for pointer, message in found_problems:
            add(pointer, message)
        if found is None:
            continue
        key = (found.case, found.metric, found.group)
        if key in seen:
            add(documents.pointer('values', index), 'This (case, metric, group) appears earlier in the file.')
        seen.add(key)
        values.append(found)
    if problems:
        return None, problems
    return ValuesFile(benchmark_name, subject, commit, produced, tuple(values)), problems


def _check_value(row, index, metrics, group_by, known):
    """Check one entry of values[]; return (Value or None, [(pointer, message)])."""
    problems = []
    here = ('values', index)

    def add(*parts_and_message):
        *parts, message = parts_and_message
        problems.append((documents.pointer(*here, *parts), message))

    if not isinstance(row, dict):
        add('Each value must be an object.')
        return None, problems
    for key in sorted(set(row) - set(_VALUE_FIELDS)):
        add(key, f'The field {key!r} is not part of a value; remove it.')
    case = row.get('case')
    if not (isinstance(case, str) and 1 <= len(case) <= 200):
        add('case', 'The case must be a string of 1 to 200 characters.')
    metric = row.get('metric')
    if not isinstance(metric, str) or (known and metric not in metrics):
        add('metric', f'The metric {metric!r} is not a metric id of the benchmark.')
    value = None
    if 'value' not in row:
        add("The field 'value' is required: a number, or null with a reason.")
    elif row['value'] is not None:
        value = _number(row['value'])
        if value is None:
            add('value', 'The value must be a finite number, or null.')
    reason = row.get('reason')
    if 'value' in row and row['value'] is None:
        if not (isinstance(reason, str) and 1 <= len(reason) <= 400):
            add('reason', 'A null value needs a reason of 1 to 400 characters.')
    elif 'reason' in row:
        add('reason', 'A reason is allowed only when the value is null.')
    group = row.get('group', {})
    pairs = []
    if not isinstance(group, dict):
        add('group', 'The group must be an object.')
        group = {}
    for key in sorted(group):
        if known and key not in group_by:
            add('group', key, f"The group key {key!r} is not in the benchmark's summary.group_by.")
        text = _group_text(group[key])
        if text is None:
            add('group', key, 'A group value must be a string, a number or a boolean.')
        elif any(mark in text for mark in ';=\r\n'):
            add('group', key, 'A group value may not contain ";", "=" or a line break.')
        else:
            pairs.append((key, text))
    if problems:
        return None, problems
    return Value(case, metric, ';'.join(f'{key}={text}' for key, text in pairs),
                 value, None if value is not None else reason, tuple(pairs)), problems


# ------------------------------------------------------------ summaries (3)

def summaries_from_values(values_file):
    """The SummaryRow items of one values file: per metric, the ungrouped row and one per single key=value."""
    measured, missing = defaultdict(list), defaultdict(int)
    for item in values_file.values:
        for group in ('', *(f'{key}={text}' for key, text in item.pairs)):
            measured[item.metric, group]  # every set gets a row, even with nothing measured
            if item.value is None:
                missing[item.metric, group] += 1
            else:
                measured[item.metric, group].append(item.value)
    return [results.SummaryRow(subject=values_file.subject, metric=metric, group=group,
                               commit=values_file.commit, produced=values_file.produced,
                               **results.summarise(measured[metric, group], missing[metric, group]))
            for metric, group in sorted(measured)]


def _fits(row, subjects, metrics, group_by):
    """True when a summary row still belongs to the benchmark: known subject and metric, group keys in group_by."""
    if row.subject not in subjects or row.metric not in metrics:
        return False
    return row.group == '' or all(pair.partition('=')[0] in group_by for pair in row.group.split(';'))


def _summary_parameters(benchmark, row, origin):
    return (benchmark, row.subject, row.metric, row.group, row.count, row.unavailable,
            *(None if getattr(row, name) is None else float(getattr(row, name)) for name in results.STATISTICS),
            row.commit, row.produced, origin)


def subjects_with_values(connection, schema, benchmark):
    return {subject for (subject,) in connection.execute(
        _q(schema, 'SELECT DISTINCT subject FROM {schema}.result_values WHERE benchmark = %s'), (benchmark,))}


def import_file(connection, schema, benchmark, text, document):
    """Replace the benchmark's origin-'file' summaries with the rows of its results file and record its digest.

    Subjects with values in the database keep their 'values' summaries; rows
    that no longer fit the benchmark document (an unsaved edit) are left out.
    """
    subjects, metrics, group_by, _ = results._benchmark_names(document)
    keep = subjects_with_values(connection, schema, benchmark)
    rows = [row for row in results.read_results(text)
            if row.subject not in keep and _fits(row, subjects, metrics, group_by)]
    connection.execute(_q(schema, "DELETE FROM {schema}.result_summaries WHERE benchmark = %s AND origin = 'file'"),
                       (benchmark,))
    if rows:
        with connection.cursor() as cursor:
            cursor.executemany(_q(schema, _INSERT_SUMMARY), [_summary_parameters(benchmark, row, 'file') for row in rows])
    record_file(connection, schema, benchmark, sha256_text(text))


def forget_file(connection, schema, benchmark):
    """The results file is gone: drop its origin-'file' summaries and its digest."""
    connection.execute(_q(schema, "DELETE FROM {schema}.result_summaries WHERE benchmark = %s AND origin = 'file'"),
                       (benchmark,))
    connection.execute(_q(schema, 'DELETE FROM {schema}.results_files WHERE benchmark = %s'), (benchmark,))


def record_file(connection, schema, benchmark, sha):
    connection.execute(_q(schema, '''INSERT INTO {schema}.results_files (benchmark, file_sha256) VALUES (%s, %s)
                                     ON CONFLICT (benchmark) DO UPDATE SET file_sha256 = EXCLUDED.file_sha256'''),
                       (benchmark, sha))


def replace_values(connection, schema, values_file):
    """Replace one (benchmark, subject)'s values and summaries; the caller holds the transaction."""
    key = (values_file.benchmark, values_file.subject)
    connection.execute(_q(schema, 'DELETE FROM {schema}.result_values WHERE benchmark = %s AND subject = %s'), key)
    connection.execute(_q(schema, 'DELETE FROM {schema}.result_summaries WHERE benchmark = %s AND subject = %s'), key)
    with connection.cursor() as cursor:
        with cursor.copy(_q(schema, 'COPY {schema}.result_values '
                                    '(benchmark, subject, case_id, metric, grp, value, reason) FROM STDIN')) as copy:
            for item in values_file.values:
                copy.write_row((*key, item.case, item.metric, item.group, item.value, item.reason))
        rows = summaries_from_values(values_file)
        cursor.executemany(_q(schema, _INSERT_SUMMARY),
                           [_summary_parameters(values_file.benchmark, row, 'values') for row in rows])
    return {'benchmark': values_file.benchmark, 'subject': values_file.subject,
            'values': len(values_file.values), 'summaries': len(rows)}


def remove_benchmark(connection, schema, benchmark):
    """Drop a benchmark's summaries and values (its results_files digest stays until save deletes the file)."""
    for table in ('result_summaries', 'result_values'):
        connection.execute(_q(schema, f'DELETE FROM {{schema}}.{table} WHERE benchmark = %s'), (benchmark,))


def prune(connection, schema, benchmark, document):
    """Drop rows that no longer fit the benchmark: unknown subjects or metrics, and summaries of unknown group keys."""
    subjects, metrics, group_by, _ = results._benchmark_names(document)
    subjects, metrics = sorted(subjects), sorted(metrics)
    for table in ('result_summaries', 'result_values'):
        connection.execute(_q(schema, f'DELETE FROM {{schema}}.{table} WHERE benchmark = %s '
                                      'AND (NOT subject = ANY(%s) OR NOT metric = ANY(%s))'),
                           (benchmark, subjects, metrics))
    stale = [(row.subject, row.metric, row.group) for row in (stored.row for stored in summaries(connection, schema, benchmark))
             if not _fits(row, set(subjects), set(metrics), group_by)]
    if stale:
        with connection.cursor() as cursor:
            cursor.executemany(_q(schema, 'DELETE FROM {schema}.result_summaries WHERE benchmark = %s '
                                          'AND subject = %s AND metric = %s AND grp = %s'),
                               [(benchmark, *key) for key in stale])


# --------------------------------------------------------------- reading (4)

def _stored(record):
    *columns, origin = record
    fields = dict(zip(_SUMMARY_COLUMNS, columns))
    fields['group'] = fields.pop('grp')
    return StoredSummary(results.SummaryRow(**fields), origin)


def summaries(connection, schema, benchmark, subject=None, metric=None, group=None):
    """StoredSummary rows of a benchmark, sorted by subject, metric and group.

    group None means every group, '' only the ungrouped rows, and a key the
    rows whose group is that one key (key=value), not combinations.
    """
    where, parameters = ['benchmark = %s'], [benchmark]
    if subject is not None:
        where.append('subject = %s')
        parameters.append(subject)
    if metric is not None:
        where.append('metric = %s')
        parameters.append(metric)
    if group == '':
        where.append("grp = ''")
    elif group is not None:
        where.append("left(grp, length(%s) + 1) = %s || '=' AND strpos(grp, ';') = 0")
        parameters += [group, group]
    query = _SELECT_SUMMARY + ' WHERE ' + ' AND '.join(where) + _ORDER
    return [_stored(record) for record in connection.execute(_q(schema, query), parameters)]


def values(connection, schema, benchmark, subject, metric=None, offset=0, limit=200):
    """{'total', 'values': [{case, metric, group, value, reason}]} for one subject; total 0 when none are held."""
    where, parameters = 'benchmark = %s AND subject = %s', [benchmark, subject]
    if metric is not None:
        where += ' AND metric = %s'
        parameters.append(metric)
    total = connection.execute(_q(schema, f'SELECT count(*) FROM {{schema}}.result_values WHERE {where}'),
                               parameters).fetchone()[0]
    rows = connection.execute(_q(schema, f'''SELECT case_id, metric, grp, value, reason FROM {{schema}}.result_values
                                             WHERE {where} ORDER BY metric COLLATE "C", case_id COLLATE "C", grp COLLATE "C"
                                             OFFSET %s LIMIT %s'''), [*parameters, offset, limit]).fetchall()
    return {'total': total, 'values': [{'case': case, 'metric': row_metric, 'group': grp, 'value': value,
                                        'reason': reason} for case, row_metric, grp, value, reason in rows]}


def file_texts(connection, schema):
    """{benchmark: (text the database's summaries make, or None when it has none; recorded file digest or None)}."""
    grouped = defaultdict(list)
    for record in connection.execute(_q(schema, _SELECT_SUMMARY.replace('SELECT ', 'SELECT benchmark, ', 1))):
        grouped[record[0]].append(_stored(record[1:]).row)
    recorded = dict(connection.execute(_q(schema, 'SELECT benchmark, file_sha256 FROM {schema}.results_files')).fetchall())
    return {benchmark: (results.write_results(grouped[benchmark]) if benchmark in grouped else None,
                        recorded.get(benchmark))
            for benchmark in sorted(set(grouped) | set(recorded))}


def differs(text, recorded):
    """True when what the database holds is not the file as last imported or saved."""
    return (None if text is None else sha256_text(text)) != recorded


def overview(connection, schema):
    """Per benchmark: subjects with results, subjects with values, summary rows per origin, and whether it differs from its file."""
    names = {name for (name,) in connection.execute(
        _q(schema, "SELECT name FROM {schema}.definitions WHERE directory = 'benchmarks' AND NOT removed"))}
    counts = defaultdict(dict)
    for benchmark, subjects, file_rows, value_rows in connection.execute(_q(schema, '''
            SELECT benchmark, count(DISTINCT subject), count(*) FILTER (WHERE origin = 'file'),
                   count(*) FILTER (WHERE origin = 'values')
            FROM {schema}.result_summaries GROUP BY benchmark''')):
        counts[benchmark].update(subjects_with_results=subjects, rows_file=file_rows, rows_values=value_rows)
    for benchmark, subjects in connection.execute(_q(schema, '''
            SELECT benchmark, count(*) FROM (SELECT DISTINCT benchmark, subject FROM {schema}.result_values) AS held
            GROUP BY benchmark''')):
        counts[benchmark]['subjects_with_values'] = subjects
    texts = file_texts(connection, schema)
    found = []
    for benchmark in sorted(names | set(counts) | set(texts)):
        count = counts.get(benchmark, {})
        file_rows, value_rows = count.get('rows_file', 0), count.get('rows_values', 0)
        found.append({'benchmark': benchmark, 'subjects_with_results': count.get('subjects_with_results', 0),
                      'subjects_with_values': count.get('subjects_with_values', 0),
                      'rows': file_rows + value_rows, 'rows_file': file_rows, 'rows_values': value_rows,
                      'differs_from_file': differs(*texts[benchmark]) if benchmark in texts else False})
    return found
