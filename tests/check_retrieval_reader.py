"""Bounded positive-only serialized oracle and unchanged published reader; no fitting."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import locale
import math
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import unicodedata
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
MAX_LOGICAL = 40 * 1024 * 1024
MAX_PHYSICAL = 48 * 1024 * 1024
STREAMS = ('corpus.jsonl', 'queries.jsonl', 'train_pairs.jsonl')
SPLITS = ('train', 'validation', 'test')
ID = re.compile(r'[a-f0-9]{32}')
HASH = re.compile(r'[a-f0-9]{64}')
SCOPE = dict(kind='human_positive_only', listed_relationships='explicit reviewed positives',
    unlisted_relationships='unjudged', negative_judgments_supported=False,
    empty_positive_sets_supported=False, declared_import_refs='unreviewed source claims',
    consumer_execution='JSONL reading and pure formatting/hash helpers only')
SNAPSHOT_KEYS = {'id', 'kind', 'revision', 'source_revision', 'content_hash', 'pixel_hash',
    'groups', 'parents', 'source_available', 'source_lineage_known', 'source_split',
    'source_sha256', 'book_id', 'session_id'}
RECORD_KEYS = SNAPSHOT_KEYS | {'name', 'text', 'task', 'annotation', 'review', 'created_at',
    'updated_at', 'provenance', 'width', 'height', 'corner_annotation'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode(raw):
    """Strict UTF-8, finite, unique-key, bounded-depth JSON before permissive parsing."""
    require(type(raw) is bytes and len(raw) <= MAX_LOGICAL, 'JSON byte bound')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON constant ' + value)
    try:
        result = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs, parse_constant=invalid)
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= 64, 'JSON nesting bound')
            if type(value) is float:
                require(math.isfinite(value), 'Nonfinite JSON number')
            elif type(value) is dict:
                pending.extend((item, depth + 1) for item in value.values())
            elif type(value) is list:
                pending.extend((item, depth + 1) for item in value)
            elif type(value) is str:
                value.encode('utf-8', errors='strict')
        return result
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as error:
        raise ValueError('Malformed bounded JSON') from error


def capture(path, maximum):
    with path.open('rb') as handle:
        raw = handle.read(maximum + 1)
    require(0 < len(raw) <= maximum, 'Captured file byte bound')
    return raw


def zip_payloads(raw):
    """EOCD/count/central-size fences before ZipFile constructs its entry list."""
    require(22 <= len(raw) <= MAX_PHYSICAL, 'ZIP physical byte bound')
    require(raw[-22:-18] == b'PK\x05\x06', 'ZIP must have exact comment-free EOCD')
    _, disk, central_disk, disk_count, count, central_size, offset, comment = struct.unpack('<4s4H2IH', raw[-22:])
    require(disk == central_disk == comment == 0 and disk_count == count and 5 < count <= 5005,
        'ZIP single-disk bounded entry count')
    require(offset + central_size == len(raw) - 22, 'ZIP central directory custody')
    cursor = offset
    for _ in range(count):
        require(cursor + 46 <= offset + central_size and raw[cursor:cursor + 4] == b'PK\x01\x02', 'ZIP central record')
        name, extra, note = struct.unpack_from('<3H', raw, cursor + 28)
        require(0 < name <= 256 and extra == note == 0, 'ZIP name/extra bounds; no ZIP64')
        cursor += 46 + name
    require(cursor == offset + central_size, 'ZIP exact central count')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as packet:
            infos = packet.infolist(); names = [i.filename for i in infos]
            require(len(infos) == count and len(set(names)) == count, 'Duplicate ZIP member')
            require(sum(i.file_size for i in infos) <= MAX_LOGICAL, 'Complete logical ZIP bound')
            payloads = {}
            for item in infos:
                require(item.compress_type == zipfile.ZIP_STORED and not item.flag_bits & 1,
                    'Only unencrypted stored ZIP members')
                require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG) and not item.external_attr & 0x10,
                    'Only regular ZIP files')
                require(not item.is_dir() and not item.filename.startswith('/') and '\\' not in item.filename
                    and all(p not in ('', '.', '..') for p in item.filename.split('/')), 'Unsafe ZIP path')
                payloads[item.filename] = packet.read(item)
            return payloads
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as error:
        raise ValueError('Invalid ZIP payload or CRC') from error


def positive_integer(value, name):
    require(type(value) is int and 1 <= value <= 2**63 - 1, name + ' exact bounded integer')


def string_list(value, name, identifiers=False):
    require(type(value) is list and len(value) <= 5000
        and all(type(v) is str and v and len(v) <= 120 and (not identifiers or ID.fullmatch(v)) for v in value), name + ' bounded strings')
    require(len(value) == len(set(value)), name + ' unique list')


def inspect_archive(raw, expected_records=None):
    """Independent native record/source graph and serialized relation association."""
    payloads = zip_payloads(raw)
    require('manifest.json' in payloads, 'Missing manifest')
    manifest = decode(payloads['manifest.json'])
    require(type(manifest) is dict and set(manifest) == {'schema_version', 'format', 'consumer', 'judgment_scope',
        'seed', 'records', 'protected_components', 'lineage', 'assignments', 'split_report', 'retrieval_counts',
        'files', 'warnings', 'assets', 'limits'}, 'Closed retrieval manifest')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1
        and manifest['format'] == 'text_retrieval_v1', 'Retrieval format/version')
    require(encoded(manifest['judgment_scope']) == encoded(SCOPE), 'Positive-only unjudged contract')
    require(manifest['limits'] == dict(selected_records=5000, positive_refs_per_query=30,
        logical_archive_bytes=MAX_LOGICAL), 'Native limits')
    require(type(manifest['seed']) is int and 0 <= manifest['seed'] <= 2**32 - 1, 'Seed')
    consumer = manifest['consumer']
    pins = decode((FIXTURES / 'retrieval_consumer/pins.json').read_bytes())
    require(type(consumer) is dict and set(consumer) == {'repository', 'commit', 'companion_sha256', 'path',
        'sha256', 'helper_sha256', 'neural_trainer_source_sha256', 'reader_path', 'contract_path',
        'contract_sha256', 'qualification'} and consumer['commit'] == pins['commit']
        and consumer['repository'] == pins['repository'] and consumer['companion_sha256'] == pins['companion_sha256'], 'Consumer pin')
    require(consumer['helper_sha256'] == pins['files']['retrieval_common.py']
        and consumer['contract_sha256'] == pins['files']['embedding_contract.py']
        and consumer['path'] == 'examples/embeddings/lexical_baseline.py'
        and consumer['sha256'] == pins['files']['lexical_baseline.py']
        and consumer['neural_trainer_source_sha256'] == pins['originating_neural_source_sha256']
        and consumer['reader_path'] == 'examples/embeddings/retrieval_common.py'
        and consumer['contract_path'] == 'examples/embeddings/embedding_contract.py', 'Executed reader/helper pins')
    require(consumer['qualification'] == 'unchanged read_jsonl and pure format_query/sha256_file only; no fitting, ranking, metrics, model loading or training', 'Reader-only qualification')
    rows = manifest['records']
    require(type(rows) is list and 1 <= len(rows) <= 5000, 'Selected record bound')
    ids = [row['id'] for row in rows]
    require(len(set(ids)) == len(ids) and ids == sorted(ids), 'Unique sorted record IDs')
    require(set(payloads) == {'manifest.json', 'README.txt', *STREAMS} | {'assets/' + i + '.txt' for i in ids}, 'Exact archive file closure')
    require(type(manifest['assets']) is dict and set(manifest['assets']) == set(ids), 'Exact asset membership')
    if expected_records is not None:
        require(type(expected_records) is list and len(expected_records) == len(rows), 'Expected record membership')
        expected = {row['id']: row for row in expected_records}
        require(len(expected) == len(rows) and set(expected) == set(ids), 'Expected IDs')
        for row in rows:
            require(encoded(row) == encoded(expected[row['id']]), 'Exact revision/source/provenance/target snapshot')
    documents, queries = {}, []
    for row in rows:
        require(type(row) is dict and set(row) in (RECORD_KEYS, RECORD_KEYS | {'target_proposal'}), 'Closed native record')
        require(type(row['id']) is str and ID.fullmatch(row['id']), 'Record ID')
        positive_integer(row['revision'], 'Revision')
        require(type(row['source_revision']) is int and row['source_revision'] == 1, 'Immutable text source revision')
        require(row['kind'] == 'text' and row['task'] == 'text_retrieval' and row['review'] == 'human_reviewed'
            and row['source_available'] is True and row['source_lineage_known'] is True, 'Reviewed available retrieval source')
        require(row['source_split'] == 'unassigned' and all(row[k] is None for k in ('pixel_hash', 'book_id', 'session_id', 'width', 'height')), 'Text source identity')
        require(type(row['text']) is str and 0 < len(row['text']) <= 200000 and row['text'].strip()
            and unicodedata.normalize('NFC', row['text']) == row['text'] and '\r' not in row['text'], 'Canonical source text')
        require(type(row['source_sha256']) is str and HASH.fullmatch(row['source_sha256'])
            and type(row['provenance']) is dict and row['provenance'].get('normalization') == 'NFC; LF newlines', 'Original source/hash provenance')
        asset_name = 'assets/' + row['id'] + '.txt'; asset = payloads[asset_name]
        require(asset == row['text'].encode('utf-8') and sha(asset) == row['content_hash'], 'Exact canonical asset bytes/hash')
        require(manifest['assets'][row['id']] == dict(path=asset_name, sha256=sha(asset)), 'Asset manifest association')
        string_list(row['groups'], 'Groups'); string_list(row['parents'], 'Parents', True)
        require(row['groups'], 'Protected groups required')
        a = row['annotation']; require(type(a) is dict and a.get('role') in ('document', 'query'), 'Retrieval role')
        require(type(a.get('note')) is str and 0 < len(a['note']) <= 4000 and a['note'] == a['note'].strip(), 'Canonical review note')
        require(set(a) == ({'role', 'note'} if a['role'] == 'document' else {'role', 'note', 'positive_refs'}), 'Closed positive-only annotation')
        if a['role'] == 'document': documents[row['id']] = row
        else:
            refs = a['positive_refs']; require(type(refs) is list and 1 <= len(refs) <= 30, 'Positive ref count')
            seen = set()
            for ref in refs:
                require(type(ref) is dict and set(ref) == {'id', 'revision', 'source_revision'}, 'Closed positive ref')
                require(type(ref['id']) is str and ID.fullmatch(ref['id']) and ref['id'] not in seen
                    and ref['id'] in row['parents'], 'Unique immutable positive parent')
                for k in ('revision', 'source_revision'): positive_integer(ref[k], 'Positive ' + k)
                seen.add(ref['id'])
            queries.append(row)
    assignments = manifest['assignments']
    require(type(assignments) is dict and set(assignments) == set(ids) and all(v in SPLITS for v in assignments.values()), 'Exact selected assignments')
    # Rebuild the known full snapshot graph independently, including unselected bridges.
    snapshots = manifest['protected_components']; require(type(snapshots) is dict and 1 <= len(snapshots) <= 5000, 'Family proof')
    require(sum(len(m) for m in snapshots.values() if type(m) is list) <= 50000, 'Complete known snapshot count bound')
    parent = {}; snapshot_by_id = {}; family_by_id = {}
    def root(key):
        parent.setdefault(key, key)
        while key != parent[key]:
            parent[key] = parent[parent[key]]; key = parent[key]
        return key
    def join(a, b): parent[root(b)] = root(a)
    for family, members in snapshots.items():
        require(type(family) is str and family.startswith('component:') and HASH.fullmatch(family[10:]), 'Family identity')
        require(type(members) is list and 1 <= len(members) <= 5000, 'Bounded family members')
        mids = [s['id'] for s in members]
        require(mids == sorted(mids) and len(set(mids)) == len(mids)
            and family == 'component:' + sha(encoded(mids).encode()), 'Exact family membership hash')
        for s in members:
            require(type(s) is dict and set(s) == SNAPSHOT_KEYS and type(s['id']) is str and ID.fullmatch(s['id']), 'Closed family snapshot')
            require(s['id'] not in snapshot_by_id and s['kind'] in ('text', 'image', 'sequence', 'mesh', 'pointcloud'), 'Unique source snapshot')
            positive_integer(s['revision'], 'Snapshot revision')
            require(type(s['source_available']) is bool and s['source_lineage_known'] is True, 'Typed known source availability')
            require(s['source_split'] in ('unassigned', *SPLITS), 'Known source split')
            string_list(s['groups'], 'Snapshot groups'); string_list(s['parents'], 'Snapshot parents', True)
            if s['kind'] == 'text':
                require(s['source_available'] is True and s['source_lineage_known'] is True
                    and type(s['source_revision']) is int and s['source_revision'] == 1 and s['source_split'] == 'unassigned'
                    and s['pixel_hash'] is s['book_id'] is s['session_id'] is None
                    and type(s['source_sha256']) is str and HASH.fullmatch(s['source_sha256']), 'Text snapshot source identity')
            elif s['kind'] in ('sequence', 'mesh', 'pointcloud'):
                require(s['source_available'] is True and type(s['source_revision']) is int and s['source_revision'] == 1
                    and (s['kind'] == 'pointcloud' or s['source_split'] == 'unassigned') and s['source_sha256'] == s['content_hash']
                    and HASH.fullmatch(s['content_hash']) and s['pixel_hash'] is s['book_id'] is s['session_id'] is None,
                    'Immutable native snapshot source identity')
            elif s['source_available']:
                positive_integer(s['source_revision'], 'Image snapshot source revision')
                require(type(s['source_sha256']) is str and HASH.fullmatch(s['source_sha256']), 'Available image raw hash')
            else:
                require(s['source_revision'] is s['source_sha256'] is None, 'Deleted image source identity')
            require(type(s['content_hash']) is str and (not s['content_hash'] or HASH.fullmatch(s['content_hash'])), 'Snapshot content hash')
            require(s['pixel_hash'] is None or type(s['pixel_hash']) is str and (not s['pixel_hash'] or HASH.fullmatch(s['pixel_hash'])), 'Snapshot pixel hash')
            snapshot_by_id[s['id']] = s; family_by_id[s['id']] = family
            key = 'id:' + s['id']; root(key)
            links = ['group:' + g for g in s['groups']] + ['id:' + p for p in s['parents']]
            if s['content_hash']: links.append('content:' + s['kind'] + ':' + s['content_hash'])
            if s['pixel_hash']: links.append('pixels:' + s['pixel_hash'])
            if s['kind'] == 'image' and s['source_lineage_known']:
                require(type(s['book_id']) is str and type(s['session_id']) is str, 'Image retained lineage')
                links.append('legacy:' + ('book:' + s['book_id'] if s['book_id'] else 'session:' + s['session_id']))
            for link in links: join(key, link)
    require(set(ids) <= set(snapshot_by_id), 'Every selected record has family proof')
    graph_families = {}
    for ident in snapshot_by_id: graph_families.setdefault(root('id:' + ident), set()).add(family_by_id[ident])
    require(all(len(f) == 1 for f in graph_families.values()) and len(graph_families) == len(snapshots), 'Known graph closure and connected families')
    expected_lineage = []
    for family, members in snapshots.items():
        selected = [s['id'] for s in members if s['id'] in assignments]
        require(selected and len({assignments[i] for i in selected}) == 1, 'Family indivisible split')
        fixed = sorted({s['source_split'] for s in members if s['source_split'] in SPLITS})
        require(len(fixed) <= 1 and (not fixed or fixed[0] == assignments[selected[0]]), 'Retained fixed family split')
        expected_lineage.append(dict(id=family, selected_ids=selected, member_ids=[s['id'] for s in members],
            deleted_ids=[s['id'] for s in members if not s['source_available']], fixed_splits=fixed))
    require(manifest['lineage'] == sorted(expected_lineage, key=lambda f: f['id']), 'Exact lineage report')
    for row in rows:
        require(encoded({k: row[k] for k in SNAPSHOT_KEYS}) == encoded(snapshot_by_id[row['id']]), 'Selected source snapshot equality')
    expected_streams = {name: [] for name in STREAMS}; referenced = set(); anchors = set(); train_ids = set()
    for row in rows:
        split = 'val' if assignments[row['id']] == 'validation' else assignments[row['id']]
        group = family_by_id[row['id']]
        if row['annotation']['role'] == 'document':
            expected_streams['corpus.jsonl'].append(dict(doc_id=row['id'], text=row['text'], group=group, split=split))
        else:
            anchor = row['text'].strip(); require(anchor not in anchors, 'Distinct formatted query anchors'); anchors.add(anchor)
            refs = row['annotation']['positive_refs']
            for ref in refs:
                require(ref['id'] in documents, 'Every positive explicitly selected as document')
                doc = documents[ref['id']]
                require(all(type(ref[k]) is int and ref[k] == doc[k] for k in ('revision', 'source_revision')), 'Positive current exact revisions')
                require(assignments[doc['id']] == assignments[row['id']] and family_by_id[doc['id']] == group, 'Positive family/split association')
                referenced.add(doc['id'])
            expected_streams['queries.jsonl'].append(dict(query_id=row['id'], text=row['text'],
                relevant_doc_ids=[r['id'] for r in refs], split=split))
            if split == 'train':
                require(len(refs) == 1, 'No dropped training positives'); doc = documents[refs[0]['id']]; train_ids.add(doc['id'])
                expected_streams['train_pairs.jsonl'].append(dict(query=row['text'], positive=doc['text'], doc_id=doc['id'], group=group))
    require(len(train_ids) >= 2 and len({documents[i]['text'] for i in train_ids}) == len(train_ids), 'Distinct train positives')
    counts = {}
    for split in SPLITS:
        ds = [r for r in documents.values() if assignments[r['id']] == split]; qs = [q for q in queries if assignments[q['id']] == split]
        require(ds and qs, 'All three splits contain documents and queries')
        counts[split] = dict(documents=len(ds), queries=len(qs), emitted_pairs=len(qs) if split == 'train' else 0,
            distinct_positive_documents=len({r['id'] for q in qs for r in q['annotation']['positive_refs']}),
            families=len({family_by_id[r['id']] for r in ds + qs}))
    require(encoded(manifest['retrieval_counts']) == encoded(counts), 'Exact typed split counts')
    require(type(manifest['split_report']['independent_components']) is int
        and manifest['split_report']['independent_components'] == len(snapshots)
        and encoded(manifest['split_report']['actual_counts']) == encoded({s: sum(v == s for v in assignments.values()) for s in SPLITS}), 'Split report association')
    require(type(manifest['files']) is dict and set(manifest['files']) == set(STREAMS), 'Stream hash membership')
    for name in STREAMS:
        raw_stream = payloads[name]
        require(raw_stream.endswith(b'\n') and b'\r' not in raw_stream, 'Nonblank LF JSONL')
        lines = raw_stream.splitlines(); require(all(line for line in lines), 'No blank serialized rows')
        parsed = [decode(line) for line in lines]
        require(encoded(parsed) == encoded(expected_streams[name]), 'Exact closed serialized positive projection: ' + name)
        require(manifest['files'][name] == dict(bytes=len(raw_stream), sha256=sha(raw_stream)), 'Exact stream hash: ' + name)
    require(b'UNJUDGED' in payloads['README.txt'] and b'not negatives' in payloads['README.txt'], 'Frozen positive-only warning')
    require(type(manifest['warnings']) is list and any('UNJUDGED' in w for w in manifest['warnings']), 'Preview/manifest positive-only warning')
    return dict(manifest=manifest, payloads=payloads, streams=expected_streams, counts=counts,
        unjudged_document_ids=sorted(set(documents) - referenced), selected_pairs=[{k: r[k] for k in ('id', 'revision', 'source_revision')} for r in rows],
        family_members=len(snapshot_by_id), families=len(snapshots))


def load_published(name, pins):
    path = FIXTURES / 'retrieval_consumer' / name
    require(sha(path.read_bytes()) == pins['files'][name], 'Exact published helper source')
    spec = importlib.util.spec_from_file_location('_published_retrieval_' + path.stem, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def verify(raw, output, expected_records=None):
    checked = inspect_archive(raw, expected_records)
    pins = decode((FIXTURES / 'retrieval_consumer/pins.json').read_bytes())
    require(all(sha((FIXTURES / 'retrieval_consumer' / name).read_bytes()) == digest
        for name, digest in pins['files'].items()), 'All retained source-only and executed helper bytes')
    before_modules = set(sys.modules)
    common = load_published('retrieval_common.py', pins)
    contract = load_published('embedding_contract.py', pins)
    def forbidden(*args, **kwargs):
        raise AssertionError('Fitting, model inspection or metrics are outside reader qualification')
    common.retrieval_metrics = forbidden; contract.model_fingerprint = forbidden
    with tempfile.TemporaryDirectory(prefix='published-jsonl-', dir=output) as tmp:
        for name in STREAMS:
            path = Path(tmp) / name; path.write_bytes(checked['payloads'][name])
            require(encoded(common.read_jsonl(path)) == encoded(checked['streams'][name]), 'Actual published JSONL reader equality')
            require(contract.sha256_file(path) == sha(checked['payloads'][name]), 'Actual published hash helper')
        for row in checked['streams']['queries.jsonl']:
            require(contract.format_query(row['text']) == 'Instruct: ' + contract.DEFAULT_INSTRUCTION.strip()
                + '\nQuery:' + row['text'].strip(), 'Actual pure formatter; export text stays raw')
    banned = ('sklearn', 'sentence_transformers', 'transformers', 'torch', 'lexical_baseline')
    require(not any(name.split('.')[0] in banned for name in set(sys.modules) - before_modules), 'No fitting/model/neural imports')
    return dict(status='passed', result='PASS', archive=dict(bytes=len(raw), sha256=sha(raw)),
        counts=checked['counts'], documents=len(checked['streams']['corpus.jsonl']), queries=len(checked['streams']['queries.jsonl']),
        train_pairs=len(checked['streams']['train_pairs.jsonl']), selected_pairs=checked['selected_pairs'],
        unjudged_document_ids=checked['unjudged_document_ids'], family_members=checked['family_members'], families=checked['families'],
        judgment_scope=SCOPE, exact_source_target_and_family_oracle=True, actual_published_read_jsonl=True,
        source_pins=pins, executed_module_hashes={name: sha((FIXTURES / 'retrieval_consumer' / name).read_bytes())
            for name in ('retrieval_common.py', 'embedding_contract.py')},
        environment=dict(python=sys.version.split()[0], numpy=importlib.metadata.version('numpy'),
            published_reader_default_encoding=locale.getpreferredencoding(False)),
        files={name: dict(bytes=len(value), sha256=sha(value)) for name, value in checked['payloads'].items()},
        fitting_executed=False, ranking_executed=False, metrics_executed=False, training_executed=False,
        model_loading=False, downloads=False, negatives_inferred=False,
        forbidden_function_and_import_guards=True,
        oracle_limits=dict(physical_archive_bytes=MAX_PHYSICAL, complete_logical_bytes=MAX_LOGICAL,
            selected_records=5000, zip_members=5005, known_source_snapshots=50000, json_depth=64),
        review_basis='Automated authored compatibility controls; no actual human benchmark or semantic independence claim.')


def archive_from(payloads, duplicate=None, symlink=None):
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as packet:
        for name, raw in payloads.items():
            info = zipfile.ZipInfo(name)
            if name == symlink: info.external_attr = (stat.S_IFLNK | 0o777) << 16
            packet.writestr(info, raw)
        if duplicate:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='Duplicate name:', category=UserWarning)
                packet.writestr(duplicate, payloads[duplicate])
    return target.getvalue()


def malformed_oracles(raw, expected):
    base = zip_payloads(raw); cases = {}
    def changed(name, mutate):
        payloads = dict(base); value = decode(payloads[name]); mutate(value)
        payloads[name] = encoded(value).encode(); return archive_from(payloads)
    cases['asset_hash'] = changed('manifest.json', lambda m: m['assets'][m['records'][0]['id']].update(sha256='0' * 64))
    cases['source_revision_bool'] = changed('manifest.json', lambda m: m['records'][0].update(source_revision=True))
    cases['target_ref_revision_bool'] = changed('manifest.json', lambda m: next(r for r in m['records'] if r['annotation']['role'] == 'query')['annotation']['positive_refs'][0].update(revision=True))
    cases['negative_scope'] = changed('manifest.json', lambda m: m['judgment_scope'].update(unlisted_relationships='negative'))
    cases['boolean_count'] = changed('manifest.json', lambda m: m['retrieval_counts']['train'].update(families=True))
    cases['missing_family_proof'] = changed('manifest.json', lambda m: m.update(protected_components={}))
    def cross(m):
        q = next(r for r in m['records'] if r['annotation']['role'] == 'query'); old = m['assignments'][q['id']]
        m['assignments'][q['id']] = next(s for s in SPLITS if s != old)
    cases['family_cross_split'] = changed('manifest.json', cross)
    cases['forged_annotation_negative'] = changed('manifest.json', lambda m: next(r for r in m['records'] if r['annotation']['role'] == 'query')['annotation'].update(negative_refs=[]))
    cases['selected_source_mutation'] = changed('manifest.json', lambda m: m['records'][0]['provenance'].update(rights='Forged'))
    cases['duplicate_zip_member'] = archive_from(base, duplicate='corpus.jsonl')
    cases['symlink_member'] = archive_from(base, symlink='corpus.jsonl')
    for label, line in [('unknown_ref', {'query_id': '0' * 32, 'text': 'query', 'relevant_doc_ids': ['f' * 32], 'split': 'train'}),
                        ('extra_negative_field', {'query_id': '0' * 32, 'text': 'query', 'relevant_doc_ids': ['f' * 32], 'split': 'train', 'negative_doc_ids': []})]:
        payloads = dict(base); payloads['queries.jsonl'] = encoded(line).encode() + b'\n'; cases[label] = archive_from(payloads)
    for label, value in [('nonfinite_constant', b'{"score":NaN}\n'), ('nonfinite_overflow', b'{"score":1e400}\n'),
                          ('duplicate_json_key', b'{"doc_id":"a","doc_id":"b"}\n'), ('invalid_utf8', b'{"text":"\xff"}\n')]:
        payloads = dict(base); payloads['corpus.jsonl'] = value; cases[label] = archive_from(payloads)
    cases['bad_stream_hash'] = changed('manifest.json', lambda m: m['files']['queries.jsonl'].update(sha256='0' * 64))
    # Schema/finite cases get an internally updated hash so refusal is not merely checksum failure.
    for label in ('unknown_ref', 'extra_negative_field', 'nonfinite_constant', 'nonfinite_overflow', 'duplicate_json_key', 'invalid_utf8'):
        payloads = zip_payloads(cases[label]); m = decode(payloads['manifest.json'])
        for name in STREAMS: m['files'][name] = dict(bytes=len(payloads[name]), sha256=sha(payloads[name]))
        payloads['manifest.json'] = encoded(m).encode(); cases[label] = archive_from(payloads)
    passed = []
    for label, malformed in cases.items():
        try: inspect_archive(malformed, expected if label == 'selected_source_mutation' else None)
        except (ValueError, KeyError, TypeError): passed.append(label)
        else: raise AssertionError('Malformed oracle unexpectedly admitted: ' + label)
    # Reject before ZipFile list construction even when declared entry count is forged.
    forged = bytearray(raw); struct.pack_into('<HH', forged, len(raw) - 22 + 8, 65535, 65535)
    try: inspect_archive(bytes(forged))
    except ValueError: passed.append('declared_zip_count_bound')
    else: raise AssertionError('Unbounded central entry count admitted')
    return passed


def output_preflight(path):
    output = path.resolve(); relative = None
    try: relative = output.relative_to(ROOT.resolve())
    except ValueError: pass
    require(relative is None or relative.parts and relative.parts[0] in ('build', 'output'),
        'QA output must be outside source or inside ignored build/output')
    output.mkdir(parents=True, exist_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path); parser.add_argument('--expected', type=Path)
    args = parser.parse_args(); output = output_preflight(args.output)
    output_files = [output / name for name in ('report.json', 'retrieval-release.zip', 'expected-records.json')]
    require(all(not path.is_symlink() for path in output_files), 'Output file cannot be a symlink')
    for path in (args.archive, args.expected):
        if path is not None:
            require(path.resolve() not in set(output_files)
                and not any(target.exists() and target.samefile(path) for target in output_files), 'Input cannot alias an output file')
    expected = decode(capture(args.expected, MAX_LOGICAL)) if args.expected else None
    if args.archive:
        raw = capture(args.archive, MAX_PHYSICAL); result = verify(raw, output, expected)
    else:
        sys.path[:0] = [str(ROOT), str(FIXTURES)]
        from app import Dataset
        from retrieval_fixture import populate, freeze
        with tempfile.TemporaryDirectory(prefix='retrieval-reader-', dir=output) as tmp:
            dataset = Dataset(Path(tmp) / 'data')
            try:
                rows, draft, original_hashes = populate(dataset)
                raw, preview = freeze(dataset, rows)
                # Keep evaluated positive count >1 in one nontrain query; parents were declared.
                query = next(r for r in rows if r['annotation']['role'] == 'query' and preview['assignments'][r['id']] != 'train')
                docs = [r for r in rows if r['id'] in query['parents']]
                annotation = dict(query['annotation'], positive_refs=[{k: r[k] for k in ('id', 'revision', 'source_revision')} for r in docs])
                updated = dataset.workbench.save(query['id'], dict(query, annotation=annotation, review='human_reviewed'))
                rows = [updated if r['id'] == updated['id'] else r for r in rows]
                raw, preview = freeze(dataset, rows)
                require(all(row['source_sha256'] == original_hashes[row['id']] for row in rows), 'Actual original import bytes retained')
            finally: dataset.close()
            (output / 'retrieval-release.zip').write_bytes(raw)
            (output / 'expected-records.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
            result = verify(raw, output, rows)
            require(result['documents'] == 7 and result['queries'] == 6 and result['train_pairs'] == 2
                and len(result['unjudged_document_ids']) == 1 and result['family_members'] == 14, 'Authored fixture association')
            require(draft['id'] not in {r['id'] for r in rows} and any(draft['id'] in f['member_ids'] for f in preview['lineage']), 'Unselected draft bridge retained')
            result['unselected_draft_id'] = draft['id']; result['malformed_oracles'] = malformed_oracles(raw, rows)
            result['original_source_hashes_verified_from_authored_raw_texts'] = True
            result['evaluation_multi_positive_retained'] = True
    (output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(status='passed', documents=result['documents'], queries=result['queries'],
        train_pairs=result['train_pairs'], malformed_oracles=len(result.get('malformed_oracles', [])), training_executed=False)))


if __name__ == '__main__':
    main()
