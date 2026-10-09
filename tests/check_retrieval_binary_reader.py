"""Independent bounded binary oracle and unchanged released source-loaded reader.

Only actual Qrel/read_trec_qrels definitions execute from ir_measures. No full
package/provider initialization, ranking, metrics, model loading or training.
"""
import argparse
import ast
import base64
import copy
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import stat
import struct
import sys
import typing
import unicodedata
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
SOURCE = FIXTURES / 'retrieval_binary_consumer'
MAX_PHYSICAL = 9 * 1024 * 1024
MAX_LOGICAL = 8 * 1024 * 1024
MAX_RECORDS = 128
MAX_MEMBERS = 134
MAX_CONTEXT = 5000
STREAMS = ('corpus.jsonl', 'queries.jsonl', 'judgments.jsonl', 'qrels.txt')
SPLITS = ('train', 'validation', 'test')
STATES = {'relevant': 1, 'not_relevant': 0, 'unjudged': -1}
SCOPE = {'kind': 'human_binary_relevance', 'relevance_values': STATES,
    'omitted_relationships': 'unjudged', 'explicit_unjudged': 'retained, not a reviewed negative',
    'imported_review': 'draft; upstream review is evidence only',
    'qualification': 'source transport and qrels reading only; no ranking, metrics, training or model quality'}
LIMITS = {'selected_records': 128, 'judgments_per_query': 30,
    'logical_archive_bytes': MAX_LOGICAL, 'context_snapshots': MAX_CONTEXT}
README = ("Tuldok reviewed binary retrieval v2. Relevant=1, not relevant=0, explicit unjudged=-1.\n"
    "Omitted query-document relationships remain unjudged; no Cartesian negatives or implicit pairs.\n"
    "Exact typed judgments and manifest are semantic authority; qrels.txt has four TREC fields.\n"
    "All declared relations and retained former parents stay in one whole-family split.\n"
    "Imported records become local drafts with unknown rights, new IDs and remapped document refs.\n"
    "Separate human document review changes revisions: deliberately refresh query refs before review.\n"
    "Source/family/rights claims are not authenticated. No ranking, metrics, training or model quality.\n").encode()
ID = re.compile(r'[a-f0-9]{32}')
HASH = re.compile(r'[a-f0-9]{64}')
SNAPSHOT_KEYS = {'id', 'kind', 'revision', 'source_revision', 'content_hash', 'pixel_hash',
    'groups', 'parents', 'source_available', 'source_lineage_known', 'source_split',
    'source_sha256', 'book_id', 'session_id'}
RECORD_KEYS = SNAPSHOT_KEYS | {'name', 'text', 'task', 'annotation', 'review', 'created_at',
    'updated_at', 'provenance', 'width', 'height', 'corner_annotation'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def decode(raw):
    require(type(raw) is bytes and len(raw) <= MAX_LOGICAL, 'JSON byte cap')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def bad(value):
        raise ValueError('Nonfinite JSON ' + value)
    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=bad)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= 64, 'JSON depth cap')
            if type(value) is float:
                require(math.isfinite(value), 'Nonfinite JSON overflow')
            elif type(value) is dict:
                pending.extend((v, depth + 1) for v in value.values())
            elif type(value) is list:
                pending.extend((v, depth + 1) for v in value)
            elif type(value) is str:
                value.encode('utf-8')
        return result
    except (UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError('Malformed bounded UTF-8 JSON') from error


def capture(path, maximum):
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require(0 < len(raw) <= maximum, 'Captured file byte cap')
    return raw


def zip_payloads(raw):
    require(type(raw) is bytes and 22 <= len(raw) <= MAX_PHYSICAL, 'ZIP physical cap')
    require(raw[-22:-18] == b'PK\x05\x06', 'Exact comment-free ZIP EOF')
    _, disk, central_disk, disk_count, count, size, offset, comment = struct.unpack('<4s4H2IH', raw[-22:])
    require(disk == central_disk == comment == 0 and disk_count == count and 7 <= count <= MAX_MEMBERS,
        'ZIP entry count before allocation')
    require(offset + size == len(raw) - 22, 'Exact ZIP central custody')
    cursor = offset
    for _ in range(count):
        require(cursor + 46 <= offset + size and raw[cursor:cursor + 4] == b'PK\x01\x02', 'ZIP central record')
        name, extra, note = struct.unpack_from('<3H', raw, cursor + 28)
        require(0 < name <= 256 and extra == note == 0, 'ZIP names/no ZIP64 or member comments')
        cursor += 46 + name
    require(cursor == offset + size, 'ZIP exact declared central count')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(len(infos) == count and len({i.filename for i in infos}) == count, 'Duplicate ZIP members')
            require(sum(i.file_size for i in infos) <= MAX_LOGICAL, 'Complete logical ZIP cap')
            payloads = {}; cursor = 0
            for item in sorted(infos, key=lambda i: i.header_offset):
                require(item.compress_type == zipfile.ZIP_STORED and item.compress_size == item.file_size
                    and item.flag_bits in (0, 0x800), 'Only plain stored ZIP members')
                require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG)
                    and not item.is_dir() and not item.external_attr & 0x10, 'Only regular ZIP files')
                require(item.header_offset == cursor and raw[cursor:cursor + 4] == b'PK\x03\x04', 'Contiguous ZIP local custody')
                flags, method = struct.unpack_from('<HH', raw, cursor + 6)
                crc, compressed, logical, name_len, extra_len = struct.unpack_from('<IIIHH', raw, cursor + 14)
                require(flags == item.flag_bits and method == 0 and extra_len == 0 and crc == item.CRC
                    and compressed == logical == item.file_size, 'ZIP local/central association')
                name = raw[cursor + 30:cursor + 30 + name_len].decode('utf-8' if flags & 0x800 else 'cp437')
                require(name == item.filename and not name.startswith('/') and '\\' not in name
                    and all(p not in ('', '.', '..') for p in name.split('/')), 'ZIP path association')
                cursor += 30 + name_len + logical
                require(cursor <= offset, 'ZIP payload custody')
                payloads[name] = archive.read(item)
            require(cursor == offset, 'No hidden ZIP prefix/trailer')
            return payloads
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, OSError, EOFError, struct.error) as error:
        raise ValueError('Invalid ZIP bytes/CRC') from error


