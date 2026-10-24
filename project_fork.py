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
    'pipeline_graph', 'recipe_definition', 'project_file', 'project_operation', 'project_composition', FAMILY))
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


def _reconcile_existing(sources, trusted_root_fd, relative, root_path,
                        expected_input, request_key, digest, validate_candidate, *, composed):
    with ProjectStore.open_at(trusted_root_fd, relative, root_path=root_path) as destination:
        snapshot = destination.snapshot()
        overlay = decode_fork(snapshot['records'], project_id=snapshot['project_id'])
        if composed:
            from project_composition import decode_records, composition_input
            document = decode_records(snapshot['records'],project_id=snapshot['project_id']).get(snapshot['project_id'])
            observed_input = None if document is None else composition_input(document['sources'],document['directory'],document['name'],document['request_key'])
            observed_digest = None if document is None else document['request_sha256']
        else:
            observed_input = None if overlay is None else _input(overlay['source'],overlay['directory'],overlay['name'],overlay['request_key'])
            observed_digest = None if overlay is None else overlay['request_sha256']
        if observed_input != expected_input or observed_digest != digest:
            _fail('Existing destination does not belong to this exact fork request.', 'conflict', 409)
        if destination.reconcile(request_key, digest) is None:
            _fail('Existing destination lacks the canonical fork publication receipt.', 'conflict', 409)
        declarations = _declarations(snapshot['records'])
        with ProjectArtifacts(destination) as artifacts:
            validate_candidate(copy.deepcopy(snapshot['records']),snapshot['project_id'],artifacts)
            for identity in overlay['artifacts']['copied']:
                if artifacts.status(declarations[identity])['state'] != 'verified':
                    _fail('Previously copied fork payloads are missing or corrupt.', 'unavailable', 409)
        for item in sources:
            _source_current(item['store'],item['identity'])
        destination.save(snapshot['checkpoint'])
        result = _result(destination.snapshot(),overlay,True)
        if composed:result['composition']=copy.deepcopy(document)
        return result


def publish_fork(source_store, source_artifacts, trusted_root_fd, relative, *, root_path,
                 name, expected_checkpoint, request_key, quiescent, build_candidate,
                 validate_candidate):
    """Publish an independent single-source fork through the shared lifecycle."""
    if not callable(validate_candidate):
        _fail('Fork requires complete validation.','unavailable',503)
    return _publish_project(source_store,source_artifacts,trusted_root_fd,relative,
        root_path=root_path,name=name,expected_checkpoint=expected_checkpoint,request_key=request_key,
        quiescent=quiescent,build_candidate=build_candidate,
        validate_candidate=lambda records,identity,_artifacts:validate_candidate(records,identity))


