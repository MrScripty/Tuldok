"""Small authored transport fixture; no claim of useful training quality."""
import base64
import io
from PIL import Image

LABELS = ('../Class β', '<img src=x onerror=alert(1)>')


def populate(dataset):
    rows = []
    for ordinal, (split, label) in enumerate((split, label)
            for split in ('train', 'validation', 'test') for label in LABELS):
        data = io.BytesIO()
        Image.new('RGB', (16, 12), (ordinal + 1, 60, 120)).save(data, 'PNG')
        row = dataset.workbench.import_asset(dict(kind='image', image=base64.b64encode(data.getvalue()).decode(),
            name=f'classifier-{ordinal}.png', groups=[f'fixture-source-{ordinal}'],
            rights='Authored test fixture; not a training-quality corpus'), source_split=split)
        row = dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_classification', annotation={'label': label}, groups=row['groups'], review='human_reviewed'))
        rows.append(row)
    return rows