def integer(value, name):
    require(type(value) is int and 1 <= value <= 2**63 - 1, name + ' exact positive signed64 integer')


def strings(value, name, identifiers=False):
    require(type(value) is list and len(value) <= 30
        and all(type(v) is str and v and len(v) <= 120 and (not identifiers or ID.fullmatch(v)) for v in value)
        and len(value) == len(set(value)), name + ' bounded unique strings')


def graph_oracle(manifest, rows):
    snapshots = manifest['protected_components']
    require(type(snapshots) is dict and 1 <= len(snapshots) <= MAX_CONTEXT, 'Bounded protected components')
    require(sum(len(v) for v in snapshots.values() if type(v) is list) <= MAX_CONTEXT, 'Total context cap')
    parents = {}; by_id = {}; family_by_id = {}
    def root(key):
        parents.setdefault(key, key)
        while key != parents[key]:
            parents[key] = parents[parents[key]]; key = parents[key]
        return key
    def join(a, b):
        parents[root(b)] = root(a)
    for family, members in snapshots.items():
        require(type(members) is list and 1 <= len(members) <= MAX_CONTEXT, 'Bounded component members')
        require(all(type(s) is dict and set(s) == SNAPSHOT_KEYS for s in members), 'Closed source snapshots')
        ids = [s['id'] for s in members]
        require(all(type(i) is str and ID.fullmatch(i) for i in ids) and ids == sorted(set(ids))
            and family == 'component:' + sha(encoded(ids).encode()), 'Exact sorted family identity')
        for source in members:
            ident = source['id']; require(ident not in by_id, 'Unique complete context IDs')
            require(source['kind'] in ('text', 'image', 'sequence', 'mesh', 'pointcloud'), 'Known snapshot kind')
            integer(source['revision'], 'Context revision')
            require(type(source['source_available']) is bool and source['source_lineage_known'] is True,
                'Typed known context lineage')
            require(source['source_split'] in ('unassigned', *SPLITS), 'Context split')
            strings(source['groups'], 'Context groups'); strings(source['parents'], 'Context parents', True)
            require(type(source['content_hash']) is str and (not source['content_hash'] or HASH.fullmatch(source['content_hash'])), 'Context content hash')
            require(source['pixel_hash'] is None or type(source['pixel_hash']) is str and HASH.fullmatch(source['pixel_hash']), 'Context pixel hash')
            if source['kind'] == 'text':
                require(type(source['source_revision']) is int and source['source_revision'] == 1
                    and type(source['source_sha256']) is str and HASH.fullmatch(source['source_sha256'])
                    and source['pixel_hash'] is source['book_id'] is source['session_id'] is None, 'Text context identity')
            elif source['kind'] in ('sequence', 'mesh', 'pointcloud'):
                require(type(source['source_revision']) is int and source['source_revision'] == 1
                    and source['source_sha256'] == source['content_hash'] and HASH.fullmatch(source['content_hash'])
                    and (source['kind'] == 'pointcloud' or source['source_split'] == 'unassigned')
                    and source['pixel_hash'] is source['book_id'] is source['session_id'] is None, 'Immutable context identity')
            elif source['source_available']:
                integer(source['source_revision'], 'Image context revision')
                require(type(source['source_sha256']) is str and HASH.fullmatch(source['source_sha256']), 'Image raw hash')
            else:
                require(source['source_revision'] is source['source_sha256'] is None, 'Deleted image identity')
            by_id[ident] = source; family_by_id[ident] = family
            key = 'id:' + ident; root(key)
            links = ['group:' + g for g in source['groups']] + ['id:' + p for p in source['parents']]
            if source['content_hash']: links.append('content:' + source['kind'] + ':' + source['content_hash'])
            if source['pixel_hash']: links.append('pixels:' + source['pixel_hash'])
            if source['kind'] == 'image':
                require(type(source['book_id']) is str and type(source['session_id']) is str, 'Image lineage strings')
                links.append('legacy:' + ('book:' + source['book_id'] if source['book_id'] else 'session:' + source['session_id']))
            for link in links: join(key, link)
    graph_families = {}
    for ident in by_id: graph_families.setdefault(root('id:' + ident), set()).add(family_by_id[ident])
    require(all(len(v) == 1 for v in graph_families.values()) and len(graph_families) == len(snapshots), 'Declared known graph closure')
    assignments = manifest['assignments']; ids = {row['id'] for row in rows}
    require(type(assignments) is dict and set(assignments) == ids and all(v in SPLITS for v in assignments.values()), 'Exact selected split assignments')
    require(ids <= by_id.keys() and all(p in by_id for s in by_id.values() for p in s['parents']),
        'Every selected source and retained parent has context')
    lineage = []
    for family, members in snapshots.items():
        selected = [s['id'] for s in members if s['id'] in ids]
        fixed = sorted({s['source_split'] for s in members if s['source_split'] in SPLITS})
        require(selected and len({assignments[i] for i in selected}) == 1 and len(fixed) <= 1
            and (not fixed or assignments[selected[0]] == fixed[0]), 'Whole family/fixed split')
        lineage.append(dict(id=family, selected_ids=selected, member_ids=[s['id'] for s in members],
            deleted_ids=[s['id'] for s in members if not s['source_available']], fixed_splits=fixed))
    require(encoded(manifest['lineage']) == encoded(sorted(lineage, key=lambda f: f['id'])), 'Exact lineage projection')
    for row in rows:
        require(encoded({k: row[k] for k in SNAPSHOT_KEYS}) == encoded(by_id[row['id']]), 'Selected snapshot equality')
    return family_by_id, by_id


