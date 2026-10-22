"""Workbench-owned project data and history, composed by ProjectSession.

Each family below has a closed semantic decoder. SQL is a disposable projection;
the adapter supplies changed owned documents to the shared session, never a
replacement inventory or an independent commit. Existing domain owners admit
mutations and immutable artifact storage owns exact source bytes.
"""
import copy
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import re
from types import SimpleNamespace
import unicodedata

from workbench import (Workbench, WorkbenchError, IDENTIFIER, TASKS, REVIEWS, MAX_TEXT,
                       encode, encode_retained, strings, text_value, timestamp, validate_annotation)
from project_text import decode_records as decode_text_records, SNAPSHOT_FIELDS
from saved_searches import SavedSearches, criteria
from saved_selections import SavedSelections
from dataset_releases import Releases

FAMILIES = {
    'workbench_record': 'workbench_record_v1',
    'workbench_response': 'workbench_response_v1',
    'workbench_preference': 'workbench_preference_v1',
    'saved_selection': 'saved_selection_v1',
    'saved_search': 'saved_search_v1',
    'dataset_release': 'dataset_release_v1',
    'dataset_exposure': 'dataset_exposure_v1',
}
SHA = re.compile(r'^[a-f0-9]{64}$')
ASSET_KINDS = ('sequence', 'mesh', 'pointcloud', 'volume', 'audio', 'field_sequence')
SOURCE_FIELDS = set('id sha256 filename width height book_id session_id split created_at updated_at revision annotation'.split())
RESPONSE_FIELDS = set('id prompt_id revision completion review provenance created_at updated_at'.split())
JUDGMENT_FIELDS = set('id prompt_id parent_revision source_revision left_id left_revision right_id right_revision revision outcome rationale review deleted created_at updated_at provenance'.split())


def fail(message, code='invalid', status=400):
    raise WorkbenchError(message, code, status)


def closed(value, fields, name):
    if type(value) is not dict or set(value) != set(fields):
        fail('Invalid ' + name + ' fields.')


def identity(value, name='identity'):
    if type(value) is not str or not IDENTIFIER.fullmatch(value):
        fail('Invalid project data ' + name + '.')
    return value


def sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        fail('Invalid project data digest.')
    return value


def natural(value, minimum=1):
    if type(value) is not int or not minimum <= value <= 2**53 - 1:
        fail('Invalid project data revision/count.')
    return value


def date(value):
    text_value(value, 'Timestamp', 80)
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        fail('Invalid project data timestamp.')


def digest(value):
    return hashlib.sha256(encode_retained(value).encode()).hexdigest()


def _audit(facts):
    if type(facts) is not list:
        fail('Data audit must be a list.')
    for fact in facts:
        closed(fact, {'action', 'target', 'details', 'result', 'actor_id', 'occurred_at'}, 'data audit')
        if type(fact['action']) is not str or fact['action'] not in DATA_ACTIONS or fact['result'] != 'success' or type(fact['details']) is not dict:
            fail('Invalid data audit action/result.')
        identity(fact['actor_id'], 'historical actor')
        if fact['target'] is not None:
            text_value(fact['target'], 'Audit target', 128)
        date(fact['occurred_at'])
        # The current domain owners publish hashes/revisions, never credentials.
        if set(fact['details']) & {'credential_id', 'token', 'admission_id', 'grant_id'}:
            fail('Current access authority cannot enter data audit facts.')


def _events(events):
    if type(events) is not list:
        fail('Data events must be a list.')
    for event in events:
        closed(event, {'operation', 'request_key', 'record_revision', 'source_revision', 'deleted', 'occurred_at', 'snapshot'}, 'data event')
        if type(event['operation']) is not str or event['operation'] not in DATA_OPERATIONS|RUNTIME_DATA_OPERATIONS or type(event['deleted']) is not bool:
            fail('Invalid data lifecycle event.')
        text_value(event['request_key'], 'Operation key', 128)
        natural(event['record_revision'])
        if event['source_revision'] is not None:
            natural(event['source_revision'])
        date(event['occurred_at'])
        state=event['snapshot'];validate_record_snapshot(state)
        if state['revision']!=event['record_revision'] or state['source_revision']!=event['source_revision']:
            fail('Lifecycle event snapshot revision differs.')


def _edge(value, declarations, kind, role):
    closed(value, {'artifact', 'media_type', 'kind', 'role', 'preservation', 'required_for'}, 'artifact edge')
    closed(value['artifact'], {'namespace', 'sha256'}, 'artifact reference')
    identity(value['artifact']['namespace'], 'artifact namespace')
    sha(value['artifact']['sha256'])
    if value['kind'] != kind or value['role'] != role or value['preservation'] not in ('unique', 'regenerable'):
        fail('Artifact edge meaning differs from its data owner.')
    text_value(value['media_type'], 'Media type', 120)
    if value['required_for'] != ['inspect', 'release']:
        fail('Unsupported data artifact required operations.')
    declaration = declarations.get(value['artifact']['sha256'])
    if declaration is None:
        fail('Data artifact declaration is missing.')
    return declaration


def _source_row(row, record_id):
    closed(row, SOURCE_FIELDS, 'image source snapshot')
    if row['id'] != record_id:
        fail('Image source identity differs.')
    sha(row['sha256']); natural(row['revision'])
    natural(row['width']); natural(row['height'])
    if row['width'] * row['height'] > 40_000_000:
        fail('Image geometry exceeds owner limit.')
    text_value(row['filename'], 'Filename', 200)
    from image_sources import metadata, validate_annotation as validate_corners
    if metadata(row) != {key: row[key] for key in ('book_id', 'session_id', 'split')}:
        fail('Image source metadata is not canonical.')
    if row['annotation'] is not None and validate_corners(row['annotation']) != row['annotation']:
        fail('Image corner annotation is not canonical.')
    if date(row['updated_at']) < date(row['created_at']):
        fail('Image source update precedes creation.')


def _source_metadata(kind,value):
    if kind=='sequence':
        from sequence_assets import SequenceAssets
        SequenceAssets.validate_project_metadata(value)
    elif kind=='mesh':
        from meshes import MeshAssets
        MeshAssets.validate_project_metadata(value)
    elif kind in ('pointcloud','volume'):
        from spatial_assets import SpatialAssets
        SpatialAssets.validate_project_metadata(kind,value)
    elif kind=='audio':
        from audio_assets import validate_project_metadata
        validate_project_metadata(value)
    else:
        from scientific_fields import validate_project_metadata
        validate_project_metadata(value)


def _acquisition(value,record,source,records):
    """Only the finite receipts produced by the existing import owners."""
    if record['kind']=='sequence':
        from sequence_assets import SequenceAssets
        SequenceAssets.validate_project_acquisition(value,source['metadata'])
        return
    if type(value) is not dict:fail('Acquisition facts must be an object.')
    from bulk_import import leaf_name, REQUEST_ID, MAX_ROWS
    if type(value.get('request_id')) is not str or not REQUEST_ID.fullmatch(value['request_id']):fail('Invalid retained import request marker.')
    format_name=value.get('format');declared=value.get('declared')
    if format_name=='tuldok_assets_jsonl_v1':
        closed(value,{'format','request_id','row_sha256','declared'},'JSONL acquisition')
        fields={'manifest_name','row_number'}|({'image_file'} if record['kind']=='image' else set())
        closed(declared,fields,'JSONL source declaration');leaf_name(declared['manifest_name'],'Manifest name')
        if record['kind']=='image':leaf_name(declared['image_file'],'Image filename')
        if type(declared['row_number']) is not int or not 1<=declared['row_number']<=MAX_ROWS:fail('Invalid retained JSONL row number.')
        sha(value['row_sha256']);return
    if format_name=='image_caption_v1':
        from caption_import import snapshot, SNAPSHOT_KEYS, RECORD_KEYS
        closed(value,{'format','request_id','row_sha256','observed','declared'},'caption acquisition')
        closed(value['observed'],{'manifest_sha256','metadata_sha256','asset_sha256','pixel_sha256'},'caption observed hashes')
        closed(declared,{'manifest_name','metadata_path','row_number','image_file','origin_record','protected_component'},'caption declaration')
        if declared['manifest_name']!='manifest.json' or declared['metadata_path'] not in ('train/metadata.jsonl','val/metadata.jsonl','test/metadata.jsonl'):fail('Invalid retained caption metadata location.')
        upstream=declared['origin_record'];closed(upstream,RECORD_KEYS,'caption origin record')
        members=declared['protected_component']
        if type(members) is not list or not 1<=len(members)<=30:fail('Invalid retained protected caption component.')
        for member in members:snapshot(member)
        if not any(member=={k:upstream[k] for k in SNAPSHOT_KEYS} for member in members):fail('Caption source is absent from its declared component.')
        for digest_value in value['observed'].values():sha(digest_value)
    elif format_name=='canonical_v1':
        text_source=record['kind']=='text'
        fields={'format','request_id','archive_sha256','manifest_sha256','row_sha256','asset_sha256','input_sha256','input_basis','declared'}
        fields|={'metadata_sha256'} if text_source else {'coco_sha256','row_hash_basis','pixel_sha256','upstream_graph'}
        closed(value,fields,'native acquisition')
        closed(declared,{'archive_name','metadata_path','row_number','asset','upstream'},'native source declaration')
        leaf_name(declared['archive_name'],'Archive filename')
        closed(declared['upstream'],{'record','original_status'},'native upstream declaration')
        if declared['upstream']['original_status']!='unavailable':fail('Native imported original status differs.')
        upstream=declared['upstream']['record']
        from native_text_import import RECORD_KEYS
        closed(upstream,RECORD_KEYS,'native origin record')
        if text_source:
            sha(value['metadata_sha256'])
            if value['input_basis']!='consumed_exported_text' or declared['metadata_path'] not in ('train/records.jsonl','validation/records.jsonl','test/records.jsonl'):fail('Invalid retained native text input.')
        else:
            closed(value['coco_sha256'],{'train','validation','test'},'native COCO hashes')
            for item in value['coco_sha256'].values():sha(item)
            sha(value['pixel_sha256'])
            if value['input_basis']!='consumed_exported_png' or value['row_hash_basis']!='canonical_parsed_manifest_record' or value['upstream_graph']!='selected_declared_links_only' or declared['metadata_path']!='manifest.json':fail('Invalid retained native image input.')
        for field in ('archive_sha256','manifest_sha256','asset_sha256','input_sha256'):sha(value[field])
    else:fail('Unsupported retained acquisition format.','unsupported',409)
    sha(value['row_sha256'])
    if type(declared['row_number']) is not int or not 1<=declared['row_number']<=1000:fail('Invalid retained source row number.')
    path=declared['image_file'] if format_name=='image_caption_v1' else declared['asset']
    if type(path) is not str or path!=upstream['asset'] or any(part in ('','.','..') for part in path.split('/')) or '\\' in path or path.startswith('/'):fail('Invalid retained source asset reference.')
    captured={k:upstream[k] for k in SNAPSHOT_FIELDS}
    _record(captured,identity(captured['id']))
    foreign_source=dict(kind=captured['kind'],original={'artifact':{'sha256':captured['source_sha256']}})
    origin=dict(captured['provenance']);origin.pop('rights_note_correction',None)
    _origin(origin,captured,foreign_source,records)


