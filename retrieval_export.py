"""Reviewed relevance references and exact published retrieval JSONL projection."""
import hashlib
from workbench import WorkbenchError, IDENTIFIER, MAX_SELECTED_TEXT_BYTES, encode, text_value, rights_note, analyze

FORMAT = 'text_retrieval_v1'
MAX_REQUEST = 1024 * 1024
STREAM_FILES = ('corpus.jsonl', 'queries.jsonl', 'train_pairs.jsonl')
CONSUMER = {'repository': 'bc-ai-ecosystem/training-your-own-models',
    'commit': 'fb895e1a3e08fac86738106e6122bdcafb124e65',
    'companion_sha256': 'e924589b152f68bb15d89b8f95e3b52005bbe4a9f7770f2d0550b5422d3a11d6',
    'path': 'examples/embeddings/lexical_baseline.py',
    'sha256': 'ada8e0780f41f70332dda3563332103a16b09f865f5758f301d07068ee6c7a9d',
    'helper_sha256': '2c31d9dc1cfd3e79675e95191ca3af341047ff7b622a4d605b9867d24f526e46',
    'neural_trainer_source_sha256': 'a22e8a48fd7ce4aacbc311f7222f92706da219e579b542e7376de114cbbb4b22',
    'reader_path': 'examples/embeddings/retrieval_common.py',
    'contract_path': 'examples/embeddings/embedding_contract.py',
    'contract_sha256': 'c84d518d3dc392ab9cc5082e822cc68fee1bb52fefa49ff71d33b9a719a421ff',
    'qualification': 'unchanged read_jsonl and pure format_query/sha256_file only; no fitting, ranking, metrics, model loading or training'}
JUDGMENT_SCOPE = {'kind': 'human_positive_only', 'listed_relationships': 'explicit reviewed positives',
    'unlisted_relationships': 'unjudged', 'negative_judgments_supported': False,
    'empty_positive_sets_supported': False, 'declared_import_refs': 'unreviewed source claims',
    'consumer_execution': 'JSONL reading and pure formatting/hash helpers only'}
POSITIVE_ONLY_WARNING = 'Only listed, explicitly reviewed relationships are positive; every unlisted relationship is UNJUDGED, never an inferred negative.'
README = ('Tuldok reviewed retrieval v1. Exact canonical NFC/LF texts, without trimming or query instructions.\n'
    'corpus.jsonl contains the complete selected inference corpus, including held-out documents.\n'
    'queries.jsonl retains reviewed positives and train/val/test membership; train_pairs.jsonl uses train queries only.\n'
    'Train queries require one positive; evaluation may have multiple positives. No targets are dropped.\n'
    'Whole connected source families, including unselected/deleted bridges, are indivisible.\n'
    'Only listed relationships are reviewed positives. All omitted relationships are UNJUDGED, not negatives.\n'
    'Empty positive sets and explicit negative judgments are unsupported; imported declared refs grant no review.\n'
    'Qualification executes unchanged JSONL reading and pure formatting/hash helpers only: no fitting, ranking, metrics or training.\n'
    'Review and family grouping establish neither semantic independence nor permission or model quality.\n'
    'manifest.json retains exact revisions, relevance refs, provenance/rights, family proof and file hashes.\n').encode()


def references(value):
    if type(value) is not list or not 1 <= len(value) <= 30:
        raise WorkbenchError('Provide 1–30 exact positive document references.')
    seen = set()
    for ref in value:
        if type(ref) is not dict or set(ref) != {'id', 'revision', 'source_revision'}:
            raise WorkbenchError('Positive refs need exactly id, revision and source_revision.')
        if type(ref['id']) is not str or not IDENTIFIER.fullmatch(ref['id']) or ref['id'] in seen:
            raise WorkbenchError('Positive document IDs must be unique canonical record IDs.')
        if any(type(ref[k]) is not int or not 1 <= ref[k] <= 2**63-1 for k in ('revision','source_revision')):
            raise WorkbenchError('Positive revisions must be positive bounded integers.')
        seen.add(ref['id'])
    return [dict(ref) for ref in value]


def annotation(value, row):
    if type(value) is not dict or value.get('role') not in ('document','query'):
        raise WorkbenchError('Choose retrieval document or query role.')
    expected = {'role','note'} | ({'positive_refs'} if value['role'] == 'query' else set())
    if set(value) != expected:
        raise WorkbenchError('Retrieval annotation has unknown or missing fields.')
    result = {'role':value['role'], 'note':text_value(value['note'],'Retrieval review note',4000)}
    if value['role'] == 'query':
        result['positive_refs'] = references(value['positive_refs'])
        if any(ref['id'] not in row['parents'] for ref in result['positive_refs']):
            raise WorkbenchError('Every positive must be an existing immutable query parent; declare parents when importing the query.')
    return result


