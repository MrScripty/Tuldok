"""Explicit quiesced PostgreSQL schema 1 to 2 upgrade, without data rewriting."""
import argparse
import json

import psycopg

from metadata import (Metadata, SCHEMA_VERSION, StorageError, WORKSPACE_TABLES,
                      definition_hash)


def upgrade_catalog(path, *, dsn=None, quiesced=False):
    """Prove a known source, add workspace tables and publish one atomic ledger.

    Stop every old/new app and artifact writer before calling. The advisory lock
    coordinates cooperating commands; it is not a fence against a live old app.
    Re-entry verifies current schema 2, including its independently known shape,
    and performs no writes to domain rows, artifacts or the dataset manifest.
    """
    if not quiesced:
        raise StorageError('Stop all app/artifact writers and explicitly pass quiesced=True / --quiesced.')
    metadata = Metadata(path, dsn=dsn, create=False, schema_version=None)
    try:
        with metadata.transaction():
            metadata.validate_schema()
            source = metadata.schema_version
            if metadata._signature() != metadata.expected_signature(source):
                raise StorageError('Catalog differs from the known schema definition; refuse upgrading or refreshing its signature.')
            if source == 1:
                for statement in WORKSPACE_TABLES.values():
                    metadata.execute(statement)
                signature = metadata._signature()
                if signature != metadata.expected_signature(SCHEMA_VERSION):
                    raise StorageError('Workspace schema upgrade postcondition failed; all changes are rolled back.')
                changed = metadata.execute('''UPDATE catalog_version
                    SET version=%s,definition_sha256=%s,catalog_sha256=%s
                    WHERE version=1 AND dataset_id=%s AND definition_sha256=%s
                    RETURNING version''', (SCHEMA_VERSION, definition_hash(), signature,
                                          metadata.dataset_id, definition_hash(1))).fetchall()
                if len(changed) != 1:
                    raise StorageError('Catalog version changed during upgrade.')
                metadata.schema_version = SCHEMA_VERSION
                metadata.validate_schema()
            result = {'kind': 'postgresql-schema-upgrade',
                      'migration': 'workspace-metadata-1-to-2',
                      'dataset_id': metadata.dataset_id,
                      'schema_version': SCHEMA_VERSION,
                      'definition_sha256': definition_hash(),
                      'catalog_sha256': metadata._signature(),
                      'status': 'upgraded' if source == 1 else 'already_current'}
        return result
    finally:
        metadata.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog')
    parser.add_argument('--quiesced', action='store_true')
    args = parser.parse_args()
    try:
        result = upgrade_catalog(args.catalog, quiesced=args.quiesced)
    except (StorageError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    except psycopg.Error:
        parser.exit(1, 'PostgreSQL schema upgrade failed. Keep writers stopped and inspect the catalog before retrying.\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
