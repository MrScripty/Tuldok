"""The working copy of annotations in the database: its tables and the SQL that fills, reads and saves them.

Owns the database side of sections 3 and 4 of
docs/plans/definition-first-projects/spec-d4.md. Three tables of a project
schema: annotation_files (the line files known: a task's file digest, size
and time in nanoseconds as last imported or saved, so that size and time are
compared before a file is hashed), annotations (one row per task and record:
the line's fields as they now are, the line as it is in the file or NULL,
and whether the row is unsaved; a row whose state is NULL holds no annotation
here, and stands for a line of the file removed and not yet saved), and
record_hashes (the SHA-256 of a record's content per run and record, NULL for
a record over the bound). A row also keeps the fingerprint of the task it was
last checked against and whether its value fitted, so that counting the
values a task no longer allows reads no value until the task changes.
store.py calls these functions inside its own transactions, and the service
through an open project; nothing here reads a file or a product.
"""
from dataclasses import dataclass, field
import time
import hashlib
import json

from psycopg import sql
from psycopg.types.json import Json, Jsonb

from . import annotations, documents, folder as folder_reader

DIRECTORY = folder_reader.ANNOTATIONS

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.annotation_files (
           task text PRIMARY KEY, sha256 text NOT NULL,
           size bigint NOT NULL, mtime_ns bigint NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS {schema}.annotations (
           task text NOT NULL, record text NOT NULL,
           sha256 text,
           state text CHECK (state IN ('draft', 'accepted', 'needs-work', 'rejected')),
           value jsonb, note text, "by" text, "at" text, origin json,
           saved text, unsaved boolean NOT NULL DEFAULT false,
           checked text, valid boolean NOT NULL DEFAULT true,
           PRIMARY KEY (task, record))''',
    'CREATE INDEX IF NOT EXISTS annotations_state ON {schema}.annotations (task, state)',
    'CREATE INDEX IF NOT EXISTS annotations_unsaved ON {schema}.annotations (task) WHERE unsaved',
    '''CREATE TABLE IF NOT EXISTS {schema}.record_hashes (
           run_id text NOT NULL, record text NOT NULL, sha256 text,
           PRIMARY KEY (run_id, record))''',
)

_LINE_COLUMNS = 'record, sha256, state, value, note, "by", "at", origin'
_COPY_COLUMNS = ('task', 'record', 'sha256', 'state', 'value', 'note', 'by', 'at', 'origin', 'saved', 'unsaved',
                 'checked', 'valid')


def _q(schema, template):
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def path(name):
    """The line file of task name, relative to the folder."""
    return f'{DIRECTORY}/{name}{folder_reader.LINES_SUFFIX}'


def reference(name):
    return documents.reference(DIRECTORY, name)


def fingerprint(document):
    """What of a task decides whether a value fits it: its task and vocabulary, as one digest."""
    if not isinstance(document, dict):
        return None
    shown = json.dumps([document.get('task'), document.get('vocabulary') or []], ensure_ascii=False,
                       separators=(',', ':'))
    return hashlib.sha256(shown.encode('utf-8', 'surrogatepass')).hexdigest()


def fits(document, row):
    """Whether a row's value is one the task document allows (the record's kind is not judged here)."""
    errors, unknown = annotations.value_problems(document.get('task'), document.get('vocabulary') or [],
                                                 row.get('state'), row.get('value'))
    return not errors and not unknown


def has_nul(value):
    """Whether any string in value holds U+0000, which a Postgres text or jsonb cannot keep."""
    if isinstance(value, str):
        return '\x00' in value
    if isinstance(value, list):
        return any(has_nul(item) for item in value)
    if isinstance(value, dict):
        return any(has_nul(key) or has_nul(item) for key, item in value.items())
    return False


def line_of(record, sha256, state, value, note, by, at, origin):
    """The row (annotations.KEYS) of one annotation from its columns; note and from only when present."""
    row = {'record': record, 'sha256': sha256, 'state': state, 'value': value}
    if note is not None:
        row['note'] = note
    row['by'], row['at'] = by, at
    if origin is not None:
        row['from'] = origin
    return row


def _columns(row):
    """The columns sha256 to origin of a row, adapted for psycopg."""
    value = row.get('value')
    origin = row.get('from')
    return (row.get('sha256'), row['state'], None if value is None else Jsonb(value), row.get('note'),
            row['by'], row['at'], None if origin is None else Json(origin))


# ------------------------------------------------------------------- files

def recorded_files(connection, schema):
    """{task name: (sha256, size, mtime_ns)} of the line files as last imported or saved."""
    return {name: (sha, size, mtime) for name, sha, size, mtime in connection.execute(
        _q(schema, 'SELECT task, sha256, size, mtime_ns FROM {schema}.annotation_files'))}


# A file's size and time are trusted to say it is unchanged only when its time was already old when it was
# looked at. One written a moment ago can be written again within the same tick of the clock, to the same size,
# and would look untouched (the "racy" case Git guards against the same way). Its time is recorded as UNSETTLED,
# which equals no real time, so it is read and hashed again until it is seen settled.
SETTLED_NS = 2_000_000_000
UNSETTLED = -1


def record_file(connection, schema, name, sha256, size, mtime_ns):
    if time.time_ns() - mtime_ns < SETTLED_NS:
        mtime_ns = UNSETTLED
    connection.execute(_q(schema, '''INSERT INTO {schema}.annotation_files (task, sha256, size, mtime_ns)
                                     VALUES (%s, %s, %s, %s)
                                     ON CONFLICT (task) DO UPDATE SET sha256 = EXCLUDED.sha256,
                                         size = EXCLUDED.size, mtime_ns = EXCLUDED.mtime_ns'''),
                       (name, sha256, size, mtime_ns))


def forget_file(connection, schema, name):
    connection.execute(_q(schema, 'DELETE FROM {schema}.annotation_files WHERE task = %s'), (name,))


def forget_task(connection, schema, name):
    """Drop every row of a task and its line file's record (a task that is gone)."""
    connection.execute(_q(schema, 'DELETE FROM {schema}.annotations WHERE task = %s'), (name,))
    forget_file(connection, schema, name)


# ------------------------------------------------------------------ import

@dataclass
class Comparison:
    """How a line file read from disk differs from a task's rows.

    take: records whose row becomes the file's line (or goes, when the file
    has none); contested: records whose saved line the file changes while
    they have an unsaved edit here, each with the file's line or None.
    """
    take: list = field(default_factory=list)
    contested: list = field(default_factory=list)


def compare(connection, schema, name, lines):
    """Compare lines ({record: (line text, row)}, or None for a file that is gone) with the task's rows."""
    lines = lines or {}
    found = Comparison()
    held = {}
    for record, saved, unsaved in connection.execute(
            _q(schema, 'SELECT record, saved, unsaved FROM {schema}.annotations WHERE task = %s'), (name,)):
        held[record] = (saved, unsaved)
    for record in sorted(set(held) | set(lines), key=annotations.sort_key):
        saved, unsaved = held.get(record, (None, False))
        text = lines[record][0] if record in lines else None
        if saved == text:
            continue
        if unsaved:
            found.contested.append((record, text))
        else:
            found.take.append(record)
    return found


def apply_import(connection, schema, name, lines, document, take, reseat):
    """Make records of take the file's lines, and give records of reseat ([(record, line or None)]) a new saved line.

    lines is {record: (line text, row)} as read from the file; document is
    the task as the project now has it (None when it is gone), which each
    taken row is checked against.
    """
    lines = lines or {}
    check = fingerprint(document)
    if take:
        connection.execute(_q(schema, 'DELETE FROM {schema}.annotations WHERE task = %s AND record = ANY(%s)'),
                           (name, list(take)))
        statement = _q(schema, 'COPY {schema}.annotations (' + ', '.join(f'"{column}"' for column in _COPY_COLUMNS)
                       + ') FROM STDIN')
        with connection.cursor() as cursor, cursor.copy(statement) as copy:
            for record in take:
                if record not in lines:
                    continue
                text, row = lines[record]
                valid = fits(document, row) if document is not None else True
                copy.write_row((name, record, *_columns(row), text, False, check, valid))
    if reseat:
        with connection.cursor() as cursor:
            cursor.executemany(_q(schema, 'UPDATE {schema}.annotations SET saved = %s WHERE task = %s AND record = %s'),
                               [(text, name, record) for record, text in reseat])
        connection.execute(_q(schema, 'DELETE FROM {schema}.annotations WHERE task = %s AND state IS NULL '
                                      'AND saved IS NULL'), (name,))


# ----------------------------------------------------------------- reading

def unsaved_counts(connection, schema):
    """{task name: how many of its records have an unsaved change}."""
    return dict(connection.execute(_q(schema, 'SELECT task, count(*) FROM {schema}.annotations WHERE unsaved '
                                              'GROUP BY task ORDER BY task')).fetchall())


def held_count(connection, schema, name):
    """How many annotations a task now has (rows removed here and not yet saved are not counted)."""
    return connection.execute(_q(schema, 'SELECT count(*) FROM {schema}.annotations '
                                         'WHERE task = %s AND state IS NOT NULL'), (name,)).fetchone()[0]


def recheck(connection, schema, name, document):
    """Check against the task as it now is every row last checked against another; returns how many were."""
    check = fingerprint(document)
    rows = connection.execute(_q(schema, f'SELECT {_LINE_COLUMNS} FROM {{schema}}.annotations '
                                         'WHERE task = %s AND state IS NOT NULL AND checked IS DISTINCT FROM %s'),
                              (name, check)).fetchall()
    if not rows:
        return 0
    wrong = [row[0] for row in rows if not fits(document, line_of(*row))]
    connection.execute(_q(schema, 'UPDATE {schema}.annotations SET checked = %s, valid = NOT (record = ANY(%s)) '
                                  'WHERE task = %s AND state IS NOT NULL AND checked IS DISTINCT FROM %s'),
                       (check, wrong, name, check))
    return len(rows)


def held_rows(connection, schema, name):
    """{record: (sha256, state, valid, unsaved)} of every annotation the task now has."""
    return {record: (sha, state, valid, unsaved) for record, sha, state, valid, unsaved in connection.execute(
        _q(schema, 'SELECT record, sha256, state, valid, unsaved FROM {schema}.annotations '
                   'WHERE task = %s AND state IS NOT NULL'), (name,))}


def rows(connection, schema, name, records):
    """{record: (row as it now is or None, saved line text or None, unsaved)} for the records that have a row."""
    found = {}
    for record, sha, state, value, note, by, at, origin, saved, unsaved in connection.execute(
            _q(schema, f'SELECT {_LINE_COLUMNS}, saved, unsaved FROM {{schema}}.annotations '
                       'WHERE task = %s AND record = ANY(%s)'), (name, list(records))):
        current = None if state is None else line_of(record, sha, state, value, note, by, at, origin)
        found[record] = (current, saved, unsaved)
    return found


def cached_hashes(connection, schema, run_id, records=None):
    """{record: sha256 or None} kept for run_id, for the records given (all when None)."""
    if records is None:
        query, parameters = 'SELECT record, sha256 FROM {schema}.record_hashes WHERE run_id = %s', (run_id,)
    else:
        query = 'SELECT record, sha256 FROM {schema}.record_hashes WHERE run_id = %s AND record = ANY(%s)'
        parameters = (run_id, list(records))
    return dict(connection.execute(_q(schema, query), parameters).fetchall())


def keep_hashes(connection, schema, run_id, hashes):
    """Keep {record: sha256 or None} for run_id; a record already kept keeps its first hash."""
    if not hashes:
        return
    with connection.cursor() as cursor:
        cursor.executemany(_q(schema, 'INSERT INTO {schema}.record_hashes (run_id, record, sha256) '
                                      'VALUES (%s, %s, %s) ON CONFLICT DO NOTHING'),
                           [(run_id, record, sha) for record, sha in hashes.items()])


# ----------------------------------------------------------------- editing

def set_rows(connection, schema, name, given, removals, document):
    """Store given (rows of annotations.KEYS, already checked) as unsaved, and remove the records of removals.

    A row whose line is exactly its saved line is not unsaved. Returns
    (how many were set, how many annotations were removed).
    """
    check = fingerprint(document)
    if given:
        saved = {record: text for record, text in connection.execute(
            _q(schema, 'SELECT record, saved FROM {schema}.annotations WHERE task = %s AND record = ANY(%s)'),
            (name, [row['record'] for row in given]))}
        with connection.cursor() as cursor:
            cursor.executemany(_q(schema, '''INSERT INTO {schema}.annotations
                                                 (task, record, sha256, state, value, note, "by", "at", origin,
                                                  unsaved, checked, valid)
                                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
                                             ON CONFLICT (task, record) DO UPDATE SET
                                                 sha256 = EXCLUDED.sha256, state = EXCLUDED.state,
                                                 value = EXCLUDED.value, note = EXCLUDED.note,
                                                 "by" = EXCLUDED."by", "at" = EXCLUDED."at",
                                                 origin = EXCLUDED.origin, unsaved = EXCLUDED.unsaved,
                                                 checked = EXCLUDED.checked, valid = true'''),
                               [(name, row['record'], *_columns(row),
                                 annotations.encode(row) != saved.get(row['record']), check) for row in given])
    removed = 0
    if removals:
        removed = connection.execute(_q(schema, 'SELECT count(*) FROM {schema}.annotations WHERE task = %s '
                                                'AND record = ANY(%s) AND state IS NOT NULL'),
                                     (name, list(removals))).fetchone()[0]
        connection.execute(_q(schema, 'DELETE FROM {schema}.annotations WHERE task = %s AND record = ANY(%s) '
                                      'AND saved IS NULL'), (name, list(removals)))
        connection.execute(_q(schema, '''UPDATE {schema}.annotations SET sha256 = NULL, state = NULL, value = NULL,
                                             note = NULL, "by" = NULL, "at" = NULL, origin = NULL, unsaved = true,
                                             checked = NULL, valid = true
                                         WHERE task = %s AND record = ANY(%s)'''), (name, list(removals)))
    return len(given), removed


def revert(connection, schema, name, records, document):
    """Put back the saved line of the records' unsaved rows (every unsaved row of the task when records is None).

    A row with no saved line goes. Returns how many rows were reverted.
    """
    query = 'SELECT record, saved FROM {schema}.annotations WHERE task = %s AND unsaved'
    parameters = [name]
    if records is not None:
        query += ' AND record = ANY(%s)'
        parameters.append(list(records))
    found = connection.execute(_q(schema, query), parameters).fetchall()
    if not found:
        return 0
    gone = [record for record, saved in found if saved is None]
    back = [(record, saved) for record, saved in found if saved is not None]
    if gone:
        connection.execute(_q(schema, 'DELETE FROM {schema}.annotations WHERE task = %s AND record = ANY(%s)'),
                           (name, gone))
    if back:
        check = fingerprint(document)
        updates = []
        for record, saved in back:
            row = json.loads(saved)
            valid = fits(document, row) if document is not None else True
            updates.append((*_columns(row), check, valid, name, record))
        with connection.cursor() as cursor:
            cursor.executemany(_q(schema, '''UPDATE {schema}.annotations SET sha256 = %s, state = %s, value = %s,
                                                 note = %s, "by" = %s, "at" = %s, origin = %s, unsaved = false,
                                                 checked = %s, valid = %s
                                             WHERE task = %s AND record = %s'''), updates)
    return len(found)


# ------------------------------------------------------------------ saving

def file_text(connection, schema, name):
    """(the bytes of the task's line file as the rows now make it, [(record, line)] in file order)."""
    held = [line_of(*row) for row in connection.execute(
        _q(schema, f'SELECT {_LINE_COLUMNS} FROM {{schema}}.annotations WHERE task = %s AND state IS NOT NULL'),
        (name,))]
    data = annotations.write(held)
    texts = data.decode('utf-8').split('\n')[:-1]
    ordered = sorted((row['record'] for row in held), key=annotations.sort_key)
    return data, list(zip(ordered, texts))


def mark_saved(connection, schema, name, lines):
    """After the task's file was written with lines ([(record, line)]): rows hold them as saved, none is unsaved."""
    connection.execute(_q(schema, 'DELETE FROM {schema}.annotations WHERE task = %s AND state IS NULL'), (name,))
    connection.execute(_q(schema, '''UPDATE {schema}.annotations AS a SET saved = given.line, unsaved = false
                                     FROM unnest(%s::text[], %s::text[]) AS given(record, line)
                                     WHERE a.task = %s AND a.record = given.record
                                       AND (a.unsaved OR a.saved IS DISTINCT FROM given.line)'''),
                       ([record for record, _ in lines], [line for _, line in lines], name))
