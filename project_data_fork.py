"""Finite, pure constructors for independent editable Workbench copies.

Original documents remain exact inert records. A validated project_fork overlay
binds every new initial snapshot to its original domain revision; no old audit,
operation receipt, approval or producer application is rewritten as a new fact.
"""
import copy

from project_data import (FAMILIES, ASSET_KINDS, closed, date, decode_data_records,
                          fail, identity, natural, sha)
from workbench import rights_note

OWNED = frozenset(('workbench_text', 'workbench_record', 'workbench_response',
                   'workbench_preference', 'saved_selection', 'saved_search'))


def _destination_family(family):
    return 'workbench_record' if family == 'workbench_text' else family


def _index(records):
    return {(r['family'], r['id']): r for r in records}


def _revision(envelope):
    return envelope['document']['current']['revision']


def _source(envelope):
    doc = envelope['document']
    if envelope['family'] == 'workbench_text':
        return dict(kind='text', original_text=doc['original_text'])
    return copy.deepcopy(doc['source'])


def _origin(source_project, checkpoint, envelope):
    row = envelope['document']['current']
    return dict(method='project_fork', rights=rights_note(row), origin=dict(
        project_id=source_project, checkpoint=checkpoint, family=envelope['family'],
        id=envelope['id'], revision=row['revision'], source_revision=row['source_revision']))


def _asset(envelope, destination_id, source_project, checkpoint, now, resolve_asset):
    old = envelope['document']['current']
    source = _source(envelope)
    row = copy.deepcopy(old)
    row.update(id=destination_id, revision=1, source_revision=1,
               created_at=now, updated_at=now, review='draft',
               parents=[resolve_asset(parent) or parent for parent in old['parents']],
               provenance=_origin(source_project, checkpoint, envelope))
    row.pop('target_proposal', None)
    if source['kind'] == 'image':
        if source['deleted']:
            fail('Deleted image sources cannot become fresh editable records.')
        sample = copy.deepcopy(source['revisions'][-1])
        sample.update(id=destination_id, revision=1, created_at=now, updated_at=now)
        source['revisions'] = [sample]
        for field, sample_field in {'width':'width','height':'height','source_sha256':'sha256',
                'book_id':'book_id','session_id':'session_id','source_split':'split',
                'corner_annotation':'annotation'}.items():
            row[field] = copy.deepcopy(sample[sample_field])
    return dict(family='workbench_record', id=destination_id, document=dict(
        format='workbench_record_v1', origin=copy.deepcopy(row['provenance']), source=source,
        current=row, history=[copy.deepcopy(row)], events=[], audit=[]))


def _response(envelope, revision, destination_id, parent, now):
    original = next((h['response'] for h in envelope['document']['history']
                     if h['response']['revision'] == revision), None)
    if original is None:
        fail('Fork response revision is missing.')
    row = copy.deepcopy(original)
    row.update(id=destination_id, prompt_id=parent['id'], revision=1,
               review='draft', created_at=now, updated_at=now)
    row['provenance'] = dict(method=original['provenance']['method'], prompt_id=parent['id'],
        prompt_sha256=parent['content_hash'], source_sha256=parent['source_sha256'])
    return dict(family='workbench_response', id=destination_id, document=dict(
        format='workbench_response_v1', current=row,
        history=[dict(response=copy.deepcopy(row), parent=copy.deepcopy(parent))], audit=[]))


def _preference(envelope, destination_id, parent, left, right, now):
    row = copy.deepcopy(envelope['document']['current'])
    if row['deleted']:
        fail('Deleted judgments cannot become fresh editable judgments.')
    row.update(id=destination_id, revision=1, prompt_id=parent['id'], parent_revision=1,
        source_revision=1, left_id=left['id'], right_id=right['id'], left_revision=1,
        right_revision=1, review='draft', provenance=dict(method='draft_comparative_judgment'),
        created_at=now, updated_at=now)
    return dict(family='workbench_preference', id=destination_id, document=dict(
        format='workbench_preference_v1', current=row, history=[dict(judgment=copy.deepcopy(row),
        parent=copy.deepcopy(parent), left=copy.deepcopy(left), right=copy.deepcopy(right))], audit=[]))


def _intent(envelope, destination_id, now, resolve_asset_row):
    doc = envelope['document']
    if doc['deleted']:
        fail('Deleted saved intent cannot become fresh editable intent.')
    row = copy.deepcopy(doc['current'])
    row.update(id=destination_id, revision=1, created_at=now, updated_at=now)
    if envelope['family'] == 'saved_selection':
        members=[]
        for member in row['items']:
            fresh=resolve_asset_row(member['id'])
            # A missing/deleted source remains an explicit archived membership,
            # rather than silently dropping the entered membership or reviving it.
            members.append({k:fresh[k] for k in member} if fresh else member)
        row['items']=members
    return dict(family=envelope['family'], id=destination_id, document=dict(
        format=FAMILIES[envelope['family']], current=row, history=[copy.deepcopy(row)],
        deleted=False, audit=[]))