def load_reader():
    pins = decode((SOURCE / 'pins.json').read_bytes())
    require(type(pins) is dict and set(pins) == {'format', 'package', 'version', 'release_url', 'wheel_name',
        'wheel_bytes', 'wheel_sha256', 'files', 'source_path', 'definitions', 'definition_ast_sha256', 'scope'}, 'Closed reader pins')
    require(pins['format'] == 'retrieval-binary-reader-pins-v1'
        and pins['package'] == 'ir_measures' and pins['version'] == '0.4.3'
        and pins['release_url'] == 'https://pypi.org/project/ir-measures/0.4.3/'
        and pins['wheel_name'] == 'ir_measures-0.4.3-py3-none-any.whl'
        and type(pins['wheel_bytes']) is int and pins['wheel_bytes'] == 61311
        and pins['wheel_sha256'] == '3d8b3b5283e4a77df85f9f6c8a1c2c99a7421b78fa014ef97f2ddab3037d3dcf'
        and type(pins['files']) is dict and set(pins['files']) == {'util.py', 'LICENSE.txt'}
        and pins['source_path'] == 'ir_measures/util.py' and pins['definitions'] == ['Qrel', 'read_trec_qrels']
        and pins['files']['util.py'] == '0920e4b211b1d32e2fed011dddc8f96ce589b63e379d10fd9b4fa1c454afcc6e', 'Released source pins')
    for name, digest in pins['files'].items():
        require(name in ('util.py', 'LICENSE.txt') and sha((SOURCE / name).read_bytes()) == digest, 'Complete released fixture bytes')
    tree = ast.parse((SOURCE / 'util.py').read_bytes())
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in pins['definitions']]
    module = ast.Module(body=nodes, type_ignores=[])
    require([n.name for n in nodes] == ['Qrel', 'read_trec_qrels']
        and sha(ast.dump(module, include_attributes=False).encode()) == pins['definition_ast_sha256']
        == 'ce0aff6105b59223459b163741e9019233b5a5527e00d21d1d5e39413ae1b46a', 'Exact unchanged executed definitions')
    allowed = {'hasattr', 'int', 'isinstance', 'open', 'read_trec_qrels', 'io.StringIO', 'gzip.open',
        'line.strip', 'line.split', 'Qrel', 'file.endswith', 'reader'}
    for node in ast.walk(module):
        if isinstance(node, ast.Call):
            require(ast.unparse(node.func) in allowed, 'Closed external reader call scope')
        require(not isinstance(node, (ast.Import, ast.ImportFrom)), 'No external reader imports')
    before = set(sys.modules)
    namespace = {'NamedTuple': typing.NamedTuple, 'io': io, 'gzip': gzip}
    exec(compile(module, 'ir_measures-0.4.3/ir_measures/util.py', 'exec'), namespace)
    require(namespace['Qrel']._fields == ('query_id', 'doc_id', 'relevance', 'iteration'), 'Actual released Qrel schema')
    require(not any(n.split('.')[0] in ('ir_measures', 'pytrec_eval', 'ranx', 'sklearn', 'torch', 'transformers')
        for n in set(sys.modules) - before), 'No package/providers/models import')
    return namespace['read_trec_qrels'], pins