def _origin(value,record,source,records):
    kind=record['kind']
    method=value.get('method')
    if method=='project_fork':
        from project_data_fork import validate_origin
        validate_origin(value,record,source,records)
        return
    if method in ('model_generated','model_grounded_rewrite'):
        from project_producers import validate_record_origin
        validate_record_origin(value,record,records)
        return
    if method=='procedural':
        closed(value,{'method','recipe','recipe_version','seed','ordinal','factors','rights','verification'},'procedural origin')
        from dataset_recipes import RECIPES
        if value['recipe'] not in RECIPES or RECIPES[value['recipe']]['kind']!=kind or type(value['recipe_version']) is not int or value['recipe_version']!=1 or type(value['seed']) is not int or not 0<=value['seed']<=2**32-1 or type(value['ordinal']) is not int or not 0<=value['ordinal']<100 or type(value['factors']) is not dict:
            fail('Invalid retained procedural origin.')
        factors=value['factors']
        if kind=='image':
            closed(factors,{'canvas','objects','occlusion'},'procedural image factors')
            if factors['canvas']!=[128,96] or any(type(n) is not int for n in factors['canvas']) or type(factors['objects']) is not int or factors['objects']!=value['ordinal']%4 or type(factors['occlusion']) is not int or factors['occlusion']!=0:fail('Procedural image factors differ from the owned recipe.')
        else:
            from dataset_recipes import TEMPLATES
            closed(factors,{'topic','day','hour','template'},'procedural text factors')
            if factors['topic'] not in ('design review','project planning','reading group','demo','studio session') or factors['day'] not in ('Monday','Tuesday','Wednesday','Thursday','Friday') or type(factors['hour']) is not str or not re.fullmatch(r'(?:[89]|1[0-8]):(?:00|15|30|45)',factors['hour']) or type(factors['template']) is not int or factors['template']!=value['ordinal']%len(TEMPLATES):fail('Procedural text factors differ from the owned recipe.')
        if value['verification']!='Targets derived from authored scene/template state; no human review or real-world quality claim.':fail('Procedural verification declaration differs.')
        return
    if kind=='text':
        fields={'method','rights','normalization'}
        if 'acquisition' in value:fields.add('acquisition')
        closed(value,fields,'text origin')
        if method!='import' or value['normalization']!='NFC; LF newlines':fail('Unsupported text origin.','unsupported',409)
    elif kind=='image':
        fields={'method','rights','source_sha256'}
        if 'acquisition' in value:fields.add('acquisition')
        closed(value,fields,'image origin')
        if method!='import' or value['source_sha256']!=source['original']['artifact']['sha256']:fail('Image origin differs from its original bytes.')
    elif kind=='sequence':
        fields={'method','rights','adapter','run_sha256','frames_sha256'}
        if 'sequence_acquisition' in value:fields.add('sequence_acquisition')
        closed(value,fields,'sequence origin');meta=source['metadata']
        if method!='simulation_import' or value['adapter']!=meta['adapter'] or value['run_sha256']!=meta['run_sha256'] or value['frames_sha256']!=meta['manifest']['frames_sha256']:fail('Sequence origin differs from its owner metadata.')
    elif kind in ('mesh','pointcloud','volume'):
        fields={'method','rights','format','manifest_sha256'}|({'geometry_sha256'} if kind=='mesh' else set())
        closed(value,fields,'native source origin');meta=source['metadata']
        if method!=kind+'_import' or value['format']!=meta['manifest']['format'] or value['manifest_sha256']!=meta['manifest_sha256'] or kind=='mesh' and value['geometry_sha256']!=meta['manifest']['geometry_sha256']:fail('Native source provenance differs from its metadata.')
    elif kind=='audio':
        closed(value,{'method','rights','audio','source_sha256','transform'},'audio origin')
        if method!='import' or value['audio']!=source['metadata'] or value['source_sha256']!=source['asset']['artifact']['sha256'] or value['transform']!='none; original interleaved PCM WAV bytes preserved':fail('Audio origin differs from its original source.')
    else:
        key='project_source' if method=='project_data_import' else 'run_source'
        closed(value,{'method','rights','field_sequence','source_sha256',key},'scientific origin')
        if value['field_sequence']!=source['metadata'] or value['source_sha256']!=source['asset']['artifact']['sha256']:fail('Scientific source origin differs.')
        from scientific_fields import validate_source_declaration
        validate_source_declaration(method,value[key],value['source_sha256'],source['metadata']['source_bytes'])
    acquisition=value.get('acquisition',value.get('sequence_acquisition'))
    if 'acquisition' in value or 'sequence_acquisition' in value:
        _acquisition(acquisition,record,source,records)


def _record(row, record_id, source=None):
    if type(row) is not dict or row.get('kind') not in ('image', 'text', *ASSET_KINDS):
        fail('Unsupported data record kind.', 'unsupported', 409)
    extra = {row['kind']} if row['kind'] in ASSET_KINDS else set()
    optional = {'target_proposal'} if 'target_proposal' in row else set()
    closed(row, SNAPSHOT_FIELDS | extra | optional, 'Workbench record')
    if row['id'] != record_id:
        fail('Workbench record identity differs.')
    natural(row['revision']); sha(row['content_hash'])
    if row['source_revision'] is not None:
        natural(row['source_revision'])
    if row['source_sha256'] is not None:
        sha(row['source_sha256'])
    if row['pixel_hash'] is not None:
        sha(row['pixel_hash'])
    text_value(row['name'], 'Name')
    if strings(row['groups'], 'Groups') != row['groups'] or not row['groups'] or strings(row['parents'], 'Parents') != row['parents']:
        fail('Invalid Workbench groups or parents.')
    for parent in row['parents']:
        identity(parent, 'parent')
    if row['task'] not in TASKS or not row['task'].startswith(row['kind'] + '_') or row['review'] not in REVIEWS:
        fail('Invalid Workbench task or review.')
    if type(row['source_available']) is not bool or type(row['source_lineage_known']) is not bool:
        fail('Invalid historical source availability.')
    if type(row['provenance']) is not dict:
        fail('Invalid Workbench provenance.')
    text_value(row['provenance'].get('rights'), 'Rights note', 1000)
    correction = row['provenance'].get('rights_note_correction')
    if correction is not None:
        closed(correction, {'note', 'revision'}, 'rights correction')
        text_value(correction['note'], 'Rights note', 1000)
        natural(correction['revision'])
        if correction['revision'] > row['revision']:
            fail('Rights correction is newer than its record.')
    annotation_record = row
    deleted_geometry = row['task'] == 'image_detection' and (row['width'] is None or row['height'] is None)
    if deleted_geometry and source is not None:
        # Source deletion removes the live join, not the retained image geometry.
        # The complete codec validates this source history before acknowledging it.
        geometry = source['revisions'][-1]
        annotation_record = dict(row, width=geometry['width'], height=geometry['height'])
    # A standalone tombstone frame has no geometry to prove box fit. Its full
    # record decoder supplies retained source geometry; receipt validation also
    # requires an exact match to that fully validated retained state.
    if row['annotation'] is not None and not (deleted_geometry and source is None):
        if validate_annotation(row['task'], row['annotation'], annotation_record) != row['annotation']:
            fail('Workbench annotation is not canonical.')
    if row['review'] != 'draft' and row['annotation'] is None:
        fail('Reviewed record has no annotation.')
    if row['kind'] == 'text':
        text_value(row['text'], 'Text', MAX_TEXT)
        if hashlib.sha256(row['text'].encode()).hexdigest() != row['content_hash']:
            fail('Normalized text digest differs.')
    elif row['text'] is not None:
        fail('Non-text record contains text source.')
    if date(row['updated_at']) < date(row['created_at']):
        fail('Workbench update precedes creation.')
    return row


def validate_record_snapshot(record):
    """Pure Workbench capture validation for the producer history owner."""
    if type(record) is not dict:
        fail('Captured record must be an object.')
    _record(record, identity(record.get('id')))
    return copy.deepcopy(record)


def _response(row, record_id):
    closed(row, RESPONSE_FIELDS, 'response')
    if row['id'] != record_id:
        fail('Response identity differs.')
    identity(row['prompt_id'], 'prompt'); natural(row['revision'])
    text_value(row['completion'], 'Completion', MAX_TEXT)
    if row['review'] not in ('draft', 'human_reviewed'):
        fail('Invalid response review.')
    closed(row['provenance'], {'method', 'prompt_id', 'prompt_sha256', 'source_sha256'}, 'response provenance')
    if row['provenance']['method'] not in ('human_authored', 'agent_authored') or row['provenance']['prompt_id'] != row['prompt_id']:
        fail('Invalid response origin.')
    sha(row['provenance']['prompt_sha256']); sha(row['provenance']['source_sha256'])
    if date(row['updated_at']) < date(row['created_at']):
        fail('Response update precedes creation.')


def _judgment(row, record_id):
    closed(row, JUDGMENT_FIELDS, 'preference')
    if row['id'] != record_id:
        fail('Preference identity differs.')
    for key in ('id', 'prompt_id', 'left_id', 'right_id'):
        identity(row[key], key)
    for key in ('revision', 'parent_revision', 'source_revision', 'left_revision', 'right_revision'):
        natural(row[key])
    if row['left_id'] == row['right_id'] or row['outcome'] not in ('left', 'right', 'tie', 'abstain') or row['review'] not in ('draft', 'human_reviewed') or type(row['deleted']) is not bool:
        fail('Invalid preference meaning.')
    text_value(row['rationale'], 'Rationale', 4000)
    closed(row['provenance'], {'method'}, 'preference provenance')
    if row['provenance']['method'] != ('human_comparative_judgment' if row['review'] == 'human_reviewed' else 'draft_comparative_judgment'):
        fail('Preference origin differs from review.')
    if date(row['updated_at']) < date(row['created_at']):
        fail('Preference update precedes creation.')


