"""The record of changes asked of a project through the service: one row per mutating operation.

Owns section 5 of docs/plans/definition-first-projects/spec-m7.md: the activity
table of a project schema, writing a row (who asked, which operation, what it
named, done or the refusal's code) and reading them newest first. Reads are
never recorded. store.py creates the table with the project schema.
"""
from psycopg import sql
from psycopg.types.json import Jsonb

DETAIL_CHARACTERS = 400
TARGET_CHARACTERS = 200

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.activity (
           id bigserial PRIMARY KEY, at timestamptz NOT NULL,
           actor jsonb NOT NULL, operation text NOT NULL,
           target text NOT NULL, outcome text NOT NULL, detail text NOT NULL)''',
)

_COLUMNS = ('id', 'at', 'actor', 'operation', 'target', 'outcome', 'detail')


def _q(schema, template):
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def record(connection, schema, actor, operation, target, outcome, detail=''):
    """Write one row; actor is kept as {actor_id, kind, label}, target and detail are cut to their limits."""
    shown = {key: actor.get(key) for key in ('actor_id', 'kind', 'label')}
    connection.execute(_q(schema, 'INSERT INTO {schema}.activity (at, actor, operation, target, outcome, detail) '
                                  'VALUES (now(), %s, %s, %s, %s, %s)'),
                       (Jsonb(shown), operation, (target or '')[:TARGET_CHARACTERS], outcome,
                        (detail or '')[:DETAIL_CHARACTERS]))


def items(connection, schema, offset=0, limit=100):
    """{'items': one page of rows, newest first, 'total': how many rows there are}."""
    total = connection.execute(_q(schema, 'SELECT count(*) FROM {schema}.activity')).fetchone()[0]
    rows = connection.execute(_q(schema, 'SELECT ' + ', '.join(_COLUMNS) + ' FROM {schema}.activity '
                                         'ORDER BY id DESC OFFSET %s LIMIT %s'), (offset, limit)).fetchall()
    return {'items': [dict(zip(_COLUMNS, row)) for row in rows], 'total': total}
