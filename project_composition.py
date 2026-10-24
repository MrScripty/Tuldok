"""Pure retained-source assembly for native independent project composition.

Sources are ordered: the primary supplies the base envelope for an overlapping
identity. Exact duplicates share custody. Only admission-proof grant/consumption
variants of otherwise byte-identical Runs can coexist as native Run observations.
No source root, catalog permission, runtime or editable overlay is activated here.
The lifecycle owner must validate each source and the complete final candidate,
clone primary edits and publish all required bytes through the native owners.
"""
import hashlib

from project_fork import ARCHIVE_FAMILIES, _sha, _uuid, decode_fork
from project_history import capture_run_observation
from project_store import (MAX_RECORDS, MAX_TOTAL_BYTES, ProjectStoreError,
                           _encode, _records)


class ProjectCompositionError(ProjectStoreError):
    pass


def _fail(message, code='invalid', status=400):
    raise ProjectCompositionError(message, code, status)


def _record_sha(record):
    return hashlib.sha256(_encode(record)).hexdigest()


def _approval_variant(original, alternate):
    if original['family'] != 'run_history':
        return False
    left, right = original['document'], alternate['document']
    if _encode({k:v for k,v in left.items() if k != 'admission_proof'}) != _encode(
            {k:v for k,v in right.items() if k != 'admission_proof'}):
        return False
    left, right = left.get('admission_proof'), right.get('admission_proof')
    fields = {'grant', 'consumption', 'admission'}
    return (type(left) is dict and type(right) is dict and set(left) == fields and set(right) == fields
            and _encode(left['admission']) == _encode(right['admission']))


def merge_retained_sources(snapshots):
    """Return owned originals, exact source memberships and inactive dispositions.

    This internal construction step is not a publication or a fresh domain
    admission boundary. Each source must already have passed its domain owners.
    Store shape/size checks are retained here. Sources may be supplied lazily
    to keep one temporary source snapshot in memory at a time. Same-ID conflicts outside the one
    explicit Run-proof case are rejected; nothing is renamed or overwritten.
    Membership digests cover complete canonical envelopes, not Python equality.
    """
    try:
        snapshots = iter(snapshots)
    except TypeError:
        _fail('Composition requires explicit complete source snapshots.')
    projects, indexed, hashes, sizes = set(), {}, {}, {}
    memberships, archived = [], set()
    for snapshot in snapshots:
        if type(snapshot) is not dict or set(snapshot) != {'project_id','name','checkpoint','records'}:
            _fail('Composition requires complete canonical source snapshots.')
        _uuid(snapshot['project_id']); _sha(snapshot['checkpoint'])
        if snapshot['project_id'] in projects:
            _fail('Composition source project identity repeats.', 'conflict', 409)
        projects.add(snapshot['project_id'])
        if type(snapshot['name']) is not str or not snapshot['name'].strip() or len(snapshot['name']) > 200:
            _fail('Composition source name differs from the project contract.')
        previous = decode_fork(snapshot['records'], project_id=snapshot['project_id'])
        if previous is not None:
            archived.update((item['family'], item['id']) for item in previous['archived'])
        membership = dict(project_id=snapshot['project_id'], name=snapshot['name'],
                          checkpoint=snapshot['checkpoint'], records={}, run_observations={})
        if len(snapshot['records']) > MAX_RECORDS:
            _fail('Composition source exceeds the project record budget.', 'too_large', 413)
        source_bytes = 0
        for original in snapshot['records']:
            # Validate/copy one envelope at a time. Holding another complete
            # source-sized serialized/deep-copy list is unnecessary for custody.
            family, identity, document, raw = _records([original])[0]
            source_bytes += len(raw)
            if source_bytes > MAX_TOTAL_BYTES:
                _fail('Composition source exceeds the project byte budget.', 'too_large', 413)
            record = dict(family=family, id=identity, document=document)
            key = family, identity
            sha = _record_sha(record)
            membership['records'].setdefault(family, {})[identity] = sha
            if family in ARCHIVE_FAMILIES:
                archived.add(key)
            if key not in indexed:
                indexed[key], hashes[key], sizes[key] = record, sha, len(raw)
            elif hashes[key] != sha:
                if not _approval_variant(indexed[key], record):
                    _fail('Composition has conflicting retained envelopes: '+family+'/'+identity+'.', 'conflict', 409)
                observation = capture_run_observation(document)
                observation_key = observation['family'], observation['id']
                observation_sha = _record_sha(observation)
                if observation_key in indexed and hashes[observation_key] != observation_sha:
                    _fail('Composition Run observation identity conflicts.', 'conflict', 409)
                indexed[observation_key], hashes[observation_key] = observation, observation_sha
                sizes[observation_key] = len(_records([observation])[0][3])
                membership['run_observations'][identity] = observation['id']
        memberships.append(membership)
        del snapshot
    if len(projects) < 2:
        _fail('Composition requires at least two explicit complete source snapshots.')
    if len(indexed) > MAX_RECORDS or sum(sizes.values()) > MAX_TOTAL_BYTES:
        _fail('Composed retained sources exceed the project record budget.', 'too_large', 413)
    return dict(records=[indexed[key] for key in sorted(indexed)], sources=memberships,
                archived=[dict(family=family,id=identity) for family,identity in sorted(archived)])