def _audit_bindings(family,record_id,doc):
    """Audit hashes describe exact owner snapshots, never free-standing claims."""
    for fact in doc.get('audit',[]):
        action,details=fact['action'],fact['details']
        if action=='dataset.add_generated' and family=='workbench_record':
            origin=doc['origin']
            if origin.get('method')!='model_generated' or fact['target']!=origin['generation']['job_id']:
                fail('Generated source audit differs from its exact producer job.')
        elif fact['target']!=record_id:fail('Data audit target differs from its owning record.')
        expected=None
        if family=='workbench_record':
            states=[doc['current'],*doc['history'],*(e['snapshot'] for e in doc['events'])]
            if action.startswith('workbench.'):
                candidates=[s for s in states if s['revision']==details.get('revision') and s['source_revision']==details.get('source_revision') and digest(s)==details.get('content_sha256')]
                if not candidates:fail('Workbench audit snapshot is not retained.')
                state=candidates[0]
                expected=dict(revision=state['revision'],source_revision=state['source_revision'],content_sha256=digest(state))
                if action in ('workbench.save','workbench.approve_review','workbench.verify','workbench.correct_rights_note'):
                    expected.update(before_revision=state['revision']-1,before_source_revision=state['source_revision'])
            elif action in ('dataset.add','dataset.add_generated'):
                source=doc['source']
                if source['kind']!='image':fail('Image audit is attached to another modality.')
                expected=dict(sample_id=record_id,revision=1,source_sha256=source['revisions'][0]['sha256'])
            elif action=='dataset.save':
                source=doc['source'];sample=next((r for r in source.get('revisions',[]) if r['revision']==details.get('revision')),None)
                if sample is None:fail('Image audit source revision is not retained.')
                expected=dict(before_revision=sample['revision']-1,revision=sample['revision'],annotation_sha256=digest(sample['annotation']))
            elif action=='dataset.delete':
                if not doc['source'].get('deleted'):fail('Image deletion audit lacks its tombstone.')
                expected={}
            elif action in ('immutable_assets.admit','audio_assets.admit','scientific_fields.admit'):
                expected=dict(revision=1,source_sha256=doc['current']['content_hash'])
        elif family=='workbench_response':
            state=next((h for h in doc['history'] if h['response']['revision']==details.get('revision')),None)
            if state and action in ('workbench.save_response','workbench.approve_response'):
                r,p=state['response'],state['parent']
                expected=dict(before_revision=r['revision']-1,revision=r['revision'],prompt_id=p['id'],parent_revision=p['revision'],source_revision=p['source_revision'],content_sha256=digest(state))
        elif family=='workbench_preference':
            state=next((h for h in doc['history'] if h['judgment']['revision']==details.get('revision')),None)
            if state and action in ('preferences.save','preferences.delete'):
                expected=dict(revision=state['judgment']['revision'],review=state['judgment']['review'],binding_sha256=digest(state))
        elif family in ('saved_selection','saved_search'):
            owner='saved_selections' if family=='saved_selection' else 'saved_searches'
            state=next((h for h in doc['history'] if h['revision']==details.get('revision')),None)
            if state:
                if action==owner+'.create':expected=dict(revision=1,content_sha256=digest(state['items'] if family=='saved_selection' else state['criteria']))
                elif action==owner+'.rename':expected=dict(revision=state['revision'],name_sha256=hashlib.sha256(state['name'].encode()).hexdigest())
                elif action==owner+'.delete' and doc['deleted']:expected=dict(revision=state['revision'],retired_sha256=digest(state))
        elif family=='dataset_release' and action=='dataset_releases.create':
            expected=dict(release_sha256=record_id,format=doc['release_format'])
        if expected is None or encode_retained(expected)!=encode_retained(details):
            fail('Data audit details do not match the retained owner facts.')


