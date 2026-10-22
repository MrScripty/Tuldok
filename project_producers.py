"""Inert, origin-scoped producer observations and exact evidence payloads.

No producer constructor, admission, worker, cancellation or resume API enters this
owner. Four closed codecs preserve the scientific observations their existing
owners validate. Local transport configuration and admission envelopes have an
explicit exclusion; unknown fields fail instead of disappearing during export.
"""
import base64
import copy
from datetime import datetime
import hashlib
import json
import re

from access import authorized
import caption_proposals
import grounded_candidates
import image_generation
import pumas_operations as pumas
import synthetic
import text_classification_proposals
from workbench import WorkbenchError, encode, text_value, validate_annotation

FAMILIES = {
    'generation_history': 'project_generation_history_v1',
    'grounded_history': 'project_grounded_history_v1',
    'caption_proposal_history': 'project_caption_proposal_history_v1',
    'text_proposal_history': 'project_text_proposal_history_v1',
}
TABLES = {'generation_history': 'generation_jobs', 'grounded_history': 'grounded_jobs',
          'caption_proposal_history': 'caption_proposals', 'text_proposal_history': 'text_classification_proposals'}
ID = re.compile(r'^[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
MAX_RECORDS = 100_000
MAX_RESPONSE = 256 * 1024
LOCAL_JOB_FIELDS = {'admission_id', 'request_digest'}
LOCAL_CONFIG_FIELDS = {'server_url', 'requested_server_url', 'prompt_url'}
AUTHORITY_FIELDS = {'token', 'token_sha256', 'access_token', 'refresh_token', 'api_key', 'password',
                    'authorization', 'cookie', 'set-cookie', 'credentials', 'admission_id', 'grant_id'}
EVIDENCE_FIELDS = {'response_sha256', 'capability_observation', 'producer_contract_source', 'canonical_request',
                   'provider_outcome', 'provider_error_code', 'provider_http_status', 'build_observation', 'canonical_request_sha256'}
JOB_COMMON = {'schema_version', 'id', 'revision', 'status', 'error', 'created_at', 'updated_at',
              'source', 'config', 'system_prompt', 'prompt_version', 'prompt_sha256',
              'canonical_request_sha256', 'response_sha256', 'verification'}
JOB_OPTIONAL = {'reported_model', 'catalog_qualification', 'listed_models'} | EVIDENCE_FIELDS
PAYLOAD_FIELDS = {'raw_response_base64': 'raw_response', 'canonical_request': 'canonical_request',
                  'input_image_base64': 'input_image'}
ENTRY_REQUIRED = {'id', 'job_id', 'ordinal', 'prompt', 'status', 'sample_id', 'error', 'model',
                  'width', 'height', 'requested_seed'}
ENTRY_OPTIONAL = {'size', 'metadata', 'deleted_at', 'request_id', 'provider_outcome', 'attempt_evidence'}


def fail(message, code='invalid', status=400):
    raise WorkbenchError(message, code, status)


def shape(value, required, optional=(), name='producer'):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        fail('Unsupported ' + name + ' fields.')


def identity(value):
    if type(value) is not str or not ID.fullmatch(value):
        fail('Invalid producer historical identity.')
    return value


def digest(value):
    if type(value) is not str or not SHA.fullmatch(value):
        fail('Invalid producer digest.')
    return value


def integer(value, minimum=0, maximum=2**53-1):
    if type(value) is not int or not minimum <= value <= maximum:
        fail('Invalid producer count/revision.')
    return value


def date(value):
    try:
        if type(value) is not str or len(value) > 80:
            raise ValueError()
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except ValueError:
        fail('Invalid producer observation timestamp.')


def _safe(value, depth=0):
    if depth > 64:
        fail('Producer evidence exceeds its nesting bound.')
    if type(value) is dict:
        if any(type(key) is not str or key.lower() in AUTHORITY_FIELDS for key in value):
            fail('Producer evidence contains live credential or admission material.')
        for child in value.values():
            _safe(child, depth+1)
    elif type(value) is list:
        for child in value:
            _safe(child, depth+1)
    elif type(value) not in (str, int, float, bool, type(None)):
        fail('Producer evidence is not finite JSON.')
    try:
        if depth == 0:
            json.dumps(value, allow_nan=False, ensure_ascii=False).encode('utf-8')
    except (ValueError, UnicodeError, OverflowError):
        fail('Producer evidence contains invalid Unicode or nonfinite values.')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bytes(value, maximum):
    try:
        if type(value) is not str or len(value) > 4*((maximum+2)//3):
            raise ValueError()
        raw = base64.b64decode(value, validate=True)
        if len(raw) > maximum or base64.b64encode(raw).decode('ascii') != value:
            raise ValueError()
        return raw
    except ValueError:
        fail('Producer payload requires bounded exact base64 bytes.')


def _observations(job):
    for field in ('canonical_request_sha256', 'response_sha256'):
        if job.get(field) is not None:
            digest(job[field])
    if 'capability_observation' in job:
        observed = job['capability_observation']
        shape(observed, {'capabilities', 'observed_sha256'}, name='capability observation')
        # The original wire digest is retained independently: the manifest is an
        # already-decoded observation and cannot recreate its original spacing.
        pumas.validate_manifest(encode(observed['capabilities']).encode())
        digest(observed['observed_sha256'])
        if observed['capabilities']['model'] != job['config']['model']:
            fail('Producer capability observation belongs to another model.')
    if 'producer_contract_source' in job:
        source = job['producer_contract_source']
        if type(source) is not str or not re.fullmatch('[a-f0-9]{40}', source):
            fail('Invalid producer contract source identity.')
    if 'provider_outcome' in job and job['provider_outcome'] not in ('not_admitted', 'unknown', 'result_received'):
        fail('Unsupported historical provider outcome.')
    if job.get('provider_http_status') is not None:
        integer(job['provider_http_status'], 100, 599)
    if job.get('provider_error_code') is not None:
        text_value(job['provider_error_code'], 'Provider error code', 200)
    if 'build_observation' in job:
        import pumas_gateway_descriptor as descriptor
        build = job['build_observation']
        # Build observation interpretation stays with its existing owner.
        shape(build, {'advertisement', 'observed_sha256'}, name='retained build observation')
        descriptor.decode(encode(build['advertisement']).encode())
        digest(build['observed_sha256'])


def _config(family, config):
    if family == 'generation_history':
        required = {'model', 'prompt', 'width', 'height', 'count', 'strategy'}
        optional = {'seed', 'protocol', 'profile', 'prompt_model', 'size'}
    else:
        required = {'model', 'instruction', 'seed'}
        optional = {'protocol', 'profile'}
        if family != 'grounded_history':
            required.add('provider')
        if family == 'grounded_history':
            required.add('count')
        if family == 'text_proposal_history':
            required |= {'labels', 'requested_model'}
    shape(config, required, optional, 'producer configuration')
    pumas.alias(config['model'])
    mode = pumas.configuration(config, image=family == 'generation_history')
    if (family == 'generation_history' and config.get('seed') is not None
            or family != 'generation_history' and not mode):
        integer(config.get('seed'), 0, 2**32-1)
    if family == 'generation_history':
        dimensions = synthetic.saved_dimensions(config)
        if (dimensions['width'], dimensions['height']) != (config['width'], config['height']):
            fail('Saved producer geometry differs.')
        integer(config['count'], 1, 10000)
        text_value(config['prompt'], 'Generation prompt', 4000)
        if config['strategy'] not in ('varied', 'repeat') or mode and config['strategy'] != 'repeat':
            fail('Unsupported saved prompt strategy.')
        if config['strategy'] == 'varied':
            pumas.alias(config.get('prompt_model'))
    else:
        text_value(config['instruction'], 'Producer guidance', 2000)
        if family == 'grounded_history':
            integer(config['count'], 1, 10)
        if family == 'text_proposal_history':
            text_classification_proposals.validate_labels(config['labels'])
            text_value(config['requested_model'], 'Requested model identity', 200)
        if family != 'grounded_history' and config['provider'] not in (
                'pumas_chat_compatible', 'pumas_image_to_text', pumas.PROTOCOL):
            fail('Unsupported producer identity.')


def _entry(entry, job):
    shape(entry, ENTRY_REQUIRED, ENTRY_OPTIONAL, 'generation entry')
    identity(entry['id']); identity(entry['job_id'])
    if entry['job_id'] != job['id'] or entry['model'] != job['config']['model']:
        fail('Generation entry belongs to another job/model.')
    integer(entry['ordinal'], 0, job['config']['count']-1)
    dimensions = synthetic.saved_dimensions(entry)
    if (dimensions['width'], dimensions['height']) != (job['config']['width'], job['config']['height']):
        fail('Generation entry geometry differs from its job.')
    text_value(entry['prompt'], 'Saved generation prompt', 4000)
    text_value(entry['error'], 'Generation error', 800, empty=True)
    if entry['status'] not in ('pending', 'generating', 'completed', 'failed', 'deleted'):
        fail('Unsupported saved generation entry status.')
    if entry['sample_id'] is not None:
        identity(entry['sample_id'])
    if ((entry['status'] == 'completed') != (entry['sample_id'] is not None)):
        fail('Generation entry source/deletion state differs.')
    expected_seed = ((job['config']['seed'] + entry['ordinal']) % 2**32
                     if job['config'].get('seed') is not None else None)
    if entry['requested_seed'] != expected_seed:
        fail('Generation entry seed differs from its saved ordinal.')
    if 'deleted_at' in entry:
        date(entry['deleted_at'])
    if 'request_id' in entry:
        identity(entry['request_id'])
    if 'provider_outcome' in entry and entry['provider_outcome'] not in ('not_admitted', 'unknown', 'result_received'):
        fail('Unsupported generation provider outcome.')
    for field in ('metadata', 'attempt_evidence'):
        if field in entry:
            value = entry[field]
            optional = {'seed', 'steps', 'guidance', 'duration_seconds', 'memory_policy', 'protocol'} | EVIDENCE_FIELDS
            shape(value, (), optional if field == 'metadata' else EVIDENCE_FIELDS, 'generation result evidence')
            for number in ('seed', 'steps', 'guidance', 'duration_seconds'):
                if number in value and type(value[number]) not in (int, float):
                    fail('Generation numeric observation differs from its owner.')
            if 'memory_policy' in value and value['memory_policy'] not in ('sequential_cpu_offload', 'model_cpu_offload', 'gpu'):
                fail('Unsupported generation memory policy observation.')
            if 'protocol' in value and value['protocol'] != pumas.PROTOCOL:
                fail('Unsupported generation protocol observation.')
            _observations(dict(value, config=job['config']))
            _safe(value)
    _safe(entry)


def _validate_job_value(family, job):
    if family == 'generation_history':
        shape(job, {'id', 'config', 'meta', 'status', 'error', 'completed'}, EVIDENCE_FIELDS,
              'generation job')
        from image_sources import metadata
        if metadata(job['meta']) != job['meta']:
            fail('Generation source metadata differs from its owner.')
        _config(family, job['config'])
        integer(job['completed'], 0, job['config']['count'])
        states = ('preparing', 'generating', 'stopping', 'completed', 'failed', 'cancelled', 'interrupted')
    else:
        extra = {'candidates', 'raw_response_text_available'} if family == 'grounded_history' else {'intent_sha256', 'annotation', 'application'}
        if family == 'caption_proposal_history':
            extra.add('input_image')
        if family == 'text_proposal_history':
            extra |= {'labels_sha256', 'source_text_sha256'}
        shape(job, JOB_COMMON | extra, JOB_OPTIONAL - {'canonical_request'}, 'proposal history')
        if job['schema_version'] != 1:
            fail('Unsupported producer schema version.', 'unsupported', 422)
        _config(family, job['config'])
        integer(job['revision'], 1)
        if date(job['updated_at']) < date(job['created_at']):
            fail('Producer update precedes creation.')
        from project_data import validate_record_snapshot
        validate_record_snapshot(job['source'])
        expected_kind = 'image' if family == 'caption_proposal_history' else 'text'
        if job['source']['kind'] != expected_kind:
            fail('Captured source has the wrong producer modality.')
        text_value(job['system_prompt'], 'Captured system prompt', 20000)
        module = {'grounded_history': grounded_candidates, 'caption_proposal_history': caption_proposals, 'text_proposal_history': text_classification_proposals}[family]
        if job['prompt_version'] != module.PROMPT_VERSION or job['system_prompt'] != module.SYSTEM_PROMPT:
            fail('Unsupported historical producer prompt contract.', 'unsupported', 422)
        if _sha(job['system_prompt'].encode()) != job['prompt_sha256']:
            fail('Captured system prompt digest differs.')
        digest(job['canonical_request_sha256'])
        if job['response_sha256'] is not None:
            digest(job['response_sha256'])
        if family == 'text_proposal_history':
            if _sha(encode(job['config']['labels']).encode()) != job['labels_sha256'] or _sha(job['source']['text'].encode()) != job['source_text_sha256']:
                fail('Frozen labels or source text digest differs.')
        if family != 'grounded_history':
            digest(job['intent_sha256'])
        text_value(job['verification'], 'Producer verification qualification', 2000)
        if job.get('reported_model') is not None:
            text_value(job['reported_model'], 'Reported model', 200)
        if 'catalog_qualification' in job:
            text_value(job['catalog_qualification'], 'Model catalog qualification', 2000)
        if 'listed_models' in job:
            if type(job['listed_models']) is not list or len(job['listed_models']) > 10000:
                fail('Invalid observed serving model catalog.')
            for model in job['listed_models']:
                text_value(model, 'Observed serving model', 256)
        if family == 'grounded_history':
            if type(job['raw_response_text_available']) is not bool:
                fail('Invalid exact-response text-view observation.')
            if job['source']['task'] != 'text_classification' or job['source']['review'] != 'human_reviewed' or job['source']['annotation'] is None:
                fail('Grounded source lacks its captured human-reviewed class.')
            if len(job['source']['text']) > grounded_candidates.MAX_SOURCE:
                fail('Captured grounded source exceeds its owner bound.')
            _candidates(job)
        elif job['application'] is not None:
            shape(job['application'], {'record_id', 'revision', 'source_revision'}, name='proposal application')
            application = job['application']
            if (application['record_id'] != job['source']['id'] or application['revision'] != job['source']['revision']+1
                    or application['source_revision'] != job['source']['source_revision'] or job['status'] != 'applied'):
                fail('Proposal application differs from its captured revisions.')
        elif job['status'] == 'applied':
            fail('Applied producer observation lacks its application facts.')
        if family == 'caption_proposal_history':
            shape(job['input_image'], {'mime', 'size', 'bytes', 'sha256', 'preparation'}, name='prepared image')
            image = job['input_image']
            if image['mime'] != 'image/jpeg' or type(image['size']) is not list or len(image['size']) != 2:
                fail('Invalid prepared image format.')
            for size in image['size']:
                integer(size, 1, 1600)
            integer(image['bytes'], 1, caption_proposals.MAX_IMAGE); digest(image['sha256'])
            if image['preparation'] != 'oriented canonical RGB; thumbnail max 1600; JPEG quality 95':
                fail('Unsupported prepared image procedure.', 'unsupported', 422)
            if job['annotation'] is not None:
                validate_annotation('image_caption', job['annotation'], job['source'])
        if family == 'text_proposal_history' and job['annotation'] is not None:
            if job['annotation'] not in [{'label': label} for label in job['config']['labels']]:
                fail('Saved target is outside its frozen label set.')
        states = ('preparing', 'generating', 'stopping', 'completed', 'failed', 'cancelled', 'interrupted', 'applied', 'rejected')
        if family == 'text_proposal_history':
            states += ('abstained',)
    identity(job['id'])
    if job['status'] not in states:
        fail('Unsupported producer lifecycle observation.')
    text_value(job['error'], 'Producer error observation', 800, empty=True)
    _observations(job); _safe(job)


def _job(family, job):
    try:
        _validate_job_value(family, job)
    except WorkbenchError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        fail('Invalid retained producer value.')


def _candidates(job):
    values = job['candidates']
    if type(values) is not list or len(values) > job['config']['count']:
        fail('Invalid retained grounded candidate list.')
    if job['status'] == 'completed' and len(values) != job['config']['count']:
        fail('Completed grounded output is incomplete.')
    seen, texts = set(), {job['source']['text']}
    for candidate in values:
        shape(candidate, {'id', 'text', 'label', 'evidence', 'status', 'record_id', 'review_note'}, name='grounded candidate')
        identity(candidate['id'])
        if candidate['id'] in seen:
            fail('Duplicate grounded candidate identity.')
        seen.add(candidate['id'])
        grounded_candidates.validate_candidate_values([candidate], job['source'], existing_texts=texts)
        texts.add(candidate['text'])
        if candidate['status'] not in ('pending_review', 'admitted', 'rejected'):
            fail('Invalid grounded review disposition.')
        if candidate['record_id'] is not None:
            identity(candidate['record_id'])
        if (candidate['status'] == 'admitted') != (candidate['record_id'] is not None):
            fail('Grounded admission identity differs from its disposition.')
        text_value(candidate['review_note'], 'Grounded review note', 1000, empty=True)


def _declarations(records):
    result = {}
    for envelope in records:
        if envelope.get('family') == 'project_artifact':
            from project_artifacts import validate_declaration
            declaration = validate_declaration(envelope['document'])
            if envelope['id'] != declaration['sha256'] or declaration['sha256'] in result:
                fail('Invalid duplicate producer artifact declaration.')
            result[declaration['sha256']] = declaration
    return result


def _edge(edge, declarations, role):
    shape(edge, {'artifact', 'media_type', 'kind', 'role', 'preservation', 'required_for'}, name='producer artifact edge')
    shape(edge['artifact'], {'namespace', 'sha256'}, name='producer artifact identity')
    identity(edge['artifact']['namespace']); digest(edge['artifact']['sha256'])
    if edge['kind'] != 'producer_evidence' or edge['role'] != role or edge['preservation'] != 'unique' or edge['required_for'] != ['verify_producer']:
        fail('Producer payload role or retention differs.')
    expected_media = 'image/jpeg' if role == 'input_image' else 'application/octet-stream' if role == 'raw_response' else 'application/json'
    if edge['media_type'] != expected_media:
        fail('Producer payload media type differs from its role.')
    declaration = declarations.get(edge['artifact']['sha256'])
    if declaration is None:
        fail('Producer payload declaration is missing.')
    return declaration


def _payloads(value, declarations, roles):
    shape(value, (), roles, 'producer payloads')
    for role, edge in value.items():
        _edge(edge, declarations, role)


def decode_records(records, *, artifacts=None):
    """Validate four fixed history families; absent payloads remain declared.

    With an artifact capability, every available payload is decoded by its
    original owner. Missing bytes permit metadata inspection, never inference
    or a new verified result. Corrupt available bytes fail closed.
    """
    if type(records) is not list or len(records) > MAX_RECORDS or any(type(item) is not dict for item in records):
        fail('Producer inventory exceeds its record bound.')
    declarations = _declarations(records)
    result = []
    seen, observed_order = set(), set()
    for envelope in records:
        family = envelope.get('family')
        if family not in FAMILIES:
            continue
        shape(envelope, {'family', 'id', 'document'}, name='producer envelope')
        doc = envelope['document']
        shape(doc, {'format', 'origin_catalog_id', 'ordinal', 'job', 'payloads', 'observation_integrity'} | ({'entries'} if family == 'generation_history' else set()), {'prompt_batches'} if family == 'generation_history' else (), name='producer document')
        if doc['format'] != FAMILIES[family]:
            fail('Unsupported producer document format.', 'unsupported', 422)
        identity(doc['origin_catalog_id']); _job(family, doc['job'])
        integer(doc['ordinal'], 1, 2**63-1)
        order_key = (family, doc['origin_catalog_id'], doc['ordinal'])
        if order_key in observed_order:
            fail('Duplicate historical producer ordering.')
        observed_order.add(order_key)
        if doc['observation_integrity'] != _observation_integrity(doc['job']):
            fail('Producer observation wire-integrity classification differs.')
        if envelope['id'] != doc['origin_catalog_id'] + '.' + doc['job']['id'] or (family, envelope['id']) in seen:
            fail('Producer origin/identity differs or repeats.')
        seen.add((family, envelope['id']))
        roles = {'raw_response', 'canonical_request'} | ({'input_image'} if family == 'caption_proposal_history' else set())
        _payloads(doc['payloads'], declarations, roles)
        if family != 'generation_history' and 'canonical_request' not in doc['payloads']:
            fail('Producer canonical request declaration is missing.')
        if doc['job'].get('response_sha256') is not None and 'raw_response' not in doc['payloads']:
            fail('Producer response declaration is missing.')
        if family == 'caption_proposal_history' and 'input_image' not in doc['payloads']:
            fail('Prepared producer input declaration is missing.')
        if family == 'generation_history':
            _prompt_batches(doc,declarations)
            if type(doc['entries']) is not list or len(doc['entries']) > doc['job']['config']['count']:
                fail('Invalid generation queue closure.')
            ordinals, identities, storage_orders = set(), set(), set()
            for value in doc['entries']:
                shape(value, {'entry', 'history', 'payloads', 'observation_integrity', 'storage_order'}, {'history_payloads'}, name='generation entry history')
                integer(value['storage_order'], 1, 2**63-1)
                if value['storage_order'] in storage_orders:
                    fail('Duplicate historical generation storage ordering.')
                storage_orders.add(value['storage_order'])
                if value['observation_integrity'] != _entry_integrity(value['entry']):
                    fail('Generation observation wire-integrity classification differs.')
                _entry_history(value, doc['job'])
                _entry(value['entry'], doc['job'])
                ordinal, entry_id = value['entry']['ordinal'], value['entry']['id']
                if ordinal in ordinals or entry_id in identities:
                    fail('Duplicate generation queue entry.')
                ordinals.add(ordinal); identities.add(entry_id)
                _payloads(value['payloads'], declarations, {'attempt_request', 'result_request'})
                histories=value.get('history_payloads',[value['payloads'] for _ in value['history']])
                if type(histories) is not list or len(histories)!=len(value['history']) or histories[-1]!=value['payloads']:
                    fail('Generation evidence history differs from its observations.')
                for entry,mapping in zip(value['history'],histories):
                    _payloads(mapping,declarations,{'attempt_request','result_request'})
                    for field,role in (('attempt_evidence','attempt_request'),('metadata','result_request')):
                        sha=entry.get(field,{}).get('canonical_request_sha256')
                        if sha is not None and (role not in mapping or mapping[role]['artifact']['sha256']!=sha):
                            fail('Generation request declaration is missing or differs.')
            if sorted(ordinals) != list(range(len(ordinals))):
                fail('Generation queue ordinals have a gap.')
            if doc['job']['completed'] != sum(value['entry']['status'] in ('completed', 'deleted') for value in doc['entries']):
                fail('Generation completed count differs from its retained entries.')
            if doc['job']['status'] == 'completed' and doc['job']['completed'] != doc['job']['config']['count']:
                fail('Completed generation job lacks its complete queue.')
            try:
                synthetic.validate_saved_queue(doc['job'], [value['entry'] for value in doc['entries']])
            except ValueError:
                fail('Retained generation geometry differs from its queue owner.')
        if artifacts is not None:
            _verify_payloads(family, doc, declarations, artifacts)
        result.append(copy.deepcopy(envelope))
    _source_closure(result, records)
    return result


def _read(edge, declarations, artifacts, maximum):
    declaration = declarations[edge['artifact']['sha256']]
    state = artifacts.status(declaration)['state']
    if state == 'missing':
        return None
    if state != 'verified':
        fail('Producer evidence payload is corrupt.', 'integrity', 409)
    return artifacts.read_blob({'sha256': declaration['sha256'], 'bytes': declaration['bytes']}, maximum_bytes=maximum)


def _verify_payloads(family, doc, declarations, artifacts):
    job = copy.deepcopy(doc['job'])
    payloads = doc['payloads']
    for role in ('raw_response', 'canonical_request', 'input_image'):
        if role not in payloads:
            continue
        maximum = caption_proposals.MAX_IMAGE if role == 'input_image' else 32*1024*1024 if role == 'canonical_request' else image_generation.MAX_JSON if family == 'generation_history' else MAX_RESPONSE
        raw = _read(payloads[role], declarations, artifacts, maximum)
        if raw is None:
            continue
        if role == 'canonical_request':
            parsed = pumas.strict_json(raw); _safe(parsed)
            if _sha(raw) != job.get('canonical_request_sha256'):
                fail('Canonical producer request digest differs.')
            job['canonical_request'] = parsed
        elif role == 'input_image':
            if _sha(raw) != job['input_image']['sha256'] or len(raw) != job['input_image']['bytes']:
                fail('Prepared producer image differs from its observation.')
            job['input_image_base64'] = base64.b64encode(raw).decode('ascii')
        else:
            if _sha(raw) != job.get('response_sha256'):
                fail('Producer response digest differs.')
            _response_values(raw)
            job['raw_response_base64'] = base64.b64encode(raw).decode('ascii')
    if family == 'generation_history':
        _verify_prompt_batches(doc,declarations,artifacts)
        for wrapper in doc['entries']:
            histories=wrapper.get('history_payloads',[wrapper['payloads'] for _ in wrapper['history']])
            for entry,mapping in zip(wrapper['history'],histories):
                for field,role in (('attempt_evidence','attempt_request'),('metadata','result_request')):
                    if role not in mapping:continue
                    raw=_read(mapping[role],declarations,artifacts,32*1024*1024)
                    if raw is None:continue
                    evidence=copy.deepcopy(entry.get(field,{}))
                    evidence['canonical_request']=pumas.strict_json(raw)
                    _safe(evidence)
                    try:synthetic.validate_retained_attempt(job,entry,evidence)
                    except (ValueError,TypeError,KeyError):fail('Generation request differs from its retained entry intent.')

    else:
        module = {'grounded_history': grounded_candidates, 'caption_proposal_history': caption_proposals,
                  'text_proposal_history': text_classification_proposals}[family]
        module.validate_retained_result(job)
        if family != 'caption_proposal_history' or 'input_image_base64' in job:
            expected = module.request_payload(job) if family == 'grounded_history' else module.payload(job)
            if pumas.typed(job['config']) and 'capability_observation' in job:
                expected['profile'] = job['capability_observation']['capabilities']['profile']
            if _sha(encode(expected).encode()) != job['canonical_request_sha256']:
                fail('Producer request differs from its captured source/configuration.')
            if 'canonical_request' in job and expected != job['canonical_request']:
                fail('Retained producer request body differs from its owner.')


class InertGenerationEntries:
    """Source-deletion projection; deliberately has no Jobs lifecycle methods."""
    def __init__(self, owner):
        self.owner, self.db, self.access = owner, owner.session.db, owner.session.access
        self.lock = self.db.lock

    @authorized('inspect', 'synthetic.snapshot')
    def snapshot(self):
        with self.lock:
            jobs = [copy.deepcopy(item['document']['job']) for item in sorted(self.owner._records,
                    key=lambda item: (item['document']['origin_catalog_id'], item['document']['ordinal']))
                    if item['family'] == 'generation_history']
            entries = [json.loads(row[0]) for row in self.db.execute('SELECT data FROM generation_entries ORDER BY storage_order')]
            return {'jobs': jobs, 'entries': entries}

    def capture_records(self):
        return self.owner.capture()

    def _entry(self, entry):
        self.access.require('edit', 'dataset.delete', entry.get('sample_id'))
        previous = self.db.execute('SELECT data FROM generation_entries WHERE id=%s', (entry.get('id'),)).fetchone()
        if previous is None:
            fail('Only an existing inert generation entry can be changed.')
        old = json.loads(previous[0])
        expected = dict(old, status='deleted', sample_id=None, deleted_at=entry.get('deleted_at'))
        if entry != expected or old['status'] not in ('completed', 'deleted'):
            fail('Only source-deletion facts may change an inert generation entry.')
        date(entry['deleted_at'])
        self.db.execute('UPDATE generation_entries SET data=%s WHERE id=%s', (encode(entry), entry['id']))


class ProjectProducers:
    def __init__(self, session):
        self.session = session
        self._records, self._artifacts = [], {}
        self._pending_payloads = {}
        self.generation_jobs = InertGenerationEntries(self)
        self.generation_entries = self.generation_jobs

    def _read(self, action, invoke):
        with self.session.access.lock, self.session.lock, self.session.db.lock:
            self.session.access.require('inspect', action)
            self.session.check()
            result = invoke(self.session.snapshot['records'])
            self.session.check()
            return result

    def list(self, family, *, origin_catalog_id=None, offset=0, limit=40):
        if family not in FAMILIES:
            fail('Unsupported producer family.')
        if origin_catalog_id is not None:
            identity(origin_catalog_id)
        integer(offset); integer(limit, 1, 100)
        def read(records):
            values = sorted((item['document'] for item in records if item['family'] == family
                and (origin_catalog_id is None or item['document']['origin_catalog_id'] == origin_catalog_id)),
                key=lambda doc: (doc['origin_catalog_id'], doc['ordinal']))
            return dict(items=[_summary(family, doc) for doc in values[offset:offset+limit]],
                        total=len(values), offset=offset, limit=limit)
        return self._read('project_files.producers', read)

    def get(self, family, id, *, origin_catalog_id, entries_offset=0, entries_limit=40):
        if family not in FAMILIES:
            fail('Unsupported producer family.')
        identity(id); identity(origin_catalog_id)
        integer(entries_offset); integer(entries_limit, 1, 100)
        def read(records):
            doc = next((item['document'] for item in records if item['family'] == family
                       and item['id'] == origin_catalog_id + '.' + id), None)
            if doc is None:
                fail('Historical producer was not found.', 'not_found', 404)
            declarations = _declarations(records)
            result = _summary(family, doc)
            result['job'] = {key:copy.deepcopy(value) for key,value in doc['job'].items() if key != 'source'}
            source = doc['job'].get('source')
            result['source_reference'] = ({key:source[key] for key in
                ('id','kind','revision','source_revision','content_hash','source_sha256')} if source else None)
            result['payloads'] = self._payload_status(doc['payloads'], declarations)
            result['observation_integrity'] = copy.deepcopy(doc['observation_integrity'])
            entries = doc.get('entries', [])
            page, used = [], 0
            for value in entries[entries_offset:entries_offset+entries_limit]:
                item = copy.deepcopy(value)
                item['payloads'] = self._payload_status(item['payloads'], declarations)
                if 'history_payloads' in item:item['history_payloads']=[self._payload_status(value,declarations) for value in item['history_payloads']]
                size = len(encode(item).encode())
                if used + size > 8*1024*1024:
                    break
                page.append(item); used += size
            next_offset = entries_offset + len(page)
            batches=[]
            for value in doc.get('prompt_batches',[])[entries_offset:entries_offset+entries_limit]:
                item=copy.deepcopy(value)
                item['payloads']=self._payload_status(item['payloads'],declarations)
                if len(encode(batches+[item]).encode())>8*1024*1024:break
                batches.append(item)
            next_batch=entries_offset+len(batches)
            result['prompt_batches']=dict(items=batches,total=len(doc.get('prompt_batches',[])),offset=entries_offset,limit=entries_limit,
                                          next_offset=next_batch if next_batch<len(doc.get('prompt_batches',[])) else None)
            result['entries'] = dict(items=page, total=len(entries), offset=entries_offset, limit=entries_limit,
                                    next_offset=next_offset if next_offset < len(entries) else None)
            return result
        return self._read('project_files.producer', read)

    def _payload_status(self, payloads, declarations):
        result = copy.deepcopy(payloads)
        for edge in result.values():
            # Presence is not byte verification. Reads by scientific consumers
            # still obtain verified snapshots from the artifact owner.
            edge['availability'] = self.session.artifacts.inspect(declarations[edge['artifact']['sha256']])
        return result

    def capture_source(self, *, origin_catalog_id=None):
        previous = self._artifacts
        self._artifacts = {}
        try:
            return _capture_source(self, origin_catalog_id=origin_catalog_id)
        except BaseException:
            self._artifacts = previous
            self._pending_payloads = {}
            raise

    def restore(self, snapshot):
        records = decode_records(snapshot['records'], artifacts=self.session.artifacts)
        with self.session.db.transaction():
            for table in TABLES.values():
                if self.session.db.execute('SELECT 1 FROM ' + table + ' LIMIT 1').fetchone():
                    fail('Inert project reconstruction cannot adopt live producer queues.')
            self.session.db.execute('DELETE FROM generation_entries')
            seen, storage_orders = set(), set()
            for envelope in records:
                if envelope['family'] != 'generation_history':
                    continue
                for value in envelope['document']['entries']:
                    entry = value['entry']
                    if entry['id'] in seen or value['storage_order'] in storage_orders:
                        fail('Ambiguous generation entry identity across origins.', 'unsupported', 422)
                    seen.add(entry['id'])
                    storage_orders.add(value['storage_order'])
                    self.session.db.execute('INSERT INTO generation_entries(id,job_id,ordinal,data,storage_order) VALUES(%s,%s,%s,%s,%s)',
                        (entry['id'], entry['job_id'], entry['ordinal'], encode(entry), value['storage_order']))
            maximum=self.session.db.execute('SELECT COALESCE(max(storage_order),0) FROM generation_entries').fetchone()[0]
            self.session.db.execute('SELECT setval(pg_get_serial_sequence(%s,%s),%s,%s)',('generation_entries','storage_order',max(1,maximum),maximum>0))
        self._records = records
        all_declarations = _declarations(snapshot['records'])
        referenced = _referenced_artifacts(records)
        self._artifacts = {sha: all_declarations[sha] for sha in referenced}
        return self

    def refresh(self, snapshot):
        """Refresh canonical science after proven current custody drainage.

        This never creates producer jobs/admissions, deletes a local job table,
        or turns a retained endpoint/identity into current execution authority.
        """
        records=decode_records(snapshot['records'],artifacts=self.session.artifacts)
        seen=set();orders=set()
        for envelope in records:
            if envelope['family']=='generation_history':
                for value in envelope['document']['entries']:
                    if value['entry']['id'] in seen or value['storage_order'] in orders:
                        fail('Ambiguous generation entry identity across origins.','unsupported',422)
                    seen.add(value['entry']['id']);orders.add(value['storage_order'])
        with self.session.db.transaction():
            for envelope in records:
                if envelope['family']!='generation_history':continue
                for value in envelope['document']['entries']:
                    entry=value['entry']
                    self.session.db.execute('INSERT INTO generation_entries(id,job_id,ordinal,data,storage_order) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET job_id=excluded.job_id,ordinal=excluded.ordinal,data=excluded.data,storage_order=excluded.storage_order',
                        (entry['id'],entry['job_id'],entry['ordinal'],encode(entry),value['storage_order']))
            maximum=self.session.db.execute('SELECT COALESCE(max(storage_order),0) FROM generation_entries').fetchone()[0]
            self.session.db.execute('SELECT setval(pg_get_serial_sequence(%s,%s),%s,%s)',('generation_entries','storage_order',max(1,maximum),maximum>0))
        self._records=records
        declarations=_declarations(snapshot['records'])
        self._artifacts={sha:declarations[sha] for sha in _referenced_artifacts(records)}
        return self

    def capture(self):
        result = copy.deepcopy(self._records)
        by_id = {entry['id']: entry for entry in [json.loads(row[0]) for row in self.session.db.execute('SELECT data FROM generation_entries ORDER BY storage_order')]}
        for envelope in result:
            if envelope['family'] == 'generation_history':
                for value in envelope['document']['entries']:
                    if value['entry']['id'] not in by_id:
                        fail('An inert generation entry disappeared from its projection.')
                    current = copy.deepcopy(by_id.pop(value['entry']['id']))
                    if current != value['entry']:
                        value['history'].append(current)
                        if 'history_payloads' in value:value['history_payloads'].append(copy.deepcopy(value['payloads']))
                    value['entry'] = current
        if by_id:
            fail('Unclassified generation entries appeared in the project projection.')
        result.extend(dict(family='project_artifact', id=sha, document=copy.deepcopy(value)) for sha, value in sorted(self._artifacts.items()))
        decode_records(_composed(self.session.snapshot['records'], result), artifacts=self.session.artifacts)
        return result


def _summary(family, document):
    job = document['job']
    return dict(family=family, origin_catalog_id=document['origin_catalog_id'], id=job['id'],
                format=document['format'], ordinal=document['ordinal'], status=job['status'],
                revision=job.get('revision'), created_at=job.get('created_at'), updated_at=job.get('updated_at'),
                entry_count=len(document.get('entries', [])), candidate_count=len(job.get('candidates', [])),
                prompt_batch_count=len(document.get('prompt_batches',[])))


def _observation_integrity(value):
    return {key: 'unverified_missing_original_wire' for key in ('capability_observation', 'build_observation') if key in value}


def _entry_integrity(entry):
    result = {field + '.' + key: state for field in ('metadata', 'attempt_evidence')
              for key, state in _observation_integrity(entry.get(field, {})).items()}
    # Live image generation retains the successful response digest and decoded
    # PNG, but not the original response envelope. Do not invent that envelope.
    for field in ('metadata', 'attempt_evidence'):
        if entry.get(field, {}).get('response_sha256') is not None:
            result[field + '.response_sha256'] = 'unverified_missing_original_wire'
    return result


def _entry_history(value, job):
    history = value['history']
    if type(history) is not list or not 1 <= len(history) <= 100_000 or history[-1] != value['entry']:
        fail('Invalid generation observation history.')
    for entry in history:
        _entry(entry, job)
        if any(entry[k] != history[0][k] for k in ('id', 'job_id', 'ordinal', 'prompt', 'model', 'width', 'height', 'requested_seed')):
            fail('Generation history rewrites its immutable producer intent.')
    for previous, current in zip(history, history[1:]):
        if previous['status'] == 'deleted':
            fail('Deleted generation history cannot resume.')
        if current['status'] == 'deleted':
            expected = dict(previous, status='deleted', sample_id=None, deleted_at=current.get('deleted_at'))
            if previous['status'] != 'completed' or current != expected:
                fail('Unsupported generation deletion transition.')
        elif previous['status'] == 'completed':
            fail('Completed generation history cannot be rewritten.')


def _prompt_batches(doc, declarations):
    values=doc.get('prompt_batches',[])
    if type(values) is not list or len(values)>10000:
        fail('Generation prompt batch observations exceed their bound.')
    if values and doc['job']['config']['strategy']!='varied':
        fail('Repeat generation cannot import variation observations.')
    seen=set();last_offset=0
    for wrapper in values:
        shape(wrapper,{'batch','payloads'},name='prompt batch observation')
        batch=wrapper['batch']
        shape(batch,{'id','offset','count','status','error','request_sha256','response_sha256','prompts'},name='prompt batch')
        identity(batch['id']);digest(batch['request_sha256'])
        if batch['id'] in seen:fail('Prompt batch identity repeats.')
        seen.add(batch['id'])
        integer(batch['offset'],0,doc['job']['config']['count']-1)
        integer(batch['count'],1,min(synthetic.BATCH_SIZE,doc['job']['config']['count']-batch['offset']))
        if batch['offset']<last_offset:fail('Prompt batch ordering moves backwards.')
        last_offset=batch['offset']
        if batch['status'] not in ('requesting','completed','failed'):fail('Unsupported prompt batch lifecycle.')
        text_value(batch['error'],'Prompt batch error',800,empty=True)
        if batch['status']=='requesting':
            if batch['prompts'] is not None or batch['response_sha256'] is not None or batch['error']:
                fail('Unreceived prompt batch contains a claimed result.')
        else:
            digest(batch['response_sha256'])
            if batch['status']=='completed':
                if (batch['error'] or type(batch['prompts']) is not list or len(batch['prompts'])!=batch['count']
                        or any(type(p) is not str or not p.strip() or len(p)>4000 or p!=p.strip() for p in batch['prompts'])):
                    fail('Prompt batch result shape differs.')
            elif batch['prompts'] is not None or not batch['error']:
                fail('Failed prompt batch claims valid prompts.')
        _safe(batch)
        roles={'canonical_request'} | ({'raw_response'} if batch['response_sha256'] is not None else set())
        if set(wrapper['payloads'])!=roles:fail('Prompt batch exact payload declarations differ.')
        _payloads(wrapper['payloads'],declarations,roles)
        for role,field in (('canonical_request','request_sha256'),('raw_response','response_sha256')):
            if role in wrapper['payloads'] and wrapper['payloads'][role]['artifact']['sha256']!=batch[field]:
                fail('Prompt batch payload digest differs.')


def _verify_prompt_batches(doc,declarations,artifacts):
    entries=[v['entry'] for v in doc['entries']]
    expected=None;available=True
    for wrapper in doc.get('prompt_batches',[]):
        batch=wrapper['batch']
        request=_read(wrapper['payloads']['canonical_request'],declarations,artifacts,32*1024*1024)
        response=(_read(wrapper['payloads']['raw_response'],declarations,artifacts,256*1024)
                  if 'raw_response' in wrapper['payloads'] else None)
        if response is not None:_response_values(response)
        if request is None:
            available=False;continue
        parsed=caption_proposals.strict_json(request);_safe(parsed)
        try:synthetic.validate_retained_prompt_batch(doc['job']['config'],batch,parsed,response)
        except (ValueError,KeyError,TypeError,IndexError):fail('Retained prompt batch wire differs from its queue intent.')
        if expected is None:expected=[v['prompt'] for v in entries[:batch['offset']]]
        if available and batch['offset']!=len(expected):fail('Prompt batch offset differs from retained unique results.')
        if available and json.loads(parsed['messages'][1]['content'])['recent_prompts_to_avoid']!=expected[-synthetic.BATCH_SIZE:]:
            fail('Prompt batch context differs from preceding retained queue prompts.')
        if batch['status']=='completed' and available:
            seen={' '.join(value.casefold().split()) for value in expected}
            for prompt in batch['prompts']:
                key=' '.join(prompt.casefold().split())
                if key not in seen:expected.append(prompt);seen.add(key)
    if available and expected is not None and [v['prompt'] for v in entries]!=expected[:len(entries)]:
        fail('Saved generation prompts differ from exact variation results.')


def _capture_prompt_batches(owner,job,batches):
    result=[]
    for original in batches:
        batch=copy.deepcopy(original)
        request=batch.pop('canonical_request')
        raw=batch.pop('raw_response_base64')
        synthetic.validate_retained_prompt_batch(job['config'],batch,request,_bytes(raw,256*1024) if raw is not None else None)
        _safe(request)
        payloads={'canonical_request':_publish(owner,encode(request).encode(),'canonical_request')}
        if raw is not None:
            data=_bytes(raw,256*1024);_response_values(data)
            payloads['raw_response']=_publish(owner,data,'raw_response','application/octet-stream')
        result.append(dict(batch=batch,payloads=payloads))
    return result


def _referenced_artifacts(records):
    result = set()
    for envelope in records:
        doc = envelope['document']
        mappings = [doc['payloads']]
        mappings.extend(value['payloads'] for value in doc.get('prompt_batches',[]))
        if envelope['family'] == 'generation_history':
            mappings.extend(value['payloads'] for value in doc['entries'])
            mappings.extend(mapping for value in doc['entries'] for mapping in value.get('history_payloads',[]))
        result.update(edge['artifact']['sha256'] for mapping in mappings for edge in mapping.values())
    return result


def _portable_observations(value):
    value = copy.deepcopy(value)
    if 'build_observation' in value:
        build = value['build_observation']
        shape(build, {'advertisement', 'observed_sha256'}, {'server_url'}, 'stored build observation')
        build.pop('server_url', None)
    return value


def _historical_urls(value):
    """Known attribution URLs are historical facts, never current resolvers."""
    if type(value) is dict:
        for key, child in value.items():
            if key in ('server_url', 'requested_server_url', 'prompt_url'):
                import ai_http
                ai_http.validate_url('llamacpp', child)
            _historical_urls(child)
    elif type(value) is list:
        for child in value:
            _historical_urls(child)


def _publish(owner, raw, role, media='application/json'):
    declaration = dict(format='project_artifact_v1', sha256=_sha(raw), bytes=len(raw))
    previous = owner._pending_payloads.get(declaration['sha256'])
    if previous is not None and previous != raw:
        fail('Conflicting exact producer payload bytes.')
    owner._pending_payloads[declaration['sha256']] = raw
    owner._artifacts[declaration['sha256']] = declaration
    return dict(artifact=dict(namespace=owner.session.snapshot['project_id'], sha256=declaration['sha256']),
                media_type=media, kind='producer_evidence', role=role,
                preservation='unique', required_for=['verify_producer'])


def _capture_payloads(owner, family, job):
    payloads = {}
    for field, role in PAYLOAD_FIELDS.items():
        value = job.pop(field, None)
        if value is None:
            continue
        if field == 'canonical_request':
            _safe(value)
            raw = encode(value).encode()
        else:
            maximum = caption_proposals.MAX_IMAGE if role == 'input_image' else image_generation.MAX_JSON if family == 'generation_history' else MAX_RESPONSE
            raw = _bytes(value, maximum)
            if role == 'raw_response':
                _response_values(raw)
        payloads[role] = _publish(owner, raw, role, 'image/jpeg' if role == 'input_image' else 'application/octet-stream' if role == 'raw_response' else 'application/json')
    return payloads


def _response_values(raw):
    try:
        # The existing chat owner accepts JSON's historical UTF-16 byte
        # encodings too. Inspect values without rewriting original bytes.
        parsed = caption_proposals.strict_json(raw)
    except (UnicodeError, ValueError, RecursionError):
        fail('Opaque provider response bytes lack a supported credential-free classification.', 'unsupported', 422)
    _safe(parsed)
    return parsed


def _capture_entry(owner, entry, storage_order):
    result, payloads = copy.deepcopy(entry), {}
    for field, role in (('attempt_evidence', 'attempt_request'), ('metadata', 'result_request')):
        if field in result:
            result[field] = _portable_observations(result[field])
            request = result[field].pop('canonical_request', None)
            if request is not None:
                _safe(request)
                raw = encode(request).encode()
                if _sha(raw) != result[field]['canonical_request_sha256']:
                    fail('Generation request body digest differs.')
                payloads[role] = _publish(owner, raw, role)
    return dict(entry=result, history=[copy.deepcopy(result)], payloads=payloads, storage_order=storage_order,
                observation_integrity=_entry_integrity(result))


def _capture_job(owner, family, original, ordinal, entries):
    job = copy.deepcopy(original)
    prompt_batches = job.pop('prompt_batches',None) if family == 'generation_history' else None
    # These are the complete classified local fields, not a denylist fallback.
    # All remaining source fields must satisfy the owned closed codec below.
    for key in LOCAL_JOB_FIELDS:
        if key in job:
            (identity if key == 'admission_id' else digest)(job[key])
        job.pop(key, None)
    if type(job.get('config')) is not dict:
        fail('Missing producer configuration.')
    for field in LOCAL_CONFIG_FIELDS:
        if field in job['config']:
            import ai_http
            ai_http.validate_url('llamacpp', job['config'][field])
        job['config'].pop(field, None)
    if family != 'caption_proposal_history' and 'input_image_base64' in job:
        fail('Unexpected image payload in this producer family.')
    job = _portable_observations(job)
    if 'source' in job:
        _historical_urls(job['source'])
    if family == 'grounded_history':
        view = job.pop('raw_response', None)
        job['raw_response_text_available'] = view is not None
        if view is not None:
            if type(view) is not str:
                fail('Invalid retained grounded response view.')
            raw = _bytes(job['raw_response_base64'], MAX_RESPONSE)
            if raw.decode('utf-8') != view:
                fail('Grounded response text view differs from its exact bytes.')
    if family != 'generation_history' and 'canonical_request' not in job:
        module = {'grounded_history': grounded_candidates, 'caption_proposal_history': caption_proposals,
                  'text_proposal_history': text_classification_proposals}[family]
        job['canonical_request'] = module.request_payload(job) if family == 'grounded_history' else module.payload(job)
        if _sha(encode(job['canonical_request']).encode()) != job['canonical_request_sha256']:
            fail('Reconstructed canonical producer request differs from its stored identity.')
    payloads = _capture_payloads(owner, family, job)
    document = dict(format=FAMILIES[family], origin_catalog_id=owner._origin, ordinal=ordinal,
                    job=job, payloads=payloads, observation_integrity=_observation_integrity(job))
    if prompt_batches is not None:
        document['prompt_batches'] = _capture_prompt_batches(owner,job,prompt_batches)
    if family == 'generation_history':
        document['entries'] = [_capture_entry(owner, entry, storage_order) for entry, storage_order in entries if entry['job_id'] == job['id']]
    return dict(family=family, id=owner._origin+'.'+job['id'], document=document)


def _capture_source(self, *, origin_catalog_id=None):
    """Explicit historical extraction primitive; never called by inert Open.

    Reads the five named producer tables. It may publish exact evidence bytes,
    but neither alters the source rows nor constructs any producer supervisor.
    """
    self._origin = identity(origin_catalog_id or self.session.db.dataset_id)
    self._pending_payloads = {}
    entries = []
    for row_id, job_id, ordinal, raw, storage_order in self.session.db.execute(
            'SELECT id,job_id,ordinal,data,storage_order FROM generation_entries ORDER BY storage_order'):
        entry = json.loads(raw)
        if (entry.get('id'), entry.get('job_id'), entry.get('ordinal')) != (row_id, job_id, ordinal):
            fail('Generation row identity differs from its observed document.')
        entries.append((entry, storage_order))
    records = []
    for family, table in TABLES.items():
        for row_id, raw, ordinal in self.session.db.execute('SELECT id,data,ordinal FROM ' + table + ' ORDER BY ordinal'):
            job = json.loads(raw)
            if job.get('id') != row_id:
                fail('Producer row identity differs from its observed document.')
            records.append(_capture_job(self, family, job, ordinal, entries))
    known_jobs = {item['document']['job']['id'] for item in records if item['family'] == 'generation_history'}
    if any(entry['job_id'] not in known_jobs for entry, _ in entries):
        fail('Generation entry has no retained producer job.')
    records.extend(dict(family='project_artifact', id=sha, document=copy.deepcopy(declaration))
                   for sha, declaration in sorted(self._artifacts.items()))
    composed = _composed(self.session.snapshot['records'], records)
    decode_records(composed, artifacts=_CapturedEvidence(self))
    for sha, raw in self._pending_payloads.items():
        self.session.artifacts.publish_bytes(raw, self._artifacts[sha], maximum_bytes=32*1024*1024)
    self._pending_payloads = {}
    return records



def _producer_document(records, family, job_id, source_id=None):
    candidates = [item['document'] for item in decode_records(records)
                  if item['family'] == family and item['document']['job']['id'] == job_id
                  and (source_id is None or item['document']['job'].get('source', {}).get('id') == source_id)]
    if len(candidates) != 1:
        fail('Producer evidence has a missing or ambiguous historical producer closure.')
    return candidates[0]


def _same_payload(value, document, role):
    edge = document['payloads'].get(role)
    if edge is None or _sha(encode(value).encode()) != edge['artifact']['sha256']:
        fail('Retained request evidence differs from its declared producer payload.')


def validate_target_proposal(evidence, record, records):
    """Validate owner-generated draft evidence, never mint current approval."""
    if type(evidence) is not dict:
        fail('Applied target proposal evidence must be an object.')
    text_target = 'source_text_sha256' in evidence
    required = {'job_id', 'applied_revision', 'captured_revision', 'source_revision', 'source_sha256',
                'config', 'prompt_version', 'prompt_sha256', 'canonical_request_sha256',
                'response_sha256', 'reported_model', 'verification'}
    required |= {'source_text_sha256', 'labels_sha256'} if text_target else {'canonical_image_sha256', 'input_image'}
    shape(evidence, required, EVIDENCE_FIELDS - required, 'applied proposal evidence')
    _safe(evidence); _historical_urls(evidence)
    family = 'text_proposal_history' if text_target else 'caption_proposal_history'
    doc = _producer_document(records, family, identity(evidence['job_id']), record['id'])
    expected_verification = ('Exact label shape only; applied as draft, never approved.' if text_target
                             else 'Caption shape only; applied as draft, never approved.')
    if evidence['verification'] != expected_verification:
        fail('Applied target verification qualification differs from its owner.')
    job, source = doc['job'], doc['job']['source']
    for key in ('prompt_version', 'prompt_sha256', 'canonical_request_sha256', 'response_sha256'):
        if evidence[key] != job[key]:
            fail('Applied target evidence differs from its producer ' + key + '.')
    if type(evidence['config']) is not dict:
        fail('Applied target configuration must be an object.')
    config = {key: value for key, value in evidence['config'].items() if key not in LOCAL_CONFIG_FIELDS}
    if config != job['config'] or evidence['reported_model'] != job.get('reported_model'):
        fail('Applied target evidence rewrites its producer configuration/result.')
    if (type(evidence['applied_revision']) is not int or evidence['applied_revision'] != source['revision'] + 1
            or evidence['captured_revision'] != source['revision']
            or evidence['source_revision'] != source['source_revision']
            or evidence['source_sha256'] != source['source_sha256']
            or evidence['applied_revision'] > record['revision']):
        fail('Applied target evidence belongs to different captured revisions.')
    if job['status'] != 'applied' or job['application'] != {
            'record_id': record['id'], 'revision': evidence['applied_revision'], 'source_revision': evidence['source_revision']}:
        fail('Applied target lacks its historical application disposition.')
    if record['revision'] == evidence['applied_revision'] and (
            record['annotation'] != job['annotation'] or record['review'] != 'draft'
            or record['task'] != ('text_classification' if text_target else 'image_caption')):
        fail('A proposal application cannot establish human review or a different target.')
    if text_target:
        if evidence['source_text_sha256'] != job['source_text_sha256'] or evidence['labels_sha256'] != job['labels_sha256']:
            fail('Applied target source/label identity differs.')
    elif evidence['canonical_image_sha256'] != source['content_hash'] or evidence['input_image'] != job['input_image']:
        fail('Applied target prepared/oriented image identity differs.')
    for key in EVIDENCE_FIELDS - {'canonical_request', 'canonical_request_sha256', 'response_sha256'}:
        if key in evidence and evidence[key] != job.get(key):
            fail('Applied target provider observation differs.')
    if 'canonical_request' in evidence:
        _same_payload(evidence['canonical_request'], doc, 'canonical_request')
    return True


def validate_record_origin(origin, record, records):
    """Recognize only the two producer provenance variants owned here."""
    if type(origin) is not dict or origin.get('method') not in ('model_generated', 'model_grounded_rewrite'):
        return False
    _safe(origin); _historical_urls(origin)
    if origin['method'] == 'model_generated':
        shape(origin, {'method', 'source_sha256', 'rights', 'generation'}, {'rights_note_correction'}, 'generated source provenance')
        generation = origin['generation']
        shape(generation, {'job_id', 'ordinal', 'prompt', 'model', 'width', 'height', 'requested_seed'}, {'metadata', 'size'}, 'generated source binding')
        docs = [item['document'] for item in decode_records(records) if item['family'] == 'generation_history'
                and item['document']['job']['id'] == generation['job_id']]
        matched = []
        for doc in docs:
            for wrapper in doc['entries']:
                for entry in wrapper['history']:
                    if entry['sample_id'] == record['id'] and entry['ordinal'] == generation['ordinal']:
                        matched.append((wrapper, entry))
        if len(matched) != 1:
            fail('Generated source lacks an exact producer entry/source closure.')
        wrapper, entry = matched[0]
        for key in ('job_id', 'ordinal', 'prompt', 'model', 'width', 'height', 'requested_seed', 'size'):
            if key in generation and generation[key] != entry.get(key):
                fail('Generated source intent differs from its retained entry.')
        if 'metadata' in generation:
            metadata = copy.deepcopy(generation['metadata'])
            request = metadata.pop('canonical_request', None)
            if request is not None:
                edge = wrapper['payloads'].get('result_request')
                if edge is None or _sha(encode(request).encode()) != edge['artifact']['sha256']:
                    fail('Generated source result request differs.')
            if _portable_observations(metadata) != entry.get('metadata'):
                fail('Generated source result metadata differs.')
        if record['kind'] != 'image' or origin['source_sha256'] not in {record['source_sha256'], *(
                row['sha256'] for item in records if item['family'] == 'workbench_record' and item['id'] == record['id']
                for row in item['document']['source'].get('revisions', []))}:
            fail('Generated source hash differs from its retained image lineage.')
    else:
        required = {'method', 'rights', 'normalization', 'provider', 'server_url', 'requested_model', 'requested_seed',
                    'instruction', 'system_prompt', 'prompt_version', 'prompt_sha256', 'reported_model',
                    'canonical_request_sha256', 'requested_count', 'max_tokens', 'job_id', 'candidate_id',
                    'response_sha256', 'source', 'evidence', 'verification', 'admission_note'}
        shape(origin, required, EVIDENCE_FIELDS | {'profile', 'rights_note_correction'}, 'grounded source provenance')
        doc = _producer_document(records, 'grounded_history', identity(origin['job_id']))
        job = doc['job']
        values = [candidate for candidate in job['candidates'] if candidate['id'] == origin['candidate_id']]
        if len(values) != 1:
            fail('Grounded source candidate closure is missing.')
        candidate = values[0]
        if candidate['status'] != 'admitted' or candidate['record_id'] != record['id'] or candidate['text'] != record['text']:
            fail('Grounded source differs from its reviewed candidate.')
        for key, expected in {'requested_model': job['config']['model'], 'requested_seed': job['config']['seed'],
                'instruction': job['config']['instruction'], 'requested_count': job['config']['count'], 'max_tokens': 6000,
                'system_prompt': job['system_prompt'], 'prompt_version': job['prompt_version'],
                'prompt_sha256': job['prompt_sha256'], 'canonical_request_sha256': job['canonical_request_sha256'],
                'response_sha256': job['response_sha256'], 'reported_model': job.get('reported_model'),
                'evidence': candidate['evidence'], 'admission_note': candidate['review_note'], 'verification': job['verification']}.items():
            if origin[key] != expected:
                fail('Grounded source provenance differs from its producer ' + key + '.')
        if (origin['provider'] != (pumas.PROTOCOL if pumas.typed(job['config']) else 'pumas_chat_compatible')
                or origin['normalization'] != 'NFC; LF newlines'
                or pumas.typed(job['config']) and origin.get('profile') != job['config'].get('profile')):
            fail('Grounded source producer or normalization attribution differs.')
        if record['revision'] == 1 and (record['review'] != 'draft' or record['task'] != 'text_classification'
                or record['annotation'] != {'label':candidate['label']}):
            fail('Grounded admission cannot establish human review or a different target.')
        for key in EVIDENCE_FIELDS - {'canonical_request', 'canonical_request_sha256', 'response_sha256'}:
            if key in origin and origin[key] != job.get(key):
                fail('Grounded source provider observation differs.')
        expected_source = {key: job['source'][key] for key in ('id', 'revision', 'source_revision', 'content_hash', 'text', 'annotation')}
        if origin['source'] != expected_source:
            fail('Grounded source provenance rewrites its captured input.')
        if 'canonical_request' in origin:
            _same_payload(origin['canonical_request'], doc, 'canonical_request')
    return True


def validate_operation_result(operation, target, result, records):
    from project_producer_execution import validate_operation_result as validate_action
    return validate_action(operation, target, result, records)


def _composed(current, upserts):
    result = {(item['family'], item['id']): item for item in current}
    result.update({(item['family'], item['id']): item for item in upserts})
    return [result[key] for key in sorted(result)]


def _source_closure(producers, records):
    assets = {item['id']: item['document'] for item in records
              if item['family'] in ('workbench_record', 'workbench_text')}
    for envelope in producers:
        doc, family = envelope['document'], envelope['family']
        job = doc['job']
        if family == 'generation_history':
            for wrapper in doc['entries']:
                for entry in wrapper['history']:
                    if entry['sample_id'] is not None and entry['sample_id'] not in assets:
                        fail('Generated source canonical record is missing.')
            continue
        source = job['source']
        asset = assets.get(source['id'])
        if asset is None or source not in asset.get('history', []):
            fail('Producer captured source differs from its retained Workbench history.')
        if family == 'grounded_history':
            for candidate in job['candidates']:
                if candidate['record_id'] is not None:
                    target = assets.get(candidate['record_id'])
                    if target is None or target['current']['text'] != candidate['text']:
                        fail('Admitted grounded candidate canonical record is missing or differs.')


class _CapturedEvidence:
    """Immutable source buffers prove owner semantics before any publication."""
    def __init__(self, owner):
        self.owner = owner

    def status(self, declaration):
        raw = self.owner._pending_payloads.get(declaration['sha256'])
        if raw is None:
            return self.owner.session.artifacts.status(declaration)
        if len(raw) != declaration['bytes'] or _sha(raw) != declaration['sha256']:
            fail('Captured producer payload identity differs.')
        return {'state': 'verified'}

    def read_blob(self, descriptor, *, maximum_bytes):
        raw = self.owner._pending_payloads.get(descriptor['sha256'])
        if raw is None:
            return self.owner.session.artifacts.read_blob(descriptor, maximum_bytes=maximum_bytes)
        if len(raw) != descriptor['bytes'] or len(raw) > maximum_bytes:
            fail('Captured producer payload exceeds its owner bound.')
        return raw
