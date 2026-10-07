"""Local retained-metadata fixtures; no provider, external dataset or permission judgment."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from workbench import encode

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--data', required=True)
args, _ = parser.parse_known_args()
dataset = app.Dataset(args.data)
try:
    for name, note in [('legacy-missing-note', {}), ('legacy-null-note', {'rights': None})]:
        row = dataset.workbench.import_asset({'kind': 'text', 'name': name, 'text': 'Local retained fixture '+name,
                                              'groups': ['legacy-source']})
        origin = dict(row['provenance']); origin.pop('rights'); origin.update(note)
        with dataset.lock, dataset.db:
            dataset.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?', (encode(origin), row['id']))
finally:
    dataset.close()
app.main()