def _decode_data_records(records):
    """Validate complete owned closure, without opening missing payloads or SQL."""
    if type(records) is not list or any(type(r) is not dict for r in records):
        fail('Project records must be a list.')
    owned, assets, responses, declarations, seen = [], {}, {}, {}, set()
    legacy = [r for r in records if r.get('family') == 'workbench_text']
    # Legacy parent closure may cross to a new record; validate each legacy
    # record locally, then check parent closure across all data families below.
    for item in legacy:
        single = copy.deepcopy(item)
        parents = single['document']['current']['parents']
        if parents:
            # The unchanged M1 decoder requires its family-local parent set.
            # Supply the legacy set, whose already-admitted parents stay v1.
            decode_text_records(legacy)
            break
        decode_text_records([single])
    for item in legacy:
        assets[item['id']] = item['document']
    for envelope in records:
        if type(envelope) is not dict:
            fail('Invalid project envelope.')
        family = envelope.get('family')
        if family not in FAMILIES:
            continue
        closed(envelope, {'family', 'id', 'document'}, 'data envelope')
        record_id, doc = envelope['id'], envelope['document']
        if family in ('dataset_release', 'dataset_exposure'):
            sha(record_id) if family == 'dataset_release' else identity(record_id)
        else:
            identity(record_id)
        if (family, record_id) in seen:
            fail('Duplicate data envelope.')
        seen.add((family, record_id))
        if type(doc) is not dict or doc.get('format') != FAMILIES[family]:
            fail('Unsupported data document format.', 'unsupported', 409)
        owned.append(envelope)
        if family == 'workbench_record':
            if record_id in assets:
                fail('An asset has more than one current domain family.')
            assets[record_id] = doc
        elif family == 'workbench_response':
            responses[record_id] = doc
    for envelope in records:
        if envelope.get('family') == 'project_artifact':
            declaration = envelope['document']
            closed(declaration, {'format', 'sha256', 'bytes'}, 'artifact declaration')
            if declaration['format'] != 'project_artifact_v1' or declaration['sha256'] != envelope['id']:
                fail('Artifact declaration identity differs.')
            sha(declaration['sha256'])
            if type(declaration['bytes']) is not int or not 0<=declaration['bytes']<=2**63-1:fail('Invalid artifact declared byte count.')
            declarations[envelope['id']] = declaration
    def binding(parent):
        _record(parent, identity(parent.get('id')))
        retained = assets.get(parent['id'])
        if retained is None:
            fail('Captured prompt/source is missing from data closure.')
        candidates = [retained['current'], *retained['history'], *(e['snapshot'] for e in retained.get('events',[]))]
        if not any(state == parent for state in candidates):
            fail('Captured prompt/source snapshot differs from its retained revision.')
    for envelope in owned:
        family, record_id, doc = envelope['family'], envelope['id'], envelope['document']
        if family == 'workbench_record':
            closed(doc, {'format', 'origin', 'source', 'current', 'history', 'events', 'audit'}, 'data record document')
            source, current, history = doc['source'], doc['current'], doc['history']
            if type(source) is not dict or source.get('kind') not in ('image', 'text', *ASSET_KINDS):
                fail('Invalid data source kind.')
            kind = source['kind']
            _record(current, record_id, source)
            if current['kind'] != kind or type(doc['origin']) is not dict or 'rights_note_correction' in doc['origin']:
                fail('Record source/origin differs.')
            if kind == 'text':
                closed(source, {'kind', 'original_text'}, 'text source')
                text_value(source['original_text'], 'Original text', MAX_TEXT)
                normalized = unicodedata.normalize('NFC', source['original_text'].replace('\r\n', '\n').replace('\r', '\n'))
                if current['text'] != normalized or current['source_sha256'] != hashlib.sha256(source['original_text'].encode()).hexdigest():
                    fail('Original text normalization/source hash differs.')
            elif kind == 'image':
                closed(source, {'kind', 'original', 'oriented', 'revisions', 'deleted'}, 'image source')
                original = _edge(source['original'], declarations, kind, 'original')
                oriented = _edge(source['oriented'], declarations, kind, 'oriented')
                if type(source['deleted']) is not bool or type(source['revisions']) is not list or not source['revisions']:
                    fail('Invalid image source lifecycle.')
                previous = 0
                for row in source['revisions']:
                    _source_row(row, record_id)
                    if row['revision'] != previous + 1 or row['sha256'] != original['sha256'] or any(row[k] != source['revisions'][0][k] for k in ('width','height','created_at')):
                        fail('Image source revisions or original hash differ.')
                    previous = row['revision']
                if current['content_hash'] != oriented['sha256']:
                    fail('Oriented image identity differs.')
            else:
                closed(source, {'kind', 'asset', 'metadata'}, 'immutable source')
                declaration = _edge(source['asset'], declarations, kind, 'original')
                if current['content_hash'] != declaration['sha256'] or current[kind] != source['metadata']:
                    fail('Immutable source metadata or content identity differs.')
                if type(source['metadata']) is not dict:
                    fail('Immutable metadata must be an object.')
                _source_metadata(kind,source['metadata'])
                expected_bytes=source['metadata'].get('bundle_bytes',source['metadata'].get('source_bytes'))
                if expected_bytes!=declaration['bytes'] or not set(source['metadata']['protected_groups'])<=set(current['groups']):
                    fail('Immutable byte count or protected groups differ.')
            _origin(doc['origin'],current,source,records)
            if type(history) is not list or not history:
                fail('Workbench annotation history is missing.')
            for revision, state in enumerate(history, 1):
                _record(state, record_id, source)
                if state['revision'] != revision or state['kind'] != kind or state['content_hash'] != current['content_hash']:
                    fail('Workbench immutable identity/history revisions differ.')
                if state['created_at']!=current['created_at'] or state['parents']!=current['parents'] or state['pixel_hash']!=current['pixel_hash']:
                    fail('Workbench history rewrites immutable source lineage.')
                if revision>1 and date(state['updated_at'])<date(history[revision-2]['updated_at']):
                    fail('Workbench annotation history reverses time.')
                origin = dict(state['provenance']); origin.pop('rights_note_correction', None)
                _origin(origin,state,source,records)
                if 'target_proposal' in state:
                    from project_producers import validate_target_proposal
                    validate_target_proposal(state['target_proposal'], state, records)
            if current['revision'] != len(history):
                fail('Current annotation revision differs from retained history.')
            annotation_fields={'id','kind','text','content_hash','pixel_hash','groups','parents','provenance','task','annotation','review','revision','created_at','updated_at'}
            if any(current[k]!=history[-1][k] for k in annotation_fields):
                fail('Current annotation differs from its final retained revision.')
            _events(doc['events']); _audit(doc['audit'])
            current_origin=dict(current['provenance']);current_origin.pop('rights_note_correction',None)
            if current_origin!=doc['origin']:fail('Current raw origin differs from Workbench provenance.')
            for event in doc['events']:
                state=event['snapshot']
                _record(state, record_id, source)
                if state['id']!=record_id or state['kind']!=kind or state['content_hash']!=current['content_hash']:
                    fail('Lifecycle event changes immutable asset identity.')
            if kind=='image':
                by_revision={r['revision']:r for r in source['revisions']}
                if source['deleted']!=(current['source_revision'] is None):fail('Image tombstone/current source differs.')
                for state in [current,*history,*(e['snapshot'] for e in doc['events'])]:
                    if state['source_revision'] is None:continue
                    sample=by_revision.get(state['source_revision'])
                    expected={'source_sha256':'sha256','book_id':'book_id','session_id':'session_id','source_split':'split','width':'width','height':'height','corner_annotation':'annotation'}
                    if sample is None or any(state[key]!=sample[value] for key,value in expected.items()):fail('Workbench image snapshot differs from its source revision.')
            else:
                for state in [current,*history,*(e['snapshot'] for e in doc['events'])]:
                    if type(state['source_revision']) is not int or state['source_revision']!=1 or state['source_split']!='unassigned' or state['source_sha256']!=current['source_sha256']:
                        fail('Immutable source revision/hash differs across history.')
        elif family == 'workbench_response':
            closed(doc, {'format', 'current', 'history', 'audit'}, 'response document')
            _response(doc['current'], record_id)
            if type(doc['history']) is not list or not doc['history']:
                fail('Response history is missing.')
            for revision, state in enumerate(doc['history'], 1):
                closed(state, {'response', 'parent'}, 'response capture')
                _response(state['response'], record_id); binding(state['parent'])
                if state['response']['revision'] != revision or state['response']['prompt_id'] != state['parent']['id'] or state['parent']['kind'] != 'text':
                    fail('Response prompt/revision binding differs.')
                if state['response']['provenance']['prompt_sha256']!=state['parent']['content_hash'] or state['response']['provenance']['source_sha256']!=state['parent']['source_sha256']:
                    fail('Response source hash differs from its captured prompt.')
                if state['response']['created_at']!=doc['current']['created_at'] or revision>1 and date(state['response']['updated_at'])<date(doc['history'][revision-2]['response']['updated_at']):
                    fail('Response history changes creation or reverses time.')
            if doc['current'] != doc['history'][-1]['response']:
                fail('Current response differs from its last history.')
            _audit(doc['audit'])
        elif family == 'workbench_preference':
            closed(doc, {'format', 'current', 'history', 'audit'}, 'preference document')
            _judgment(doc['current'], record_id)
            if type(doc['history']) is not list or not doc['history']:
                fail('Preference history is missing.')
            for revision, capture in enumerate(doc['history'], 1):
                closed(capture, {'judgment', 'parent', 'left', 'right'}, 'preference capture')
                judgment = capture['judgment']; _judgment(judgment, record_id); binding(capture['parent'])
                if judgment['revision'] != revision or judgment['prompt_id'] != capture['parent']['id'] or judgment['parent_revision'] != capture['parent']['revision'] or judgment['source_revision'] != capture['parent']['source_revision']:
                    fail('Preference prompt binding differs.')
                for side in ('left', 'right'):
                    answer = capture[side]; _response(answer, judgment[side + '_id'])
                    retained = responses.get(answer['id'])
                    if answer['revision'] != judgment[side + '_revision'] or answer['prompt_id'] != judgment['prompt_id'] or retained is None or not any(h['response'] == answer for h in retained['history']):
                        fail('Preference answer binding is missing or differs.')
            if doc['current'] != doc['history'][-1]['judgment']:
                fail('Current preference differs from its last history.')
            _audit(doc['audit'])
        elif family in ('saved_selection', 'saved_search'):
            closed(doc, {'format', 'current', 'history', 'deleted', 'audit'}, 'saved intent document')
            if type(doc['deleted']) is not bool or type(doc['history']) is not list or not doc['history']:
                fail('Invalid saved intent lifecycle.')
            for revision, state in enumerate(doc['history'], 1):
                fields = {'id', 'name', 'revision', 'created_at', 'updated_at', 'mode', 'schema_version'} | ({'items', 'member_count'} if family == 'saved_selection' else {'criteria'})
                closed(state, fields, 'saved intent snapshot')
                natural(state['revision'])
                if state['id'] != record_id or state['revision'] != revision or type(state['schema_version']) is not int or state['schema_version'] != 1 or state['mode'] != ('fixed' if family == 'saved_selection' else 'dynamic'):
                    fail('Saved intent identity differs.')
                text_value(state['name'], 'Saved intent name', 120); date(state['created_at']); date(state['updated_at'])
                if family == 'saved_search':
                    if criteria(state['criteria']) != state['criteria']:
                        fail('Saved search criteria differ.')
                else:
                    if type(state['items']) is not list or not 1 <= len(state['items']) <= 5000 or type(state['member_count']) is not int or state['member_count'] != len(state['items']):
                        fail('Saved membership count differs.')
                    member_ids = set()
                    for member in state['items']:
                        closed(member, {'id', 'name', 'kind', 'revision', 'source_revision', 'source_sha256', 'content_hash', 'pixel_hash'}, 'saved member')
                        if member['id'] in member_ids or member['id'] not in assets:
                            fail('Saved membership repeats or loses a source.')
                        member_ids.add(member['id']); natural(member['revision']); natural(member['source_revision'])
                        retained = assets[member['id']]
                        if not any(all(snapshot.get(key) == value for key, value in member.items()) for snapshot in [retained['current'], *retained['history'],*(e['snapshot'] for e in retained.get('events',[]))]):
                            fail('Saved member revision/source differs.')
            if doc['current'] != doc['history'][-1]:
                fail('Saved intent current value differs.')
            _audit(doc['audit'])
        elif family == 'dataset_release':
            closed(doc, {'format', 'asset', 'manifest', 'release_format', 'audit'}, 'release document')
            declaration = _edge(doc['asset'], declarations, 'release', 'frozen_archive')
            if declaration['sha256'] != record_id or type(doc['manifest']) is not dict:
                fail('Frozen release identity differs.')
            manifest=doc['manifest'];Releases.validate_project_manifest(manifest)
            if doc['release_format']!=manifest.get('format','canonical_v1'):fail('Release format differs from retained manifest.')
            exported={'split','asset','asset_sha256','export_group','export_split','exported_pixel_sha256','class_index',
                'audio_target_schema_version','audio_coordinate_contract','target_label','pcm_sha256','audio_family_sha256',
                'sample_rate_hz','channels','channel','start_frame','end_frame'}
            for state in manifest.get('records',[]):
                fields=SNAPSHOT_FIELDS|({state['kind']} if state.get('kind') in ASSET_KINDS else set())|({'target_proposal'} if 'target_proposal' in state else set())
                if set(state)-fields-exported:fail('Unknown frozen release record fields.')
                binding({key:state[key] for key in fields})
                if state.get('asset_sha256')!=state['content_hash']:fail('Frozen release source identity differs.')
            for parent in manifest.get('prompts',[]):binding(parent)
            for response in manifest.get('responses',[]):
                _response(response,identity(response.get('id')))
                retained=responses.get(response['id'])
                if retained is None or not any(h['response']==response for h in retained['history']):fail('Frozen release response binding is missing.')
            for judgment in [*manifest.get('judgments',[]),*manifest.get('competing_reviewed_judgments',[])]:
                _judgment(judgment,identity(judgment.get('id')))
                retained=next((r['document'] for r in owned if r['family']=='workbench_preference' and r['id']==judgment['id']),None)
                if retained is None or not any(h['judgment']==judgment for h in retained['history']):fail('Frozen release judgment binding is missing.')
            _audit(doc['audit'])
        elif family == 'dataset_exposure':
            closed(doc, {'format', 'id', 'record_id', 'source_hash', 'reason', 'run_id', 'release_id', 'created_at'}, 'exposure fact')
            if doc['id'] != record_id or doc['record_id'] not in assets:
                fail('Exposure source is missing.')
            sha(doc['source_hash']); identity(doc['run_id']); sha(doc['release_id'])
            if not any(r.get('family') == 'dataset_release' and r['id'] == doc['release_id'] for r in records):
                fail('Exposure release is missing.')
            text_value(doc['reason'], 'Exposure reason', 500); date(doc['created_at'])
    # Parent references use the full retained data closure, including tombstones.
    for record_id, doc in assets.items():
        for parent in doc['current']['parents']:
            if parent not in assets:
                fail('Workbench parent is missing from the project.')
        pending, visited = list(doc['current']['parents']), {record_id}
        while pending:
            parent = pending.pop()
            if parent == record_id:
                fail('Workbench source lineage contains a cycle.')
            if parent in visited:
                continue
            visited.add(parent); pending.extend(assets[parent]['current']['parents'])
    for envelope in owned:
        _audit_bindings(envelope['family'],envelope['id'],envelope['document'])
    if any(r['family']=='project_fork' for r in records):
        from project_data_fork import validate_records
        validate_records(records)
    return copy.deepcopy(owned)


def decode_data_records(records):
    try:
        return _decode_data_records(records)
    except WorkbenchError:
        raise
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError) as error:
        raise WorkbenchError('Malformed retained project data.') from error


DATA_ACTIONS = {
    'workbench.import_asset', 'workbench.save', 'workbench.approve_review', 'workbench.verify',
    'workbench.correct_rights_note', 'workbench.preserve_deleted_source', 'workbench.save_response', 'workbench.approve_response',
    'preferences.save', 'preferences.delete', 'saved_selections.create', 'saved_selections.rename', 'saved_selections.delete',
    'saved_searches.create', 'saved_searches.rename', 'saved_searches.delete', 'immutable_assets.admit',
    'audio_assets.admit', 'scientific_fields.admit', 'dataset.add', 'dataset.add_generated', 'dataset.save', 'dataset.delete', 'dataset_releases.create',
}
RUNTIME_DATA_OPERATIONS = frozenset(('data.runtime_generated_image','data.runtime_grounded_text',
                                   'data.runtime_caption','data.runtime_text_classification'))