def recover_committed_publication(trusted_root_fd, staging, relative, *, root_path,
                                  expected_project_id, expected_checkpoint,
                                  expected_request, quiescent):
    """Publish one explicitly selected committed stage without rebuilding it.

    This operator recovery accepts a frozen historical snapshot, not a new read
    of its original sources. The caller owns current filesystem authority and
    cessation of the former process. The store's exclusive root lock, complete
    domain validation, exact original request/commit receipt, payload custody,
    and clean captured files are required before a no-overwrite rename. No SQL
    projection, source permission, source runtime or worker is restored here.
    After an uncertain rename, repeat this exact recovery to inspect the final
    destination; never repeat composition or create another stage.
    """
    if quiescent is not True:
        _fail('Recovery requires proven cessation of the former publication owner.', 'busy', 409)
    _uuid(expected_project_id);_sha(expected_checkpoint)
    stage_parts=_relative_parts(staging);parts=_relative_parts(relative)
    if (stage_parts[:-1]!=parts[:-1]
            or not re.fullmatch(r'\.tuldok-fork-[a-f0-9]{32}',stage_parts[-1])
            or stage_parts==parts):
        _fail('Recovery requires an explicit fork stage beside its original destination.')
    if type(expected_request) is not dict or expected_request.get('directory')!=relative:
        _fail('Recovery requires the exact original publication request.')
    key=expected_request.get('request_key')
    if type(key) is not str or not REQUEST_KEY.fullmatch(key):
        _fail('Recovery requires the original publication request key.')
    digest=_digest(expected_request)
    published=False
    try:
        with anchored_directory(trusted_root_fd,'/'.join(parts[:-1]),root_path=root_path) as parent:
            def exists(name):
                try:os.stat(name,dir_fd=parent,follow_symlinks=False);return True
                except FileNotFoundError:return False
            stage_exists,final_exists=exists(stage_parts[-1]),exists(parts[-1])
            if stage_exists and final_exists:
                _fail('Both stage and destination exist; neither was replaced.', 'conflict', 409)
            if not stage_exists and not final_exists:
                _fail('Neither the selected stage nor its destination is available.', 'unavailable', 409)
            selected=relative if final_exists else staging
            with ProjectStore.open_at(trusted_root_fd,selected,root_path=root_path) as store:
                snapshot=store.snapshot()
                if (snapshot['project_id']!=expected_project_id
                        or snapshot['checkpoint']!=expected_checkpoint):
                    _fail('Recovery project identity or checkpoint differs.', 'stale', 409)
                overlay=decode_fork(snapshot['records'],project_id=expected_project_id)
                if overlay is None:_fail('Recovery requires a committed independent publication.')
                from project_composition import decode_records, composition_input
                composition=decode_records(snapshot['records'],project_id=expected_project_id).get(expected_project_id)
                observed=(composition_input(composition['sources'],composition['directory'],composition['name'],composition['request_key'])
                          if composition is not None else _input(overlay['source'],overlay['directory'],overlay['name'],overlay['request_key']))
                if observed!=expected_request or store.reconcile(key,digest) is None:
                    _fail('Committed stage does not match the original request and receipt.', 'conflict', 409)
                from project_projection import validate_project_records
                from project_files import inspect_captured
                declarations=_declarations(snapshot['records'])
                with ProjectArtifacts(store) as artifacts:
                    validate_project_records(snapshot['records'],project_id=expected_project_id,artifacts=artifacts)
                    checks=artifacts.status_many([declarations[identity] for identity in overlay['artifacts']['copied']])
                    if any(item['state']!='verified' for item in checks):
                        _fail('Committed publication payloads are missing or corrupt.', 'unavailable', 409)
                    with store.root_directory() as project_root:
                        if any(item['state'] not in ('unchanged','deleted')
                               for item in inspect_captured(snapshot['records'],expected_project_id,project_root)):
                            _fail('Committed stage has changed or missing working files.', 'working_files_changed', 409)
                    store.save(expected_checkpoint)
                if not final_exists:
                    # Recheck the selected directory entry while the store root
                    # remains locked; an external rename must not substitute it.
                    with store.root_directory() as project_root:
                        entry=os.stat(stage_parts[-1],dir_fd=parent,follow_symlinks=False)
                        actual=os.fstat(project_root)
                        if (entry.st_dev,entry.st_ino)!=(actual.st_dev,actual.st_ino):
                            _fail('Selected stage directory changed.', 'stale', 409)
                    _rename_noreplace(parent,stage_parts[-1],parts[-1]);published=True
                os.fsync(parent)
                return dict(project_id=expected_project_id,checkpoint=expected_checkpoint,
                            directory=relative,request_key=key,reconciled=final_exists,
                            payloads_copied=0,selected=False)
    except BaseException as error:
        # Anchored directory owners also translate IO failures. Preserve the
        # uncertain post-rename outcome through either exception representation.
        if published:
            raise ProjectForkError('Committed publication was renamed but acknowledgement is uncertain; reconcile this exact recovery.',
                                   'unknown',503) from error
        if isinstance(error,OSError):
            code='conflict' if error.errno==errno.EEXIST else 'unavailable'
            raise ProjectForkError('Committed publication recovery is unavailable; no stage was rebuilt.',
                                   code,503 if code!='conflict' else 409) from error
        raise


