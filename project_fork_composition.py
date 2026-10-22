"""Pure fixed-owner composition for an independent project fork.

The lifecycle owner supplies a validated source checkpoint, creation fact and
fresh ID allocator. This module never opens files, SQL, runtimes or permissions.
The publication owner adds the fork overlay and verifies actual payload custody.
"""
import copy

from project_artifacts import validate_declaration
from project_data_fork import fork_records as fork_data
from project_material_fork import fork_records as fork_material, OWNED as MATERIAL_EDITABLE
from project_files import fork_records as fork_files
from project_fork import ARCHIVE_FAMILIES, ProjectForkError, decode_fork, ID, _uuid, _sha
from project_store import _records


def _fail(message, code='invalid', status=400):
    raise ProjectForkError(message, code, status)


def artifact_plan(records):
    """Give every intrinsic declaration a conservative explicit disposition.

    Runtime files alone can be regenerable. Any unique owner edge to the same
    bytes wins, including archived sources and past producer wire observations.
    Unclassified declarations remain unique; no filename/path guesses are used.
    """
    try:
        declarations = {}
        for item in records:
            if item['family'] != 'project_artifact': continue
            declaration = validate_declaration(item['document'])
            sha = declaration['sha256']
            if item['id'] != sha or sha in declarations:
                _fail('Fork artifact declaration identity differs or repeats.')
            declarations[sha] = declaration
        unique, regenerable, missing = set(), set(), []

        def mark(sha, record, role, name, size=None, *, policy='unique'):
            _sha(sha)
            declaration = declarations.get(sha)
            if declaration is None:
                if policy == 'unique':
                    missing.append(dict(family=record['family'],id=record['id'],role=role,name=name,
                                        sha256=sha,bytes=size))
                return
            if size is not None and declaration['bytes'] != size:
                _fail('Fork owner byte count differs from its intrinsic declaration.')
            (unique if policy == 'unique' else regenerable).add(sha)

        # Finite Workbench source fields. Both original and oriented image bytes
        # are historical identity; re-encoding does not reproduce their hashes.
        for record in records:
            family, doc = record['family'], record['document']
            edges = []
            if family == 'workbench_record':
                source = doc['source']
                if source['kind'] == 'image': edges = [source['original'],source['oriented']]
                elif source['kind'] != 'text': edges = [source['asset']]
            elif family == 'dataset_release': edges = [doc['asset']]
            for edge in edges:
                mark(edge['artifact']['sha256'],record,edge['role'],edge['role'])

        # The material owner has already closed and correlated these inventories
        # with its hashed model, recipe, snapshot and runtime definitions.
        from project_material import decode_records as material_records
        for (family, locator), doc in material_records(records).items():
            record = dict(family=family,id=locator)
            for edge in doc.get('artifacts',[]):
                runtime_file = family == 'runtime_material' and edge['role'] == 'runtime_file' and edge['preservation'] == 'regenerable'
                mark(edge['blob']['sha256'],record,edge['role'],edge['name'],edge['blob']['bytes'],
                     policy='regenerable' if runtime_file else 'unique')

        # Run outputs, exact execution captures, publication proofs and measured
        # host module bytes remain unique regardless of a weaker edge label.
        from project_history import declarations as run_declarations
        for record in records:
            if record['family'] not in ('run_history', 'run_observation'): continue
            doc = (record['document']['observation'] if record['family'] == 'run_observation'
                   else record['document'])
            by_sha = {edge['blob']['sha256']:edge['name'] for edge in doc['payloads']}
            publication = doc['publication']
            if publication is not None:
                for name in ('source','result'):
                    if publication[name] is not None: by_sha[publication[name]['sha256']] = 'publication.'+name
            for declaration in run_declarations(dict(family='run_history', id=record['id'], document=doc)):
                blob = declaration['document']
                mark(blob['sha256'],record,'run_payload',by_sha[blob['sha256']],blob['bytes'])
            run = doc['run']
            if run.get('execution_kind') == 'external_recipe':
                for name, sha in run['material']['host_files'].items():
                    mark(sha,record,'host_source',name)

        # Native measured proof/source/output bytes retain unique custody even
        # when identical bytes also occur in a regenerable runtime dependency.
        for record in records:
            if record['family'] != 'native_execution_history': continue
            for edge in record['document']['payloads']:
                mark(edge['blob']['sha256'],record,edge['role'],edge['name'],edge['blob']['bytes'])

        # Existing pure getter covers the four producer families, entry history
        # payload maps, and variation prompt-batch request/response observations.
        from project_producers import FAMILIES as PRODUCER_FAMILIES, _referenced_artifacts
        for record in records:
            if record['family'] in PRODUCER_FAMILIES:
                for sha in _referenced_artifacts([record]):
                    mark(sha,record,'producer_wire','producer_wire')
        if missing:
            failure = ProjectForkError('Complete fork requires declarations for unique historical payloads.',
                                       'missing_unique',409)
            failure.missing_unique = sorted(missing,key=lambda item:(item['family'],item['id'],item['role'],item['name'],item['sha256']))
            raise failure
        return [dict(declaration=copy.deepcopy(declarations[sha]),
                     preservation='regenerable' if sha in regenerable and sha not in unique else 'unique')
                for sha in sorted(declarations)]
    except ProjectForkError: raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, RecursionError):
        _fail('Malformed fixed-owner fork artifact closure.')


