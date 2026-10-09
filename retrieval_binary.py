"""Bounded reviewed binary relevance, separate from positive-only retrieval v1."""
import base64
import hashlib
import io
import json
import math
import re
import struct
import unicodedata
import zipfile

from workbench import WorkbenchError, IDENTIFIER, MAX_TEXT, encode, text_value, strings, analyze, rights_note

TASK = 'text_retrieval_binary'
FORMAT = 'text_retrieval_binary_v2'
STATES = {'relevant': 1, 'not_relevant': 0, 'unjudged': -1}
MAX_RECORDS = 128
MAX_LOGICAL = 8 * 1024 * 1024
MAX_PHYSICAL = 9 * 1024 * 1024
MAX_REQUEST = 13 * 1024 * 1024
MAX_QUERY_REQUEST = 1024 * 1024
MAX_MEMBERS = MAX_RECORDS + 6
MAX_CONTEXT = 5000
HASH = re.compile(r'^[a-f0-9]{64}$')
STREAM_FILES = ('corpus.jsonl', 'queries.jsonl', 'judgments.jsonl', 'qrels.txt')
SCOPE = {'kind': 'human_binary_relevance', 'relevance_values': STATES,
    'omitted_relationships': 'unjudged', 'explicit_unjudged': 'retained, not a reviewed negative',
    'imported_review': 'draft; upstream review is evidence only',
    'qualification': 'source transport and qrels reading only; no ranking, metrics, training or model quality'}
LIMITS = {'selected_records': MAX_RECORDS, 'judgments_per_query': 30,
    'logical_archive_bytes': MAX_LOGICAL, 'context_snapshots': MAX_CONTEXT}
README = ("Tuldok reviewed binary retrieval v2. Relevant=1, not relevant=0, explicit unjudged=-1.\n"
    "Omitted query-document relationships remain unjudged; no Cartesian negatives or implicit pairs.\n"
    "Exact typed judgments and manifest are semantic authority; qrels.txt has four TREC fields.\n"
    "All declared relations and retained former parents stay in one whole-family split.\n"
    "Imported records become local drafts with unknown rights, new IDs and remapped document refs.\n"
    "Separate human document review changes revisions: deliberately refresh query refs before review.\n"
    "Source/family/rights claims are not authenticated. No ranking, metrics, training or model quality.\n").encode()
SNAPSHOT_KEYS = set('id kind revision source_revision content_hash pixel_hash groups parents source_available source_lineage_known source_split source_sha256 book_id session_id'.split())
RECORD_KEYS = SNAPSHOT_KEYS | set('name text provenance task annotation review created_at updated_at width height corner_annotation'.split())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise WorkbenchError(message)


def judgments(value):
    from retrieval_export import references
    require(type(value) is list and 1 <= len(value) <= 30, 'Provide 1–30 explicit relevance relationships.')
    refs, result = [], []
    for item in value:
        require(type(item) is dict and set(item) == {'document', 'relevance'}, 'A judgment needs exactly document and relevance.')
        require(type(item['relevance']) is str and item['relevance'] in STATES, 'Choose relevant, not_relevant or unjudged; arbitrary grades are unsupported.')
        refs.append(item['document'])
        result.append({'document': item['document'], 'relevance': item['relevance']})
    clean = references(refs)
    return [dict(item, document=ref) for item, ref in zip(result, clean)]


def annotation(value, row):
    require(type(value) is dict and value.get('role') in ('document', 'query'), 'Choose binary retrieval document or query.')
    expected = {'role', 'note'} | ({'judgments'} if value['role'] == 'query' else set())
    require(set(value) == expected, 'Binary relevance annotation has unknown or missing fields.')
    result = {'role': value['role'], 'note': text_value(value['note'], 'Binary relevance review note', 4000)}
    if value['role'] == 'query':
        result['judgments'] = judgments(value['judgments'])
        require(all(item['document']['id'] in row['parents'] for item in result['judgments']),
            'Every declared relationship, including unjudged, must be an immutable query parent.')
    return result


def check_documents(w, values):
    for item in judgments(values):
        ref = item['document']; doc = w._get(ref['id'])
        require(doc['kind'] == 'text' and doc['task'] == TASK and doc['review'] == 'human_reviewed'
            and doc['source_available'] and doc['source_lineage_known'] and doc['annotation']
            and doc['annotation'].get('role') == 'document', 'References need available, separately human-reviewed binary retrieval documents.')
        if any(ref[key] != doc[key] for key in ('revision', 'source_revision')):
            raise WorkbenchError('Referenced document changed; inspect and deliberately refresh its exact revision.', 'conflict', 409)
        require(encode(annotation(doc['annotation'], doc)) == encode(doc['annotation']), 'Stored binary document target is invalid.')