def fork_records(records, source_project_id, source_checkpoint, destination_project_id,
                 *, id_factory, created_at):
    """Construct fresh drafts; the caller archives originals and publishes once.

    id_factory(family, source_id, domain_revision) owns fresh allocation. This
    function performs no SQL, filesystem access, random allocation or publication.
    """
    identity(source_project_id); identity(destination_project_id); sha(source_checkpoint); date(created_at)
    if source_project_id == destination_project_id or not callable(id_factory):
        fail('An independent fork needs a new project and an ID allocator.')
    decode_data_records(records)
    from project_fork import active_records
    active = [r for r in active_records(records,project_id=source_project_id) if r['family'] in OWNED]
    all_records=_index(records)
    mapping=[]; allocated={}; fresh={}; used={r['id'] for r in records}
    def allocate(envelope, revision=None):
        revision=_revision(envelope) if revision is None else revision
        key=envelope['family'],envelope['id'],revision
        if key not in allocated:
            new_id=identity(id_factory(*key))
            if new_id in used:fail('Fork allocator reused an existing identity.')
            used.add(new_id);allocated[key]=new_id
            mapping.append(dict(family=key[0],source_id=key[1],source_revision=key[2],destination_id=new_id))
        return allocated[key]
    assets=[r for r in active if r['family'] in ('workbench_text','workbench_record') and not _source(r).get('deleted',False)]
    source_assets={r['id']:r for r in assets}
    for envelope in assets:allocate(envelope)
    def resolve_asset(record_id):
        envelope=source_assets.get(record_id)
        return allocate(envelope) if envelope is not None else None
    for envelope in assets:
        made=_asset(envelope,allocate(envelope),source_project_id,source_checkpoint,created_at,resolve_asset)
        fresh[(made['family'],made['id'])]=made
    def asset_row(record_id):
        new_id=resolve_asset(record_id)
        return fresh[('workbench_record',new_id)]['document']['current'] if new_id else None
    responses={(r['id'],_revision(r)):r for r in active if r['family']=='workbench_response'}
    preferences=[r for r in active if r['family']=='workbench_preference' and not r['document']['current']['deleted']]
    for envelope in preferences:
        row=envelope['document']['current']
        for side in ('left','right'):
            key=row[side+'_id'],row[side+'_revision']
            responses[key]=all_records[('workbench_response',key[0])]
    for (record_id,revision),envelope in sorted(responses.items()):
        original=next(h['response'] for h in envelope['document']['history'] if h['response']['revision']==revision)
        parent=asset_row(original['prompt_id'])
        if parent is None:fail('Fork response needs a current editable prompt.')
        made=_response(envelope,revision,allocate(envelope,revision),parent,created_at)
        fresh[(made['family'],made['id'])]=made
    for envelope in preferences:
        row=envelope['document']['current'];parent=asset_row(row['prompt_id'])
        answers=[]
        for side in ('left','right'):
            original=all_records[('workbench_response',row[side+'_id'])]
            new_id=allocate(original,row[side+'_revision'])
            answers.append(fresh[('workbench_response',new_id)]['document']['current'])
        made=_preference(envelope,allocate(envelope),parent,*answers,created_at)
        fresh[(made['family'],made['id'])]=made
    for envelope in active:
        if envelope['family'] in ('saved_selection','saved_search') and not envelope['document']['deleted']:
            made=_intent(envelope,allocate(envelope),created_at,asset_row)
            fresh[(made['family'],made['id'])]=made
    mapping.sort(key=lambda m:(m['family'],m['source_id'],m['source_revision'] or 0,m['destination_id']))
    return dict(records=[fresh[key] for key in sorted(fresh)],mapping=mapping)


def _overlay_maps(records):
    if not any(r['family']=='project_fork' for r in records):return []
    from project_fork import decode_fork
    decode_fork(records)
    return [r['document'] for r in records if r['family']=='project_fork']


