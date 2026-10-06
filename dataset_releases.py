"""Frozen, self-contained releases with connected-source split allocation."""
import hashlib
import json
import os
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from PIL import Image

from workbench import WorkbenchError, analyze, encode, file_hash, validate_annotation

SPLITS = ('train', 'validation', 'test')
RELEASE_ID = re.compile(r'^[a-f0-9]{64}$')
CAPTION_FORMAT = 'image_caption_v1'
CAPTION_CONSUMER = {'path': 'examples/diffusion/check_image_data.py',
                    'sha256': '6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94'}
CAPTION_SPLITS = {'train': 'train', 'validation': 'val', 'test': 'test'}


def connected_components(universe):
    """One relationship graph owns allocation and exported family identities."""
    parent = {}
    def root(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def join(a, b):
        parent[root(b)] = root(a)
    # All records participate, including unselected bridges and deleted sources.
    for row in universe:
        key = 'id:' + row['id']
        root(key)
        links = ['group:' + g for g in row['groups']] + ['id:' + p for p in row['parents']]
        if row['content_hash']:
            links.append('content:' + row['kind'] + ':' + row['content_hash'])
        if row['pixel_hash']:
            links.append('pixels:' + row['pixel_hash'])
        if row['kind'] == 'image' and row.get('source_lineage_known', row['source_available']):
            links.append('legacy:' + ('book:' + row['book_id'] if row['book_id'] else 'session:' + row['session_id']))
        for link in links:
            join(key, link)
    return {row['id']: root('id:' + row['id']) for row in universe}


def allocate(selected, universe, ratios, seed):
    if not isinstance(ratios, dict) or set(ratios) != set(SPLITS):
        raise WorkbenchError('Supply train, validation and test percentages.')
    if any(type(n) is not int or not 0 <= n <= 100 for n in ratios.values()) or sum(ratios.values()) != 100:
        raise WorkbenchError('Split percentages must be integers totaling 100.')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise WorkbenchError('Split seed must be a nonnegative 32-bit integer.')
    roots = connected_components(universe)
    components = {}
    for row in selected:
        components.setdefault(roots[row['id']], []).append(row['id'])
    active = [s for s in SPLITS if ratios[s]]
    if len(components) < len(active):
        raise WorkbenchError('Too few independent source groups for the requested nonempty splits. Select more independent groups or set unused splits to zero.')
    fixed = {}
    for row in universe:
        split = row.get('source_split', 'unassigned')
        component = roots[row['id']]
        if component in components and not row.get('source_lineage_known', True):
            raise WorkbenchError('A related deleted source has no retained source lineage. Its split independence cannot be established.')
        if split in SPLITS and component in components:
            if component in fixed and fixed[component] != split:
                raise WorkbenchError('Connected source groups have conflicting existing splits. Resolve the source assignments before releasing.')
            if not ratios[split] and component in components:
                raise WorkbenchError('A selected source is already assigned to a split with zero requested weight.')
            fixed[component] = split
    assigned, counts = {}, Counter()
    pending = []
    for component, ids in components.items():
        if component in fixed:
            for record_id in ids:
                assigned[record_id] = fixed[component]
            counts[fixed[component]] += len(ids)
        else:
            pending.append(ids)
    if len(pending) < sum(not counts[split] for split in active):
        raise WorkbenchError('Existing source splits leave too few independent groups to populate all requested splits.')
    groups = sorted(pending, key=lambda ids: (-len(ids), hashlib.sha256((str(seed) + ':' + ','.join(sorted(ids))).encode()).hexdigest()))
    for index, ids in enumerate(groups):
        empty = [s for s in active if not counts[s]]
        choices = empty if len(groups) - index == len(empty) else active
        split = max(choices, key=lambda s: (ratios[s] * len(selected) / 100 - counts[s], -SPLITS.index(s)))
        for record_id in ids:
            assigned[record_id] = split
        counts[split] += len(ids)
    return assigned, {'requested_percentages': ratios, 'actual_counts': dict(counts), 'independent_components': len(components),
                      'note': 'Whole connected groups are indivisible; existing source splits are preserved. Requested percentages are targets, not exact quotas.'}


def archive_asset(archive, asset, filename, expected_hash):
    """Hash the bytes actually archived, not a preceding filesystem read."""
    if isinstance(asset, Path):
        hasher = hashlib.sha256()
        with asset.open('rb') as source, archive.open(zipfile.ZipInfo(filename), 'w') as dest:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                hasher.update(chunk)
                dest.write(chunk)
        digest = hasher.hexdigest()
    else:
        digest = hashlib.sha256(asset).hexdigest()
        archive.writestr(zipfile.ZipInfo(filename), asset)
    if digest != expected_hash:
        raise WorkbenchError('Source bytes changed outside Tuldok. Restore the original asset before release.', 'conflict', 409)
    return digest


class Releases:
    def __init__(self, workbench):
        self.workbench = workbench
        self.path = workbench.dataset.path / 'releases'
        self.path.mkdir(exist_ok=True)

    def locate(self, release_id):
        if not isinstance(release_id, str) or not RELEASE_ID.fullmatch(release_id):
            raise WorkbenchError('Invalid release ID.')
        path = self.path / (release_id + '.zip')
        if not path.is_file():
            raise WorkbenchError('Release not found.', 'unavailable', 404)
        return path

    def preview(self, body):
        """Inspect the exact selection without persisting even lazy image enrollment."""
        workbench = self.workbench
        with workbench.lock:
            workbench.db.execute('SAVEPOINT release_preview')
            try:
                return self._prepare(body)['preview']
            finally:
                workbench.db.execute('ROLLBACK TO release_preview')
                workbench.db.execute('RELEASE release_preview')

    def _prepare(self, body):
        """Shared validation/allocation authority for preview and final export.

        Caller owns the source lock. A preview token is a freshness fingerprint,
        not a permission grant. No archive or persistent split is created here.
        """
        workbench = self.workbench
        format_name = body.get('format', 'canonical_v1')
        preview = {'eligible': False, 'format': format_name, 'selected_count': 0,
                   'analysis': None, 'blockers': [], 'warnings': [], 'lineage': [],
                   'split_report': None, 'assignments': {}, 'preview_token': None}
        def block(error, record_id=None):
            item = {'code': error.code, 'message': str(error), 'status': error.status}
            if record_id is not None:
                item['record_id'] = record_id
            preview['blockers'].append(item)
        if format_name not in ('canonical_v1', CAPTION_FORMAT):
            block(WorkbenchError('Unknown release format.'))
        try:
            rows = workbench.selection(body.get('items'))
        except WorkbenchError as error:
            block(error)
            return {'preview': preview}
        preview['selected_count'] = len(rows)
        preview['analysis'] = analyze(rows)
        universe = workbench._all()
        roots = connected_components(universe)
        active_roots = {roots[row['id']] for row in rows}
        families = {}
        for row in universe:
            if roots[row['id']] in active_roots:
                families.setdefault(roots[row['id']], []).append(row)
        groups = {component: 'component:' + hashlib.sha256(encode(sorted(r['id'] for r in family)).encode()).hexdigest()
                  for component, family in families.items()}
        selected_ids = {row['id'] for row in rows}
        snapshots = {}
        for component, family in families.items():
            family = sorted(family, key=lambda row: row['id'])
            snapshots[groups[component]] = [
                {key: row[key] for key in ('id', 'kind', 'revision', 'source_revision', 'content_hash', 'pixel_hash',
                                          'groups', 'parents', 'source_available', 'source_lineage_known',
                                          'source_split', 'source_sha256', 'book_id', 'session_id')}
                for row in family]
            preview['lineage'].append({'id': groups[component],
                'selected_ids': [row['id'] for row in family if row['id'] in selected_ids],
                'member_ids': [row['id'] for row in family],
                'deleted_ids': [row['id'] for row in family if not row['source_available']],
                'fixed_splits': sorted({row['source_split'] for row in family if row['source_split'] in SPLITS})})
        preview['lineage'].sort(key=lambda family: family['id'])
        pixels, pixel_hashes = set(), {}
        for row in rows:
            try:
                if format_name == CAPTION_FORMAT:
                    if row['task'] != 'image_caption' or row['review'] != 'human_reviewed' or not row['source_available']:
                        raise WorkbenchError('Caption export requires available images with human-reviewed image-caption annotations.')
                elif not row['source_available'] or row['annotation'] is None or row['review'] == 'draft':
                    raise WorkbenchError('Every selected record needs an available source and reviewed or programmatically verified annotation.')
                validate_annotation(row['task'], row['annotation'], row)
            except WorkbenchError as error:
                block(error, row['id'])
            try:
                asset, _ = workbench.asset(row['id'])
                digest = file_hash(asset) if isinstance(asset, Path) else hashlib.sha256(asset).hexdigest()
                if digest != row['content_hash']:
                    raise WorkbenchError('Source bytes changed outside Tuldok. Restore the original asset before release.', 'conflict', 409)
                if row['kind'] == 'image':
                    with Image.open(asset) as image:
                        if image.format != 'PNG' or image.getexif().get(274, 1) != 1:
                            raise WorkbenchError('Image assets must be normalized PNGs with EXIF orientation 1.')
                        image = image.convert('RGB'); image.load()
                        pixel_hash = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
                        if image.size != (row['width'], row['height']) or pixel_hash != row['pixel_hash']:
                            raise WorkbenchError('Source pixels changed outside Tuldok.', 'conflict', 409)
                        if format_name == CAPTION_FORMAT:
                            if min(image.size) < 512:
                                preview['warnings'].append(f"Small image: {row['id']}.png ({image.width}x{image.height}); consumer warns below 512 pixels.")
                            if pixel_hash in pixels:
                                raise WorkbenchError('Caption export forbids exact decoded-pixel duplicates, including within a split.')
                        pixels.add(pixel_hash)
                        pixel_hashes[row['id']] = pixel_hash
            except WorkbenchError as error:
                block(error, row['id'])
            except (OSError, ValueError):
                block(WorkbenchError('Source asset is unreadable.', 'unavailable', 409), row['id'])
        try:
            assignments, report = allocate(rows, universe, body.get('ratios'), body.get('seed'))
            preview['assignments'], preview['split_report'] = assignments, report
            if format_name == CAPTION_FORMAT and any(not report['actual_counts'].get(split) for split in SPLITS):
                raise WorkbenchError('Image-caption export requires nonempty train, validation and test splits.')
        except WorkbenchError as error:
            block(error)
        if format_name == 'canonical_v1':
            preview['warnings'].append('Canonical export projects detection to COCO; other tasks remain typed JSONL records, not one interchangeable training format.')
            if any(row['task'] == 'image_caption' for row in rows):
                preview['warnings'].append('Canonical captions remain manifest/JSONL records. Choose image-caption format for the pinned train/val/test imagefolder consumer.')
        if preview['analysis']['unknown_rights']:
            preview['warnings'].append('Some selected records have unknown rights. Review permission before training or sharing.')
        preview['warnings'].append('Exact matches and protected lineage do not establish semantic independence or training quality.')
        preview['eligible'] = not preview['blockers']
        if preview['eligible']:
            preview['preview_token'] = hashlib.sha256(encode({
                'preview_schema': 1, 'format': format_name, 'ratios': body['ratios'], 'seed': body['seed'],
                'records': rows, 'protected_components': snapshots,
                'assignments': preview['assignments']}).encode()).hexdigest()
        return {'preview': preview, 'rows': rows, 'pixel_hashes': pixel_hashes,
                'roots': roots, 'groups': groups, 'snapshots': snapshots}

    def _checked(self, body):
        prepared = self._prepare(body)
        preview = prepared['preview']
        if preview['blockers']:
            first = preview['blockers'][0]
            raise WorkbenchError(first['message'], first['code'], first['status'])
        if 'preview_token' in body and body['preview_token'] != preview['preview_token']:
            raise WorkbenchError('Release preview changed. Preview the current selection and settings again.', 'conflict', 409)
        return prepared

    def create(self, body):
        format_name = body.get('format', 'canonical_v1')
        if format_name not in ('canonical_v1', CAPTION_FORMAT):
            raise WorkbenchError('Unknown release format.')
        if format_name == CAPTION_FORMAT:
            return self._create_captions(body)
        workbench = self.workbench
        with workbench.lock, workbench.db:
            prepared = self._checked(body)
            rows = prepared['rows']
            assignments = prepared['preview']['assignments']
            report = prepared['preview']['split_report']
            manifest = {'schema_version': 1, 'seed': body['seed'], 'split_report': report,
                        'coordinate_contract': 'Oriented image pixel-edge xywh; text spans are NFC/LF Unicode code-point [start,end).',
                        'limitations': ['Review status is evidence, not a quality guarantee.', 'Rights and semantic source independence require human judgment.'],
                        'records': []}
            vocabulary = sorted({target['label'] for row in rows if row['task'] == 'image_detection' for target in row['annotation']['boxes']})
            categories = {label: i + 1 for i, label in enumerate(vocabulary)}
            coco = {split: {'info': {'description': 'Tuldok detection release', 'version': '1'}, 'licenses': [], 'images': [], 'annotations': [], 'categories': [{'id': i, 'name': label} for label, i in categories.items()]} for split in SPLITS}
            text_rows = {split: [] for split in SPLITS}
            fd, temporary = tempfile.mkstemp(prefix='.building-', suffix='.zip', dir=self.path)
            try:
                with os.fdopen(fd, 'w+b') as target:
                    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                        for index, row in enumerate(rows, 1):
                            split = assignments[row['id']]
                            asset, _ = workbench.asset(row['id'])
                            filename = 'assets/' + row['id'] + ('.png' if row['kind'] == 'image' else '.txt')
                            digest = archive_asset(archive, asset, filename, row['content_hash'])
                            record = dict(row, split=split, asset=filename, asset_sha256=digest)
                            manifest['records'].append(record)
                            if row['task'] == 'image_detection':
                                coco[split]['images'].append({'id': index, 'file_name': filename, 'width': row['width'], 'height': row['height']})
                                for box in row['annotation']['boxes']:
                                    coco[split]['annotations'].append({'id': len(coco[split]['annotations']) + 1, 'image_id': index,
                                        'category_id': categories[box['label']], 'bbox': [box[k] for k in ('x', 'y', 'width', 'height')],
                                        'area': box['width'] * box['height'], 'iscrowd': 0})
                            else:
                                text_rows[split].append(record)
                        manifest['vocabulary'] = vocabulary
                        archive.writestr(zipfile.ZipInfo('manifest.json'), encode(manifest))
                        for split in SPLITS:
                            archive.writestr(zipfile.ZipInfo(split + '/coco.json'), encode(coco[split]))
                            archive.writestr(zipfile.ZipInfo(split + '/records.jsonl'), ''.join(encode(row) + '\n' for row in text_rows[split]))
                        archive.writestr(zipfile.ZipInfo('README.txt'), 'Tuldok frozen release v1. Asset paths are relative to archive root.\nCOCO projections contain detection only. JSONL contains other task records.\nText spans index Unicode code points in canonical text, not UTF-16 or bytes.\nSee manifest.json for revisions, lineage, review, vocabulary and split report.\n')
                    target.flush()
                    os.fsync(target.fileno())
                release_id = file_hash(Path(temporary))
                os.replace(temporary, self.path / (release_id + '.zip'))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {'id': release_id, 'url': '/api/workbench/releases/' + release_id + '.zip', 'records': len(rows), 'split_report': report}

    def _create_captions(self, body):
        """Freeze only reviewed captions into the pinned imagefolder contract."""
        workbench = self.workbench
        with workbench.lock, workbench.db:
            prepared = self._checked(body)
            rows = prepared['rows']
            assignments = prepared['preview']['assignments']
            report = prepared['preview']['split_report']
            roots, groups = prepared['roots'], prepared['groups']
            manifest = {'schema_version': 1, 'format': CAPTION_FORMAT, 'consumer': CAPTION_CONSUMER,
                        'seed': body['seed'], 'split_mapping': CAPTION_SPLITS, 'split_report': report,
                        'records': [], 'protected_components': {}, 'warnings': [],
                        'limitations': ['Human review is evidence, not a quality guarantee.',
                                       'Rights, sensitive metadata, near duplicates and semantic independence require manual inspection.']}
            manifest['protected_components'] = prepared['snapshots']
            manifest['warnings'] = [warning for warning in prepared['preview']['warnings'] if warning.startswith('Small image:')]
            metadata = {split: [] for split in CAPTION_SPLITS.values()}
            fd, temporary = tempfile.mkstemp(prefix='.building-', suffix='.zip', dir=self.path)
            try:
                with os.fdopen(fd, 'w+b') as target:
                    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                        for row in rows:
                            canonical_split = assignments[row['id']]
                            split = CAPTION_SPLITS[canonical_split]
                            filename = row['id'] + '.png'
                            asset, _ = workbench.asset(row['id'])
                            pixel_hash = prepared['pixel_hashes'][row['id']]
                            digest = archive_asset(archive, asset, split + '/' + filename, row['content_hash'])
                            group = groups[roots[row['id']]]
                            metadata[split].append({'file_name': filename, 'text': row['annotation']['caption'], 'group': group})
                            manifest['records'].append(dict(row, split=canonical_split, export_split=split,
                                export_group=group, asset=split + '/' + filename, asset_sha256=digest,
                                exported_pixel_sha256=pixel_hash))
                        for split, records in metadata.items():
                            archive.writestr(zipfile.ZipInfo(split + '/metadata.jsonl'), ''.join(encode(row) + '\n' for row in records))
                        archive.writestr(zipfile.ZipInfo('manifest.json'), encode(manifest))
                        archive.writestr(zipfile.ZipInfo('README.txt'),
                            'Tuldok image-caption v1. Extract and run the pinned consumer validator.\n'
                            'train/val/test contain normalized PNGs and metadata.jsonl (file_name, text, group).\n'
                            'validation maps explicitly to val. text is a reviewed caption, never a generation prompt.\n'
                            'manifest.json freezes canonical revisions, hashes, provenance and connected protected lineage.\n')
                    target.flush(); os.fsync(target.fileno())
                release_id = file_hash(Path(temporary))
                os.replace(temporary, self.path / (release_id + '.zip'))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {'id': release_id, 'url': '/api/workbench/releases/' + release_id + '.zip',
                    'format': CAPTION_FORMAT, 'records': len(rows), 'split_report': report, 'warnings': manifest['warnings']}
