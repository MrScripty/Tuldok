"""Explicit offline Rheon lab conversion. Never import from application code."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

# This script deliberately lives outside the application's import root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from psycopg import sql
from access import Access
from backup_metadata import (canonical, copy_tree, digest, file_hash, read_catalog,
                             read_sequences, summaries, table_state, tree_manifest,
                             unpack, write_json, separate_paths)
from metadata import Metadata, SCHEMA_VERSION, TABLES_V8, definition_hash
from projects import Projects, decode, manifest, relative_path
from runs import Runs, TERMINAL
from workbench import WorkbenchError, encode


class ConversionError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ConversionError(message)


def terminal_run_observation(run):
    """Retain a pre-GO interruption without asserting drainage or new custody."""
    require(run.get('state') in set(TERMINAL) - {'unknown'},
            'Nonterminal/unknown-custody Run blocks conversion; reconcile through its original owner.')
    if run.get('custody_phase', 'drained') == 'drained':
        return None
    # The original Runs owner marks an external attempt interrupted while still
    # prepared when its supervisor fails before GO. This narrow representation
    # never admitted recipe execution; it is not a drained/completed receipt.
    events = run.get('events')
    require(run.get('execution_kind') == 'external_recipe' and run['state'] == 'interrupted'
            and run.get('custody_phase') == 'prepared'
            and 'custody_identity' in run and run['custody_identity'] is None
            and 'worker' in run and run['worker'] is None
            and type(run.get('finished_at')) is str and bool(run['finished_at'])
            and type(events) is list and bool(events) and type(events[-1]) is dict
            and events[-1].get('state') == 'interrupted',
            'Nonterminal/unknown-custody Run blocks conversion; reconcile through its original owner.')
    return ('Original external attempt interrupted while prepared before GO; no worker or custody identity '
            'was recorded. Archived as historical evidence; drainage and current execution are not asserted.')


def identity(value):
    return digest(value)[:32]


def target_identity(metadata):
    """No credential material: bind catalog path and isolated server selection too."""
    info = metadata.connection.info
    return digest({'catalog': str(metadata.path.resolve()), 'host': info.host,
                   'port': info.port, 'database': info.dbname, 'user': info.user})


def application_identity():
    root = Path(__file__).resolve().parents[3]
    return digest({p.name: file_hash(p) for p in sorted(root.glob('*.py'))})


def _reader(roots):
    return Projects(SimpleNamespace(access=None, db=None, lock=None), roots)


def selected_inventory(root, paths):
    """Hash only declared rooted paths and their parents, never walk an alias root."""
    files, unavailable = {}, {}
    reader = _reader({'source': root})
    try:
        for name in sorted(set(paths)):
            relative_path(name)
            try:
                with reader._file('source', name) as (fd, before):
                    sha = hashlib.sha256()
                    for block in iter(lambda: os.read(fd, 1024 * 1024), b''):
                        sha.update(block)
                    after = os.fstat(fd)
                    require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                            (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Selected file changed.')
                    files[name] = {'kind': 'file', 'bytes': before.st_size, 'sha256': sha.hexdigest()}
                parent = Path(name).parent
                while parent != Path('.'):
                    files[parent.as_posix()] = {'kind': 'directory'}
                    parent = parent.parent
            except (OSError, WorkbenchError) as error:
                unavailable[name] = {'status': 'pre-existing-unavailable', 'reason': type(error).__name__}
    finally:
        reader.close()
    return {'files': dict(sorted(files.items())), 'unavailable': unavailable}


def reference_paths(data, alias, root):
    """Bounded union of Project references plus declared recipe source files."""
    paths, recipe_paths = set(), set()
    state = data['tables']['workspace_projects']
    for row in state['rows']:
        saved = decode(unpack(row[state['columns'].index('document')]).encode())
        if saved['root'] != alias:
            continue
        paths.add(relative_path(saved['manifest_path']))
        value = saved['manifest']
        if value.get('activity_path'):
            paths.add(relative_path(value['activity_path']))
        for group in ('data', 'recipes', 'evidence', 'requirements', 'extensions'):
            for ref in value.get(group, []):
                if 'path' in ref:
                    paths.add(relative_path(ref['path']))
                    if group == 'recipes':
                        recipe_paths.add(ref['path'])
    reader = _reader({'source': root})
    try:
        for path in sorted(recipe_paths):
            try:
                value = decode(reader._read('source', path, 64 * 1024))
            except (OSError, WorkbenchError):
                continue
            if isinstance(value, dict):
                for field in ('sources', 'native_sources'):
                    for ref in value.get(field, []) if isinstance(value.get(field, []), list) else []:
                        if isinstance(ref, dict) and isinstance(ref.get('path'), str):
                            paths.add(relative_path(ref['path']))
    finally:
        reader.close()
    return sorted(paths)


def _copy_selected(source, target, selection):
    reader = _reader({'source': source})
    target.mkdir(parents=True)
    try:
        for name, entry in selection.items():
            if entry['kind'] == 'directory':
                (target / name).mkdir(parents=True, exist_ok=True)
                continue
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with reader._file('source', name) as (fd, before), destination.open('xb') as output:
                sha = hashlib.sha256()
                count = 0
                for block in iter(lambda: os.read(fd, 1024 * 1024), b''):
                    output.write(block)
                    sha.update(block)
                    count += len(block)
                output.flush()
                os.fsync(output.fileno())
                after = os.fstat(fd)
                require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                        (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                        and count == entry['bytes'] and sha.hexdigest() == entry['sha256'], 'Selected source changed during copy.')
    finally:
        reader.close()
    require(tree_manifest(target) == selection, 'Selected archive differs.')


def _snapshot_observation(old, root):
    """A stale/unavailable original snapshot is historical evidence, never invented bytes."""
    path = root / relative_path(old['manifest_path'])
    if not path.is_file() or file_hash(path) != old['manifest_sha256']:
        return 'pre-existing source manifest unavailable or changed'
    for group in ('data', 'recipes', 'evidence', 'requirements', 'extensions'):
        for ref in old['manifest'].get(group, []):
            if 'path' not in ref:
                continue
            path = root / relative_path(ref['path'])
            if not path.is_file() or ('sha256' in ref and file_hash(path) != ref['sha256']):
                return 'pre-existing source reference unavailable or changed: ' + ref['path']
    activity = old['manifest'].get('activity_path')
    if activity and not (root / relative_path(activity)).is_file():
        return 'pre-existing source activity unavailable'
    import recipe_contract
    for ref in old['manifest']['recipes']:
        try:
            definition = recipe_contract.decode_definition((root / relative_path(ref['path'])).read_bytes())
        except WorkbenchError:
            continue  # Obsolete definitions become historical evidence in _plan_project.
        for source in definition['sources']:
            path = root / relative_path(source['path'])
            if not path.is_file() or file_hash(path) != source['sha256']:
                return 'pre-existing recipe source unavailable or changed: ' + source['path']
    return None


def _expected_references(data, alias, root=None):
    expected = set()
    state = data['tables']['workspace_projects']
    for row in state['rows']:
        saved = decode(unpack(row[state['columns'].index('document')]).encode())
        if saved['root'] == alias:
            expected.add((saved['manifest_path'], saved['manifest_sha256']))
            for group in ('data', 'recipes', 'evidence', 'requirements', 'extensions'):
                expected.update((ref['path'], ref['sha256']) for ref in saved['manifest'].get(group, [])
                                if 'path' in ref and 'sha256' in ref)
            if root is not None:
                for ref in saved['manifest']['recipes']:
                    path = Path(root) / relative_path(ref['path'])
                    if 'sha256' not in ref or not path.is_file() or file_hash(path) != ref['sha256']:
                        continue
                    try:
                        definition = decode(path.read_bytes())
                    except WorkbenchError:
                        continue
                    if isinstance(definition, dict) and isinstance(definition.get('sources'), list):
                        expected.update((source['path'], source['sha256']) for source in definition['sources']
                                        if isinstance(source, dict) and isinstance(source.get('path'), str)
                                        and isinstance(source.get('sha256'), str))
    return expected


def recovery_bytes(recovery):
    """Recover only explicitly selected bytes with an independently pinned old hash."""
    source = recovery['source']
    if source['kind'] == 'git':
        require(bool(re.fullmatch('[a-f0-9]{40}', source['revision'])), 'Recovery requires exact Git revision.')
        relative_path(source['path'])
        selection = source['revision'] + ':' + source['path']
        command = ['git', '--no-optional-locks', '-C', source['repository']]
        size = int(subprocess.check_output(command + ['cat-file', '-s', selection]))
        require(size <= 40 * 1024 * 1024, 'Recovery exceeds bounded current data capture limit.')
        raw = subprocess.check_output(command + ['show', selection])
    elif source['kind'] == 'file':
        reader = _reader({'recovery': source['root']})
        try:
            raw = reader._read('recovery', relative_path(source['path']), 40 * 1024 * 1024)
        finally:
            reader.close()
    else:
        raise ConversionError('Unsupported exact recovery source.')
    require(hashlib.sha256(raw).hexdigest() == recovery['sha256'], 'Recovered bytes differ from original pinned SHA256.')
    return raw


def verify_archive(path, expected_sha256):
    """Verify independent receipt, every SQL row and every original file byte."""
    path = Path(path)
    require(file_hash(path / 'backup-receipt.json') == expected_sha256,
            'Original archive receipt identity differs.')
    receipt = decode((path / 'backup-receipt.json').read_bytes())
    require(receipt.get('kind') == 'postgresql' and receipt.get('format_version') == 1
            and receipt.get('schema_version') == 8, 'Require exact schema-8 original archive.')
    require(tree_manifest(path / 'catalog') == receipt['files'], 'Original archive files differ.')
    require(file_hash(path / 'metadata.json') == receipt['metadata_sha256'], 'Original archive metadata differs.')
    data = decode((path / 'metadata.json').read_bytes())
    require((data['dataset_id'], data['schema_version'], data['format_version']) ==
            (receipt['dataset_id'], 8, 1), 'Archive identity differs.')
    require(set(data['tables']) == set(TABLES_V8), 'Original archive table inventory differs from schema 8.')
    for state in data['tables'].values():
        require(table_state(state['columns'], [[unpack(v) for v in row] for row in state['rows']]) == state,
                'Archive row identity differs.')
    require(summaries(data['tables']) == receipt['tables'] and data['sequences'] == receipt['sequences'],
            'Archive inventory differs.')
    return receipt, data


def current_project(value):
    """The only source-format decoding: activity_path becomes ordinary evidence."""
    value = copy.deepcopy(value)
    activity = value.pop('activity_path', None)
    require(value.get('schema_version') in (1, 2), 'Unknown source Project format.')
    value['schema_version'] = 2
    value.setdefault('extensions', [])
    if activity is not None:
        relative_path(activity)
        matches = [ref for ref in value['evidence'] if ref['id'] == 'activity']
        require(not matches or (len(matches) == 1 and matches[0]['path'] == activity
                                and 'sha256' not in matches[0]), 'Activity reference conflicts.')
        if not matches:
            value['evidence'].append({'id': 'activity', 'label': 'Live activity', 'path': activity})
    return manifest(value)


def source_key(table, row_hash, ordinal):
    return f'row:{table}:{row_hash}:{ordinal}'


def accounting_check(source_keys, accounting):
    keys = [item['source'] for item in accounting]
    require(len(keys) == len(set(keys)) and set(keys) == set(source_keys),
            'Every source must have exactly one disposition.')
    require(all(item['disposition'] in ('already-current', 'converted-current', 'archived-visible')
                and item.get('destination') for item in accounting), 'Incomplete source disposition.')


def _file_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _project_saved(project, root, path, roots, raw):
    info = Path(roots[root]).stat()
    return {'id': project['id'], 'name': project['name'], 'root': root,
            'root_identity': [info.st_dev, info.st_ino], 'manifest_path': path,
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'manifest': project}


def _recipe_archive_reason(definition, roots):
    """Classify historical declarations without qualifying installed execution."""
    import recipe_contract
    if not recipe_contract.is_bound_evidence(definition) and (
            recipe_contract.is_evidence(definition) or definition['runtime'] != recipe_contract.TORCH_PROFILE):
        return 'unsupported current Project recipe'
    if definition['runtime'] == recipe_contract.TORCH_PROFILE:
        import torch_runtime
        path = (Path(roots['historical']) / 'original-archive/catalog/torch-runtimes' /
                (definition['runtime_snapshot_sha256'] + '.json'))
        try:
            # Decode the exact referenced registry descriptor using its current
            # owner. Do not inspect opaque trainer inputs or invent file_links.
            # Asset availability/qualification remains fresh admission's job.
            torch_runtime.load(path)
            require(file_hash(path) == definition['runtime_snapshot_sha256'],
                    'Referenced runtime descriptor hash differs.')
        except OSError:
            return 'unavailable current runtime descriptor'
        except ValueError:
            return 'obsolete runtime descriptor'
    return None


def _converted_manifest(old, key, spec, roots):
    alias = old['root']
    new = current_project(old['manifest'])
    new['id'] = identity({'source': key, 'manifest': new, 'archive': spec['archive_receipt_sha256']})
    import recipe_contract
    kept = []
    for ref in new['recipes']:
        recipe_raw = (Path(roots[alias]) / relative_path(ref['path'])).read_bytes()
        try:
            definition = recipe_contract.decode_definition(recipe_raw)
            reason = _recipe_archive_reason(definition, roots)
        except WorkbenchError:
            reason = 'obsolete recipe definition'
        if reason:
            new['evidence'].append(dict(ref, id='historical-' + ref['id'],
                label='Historical recipe (' + reason + '): ' + ref['label']))
        else:
            kept.append(ref)
    new['recipes'] = kept
    manifest(new)
    return new


def _plan_project(old, key, spec, roots, planned, deletes, item):
    alias = old['root']
    new = _converted_manifest(old, key, spec, roots)
    path = '_rheon-current/' + new['id'] + '.json'
    raw = canonical(new) + b'\n'
    _file_write(Path(roots[alias]) / path, raw)
    saved = _project_saved(new, alias, path, roots, raw)
    planned.append(saved)
    deletes.append({'table': 'workspace_projects', 'id': old['id']})
    item.update(disposition='converted-current', destination={'table': 'workspace_projects', 'id': new['id'],
                'manifest_sha256': saved['manifest_sha256'], 'document_sha256': digest(saved)})


def prepare(metadata, archive, stage, spec, *, quiesced=False):
    """Read-only DB planning; staged files are private until publish's one commit."""
    require(quiesced, 'All writers must be stopped; explicitly attest quiesced.')
    archive, stage, catalog = separate_paths(archive, stage, metadata.path)
    require(not stage.exists(), 'Stage exists. Verify/publish the exact prepared stage; never rebuild it in place.')
    receipt, data = verify_archive(archive, spec['archive_receipt_sha256'])
    require(metadata.schema_version == SCHEMA_VERSION == spec['target_schema_version']
            and definition_hash() == spec['target_definition_sha256']
            and metadata.dataset_id == spec['dataset_id'] == receipt['dataset_id']
            and target_identity(metadata) == spec['target_connection_sha256']
            and application_identity() == spec['target_application_sha256'], 'Exact target identity differs.')
    metadata.validate_schema()
    before = read_catalog(metadata)
    require(all(before[name] == state for name, state in data['tables'].items())
            and all(not state['count'] for name, state in before.items() if name not in data['tables']),
            'Target must be the exact schema-only upgrade of the stopped archive.')
    require(read_sequences(metadata) == data['sequences'], 'Target sequence state differs.')
    actual_files = tree_manifest(catalog)
    compared_files = dict(actual_files)
    restore_name = '.restore-receipt-' + digest(receipt) + '.json'
    if restore_name in compared_files and restore_name not in receipt['files']:
        require(decode((catalog / restore_name).read_bytes()) ==
                {'kind': 'postgresql-restore', 'backup_sha256': digest(receipt), 'dataset_id': receipt['dataset_id']},
                'Target restore-owner receipt differs.')
        compared_files.pop(restore_name)
    require(compared_files == receipt['files'], 'Target files must exactly match original archive plus its exact restore-owner receipt.')
    require('historical' not in spec['roots'], 'historical is a reserved conversion root alias.')
    stage.mkdir(mode=0o700)
    # Retain complete independent original archive and every configured external tree.
    copy_tree(archive, stage / 'original-archive', tree_manifest(archive))
    roots = {'historical': str(stage)}
    external_inventory = {}
    for alias, selected in sorted(spec['roots'].items()):
        require(alias and '/' not in alias and alias not in ('.', '..'), 'Invalid source root alias.')
        source = Path(selected['path']).resolve(strict=True)
        require(source != stage, 'External source cannot be the stage itself.')
        paths = reference_paths(data, alias, source)
        observed = selected_inventory(source, paths)
        require(observed == {'files': selected['files'], 'unavailable': selected['unavailable']}
                and digest(observed) == selected['selection_sha256'], 'Selected external source inventory differs: ' + alias)
        target = stage / 'external' / alias
        _copy_selected(source, target, observed['files'])
        roots[alias] = str(target)
        external_inventory[alias] = observed['files']
        for recovery in selected.get('recoveries', []):
            require((recovery['original_path'], recovery['sha256']) in _expected_references(data, alias, target),
                    'Recovery is not pinned by an original source reference.')
            raw = recovery_bytes(recovery)
            path = stage / 'recovered' / recovery['sha256']
            if not path.exists():
                _file_write(path, raw)
    planned, accounting, source_keys, deletes = [], [], [], []
    # No Runs constructor: it owns recovery/dispatch, which offline conversion must never start.
    run_reader = Runs.__new__(Runs)
    run_reader.db, run_reader.lock = metadata, metadata.lock
    for table, state in data['tables'].items():
        for ordinal, (row, sha) in enumerate(zip(state['rows'], state['row_sha256'])):
            key = source_key(table, sha, ordinal)
            source_keys.append(key)
            decoded = dict(zip(state['columns'], [unpack(v) for v in row]))
            item = {'source': key, 'source_id': decoded.get('id', decoded.get('grant_id')),
                    'source_sha256': sha, 'disposition': 'already-current',
                    'destination': {'table': table, 'row_sha256': sha}}
            if table == 'workspace_projects':
                old = decode(decoded['document'].encode())
                require(old['id'] == decoded['id'], 'Source Project ID differs.')
                alias = old['root']
                require(alias in roots, 'Every source Project root must be explicitly archived.')
                source_root = Path(spec['roots'][alias]['path']).stat()
                require(old['root_identity'] == [source_root.st_dev, source_root.st_ino],
                        'Source Project root identity differs.')
                old_path = relative_path(old['manifest_path'])
                observation = _snapshot_observation(old, Path(roots[alias]))
                if observation:
                    item.update(disposition='archived-visible', source_observation=observation)
                    deletes.append({'table': table, 'id': decoded['id']})
                    # Row evidence below is still produced for this exact original.
                    old = None
                if old is not None:
                    raw = (Path(roots[alias]) / old_path).read_bytes()
                    require(decode(raw) == old['manifest'], 'Source Project content differs from its bound hash.')
                    _plan_project(old, key, spec, roots, planned, deletes, item)
            elif table == 'workspace_runs':
                envelope = decode(decoded['document'].encode())
                observation = terminal_run_observation(envelope)
                try:
                    if observation:
                        item['source_observation'] = observation
                        raise WorkbenchError('Historical pre-GO interruption is archive-only.', 'unavailable', 409)
                    run_reader._load(decoded['id'])
                except WorkbenchError:
                    item['disposition'] = 'archived-visible'
                    deletes.append({'table': table, 'id': decoded['id']})
            elif table in ('access_execution_grants', 'access_execution_consumptions'):
                # Historical grants never authorize freshly qualified current material.
                item['disposition'] = 'archived-visible'
                deletes.append({'table': table, 'id': decoded.get('id', decoded.get('grant_id'))})
            elif table == 'workspace_graphs':
                from pipeline import decode_graph
                graph = decode(decoded['document'].encode())
                try:
                    decode_graph(graph)
                    require(graph.get('recipe') != 'external_recipe',
                            'Source external graphs require fresh current material qualification.')
                except (WorkbenchError, ConversionError):
                    # External graphs bind original Project IDs/recipe hashes. Preserve
                    # their exact history, never leave them runnable with stale references.
                    item['disposition'] = 'archived-visible'
                    deletes.append({'table': table, 'id': decoded['id']})
            # Each original row gets an ordinary evidence file, including exact opaque JSON text.
            row_path = 'rows/' + table + '/' + str(ordinal) + '.json'
            row_raw = canonical({'historical_import': True, 'authority': 'original_archived_evidence',
                                 'table': table, 'columns': state['columns'], 'values': row,
                                 'original_row_sha256': sha,
                                 'migration_observation': item.get('source_observation')}) + b'\n'
            require(len(row_raw) <= 8 * 1024 * 1024, 'Original row exceeds current evidence inspection limit.')
            _file_write(Path(roots['historical']) / row_path, row_raw)
            item['archive'] = {'root': 'historical', 'path': row_path,
                               'sha256': hashlib.sha256(row_raw).hexdigest()}
            item['inspection'] = []
            # The existing evidence API previews at most 64 KiB. Expose every
            # original fact through exact ASCII fragments; never truncate a row.
            for start in range(0, len(row_raw), 60 * 1024):
                part_path = row_path + '.part-' + str(start // (60 * 1024) + 1) + '.txt'
                part = row_raw[start:start + 60 * 1024]
                _file_write(Path(roots['historical']) / part_path, part)
                item['inspection'].append({'path': part_path, 'sha256': hashlib.sha256(part).hexdigest()})
            if item['disposition'] == 'archived-visible':
                item['destination'] = item['archive']
            accounting.append(item)
    # Original files remain original files; evidence never describes their execution as new.
    for prefix, files in [('catalog', receipt['files'])] + [('external/' + a, f) for a, f in external_inventory.items()]:
        for name, entry in files.items():
            key = 'file:' + prefix + '/' + name
            source_keys.append(key)
            dest = ('original-archive/catalog/' + name if prefix == 'catalog' else prefix + '/' + name)
            accounting.append({'source': key, 'source_sha256': entry.get('sha256'),
                               'disposition': 'archived-visible', 'destination': {'stage_path': dest}})
    for alias, selected in sorted(spec['roots'].items()):
        for name, observation in sorted(selected['unavailable'].items()):
            key = 'reference-unavailable:' + alias + '/' + name
            source_keys.append(key)
            path = 'unavailable/' + identity(key) + '.json'
            raw = canonical({'historical_import': True, 'path': name, 'root': alias, 'observation': observation,
                             'meaning': 'Unavailable before migration; original bytes are not invented.'}) + b'\n'
            _file_write(stage / path, raw)
            accounting.append({'source': key, 'disposition': 'archived-visible',
                               'destination': {'stage_path': path, 'sha256': hashlib.sha256(raw).hexdigest()}})
    for alias, selected in sorted(spec['roots'].items()):
        for recovery in selected.get('recoveries', []):
            key = 'recovered:' + alias + '/' + recovery['original_path'] + ':' + recovery['sha256']
            source_keys.append(key)
            accounting.append({'source': key, 'source_sha256': recovery['sha256'],
                               'recovery_provenance': recovery['source'], 'disposition': 'archived-visible',
                               'destination': {'stage_path': 'recovered/' + recovery['sha256']}})
    # Existing Projects own inspection: paginate references into ordinary schema-2 manifests.
    references, data_references, seen_data = [], [], set()
    for i, item in enumerate(accounting):
        for j, part in enumerate(item.get('inspection', [])):
            references.append({'id': 'row-' + str(i) + '-part-' + str(j + 1),
                               'label': 'Historical ' + item['source'].split(':')[1] +
                                        ' part ' + str(j + 1) + '/' + str(len(item['inspection'])), **part})
    for i, item in enumerate(accounting):
        if item['source'].startswith(('file:', 'recovered:')) and item.get('source_sha256'):
            path = 'files/' + str(i) + '.json'
            raw = canonical({'historical_import': True, 'authority': 'original_archived_evidence',
                             'source': item['source'], 'original_sha256': item['source_sha256'],
                             'recovery_provenance': item.get('recovery_provenance'),
                             'archive_path': item['destination']['stage_path']}) + b'\n'
            _file_write(stage / path, raw)
            references.append({'id': 'file-' + str(i), 'label': 'Historical original file ' + str(i),
                               'path': path, 'sha256': hashlib.sha256(raw).hexdigest()})
            data_key = (item['destination']['stage_path'], item['source_sha256'])
            if data_key not in seen_data:
                seen_data.add(data_key)
                data_references.append({'id': 'file-bytes-' + str(i), 'label': 'Original file bytes ' + str(i),
                                        'path': item['destination']['stage_path'], 'sha256': item['source_sha256']})
        elif item['source'].startswith('reference-unavailable:'):
            references.append({'id': 'unavailable-' + str(i), 'label': 'Pre-existing unavailable source ' + str(i),
                               'path': item['destination']['stage_path'], 'sha256': item['destination']['sha256']})
    for offset in range(0, len(references), 60):
        value = {'schema_version': 2, 'id': identity({'archive': spec['archive_receipt_sha256'], 'page': offset}),
                 'name': 'Historical imported evidence ' + str(offset // 60 + 1),
                 'data': data_references[offset:offset+60], 'recipes': [],
                 'evidence': references[offset:offset+60], 'requirements': [], 'extensions': []}
        manifest(value)
        path = 'project-' + value['id'] + '.json'
        raw = canonical(value) + b'\n'
        _file_write(Path(roots['historical']) / path, raw)
        planned.append(_project_saved(value, 'historical', path, roots, raw))
    accounting_check(source_keys, accounting)
    prepared = {'format': 'rheon_lab_once_v1', 'spec': spec, 'converter_sha256': file_hash(__file__), 'source_keys': source_keys,
                'before': summaries(before), 'sequences': read_sequences(metadata), 'catalog_files': actual_files,
                'external_originals': external_inventory,
                'roots': roots, 'projects': planned, 'deletes': deletes, 'accounting': accounting}
    write_json(stage / 'prepared.json', prepared)
    prepared['stage_files'] = tree_manifest(stage, ('prepared.json',))
    write_json(stage / 'prepared.json', prepared)
    return digest(prepared)


def _verify_stage(stage, expected):
    stage = Path(stage)
    prepared = decode((stage / 'prepared.json').read_bytes())
    require(digest(prepared) == expected and prepared['format'] == 'rheon_lab_once_v1', 'Prepared conversion identity differs.')
    require(tree_manifest(stage, ('prepared.json',)) == prepared['stage_files'], 'Private staged files differ.')
    require(prepared['roots'] == {'historical': str(stage.resolve()), **{
        alias: str(stage.resolve() / 'external' / alias) for alias in prepared['spec']['roots']}},
        'Current Project roots differ from the private stage.')
    # Reconstruct coverage from archived source, independently of planner's source_keys.
    receipt, source = verify_archive(stage / 'original-archive', prepared['spec']['archive_receipt_sha256'])
    source_keys, expected_deletes = [], []
    by_key = {item['source']: item for item in prepared['accounting']}
    projects = {saved['id']: saved for saved in prepared['projects']}
    require(len(projects) == len(prepared['projects']), 'Duplicate planned Project IDs.')
    converted_project_ids = set()
    for table, state in source['tables'].items():
        for ordinal, (row, sha) in enumerate(zip(state['rows'], state['row_sha256'])):
            key = source_key(table, sha, ordinal)
            source_keys.append(key)
            item = by_key.get(key, {})
            require(item.get('source_sha256') == sha and 'archive' in item, 'Original row mapping differs.')
            evidence = decode((stage / item['archive']['path']).read_bytes())
            require(evidence['columns'] == state['columns'] and evidence['values'] == row
                    and evidence['original_row_sha256'] == sha and item['archive']['root'] == 'historical'
                    and file_hash(stage / item['archive']['path']) == item['archive']['sha256'],
                    'Archived original row facts or destination hash differ.')
            fragments = [stage / part['path'] for part in item['inspection']]
            require(b''.join(path.read_bytes() for path in fragments) == (stage / item['archive']['path']).read_bytes()
                    and all(path.stat().st_size <= 60 * 1024 for path in fragments),
                    'Current evidence fragments omit or change original row facts.')
            decoded = dict(zip(state['columns'], [unpack(v) for v in row]))
            disposition = item['disposition']
            if disposition != 'already-current':
                allowed = ((table == 'workspace_projects' and disposition in ('converted-current', 'archived-visible')) or
                           (table in ('workspace_runs', 'workspace_graphs', 'access_execution_grants', 'access_execution_consumptions')
                            and disposition == 'archived-visible'))
                require(allowed, 'Unsupported source row disposition.')
                expected_deletes.append({'table': table, 'id': decoded.get('id', decoded.get('grant_id'))})
                if disposition == 'archived-visible':
                    require(item['destination'] == item['archive'], 'Archived row destination differs from its visible original.')
                if disposition == 'converted-current':
                    old = decode(decoded['document'].encode())
                    expected_manifest = _converted_manifest(old, key, prepared['spec'], prepared['roots'])
                    saved = projects.get(expected_manifest['id'])
                    require(saved is not None and saved['manifest'] == expected_manifest
                            and saved['root'] == old['root'], 'Converted source Project lacks its exact current destination.')
                    raw = (Path(prepared['roots'][saved['root']]) / relative_path(saved['manifest_path'])).read_bytes()
                    require(decode(raw) == expected_manifest and _project_saved(expected_manifest, saved['root'],
                            saved['manifest_path'], prepared['roots'], raw) == saved,
                            'Converted Project bytes/root identity differ from its source mapping.')
                    require(item['destination'] == {'table': 'workspace_projects', 'id': saved['id'],
                            'manifest_sha256': saved['manifest_sha256'], 'document_sha256': digest(saved)},
                            'Converted Project destination IDs/hashes differ.')
                    converted_project_ids.add(saved['id'])
            else:
                require(item['destination'] == {'table': table, 'row_sha256': sha}, 'Retained original row mapping differs.')
    require(sorted(expected_deletes, key=canonical) == sorted(prepared['deletes'], key=canonical),
            'Active row replacements differ from source dispositions.')
    require(converted_project_ids == {saved['id'] for saved in prepared['projects'] if saved['root'] != 'historical'},
            'Unaccounted planned current Project.')
    inventories = [('catalog', receipt['files'])]
    require(set(prepared['external_originals']) == set(prepared['spec']['roots']), 'External root coverage differs.')
    for alias, files in prepared['external_originals'].items():
        require(digest({'files': files, 'unavailable': prepared['spec']['roots'][alias]['unavailable']}) ==
                prepared['spec']['roots'][alias]['selection_sha256'], 'Archived external root inventory differs.')
        inventories.append(('external/' + alias, files))
    for prefix, files in inventories:
        for name, entry in files.items():
            key = 'file:' + prefix + '/' + name
            source_keys.append(key)
            item = by_key.get(key, {})
            path = ('original-archive/catalog/' + name if prefix == 'catalog' else prefix + '/' + name)
            require(item.get('disposition') == 'archived-visible' and item.get('source_sha256') == entry.get('sha256')
                    and item.get('destination') == {'stage_path': path}
                    and prepared['stage_files'].get(path) == entry, 'Original file mapping differs.')
    for alias, selected in sorted(prepared['spec']['roots'].items()):
        for name, observation in sorted(selected['unavailable'].items()):
            key = 'reference-unavailable:' + alias + '/' + name
            source_keys.append(key)
            item = by_key.get(key, {})
            require(item.get('disposition') == 'archived-visible', 'Unavailable source reference unaccounted.')
            archived = decode((stage / item['destination']['stage_path']).read_bytes())
            require(archived['root'] == alias and archived['path'] == name and archived['observation'] == observation,
                    'Pre-existing unavailability fact differs.')
    for alias, selected in sorted(prepared['spec']['roots'].items()):
        for recovery in selected.get('recoveries', []):
            key = 'recovered:' + alias + '/' + recovery['original_path'] + ':' + recovery['sha256']
            source_keys.append(key)
            require((recovery['original_path'], recovery['sha256']) in
                    _expected_references(source, alias, stage / 'external' / alias),
                    'Recovered source was not originally pinned.')
            item = by_key.get(key, {})
            path = 'recovered/' + recovery['sha256']
            require(item.get('disposition') == 'archived-visible' and item.get('source_sha256') == recovery['sha256']
                    and item.get('recovery_provenance') == recovery['source']
                    and item.get('destination') == {'stage_path': path}
                    and file_hash(stage / path) == recovery['sha256'], 'Recovered original mapping differs.')
    require(source_keys == prepared['source_keys'], 'Planned source inventory differs from independent original inventory.')
    accounting_check(source_keys, prepared['accounting'])
    # Original bytes alone are insufficient: prove that all archived facts and
    # artifacts are actually reachable through registered current Projects.
    expected_evidence, expected_data = set(), set()
    for i, item in enumerate(prepared['accounting']):
        expected_evidence.update((part['path'], part['sha256']) for part in item.get('inspection', []))
        if item['source'].startswith(('file:', 'recovered:')) and item.get('source_sha256'):
            path = 'files/' + str(i) + '.json'
            descriptor = decode((stage / path).read_bytes())
            require(descriptor == {'historical_import': True, 'authority': 'original_archived_evidence',
                    'source': item['source'], 'original_sha256': item['source_sha256'],
                    'recovery_provenance': item.get('recovery_provenance'),
                    'archive_path': item['destination']['stage_path']}, 'Original file descriptor differs.')
            expected_evidence.add((path, file_hash(stage / path)))
            expected_data.add((item['destination']['stage_path'], item['source_sha256']))
        elif item['source'].startswith('reference-unavailable:'):
            expected_evidence.add((item['destination']['stage_path'], item['destination']['sha256']))
    actual_evidence, actual_data = [], []
    for saved in prepared['projects']:
        if saved['root'] != 'historical':
            continue
        value = manifest(saved['manifest'])
        require(value['schema_version'] == 2, 'Historical evidence requires a current Project.')
        raw = (stage / relative_path(saved['manifest_path'])).read_bytes()
        require(decode(raw) == value and _project_saved(value, 'historical', saved['manifest_path'],
                prepared['roots'], raw) == saved, 'Historical Project bytes/root identity differ.')
        actual_evidence.extend((ref['path'], ref.get('sha256')) for ref in value['evidence'])
        actual_data.extend((ref['path'], ref.get('sha256')) for ref in value['data'])
    require(len(actual_evidence) == len(set(actual_evidence)) and set(actual_evidence) == expected_evidence,
            'Archived original facts lack exact current evidence visibility.')
    require(len(actual_data) == len(set(actual_data)) and set(actual_data) == expected_data,
            'Archived original artifacts lack exact current data visibility.')
    return prepared


def publish(metadata, stage, expected, *, quiesced=False, token=None, fail_before_commit=False, verify_only=False):
    """One Metadata commit publishes all coordinated rows plus the exact audit receipt.

    On CommitOutcomeUnknown keep writers stopped. Reopen Metadata and call this
    exact reconciliation command: verification never replays publication.
    """
    require(quiesced, 'Keep all writers stopped; explicitly attest quiesced.')
    p = _verify_stage(stage, expected)
    require(metadata.schema_version == p['spec']['target_schema_version']
            and metadata.dataset_id == p['spec']['dataset_id']
            and definition_hash() == p['spec']['target_definition_sha256']
            and target_identity(metadata) == p['spec']['target_connection_sha256']
            and application_identity() == p['spec']['target_application_sha256']
            and file_hash(__file__) == p['converter_sha256'], 'Publication target differs.')
    access = Access(metadata, metadata.path)
    dataset = SimpleNamespace(db=metadata, lock=metadata.lock, access=access)
    owner = Projects(dataset, p['roots'])
    receipt_id = identity({'conversion': expected})
    try:
        with access.bind(token), metadata.lock, metadata.transaction():
            access.require('admin', 'rheon_lab_once.publish', owner_only=True)
            existing = metadata.execute('SELECT details_json FROM access_audit WHERE action=%s AND target_json=%s',
                                        ('rheon_lab_once.publish', encode(receipt_id))).fetchall()
            if existing:
                require(len(existing) == 1, 'Duplicate conversion receipts; keep writers stopped.')
                saved = decode(existing[0][0].encode())
                require(saved['conversion_sha256'] == expected, 'Saved conversion receipt differs.')
                current = read_catalog(metadata)
                audit = current['access_audit']
                retained_audit = [row for row in audit['rows'] if
                                  not (row[audit['columns'].index('action')] == 'rheon_lab_once.publish' and
                                       row[audit['columns'].index('target_json')] == encode(receipt_id))]
                require(digest(table_state(audit['columns'], retained_audit)) == saved['audit_before_receipt_sha256'],
                        'Completed conversion audit inventory differs.')
                current.pop('access_audit')
                require(digest(summaries(current)) == saved['after_without_audit_sha256']
                        and read_sequences(metadata) == p['sequences']
                        and tree_manifest(metadata.path) == p['catalog_files'], 'Completed conversion inventory differs.')
                _verify_projects(owner, p)
                return {'status': 'verified-completed', 'conversion_sha256': expected, 'receipt_id': receipt_id}
            require(summaries(read_catalog(metadata)) == p['before'] and read_sequences(metadata) == p['sequences']
                    and tree_manifest(metadata.path) == p['catalog_files'], 'Stopped target changed before publication.')
            if verify_only:
                return {'status': 'verified-unpublished', 'conversion_sha256': expected, 'receipt_id': receipt_id}
            for item in p['deletes']:
                require(item['table'] in ('workspace_projects', 'workspace_runs', 'workspace_graphs', 'access_execution_grants',
                                         'access_execution_consumptions'), 'Unsupported row replacement.')
                column = 'grant_id' if item['table'] == 'access_execution_consumptions' else 'id'
                metadata.execute(sql.SQL('DELETE FROM {} WHERE {}=%s').format(
                    sql.Identifier(item['table']), sql.Identifier(column)), (item['id'],))
            for saved in p['projects']:
                # Existing Project registration validates current bytes, roots, collisions and audit.
                owner.register_snapshot({'root': saved['root'], 'manifest_path': saved['manifest_path']})
            _verify_projects(owner, p)
            after = read_catalog(metadata)
            audit = after.pop('access_audit')
            access.audit('rheon_lab_once.publish', receipt_id,
                         {'conversion_sha256': expected, 'after_without_audit_sha256': digest(summaries(after)),
                          'audit_before_receipt_sha256': digest(audit)})
            if fail_before_commit:
                raise ConversionError('Injected before-publication failure.')
        return {'status': 'published', 'conversion_sha256': expected, 'receipt_id': receipt_id}
    finally:
        owner.close()


def _verify_projects(owner, prepared):
    import recipe_contract
    for saved in prepared['projects']:
        require(owner._saved(saved['id'], extensions=True) == saved, 'Published Project envelope differs.')
        result = owner._get(saved['id'], True)
        require(result['manifest_status'] == 'unchanged', 'Current Project manifest unavailable.')
        for group in ('data', 'recipes', 'evidence'):
            require(all(ref['status'] == 'available' and ref.get('integrity') != 'mismatch'
                        for ref in result[group]), 'Current Project reference unavailable or corrupt.')
        for ref in saved['manifest']['recipes']:
            inspected = recipe_contract.inspect_recipe(owner, saved['id'], ref['id'], ref['sha256'])
            require(_recipe_archive_reason(inspected['definition'], prepared['roots']) is None,
                    'Retained recipe lacks a current descriptor/Project contract.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inventory', 'prepare', 'publish', 'reconcile'))
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--stage', required=True)
    parser.add_argument('--archive')
    parser.add_argument('--spec')
    parser.add_argument('--prepared-sha256')
    parser.add_argument('--quiesced', action='store_true')
    args = parser.parse_args()
    metadata = Metadata(args.catalog, create=False)
    try:
        if args.mode == 'inventory':
            require(args.archive and args.spec, 'Inventory requires archive and initial spec.')
            result = decode(Path(args.spec).read_bytes())
            _receipt, data = verify_archive(args.archive, result['archive_receipt_sha256'])
            for alias, selected in result['roots'].items():
                observed = selected_inventory(selected['path'], reference_paths(data, alias, selected['path']))
                selected.update(observed, selection_sha256=digest(observed))
        elif args.mode == 'prepare':
            require(args.archive and args.spec, 'Prepare requires exact archive and spec.')
            result = {'prepared_sha256': prepare(metadata, args.archive, args.stage,
                      decode(Path(args.spec).read_bytes()), quiesced=args.quiesced)}
        else:
            require(args.prepared_sha256, 'Publish requires exact prepared SHA256.')
            result = publish(metadata, args.stage, args.prepared_sha256, quiesced=args.quiesced,
                             token=os.environ.get('TULDOK_MIGRATION_OWNER_TOKEN'), verify_only=args.mode == 'reconcile')
        print(json.dumps(result, indent=2))
    finally:
        metadata.close()


if __name__ == '__main__':
    main()
