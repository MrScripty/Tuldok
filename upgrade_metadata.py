"""Explicit quiesced PostgreSQL schema 1–5 to 6 upgrade, without data rewriting."""
import argparse
import json

import psycopg

from metadata import (Metadata, SCHEMA_VERSION, StorageError, WORKSPACE_TABLES, SPATIAL_TABLES, PROJECT_TABLES,
                      definition_hash)

# Accepted ordered transitions, with stable identities. The complete chain is
# one transaction: no intermediate version is published if a later step fails.
UPGRADES = {
    5: ('field-sequence-metadata-5-to-6', (
        'ALTER TABLE workbench_records DROP CONSTRAINT workbench_records_kind_check',
        "ALTER TABLE workbench_records ADD CONSTRAINT workbench_records_kind_check CHECK(kind IN ('image','text','sequence','mesh','audio','pointcloud','volume','field_sequence'))",
    )),
    4: ('project-metadata-4-to-5', tuple(PROJECT_TABLES.values())),
    1: ('workspace-metadata-1-to-2', tuple(WORKSPACE_TABLES.values())),
    3: ('spatial-metadata-3-to-4', (
        'ALTER TABLE workbench_records DROP CONSTRAINT workbench_records_kind_check',
        "ALTER TABLE workbench_records ADD CONSTRAINT workbench_records_kind_check CHECK(kind IN ('image','text','sequence','mesh','audio','pointcloud','volume'))",
        *SPATIAL_TABLES.values(),
    )),
    2: ('audio-metadata-2-to-3', (
        'ALTER TABLE workbench_records DROP CONSTRAINT workbench_records_kind_check',
        "ALTER TABLE workbench_records ADD CONSTRAINT workbench_records_kind_check CHECK(kind IN ('image','text','sequence','mesh','audio'))",
    )),
}


def upgrade_catalog(path, *, dsn=None, quiesced=False):
    """Prove a known source and publish the accepted upgrade chain atomically.

    Stop every old/new app and artifact writer before calling. The advisory lock
    coordinates cooperating commands; it is not a fence against a live old app.
    Re-entry verifies current schema 6, including its independently known shape,
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
            for version in range(source, SCHEMA_VERSION):
                migration, statements = UPGRADES[version]
                for statement in statements:
                    metadata.execute(statement)
                signature = metadata._signature()
                target = version + 1
                if signature != metadata.expected_signature(target):
                    raise StorageError(f'{migration} postcondition failed; all changes are rolled back.')
                changed = metadata.execute('''UPDATE catalog_version
                    SET version=%s,definition_sha256=%s,catalog_sha256=%s
                    WHERE version=%s AND dataset_id=%s AND definition_sha256=%s
                    RETURNING version''', (target, definition_hash(target), signature,
                                          version, metadata.dataset_id, definition_hash(version))).fetchall()
                if len(changed) != 1:
                    raise StorageError('Catalog version changed during upgrade.')
                metadata.schema_version = target
                metadata.validate_schema()
            result = {'kind': 'postgresql-schema-upgrade',
                      'migration': UPGRADES[SCHEMA_VERSION - 1][0],
                      'dataset_id': metadata.dataset_id,
                      'schema_version': SCHEMA_VERSION,
                      'definition_sha256': definition_hash(),
                      'catalog_sha256': metadata._signature(),
                      'status': 'upgraded' if source < SCHEMA_VERSION else 'already_current'}
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
