"""Tiny authored positive-only compatibility controls, never benchmark truth."""
import hashlib
import unicodedata


def ref(row):
    return {key: row[key] for key in ('id', 'revision', 'source_revision')}


def populate(dataset):
    import retrieval_export
    w = dataset.workbench
    rows, original_hashes = [], {}
    for ordinal, family in enumerate(('orchard', 'garden', 'river')):
        group = 'retrieval-reader-qa-' + family
        docs = []
        for index in range(2):
            text = f'  {family} article {index}: Cafe\u0301, 水 and sunlight.\r\nKeep trailing space.  \n'
            raw = w.import_asset(dict(kind='text', name=f'{family} document {index}', text=text,
                groups=[group], rights='Authored compatibility fixture, not a benchmark'))
            original_hashes[raw['id']] = hashlib.sha256(text.encode()).hexdigest()
            doc = w.save(raw['id'], dict(ref(raw), task='text_retrieval', groups=raw['groups'],
                review='human_reviewed', annotation=dict(role='document', note='Automated QA source review.')))
            assert doc['text'] == unicodedata.normalize('NFC', text.replace('\r\n', '\n'))
            docs.append(doc); rows.append(doc)
        for index in range(2):
            text = f'  How does {family} article {index} discuss Cafe\u0301?\r\n  '
            # Both parents remain immutable even though each current judgment lists one.
            raw = retrieval_export.import_query(w, dict(name=f'{family} query {index}', text=text,
                groups=[group], rights='Authored compatibility fixture, not a benchmark',
                positive_refs=[ref(doc) for doc in docs]))
            assert raw['annotation'] is None and raw['review'] == 'draft'
            original_hashes[raw['id']] = hashlib.sha256(text.encode()).hexdigest()
            rows.append(w.save(raw['id'], dict(ref(raw), task='text_retrieval', groups=raw['groups'],
                review='human_reviewed', annotation=dict(role='query', note='Automated QA explicit positive only.',
                    positive_refs=[ref(docs[index])]))))
        if ordinal == 0:
            text = 'Unused orchard article: this document is UNJUDGED for every query.\n'
            raw = w.import_asset(dict(kind='text', text=text, name='Selected unused document',
                groups=[group], rights='Authored compatibility fixture'))
            original_hashes[raw['id']] = hashlib.sha256(text.encode()).hexdigest()
            rows.append(w.save(raw['id'], dict(ref(raw), task='text_retrieval', groups=raw['groups'],
                review='human_reviewed', annotation=dict(role='document', note='Corpus review grants no relevance.'))))
    draft = w.import_asset(dict(kind='text', text='Unselected raw draft bridge, no review granted.\n',
        name='Unselected raw draft', groups=['retrieval-reader-qa-orchard'], rights='unknown'))
    assert draft['annotation'] is None and draft['review'] == 'draft'
    return rows, draft, original_hashes


def body(rows):
    return dict(format='text_retrieval_v1', items=[ref(row) for row in rows],
        ratios=dict(train=34, validation=33, test=33), seed=42)


def freeze(dataset, rows):
    request = body(rows); preview = dataset.releases.preview(request)
    assert preview['eligible'], preview
    release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
    return dataset.releases.locate(release['id']).read_bytes(), preview
