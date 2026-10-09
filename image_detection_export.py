"""Bounded box-target transport for the actual pinned Chapter 9 mask reader."""
import hashlib
import io
from PIL import Image
from workbench import WorkbenchError, encode, validate_annotation

FORMAT = 'image_detection_v1'
SPLIT_MAPPING = {'train': 'train', 'validation': 'val', 'test': 'test'}
MAX_RECORDS = 100
MAX_PIXELS = 40_000_000
MAX_TOTAL_PIXELS = 100_000_000
MAX_BYTES = 40 * 1024 * 1024
CONSUMER = {
    'repository': 'bc-ai-ecosystem/training-your-own-models',
    'commit': 'fb895e1a3e08fac86738106e6122bdcafb124e65',
    'archive': 'docs/downloads/training-models-companion.zip',
    'archive_sha256': 'e924589b152f68bb15d89b8f95e3b52005bbe4a9f7770f2d0550b5422d3a11d6',
    'path': 'examples/tiny-ml/train_detector.py',
    'sha256': 'a764f819c9757b9c6869d1695db620372e81aadb2442e018830d21b2743ee551',
    'helper_sha256': 'f99664c5ebc09a07b39d3dd7643bbbe1e669e8c85975642ae8be60dc72591924',
    'torch_api': '2.8.0', 'reader': 'train_detector.Images',
}
TARGET_CONTRACT = {
    'scope': 'Derived rectangular box-target transport; not segmentation ground truth.',
    'mask': 'Same-size L PNG, only 0 and 255; integer pixel-edge xywh, exclusive maximum edge.',
    'negative': 'All-zero mask; presence 0 and normalized xyxy [0,0,0,0].',
    'consumer': 'RGB bilinear resize to 96x96, divide by 255, CHW float32; boxes normalized using original dimensions, float32.',
    'class_names': ['foreground object'],
    'category_namespace': 'Reader class index 0 and binary presence are separate from release-local COCO IDs and retained original-source category IDs.',
}
WARNING = ('Derived rectangular masks transport reviewed boxes, not segmentation ground truth. '
           'The consumer supports one foreground class and at most one object, resizing RGB to 96×96. '
           'Preserve the exact label mapping with the checkpoint; compatibility does not establish training quality.')
README = ("Tuldok image_detection_v1 for the pinned Chapter 9 train_detector.py.\n"
          "Extract; pass archive root as --data. train/val/test/images and matching masks are PNGs.\n"
          "Masks are derived rectangular box-target transport, not segmentation ground truth.\n"
          "Integer pixel edges are retained exactly; fractional and multiple boxes are blocked, never rounded or dropped.\n"
          "Consumer resizes RGB to 96x96 bilinearly; normalized xyxy uses original dimensions and float32.\n"
          "manifest.json foreground_label maps the consumer's generic 'foreground object' label. Keep it with the checkpoint.\n"
          "label_mapping records class index 0 and presence 1, not a foreign COCO category ID.\n"
          "Original native category tables/IDs remain scoped provenance; legacy missing tables are explicitly unavailable.\n"
          "Canonical revisions, source bytes, rights, review and connected family evidence remain in manifest.json.\n"
          "One class, at most one object, nonempty train/val/test; this is compatibility, not quality qualification.\n").encode()


def category_id_status(row):
    """Original acquisition IDs never become IDs for a later edited target."""
    acquisition = row['provenance'].get('acquisition', {})
    if not isinstance(acquisition, dict):
        raise WorkbenchError('Source acquisition evidence must be an object.')
    if acquisition.get('format') != 'canonical_v1':
        return 'not_native'
    declared = acquisition.get('declared')
    upstream = declared.get('upstream') if isinstance(declared, dict) else None
    original = upstream.get('record') if isinstance(upstream, dict) else None
    if not isinstance(original, dict):
        raise WorkbenchError('Original native acquisition evidence is incomplete.')
    if original.get('task') != 'image_detection':
        return 'not_native'
    if 'category_table' not in upstream and 'annotation_category_ids' not in upstream:
        return 'unavailable'
    table, ids = upstream.get('category_table'), upstream.get('annotation_category_ids')
    if (not isinstance(table, list) or not isinstance(ids, list)
            or any(type(item) is not dict or set(item) != {'id', 'name'}
                   or type(item['id']) is not int or item['id'] != number
                   or not isinstance(item['name'], str) for number, item in enumerate(table, 1))):
        raise WorkbenchError('Original native category evidence is incomplete or invalid.')
    mapping = {item['name']: item['id'] for item in table}
    annotation = original.get('annotation')
    if (not isinstance(annotation, dict) or not isinstance(annotation.get('boxes'), list)
            or any(not isinstance(box, dict) or not isinstance(box.get('label'), str) for box in annotation['boxes'])):
        raise WorkbenchError('Original native targets are invalid.')
    boxes = annotation['boxes']
    if (len(mapping) != len(table) or any(box['label'] not in mapping for box in boxes)
            or any(type(value) is not int for value in ids)
            or ids != [mapping[box['label']] for box in boxes]):
        raise WorkbenchError('Original native category evidence differs from its original targets.')
    return 'retained'


