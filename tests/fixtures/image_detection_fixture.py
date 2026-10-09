"""Retained six authored 16x12 QA images and test-only target/review states.

These annotations and automated review actions are not human-labelled data or
meaningfully independent physical families. Groups exercise allocator custody.
"""
import base64
import io
from PIL import Image
LABEL = '<img src=x onerror=alert(1)> β'
OTHER_LABEL = '! Other authored QA label'


def populate(dataset):
    rows = []
    for ordinal in range(6):
        split = ('train', 'validation', 'test')[ordinal // 2]
        image = io.BytesIO()
        Image.new('RGB', (16, 12), (ordinal + 1, 60, 120)).save(image, 'PNG')
        row = dataset.workbench.import_asset(dict(kind='image', image=base64.b64encode(image.getvalue()).decode(),
            name=f'detection-{ordinal}.png', groups=[f'authored-independent-{ordinal}'],
            rights='Authored compatibility fixture; automated review-state QA, not human-labelled data'), source_split=split, annotation_task='image_detection')
        # Exercise single pixel at bottom-right, full image and non-square interior.
        bounds = ((15, 11, 1, 1), (0, 0, 16, 12), (2, 3, 7, 5))[ordinal // 2]
        boxes = [dict(zip(('x', 'y', 'width', 'height'), bounds), label=LABEL)] if ordinal % 2 == 0 else []
        row = dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_detection', annotation={'boxes': boxes}, groups=row['groups'], review='human_reviewed'))
        rows.append(row)
    return rows
