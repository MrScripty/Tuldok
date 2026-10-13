# Archived SQLite migration workflow fixture

The source producer is `MrScripty/Tuldok` commit
`1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`, before the PostgreSQL migration.
The fixture was created on 2026-10-11 by loading that exact archived `app.Dataset`
and calling its real import, edit, rights-correction, image-deletion,
instruction-response, preference, saved-selection, saved-search, preview and
release owners. The connection's `iterdump()` produced the SQL snapshot after closing the
dataset. Three multiline SQL text literals were subsequently represented as
`CAST(X'<UTF-8 hex>' AS TEXT)` expressions in `catalog.sql`; SQLite decodes the
exact same values without literal carriage returns or trailing whitespace in
the source fixture. `expected.json` records the original owner responses.

The inputs are newly authored tiny test data: two solid-color 3×4 Pillow RGB
images and short example text with decomposed Unicode, CR/LF, emoji and BOM
characters. One image was deleted through the original owner to retain deleted
lineage. All source text and image fixture bytes are dedicated to the public
domain under CC0 1.0 for testing. Rights notes inside the data are fixture
statements, not a grant for any external dataset. There are no personal data,
secrets, external provider responses, downloaded models or inference calls.

`catalog.sql` preserves original CR/LF and decomposed Unicode evidence through
SQLite UTF-8 hex-to-text expressions. Loading it with
`read_bytes().decode('utf-8')` retains the source representation exactly. The
fixture conversion compared every stored value before and after re-encoding;
all 21 rows were identical.
The PNG, original source, JPEG thumbnail and release archive are retained exact
producer bytes. The migration tests never regenerate the retained archive.

The 4,690-byte frozen ZIP's SHA-256 (also its content-derived release ID) is:

```text
ca3cc6c36ad232912e5b833564c4353e638979ee330895c54c0dc852b952a156
```

The retained SQL snapshot SHA-256 is:

```text
b54c799650573f47082e75608eeb3650209287953f5d4afb90cedc6db2303674
```

This audit command reconstructs the archived producer in a temporary directory
and generates an independent fixture-only release from the retained SQL and
image bytes. It never writes this checked-in fixture, accesses a user dataset,
or regenerates a release during migration:

```sh
legacy_archive=$(mktemp -d)
git archive 1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c | tar -x -C "$legacy_archive"
python - "$legacy_archive" "$PWD/tests/fixtures/sqlite_migration_workflow" <<'PY'
import hashlib, json, pathlib, shutil, sqlite3, sys, tempfile
sys.path.insert(0, sys.argv[1])
from app import Dataset
fixture = pathlib.Path(sys.argv[2])
expected = json.loads((fixture / 'expected.json').read_bytes())
with tempfile.TemporaryDirectory() as directory:
    path = pathlib.Path(directory)
    connection = sqlite3.connect(path / 'dataset.sqlite3')
    connection.executescript((fixture / 'catalog.sql').read_bytes().decode('utf-8'))
    connection.close()
    shutil.copytree(fixture / 'images', path / 'images')
    dataset = Dataset(path)
    try:
        record = expected['record']
        body = dict(items=[{key: record[key] for key in ('id', 'revision', 'source_revision')}],
                    ratios=dict(train=100, validation=0, test=0), seed=42)
        preview = dataset.releases.preview(body)
        release = dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        actual = dataset.releases.locate(release['id']).read_bytes()
        retained = (fixture / 'releases' / (expected['release']['id'] + '.zip')).read_bytes()
        assert actual == retained
        print(hashlib.sha256(actual).hexdigest())
    finally:
        dataset.close()
PY
```

The temporary archived source can then be removed. Runtime migration acceptance
is `python -m unittest discover -s tests -p test_metadata_migration.py -v` with a
disposable local `TULDOK_DATABASE_URL`. Other synthetic per-table migration rows
are constructed in that test module; they exercise exact typed storage and are
not presented as fully validated domain records.
