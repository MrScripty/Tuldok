"""Bounded local passage composition; Workbench owns sources and answers."""
import hashlib
import json
import unicodedata

from workbench import IDENTIFIER, WorkbenchError, encode, text_value, timestamp

MAX_REQUEST = 1024 * 1024
MAX_PASSAGE = 10_000
MAX_QUESTION = 4_000
MAX_COMPLETION = 20_000
SCHEMA = 'tuldok_grounded_instruction_v1'
REF_FIELDS = {'id', 'revision', 'source_revision', 'content_hash', 'start', 'end', 'quote'}


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise WorkbenchError('Duplicate composition field.')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkbenchError('Nonfinite JSON.')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise WorkbenchError('Invalid composition JSON.') from error


def setup(w):
    w.db.execute('CREATE TABLE IF NOT EXISTS instruction_compositions (request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, prompt_id TEXT NOT NULL)')
    w.db.execute('CREATE TABLE IF NOT EXISTS instruction_context_bindings (prompt_id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    w.db.execute('CREATE TABLE IF NOT EXISTS instruction_response_bindings (response_id TEXT PRIMARY KEY, digest TEXT NOT NULL)')


def recipe(parent):
    return parent['provenance'].get('grounded_instruction')


def compose(question, contexts):
    return '\n\n'.join([f"Source {i} [{ref['id']}]\n{ref['quote']}" for i, ref in enumerate(contexts, 1)]) + '\n\nQuestion\n' + question


def reference(source, start, end):
    return {key: source[key] for key in ('id', 'revision', 'source_revision', 'content_hash')} | dict(start=start, end=end, quote=source['text'][start:end])


def contexts(w, refs):
    if not isinstance(refs, list) or not 2 <= len(refs) <= 4:
        raise WorkbenchError('Capture 2–4 distinct text source passages.')
    result, seen = [], set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != REF_FIELDS or not isinstance(ref['id'], str) or not IDENTIFIER.fullmatch(ref['id']):
            raise WorkbenchError('Passages require exact source IDs, revisions, hash, offsets and quote.')
        if ref['id'] in seen:
            raise WorkbenchError('Capture one passage per distinct source.')
        seen.add(ref['id'])
        source = w._get(ref['id'])
        if source['kind'] != 'text' or not source['source_available']:
            raise WorkbenchError('A context source was deleted or is not available text.', 'unavailable', 409)
        for key in ('revision', 'source_revision'):
            if type(ref[key]) is not int or ref[key] != source[key]:
                raise WorkbenchError('A context source changed. Inspect and capture its current passage deliberately.', 'conflict', 409)
        if ref['content_hash'] != source['content_hash'] or hashlib.sha256(source['text'].encode()).hexdigest() != source['content_hash']:
            raise WorkbenchError('Context content hash changed.', 'conflict', 409)
        start, end = ref['start'], ref['end']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source['text']) or end-start > MAX_PASSAGE:
            raise WorkbenchError('Passage offsets use Unicode codepoints; each passage must contain 1–10,000 codepoints.')
        if not isinstance(ref['quote'], str) or ref['quote'] != source['text'][start:end]:
            raise WorkbenchError('Passage quote does not match exact source offsets.')
        result.append({'ref': dict(ref), 'source_metadata': {key: source[key] for key in ('name', 'groups', 'parents', 'provenance', 'review', 'task')}})
    try:
        size = len(encode(result).encode('utf-8'))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise WorkbenchError('Context evidence exceeds supported JSON bounds.') from error
    if size > MAX_REQUEST:
        raise WorkbenchError('Captured context metadata/evidence exceeds 1 MiB.')
    return result


def binding(w, parent):
    row = w.db.execute('SELECT data FROM instruction_context_bindings WHERE prompt_id=?', (parent['id'],)).fetchone()
    if row is None:
        raise WorkbenchError('Grounded instruction binding missing.', 'conflict', 409)
    return json.loads(row[0])


def validate(w, parent):
    data = binding(w, parent)
    if contexts(w, [item['ref'] for item in data]) != data:
        raise WorkbenchError('Context metadata changed. Reinspect before answering or exporting.', 'conflict', 409)
    creation = recipe(parent)
    if creation['schema'] != SCHEMA or parent['text'] != compose(creation['question'], [item['ref'] for item in data]):
        raise WorkbenchError('Composition no longer matches its source passages.', 'conflict', 409)
    return hashlib.sha256(encode(dict(parent_revision=parent['revision'], contexts=data)).encode()).hexdigest()


def check_answer(w, parent, response=None, completion=None):
    if not recipe(parent):
        return None
    digest = validate(w, parent)
    if completion is not None:
        text_value(completion, 'Grounded completion', MAX_COMPLETION)
    if response is not None:
        text_value(response['completion'], 'Grounded completion', MAX_COMPLETION)
        if response.get('grounded_binding_sha256') != digest:
            raise WorkbenchError('Answer review refers to older context or prompt evidence. Save and review against current passages.', 'conflict', 409)
    return digest


