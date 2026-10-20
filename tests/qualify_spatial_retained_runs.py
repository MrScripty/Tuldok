"""Qualify real old-source schema3 results through explicit current-schema evolution.

Uses disposable catalogs only. The legacy checkout must be the exact pinned,
unmodified source; no synthetic downgrade or mocked execution is accepted.
"""
from auth_helpers import ExplicitOwnerFixture
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
from app import Dataset
from backup_metadata import backup_catalog, read_catalog, read_sequences, restore_catalog, tree_manifest
from metadata import SCHEMA_VERSION, Metadata, StorageError, connection_info
from upgrade_metadata import upgrade_catalog

LEGACY_COMMIT = 'f1ecf7888a8dfa5b67ac8b087034226d533c682e'
LEGACY_PROGRAM = r'''
import json
from pathlib import Path
import sys
import time
root, destination = map(Path, sys.argv[1:])
sys.path[:0] = [str(root), str(root / 'tests')]
from app import Dataset
import meshes
from test_meshes import body, fixture
with_dataset = Dataset(destination)
try:
    assert with_dataset.db.schema_version == 3
    row = meshes.admit(with_dataset.workbench, body(*fixture('asymmetric-prism'), name='Retained native prism', rights='Project-authored fixture'))
    row = with_dataset.workbench.save(row['id'], dict(row, review='human_reviewed', annotation={'note': 'Inspected original geometry.'}))
    request = dict(items=[{key: row[key] for key in ('id','revision','source_revision')}], ratios=dict(train=100,validation=0,test=0), seed=4)
    preview = with_dataset.releases.preview(request)
    release = with_dataset.releases.create(dict(request, preview_token=preview['preview_token']))
    graph = with_dataset.pipelines.create(dict(name='Retained schema3 mesh run', release_id=release['id'], recipe='mesh_validate_export'))
    validation = with_dataset.pipelines.validate(graph['id'], {'revision': 1})
    assert validation['valid'], validation
    run = with_dataset.runs.submit(dict(request_key='retained-schema3-real-run', graph_id=graph['id'], graph_revision=1, validation_token=validation['validation_token']))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = with_dataset.runs.get(run['id'])
        if result['state'] not in ('queued','running','cancelling'):
            break
        time.sleep(.02)
    assert result['state'] == 'completed', result
    receipt = dict(dataset_id=with_dataset.db.dataset_id, run=result, graph=graph, release_id=release['id'], record=row)
finally:
    with_dataset.close()
print(json.dumps(receipt))
'''

LEGACY_REFUSAL_PROGRAM = r'''
import json
from pathlib import Path
import sys
root, destination = map(Path, sys.argv[1:])
sys.path[:0] = [str(root), str(root / 'tests')]
import app
import metadata
assert Path(app.__file__).resolve() == root / 'app.py'
assert Path(metadata.__file__).resolve() == root / 'metadata.py'
assert metadata.SCHEMA_VERSION == 3
try:
    unexpected = app.Dataset(destination)
except metadata.StorageError as error:
    assert str(error) == 'Unsupported PostgreSQL catalog version or definition.', str(error)
    print(json.dumps({'legacy_schema_version': metadata.SCHEMA_VERSION,
                      'outcome': 'unsupported_current_schema', 'error': str(error)}))
else:
    unexpected.close()
    raise AssertionError('Actual legacy application accepted the current schema.')
'''


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def drop_fixture_schema(identity):
    with psycopg.connect(connection_info(), autocommit=True) as connection:
        connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier('catalog_' + identity)))


def legacy_startup_refusal(legacy_root, path):
    """Execute the unchanged old application, then compare stopped raw state."""
    before_files = tree_manifest(path)
    metadata = Metadata(path, create=False)
    try:
        before_tables, before_sequences = read_catalog(metadata), read_sequences(metadata)
        current_version = metadata.schema_version
    finally:
        metadata.close()
    refused = subprocess.run([sys.executable, '-c', LEGACY_REFUSAL_PROGRAM,
        str(legacy_root), str(path)], cwd=legacy_root, capture_output=True, text=True,
        timeout=30, check=True)
    result = json.loads(refused.stdout)
    assert result['outcome'] == 'unsupported_current_schema'
    assert tree_manifest(path) == before_files
    metadata = Metadata(path, create=False)
    try:
        assert read_catalog(metadata) == before_tables
        assert read_sequences(metadata) == before_sequences
    finally:
        metadata.close()
    return dict(result, current_schema_version=current_version,
        legacy_app_sha256=fingerprint((legacy_root/'app.py').read_bytes()),
        legacy_metadata_sha256=fingerprint((legacy_root/'metadata.py').read_bytes()),
        raw_tables_sequences_files_unchanged=True)