def build_candidate(snapshot, destination_project_id, *, created_at, id_factory):
    """Compose originals, independent editable drafts and complete byte policy.

    id_factory(family, source_envelope_id, source_revision) must return fresh UUID
    strings. Domain owners retain their own version, provenance and binding rules.
    No historical ID, origin catalog or hash-bearing document is rewritten.
    """
    if type(snapshot) is not dict or set(snapshot) != {'project_id','name','checkpoint','records'}:
        _fail('Fork requires one complete canonical source snapshot.')
    _uuid(snapshot['project_id']); _uuid(destination_project_id); _sha(snapshot['checkpoint'])
    if destination_project_id == snapshot['project_id'] or not callable(id_factory):
        _fail('Fork requires an independent destination identity and explicit ID allocator.')
    _records(snapshot['records'])
    source = copy.deepcopy(snapshot['records'])
    previous = decode_fork(source,project_id=snapshot['project_id'])
    used = {snapshot['project_id'],destination_project_id}
    used.update(r['id'] for r in source if ID.fullmatch(r['id']))
    used.update(r['document']['current']['id'] for r in source if r['family'] in MATERIAL_EDITABLE)
    allocated = {}

    def allocate(family, source_id, revision):
        key = family,source_id,revision
        if key not in allocated:
            identity = id_factory(*key)
            _uuid(identity)
            if identity in used: _fail('Fork allocator reused an existing or allocated editable identity.')
            used.add(identity); allocated[key] = identity
        return allocated[key]

    parts = [fork_data(source,snapshot['project_id'],snapshot['checkpoint'],destination_project_id,
                       id_factory=allocate,created_at=created_at),
             fork_material(source,snapshot['project_id'],snapshot['checkpoint'],destination_project_id,
                           id_factory=allocate,created_at=created_at),
             fork_files(source,snapshot['project_id'],snapshot['checkpoint'],destination_project_id)]
    indexed = {(r['family'],r['id']):r for r in source}
    mapping = []
    for part in parts:
        mapping.extend(copy.deepcopy(part['mapping']))
        for record in part['records']:
            key = record['family'],record['id']
            if key in indexed: _fail('Fork owner generated a colliding canonical record.')
            indexed[key] = copy.deepcopy(record)
    records = [indexed[key] for key in sorted(indexed)]
    _records(records)
    archived = {(r['family'],r['id']) for r in source if r['family'] in ARCHIVE_FAMILIES}
    if previous is not None: archived.update((item['family'],item['id']) for item in previous['archived'])
    mapping.sort(key=lambda item:(item['family'],item['source_id'],item['source_revision'] or 0,item['destination_id']))
    return dict(records=records,mapping=mapping,
                archived=[dict(family=family,id=identity) for family,identity in sorted(archived)],
                artifacts=artifact_plan(source))