def validate_records(rows):
    total = 0
    for row in rows:
        if row['kind'] != 'image' or row['task'] != 'image_detection' or row['review'] != 'human_reviewed' or not row['source_available']:
            raise WorkbenchError('Chapter 9 export requires available human-reviewed image-detection records.')
        try:
            canonical = validate_annotation(row['task'], row['annotation'], row)
        except OverflowError:
            raise WorkbenchError('Box coordinates must be bounded finite numbers.') from None
        if canonical != row['annotation']:
            raise WorkbenchError('Stored boxes are not canonical. Review and save explicitly before export.')
        boxes = canonical['boxes']
        if len(boxes) > 1:
            raise WorkbenchError('The pinned Chapter 9 consumer supports at most one box per image; none are dropped.')
        if boxes and any(not float(boxes[0][key]).is_integer() for key in ('x', 'y', 'width', 'height')):
            raise WorkbenchError('Chapter 9 mask transport requires integer pixel edges. Explicitly review fractional boxes; no rounding is performed.')
        if any(type(row[key]) is not int or row[key] <= 0 for key in ('width', 'height')):
            raise WorkbenchError('Image dimensions must be positive integers.')
        pixels = row['width'] * row['height']
        total += pixels
        if pixels > MAX_PIXELS or total > MAX_TOTAL_PIXELS:
            raise WorkbenchError('Chapter 9 raster bounds are 40 MP per image and 100 MP across selected images.')
        category_id_status(row)


def inspect_projection(rows, assignments):
    labels = {box['label'] for row in rows for box in row['annotation']['boxes']}
    if len(labels) != 1:
        raise WorkbenchError('The pinned Chapter 9 consumer requires exactly one foreground label across the selection, including at least one positive image.')
    counts = {split: {'positive': 0, 'negative': 0} for split in SPLIT_MAPPING}
    for row in rows:
        counts[assignments[row['id']]]['positive' if row['annotation']['boxes'] else 'negative'] += 1
    if any(not sum(count.values()) for count in counts.values()):
        raise WorkbenchError('The pinned Chapter 9 reader requires nonempty train, validation and test splits.')
    return next(iter(labels)), counts


def mask_target(row):
    """Pillow paste uses exclusive right/bottom edges, matching box_from_mask."""
    mask = Image.new('L', (row['width'], row['height']), 0)
    boxes = row['annotation']['boxes']
    edges = [0, 0, 0, 0]
    if boxes:
        box = boxes[0]
        x, y, width, height = (int(box[key]) for key in ('x', 'y', 'width', 'height'))
        edges = [x, y, x + width, y + height]
        mask.paste(255, tuple(edges))
    output = io.BytesIO()
    mask.save(output, 'PNG')
    return output.getvalue(), dict(present=int(bool(boxes)), pixel_xyxy=edges,
        normalized_xyxy=[edges[0] / row['width'], edges[1] / row['height'], edges[2] / row['width'], edges[3] / row['height']])


def entries(workbench, prepared, body):
    """One sequential projection owns preview sizing, hash proof and freeze."""
    preview = prepared['preview']
    manifest = dict(schema_version=1, format=FORMAT, max_objects=1, consumer=CONSUMER,
        target_contract=TARGET_CONTRACT, foreground_label=preview['foreground_label'],
        consumer_label='foreground object',
        label_mapping=dict(annotation_label=preview['foreground_label'], consumer_label='foreground object',
                           consumer_class_index=0, positive_presence=1, negative_presence=0),
        native_category_evidence=preview['native_category_evidence'],
        split_mapping=SPLIT_MAPPING, seed=body['seed'],
        split_report=preview['split_report'], detection_counts=preview['detection_counts'],
        protected_components=prepared['snapshots'], warnings=preview['warnings'], records=[],
        limits=dict(selected_records=MAX_RECORDS, pixels_per_image=MAX_PIXELS,
                    selected_pixels=MAX_TOTAL_PIXELS, archive_uncompressed_bytes=MAX_BYTES))
    for row in prepared['rows']:
        split = preview['assignments'][row['id']]
        exported = SPLIT_MAPPING[split]
        image_name = exported + '/images/' + row['id'] + '.png'
        mask_name = exported + '/masks/' + row['id'] + '.png'
        # Both proof and writer consume the same bounded immutable capture.
        value = prepared['captured_images'][row['id']]
        yield image_name, value, row['content_hash']
        mask, target = mask_target(row)
        digest = hashlib.sha256(mask).hexdigest()
        yield mask_name, mask, digest
        manifest['records'].append(dict(row, split=split, export_split=exported,
            export_group=prepared['groups'][prepared['roots'][row['id']]], asset=image_name,
            asset_sha256=row['content_hash'], mask_asset=mask_name, mask_sha256=digest,
            derived_target=target, exported_pixel_sha256=row['pixel_hash'],
            native_category_id_status=category_id_status(row)))
    yield 'manifest.json', encode(manifest).encode(), None
    yield 'README.txt', README, None