def allocation_oracle(manifest, family_by_id):
    report = manifest['split_report']
    require(type(report) is dict and set(report) == {'requested_percentages', 'actual_counts', 'independent_components', 'note'},
        'Exact existing allocator report schema')
    ratios = report['requested_percentages']
    require(type(ratios) is dict and set(ratios) == set(SPLITS)
        and all(type(n) is int and 0 <= n <= 100 for n in ratios.values()) and sum(ratios.values()) == 100,
        'Exact bounded active split ratios')
    families = {}
    for row in manifest['records']: families.setdefault(family_by_id[row['id']], []).append(row['id'])
    active = [s for s in SPLITS if ratios[s]]
    require(len(families) >= len(active), 'Enough active whole families')
    assigned = {}; counts = {}; pending = []
    for family, ids in families.items():
        fixed = {s['source_split'] for s in manifest['protected_components'][family] if s['source_split'] in SPLITS}
        require(len(fixed) <= 1, 'No conflicting fixed source splits')
        if fixed:
            split = next(iter(fixed)); require(ratios[split] > 0, 'Fixed split has active weight')
            assigned.update({i: split for i in ids}); counts[split] = counts.get(split, 0) + len(ids)
        else: pending.append(ids)
    require(len(pending) >= sum(not counts.get(s, 0) for s in active), 'Enough free active families')
    pending.sort(key=lambda ids: (-len(ids), sha((str(manifest['seed']) + ':' + ','.join(sorted(ids))).encode())))
    for index, ids in enumerate(pending):
        empty = [s for s in active if not counts.get(s, 0)]
        choices = empty if len(pending) - index == len(empty) else active
        split = max(choices, key=lambda s: (ratios[s] * len(manifest['records']) / 100 - counts.get(s, 0), -SPLITS.index(s)))
        assigned.update({i: split for i in ids}); counts[split] = counts.get(split, 0) + len(ids)
    expected = dict(requested_percentages=ratios, actual_counts=counts, independent_components=len(families),
        note='Whole connected groups are indivisible; existing source splits are preserved. Requested percentages are targets, not exact quotas.')
    require(encoded(report) == encoded(expected) and assigned == manifest['assignments'], 'Independent complete split allocation')