def import_query(w, body):
    require(type(body) is dict and set(body) == {'name', 'text', 'groups', 'rights', 'judgments'}, 'Supply raw query text/name/groups/rights and declared judgments only.')
    values = judgments(body['judgments'])
    with w.lock, w.db:
        check_documents(w, values)
        return w.import_asset(dict(kind='text', name=body['name'], text=body['text'], groups=body['groups'],
            rights=body['rights'], parents=[v['document']['id'] for v in values]),
            acquisition={'format': 'text_retrieval_binary_query_v2', 'declared_judgments': values})


def setup(w):
    w.db.execute('CREATE TABLE IF NOT EXISTS retrieval_binary_sources (id TEXT PRIMARY KEY, data TEXT NOT NULL, sha256 TEXT NOT NULL)')


def binding(w, row):
    """Immutable owner evidence applies across task changes and source deletion."""
    data = w.db.execute('SELECT data,sha256 FROM retrieval_binary_sources WHERE id=?', (row['id'],)).fetchone()
    acquisition = row['provenance'].get('acquisition')
    declared = type(acquisition) is dict and acquisition.get('format') == 'native_retrieval_binary_v2'
    if data is None:
        return False if declared else None
    try:
        value = json.loads(data[0])
        require(digest(data[0].encode()) == data[1] and type(value) is dict
            and set(value) == {'source_split', 'protected_groups', 'content_hash', 'source_sha256'}
            and value['source_split'] in ('train', 'validation', 'test')
            and strings(value['protected_groups'], 'Imported protected groups') == value['protected_groups']
            and value['protected_groups'] and value['content_hash'] == row['content_hash']
            and value['source_sha256'] == row['source_sha256'], 'Imported source binding changed.')
        return value
    except (ValueError, TypeError, KeyError, WorkbenchError):
        return False


def projection(prepared, filename):
    assignments = prepared['preview']['assignments']
    for row in prepared['rows']:
        a = row['annotation']; split = assignments[row['id']]
        group = prepared['groups'][prepared['roots'][row['id']]]
        if filename == 'corpus.jsonl' and a['role'] == 'document':
            yield {'doc_id': row['id'], 'text': row['text'], 'group': group, 'split': split}
        elif filename == 'queries.jsonl' and a['role'] == 'query':
            yield {'query_id': row['id'], 'text': row['text'], 'group': group, 'split': split}
        elif a['role'] == 'query' and filename in ('judgments.jsonl', 'qrels.txt'):
            for item in a['judgments']:
                if filename == 'qrels.txt':
                    yield f"{row['id']} 0 {item['document']['id']} {STATES[item['relevance']]}\n"
                else:
                    yield {'query': {k: row[k] for k in ('id', 'revision', 'source_revision')},
                        'document': item['document'], 'relevance': item['relevance'], 'group': group, 'split': split}


def stream_bytes(prepared, filename):
    for value in projection(prepared, filename):
        yield value.encode() if filename == 'qrels.txt' else (encode(value) + '\n').encode()


def counts(rows, assignments, roots):
    result = {}
    for split in ('train', 'validation', 'test'):
        selected = [r for r in rows if assignments[r['id']] == split]
        state_counts = {state: 0 for state in STATES}
        for row in selected:
            for item in row['annotation'].get('judgments', []):
                state_counts[item['relevance']] += 1
        result[split] = {'documents': sum(r['annotation']['role'] == 'document' for r in selected),
            'queries': sum(r['annotation']['role'] == 'query' for r in selected),
            'judgments': state_counts, 'families': len({roots[r['id']] for r in selected})}
    return result


def entries(prepared, body):
    preview = prepared['preview']; rows = prepared['rows']
    manifest = {'schema_version': 2, 'format': FORMAT, 'judgment_scope': SCOPE, 'seed': body['seed'],
        'records': rows, 'protected_components': prepared['snapshots'], 'lineage': preview['lineage'],
        'assignments': preview['assignments'], 'split_report': preview['split_report'],
        'retrieval_counts': preview['retrieval_counts'], 'files': prepared['files'], 'warnings': preview['warnings'],
        'assets': {r['id']: {'path': 'assets/' + r['id'] + '.txt', 'sha256': r['content_hash']} for r in rows}, 'limits': LIMITS}
    yield 'manifest.json', encode(manifest).encode(), None
    for row in rows:
        yield 'assets/' + row['id'] + '.txt', row['text'].encode(), row['content_hash']
    for filename in STREAM_FILES:
        yield filename, b'', None
        hasher = hashlib.sha256(); size = 0
        for raw in stream_bytes(prepared, filename):
            hasher.update(raw); size += len(raw)
            yield None, raw, None
        require(prepared['files'][filename] == {'bytes': size, 'sha256': hasher.hexdigest()}, 'Binary retrieval projection changed.')
    yield 'README.txt', README, None


