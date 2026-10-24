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
