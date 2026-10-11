"""PostgreSQL fixture inspection and failure injection; never used at runtime."""
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus


def table_names(db):
    return [row[0] for row in db.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname=current_schema() ORDER BY tablename")]


def database_snapshot(db):
    """Compare exact stored values and catalog definitions independently of row order.

    Sequence counters are deliberately excluded: PostgreSQL sequences are not
    transactional. A rolled-back preview may consume a number but retain no row.
    """
    result = []
    for table in table_names(db):
        columns = [tuple(row) for row in db.execute(
            "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position", (table,))]
        rows = sorted(repr(tuple(row)) for row in db.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))))
        result.append(repr((table, columns, rows)))
    for query in (
        "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=current_schema() ORDER BY indexname",
        "SELECT c.conname,pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
        "WHERE n.nspname=current_schema() ORDER BY c.conname,pg_get_constraintdef(c.oid)",
        "SELECT t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND NOT t.tgisinternal ORDER BY t.tgname",
    ):
        result.append(repr([tuple(row) for row in db.execute(query)]))
    return result


def in_transaction(db):
    return db.connection.info.transaction_status != TransactionStatus.IDLE


def install_failure_trigger(db, table, name, message, event='INSERT', condition=None):
    if event not in ('INSERT', 'DELETE', 'UPDATE', 'UPDATE OF annotation_json', 'UPDATE OF groups_json'):
        raise ValueError('Unsupported fixture trigger event')
    function = name + '_function'
    with db.transaction():
        db.execute(sql.SQL("CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS {}")
                   .format(sql.Identifier(function), sql.Literal(
                       "BEGIN RAISE EXCEPTION '%s' USING ERRCODE = '23514'; END" % message.replace("'", "''"))))
        db.execute(sql.SQL('CREATE TRIGGER {} BEFORE {} ON {} FOR EACH ROW {} EXECUTE FUNCTION {}()')
                   .format(sql.Identifier(name), sql.SQL(event), sql.Identifier(table),
                           sql.SQL('') if condition is None else sql.SQL('WHEN ({})').format(sql.SQL(condition)),
                           sql.Identifier(function)))


def drop_failure_trigger(db, table, name):
    with db.transaction():
        db.execute(sql.SQL('DROP TRIGGER {} ON {}').format(sql.Identifier(name), sql.Identifier(table)))
        db.execute(sql.SQL('DROP FUNCTION {}()').format(sql.Identifier(name + '_function')))


@contextmanager
def observed_statements(db):
    statements = []
    original = db.execute

    def execute(query, *args, **kwargs):
        statements.append(query.as_string(db.connection) if isinstance(query, sql.Composable) else query)
        return original(query, *args, **kwargs)

    with patch.object(db, 'execute', side_effect=execute):
        yield statements


@contextmanager
def independent_reader(db):
    """A real second connection sees only committed catalog rows."""
    with psycopg.connect(db.connection.info.dsn, autocommit=True) as reader:
        schema = db.execute('SELECT current_schema()').fetchone()[0]
        reader.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        yield reader


def fixture_database(path):
    """Open an existing browser fixture without initializing owners or repairing it."""
    import json
    from pathlib import Path
    from types import SimpleNamespace
    import uuid
    from metadata import connection_info

    identity = json.loads((Path(path) / '.tuldok.json').read_text())['dataset_id']
    if uuid.UUID(hex=identity).hex != identity:
        raise ValueError('Invalid fixture catalog identity')
    connection = psycopg.connect(connection_info(), autocommit=True)
    connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier('catalog_' + identity)))
    return SimpleNamespace(connection=connection, execute=connection.execute,
                           transaction=connection.transaction, close=connection.close)
