"""Exact, filesystem-safe projection for the pinned Chapter 8 image trainer.

The canonical dataset has no two-class or per-split class-coverage restriction.
These requirements belong only to this consumer, which uses ImageFolder's
default allow_empty=False and requires at least two matching class indices.
"""
from collections import Counter

from workbench import WorkbenchError, validate_annotation

FORMAT = 'image_classification_v1'
SPLIT_MAPPING = {'train': 'train', 'validation': 'val', 'test': 'test'}
CONSUMER = {
    'name': 'Training Your Own Models, Chapter 8 image classifier',
    'path': 'examples/tiny-ml/train_image_classifier.py',
    'sha256': 'a198463590d41660c21ae45313b47c3a5baf38889eb9bc029e4c7fe8aa741ac1',
    'torch': '2.8.0', 'torchvision': '0.23.0',
    'reader': 'torchvision.datasets.ImageFolder', 'allow_empty': False,
    'source': 'https://github.com/pytorch/vision/blob/v0.23.0/torchvision/datasets/folder.py',
}


def validate_records(rows):
    """Check the target shape before generic label-count projections read it."""
    for row in rows:
        if (row['task'] != 'image_classification' or row['review'] != 'human_reviewed'
                or not row['source_available']):
            raise WorkbenchError('Chapter 8 classification export requires available images with human-reviewed single-class annotations.')
        canonical = validate_annotation(row['task'], row['annotation'], row)
        if canonical != row['annotation']:
            raise WorkbenchError('Stored class label is not canonical. Review and save it explicitly before export.')


def inspect_projection(rows, assignments):
    """Keep exact labels as data; never use a user-authored label as a path."""
    validate_records(rows)
    labels = sorted({row['annotation']['label'] for row in rows})
    vocabulary = [{'label': label, 'folder': f'class_{index:06d}', 'index': index}
                  for index, label in enumerate(labels)]
    counts = {split: Counter(row['annotation']['label'] for row in rows
                             if assignments.get(row['id']) == split)
              for split in SPLIT_MAPPING}
    coverage = [dict(item, counts={split: counts[split][item['label']] for split in SPLIT_MAPPING})
                for item in vocabulary]
    blockers = []
    if len(labels) < 2:
        blockers.append('The pinned Chapter 8 trainer requires at least two classes. Canonical export supports other class counts.')
    missing = [(split, item) for split in SPLIT_MAPPING for item in vocabulary if not counts[split][item['label']]]
    if missing:
        blockers.append('The pinned Chapter 8 ImageFolder reader requires every class in train, validation and test. '
                        'Missing coverage: ' + '; '.join(f"{split}/{item['folder']}" for split, item in missing)
                        + '. Add independent reviewed examples or adjust the split settings; no records were dropped or reassigned.')
    return vocabulary, coverage, blockers