def prepare(releases, body):
    from dataset_releases import family_context, allocate
    w = releases.workbench
    preview = {'format': FORMAT, 'eligible': False, 'selected_count': 0, 'analysis': None, 'blockers': [],
        'warnings': ['Explicit unjudged and omitted relations are not negatives; no ranking, training or model-quality qualification.'],
        'judgment_scope': SCOPE, 'lineage': [], 'assignments': {}, 'split_report': None, 'preview_token': None}
    try:
        require(type(body) is dict and not set(body) - {'format', 'items', 'ratios', 'seed', 'preview_token'}, 'Unknown binary retrieval release fields.')
        rows = sorted(w.selection(body.get('items'), max_snapshot_bytes=MAX_LOGICAL), key=lambda r: r['id'])
        require(len(rows) <= MAX_RECORDS, 'Binary profile supports at most 128 selected records.')
        preview['selected_count'] = len(rows); preview['analysis'] = analyze(rows)
        docs = {}; queries = []
        for row in rows:
            require(row['kind'] == 'text' and row['task'] == TASK and row['review'] == 'human_reviewed'
                and row['source_available'] and row['source_lineage_known'], 'Select available human-reviewed binary retrieval records only.')
            require(encode(annotation(row['annotation'], row)) == encode(row['annotation']), 'Stored binary relevance target is invalid.')
            require(digest(row['text'].encode()) == row['content_hash'], 'Binary source bytes changed.')
            if row['annotation']['role'] == 'document': docs[row['id']] = row
            else: queries.append(row)
        require(docs and queries, 'Select at least one document and one query; zero-positive queries are supported.')
        universe = w._all(); roots, groups, snapshots, preview['lineage'] = family_context(rows, universe)
        require(sum(len(v) for v in snapshots.values()) <= MAX_CONTEXT, 'Binary profile supports at most 5,000 declared context snapshots.')
        context_ids = {s['id'] for members in snapshots.values() for s in members}
        require(all(p in context_ids for members in snapshots.values() for s in members for p in s['parents']), 'Protected source parent snapshot is missing.')
        assignments, report = allocate(rows, universe, body.get('ratios'), body.get('seed'))
        preview['assignments'], preview['split_report'] = assignments, report
        for query in queries:
            values = query['annotation']['judgments']; check_documents(w, values)
            for item in values:
                ref = item['document']
                require(ref['id'] in docs, 'Select every referenced document, including explicit unjudged references.')
                require(assignments[ref['id']] == assignments[query['id']], 'Every declared relationship must stay in its whole-family split.')
        preview['retrieval_counts'] = counts(rows, assignments, roots)
        if any(rights_note(r) == 'unknown' for r in rows): preview['warnings'].append('Some source rights are unknown; inspect permission separately.')
        prepared = dict(preview=preview, rows=rows, roots=roots, groups=groups, snapshots=snapshots, files={})
        for filename in STREAM_FILES:
            h = hashlib.sha256(); size = 0
            for raw in stream_bytes(prepared, filename): h.update(raw); size += len(raw)
            prepared['files'][filename] = {'bytes': size, 'sha256': h.hexdigest()}
        total = sum(len(raw) for _, raw, _ in entries(prepared, body))
        require(total <= MAX_LOGICAL, 'Binary profile exceeds the complete logical 8 MiB archive bound.')
        preview['artifact_bytes'] = total
        preview['preview_token'] = digest(encode({'format': FORMAT, 'records': rows, 'families': snapshots,
            'assignments': assignments, 'ratios': body['ratios'], 'seed': body['seed'], 'scope': SCOPE, 'files': prepared['files']}).encode())
        preview['eligible'] = True
        return prepared
    except WorkbenchError as error:
        preview['blockers'].append({'message': str(error), 'code': error.code, 'status': error.status})
        return {'preview': preview}


