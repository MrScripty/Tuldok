"""Independent fork publication and its explicit inert-origin overlay.

Domain owners construct new editable values and their revision-specific origin
mappings. This owner never rewrites domain documents. It preserves source
records, verifies declared payload custody, and atomically publishes a complete
new directory. Runtime quiescence and current authorization belong to the caller.
"""
import copy
import errno
import hashlib
import os
import re
import stat
import uuid

from project_artifacts import ProjectArtifacts, validate_declaration
from project_store import (ProjectStore, ProjectStoreError, REQUEST_KEY, anchored_directory,
                           DIR_FLAGS, _encode, _identifier, _physical, _relative_parts,
                           _rename_noreplace, _walk)

FAMILY = 'project_fork'
FORMAT = 'project_fork_v1'
# Immutable scientific evidence stays origin-scoped and inspectable. Only these
# formerly active values/receipts become inactive through the fork overlay.
ARCHIVE_FAMILIES = frozenset(('workbench_text', 'workbench_record', 'workbench_response',
    'workbench_preference', 'saved_selection', 'saved_search', 'model_definition',
    'pipeline_graph', 'recipe_definition', 'project_file', 'project_operation', FAMILY))
ID = re.compile(r'^[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')


class ProjectForkError(ProjectStoreError):
    pass


def _fail(message, code='invalid', status=400):
    raise ProjectForkError(message, code, status)