def inspect_archive(raw, expected_records=None):
    payloads = zip_payloads(raw)
    require('manifest.json' in payloads, 'Manifest required')
    manifest = decode(payloads['manifest.json'])
    require(type(manifest) is dict and set(manifest) == {'schema_version', 'format', 'judgment_scope', 'seed',
        'records', 'protected_components', 'lineage', 'assignments', 'split_report', 'retrieval_counts',
        'files', 'assets', 'limits', 'warnings'}, 'Closed binary manifest')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 2
        and manifest['format'] == 'text_retrieval_binary_v2', 'Binary format/version')
    require(encoded(manifest['judgment_scope']) == encoded(SCOPE) and encoded(manifest['limits']) == encoded(LIMITS),
        'Exact three-state contract and limits')
    require(type(manifest['seed']) is int and 0 <= manifest['seed'] <= 2**32 - 1, 'Bounded seed')
    rows = manifest['records']
    require(type(rows) is list and 2 <= len(rows) <= MAX_RECORDS, 'Selected record count')
    require(all(type(r) is dict and RECORD_KEYS <= set(r) and not set(r) - RECORD_KEYS - {'target_proposal', 'grounded_context_binding'} for r in rows),
        'Closed source records')
    ids = [r['id'] for r in rows]
    require(all(type(i) is str and ID.fullmatch(i) for i in ids) and ids == sorted(set(ids)), 'Sorted unique record IDs')
    require(set(payloads) == {'manifest.json', 'README.txt', *STREAMS} | {'assets/' + i + '.txt' for i in ids},
        'Exact member closure')
    require(payloads['README.txt'] == README, 'Exact frozen semantic scope')
    if expected_records is not None:
        expected = sorted(expected_records, key=lambda r: r['id'])
        require(encoded(rows) == encoded(expected), 'Exact selected sources/targets/revisions/rights/provenance')
    docs = {}; queries = []
    for row in rows:
        integer(row['revision'], 'Record revision')
        require(type(row['source_revision']) is int and row['source_revision'] == 1, 'Immutable text source revision')
        require(row['kind'] == 'text' and row['task'] == 'text_retrieval_binary' and row['review'] == 'human_reviewed'
            and row['source_available'] is row['source_lineage_known'] is True, 'Available reviewed binary source')
        require(row['source_split'] in ('unassigned', *SPLITS)
            and all(row[k] is None for k in ('pixel_hash', 'book_id', 'session_id', 'width', 'height', 'corner_annotation')), 'Text identity')
        require(type(row['text']) is str and row['text'].strip() and 0 < len(row['text']) <= 200000
            and '\r' not in row['text'] and unicodedata.normalize('NFC', row['text']) == row['text'], 'Canonical NFC/LF source')
        for key in ('name', 'created_at', 'updated_at'):
            require(type(row[key]) is str and row[key].strip() and len(row[key]) <= (200 if key == 'name' else 120), 'Bounded record metadata')
        require(type(row['source_sha256']) is str and HASH.fullmatch(row['source_sha256'])
            and type(row['provenance']) is dict and row['provenance'].get('normalization') == 'NFC; LF newlines', 'Original source provenance')
        asset = payloads['assets/' + row['id'] + '.txt']
        require(asset == row['text'].encode() and sha(asset) == row['content_hash'], 'Exact source asset/hash')
        strings(row['groups'], 'Groups'); strings(row['parents'], 'Parents', True)
        require(row['groups'], 'Protected source groups')
        a = row['annotation']
        require(type(a) is dict and a.get('role') in ('document', 'query'), 'Document/query role')
        require(type(a.get('note')) is str and a['note'].strip() == a['note'] and 0 < len(a['note']) <= 4000, 'Nonempty canonical review note')
        require(set(a) == ({'role', 'note'} if a['role'] == 'document' else {'role', 'note', 'judgments'}), 'Closed binary target')
        if a['role'] == 'document': docs[row['id']] = row
        else:
            values = a['judgments']; require(type(values) is list and 1 <= len(values) <= 30, 'Bounded explicit relationships')
            seen = set()
            for value in values:
                require(type(value) is dict and set(value) == {'document', 'relevance'}
                    and type(value['relevance']) is str and value['relevance'] in STATES, 'Strict string relevance state')
                ref = value['document']; require(type(ref) is dict and set(ref) == {'id', 'revision', 'source_revision'}, 'Exact closed document ref')
                require(type(ref['id']) is str and ID.fullmatch(ref['id']) and ref['id'] not in seen and ref['id'] in row['parents'], 'Unique immutable referenced parent')
                integer(ref['revision'], 'Document ref revision'); integer(ref['source_revision'], 'Document ref source revision')
                seen.add(ref['id'])
            queries.append(row)
    require(docs and queries, 'At least one document and query')
    require(encoded(manifest['assets']) == encoded({i: dict(path='assets/' + i + '.txt', sha256=next(r['content_hash'] for r in rows if r['id'] == i)) for i in ids}),
        'Exact asset proofs')
    family, snapshots = graph_oracle(manifest, rows); allocation_oracle(manifest, family)
    streams = {name: [] for name in STREAMS if name != 'qrels.txt'}; qrels = []; pairs = []
    counts = {split: dict(documents=0, queries=0, judgments={state: 0 for state in STATES}, families=0) for split in SPLITS}
    for split in SPLITS: counts[split]['families'] = len({family[r['id']] for r in rows if manifest['assignments'][r['id']] == split})
    for row in rows:
        split = manifest['assignments'][row['id']]; group = family[row['id']]
        if row['annotation']['role'] == 'document':
            counts[split]['documents'] += 1
            streams['corpus.jsonl'].append(dict(doc_id=row['id'], text=row['text'], group=group, split=split))
        else:
            counts[split]['queries'] += 1
            streams['queries.jsonl'].append(dict(query_id=row['id'], text=row['text'], group=group, split=split))
            for value in row['annotation']['judgments']:
                ref = value['document']; require(ref['id'] in docs, 'Every explicit relationship selected')
                doc = docs[ref['id']]
                require(all(ref[k] == doc[k] for k in ('revision', 'source_revision'))
                    and manifest['assignments'][doc['id']] == split and family[doc['id']] == group, 'Exact current same-family relation')
                state = value['relevance']; counts[split]['judgments'][state] += 1
                streams['judgments.jsonl'].append(dict(query={k: row[k] for k in ('id', 'revision', 'source_revision')},
                    document=ref, relevance=state, split=split, group=group))
                qrels.append(f"{row['id']} 0 {ref['id']} {STATES[state]}\n")
                pairs.append(dict(query_id=row['id'], doc_id=ref['id'], relevance=STATES[state], iteration='0'))
    require(encoded(manifest['retrieval_counts']) == encoded(counts), 'Exact state/split counts')
    require(type(manifest['files']) is dict and set(manifest['files']) == set(STREAMS), 'Closed stream proofs')
    for filename in STREAMS:
        expected = ''.join(qrels).encode() if filename == 'qrels.txt' else ''.join(encoded(v) + '\n' for v in streams[filename]).encode()
        require(payloads[filename] == expected, 'Independent exact closed projection: ' + filename)
        require(encoded(manifest['files'][filename]) == encoded(dict(bytes=len(expected), sha256=sha(expected))), 'Exact stream proof')
        if filename.endswith('.jsonl'):
            require(encoded([decode(line) for line in expected.splitlines()]) == encoded(streams[filename]), 'Independent finite JSONL decoding')
    require(type(manifest['warnings']) is list and all(type(s) is str and len(s) <= 2000 for s in manifest['warnings']), 'Bounded warning strings')
    return dict(manifest=manifest, payloads=payloads, expected_qrels=pairs, counts=counts,
        documents=len(docs), queries=len(queries), judgments=len(pairs), families=len(manifest['protected_components']),
        context_snapshots=len(snapshots), explicit_state_counts={state: sum(c['judgments'][state] for c in counts.values()) for state in STATES})


