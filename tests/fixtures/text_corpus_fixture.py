"""Authored compatibility documents. They do not establish model/data quality."""
TEXTS = (
    'Cafe\u0301 and tea. 🙂 A document can contain non-ASCII text, spaces, punctuation and line breaks.\r\n' * 3 + '\n',
    '山と川. A second independent note about trees, sunlight and water. Keep every byte after canonical import.\n' * 3,
    'Third source: αβγ and café. These are authored fixture words for a reader test, not a useful training corpus. ' * 3,
    'Fourth document: 🐈 walks through a quiet room. The corpus projection must retain this complete record.\n' * 3,
    'Fifth source: a bicycle, a lamp, a map. Independent family ownership is metadata, not a semantic guarantee. ' * 3,
    'Sixth note: mañana, 東京, déjà vu. Human review grants this fixture a corpus task only for compatibility tests.\n' * 3,
)


def populate(dataset):
    rows = []
    for index, text in enumerate(TEXTS):
        row = dataset.workbench.import_asset(dict(kind='text', text=text, name=f'Corpus document {index}',
            groups=[f'corpus-fixture-{index}'], rights='Authored compatibility fixture'))
        rows.append(dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='text_corpus', annotation={'note': 'Reviewed this whole authored document for corpus-reader compatibility.'},
            groups=row['groups'], review='human_reviewed')))
    return rows
