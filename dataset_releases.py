"""Frozen, self-contained releases with connected-source split allocation."""
import hashlib
import json
import os
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from workbench import WorkbenchError, encode, file_hash, validate_annotation

SPLITS = ('train', 'validation', 'test')
RELEASE_ID = re.compile(r'^[a-f0-9]{64}$')


def allocate(selected, universe, ratios, seed):
    if not isinstance(ratios, dict) or set(ratios) != set(SPLITS):
        raise WorkbenchError('Supply train, validation and test percentages.')
    if any(type(n) is not int or not 0 <= n <= 100 for n in ratios.values()) or sum(ratios.values()) != 100:
        raise WorkbenchError('Split percentages must be integers totaling 100.')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise WorkbenchError('Split seed must be a nonnegative 32-bit integer.')
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
    components = {}
    for row in selected:
        components.setdefault(root('id:' + row['id']), []).append(row['id'])
    active = [s for s in SPLITS if ratios[s]]
    if len(components) < len(active):
        raise WorkbenchError('Too few independent source groups for the requested nonempty splits. Select more independent groups or set unused splits to zero.')
    fixed = {}
    for row in universe:
        split = row.get('source_split', 'unassigned')
        component = root('id:' + row['id'])
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

    def create(self, body):
        workbench = self.workbench
        with workbench.lock, workbench.db:
            rows = workbench.selection(body.get('items'))
            for row in rows:
                if not row['source_available'] or row['annotation'] is None or row['review'] == 'draft':
                    raise WorkbenchError('Every selected record needs an available source and reviewed or programmatically verified annotation.')
                validate_annotation(row['task'], row['annotation'], row)
            assignments, report = allocate(rows, workbench._all(), body.get('ratios'), body.get('seed'))
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
                            if isinstance(asset, Path):
                                # Hash the bytes actually archived, not a preceding read.
                                hasher = hashlib.sha256()
                                with asset.open('rb') as source, archive.open(zipfile.ZipInfo(filename), 'w') as dest:
                                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                                        hasher.update(chunk)
                                        dest.write(chunk)
                                digest = hasher.hexdigest()
                            else:
                                digest = hashlib.sha256(asset).hexdigest()
                                archive.writestr(zipfile.ZipInfo(filename), asset)
                            if digest != row['content_hash']:
                                raise WorkbenchError('Source bytes changed outside Tuldok. Restore the original asset before release.', 'conflict', 409)
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