def decode(raw):
    from native_text_import import decode as decode_json
    value = decode_json(raw)
    def depth(item, level=0):
        require(level <= 64, 'Binary JSON nesting exceeds depth 64.')
        if type(item) is dict:
            for key, child in item.items():
                depth(key, level + 1); depth(child, level + 1)
        elif type(item) is list:
            for child in item: depth(child, level + 1)
        elif type(item) is str:
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), 'Binary JSON requires valid Unicode without lone surrogates.')
        elif type(item) is float:
            require(math.isfinite(item), 'Binary JSON numbers must be finite, including exponent encodings.')
    depth(value)
    return value


def inspect_archive(raw, sha256):
    """Complete closed packet/known-graph validation before any owner insertion."""
    from native_sequence_dataset import bounded_zip, source_identity
    from dataset_releases import connected_components
    require(type(raw) is bytes and len(raw) <= MAX_PHYSICAL and type(sha256) is str and HASH.fullmatch(sha256)
        and digest(raw) == sha256, 'Supply complete binary release bytes and their exact SHA256.')
    try:
        with bounded_zip(raw, MAX_MEMBERS, MAX_LOGICAL) as archive:
            cursor = 0
            for info in sorted(archive.infolist(), key=lambda i: i.header_offset):
                require(info.header_offset == cursor and cursor + 30 <= len(raw), 'ZIP local members must be contiguous without extra bytes.')
                fields = struct.unpack_from('<4s5H3I2H', raw, cursor)
                require(fields[0] == b'PK\x03\x04' and fields[1] < 45 and fields[2] == info.flag_bits
                    and fields[2] in (0, 0x800) and fields[3] == 0 and fields[6] == info.CRC
                    and fields[7] == fields[8] == info.file_size and fields[10] == 0,
                    'Only exact stored local headers without extras or descriptors are supported.')
                require(raw[cursor + 30:cursor + 30 + fields[9]] == info.filename.encode('ascii'), 'ZIP local filename mismatch.')
                cursor += 30 + fields[9] + info.file_size
            require(cursor == archive.start_dir, 'ZIP local directory boundary mismatch.')
            payloads = {i.filename: archive.read(i) for i in archive.infolist()}
    except (ValueError, OSError, zipfile.BadZipFile, UnicodeError, AssertionError) as error:
        raise WorkbenchError('Invalid or truncated bounded stored binary ZIP: ' + str(error)) from None
    require('manifest.json' in payloads, 'Binary manifest missing.')
    m = decode(payloads['manifest.json'])
    require(type(m) is dict and set(m) == {'schema_version', 'format', 'judgment_scope', 'seed', 'records',
        'protected_components', 'lineage', 'assignments', 'split_report', 'retrieval_counts', 'files', 'assets', 'limits', 'warnings'}, 'Closed binary manifest required.')
    require(type(m['schema_version']) is int and m['schema_version'] == 2 and m['format'] == FORMAT
        and encode(m['judgment_scope']) == encode(SCOPE) and encode(m['limits']) == encode(LIMITS), 'Binary version/scope/limits mismatch.')
    require(type(m['seed']) is int and 0 <= m['seed'] <= 2**32 - 1, 'Invalid split seed.')
    rows = m['records']; require(type(rows) is list and 2 <= len(rows) <= MAX_RECORDS, 'Binary record count invalid.')
    ids = []; by_id = {}; docs = {}; queries = []
    for row in rows:
        require(type(row) is dict and RECORD_KEYS <= set(row) and not set(row) - RECORD_KEYS - {'target_proposal', 'grounded_context_binding'}, 'Closed binary source record required.')
        require(type(row['id']) is str and IDENTIFIER.fullmatch(row['id']) and row['id'] not in by_id, 'Unique binary record ID required.')
        require(row['kind'] == 'text' and row['task'] == TASK and row['review'] == 'human_reviewed'
            and row['source_available'] is True and row['source_lineage_known'] is True, 'Binary upstream record must be available and reviewed; local import remains draft.')
        require(type(row['text']) is str and unicodedata.normalize('NFC', row['text']) == row['text'] and '\r' not in row['text'], 'Canonical NFC/LF text required.')
        text_value(row['text'], 'Binary source text', MAX_TEXT)
        require(type(row['provenance']) is dict and row['provenance'].get('normalization') == 'NFC; LF newlines', 'Text provenance required.')
        text_value(row['name'], 'Name'); text_value(row['created_at'], 'Created time', 120); text_value(row['updated_at'], 'Updated time', 120)
        require(all(row[k] is None for k in ('width', 'height', 'corner_annotation')), 'Text geometry must be absent.')
        require(encode(annotation(row['annotation'], row)) == encode(row['annotation']), 'Exact canonical binary target required.')
        asset = 'assets/' + row['id'] + '.txt'
        require(payloads.get(asset) == row['text'].encode() and digest(payloads[asset]) == row['content_hash'], 'Binary asset hash/text mismatch.')
        ids.append(row['id']); by_id[row['id']] = row
        if row['annotation']['role'] == 'document': docs[row['id']] = row
        else: queries.append(row)
    require(ids == sorted(ids) and docs and queries, 'Sorted records need at least one document and query.')
    require(set(payloads) == {'manifest.json', 'README.txt', *STREAM_FILES} | {'assets/' + i + '.txt' for i in ids}, 'Binary archive membership mismatch.')
    require(payloads['README.txt'] == README and m['assets'] == {i: {'path': 'assets/' + i + '.txt', 'sha256': by_id[i]['content_hash']} for i in ids}, 'Binary asset/README association mismatch.')
    assignments = m['assignments']; require(type(assignments) is dict and set(assignments) == set(ids)
        and all(type(v) is str and v in ('train', 'validation', 'test') for v in assignments.values()), 'Exact split assignments required.')
    snapshots = m['protected_components']; require(type(snapshots) is dict and 1 <= len(snapshots) <= MAX_RECORDS, 'Binary family proof required.')
    members, family_by_id = {}, {}
    for family, group in snapshots.items():
        require(type(group) is list and group and len(group) <= MAX_CONTEXT, 'Bounded family snapshots required.')
        mids = []
        for member in group:
            require(type(member) is dict and set(member) == SNAPSHOT_KEYS, 'Closed source snapshot required.')
            require(type(member['id']) is str and IDENTIFIER.fullmatch(member['id']) and member['id'] not in members, 'Unique source snapshot required.')
            try: source_identity(member)
            except (ValueError, AssertionError) as error: raise WorkbenchError('Invalid source snapshot: ' + str(error)) from None
            require(strings(member['groups'], 'Source groups') == member['groups'] and member['groups'], 'Canonical source groups required.')
            require(strings(member['parents'], 'Source parents') == member['parents'] and all(IDENTIFIER.fullmatch(p) for p in member['parents']), 'Canonical parent IDs required.')
            mids.append(member['id']); members[member['id']] = member; family_by_id[member['id']] = family
        require(mids == sorted(mids) and family == 'component:' + digest(encode(mids).encode()), 'Family membership hash mismatch.')
    require(len(members) <= MAX_CONTEXT and set(ids) <= set(members), 'Source context count/membership invalid.')
    require(all(p in members for member in members.values() for p in member['parents']), 'Protected parent snapshot missing.')
    roots = connected_components(list(members.values())); declared_roots = {}
    lineage = []
    for family, group in snapshots.items():
        root_set = {roots[s['id']] for s in group}
        require(len(root_set) == 1 and not root_set & set(declared_roots), 'Declared family graph is disconnected or crosses components.')
        declared_roots[next(iter(root_set))] = family
        selected = [s['id'] for s in group if s['id'] in assignments]
        fixed = sorted({s['source_split'] for s in group if s['source_split'] != 'unassigned'})
        require(selected and len({assignments[i] for i in selected}) == 1 and len(fixed) <= 1
            and (not fixed or fixed[0] == assignments[selected[0]]), 'Whole-family/fixed split mismatch.')
        lineage.append(dict(id=family, selected_ids=selected, member_ids=[s['id'] for s in group],
            deleted_ids=[s['id'] for s in group if not s['source_available']], fixed_splits=fixed))
    require(m['lineage'] == sorted(lineage, key=lambda x: x['id']), 'Declared lineage differs from known graph.')
    for row in rows:
        require(encode({k: row[k] for k in SNAPSHOT_KEYS}) == encode(members[row['id']]), 'Selected source/family snapshot mismatch.')
    for query in queries:
        for item in query['annotation']['judgments']:
            ref = item['document']; doc = docs.get(ref['id'])
            require(doc is not None and all(type(ref[k]) is int and ref[k] == doc[k] for k in ('revision', 'source_revision'))
                and assignments[doc['id']] == assignments[query['id']], 'Stale, missing or cross-split document judgment.')
    require(type(m['split_report']) is dict and set(m['split_report']) == {'requested_percentages', 'actual_counts', 'independent_components', 'note'}, 'Closed split report required.')
    report = m['split_report']; require(type(report['requested_percentages']) is dict, 'Requested ratios required.')
    from dataset_releases import allocate
    # The known graph and exact requested allocation must reproduce every assignment.
    expected_assignments, expected_report = allocate(rows, list(members.values()), report['requested_percentages'], m['seed'])
    require(expected_assignments == assignments and encode(expected_report) == encode(report), 'Split allocation/report mismatch.')
    prepared = {'rows': rows, 'preview': {'assignments': assignments}, 'roots': roots, 'groups': declared_roots}
    require(encode(m['retrieval_counts']) == encode(counts(rows, assignments, roots)), 'Binary state/split counts mismatch.')
    require(type(m['files']) is dict and set(m['files']) == set(STREAM_FILES), 'Exact projection file proofs required.')
    for filename in STREAM_FILES:
        expected = b''.join(stream_bytes(prepared, filename))
        require(payloads[filename] == expected and encode(m['files'][filename]) == encode({'bytes': len(expected), 'sha256': digest(expected)}), 'Binary projection/qrels mismatch: ' + filename)
    require(type(m['warnings']) is list and all(type(v) is str and len(v) <= 2000 for v in m['warnings']), 'Bounded warnings required.')
    return m, family_by_id