def _publish_project(source_store, source_artifacts, trusted_root_fd, relative, *, root_path,
                     name, expected_checkpoint, request_key, quiescent, build_candidate,
                     validate_candidate, retained_sources=()):
    """One native stage/commit/no-clobber lifecycle for forks and composition.

    The workspace owns authorization, quiescence and all borrowed source owners.
    Every source is pinned and rechecked. Composed candidates additionally prove
    complete source provenance. Validators receive the actual source/destination
    artifact owner; no imported runtime, permission or source path is activated.
    No failed or unknown stage is deleted or selected by this owner.
    """
    if quiescent is not True:
        _fail('Fork requires proven quiescence under the workspace lifecycle guard.', 'busy', 409)
    if not callable(build_candidate) or not callable(validate_candidate):
        _fail('Fork requires pure domain construction and complete validation.', 'unavailable', 503)
    if type(retained_sources) not in (tuple,list):_fail('Explicit retained source owners required.')
    if type(request_key) is not str or not REQUEST_KEY.fullmatch(request_key):_fail('Invalid fork request key.')
    _sha(expected_checkpoint)
    if type(name) is not str or not name.strip() or len(name)>200:_fail('Fork name must contain 1–200 characters.')
    _encode(name);parts=_relative_parts(relative)
    owners=[dict(store=source_store,artifacts=source_artifacts,checkpoint=expected_checkpoint)]
    for item in retained_sources:
        _shape(item,('store','artifacts','checkpoint'),'retained source owner')
        _sha(item['checkpoint']);owners.append(dict(item))
    sources=[];snapshots=[];seen=set()
    for item in owners:
        snapshot=item['store'].snapshot()
        if snapshot['checkpoint']!=item['checkpoint']:_fail('Expected source checkpoint changed.','stale',409)
        if snapshot['project_id'] in seen:_fail('Retained source project identity repeats.','conflict',409)
        seen.add(snapshot['project_id'])
        validate_candidate(copy.deepcopy(snapshot['records']),snapshot['project_id'],item['artifacts'])
        identity={key:snapshot[key] for key in ('project_id','checkpoint')}
        sources.append(dict(store=item['store'],artifacts=item['artifacts'],identity=identity))
        snapshots.append(snapshot)
    composed=bool(retained_sources);source=sources[0]['identity']
    if composed:
        from project_composition import composition_input
        expected_input=composition_input(snapshots,relative,name,request_key)
    else:expected_input=_input(source,relative,name,request_key)
    digest=_digest(expected_input)
    source_roots=[];staged=artifacts=None;staging_relative=None;committed=None;published=False
    def sources_current():
        for item in sources:_source_current(item['store'],item['identity'])
    try:
        for item in sources:
            with item['store'].root_directory() as borrowed:source_roots.append(os.dup(borrowed))
        with anchored_directory(trusted_root_fd,'/'.join(parts[:-1]),root_path=root_path) as parent:
            if any(_inside(parent,root) for root in source_roots):_fail('Fork destination cannot overlap any source project.')
            try:existing=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)
            except FileNotFoundError:existing=None
            if existing is not None:
                if not stat.S_ISDIR(existing.st_mode):_fail('Fork destination is an existing or unsafe filesystem object.','conflict',409)
                selected=os.open(parts[-1],DIR_FLAGS,dir_fd=parent)
                try:
                    if any(_inside(root,selected) or _inside(selected,root) for root in source_roots):
                        _fail('Fork destination aliases or overlaps a source project.')
                finally:os.close(selected)
                return _reconcile_existing(sources,trusted_root_fd,relative,root_path,
                    expected_input,request_key,digest,validate_candidate,composed=composed)
            staging_name='.tuldok-fork-'+uuid.uuid4().hex
            staging_relative='/'.join([*parts[:-1],staging_name])
            staged=ProjectStore.create_at(trusted_root_fd,staging_relative,name,
                'fork-stage.'+hashlib.sha256(request_key.encode()).hexdigest(),digest,root_path=root_path)
            destination_id=staged.snapshot()['project_id']
            if destination_id in seen:_fail('Fork destination identity must be new.')
            candidate=build_candidate(copy.deepcopy(snapshots if composed else snapshots[0]),destination_id)
            _shape(candidate,('records','mapping','archived','artifacts'),'owned candidate')
            if type(candidate['records']) is not list:_fail('Fork candidate records must be a list.')
            records=copy.deepcopy(candidate['records']);indexed={}
            for item in records:
                _shape(item,('family','id','document'),'candidate envelope')
                _identifier(item['family'],'Fork candidate family');_identifier(item['id'],'Fork candidate record ID')
                key=item['family'],item['id']
                if key in indexed:_fail('Fork candidate repeats a record identity.')
                indexed[key]=item
            source_index={(r['family'],r['id']):r for snapshot in snapshots for r in snapshot['records']}
            if composed:
                from project_composition import validate_source_memberships
                validate_source_memberships(records,snapshots,destination_id)
            else:
                for identity,original in source_index.items():
                    if identity not in indexed or _encode(indexed[identity])!=_encode(original):
                        _fail('Fork must preserve every original canonical envelope exactly.')
            archived=[_locator(item) for item in candidate['archived']]
            if not set(archived)<=set(source_index):_fail('Fork may archive only retained source records.')
            required={key for key in source_index if key[0] in ARCHIVE_FAMILIES}
            for snapshot in snapshots:
                previous=decode_fork(snapshot['records'],project_id=snapshot['project_id'])
                if previous is not None:required.update(_locator(item) for item in previous['archived'])
            if not required<=set(archived):_fail('Fork must archive every source editable value and operation receipt.')
            declarations=_declarations(records);expected_declarations={}
            for snapshot in snapshots:
                for identity,value in _declarations(snapshot['records']).items():
                    if identity in expected_declarations and expected_declarations[identity]!=value:
                        _fail('Source artifact declarations conflict.')
                    expected_declarations[identity]=value
            if declarations!=expected_declarations:_fail('Fork must retain the source payload inventory without regenerating bytes.')
            plan=_artifact_plan(candidate['artifacts'],declarations);selected={}
            for number,item in enumerate(sources):
                own=_declarations(snapshots[number]['records']);identities=sorted(own)
                observations=item['artifacts'].status_many([own[key] for key in identities])
                for identity,observation in zip(identities,observations):
                    status=observation['state']
                    if status=='corrupt':_fail('Source fork payload is corrupt.','invalid',400)
                    if status=='verified':selected.setdefault(identity,number)
                    elif status!='missing':_fail('Fork requires verified payload custody.','unavailable',409)
            copied=sorted(selected);missing=sorted(set(plan)-set(selected))
            if any(plan[key]=='unique' for key in missing):
                _fail('Irreplaceable source bytes are missing; complete fork is unavailable.','unavailable',409)
            overlay=dict(format=FORMAT,source=source,destination_project_id=destination_id,
                request_key=request_key,request_sha256=_digest(_input(source,relative,name,request_key)),directory=relative,name=name,
                mapping=copy.deepcopy(candidate['mapping']),archived=copy.deepcopy(candidate['archived']),
                artifacts=dict(copied=copied,missing_regenerable=missing))
            records.append(dict(family=FAMILY,id=destination_id,document=overlay))
            decode_fork(records,project_id=destination_id)
            validate_candidate(copy.deepcopy(records),destination_id,source_artifacts)
            sources_current();artifacts=ProjectArtifacts(staged)
            for number,item in enumerate(sources):
                group=[declarations[key] for key in copied if selected[key]==number]
                if group:item['artifacts'].copy_many_to(artifacts,group)
            from project_files import materialize_captured
            with staged.root_directory() as destination_root:materialize_captured(records,destination_id,destination_root)
            sources_current();validate_candidate(copy.deepcopy(records),destination_id,artifacts)
            committed=staged.commit(records,staged.snapshot()['checkpoint'],request_key,digest)
            staged.save(committed['checkpoint']);sources_current()
            try:_rename_noreplace(parent,staging_name,parts[-1])
            except FileExistsError as error:
                raise ProjectForkError('Fork destination appeared during publication; it was not overwritten.','conflict',409) from error
            published=True;os.fsync(parent);sources_current()
            result=_result(committed,overlay,False)
            if composed:
                from project_composition import decode_records
                result['composition']=copy.deepcopy(decode_records(records,project_id=destination_id)[destination_id])
            return result
    except BaseException as error:
        if published:
            failure=ProjectForkError('Fork destination was published but acknowledgement is uncertain; retry this exact request.','unknown',503)
            if committed is not None:
                failure.receipt=dict(committed=True,selected=False,project_id=committed['project_id'],checkpoint=committed['checkpoint'],request_key=request_key,directory=relative)
            raise failure from error
        if isinstance(error,OSError):
            code='conflict' if error.errno==errno.EEXIST else 'unavailable'
            failure=ProjectForkError('Fork publication is unavailable; retained staging has not been selected.',code,409 if code=='conflict' else 503)
            failure.staging_directory=staging_relative;raise failure from error
        if staging_relative is not None:error.staging_directory=staging_relative
        raise
    finally:
        if artifacts is not None:artifacts.close()
        if staged is not None:staged.close()
        for descriptor in source_roots:os.close(descriptor)
