"""Project-authored tiny binary judgments, not retrieval-quality labels."""
import hashlib

TASK = 'text_retrieval_binary'
FORMAT = 'text_retrieval_binary_v2'


def ref(row):
    return {key: row[key] for key in ('id', 'revision', 'source_revision')}


def save(workbench, row, annotation, review='human_reviewed'):
    return workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
        task=TASK, annotation=annotation, groups=row['groups'], review=review))


def populate(dataset):
    w = dataset.workbench
    original_hashes = {}
    def source(text, group, parents=()):
        row = w.import_asset(dict(kind='text', text=text, name='Authored binary QA', groups=[group],
            parents=list(parents), rights='Project-authored transport QA; no semantic quality claim'))
        original_hashes[row['id']] = hashlib.sha256(text.encode()).hexdigest()
        return row
    def document(text, group):
        row = source(text, group)
        return save(w, row, dict(role='document', note='Authored document inspection QA'))
    def query(text, group, judgments):
        row = source(text, group, [d['id'] for d, _ in judgments])
        return save(w, row, dict(role='query', note='Authored three-state relation QA',
            judgments=[dict(document=ref(doc), relevance=state) for doc, state in judgments]))
    orchard = [document(text, 'binary-orchard') for text in (
        '  Cafe\u0301 orchard notes.\r\nWater and sunlight.  ',
        'Orchard transport control B: authored negative.\n',
        'Orchard transport control C: explicitly unjudged.\n',
        'Orchard unused selected document: omitted is unjudged.\n')]
    a = query('  Find café orchard?\n ', 'binary-query-A',
        list(zip(orchard[:3], ('relevant', 'not_relevant', 'unjudged'))))
    b = query('Zero-positive orchard QA?\n', 'binary-query-B',
        [(orchard[1], 'not_relevant'), (orchard[2], 'unjudged')])
    garden = document('Garden authored source: all-unjudged query control.\n', 'binary-garden')
    c = query('Garden all-unjudged QA?\n', 'binary-query-C', [(garden, 'unjudged')])
    bridge = source('Unselected retained orchard draft bridge.\n', 'binary-orchard', [orchard[0]['id']])
    return orchard + [a, b, garden, c], bridge, original_hashes


def freeze(dataset, rows):
    request = dict(format=FORMAT, items=[ref(row) for row in rows],
        ratios=dict(train=50, validation=50, test=0), seed=73)
    preview = dataset.releases.preview(request)
    assert preview['eligible'], preview
    release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
    return dataset.releases.locate(release['id']).read_bytes(), preview