def admit(w, body):
    if not isinstance(body, dict) or set(body) != {'request_id', 'name', 'question', 'contexts'}:
        raise WorkbenchError('Supply only request_id, name, question and contexts.')
    request_id = body['request_id']
    if not isinstance(request_id, str) or not IDENTIFIER.fullmatch(request_id):
        raise WorkbenchError('Invalid composition request ID.')
    try:
        raw = encode(body).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise WorkbenchError('Composition must be finite valid Unicode JSON.') from error
    if len(raw) > MAX_REQUEST:
        raise WorkbenchError('Composition request exceeds 1 MiB.')
    name = text_value(body['name'], 'Name')
    text_value(body['question'], 'Question', MAX_QUESTION)
    question = unicodedata.normalize('NFC', body['question'].replace('\r\n', '\n').replace('\r', '\n'))
    text_value(question, 'Canonical question', MAX_QUESTION)
    digest = hashlib.sha256(raw).hexdigest()
    with w.lock, w.db:
        old = w.db.execute('SELECT * FROM instruction_compositions WHERE request_id=?', (request_id,)).fetchone()
        if old:
            if old['digest'] != digest:
                raise WorkbenchError('This request ID already owns a different composition.', 'conflict', 409)
            return {'record': w._get(old['prompt_id']), 'created': False}
        captured = contexts(w, body['contexts'])
        parents = [item['ref']['id'] for item in captured]
        # Admission cannot join families with conflicting inherited image split authority.
        from dataset_releases import connected_components
        universe = w._all()
        text = compose(question, body['contexts'])
        provisional = dict(id='new-composition:' + request_id, kind='text',
                           groups=['grounded:' + request_id], parents=parents,
                           content_hash=hashlib.sha256(text.encode()).hexdigest(), pixel_hash=None)
        roots = connected_components([*universe, provisional])
        joined = roots[provisional['id']]
        related = [row for row in universe if roots[row['id']] == joined]
        fixed = {row['source_split'] for row in related if row['source_split'] != 'unassigned'}
        if len(fixed) > 1:
            raise WorkbenchError('Contexts connect conflicting fixed source splits.', 'conflict', 409)
        if any(not row['source_lineage_known'] for row in related):
            raise WorkbenchError('Related source lineage is unavailable.', 'conflict', 409)
        if len(related) > 5000:
            raise WorkbenchError('Composition source family exceeds 5,000 retained members.')
        lineage_parents = list(dict.fromkeys([*parents, *sorted(row['id'] for row in related)]))
        record = w._insert_text(text, name, provisional['groups'], lineage_parents, 'unknown',
                                provenance={'method': 'human_composed', 'grounded_instruction': dict(schema=SCHEMA, question=question, creation_contexts=captured)})
        w.db.execute('INSERT INTO instruction_context_bindings VALUES (?,?)', (record['id'], encode(captured)))
        w.db.execute('INSERT INTO instruction_compositions VALUES (?,?,?)', (request_id, digest, record['id']))
        # Initial history includes the owned current binding, without a second revision.
        record = w._get(record['id'])
        w.db.execute('UPDATE workbench_history SET snapshot=? WHERE id=? AND revision=1', (encode(record), record['id']))
        return {'record': record, 'created': True}


def inspect(w, record_id):
    with w.lock:
        parent = w._get(record_id)
        if not recipe(parent):
            raise WorkbenchError('This record is not a composed instruction.')
        data = binding(w, parent)
        current, problems = [], []
        for item in data:
            ref = item['ref']
            source = w._get(ref['id'])
            current.append(dict(source=source, captured=item))
        try:
            validate(w, parent)
        except WorkbenchError as error:
            problems.append(str(error))
        return dict(parent=parent, contexts=current, current=not problems, problems=problems)


def reinspect(w, record_id, body):
    if not isinstance(body, dict) or set(body) != {'revision', 'source_revision', 'contexts'}:
        raise WorkbenchError('Supply exact prompt revisions and deliberately inspected current contexts.')
    with w.lock, w.db:
        parent = w._get(record_id)
        if not recipe(parent) or not parent['source_available']:
            raise WorkbenchError('Instruction source unavailable.', 'unavailable', 409)
        for key in ('revision', 'source_revision'):
            if type(body[key]) is not int or body[key] != parent[key]:
                raise WorkbenchError('Prompt changed. Reload before reinspection.', 'conflict', 409)
        old = binding(w, parent)
        updated = contexts(w, body['contexts'])
        immutable = lambda data: [{k: row['ref'][k] for k in ('id', 'content_hash', 'start', 'end', 'quote')} for row in data]
        if immutable(old) != immutable(updated):
            raise WorkbenchError('Keep original source identities and passages. Compose a new prompt for different content.')
        if updated == old:
            return {'record': parent, 'changed': False}
        w.db.execute('UPDATE instruction_context_bindings SET data=? WHERE prompt_id=?', (encode(updated), record_id))
        w.db.execute("UPDATE workbench_records SET revision=revision+1,review='draft',updated_at=? WHERE id=?", (timestamp(), record_id))
        parent = w._get(record_id)
        w._history(parent)
        ids = [row[0] for row in w.db.execute('SELECT id FROM workbench_responses WHERE prompt_id=?', (record_id,))]
        for response_id in ids:
            w.db.execute("UPDATE workbench_responses SET revision=revision+1,review='draft',updated_at=? WHERE id=?", (timestamp(), response_id))
            response = w._response(response_id)
            w.db.execute('INSERT INTO workbench_response_history VALUES (?,?,?)', (response_id, response['revision'], encode(dict(response=response, parent=parent))))
        return {'record': parent, 'changed': True}