def _shape(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail('Invalid fork ' + label + ' fields.')


def _uuid(value):
    if type(value) is not str or not ID.fullmatch(value):
        _fail('Fork project identity must be a UUID.')


def _sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        _fail('Fork checkpoint must be a SHA256 digest.')


def _input(source, directory, name, key):
    return dict(source=source, directory=directory, name=name, request_key=key)


def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _locator(value):
    _shape(value, ('family', 'id'), 'archive locator')
    _identifier(value['family'], 'Fork record family')
    _identifier(value['id'], 'Fork record ID')
    return value['family'], value['id']


def _mapping_key(value):
    return value['family'], value['source_id'], value['source_revision'] or 0, value['destination_id']


def _decode_document(value, identity, indexed):
    _shape(value, ('format', 'source', 'destination_project_id', 'request_key', 'request_sha256',
                   'directory', 'name', 'mapping', 'archived', 'artifacts'), 'origin overlay')
    if value['format'] != FORMAT:
        _fail('Unsupported fork overlay format.', 'unsupported', 422)
    _shape(value['source'], ('project_id', 'checkpoint'), 'source identity')
    _uuid(value['source']['project_id'])
    _sha(value['source']['checkpoint'])
    _uuid(value['destination_project_id'])
    if identity != value['destination_project_id'] or identity == value['source']['project_id']:
        _fail('Fork source and destination identities must be independent.')
    if type(value['request_key']) is not str or not REQUEST_KEY.fullmatch(value['request_key']):
        _fail('Invalid fork request key.')
    _sha(value['request_sha256'])
    _relative_parts(value['directory'])
    if type(value['name']) is not str or not value['name'].strip() or len(value['name']) > 200:
        _fail('Invalid fork display name.')
    if value['request_sha256'] != _digest(_input(value['source'], value['directory'], value['name'], value['request_key'])):
        _fail('Fork request receipt differs from its exact input.')
    if type(value['archived']) is not list:
        _fail('Fork archive inventory must be a list.')
    archived = [_locator(item) for item in value['archived']]
    if archived != sorted(set(archived)) or any(key not in indexed for key in archived):
        _fail('Fork archive must be sorted, unique and refer to retained records.')
    if (FAMILY, identity) in archived:
        _fail('Current fork overlay cannot archive itself.')
    archived = set(archived)
    if type(value['mapping']) is not list:
        _fail('Fork mappings must be a list.')
    sources, destinations, keys = set(), set(), []
    for item in value['mapping']:
        _shape(item, ('family', 'source_id', 'source_revision', 'destination_id'), 'editable mapping')
        _identifier(item['family'], 'Fork mapping family')
        _identifier(item['source_id'], 'Fork source record ID')
        _identifier(item['destination_id'], 'Fork destination record ID')
        revision = item['source_revision']
        if revision is not None and (type(revision) is not int or revision < 1):
            _fail('Fork source revision must be positive or null.')
        source = (item['family'], item['source_id'])
        destination_family = 'workbench_record' if item['family'] == 'workbench_text' else item['family']
        destination = (destination_family, item['destination_id'])
        if (source not in archived or destination not in indexed or destination in archived or
                item['source_id'] == item['destination_id'] or (source, revision) in sources or destination in destinations):
            _fail('Fork mapping must bind an archived source revision to a unique new current record.')
        sources.add((source, revision))
        destinations.add(destination)
        keys.append(_mapping_key(item))
    if keys != sorted(keys):
        _fail('Fork mappings must be sorted.')
    _shape(value['artifacts'], ('copied', 'missing_regenerable'), 'artifact completeness')
    listed = set()
    for field in ('copied', 'missing_regenerable'):
        items = value['artifacts'][field]
        if type(items) is not list:
            _fail('Fork artifact completeness must use lists.')
        for digest in items:
            _sha(digest)
        if items != sorted(set(items)) or listed.intersection(items):
            _fail('Fork artifact completeness must be disjoint, sorted and unique.')
        if any(('project_artifact', digest) not in indexed for digest in items):
            _fail('Fork payload completeness has no intrinsic declaration.')
        listed.update(items)
    return archived


def decode_fork(records, *, project_id=None):
    """Decode the one current overlay; originals remain independently validated.

    Pure owner decoders consume all records for historical closure. Projection
    and receipt owners use active_records only when constructing current state.
    """
    if type(records) is not list:
        _fail('Fork records must be a list.')
    indexed, overlays = {}, {}
    for item in records:
        _shape(item, ('family', 'id', 'document'), 'record envelope')
        _identifier(item['family'], 'Fork record family')
        _identifier(item['id'], 'Fork record ID')
        key = item['family'], item['id']
        if key in indexed:
            _fail('Duplicate fork record identity.')
        indexed[key] = item
        if item['family'] == FAMILY:
            overlays[key] = item['document']
    if project_id is not None:
        _uuid(project_id)
    if not overlays:
        return None
    archives = {key: _decode_document(doc, key[1], indexed) for key, doc in overlays.items()}
    archived_overlays = {key for values in archives.values() for key in values if key[0] == FAMILY}
    candidates = set(overlays) - archived_overlays
    if len(candidates) != 1:
        _fail('Fork history must have exactly one current origin overlay.')
    current = next(iter(candidates))
    if project_id is not None and current[1] != project_id:
        _fail('Fork overlay belongs to a different current project.')
    archive = archives[current]
    for key, previous in archives.items():
        if key != current and (key not in archive or not previous <= archive):
            _fail('Current fork must preserve all prior archived dispositions.')
    return copy.deepcopy(overlays[current])


def active_records(records, *, project_id=None):
    overlay = decode_fork(records, project_id=project_id)
    archived = set() if overlay is None else {(item['family'], item['id']) for item in overlay['archived']}
    return [copy.deepcopy(item) for item in records if (item['family'], item['id']) not in archived]


def _inside(candidate_fd, ancestor_fd):
    """Compare physical ancestry, including directory aliases; never string-prefix."""
    current = os.dup(candidate_fd)
    try:
        expected = _physical(ancestor_fd)
        while True:
            if _physical(current) == expected:
                return True
            parent = os.open('..', DIR_FLAGS, dir_fd=current)
            if _physical(parent) == _physical(current):
                os.close(parent)
                return False
            os.close(current)
            current = parent
    finally:
        os.close(current)


def _declarations(records):
    result = {}
    for item in records:
        if item['family'] == 'project_artifact':
            value = validate_declaration(item['document'])
            if item['id'] != value['sha256'] or item['id'] in result:
                _fail('Fork artifact declaration identity differs or repeats.')
            result[item['id']] = value
    return result


def _artifact_plan(items, declarations):
    if type(items) is not list:
        _fail('Fork requires an explicit payload preservation plan.')
    plan = {}
    for item in items:
        _shape(item, ('declaration', 'preservation'), 'payload preservation edge')
        value = validate_declaration(item['declaration'])
        if item['preservation'] not in ('unique', 'regenerable') or declarations.get(value['sha256']) != value:
            _fail('Fork payload policy refers to an undeclared or changed artifact.')
        previous = plan.get(value['sha256'])
        if previous is None or item['preservation'] == 'unique':
            plan[value['sha256']] = item['preservation']
    if set(plan) != set(declarations):
        _fail('Every retained artifact declaration needs an explicit fork preservation disposition.')
    return plan


def _source_current(store, source):
    current = store.snapshot()
    if current['project_id'] != source['project_id'] or current['checkpoint'] != source['checkpoint']:
        _fail('Source project changed during fork preparation.', 'stale', 409)


def _result(snapshot, overlay, reconciled):
    return dict(snapshot=copy.deepcopy(snapshot), fork=copy.deepcopy(overlay), reconciled=reconciled)


def _reconcile_existing(source_store, source, trusted_root_fd, relative, root_path,
                        expected_input, request_key, digest, validate_candidate):
    with ProjectStore.open_at(trusted_root_fd, relative, root_path=root_path) as destination:
        snapshot = destination.snapshot()
        overlay = decode_fork(snapshot['records'], project_id=snapshot['project_id'])
        if (overlay is None or _input(overlay['source'], overlay['directory'], overlay['name'], overlay['request_key']) != expected_input
                or overlay['request_sha256'] != digest):
            _fail('Existing destination does not belong to this exact fork request.', 'conflict', 409)
        if destination.reconcile(request_key, digest) is None:
            _fail('Existing destination lacks the canonical fork publication receipt.', 'conflict', 409)
        validate_candidate(copy.deepcopy(snapshot['records']), snapshot['project_id'])
        declarations = _declarations(snapshot['records'])
        with ProjectArtifacts(destination) as artifacts:
            for identity in overlay['artifacts']['copied']:
                if artifacts.status(declarations[identity])['state'] != 'verified':
                    _fail('Previously copied fork payloads are missing or corrupt.', 'unavailable', 409)
        _source_current(source_store, source)
        # Rereading reconciles identity; this barrier resolves a lost parent
        # fsync acknowledgement without guessing durability from mere presence.
        destination.save(snapshot['checkpoint'])
        return _result(destination.snapshot(), overlay, True)


def publish_fork(source_store, source_artifacts, trusted_root_fd, relative, *, root_path,
                 name, expected_checkpoint, request_key, quiescent, build_candidate,
                 validate_candidate):
    """Publish a complete independent directory while preserving the source.

    Caller must hold its lifecycle/authorization guard and prove quiescence.
    build_candidate(source_snapshot, destination_project_id) is one pure owned
    composition callback returning exactly records/mapping/archived/artifacts.
    It preserves every original envelope and appends fresh domain-constructed
    values. validate_candidate(records, project_id) owns semantic closure.
    No temporary or final destination is deleted after failed/unknown outcomes.
    """
    if quiescent is not True:
        _fail('Fork requires proven quiescence under the workspace lifecycle guard.', 'busy', 409)
    if not callable(build_candidate) or not callable(validate_candidate):
        _fail('Fork requires pure domain construction and complete validation.', 'unavailable', 503)
    if type(request_key) is not str or not REQUEST_KEY.fullmatch(request_key):
        _fail('Invalid fork request key.')
    _sha(expected_checkpoint)
    if type(name) is not str or not name.strip() or len(name) > 200:
        _fail('Fork name must contain 1–200 characters.')
    _encode(name)
    parts = _relative_parts(relative)
    snapshot = source_store.snapshot()
    if snapshot['checkpoint'] != expected_checkpoint:
        _fail('Expected source checkpoint changed.', 'stale', 409)
    validate_candidate(copy.deepcopy(snapshot['records']), snapshot['project_id'])
    source = dict(project_id=snapshot['project_id'], checkpoint=snapshot['checkpoint'])
    expected_input = _input(source, relative, name, request_key)
    digest = _digest(expected_input)
    source_root = staged = artifacts = None
    staging_relative = None
    overlay = committed = None
    published = False
    try:
        with source_store.root_directory() as borrowed:
            source_root = os.dup(borrowed)
        with anchored_directory(trusted_root_fd, '/'.join(parts[:-1]), root_path=root_path) as parent:
            if _inside(parent, source_root):
                _fail('Fork destination cannot overlap the source project.')
            try:
                existing = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if not stat.S_ISDIR(existing.st_mode):
                    _fail('Fork destination is an existing or unsafe filesystem object.', 'conflict', 409)
                selected = os.open(parts[-1], DIR_FLAGS, dir_fd=parent)
                try:
                    if _inside(source_root, selected) or _inside(selected, source_root):
                        _fail('Fork destination aliases or overlaps the source project.')
                finally:
                    os.close(selected)
                return _reconcile_existing(source_store, source, trusted_root_fd, relative, root_path,
                                           expected_input, request_key, digest, validate_candidate)
            staging_name = '.tuldok-fork-' + uuid.uuid4().hex
            staging_relative = '/'.join([*parts[:-1], staging_name])
            staged = ProjectStore.create_at(trusted_root_fd, staging_relative, name,
                'fork-stage.' + hashlib.sha256(request_key.encode()).hexdigest(), digest, root_path=root_path)
            destination_id = staged.snapshot()['project_id']
            if destination_id == source['project_id']:
                _fail('Fork destination identity must be new.')
            candidate = build_candidate(copy.deepcopy(snapshot), destination_id)
            _shape(candidate, ('records', 'mapping', 'archived', 'artifacts'), 'owned candidate')
            if type(candidate['records']) is not list:
                _fail('Fork candidate records must be a list.')
            records = copy.deepcopy(candidate['records'])
            indexed = {}
            for item in records:
                _shape(item, ('family', 'id', 'document'), 'candidate envelope')
                _identifier(item['family'], 'Fork candidate family')
                _identifier(item['id'], 'Fork candidate record ID')
                identity = item['family'], item['id']
                if identity in indexed:
                    _fail('Fork candidate repeats a record identity.')
                indexed[identity] = item
            source_index = {(item['family'], item['id']): item for item in snapshot['records']}
            for identity, original in source_index.items():
                if identity not in indexed or _encode(indexed[identity]) != _encode(original):
                    _fail('Fork must preserve every original canonical envelope exactly.')
            archived = [_locator(item) for item in candidate['archived']]
            if not set(archived) <= set(source_index):
                _fail('Fork may archive only retained source records.')
            required = {identity for identity in source_index if identity[0] in ARCHIVE_FAMILIES}
            previous = decode_fork(snapshot['records'], project_id=source['project_id'])
            if previous is not None:
                required.update(_locator(item) for item in previous['archived'])
            if not required <= set(archived):
                _fail('Fork must archive every source editable value and operation receipt.')
            declarations = _declarations(records)
            if declarations != _declarations(snapshot['records']):
                _fail('Fork must retain the source payload inventory without regenerating bytes.')
            plan = _artifact_plan(candidate['artifacts'], declarations)
            copied, missing = [], []
            for identity in sorted(plan):
                status = source_artifacts.status(declarations[identity])['state']
                if status == 'corrupt':
                    _fail('Source fork payload is corrupt.', 'invalid', 400)
                if status == 'missing':
                    if plan[identity] == 'unique':
                        _fail('Irreplaceable source bytes are missing; complete fork is unavailable.', 'unavailable', 409)
                    missing.append(identity)
                elif status == 'verified':
                    copied.append(identity)
                else:
                    _fail('Fork requires verified payload custody.', 'unavailable', 409)
            overlay = dict(format=FORMAT, source=source, destination_project_id=destination_id,
                request_key=request_key, request_sha256=digest, directory=relative, name=name,
                mapping=copy.deepcopy(candidate['mapping']), archived=copy.deepcopy(candidate['archived']),
                artifacts=dict(copied=copied, missing_regenerable=missing))
            records.append(dict(family=FAMILY, id=destination_id, document=overlay))
            decode_fork(records, project_id=destination_id)
            validate_candidate(copy.deepcopy(records), destination_id)
            _source_current(source_store, source)
            artifacts = ProjectArtifacts(staged)
            for identity in copied:
                value = declarations[identity]
                with source_artifacts.open_verified(value, maximum_bytes=value['bytes']) as source_fd:
                    artifacts.publish_fd(source_fd, value, maximum_bytes=value['bytes'])
            # Ordinary authored files are explicitly adopted text. Only a new
            # task-owned fork stage materializes them; Open never calls this.
            from project_files import materialize_captured
            with staged.root_directory() as destination_root:
                materialize_captured(records, destination_id, destination_root)
            _source_current(source_store, source)
            validate_candidate(copy.deepcopy(records), destination_id)
            committed = staged.commit(records, staged.snapshot()['checkpoint'], request_key, digest)
            staged.save(committed['checkpoint'])
            _source_current(source_store, source)
            # All named content and its one canonical pointer are durable. The
            # destination appears in one atomic no-overwrite directory rename.
            try:
                _rename_noreplace(parent, staging_name, parts[-1])
            except FileExistsError as error:
                raise ProjectForkError('Fork destination appeared during publication; it was not overwritten.', 'conflict', 409) from error
            published = True
            os.fsync(parent)
            _source_current(source_store, source)
            return _result(committed, overlay, False)
    except BaseException as error:
        if published:
            failure = ProjectForkError('Fork destination was published but acknowledgement is uncertain; retry this exact request.',
                                       'unknown', 503)
            if committed is not None:
                failure.receipt = dict(committed=True, selected=False, project_id=committed['project_id'],
                    checkpoint=committed['checkpoint'], request_key=request_key, directory=relative)
            raise failure from error
        if isinstance(error, OSError):
            code = 'conflict' if error.errno == errno.EEXIST else 'unavailable'
            failure = ProjectForkError('Fork publication is unavailable; retained staging has not been selected.', code,
                                       409 if code == 'conflict' else 503)
            failure.staging_directory = staging_relative
            raise failure from error
        if staging_relative is not None:
            error.staging_directory = staging_relative
        raise
    finally:
        if artifacts is not None:
            artifacts.close()
        if staged is not None:
            staged.close()
        if source_root is not None:
            os.close(source_root)