def verify(raw, output, expected_records=None):
    checked = inspect_archive(raw, expected_records)
    reader, pins = load_reader()
    path = output / 'external-reader-qrels.txt'
    require(not path.is_symlink(), 'External file cannot be a symlink')
    path.write_bytes(checked['payloads']['qrels.txt'])
    with path.open('rt', encoding='utf-8') as source:
        actual = [r._asdict() for r in reader(source)]
    require(encoded(actual) == encoded(checked['expected_qrels']) and all(type(r['relevance']) is int for r in actual),
        'Actual unchanged released source-loaded file reader preserves signed integers')
    return dict(status='passed', result='PASS', archive=dict(bytes=len(raw), sha256=sha(raw)),
        counts=checked['counts'], documents=checked['documents'], queries=checked['queries'], judgments=checked['judgments'],
        families=checked['families'], context_snapshots=checked['context_snapshots'], explicit_state_counts=checked['explicit_state_counts'],
        judgment_scope=SCOPE, actual_qrels=actual, external_reader_pins=pins,
        external_execution='source-loaded unchanged Qrel/read_trec_qrels on real local UTF-8 file; not full installed package',
        exact_source_target_family_and_projection_oracle=True, external_definition_call_scope_guard=True,
        files={n: dict(bytes=len(v), sha256=sha(v)) for n, v in checked['payloads'].items()},
        ranking_executed=False, metrics_executed=False, training_executed=False, model_loading=False, downloads=False,
        negatives_inferred=False, scope='Authored transport/control QA; no semantic relevance, permission, independent corpus or model-quality qualification.')


def archive_from(payloads, duplicate=None, symlink=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        for name, raw in payloads.items():
            info = zipfile.ZipInfo(name)
            if name == symlink: info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, raw)
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr(duplicate, payloads[duplicate])
    return output.getvalue()


def output_preflight(path):
    output = path.resolve()
    try:
        relative = output.relative_to(ROOT.resolve())
        require(relative.parts and relative.parts[0] in ('build', 'output'), 'Output cannot write tracked source')
    except ValueError:
        require(not output.is_relative_to(ROOT.resolve()), 'Output cannot write tracked source')
    output.mkdir(parents=True, exist_ok=True)
    return output


def malformed_oracles(raw):
    payloads = zip_payloads(raw); cases = {}
    def changed(mutate):
        files = dict(payloads); manifest = decode(files['manifest.json']); mutate(manifest)
        files['manifest.json'] = encoded(manifest).encode(); return archive_from(files)
    def query(m): return next(r for r in m['records'] if r['annotation']['role'] == 'query')
    cases['numeric_relevance'] = changed(lambda m: query(m)['annotation']['judgments'][0].update(relevance=1))
    cases['boolean_reference_revision'] = changed(lambda m: query(m)['annotation']['judgments'][0]['document'].update(revision=True))
    cases['stale_reference'] = changed(lambda m: query(m)['annotation']['judgments'][0]['document'].update(revision=999))
    cases['duplicate_relationship'] = changed(lambda m: query(m)['annotation']['judgments'].append(copy.deepcopy(query(m)['annotation']['judgments'][0])))
    cases['unjudged_as_negative_scope'] = changed(lambda m: m['judgment_scope'].update(omitted_relationships='not_relevant'))
    cases['missing_family_proof'] = changed(lambda m: m.update(protected_components={}))
    cases['family_cross_split'] = changed(lambda m: m['assignments'].update({query(m)['id']:next(s for s in SPLITS if s != m['assignments'][query(m)['id']])}))
    def boolean_count(m):
        for split in SPLITS:
            for state, count in m['retrieval_counts'][split]['judgments'].items():
                if count == 1:
                    m['retrieval_counts'][split]['judgments'][state] = True; return
        raise AssertionError('One-valued fixture count required')
    cases['boolean_state_count'] = changed(boolean_count)
    cases['wrong_asset_hash'] = changed(lambda m: m['assets'][m['records'][0]['id']].update(sha256='0'*64))
    cases['nonfinite_manifest'] = archive_from(dict(payloads, **{'manifest.json': b'{"field":NaN}'}))
    cases['duplicate_manifest_key'] = archive_from(dict(payloads, **{'manifest.json': b'{"schema_version":2,"schema_version":2}'}))
    cases['deep_manifest'] = changed(lambda m: m['records'][0]['provenance'].update(extra=decode(b'['*64+b'0'+b']'*64)))
    cases['duplicate_zip_member'] = archive_from(payloads, duplicate='qrels.txt')
    cases['symlink_member'] = archive_from(payloads, symlink='qrels.txt')
    cases['truncated_zip'] = raw[:-7]
    for label, name, replacement in (
        ('qrels_wrong_integer','qrels.txt',payloads['qrels.txt'].replace(b' -1\n',b' -2\n',1)),
        ('qrels_duplicate_row','qrels.txt',payloads['qrels.txt']+payloads['qrels.txt'].splitlines(keepends=True)[0]),
        ('qrels_omitted_explicit_unjudged','qrels.txt',b''.join(l for l in payloads['qrels.txt'].splitlines(keepends=True) if not l.endswith(b' -1\n'))),
        ('invalid_utf8_jsonl','corpus.jsonl',b'{"text":"\xff"}\n'),
        ('nonfinite_jsonl','judgments.jsonl',b'{"relevance":NaN}\n'),
        ('extra_implicit_negative_field','queries.jsonl',b'{"negative_doc_ids":[]}\n')):
        files = dict(payloads); files[name] = replacement
        m = decode(files['manifest.json']); m['files'][name] = dict(bytes=len(replacement),sha256=sha(replacement))
        files['manifest.json'] = encoded(m).encode(); cases[label] = archive_from(files)
    forged = bytearray(raw); struct.pack_into('<HH', forged, len(raw)-22+8, 135, 135)
    cases['declared_member_count_cap'] = bytes(forged)
    for label, malformed in cases.items():
        try: inspect_archive(malformed)
        except (ValueError, TypeError, KeyError): pass
        else: raise AssertionError('Independent malformed oracle admitted: '+label)
    return cases