DATA_OPERATIONS = {
    'data.import_text', 'data.import_image', 'data.import_bundle', 'data.import_audio', 'data.import_scientific',
    'data.annotate', 'data.correct_rights_note', 'data.save_image_source', 'data.delete_image_source',
    'data.save_response', 'data.save_preference', 'data.delete_preference',
    'data.create_selection', 'data.rename_selection', 'data.delete_selection',
    'data.create_search', 'data.rename_search', 'data.delete_search', 'data.freeze_release',
}


def _validate_operation_result(operation, result, records=None):
    """Closed result variants for the session's retained, inert retry receipts."""
    if operation not in DATA_OPERATIONS:
        return False
    if operation in ('data.import_text','data.import_image','data.import_bundle','data.import_audio','data.import_scientific','data.annotate'):
        validate_record_snapshot(result)
    elif operation == 'data.correct_rights_note':
        closed(result, {'record','changed'}, 'rights result'); validate_record_snapshot(result['record'])
        if type(result['changed']) is not bool:fail('Invalid rights change result.')
    elif operation == 'data.save_image_source':
        _source_row(result, identity(result.get('id')))
    elif operation == 'data.delete_image_source':
        closed(result, {'deleted','record'}, 'source deletion result'); identity(result['deleted'])
        validate_record_snapshot(result['record'])
        if result['record']['id'] != result['deleted'] or result['record']['source_available']:
            fail('Invalid source deletion result.')
    elif operation == 'data.save_response':
        closed(result, {'response','parent','changed'}, 'response result')
        _response(result['response'], identity(result['response'].get('id'))); validate_record_snapshot(result['parent'])
        if type(result['changed']) is not bool or result['response']['prompt_id'] != result['parent']['id']:
            fail('Invalid response result binding.')
    elif operation in ('data.save_preference','data.delete_preference'):
        closed(result, {'judgment','changed'}, 'preference result')
        _judgment(result['judgment'], identity(result['judgment'].get('id')))
        if type(result['changed']) is not bool:fail('Invalid preference change result.')
    elif operation in ('data.delete_selection','data.delete_search'):
        closed(result, {'deleted'}, 'intent deletion result'); identity(result['deleted'])
    elif operation in ('data.create_selection','data.rename_selection','data.create_search','data.rename_search'):
        family = 'saved_selection' if 'selection' in operation else 'saved_search'
        doc = dict(format=FAMILIES[family], current=result, history=[result], deleted=False, audit=[])
        # Reuse the complete intent validator with retained revision history.
        if records is not None:
            actual = next((r for r in records if r['family']==family and r['id']==result.get('id')),None)
            if actual is None or result not in actual['document']['history']:fail('Intent receipt result is not retained.')
        else:
            expected = {'id','name','revision','created_at','updated_at','mode','schema_version'} | ({'items','member_count'} if family=='saved_selection' else {'criteria'})
            closed(result, expected, 'intent result'); identity(result['id']); natural(result['revision'])
            text_value(result['name'],'Saved intent name',120);date(result['created_at']);date(result['updated_at'])
            if family=='saved_search':criteria(result['criteria'])
    else:
        required={'id','url','records','split_report'}
        if type(result) is not dict:
            fail('Invalid frozen release result.')
        format_name=result.get('format','canonical_v1')
        variants={'canonical_v1':required,'image_caption_v1':required|{'format','warnings'},
            'image_classification_v1':required|{'format','class_vocabulary','warnings'},
            'text_classification_v1':required|{'format','class_vocabulary','warnings'},
            'audio_classification_v1':required|{'format','class_vocabulary','warnings'},
            'text_corpus_v1':required|{'format','corpus_counts','artifact_bytes','warnings'},
            'text_instruction_v1':required|{'format','example_count','unique_prompt_count'},
            'text_preference_v1':required|{'format','example_count','unique_prompt_count'}}
        if type(format_name) is not str or format_name not in variants or set(result)!=variants[format_name]:
            fail('Invalid frozen release result variant.')
        sha(result['id']);natural(result['records'],0)
        if result['url']!='/api/workbench/releases/'+result['id']+'.zip' or type(result['split_report']) is not dict:
            fail('Frozen release result identity differs.')
    if records is not None:
        by_key={(r['family'],r['id']):r['document'] for r in records}
        def retained_record(row):
            document=by_key.get(('workbench_record',row['id'])) or by_key.get(('workbench_text',row['id']))
            if document is None or not any(row==state for state in [document['current'],*document['history'],*(e['snapshot'] for e in document.get('events',[]))]):
                fail('Operation result is not an exact retained record revision.')
            return document
        if operation in ('data.import_text','data.import_image','data.import_bundle','data.import_audio','data.import_scientific','data.annotate'):
            retained_record(result)
            if operation!='data.annotate' and result['revision']!=1:
                fail('Import result must identify the initial retained revision.')
        elif operation=='data.correct_rights_note':
            document=retained_record(result['record'])
            if result['changed'] and not any(e['operation']==operation and e['record_revision']==result['record']['revision'] for e in document.get('events',[])):
                fail('Rights correction result lacks its retained lifecycle event.')
        elif operation=='data.save_image_source':
            document=by_key.get(('workbench_record',result['id']))
            if document is None or document['source']['kind']!='image' or result not in document['source']['revisions']:
                fail('Source save result is not a retained source revision.')
        elif operation=='data.delete_image_source':
            document=retained_record(result['record'])
            if not document['source'].get('deleted') or not any(e['operation']==operation and e['deleted'] for e in document['events']):
                fail('Source deletion result has no retained tombstone.')
        elif operation=='data.save_response':
            document=by_key.get(('workbench_response',result['response']['id']))
            if document is None or not any(h=={'response':result['response'],'parent':result['parent']} for h in document['history']):
                fail('Response operation result differs from its exact captured binding.')
        elif operation in ('data.save_preference','data.delete_preference'):
            document=by_key.get(('workbench_preference',result['judgment']['id']))
            if document is None or not any(h['judgment']==result['judgment'] for h in document['history']):
                fail('Preference operation result is not retained.')
            if operation=='data.delete_preference' and not result['judgment']['deleted']:
                fail('Deleted preference result lacks its tombstone.')
        elif operation in ('data.delete_selection','data.delete_search'):
            family='saved_selection' if operation=='data.delete_selection' else 'saved_search'
            document=by_key.get((family,result['deleted']))
            if document is None or not document['deleted']:fail('Intent deletion result lacks its tombstone.')
        elif operation=='data.freeze_release':
            document=by_key.get(('dataset_release',result['id']))
            if document is None or document['manifest']['split_report']!=result['split_report']:
                fail('Release result is not bound to its retained frozen manifest.')
            manifest=document['manifest']
            if manifest.get('format','canonical_v1')!=result.get('format','canonical_v1'):fail('Frozen result format differs.')
            if 'class_vocabulary' in result and result['class_vocabulary']!=manifest['class_vocabulary']:fail('Frozen class vocabulary result differs.')
            count=len(manifest['records']) if 'records' in manifest else sum(j['outcome'] in ('left','right') for j in manifest['judgments']) if 'judgments' in manifest else len(manifest['responses'])
            if result['records']!=count:fail('Frozen release result count differs from manifest.')
    return True


def validate_operation_result(operation,result,records=None):
    try:
        return _validate_operation_result(operation,result,records)
    except WorkbenchError:
        raise
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError) as error:
        raise WorkbenchError('Malformed retained data operation result.') from error


class _DataAccess:
    def __init__(self, session):
        self.session, self.host, self.facts = session, session.access, None
    def _selected(self):
        from access import current_context, AccessError
        context=current_context()
        if context is not None and context.mode=='job':
            if context.catalog_id!=self.session.db.dataset_id:
                raise AccessError('Current job authority belongs to another project.')
            runtime=getattr(self.session,'runtime_access',None)
            if runtime is None or runtime.catalog_id!=self.session.db.dataset_id:
                raise AccessError('Current local job authority is unavailable.')
            return runtime
        return self.host
    def _context(self):
        # Merely observing a context never authenticates it. A local job must
        # still prove its exact local admission before returning any identity.
        from access import current_context
        authority=self._selected()
        if authority is self.host:
            authority.identity()
            return current_context()
        context=current_context()
        return authority.require_job(context.kind,context.job_id,context.admission_id,context.request_digest)
    def require(self, *args, **kwargs):
        if args and args[0]!='inspect':
            window=getattr(self.session,'_data_runtime_window',None)
            if self.facts is None or window and (not self.session.db.in_transaction or window['records'] is not None):
                fail('Project data writes require an uncaptured canonical transaction.', 'unavailable', 409)
        return self._selected().require(*args, **kwargs)
    def require_job(self, *args, **kwargs):
        return self._selected().require_job(*args, **kwargs)
    def identity(self):
        self._context()
        return self._selected().identity()
    def denial(self, *args, **kwargs):
        return self._selected().denial(*args, **kwargs)
    def audit(self, action, target=None, details=None, result='success'):
        window=getattr(self.session,'_data_runtime_window',None)
        if self.facts is None or window and window['records'] is not None or action not in DATA_ACTIONS or result != 'success':
            fail('Data effect is outside its canonical mutation.', 'unavailable', 409)
        scope='freeze' if action=='dataset_releases.create' else 'approve-review' if action=='dataset.save' else 'edit'
        actor = self._selected().require(scope, action, target)
        self.facts.append(dict(action=action, target=target, details=copy.deepcopy(details or {}), result=result,
                               actor_id=actor.actor_id, occurred_at=timestamp()))