def verify(path, receipt, artifacts):
    dataset = Dataset(path)
    with ExplicitOwnerFixture.bootstrap(dataset).bound(dataset):
        try:
            assert dataset.db.schema_version == SCHEMA_VERSION
            assert dataset.db.dataset_id == receipt['dataset_id']
            assert dataset.pipelines.get(receipt['graph']['id']) == receipt['graph']
            assert dataset.runs.get(receipt['run']['id']) == receipt['run']
            assert dataset.workbench.get(receipt['record']['id']) == receipt['record']
            for name, expected in artifacts.items():
                observed, _ = dataset.runs.artifact(receipt['run']['id'], name)
                assert observed == expected, name
            return {'schema_version': SCHEMA_VERSION, 'state': 'completed', 'run_id': receipt['run']['id'],
                    'artifacts': {name: fingerprint(raw) for name, raw in artifacts.items()}}
        finally:
            dataset.close()


def qualify(legacy_root):
    legacy_root = legacy_root.resolve()
    head = subprocess.check_output(['git', '-C', str(legacy_root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != LEGACY_COMMIT:
        raise RuntimeError('Legacy source must be checked out at ' + LEGACY_COMMIT)
    subprocess.run(['git', '-C', str(legacy_root), 'diff', '--exit-code', 'HEAD', '--', '*.py'], check=True, capture_output=True)
    identity = None
    with tempfile.TemporaryDirectory(prefix='tuldok-retained-spatial-') as temporary:
        root = Path(temporary)
        source = root / 'source-schema3'
        try:
            result = subprocess.run([sys.executable, '-c', LEGACY_PROGRAM, str(legacy_root), str(source)],
                                    cwd=legacy_root, capture_output=True, text=True, timeout=90, check=True)
            receipt = json.loads(result.stdout)
            identity = receipt['dataset_id']
            assert receipt['run']['state'] == 'completed'
            run_dir = source / 'workspace-runs' / receipt['run']['id']
            artifacts = {name: (run_dir / name).read_bytes() for name in ('validation-report.json','artifact-manifest.json')}
            artifacts['release.zip'] = (source / 'releases' / (receipt['release_id'] + '.zip')).read_bytes()
            before = tree_manifest(source)
            backup3 = root / 'backup3'
            assert backup_catalog(source, backup3, quiesced=True)['schema_version'] == 3
            backup3_files = tree_manifest(backup3)
            try:
                unexpected = Dataset(source)
            except StorageError:
                pass
            else:
                unexpected.close()
                raise AssertionError('Current application silently accepted schema3.')
            assert upgrade_catalog(source, quiesced=True)['schema_version'] == SCHEMA_VERSION
            assert tree_manifest(source) == before
            upgraded = verify(source, receipt, artifacts)
            old_startup = legacy_startup_refusal(legacy_root, source)
            backup_current = root / 'backup_current'
            assert backup_catalog(source, backup_current, quiesced=True)['schema_version'] == SCHEMA_VERSION
            backup_current_files = tree_manifest(backup_current)
            drop_fixture_schema(identity)
            restored_current = root / 'restored_current'
            restore_catalog(backup_current, restored_current)
            restored = verify(restored_current, receipt, artifacts)
            drop_fixture_schema(identity)
            restored3 = root / 'restored3'
            restore_catalog(backup3, restored3)
            old = Metadata(restored3, create=False, schema_version=3)
            old.close()
            upgrade_catalog(restored3, quiesced=True)
            restored_legacy = verify(restored3, receipt, artifacts)
            assert tree_manifest(backup3) == backup3_files
            assert tree_manifest(backup_current) == backup_current_files
            return {'legacy_commit': head, 'legacy_schema': 3, 'execution': 'real mesh integrity, no training',
                    'upgrade': upgraded, 'current_schema_restore': restored, 'schema3_restore_then_upgrade': restored_legacy,
                    'actual_legacy_startup_refusal': old_startup,
                    'original_backups_unchanged': True}
        finally:
            # Recover identity even if the child failed after creating its catalog.
            if identity is None and (source / '.tuldok.json').exists():
                identity = json.loads((source / '.tuldok.json').read_text())['dataset_id']
            if identity is not None:
                drop_fixture_schema(identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-root', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = qualify(args.legacy_root)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