FAMILY = 'project_composition'
FORMAT = 'project_composition_v1'


def composition_input(sources, directory, name, request_key):
    return dict(format='project_composition_request_v1',
                sources=[dict(project_id=s['project_id'],checkpoint=s['checkpoint']) for s in sources],
                directory=directory,name=name,request_key=request_key)


def _request_digest(sources, directory, name, request_key):
    return hashlib.sha256(_encode(composition_input(sources,directory,name,request_key))).hexdigest()


def _shape(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail('Invalid composition '+label+' fields.')


def _decode_memberships(document, indexed):
    from project_store import REQUEST_KEY, _identifier, _relative_parts
    _shape(document,('format','destination_project_id','directory','name','request_key','request_sha256','sources'),'provenance')
    if document['format'] != FORMAT:
        _fail('Unsupported composition provenance format.','unsupported',422)
    _uuid(document['destination_project_id']);_relative_parts(document['directory'])
    if type(document['name']) is not str or not document['name'].strip() or len(document['name'])>200:
        _fail('Invalid composition name.')
    if type(document['request_key']) is not str or not REQUEST_KEY.fullmatch(document['request_key']):
        _fail('Invalid composition request key.')
    _sha(document['request_sha256'])
    sources=document['sources']
    if type(sources) is not list or len(sources)<2:
        _fail('Composition provenance needs at least two sources.')
    seen=set()
    for source in sources:
        _shape(source,('project_id','name','checkpoint','records','run_observations'),'source membership')
        _uuid(source['project_id']);_sha(source['checkpoint'])
        if source['project_id'] in seen or source['project_id']==document['destination_project_id']:
            _fail('Composition source identities repeat or alias the destination.')
        seen.add(source['project_id'])
        if type(source['name']) is not str or not source['name'].strip() or len(source['name'])>200:
            _fail('Invalid composition source name.')
        if type(source['records']) is not dict or type(source['run_observations']) is not dict:
            _fail('Composition membership must use explicit inventories.')
        runs=source['records'].get('run_history',{})
        if type(runs) is not dict:_fail('Composition Run membership must be an object.')
        for identity,sha in source['run_observations'].items():
            _identifier(identity,'Composition original Run ID');_sha(sha)
        if not set(source['run_observations'])<=set(runs):
            _fail('Composition has an observation mapping without an original Run.')
        for family,members in source['records'].items():
            _identifier(family,'Composition member family')
            if type(members) is not dict or not members:
                _fail('Composition family membership must be a nonempty object.')
            for identity,sha in members.items():
                _identifier(identity,'Composition member ID');_sha(sha)
                alternate=source['run_observations'].get(identity) if family=='run_history' else None
                if alternate is None:
                    retained=indexed.get((family,identity))
                    if retained is None:_fail('Composition source member is missing.','unavailable',409)
                else:
                    from project_history import _observation_document
                    _sha(alternate)
                    wrapped=indexed.get(('run_observation',alternate))
                    if wrapped is None:_fail('Composition source observation is missing.','unavailable',409)
                    observed=_observation_document(wrapped)
                    retained=dict(family='run_history',id=identity,document=observed['observation'])
                    base=indexed.get(('run_history',identity))
                    if (base is None or not _approval_variant(base,retained)
                            or _record_sha(base)==_record_sha(retained)):
                        _fail('Composition alternate observation is not an admission-proof-only variant.')
                if _record_sha(retained)!=sha:
                    _fail('Composition source membership differs from its exact retained envelope.')
    if document['request_sha256']!=_request_digest(sources,document['directory'],document['name'],document['request_key']):
        _fail('Composition request receipt differs from its exact sources.')


def decode_records(records, *, project_id=None):
    """Validate inert source provenance and its independently owned fork binding."""
    from project_fork import _decode_document
    indexed={(r['family'],r['id']):r for r in records}
    if len(indexed)!=len(records):_fail('Composition record identity repeats.')
    result={}
    for record in records:
        if record['family']!=FAMILY:continue
        document=record['document'];_decode_memberships(document,indexed)
        if record['id']!=document['destination_project_id']:
            _fail('Composition envelope belongs to a different destination.')
        fork=indexed.get(('project_fork',record['id']))
        if fork is None:_fail('Composition has no native fork overlay.','unavailable',409)
        _decode_document(fork['document'],record['id'],indexed)
        overlay=fork['document'];primary=document['sources'][0]
        if (overlay['source']!={key:primary[key] for key in ('project_id','checkpoint')}
                or any(overlay[key]!=document[key] for key in ('directory','name','request_key'))):
            _fail('Composition provenance differs from its primary fork binding.')
        archived={(r['family'],r['id']) for r in overlay['archived']}
        required={(family,identity) for source in document['sources'] for family,members in source['records'].items()
                  for identity in members if family in ARCHIVE_FAMILIES}
        if not required<=archived:
            _fail('Composition must archive all source editable values and operation receipts.')
        result[record['id']]=document
    if project_id is not None:
        current=decode_fork(records,project_id=project_id)
        archived=set() if current is None else {(r['family'],r['id']) for r in current['archived']}
        if any(identity!=project_id and (FAMILY,identity) not in archived for identity in result):
            _fail('Prior composition provenance must remain explicitly archived.')
    return result


def validate_source_memberships(records, snapshots, destination_project_id):
    """Bind a constructed candidate to the actual owner-selected complete inputs."""
    document=next((r['document'] for r in records if r['family']==FAMILY and r['id']==destination_project_id),None)
    if document is None:_fail('Composition candidate has no destination provenance.')
    if len(document['sources'])!=len(snapshots):_fail('Composition candidate source count differs.')
    for membership,snapshot in zip(document['sources'],snapshots):
        if any(membership[key]!=snapshot[key] for key in ('project_id','name','checkpoint')):
            _fail('Composition candidate belongs to different source identities.')
        expected={}
        for record in snapshot['records']:
            expected.setdefault(record['family'],{})[record['id']]=_record_sha(record)
        if membership['records']!=expected:
            _fail('Composition candidate does not preserve the complete source membership.')
    _decode_memberships(document,{(r['family'],r['id']):r for r in records})


def build_candidate(snapshots, destination_project_id, *, created_at, id_factory,
                    directory, name, request_key):
    """Preserve all sources and independently fork only the primary editable state."""
    import copy
    from project_fork_composition import build_candidate as fork_candidate, artifact_plan
    from project_fork import ID
    merged=merge_retained_sources(snapshots)
    _uuid(destination_project_id)
    used={s['project_id'] for s in snapshots}
    if destination_project_id in used:_fail('Composition destination must have a fresh identity.')
    used.update(r['id'] for r in merged['records'] if ID.fullmatch(r['id']))
    used.update(r['document']['current']['id'] for r in merged['records']
                if r['family'] in ('model_definition','pipeline_graph','recipe_definition'))
    used.add(destination_project_id)
    def allocate(family,identity,revision):
        value=id_factory(family,identity,revision);_uuid(value)
        if value in used:_fail('Composition allocator reused a source or allocated identity.')
        used.add(value);return value
    fork=fork_candidate(snapshots[0],destination_project_id,created_at=created_at,id_factory=allocate)
    indexed={(r['family'],r['id']):r for r in merged['records']}
    for record in fork['records']:
        key=record['family'],record['id']
        if key in indexed:
            if _record_sha(indexed[key])!=_record_sha(record):_fail('Primary fork changed an original envelope.')
        else:indexed[key]=record
    document=dict(format=FORMAT,destination_project_id=destination_project_id,directory=directory,name=name,
                  request_key=request_key,request_sha256=_request_digest(merged['sources'],directory,name,request_key),
                  sources=merged['sources'])
    record=dict(family=FAMILY,id=destination_project_id,document=document)
    if (FAMILY,destination_project_id) in indexed:_fail('Composition provenance identity collides.')
    indexed[(FAMILY,destination_project_id)]=record
    records=[indexed[key] for key in sorted(indexed)]
    validate_source_memberships(records,snapshots,destination_project_id)
    archived={(r['family'],r['id']) for r in merged['archived']+fork['archived']}
    return dict(records=records,mapping=copy.deepcopy(fork['mapping']),
                archived=[dict(family=f,id=i) for f,i in sorted(archived)],artifacts=artifact_plan(records))


def publish_composition(primary_store, primary_artifacts, retained_sources, trusted_root_fd, directory,
                        *, root_path, name, expected_checkpoint, request_key, quiescent,
                        created_at, id_factory, validate_candidate):
    """Publish through the native fork lifecycle with explicit additional owners."""
    from functools import partial
    from project_fork import _publish_project
    if type(retained_sources) not in (list,tuple) or not retained_sources:
        _fail('Composition requires at least one explicit secondary source owner.')
    return _publish_project(primary_store,primary_artifacts,trusted_root_fd,directory,
        root_path=root_path,name=name,expected_checkpoint=expected_checkpoint,request_key=request_key,
        quiescent=quiescent,retained_sources=retained_sources,
        build_candidate=partial(build_candidate,created_at=created_at,id_factory=id_factory,
                                directory=directory,name=name,request_key=request_key),
        validate_candidate=validate_candidate)