def check_positives(w, refs):
    for ref in references(refs):
        doc = w._get(ref['id'])
        if (doc['kind'] != 'text' or doc['task'] != 'text_retrieval' or doc['review'] != 'human_reviewed'
                or not doc['source_available'] or not doc['annotation'] or doc['annotation'].get('role') != 'document'):
            raise WorkbenchError('Positives must be available human-reviewed retrieval documents.')
        if any(ref[k] != doc[k] for k in ('revision','source_revision')):
            raise WorkbenchError('Positive document changed; inspect it and deliberately update the reference.', 'conflict',409)
        if encode(annotation(doc['annotation'],doc)) != encode(doc['annotation']):
            raise WorkbenchError('Stored document review is invalid.')


def import_query(w, body):
    if type(body) is not dict or set(body) != {'name','text','groups','rights','positive_refs'}:
        raise WorkbenchError('Supply raw query name, text, groups, rights and exact positive refs only.')
    refs = references(body['positive_refs'])
    with w.lock, w.db:
        check_positives(w,refs)
        return w.import_asset(dict(kind='text',name=body['name'],text=body['text'],groups=body['groups'],
            rights=body['rights'],parents=[r['id'] for r in refs]),
            acquisition={'format':'text_retrieval_query_v1','declared_positive_refs':refs})


def projection(prepared, filename):
    rows = prepared['rows']; assignments = prepared['preview']['assignments']
    docs = {r['id']:r for r in rows if r['annotation']['role'] == 'document'}
    family = lambda row: prepared['groups'][prepared['roots'][row['id']]]
    split = lambda row: 'val' if assignments[row['id']] == 'validation' else assignments[row['id']]
    for row in rows:
        a = row['annotation']
        if filename == 'corpus.jsonl' and a['role'] == 'document':
            yield {'doc_id':row['id'],'text':row['text'],'group':family(row),'split':split(row)}
        elif filename == 'queries.jsonl' and a['role'] == 'query':
            yield {'query_id':row['id'],'text':row['text'],'relevant_doc_ids':[r['id'] for r in a['positive_refs']], 'split':split(row)}
        elif filename == 'train_pairs.jsonl' and a['role'] == 'query' and split(row) == 'train':
            ref = a['positive_refs'][0]
            yield {'query':row['text'],'positive':docs[ref['id']]['text'],'doc_id':ref['id'],'group':family(row)}


def file_proofs(prepared):
    files = {}
    for filename in STREAM_FILES:
        digest = hashlib.sha256(); size = 0
        for row in projection(prepared, filename):
            raw = (encode(row)+'\n').encode(); digest.update(raw); size += len(raw)
            if size > MAX_SELECTED_TEXT_BYTES: raise WorkbenchError('Retrieval consumer file exceeds 40 MiB.')
        files[filename] = {'bytes':size,'sha256':digest.hexdigest()}
    return files


def entries(prepared, body):
    preview = prepared['preview']; rows = prepared['rows']
    manifest = {'schema_version':1,'format':FORMAT,'consumer':CONSUMER,'judgment_scope':JUDGMENT_SCOPE,'seed':body['seed'],
        'records':rows,'protected_components':prepared['snapshots'],'lineage':preview['lineage'],
        'assignments':preview['assignments'],'split_report':preview['split_report'],
        'retrieval_counts':preview['retrieval_counts'],'files':prepared['files'],'warnings':preview['warnings'],
        'assets':{r['id']:{'path':'assets/'+r['id']+'.txt','sha256':r['content_hash']} for r in rows},
        'limits':{'selected_records':5000,'positive_refs_per_query':30,'logical_archive_bytes':MAX_SELECTED_TEXT_BYTES}}
    yield 'manifest.json',encode(manifest).encode(),None
    for row in rows:
        yield 'assets/'+row['id']+'.txt',row['text'].encode(),row['content_hash']
    for filename in STREAM_FILES:
        yield filename,b'',None
        digest = hashlib.sha256(); size = 0
        for value in projection(prepared, filename):
            raw = (encode(value)+'\n').encode();digest.update(raw);size += len(raw)
            yield None,raw,None
        if prepared['files'][filename] != {'bytes':size,'sha256':digest.hexdigest()}:
            raise WorkbenchError('Retrieval projection changed.', 'conflict',409)
    yield 'README.txt',README,None