def validate_origin(value, record, source, records):
    """A fork origin is meaningful only with its exact archived source mapping."""
    closed(value,{'method','rights','origin'},'fork data provenance')
    ref=value['origin']
    closed(ref,{'project_id','checkpoint','family','id','revision','source_revision'},'fork data source')
    identity(ref['project_id']);sha(ref['checkpoint']);identity(ref['id']);natural(ref['revision'])
    if ref['source_revision'] is not None:natural(ref['source_revision'])
    indexed=_index(records)
    original=indexed.get((ref['family'],ref['id']))
    if ref['family'] not in ('workbench_record','workbench_text') or original is None:
        fail('Fork data origin has no retained source.')
    old=original['document']['current']
    if old['revision']!=ref['revision'] or old['source_revision']!=ref['source_revision'] or value['rights']!=rights_note(old):
        fail('Fork data origin differs from its archived current source.')
    matches=[overlay for overlay in _overlay_maps(records)
        if overlay['source']==dict(project_id=ref['project_id'],checkpoint=ref['checkpoint'])
        and dict(family=ref['family'],source_id=ref['id'],source_revision=ref['revision'],destination_id=record['id']) in overlay['mapping']]
    if len(matches)!=1:fail('Fork data origin lacks its exact independent-fork mapping.')
    if (record['kind'],record['content_hash'],record['pixel_hash'])!=(old['kind'],old['content_hash'],old['pixel_hash']):
        fail('Fork source identity differs from its original.')
    original_source=_source(original)
    if source['kind']=='image':
        if any(source[k]!=original_source[k] for k in ('kind','original','oriented')):
            fail('Fork image source bytes differ.')
    elif source!=original_source:fail('Fork original source or immutable metadata differs.')
    return True


def validate_records(records):
    """Prove initial derived snapshots without rewriting original history."""
    indexed=_index(records)
    for overlay in _overlay_maps(records):
        own=[m for m in overlay['mapping'] if m['family'] in OWNED]
        by_source={(m['family'],m['source_id'],m['source_revision']):m for m in own}
        def asset_mapping(record_id):
            values=[m for m in own if m['family'] in ('workbench_record','workbench_text') and m['source_id']==record_id]
            if len(values)>1:fail('Fork asset has ambiguous destination mappings.')
            return values[0]['destination_id'] if values else None
        def asset_row(record_id):
            new_id=asset_mapping(record_id)
            return indexed[('workbench_record',new_id)]['document']['history'][0] if new_id else None
        for mapping in own:
            family=mapping['family'];original=indexed[(family,mapping['source_id'])]
            destination=indexed[(_destination_family(family),mapping['destination_id'])]
            doc=destination['document']
            initial=doc['history'][0]
            row=initial['response'] if family=='workbench_response' else initial['judgment'] if family=='workbench_preference' else initial
            now=row['created_at'];date(now)
            if family in ('workbench_record','workbench_text'):
                if mapping['source_revision']!=_revision(original):fail('Fork source domain revision differs.')
                expected=_asset(original,destination['id'],overlay['source']['project_id'],overlay['source']['checkpoint'],now,asset_mapping)['document']
                if initial!=expected['history'][0] or doc['origin']!=expected['origin']:
                    fail('Fork initial Workbench snapshot differs from its exact derived draft.')
                if doc['source']['kind']=='image':
                    if doc['source']['revisions'][0]!=expected['source']['revisions'][0]:fail('Fork initial image source differs.')
                elif doc['source']!=expected['source']:fail('Fork immutable source differs.')
            elif family=='workbench_response':
                revision=mapping['source_revision'];natural(revision)
                source_row=next((h['response'] for h in original['document']['history'] if h['response']['revision']==revision),None)
                if source_row is None:fail('Fork response source revision is missing.')
                parent=asset_row(source_row['prompt_id'])
                if parent is None:fail('Fork response lost its current prompt.')
                expected=_response(original,revision,destination['id'],parent,now)['document']
                if initial!=expected['history'][0]:fail('Fork initial response binding differs.')
            elif family=='workbench_preference':
                if mapping['source_revision']!=_revision(original):fail('Fork judgment source revision differs.')
                source_row=original['document']['current'];parent=asset_row(source_row['prompt_id']);answers=[]
                for side in ('left','right'):
                    answer=by_source.get(('workbench_response',source_row[side+'_id'],source_row[side+'_revision']))
                    if answer is None:fail('Fork judgment exact answer revision is missing.')
                    answers.append(indexed[('workbench_response',answer['destination_id'])]['document']['history'][0]['response'])
                expected=_preference(original,destination['id'],parent,*answers,now)['document']
                if initial!=expected['history'][0]:fail('Fork initial preference binding differs.')
            else:
                if mapping['source_revision']!=_revision(original):fail('Fork saved intent source revision differs.')
                expected=_intent(original,destination['id'],now,asset_row)['document']
                if initial!=expected['history'][0]:fail('Fork initial saved intent differs.')
    return True


def source_origin(origin, records):
    """Follow only validated inert fork facts to a subtype source declaration."""
    indexed=_index(records);seen=set();value=origin
    while value.get('method')=='project_fork':
        ref=value['origin'];key=ref['family'],ref['id']
        if key in seen or key not in indexed:fail('Fork source provenance is cyclic or unavailable.')
        seen.add(key);doc=indexed[key]['document']
        value=doc.get('origin',doc['current']['provenance'])
    return copy.deepcopy(value)