class ProjectData:
    def __init__(self, session, image_sources=None, generation_entries=None):
        self.session, self.db, self.access, self.artifacts = session, session.db, session.access, session.artifacts
        self._authority = _DataAccess(session)
        self.context = SimpleNamespace(db=self.db, lock=self.db.lock, access=self._authority, path=self.db.path,
                                      project_sources={}, project_asset=self._asset, project_availability=self._available)
        self.workbench = Workbench(self.context)
        self.context.workbench = self.workbench
        if generation_entries is not None:
            self.context.generation_jobs = generation_entries
        if image_sources is None:
            from image_sources import ImageSources
            image_sources = ImageSources(self.context)
        self.images = image_sources
        self.context.add = self.images.add
        self.context.sample, self.context.rows = self.images.sample, self.images.rows
        self.selections, self.searches = SavedSelections(self.workbench), SavedSearches(self.workbench)
        self.releases = Releases(self.workbench)
        self._declarations = {}
        self._runtime_window = None
        self._sync_sources()

    @contextmanager
    def runtime_mutation(self, operation, key):
        """Open one trusted owner window inside an already owned SQL TX.

        The execution hook captures and publishes before outer COMMIT. This
        method neither owns that transaction nor calls Session.mutate.
        """
        if operation not in RUNTIME_DATA_OPERATIONS or type(key) is not str or not 1<=len(key)<=128:
            fail('Unsupported runtime data mutation.')
        if not self.db.in_transaction or getattr(self.session,'runtime_access',None) is None:
            fail('Runtime data capture requires current execution and its outer transaction.','unavailable',409)
        if self._runtime_window is not None or self._authority.facts is not None:
            fail('A data mutation window is already active.','conflict',409)
        from access import current_context
        context=current_context()
        if context is not None and context.mode=='job':
            self._authority._context()
            if operation!='data.runtime_generated_image' or context.kind!='synthetic':
                fail('This admitted job cannot own the requested data mutation.','unavailable',409)
            self._authority._selected().require('edit','dataset.add_generated',context.job_id)
        else:
            self.access.require('edit',operation)
        window=dict(operation=operation,key=key,before=None,records=None)
        self._runtime_window=window
        self.session._data_runtime_window=window
        self._authority.facts=[];self._pending_artifacts={};self._request_body={}
        def finish():
            if self._runtime_window is window:self.finish_runtime_mutation()
        self.db.on_commit(finish);self.db.on_rollback(finish)
        try:
            yield self
        except BaseException:
            finish()
            raise

    def finish_runtime_mutation(self):
        """Execution outcome owner also calls this after unknown SQL outcome."""
        self._runtime_window=None
        self.session._data_runtime_window=False
        self._authority.facts=None
        self._pending_artifacts={}
        self._sync_sources()

    def capture_runtime_changes(self, before_records, *, operation, key):
        window=self._runtime_window
        if (not self.db.in_transaction or window is None or operation!=window['operation'] or key!=window['key']):
            fail('Runtime data capture is outside its exact owned transaction.','unavailable',409)
        if window['records'] is not None:
            if before_records!=window['before']:fail('Runtime data capture checkpoint changed.','conflict',409)
            return copy.deepcopy(window['records'])
        if operation=='data.runtime_generated_image':
            for fact in self._authority.facts:
                if fact['action']=='dataset.add_generated':
                    self.workbench._sync_images(identity(fact['details'].get('sample_id')))
        captured=self._capture(None,before_records,operation,key)['records']
        window['before']=copy.deepcopy(before_records);window['records']=copy.deepcopy(captured)
        return captured

    def _sync_sources(self):
        records = self.session.snapshot['records']
        from project_fork import active_records
        active = active_records(records, project_id=self.session.project_id)
        self.context.project_sources = {r['id']: copy.deepcopy(r['document']['source']) for r in active if r['family'] == 'workbench_record'}
        self._declarations = {r['id']: r['document'] for r in records if r['family'] == 'project_artifact'}

    def _available(self, record_id):
        source = self.context.project_sources.get(record_id)
        if source is None or source['kind'] == 'text':
            return True
        if source['kind'] == 'image':
            if source['deleted']:
                return False
            edges = (source['original'], source['oriented'])
        else:
            edges = (source['asset'],)
        # Browsing metadata checks presence without repeatedly hashing every
        # large payload. Every actual consumer obtains a verified snapshot.
        return all(self.artifacts.inspect(self._declarations[e['artifact']['sha256']])['state'] != 'missing' for e in edges)

    def _asset(self, record_id, kind):
        source = self.context.project_sources[record_id]
        edge = source['oriented'] if kind == 'image' else source['asset']
        declaration = self._declarations[edge['artifact']['sha256']]
        return self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')}, maximum_bytes=40 * 1024 * 1024)

    def _publish(self, raw, kind, role, media_type):
        declaration = dict(format='project_artifact_v1', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.artifacts.publish_bytes(raw, declaration)
        self._pending_artifacts[declaration['sha256']] = declaration
        return dict(artifact=dict(namespace=self.session.snapshot['project_id'], sha256=declaration['sha256']),
                    media_type=media_type, kind=kind, role=role, preservation='unique', required_for=['inspect', 'release'])

    def _require_record(self, record_id, *, extended=False):
        from project_fork import active_records
        snapshot = self.session.snapshot
        for item in active_records(snapshot['records'], project_id=snapshot['project_id']):
            if item['id'] == record_id and item['family'] in ('workbench_record', 'workbench_text'):
                if extended and item['family'] == 'workbench_text':
                    fail('This operation requires an explicitly converted data record.', 'unsupported', 409)
                return item
        fail('Project data record is unavailable.', 'unavailable', 404)

    def _permission(self, operation, target, body):
        scope='freeze' if operation=='data.freeze_release' else 'approve-review' if operation=='data.save_image_source' else 'edit'
        self.access.require(scope, operation, target)
        if operation in ('data.annotate', 'data.save_response', 'data.save_preference') and body.get('review') == 'human_reviewed':
            self.access.require('approve-review', operation, target, owner_only=True)
        if operation == 'data.annotate' and body.get('review') == 'programmatically_verified':
            fail('Programmatic verification requires its owned verifier.', 'unsupported', 409)

    def _mutate(self, operation, target, body, expected_checkpoint, key, invoke):
        with self.access.lock:
            if type(body) is not dict:
                fail('Data mutation body must be an object.')
            self._permission(operation, target, body)
            with self.session.lock, self.db.lock:
                self.session.check()
                if operation in ('data.annotate','data.correct_rights_note','data.save_image_source','data.delete_image_source'):
                    self._require_record(target,extended=operation!='data.annotate')
                legacy = self._legacy_replay(operation, target, body, key)
                if legacy is not None:
                    return legacy
            self._pending_artifacts, self._authority.facts = {}, []
            self._request_body = copy.deepcopy(body)
            try:
                scope='freeze' if operation=='data.freeze_release' else 'approve-review' if operation=='data.save_image_source' else 'edit'
                result = self.session.mutate(operation, target, body, expected_checkpoint, key, invoke,
                    lambda result, before: self._capture(result, before, operation, key),scope=scope)
                self._sync_sources()
                return result
            finally:
                self._authority.facts = None

    def _legacy_replay(self, operation, target, body, key):
        """Retain M1 request meaning after the shared M2 session cutover."""
        records = self.session.snapshot['records']
        from project_fork import active_records
        records = active_records(records, project_id=self.session.project_id)
        if any(r['family']=='project_operation' and r['document']['request_key']==key for r in records):
            return None
        if operation not in ('data.import_text','data.annotate'):
            return None
        action = 'import_text' if operation=='data.import_text' else 'annotate'
        request_hash = hashlib.sha256(encode(dict(action=action,target=target,body=body)).encode()).hexdigest()
        for envelope in records:
            if envelope['family']!='workbench_text':continue
            doc=envelope['document']
            for receipt in doc['operations']:
                if receipt['request_key']!=key:continue
                if receipt['request_sha256']!=request_hash:
                    fail('Request key already has different M1 input.','conflict',409)
                if self.session.store.reconcile(key,request_hash) is None:
                    fail('M1 text operation has no canonical publication receipt.')
                return copy.deepcopy(doc['history'][receipt['revision']-1])
        return None

    def import_text(self, body, expected_checkpoint, key):
        if type(body) is not dict or set(body) - {'kind','text', 'name', 'groups', 'parents', 'rights'} or body.get('kind','text')!='text':
            fail('Import exactly text and its source metadata.')
        return self._mutate('data.import_text', None, body, expected_checkpoint, key,
                            lambda: self.workbench.import_asset(dict(body, kind='text')))

    def import_image(self, body, expected_checkpoint, key):
        if type(body) is not dict or body.get('kind', 'image') != 'image':
            fail('Expected an image import.')
        return self._mutate('data.import_image', None, body, expected_checkpoint, key,
                            lambda: self.workbench.import_asset(dict(body, kind='image')))

    def import_bundle(self, kind, prepared, body, expected_checkpoint, key):
        if kind not in ('sequence', 'mesh', 'pointcloud', 'volume'):
            fail('Unsupported immutable bundle kind.', 'unsupported', 409)
        # prepared belongs to the selected existing parser, not a public RPC.
        request = dict(kind=kind, body=body, bundle_sha256=hashlib.sha256(prepared['bundle']).hexdigest())
        def invoke():
            owner=self.workbench.immutable_owners[kind]
            owner.validate_project_source(prepared['bundle'],dict(prepared['metadata'],bundle_bytes=len(prepared['bundle'])))
            return owner.admit(prepared,body)
        return self._mutate('data.import_bundle', None, request, expected_checkpoint, key,invoke)

    def import_audio(self, body, expected_checkpoint, key):
        return self._mutate('data.import_audio', None, body, expected_checkpoint, key, lambda: self.workbench.audio.admit(body))

    def import_scientific(self, raw, body, source, expected_checkpoint, key):
        request = dict(body=body, source=source, sha256=hashlib.sha256(raw).hexdigest())
        return self._mutate('data.import_scientific', None, request, expected_checkpoint, key,
                            lambda: self.workbench.scientific.admit(raw, body, source))

    def annotate(self, record_id, body, expected_checkpoint, key):
        return self._mutate('data.annotate', record_id, body, expected_checkpoint, key, lambda: self.workbench.save(record_id, body))

    def correct_rights_note(self, record_id, body, expected_checkpoint, key):
        return self._mutate('data.correct_rights_note', record_id, body, expected_checkpoint, key,
                            lambda: self.workbench.correct_rights_note(record_id, body))

    def save_image_source(self, record_id, body, expected_checkpoint, key):
        def invoke():
            if not self._available(record_id):
                fail('Image source bytes are unavailable.', 'unavailable', 409)
            return self.images.save(record_id, body)
        return self._mutate('data.save_image_source', record_id, body, expected_checkpoint, key, invoke)

    def delete_image_source(self, record_id, body, expected_checkpoint, key):
        def invoke():
            if not hasattr(self.context,'generation_jobs'):
                fail('Image deletion requires its inert producer entry owner.','unavailable',409)
            # Verify/preserve the exact source before the image owner can remove
            # its disposable projection files. Canonical artifacts survive it.
            source = self.context.project_sources[record_id]
            for edge in (source['original'], source['oriented']):
                declaration = self._declarations[edge['artifact']['sha256']]
                self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')}, maximum_bytes=40 * 1024 * 1024)
            result = self.images.delete(record_id, body)
            return {'deleted': record_id, 'record': self.workbench._get(record_id)}
        return self._mutate('data.delete_image_source', record_id, body, expected_checkpoint, key, invoke)

    def save_response(self, body, expected_checkpoint, key):
        return self._mutate('data.save_response', body.get('id') if isinstance(body,dict) else None, body, expected_checkpoint, key, lambda: self.workbench.save_response(body))

    def save_preference(self, body, expected_checkpoint, key):
        return self._mutate('data.save_preference', body.get('id') if isinstance(body,dict) else None, body, expected_checkpoint, key, lambda: self.workbench.preferences.save(body))

    def delete_preference(self, body, expected_checkpoint, key):
        return self._mutate('data.delete_preference', body.get('id') if isinstance(body,dict) else None, body, expected_checkpoint, key, lambda: self.workbench.preferences.delete(body))

    def create_selection(self, body, expected_checkpoint, key):
        return self._mutate('data.create_selection', None, body, expected_checkpoint, key, lambda: self.selections.create(body))
    def rename_selection(self, record_id, body, expected_checkpoint, key):
        return self._mutate('data.rename_selection', record_id, body, expected_checkpoint, key, lambda: self.selections.mutate(record_id, 'rename', body))
    def delete_selection(self, record_id, body, expected_checkpoint, key):
        return self._mutate('data.delete_selection', record_id, body, expected_checkpoint, key, lambda: self.selections.mutate(record_id, 'delete', body))
    def create_search(self, body, expected_checkpoint, key):
        return self._mutate('data.create_search', None, body, expected_checkpoint, key, lambda: self.searches.create(body))
    def rename_search(self, record_id, body, expected_checkpoint, key):
        return self._mutate('data.rename_search', record_id, body, expected_checkpoint, key, lambda: self.searches.mutate(record_id, 'rename', body))
    def delete_search(self, record_id, body, expected_checkpoint, key):
        return self._mutate('data.delete_search', record_id, body, expected_checkpoint, key, lambda: self.searches.mutate(record_id, 'delete', body))

    def preview_release(self, body):
        return self._read('dataset_releases.preview', lambda: self.releases.preview(body))

    def freeze_release(self, body, expected_checkpoint, key):
        return self._mutate('data.freeze_release', None, body, expected_checkpoint, key, lambda: self.releases._create(body))

    def _read(self, action, invoke, target=None):
        with self.access.lock, self.session.lock, self.db.lock:
            self.access.require('inspect', action, target)
            self.session.check()
            self._sync_sources()
            result = invoke()
            self.session.check()
            return result

    def query(self, options=None):
        return self._read('workbench.query', lambda: self.workbench.query(options or {}))
    def get(self, record_id):
        return self._read('workbench.get', lambda: self.workbench.get(record_id), record_id)
    def history(self, record_id):
        return self._read('workbench.history', lambda: self.workbench.history(record_id), record_id)
    def responses(self, record_id):
        return self._read('workbench.responses', lambda: self.workbench.responses(record_id), record_id)
    def response_history(self, record_id):
        return self._read('workbench.response_history', lambda: self.workbench.response_history(record_id), record_id)
    def preferences(self, prompt_id):
        return self._read('preferences.list', lambda: self.workbench.preferences.list(prompt_id), prompt_id)
    def preference_history(self, record_id):
        return self._read('preferences.history', lambda: self.workbench.preferences.history(record_id), record_id)
    def load_selection(self, record_id):
        return self._read('saved_selections.load', lambda: self.selections.load(record_id), record_id)
    def list_selections(self):
        return self._read('saved_selections.list', self.selections.list)
    def list_searches(self):
        return self._read('saved_searches.list', self.searches.list)

    def availability(self, record_id):
        def inspect():
            envelope=self._require_record(record_id)
            if envelope['family']=='workbench_text':
                return dict(record_id=record_id,kind='text',deleted=False,artifacts=[])
            source=envelope['document']['source'];kind=source['kind']
            edges=[] if kind=='text' else [source['original'],source['oriented']] if kind=='image' else [source['asset']]
            return dict(record_id=record_id,kind=kind,deleted=source.get('deleted',False),artifacts=[
                dict(role=edge['role'],reference=edge['artifact'],observation=self.artifacts.status(self._declarations[edge['artifact']['sha256']])) for edge in edges])
        return self._read('workbench.get',inspect,record_id)

    def _capture_source(self, row, prior):
        kind, record_id = row['kind'], row['id']
        if kind == 'text':
            original = self.db.execute('SELECT original_text FROM workbench_records WHERE id=%s', (record_id,)).fetchone()[0]
            return dict(kind=kind, original_text=original)
        if kind == 'image':
            source = copy.deepcopy(prior['source']) if prior else None
            sample = self.db.execute('SELECT * FROM samples WHERE id=%s', (record_id,)).fetchone()
            if sample is None:
                if source is None:
                    fail('Deleted image lost its preserved source.', 'invalid', 409)
                source['deleted'] = True
                return source
            sample = dict(sample)
            sample['annotation'] = json.loads(sample['annotation']) if sample['annotation'] is not None else None
            if source is None:
                folder = self.db.path / 'images' / record_id
                source = dict(kind='image',
                    original=self._publish((folder / 'source').read_bytes(), kind, 'original', 'application/octet-stream'),
                    oriented=self._publish((folder / 'image.png').read_bytes(), kind, 'oriented', 'image/png'),
                    revisions=[], deleted=False)
            if not source['revisions'] or source['revisions'][-1] != sample:
                source['revisions'].append(sample)
            return source
        if prior:
            return copy.deepcopy(prior['source'])
        if kind in ('sequence', 'mesh', 'pointcloud', 'volume'):
            raw = bytes(self.db.execute('SELECT bundle FROM workbench_' + kind + '_assets WHERE id=%s', (record_id,)).fetchone()[0])
            media = 'application/zip'
        elif kind == 'audio':
            raw = (self.db.path / 'audio' / record_id / 'source.wav').read_bytes(); media = 'audio/wav'
        else:
            raw = self.workbench.scientific._capture(record_id); media = 'application/zip'
        return dict(kind=kind, asset=self._publish(raw, kind, 'original', media), metadata=copy.deepcopy(row[kind]))

    def _capture(self, result, before_records, operation, key):
        before = {(r['family'], r['id']): r for r in before_records}
        changed = []
        for identity_row in self.db.execute('SELECT id FROM workbench_records ORDER BY id'):
            record_id = identity_row[0]
            legacy = before.get(('workbench_text', record_id))
            if legacy:
                # M1 retains its unchanged decoder and annotation semantics.
                row = self.workbench._get(record_id)
                prior = copy.deepcopy(legacy)
                if row != prior['document']['current']:
                    if operation != 'data.annotate':
                        fail('M1 text lifecycle requires explicit conversion.', 'unsupported', 409)
                    doc = prior['document']; doc['current'] = row; doc['history'].append(row)
                    facts = [f for f in self._authority.facts if f['target'] == record_id]
                    doc['audit'].extend(facts)
                    request = dict(action='annotate', target=record_id, body=self._request_body)
                    doc['operations'].append(dict(request_key=key, request_sha256=digest(request), action='annotate', target=record_id, revision=row['revision']))
                    changed.append(prior)
                continue
            old = before.get(('workbench_record', record_id))
            old_doc = old['document'] if old else None
            row = self.workbench._get(record_id)
            if old_doc is not None and all(row.get(k)==v for k,v in old_doc['current'].items() if k!='source_available'):
                # Physical payload availability is current local observation,
                # never an authored change to a retained checkpoint snapshot.
                row = copy.deepcopy(old_doc['current'])
            raw = self.db.execute('SELECT provenance_json FROM workbench_records WHERE id=%s', (record_id,)).fetchone()[0]
            history = [json.loads(r[0]) for r in self.db.execute('SELECT snapshot FROM workbench_history WHERE id=%s ORDER BY revision', (record_id,))]
            source = self._capture_source(row, old_doc)
            doc = dict(format='workbench_record_v1', origin=json.loads(raw), source=source, current=row, history=history,
                       events=copy.deepcopy(old_doc['events']) if old_doc else [], audit=copy.deepcopy(old_doc['audit']) if old_doc else [])
            if old_doc is None or any(doc[field] != old_doc[field] for field in ('origin', 'source', 'current', 'history')):
                doc['events'].append(dict(operation=operation, request_key=key, record_revision=row['revision'], source_revision=row['source_revision'],
                                          deleted=source.get('deleted', False), occurred_at=timestamp(),snapshot=copy.deepcopy(row)))
                doc['audit'].extend(f for f in self._authority.facts if f['target'] == record_id or f['details'].get('sample_id') == record_id)
                changed.append(dict(family='workbench_record', id=record_id, document=doc))
        for family, table, history_table, key_name in (
            ('workbench_response', 'workbench_responses', 'workbench_response_history', 'response'),
            ('workbench_preference', 'workbench_preferences', 'workbench_preference_history', 'judgment')):
            for row in self.db.execute('SELECT id FROM ' + table + ' ORDER BY id'):
                record_id = row[0]
                current = self.workbench._response(record_id) if family == 'workbench_response' else self.workbench.preferences._get(record_id)
                history = [json.loads(r[0]) for r in self.db.execute('SELECT snapshot FROM ' + history_table + ' WHERE id=%s ORDER BY revision', (record_id,))]
                old = before.get((family, record_id))
                if old is None or old['document']['current'] != current or old['document']['history'] != history:
                    audit = copy.deepcopy(old['document']['audit']) if old else []
                    audit.extend(f for f in self._authority.facts if f['target'] == record_id)
                    changed.append(dict(family=family, id=record_id, document=dict(format=FAMILIES[family], current=current, history=history, audit=audit)))
        for family, table, owner in (('saved_selection', 'saved_selections', self.selections), ('saved_search', 'saved_searches', self.searches)):
            live = {r[0] for r in self.db.execute('SELECT id FROM ' + table)}
            from project_fork import active_records
            all_ids = live | {r['id'] for r in active_records(before_records, project_id=self.session.project_id) if r['family'] == family}
            for record_id in all_ids:
                old = before.get((family, record_id))
                current = owner._get(record_id) if record_id in live else copy.deepcopy(old['document']['current'])
                deleted = record_id not in live
                if old is None or old['document']['current'] != current or old['document']['deleted'] != deleted:
                    history = copy.deepcopy(old['document']['history']) if old else []
                    if not history or history[-1] != current:
                        history.append(current)
                    audit = copy.deepcopy(old['document']['audit']) if old else []
                    audit.extend(f for f in self._authority.facts if f['target'] == record_id)
                    changed.append(dict(family=family, id=record_id, document=dict(format=FAMILIES[family], current=current, history=history, deleted=deleted, audit=audit)))
        if operation == 'data.freeze_release':
            release_id = result['id']
            raw, _ = self.releases.capture_input(release_id, release_id, 40 * 1024 * 1024)
            manifest = self.releases.project_manifest(raw)
            edge = self._publish(raw, 'release', 'frozen_archive', 'application/zip')
            old = before.get(('dataset_release', release_id))
            if old is None:
                changed.append(dict(family='dataset_release', id=release_id, document=dict(format='dataset_release_v1', asset=edge,
                    manifest=manifest, release_format=self._request_body.get('format', 'canonical_v1'), audit=copy.deepcopy(self._authority.facts))))
        for row in self.db.execute('SELECT * FROM workspace_exposures'):
            record = dict(row)
            if ('dataset_exposure', record['id']) not in before:
                changed.append(dict(family='dataset_exposure', id=record['id'], document=dict(format='dataset_exposure_v1', **record)))
        for artifact_id, declaration in self._pending_artifacts.items():
            changed.append(dict(family='project_artifact', id=artifact_id, document=declaration))
        if operation=='data.delete_image_source':
            generation=getattr(self.context,'generation_jobs',None)
            if generation is not None:
                changed.extend(generation.capture_records())
        unique={}
        for envelope in changed:
            identity=(envelope['family'],envelope['id'])
            if identity in unique and unique[identity]!=envelope:
                fail('Two data owners captured conflicting canonical facts.')
            unique[identity]=envelope
        # The session appends one operation receipt then validates the complete
        # merged family closure; local upserts alone are not an inventory.
        return {'records': list(unique.values()), 'result': copy.deepcopy(result)}

    def restore(self, snapshot=None):
        snapshot = snapshot or self.session.snapshot
        if snapshot != self.session.snapshot:
            fail('Data reconstruction snapshot is stale.', 'stale_project', 409)
        owned = decode_data_records(snapshot['records'])
        self._sync_sources()
        # Validate present source bytes through the existing semantic owners
        # before touching any selected SQL row. Missing bytes retain metadata.
        self._verify_sources(owned)
        from project_fork import active_records
        active = active_records(snapshot['records'], project_id=self.session.project_id)
        identities = {(r['family'], r['id']) for r in active}
        owned = [r for r in owned if (r['family'], r['id']) in identities]
        with self.db.lock, self.db.transaction():
            for table in ('workbench_history', 'workbench_rights_notes', 'workbench_target_proposals', 'workbench_responses', 'workbench_response_history',
                          'workbench_preferences', 'workbench_preference_history', 'saved_selections', 'saved_searches', 'workbench_deleted_sources',
                          'workbench_sequence_assets', 'workbench_mesh_assets', 'workbench_pointcloud_assets', 'workbench_volume_assets', 'samples', 'workbench_records', 'workspace_exposures'):
                self.db.execute('DELETE FROM ' + table)
            asset_docs = [r for r in owned if r['family'] == 'workbench_record']
            for legacy in (r for r in active if r['family'] == 'workbench_text'):
                doc = legacy['document']
                asset_docs.append(dict(family='workbench_record', id=legacy['id'], document=dict(current=doc['current'], history=doc['history'],
                    origin=doc['current']['provenance'], source=dict(kind='text', original_text=doc['original_text']))))
            for envelope in asset_docs:
                doc = envelope['document']; row, source = doc['current'], doc['source']
                if source['kind'] == 'image':
                    if not source['deleted']:
                        sample = source['revisions'][-1]
                        self.db.execute('INSERT INTO samples (id,sha256,filename,width,height,book_id,session_id,split,created_at,updated_at,revision,annotation) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                            tuple(encode_retained(sample[k]) if k == 'annotation' and sample[k] is not None else sample[k] for k in ('id','sha256','filename','width','height','book_id','session_id','split','created_at','updated_at','revision','annotation')))
                    else:
                        sample = source['revisions'][-1]
                        self.db.execute('INSERT INTO workbench_deleted_sources VALUES (%s,%s,%s,%s)', (row['id'],sample['book_id'],sample['session_id'],sample['split']))
                self.db.execute('''INSERT INTO workbench_records
                    (id,kind,name,text,original_text,content_hash,pixel_hash,groups_json,parents_json,provenance_json,task,annotation_json,review,revision,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (row['id'],row['kind'],row['name'],row['text'],source.get('original_text'),row['content_hash'],row['pixel_hash'],
                     encode_retained(row['groups']),encode_retained(row['parents']),encode_retained(doc['origin']),row['task'],
                     encode_retained(row['annotation']) if row['annotation'] is not None else None,row['review'],row['revision'],row['created_at'],row['updated_at']))
                correction = row['provenance'].get('rights_note_correction')
                if correction:
                    self.db.execute('INSERT INTO workbench_rights_notes VALUES (%s,%s,%s)', (row['id'],correction['note'],correction['revision']))
                if 'target_proposal' in row:
                    self.db.execute('INSERT INTO workbench_target_proposals VALUES (%s,%s)', (row['id'],encode_retained(row['target_proposal'])))
                for state in doc['history']:
                    self.workbench._history(state)
            for envelope in owned:
                family, doc, record_id = envelope['family'], envelope['document'], envelope['id']
                if family == 'workbench_response':
                    r=doc['current']
                    self.db.execute('INSERT INTO workbench_responses VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                        (record_id,r['prompt_id'],r['revision'],r['completion'],r['review'],encode_retained(r['provenance']),r['created_at'],r['updated_at']))
                    for revision, state in enumerate(doc['history'],1):
                        self.db.execute('INSERT INTO workbench_response_history VALUES (%s,%s,%s)', (record_id,revision,encode_retained(state)))
                elif family == 'workbench_preference':
                    r=doc['current']
                    self.db.execute('INSERT INTO workbench_preferences VALUES (%s,%s,%s,%s)', (record_id,r['prompt_id'],r['revision'],encode_retained(r)))
                    for revision,state in enumerate(doc['history'],1):
                        self.db.execute('INSERT INTO workbench_preference_history VALUES (%s,%s,%s)', (record_id,revision,encode_retained(state)))
                elif family == 'saved_selection' and not doc['deleted']:
                    r=doc['current']
                    self.db.execute('INSERT INTO saved_selections VALUES (%s,%s,%s,%s,%s,%s,%s)', (record_id,r['name'],r['revision'],encode_retained(r['items']),r['member_count'],r['created_at'],r['updated_at']))
                elif family == 'saved_search' and not doc['deleted']:
                    r=doc['current']
                    self.db.execute('INSERT INTO saved_searches VALUES (%s,%s,%s,%s,%s,%s)', (record_id,r['name'],r['revision'],encode_retained(r['criteria']),r['created_at'],r['updated_at']))
                elif family == 'dataset_exposure':
                    self.db.execute('INSERT INTO workspace_exposures VALUES (%s,%s,%s,%s,%s,%s,%s)', tuple(doc[k] for k in ('id','record_id','source_hash','reason','run_id','release_id','created_at')))
            self.session.check()
        self._materialize_images_and_releases(owned)
        return snapshot

    def _verify_sources(self, owned):
        for envelope in owned:
            if envelope['family']=='dataset_release':
                doc=envelope['document'];declaration=self._declarations[doc['asset']['artifact']['sha256']]
                status=self.artifacts.status(declaration)['state']
                if status=='corrupt':fail('Frozen release artifact is corrupt.')
                if status=='verified':
                    raw=self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')},maximum_bytes=40*1024*1024)
                    if self.releases.project_manifest(raw)!=doc['manifest']:fail('Frozen manifest differs from the exact archive bytes.')
                continue
            if envelope['family'] != 'workbench_record':
                continue
            doc = envelope['document']; source, row = doc['source'], doc['current']; kind=source['kind']
            if kind == 'text':
                continue
            edges=[source['original'],source['oriented']] if kind=='image' else [source['asset']]
            states=[self.artifacts.status(self._declarations[e['artifact']['sha256']])['state'] for e in edges]
            if 'corrupt' in states:fail('Stored data artifact is corrupt.')
            if 'missing' in states:continue
            if kind == 'image':
                from image_sources import validate_project_source
                payloads=[]
                for edge in (source['original'],source['oriented']):
                    declaration=self._declarations[edge['artifact']['sha256']]
                    payloads.append(self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')},maximum_bytes=40*1024*1024))
                validate_project_source(*payloads,source['revisions'][-1],row['pixel_hash'])
            else:
                # Historical source verification uses its exact envelope;
                # only current editable records populate the runtime resolver.
                declaration=self._declarations[source['asset']['artifact']['sha256']]
                raw=self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')},
                                             maximum_bytes=40*1024*1024)
                self.workbench.immutable_owners[kind].validate_project_source(raw,source['metadata']) if kind in ('sequence','mesh','pointcloud','volume') else None
                if kind == 'audio':
                    from audio_assets import parse_wav
                    actual,_=parse_wav(raw); expected=dict(source['metadata']);expected.pop('protected_groups',None)
                    if actual!=expected:fail('Audio metadata differs from original bytes.')
                elif kind == 'field_sequence':
                    from scientific_fields import parse_bundle,validate_source
                    if parse_bundle(raw)!=source['metadata']:fail('Scientific metadata differs from original bytes.')
                    origin=doc['origin']
                    if origin['method']=='project_fork':
                        from project_data_fork import source_origin
                        origin=source_origin(origin,self.session.snapshot['records'])
                    method=origin['method']; key='project_source' if method=='project_data_import' else 'run_source'
                    validate_source(method,origin[key],raw)

    def _materialize_images_and_releases(self, owned):
        for envelope in owned:
            family,doc=envelope['family'],envelope['document']
            paths=[]
            if family=='workbench_record' and doc['source']['kind']=='image' and not doc['source']['deleted']:
                folder=self.db.path/'images'/envelope['id'];folder.mkdir(parents=True,exist_ok=True)
                paths=[(folder/'source',doc['source']['original']),(folder/'image.png',doc['source']['oriented'])]
            elif family=='dataset_release':
                paths=[(self.releases.path/(envelope['id']+'.zip'),doc['asset'])]
            for path,edge in paths:
                declaration=self._declarations[edge['artifact']['sha256']]
                if self.artifacts.status(declaration)['state']=='verified':
                    path.write_bytes(self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')},maximum_bytes=40*1024*1024))