def second_owner(raw, checked, output):
    # Owner operations are the subject of the oracle, not validation helpers.
    from app import Dataset
    from workbench import WorkbenchError
    from retrieval_binary import import_release
    from retrieval_binary_fixture import ref, save, freeze
    dataset = Dataset(output / 'owner-second')
    try:
        w = dataset.workbench; request = dict(archive=base64.b64encode(raw).decode(),sha256=sha(raw))
        imported = import_release(w,request); mapped = imported['id_map']; rows = imported['records']
        upstream = checked['manifest']['records']; by_id = {r['id']:r for r in upstream}
        require(set(mapped)==set(by_id) and len(set(mapped.values()))==len(rows)
            and set(mapped).isdisjoint(mapped.values()), 'New disjoint exact imported IDs')
        for row in rows:
            old = next(r for r in upstream if mapped[r['id']]==row['id'])
            require(row['review']=='draft' and row['revision']==1 and row['provenance']['rights']=='unknown'
                and row['task']=='text_retrieval_binary' and row['text']==old['text']
                and row['content_hash']==old['content_hash'] and row['source_split']==checked['manifest']['assignments'][old['id']],
                'Imported exact source/fixed split remains draft with unknown rights')
            require(row['parents']==[mapped[p] for p in old['parents'] if p in mapped], 'Exact selected parent remap')
            annotation = copy.deepcopy(old['annotation'])
            if annotation['role']=='query':
                for item in annotation['judgments']:
                    item['document']=dict(id=mapped[item['document']['id']],revision=1,source_revision=1)
            require(encoded(row['annotation'])==encoded(annotation), 'Exact three-state imported evidence/remapped refs')
            require(len(w.history(row['id']))==1, 'Separate new local initial history')
        initial = copy.deepcopy(rows)
        docs = [save(w,r,r['annotation']) for r in rows if r['annotation']['role']=='document']
        current_docs = {r['id']:r for r in docs}; reviewed=[]; stale_refusals=0
        for row in [r for r in rows if r['annotation']['role']=='query']:
            before=tuple(dataset.db.iterdump())
            try: save(w,row,row['annotation'])
            except WorkbenchError: stale_refusals+=1
            else: raise AssertionError('Document review did not make imported query refs stale')
            require(tuple(dataset.db.iterdump())==before, 'Stale review is atomic')
            annotation=copy.deepcopy(row['annotation'])
            for item in annotation['judgments']: item['document']=ref(current_docs[item['document']['id']])
            draft=save(w,row,annotation,review='draft'); reopened=w.get(row['id'])
            require(encoded(draft)==encoded(reopened) and reopened['review']=='draft', 'Deliberate draft refresh Save/reopen')
            reviewed.append(save(w,reopened,reopened['annotation']))
        local=docs+reviewed; second_raw,preview=freeze(dataset,local)
        require(all(preview['assignments'][r['id']]==r['source_split'] for r in local), 'Fixed imported family assignments')
        (output/'second-owner-release.zip').write_bytes(second_raw)
        (output/'second-owner-initial-drafts.json').write_text(json.dumps(initial,indent=2,ensure_ascii=False)+'\n')
        (output/'second-owner-reviewed-records.json').write_text(json.dumps(local,indent=2,ensure_ascii=False)+'\n')
        verified=verify(second_raw,output/'second-reader',local)
        require(verified['explicit_state_counts']==checked['explicit_state_counts'], 'All imported explicit states retained')
        return dict(status='PASS',id_map=mapped,initial_drafts=len(initial),separate_document_reviews=len(docs),
            stale_query_refusals=stale_refusals,explicit_refreshed_query_reviews=len(reviewed),fixed_family_splits=True,
            second_release=verified,rights='unknown; sender-local approval not transferred')
    finally:dataset.close()