def origin_groups(members):
    links = set(); retained = set()
    for member in members:
        links.add(('id', member['id']))
        links.update(('id', parent) for parent in member['parents'])
        for group in member['groups']:
            if group.startswith('retrieval-origin:') and HASH.fullmatch(group[17:]):
                retained.add(group)
            else:
                links.add(('group', group))
    result = sorted(retained | {'retrieval-origin:' + digest(encode(['retrieval-binary-origin-v2', *link]).encode()) for link in links})
    require(len(result) <= 30, 'Complete stable upstream family anchors exceed the thirty-group import bound; no lineage is dropped.')
    return result


def import_release(w, body):
    require(type(body) is dict and set(body) == {'archive', 'sha256'}, 'Supply exact base64 binary release archive and SHA256 only.')
    require(type(body['archive']) is str and len(body['archive']) <= (MAX_PHYSICAL + 2) // 3 * 4, 'Binary archive envelope exceeds bound.')
    try: raw = base64.b64decode(body['archive'], validate=True)
    except (ValueError, UnicodeError): raise WorkbenchError('Binary archive must be valid base64.') from None
    m, families = inspect_archive(raw, body['sha256'])
    protected = {family: origin_groups(members) for family, members in m['protected_components'].items()}
    # One explicit savepoint owns all records/bindings/history, even under an outer caller transaction.
    with w.lock:
        w.db.execute('SAVEPOINT binary_import')
        try:
            mapped = {}; rows = m['records']
            for row in rows:
                group = protected[families[row['id']]]
                # No public import_asset nesting: _insert_text remains inside this atomic savepoint.
                new = w._insert_text(row['text'], row['name'], group, [], 'unknown', provenance={'acquisition': {
                    'format': 'native_retrieval_binary_v2', 'release_sha256': body['sha256'], 'upstream_record': row,
                    'source_family': families[row['id']], 'source_split': m['assignments'][row['id']]}})
                mapped[row['id']] = new['id']
                binding_data = encode({'source_split': m['assignments'][row['id']], 'protected_groups': group,
                    'content_hash': new['content_hash'], 'source_sha256': new['source_sha256']})
                w.db.execute('INSERT INTO retrieval_binary_sources VALUES (?,?,?)', (new['id'], binding_data, digest(binding_data.encode())))
            for row in rows:
                local_id = mapped[row['id']]; target = dict(row['annotation'])
                parents = [mapped[p] for p in row['parents'] if p in mapped]
                if target['role'] == 'query':
                    target['judgments'] = [dict(item, document={'id': mapped[item['document']['id']], 'revision': 1, 'source_revision': 1}) for item in target['judgments']]
                w.db.execute('UPDATE workbench_records SET task=?,annotation_json=?,parents_json=? WHERE id=?',
                    (TASK, encode(target), encode(parents), local_id))
                w.db.execute('DELETE FROM workbench_history WHERE id=?', (local_id,))
                w._history(w._get(local_id))
            result = {'records': [w._get(mapped[r['id']]) for r in rows], 'id_map': mapped, 'release_sha256': body['sha256']}
            w.db.execute('RELEASE binary_import')
            return result
        except BaseException:
            w.db.execute('ROLLBACK TO binary_import'); w.db.execute('RELEASE binary_import')
            raise