def prepare(releases, body):
    from dataset_releases import family_context, allocate
    w = releases.workbench
    preview = {'format':FORMAT,'eligible':False,'selected_count':0,'analysis':None,'blockers':[],
        'warnings':[POSITIVE_ONLY_WARNING],'judgment_scope':JUDGMENT_SCOPE,'lineage':[],'assignments':{},'split_report':None,'preview_token':None}
    try:
        if set(body) - {'format','items','ratios','seed','preview_token'}:
            raise WorkbenchError('Unknown retrieval release fields.')
        rows = sorted(w.selection(body.get('items'), max_snapshot_bytes=MAX_SELECTED_TEXT_BYTES),key=lambda r:r['id'])
        preview['selected_count'] = len(rows)
        preview['analysis'] = analyze(rows)
        for row in rows:
            if row['kind'] != 'text' or row['task'] != 'text_retrieval' or row['review'] != 'human_reviewed' or not row['source_available']:
                raise WorkbenchError('Select available human-reviewed retrieval documents and query judgments only.')
            if encode(annotation(row['annotation'],row)) != encode(row['annotation']):
                raise WorkbenchError('Stored retrieval target is invalid.')
            if hashlib.sha256(row['text'].encode()).hexdigest() != row['content_hash']:
                raise WorkbenchError('Retrieval source bytes changed.', 'conflict',409)
        universe = w._all(); roots,groups,snapshots,preview['lineage'] = family_context(rows,universe)
        assignments,report = allocate(rows,universe,body.get('ratios'),body.get('seed'))
        preview['assignments'],preview['split_report'] = assignments,report
        docs = {r['id']:r for r in rows if r['annotation']['role']=='document'}
        queries = [r for r in rows if r['annotation']['role']=='query']
        anchors = set(); positives = set()
        for query in queries:
            refs = query['annotation']['positive_refs']; check_positives(w,refs)
            for ref in refs:
                if ref['id'] not in docs: raise WorkbenchError('Select every referenced positive document explicitly.')
                if assignments[ref['id']] != assignments[query['id']]: raise WorkbenchError('Query and positive document must share a family split.')
            anchor = query['text'].strip()
            if anchor in anchors: raise WorkbenchError('Consumer-formatted query anchors repeat; review the sources instead of dropping them.')
            anchors.add(anchor)
            if assignments[query['id']] == 'train':
                if len(refs) != 1: raise WorkbenchError('Train queries require exactly one positive; no positives are dropped.')
                positives.add(refs[0]['id'])
        if len(positives) < 2: raise WorkbenchError('At least two distinct training-positive documents are required.')
        if len({docs[i]['text'] for i in positives}) != len(positives): raise WorkbenchError('Duplicate training-positive text requires regrouping.')
        counts = {}
        for split in ('train','validation','test'):
            ds=[r for r in docs.values() if assignments[r['id']]==split];qs=[r for r in queries if assignments[r['id']]==split]
            counts[split]={'documents':len(ds),'queries':len(qs),'emitted_pairs':len(qs) if split=='train' else 0,
                'distinct_positive_documents':len({ref['id'] for q in qs for ref in q['annotation']['positive_refs']}),
                'families':len({roots[r['id']] for r in ds+qs})}
            if not ds or not qs: raise WorkbenchError('Retrieval train, validation and test each require documents and query judgments; '+split+' is empty.')
        preview['retrieval_counts']=counts
        preview['warnings']=[POSITIVE_ONLY_WARNING, README.decode().splitlines()[1], 'Explicit review and source-family isolation do not establish permission, semantic independence or model quality.']
        if any(rights_note(r)=='unknown' for r in rows): preview['warnings'].append('Some selected sources have unknown rights; review permission.')
        prepared=dict(preview=preview,rows=rows,roots=roots,groups=groups,snapshots=snapshots)
        prepared['files']=file_proofs(prepared);total=0
        for _,raw,expected in entries(prepared,body):
            total+=len(raw)
            if total>MAX_SELECTED_TEXT_BYTES:raise WorkbenchError('Retrieval archive exceeds the complete logical 40 MiB bound, including duplicates/metadata.')
            if expected and hashlib.sha256(raw).hexdigest()!=expected:raise WorkbenchError('Retrieval source changed.', 'conflict',409)
        preview['artifact_bytes']=total
        preview['preview_token']=hashlib.sha256(encode({'format':FORMAT,'records':rows,'families':snapshots,
            'assignments':assignments,'ratios':body['ratios'],'seed':body['seed'],'consumer':CONSUMER,'judgment_scope':JUDGMENT_SCOPE,'files':prepared['files']}).encode()).hexdigest()
        preview['eligible']=True
        return prepared
    except WorkbenchError as error:
        preview['blockers'].append({'message':str(error),'code':error.code,'status':error.status})
        return {'preview':preview}