def atomic_controls(raw,cases,output):
    from app import Dataset
    from workbench import WorkbenchError
    from retrieval_binary import import_release
    import sqlite3
    dataset=Dataset(output/'owner-atomic-controls')
    try:
        w=dataset.workbench; before=tuple(dataset.db.iterdump()); refused=[]
        for label,bad in cases.items():
            try:import_release(w,dict(archive=base64.b64encode(bad).decode(),sha256=sha(bad)))
            except WorkbenchError:pass
            else:raise AssertionError('Malformed owner packet admitted: '+label)
            require(tuple(dataset.db.iterdump())==before,'Malformed whole-owner rollback: '+label);refused.append(label)
        request=dict(archive=base64.b64encode(raw).decode(),sha256=sha(raw))
        try:import_release(w,dict(request,sha256='0'*64))
        except WorkbenchError:refused.append('wrong_complete_bundle_hash')
        else:raise AssertionError('Bad complete bundle hash admitted')
        require(tuple(dataset.db.iterdump())==before,'Bad complete hash is atomic')
        for table in ('workbench_records','retrieval_binary_sources','workbench_history'):
            dataset.db.execute('CREATE TRIGGER fail_binary BEFORE INSERT ON '+table+" BEGIN SELECT RAISE(ABORT,'controlled binary failure'); END");dataset.db.commit()
            trigger_before=tuple(dataset.db.iterdump())
            try:import_release(w,request)
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('Controlled publication failure absent: '+table)
            require(tuple(dataset.db.iterdump())==trigger_before,'Whole publication/binding/history rollback: '+table)
            dataset.db.execute('DROP TRIGGER fail_binary');dataset.db.commit();refused.append('atomic_failure_'+table)
        import_release(w,request);duplicate_before=tuple(dataset.db.iterdump())
        try:import_release(w,request)
        except WorkbenchError:pass
        else:raise AssertionError('Duplicate owner source accepted')
        require(tuple(dataset.db.iterdump())==duplicate_before,'Duplicate import whole rollback');refused.append('duplicate_source_import')
        return refused
    finally:dataset.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--archive',type=Path);parser.add_argument('--expected',type=Path)
    args=parser.parse_args();output=output_preflight(args.output)
    for p in ('report.json','retrieval-binary-release.zip','expected-records.json','external-reader-qrels.txt'):
        require(not (output/p).exists() and not (output/p).is_symlink(),'Fresh QA output required')
    sys.path[:0]=[str(ROOT),str(FIXTURES)]
    expected=decode(capture(args.expected,MAX_LOGICAL)) if args.expected else None
    if args.archive:
        raw=capture(args.archive,MAX_PHYSICAL)
        result=verify(raw,output,expected)
    else:
        from app import Dataset
        from retrieval_binary_fixture import populate,freeze
        dataset=Dataset(output/'owner-first')
        try:
            rows,bridge,original_hashes=populate(dataset);raw,preview=freeze(dataset,rows)
            require(all(r['source_sha256']==original_hashes[r['id']] for r in rows),'Authored original-source hashes')
        finally:dataset.close()
        (output/'retrieval-binary-release.zip').write_bytes(raw)
        (output/'expected-records.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n')
        checked=inspect_archive(raw,rows);result=verify(raw,output,rows)
        require((result['documents'],result['queries'],result['judgments'],result['families'],result['context_snapshots'])==(5,3,6,2,9)
            and result['explicit_state_counts']==dict(relevant=1,not_relevant=2,unjudged=3),'Exact authored fixture state/association counts')
        require(bridge['id'] not in {r['id'] for r in rows} and any(bridge['id'] in f['member_ids'] for f in preview['lineage']),'Unselected draft family bridge')
        omitted={(q['id'],d['id']) for q in rows if q['annotation']['role']=='query' for d in rows if d['annotation']['role']=='document'}
        omitted-={(v['query_id'],v['doc_id']) for v in result['actual_qrels']}
        require(len(omitted)==9,'Omitted relationships not emitted as negatives')
        cases=malformed_oracles(raw);result['malformed_oracles']=list(cases)
        result['atomic_import_controls']=atomic_controls(raw,cases,output)
        (output/'second-reader').mkdir()
        result['second_owner']=second_owner(raw,checked,output)
        require((output/'retrieval-binary-release.zip').read_bytes()==raw,'Original frozen release immutable')
        result.update(authored_fixture=True,original_source_hashes=True,zero_positive_and_all_unjudged_queries=True,
            omitted_relationship_count=len(omitted),unselected_draft_bridge_id=bridge['id'],cartesian_relationships_emitted=False)
    (output/'report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(status='passed',documents=result['documents'],queries=result['queries'],judgments=result['judgments'],
        explicit_state_counts=result['explicit_state_counts'],malformed_oracles=len(result.get('malformed_oracles',[])),training_executed=False)))


if __name__=='__main__':main()
