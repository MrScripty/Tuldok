"""Frozen, self-contained releases with connected-source split allocation."""
import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from PIL import Image

import image_classification_export as classification_export
import image_detection_export as detection_export
import text_corpus_export as corpus_export

from workbench import WorkbenchError, MAX_TEXT, MAX_SELECTED_TEXT_BYTES, analyze, encode, file_hash, rights_note, validate_annotation

SPLITS = ('train', 'validation', 'test')
RELEASE_ID = re.compile(r'^[a-f0-9]{64}$')
CAPTION_FORMAT = 'image_caption_v1'
INSTRUCTION_FORMAT = 'text_instruction_v1'
PREFERENCE_FORMAT = 'text_preference_v1'
INSTRUCTION_CONSUMER = {'trl': '0.23.1', 'trl_commit': '4529a1c8b1813480a85b02c9c8e7f75a29085d65',
                        'datasets': '4.1.1', 'datasets_commit': '9be15a723b460586999b6aa1f346e284342fcc1f',
                        'type': 'standard prompt-completion'}
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


def family_context(selected, universe):
    roots = connected_components(universe)
    active = {roots[row['id']] for row in selected}
    families = {}
    for row in universe:
        if roots[row['id']] in active:
            families.setdefault(roots[row['id']], []).append(row)
    groups = {component: 'component:' + hashlib.sha256(encode(sorted(r['id'] for r in family)).encode()).hexdigest()
              for component, family in families.items()}
    selected_ids = {row['id'] for row in selected}
    snapshots, lineage = {}, []
    for component, family in families.items():
        family = sorted(family, key=lambda row: row['id'])
        snapshots[groups[component]] = [
            {key: row[key] for key in ('id', 'kind', 'revision', 'source_revision', 'content_hash', 'pixel_hash',
                                      'groups', 'parents', 'source_available', 'source_lineage_known',
                                      'source_split', 'source_sha256', 'book_id', 'session_id')}
            for row in family]
        lineage.append({'id': groups[component],
                        'selected_ids': [row['id'] for row in family if row['id'] in selected_ids],
                        'member_ids': [row['id'] for row in family],
                        'deleted_ids': [row['id'] for row in family if not row['source_available']],
                        'fixed_splits': sorted({row['source_split'] for row in family if row['source_split'] in SPLITS})})
    return roots, groups, snapshots, sorted(lineage, key=lambda family: family['id'])


def allocate(selected, universe, ratios, seed, weights=None):
    if not isinstance(ratios, dict) or set(ratios) != set(SPLITS):
        raise WorkbenchError('Supply train, validation and test percentages.')
    if any(type(n) is not int or not 0 <= n <= 100 for n in ratios.values()) or sum(ratios.values()) != 100:
        raise WorkbenchError('Split percentages must be integers totaling 100.')
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise WorkbenchError('Split seed must be a nonnegative 32-bit integer.')
    roots = connected_components(universe)
    weights = weights or {row['id']: 1 for row in selected}
    total = sum(weights[row['id']] for row in selected)
    weight = lambda ids: sum(weights[record_id] for record_id in ids)
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
            counts[fixed[component]] += weight(ids)
        else:
            pending.append(ids)
    if len(pending) < sum(not counts[split] for split in active):
        raise WorkbenchError('Existing source splits leave too few independent groups to populate all requested splits.')
    groups = sorted(pending, key=lambda ids: (-weight(ids), hashlib.sha256((str(seed) + ':' + ','.join(sorted(ids))).encode()).hexdigest()))
    for index, ids in enumerate(groups):
        empty = [s for s in active if not counts[s]]
        choices = empty if len(groups) - index == len(empty) else active
        split = max(choices, key=lambda s: (ratios[s] * total / 100 - counts[s], -SPLITS.index(s)))
        for record_id in ids:
            assigned[record_id] = split
        counts[split] += weight(ids)
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
        if format_name == detection_export.FORMAT:
            return self._prepare_detection(body)
        if format_name == corpus_export.FORMAT:
            return self._prepare_corpus(body)
        if format_name == PREFERENCE_FORMAT:
            return self._prepare_preferences(body)
        if format_name == INSTRUCTION_FORMAT:
            return self._prepare_responses(body)
        preview = {'eligible': False, 'format': format_name, 'selected_count': 0,
                   'analysis': None, 'blockers': [], 'warnings': [], 'lineage': [],
                   'split_report': None, 'assignments': {}, 'preview_token': None}
        def block(error, record_id=None):
            item = {'code': error.code, 'message': str(error), 'status': error.status}
            if record_id is not None:
                item['record_id'] = record_id
            preview['blockers'].append(item)
        if format_name not in ('canonical_v1', CAPTION_FORMAT, classification_export.FORMAT):
            block(WorkbenchError('Unknown release format.'))
        try:
            rows = workbench.selection(body.get('items'))
        except WorkbenchError as error:
            block(error)
            return {'preview': preview}
        preview['selected_count'] = len(rows)
        if format_name == classification_export.FORMAT:
            if set(body) - {'format', 'items', 'ratios', 'seed', 'preview_token'}:
                block(WorkbenchError('Unknown classification release fields.'))
                return {'preview': preview}
            for row in rows:
                try:
                    classification_export.validate_records([row])
                except WorkbenchError as error:
                    block(error, row['id'])
                    return {'preview': preview}
        preview['analysis'] = analyze(rows)
        try:
            workbench.check_immutable_selection(rows)
        except WorkbenchError as error:
            block(error)
            return {'preview': preview}
        universe = workbench._all()
        roots, groups, snapshots, preview['lineage'] = family_context(rows, universe)
        pixels, pixel_hashes = set(), {}
        for row in rows:
            try:
                if format_name == classification_export.FORMAT:
                    if row['task'] != 'image_classification' or row['review'] != 'human_reviewed' or not row['source_available']:
                        raise WorkbenchError('Chapter 8 classification export requires available images with human-reviewed single-class annotations.')
                elif format_name == CAPTION_FORMAT:
                    if row['task'] != 'image_caption' or row['review'] != 'human_reviewed' or not row['source_available']:
                        raise WorkbenchError('Caption export requires available images with human-reviewed image-caption annotations.')
                elif not row['source_available'] or row['annotation'] is None or row['review'] == 'draft':
                    raise WorkbenchError('Every selected record needs an available source and reviewed or programmatically verified annotation.')
                if row['kind'] in ('sequence', 'mesh') and row['review'] != 'human_reviewed':
                    raise WorkbenchError('Sequence export requires human-reviewed whole trajectories.' if row['kind'] == 'sequence' else 'Mesh export requires human-reviewed whole geometry records.')
                normalized = validate_annotation(row['task'], row['annotation'], row)
                if row['task'] == 'sequence_transport' and 'temporal_labels' in row['annotation']:
                    from sequence_temporal_labels import verify_source
                    if encode(normalized) != encode(row['annotation']):
                        raise WorkbenchError('Temporal labels are not canonical stored targets.')
                    verify_source(workbench, row)
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
        if format_name == classification_export.FORMAT:
            try:
                vocabulary, coverage, blockers = classification_export.inspect_projection(rows, preview['assignments'])
                preview['class_vocabulary'], preview['class_coverage'] = vocabulary, coverage
                for message in blockers:
                    block(WorkbenchError(message))
            except WorkbenchError as error:
                block(error)
            if preview['analysis']['duplicate_content_records']:
                preview['warnings'].append('Exact decoded-pixel repeats are retained in the same connected split. Inspect repeated examples and contradictory labels before training; none are discarded.')
            preview['warnings'].append('Opaque class folders are model indices. Use manifest.json class_vocabulary to recover exact labels. The mapping is frozen per release, not shared automatically across releases.')
        if format_name == 'canonical_v1':
            if any(row['kind'] == 'mesh' for row in rows):
                preview['warnings'].append('Static mesh assets retain raw PLY/sidecar bytes and declared units/frame/provenance; geometry inspection is not simulation or training qualification.')
            if any(row['kind'] == 'sequence' for row in rows):
                preview['warnings'].append('Sequence assets are complete raw run.json/frames.jsonl ZIPs. Read sequence-only releases with native_sequence_dataset.py: separate native MAC arrays/time and human coverage. This transport-only data does not qualify a trainer, physical truth or independent train/evaluation families.')
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

    def _prepare_detection(self, body):
        preview = dict(format=detection_export.FORMAT, eligible=False, selected_count=0,
                       analysis=None, blockers=[], warnings=[], lineage=[], assignments={},
                       split_report=None, preview_token=None)
        record_id = None
        try:
            if set(body) - {'format', 'items', 'ratios', 'seed', 'preview_token'}:
                raise WorkbenchError('Unknown detection release fields.')
            items = body.get('items')
            if not isinstance(items, list) or not 1 <= len(items) <= detection_export.MAX_RECORDS:
                raise WorkbenchError('Select 1–100 records per Chapter 9 release.')
            try:
                rows = self.workbench.selection(items, max_snapshot_bytes=detection_export.MAX_BYTES)
            except WorkbenchError:
                raise
            except ValueError:
                raise WorkbenchError('Stored selection must contain bounded finite JSON values.') from None
            preview['selected_count'] = len(rows)
            detection_export.validate_records(rows)
            self.workbench.check_immutable_selection(rows)
            # Capture within the aggregate byte budget before any raster decode.
            # External replacements cannot change the bytes later decoded/archived.
            minimum = sum(len(encode(row).encode()) for row in rows)
            captured = {}
            for row in rows:
                record_id = row['id']
                asset, _ = self.workbench.asset(row['id'])
                remaining = detection_export.MAX_BYTES - minimum
                if remaining < 0 or asset.stat().st_size > remaining:
                    raise WorkbenchError('Detection archive exceeds the 40 MiB complete logical archive bound.')
                with asset.open('rb') as source:
                    value = source.read(remaining + 1)
                if len(value) > remaining:
                    raise WorkbenchError('Detection archive exceeds the 40 MiB complete logical archive bound.')
                minimum += len(value)
                captured[row['id']] = value
            # Check every captured header before allocating the first RGB raster.
            for row in rows:
                record_id = row['id']
                with Image.open(io.BytesIO(captured[row['id']])) as image:
                    if image.format != 'PNG':
                        raise WorkbenchError('Image assets must be normalized PNGs.')
                    if image.size != (row['width'], row['height']):
                        raise WorkbenchError('Source dimensions changed outside Tuldok.', 'conflict', 409)
            for row in rows:
                record_id = row['id']
                value = captured[row['id']]
                if hashlib.sha256(value).hexdigest() != row['content_hash']:
                    raise WorkbenchError('Source bytes changed outside Tuldok.', 'conflict', 409)
                with Image.open(io.BytesIO(value)) as image:
                    if image.size != (row['width'], row['height']):
                        raise WorkbenchError('Source dimensions changed outside Tuldok.', 'conflict', 409)
                    if image.getexif().get(274, 1) != 1:
                        raise WorkbenchError('Image assets must have EXIF orientation 1.')
                    image = image.convert('RGB')
                    digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
                    if digest != row['pixel_hash']:
                        raise WorkbenchError('Source pixels changed outside Tuldok.', 'conflict', 409)
            record_id = None
            preview['analysis'] = analyze(rows)
            universe = self.workbench._all()
            roots, groups, snapshots, preview['lineage'] = family_context(rows, universe)
            preview['assignments'], preview['split_report'] = allocate(rows, universe, body.get('ratios'), body.get('seed'))
            preview['foreground_label'], preview['detection_counts'] = detection_export.inspect_projection(rows, preview['assignments'])
            preview['native_category_evidence'] = dict.fromkeys(('retained', 'unavailable', 'not_native'), 0)
            for row in rows:
                preview['native_category_evidence'][detection_export.category_id_status(row)] += 1
            if preview['native_category_evidence']['unavailable']:
                preview['warnings'].append('Legacy native records lack original category-ID evidence. Those IDs are unavailable and have not been guessed.')
            preview['warnings'].append(detection_export.WARNING)
            for split, count in preview['detection_counts'].items():
                if not count['positive']:
                    preview['warnings'].append(f'{split} has no positives: localization is untrained in train, and positive IoU is undefined in evaluation.')
                if not count['negative']:
                    preview['warnings'].append(f'{split} has no negatives: false-alarm rate is undefined.')
            if preview['analysis']['duplicate_content_records']:
                preview['warnings'].append('Exact pixel repeats remain in one connected split; none are discarded.')
            if preview['analysis']['unknown_rights']:
                preview['warnings'].append('Some selected images have unknown rights. Review permission before training or sharing.')
            preview['warnings'].append('Human review and protected families do not establish semantic independence, quality or permission.')
            prepared = dict(preview=preview, rows=rows, roots=roots, groups=groups,
                            snapshots=snapshots, captured_images=captured)
            total, hashes = 0, {}
            for name, value, expected in detection_export.entries(self.workbench, prepared, body):
                total += len(value)
                if total > detection_export.MAX_BYTES:
                    raise WorkbenchError('Detection archive exceeds the 40 MiB complete logical archive bound, including masks and metadata.')
                digest = hashlib.sha256(value).hexdigest()
                if expected and digest != expected:
                    raise WorkbenchError('Source bytes changed outside Tuldok.', 'conflict', 409)
                hashes[name] = digest
            prepared['entry_hashes'] = hashes
            preview['artifact_bytes'] = total
            preview['preview_token'] = hashlib.sha256(encode(dict(format=detection_export.FORMAT,
                schema=1, ratios=body['ratios'], seed=body['seed'], records=rows,
                protected_components=snapshots, assignments=preview['assignments'],
                consumer=detection_export.CONSUMER, target_contract=detection_export.TARGET_CONTRACT,
                entry_hashes=hashes)).encode()).hexdigest()
            preview['eligible'] = True
            return prepared
        except (WorkbenchError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
            if not isinstance(error, WorkbenchError):
                error = WorkbenchError('Source asset is unreadable.', 'unavailable', 409)
            blocker = dict(message=str(error), code=error.code, status=error.status)
            if record_id is not None:
                blocker['record_id'] = record_id
            preview['blockers'].append(blocker)
            return dict(preview=preview)

    def _create_detection(self, body):
        with self.workbench.lock, self.workbench.db:
            prepared = self._checked(body)
            fd, temporary = tempfile.mkstemp(prefix='.building-', suffix='.zip', dir=self.path)
            try:
                with os.fdopen(fd, 'w+b') as target:
                    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                        total, names = 0, set()
                        for name, value, _ in detection_export.entries(self.workbench, prepared, body):
                            total += len(value)
                            if total > detection_export.MAX_BYTES:
                                raise WorkbenchError('Detection archive exceeds the 40 MiB complete logical archive bound.')
                            if name in names or name not in prepared['entry_hashes']:
                                raise WorkbenchError('Detection projection changed.', 'conflict', 409)
                            names.add(name)
                            archive_asset(archive, value, name, prepared['entry_hashes'][name])
                        if names != set(prepared['entry_hashes']):
                            raise WorkbenchError('Detection projection changed.', 'conflict', 409)
                    target.flush(); os.fsync(target.fileno())
                release_id = file_hash(Path(temporary))
                os.replace(temporary, self.path / (release_id + '.zip'))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            preview = prepared['preview']
            return dict(id=release_id, url='/api/workbench/releases/' + release_id + '.zip',
                        format=detection_export.FORMAT, records=len(prepared['rows']),
                        split_report=preview['split_report'], foreground_label=preview['foreground_label'],
                        detection_counts=preview['detection_counts'], artifact_bytes=preview['artifact_bytes'],
                        warnings=preview['warnings'])

    def _prepare_corpus(self, body):
        preview = {'format': corpus_export.FORMAT, 'eligible': False, 'selected_count': 0,
                   'analysis': None, 'blockers': [], 'warnings': [], 'lineage': [],
                   'assignments': {}, 'split_report': None, 'preview_token': None}
        record_id = None
        try:
            if set(body) - {'format', 'items', 'ratios', 'seed', 'preview_token'}:
                raise WorkbenchError('Unknown corpus release fields.')
            rows = self.workbench.selection(body.get('items'), max_snapshot_bytes=MAX_SELECTED_TEXT_BYTES)
            preview['selected_count'] = len(rows)
            minimum_bytes = 0
            for row in rows:
                record_id = row['id']
                corpus_export.validate_records([row])
                minimum_bytes += len(encode(row).encode('utf-8')) + 2 * len(row['text'].encode('utf-8')) + 2
                if minimum_bytes > MAX_SELECTED_TEXT_BYTES:
                    raise WorkbenchError('Corpus archive exceeds the 40 MiB complete logical archive bound, including duplicated assets and metadata.')
                asset, _ = self.workbench.asset(row['id'])
                if hashlib.sha256(asset).hexdigest() != row['content_hash']:
                    raise WorkbenchError('Source bytes changed outside Tuldok.', 'conflict', 409)
            record_id = None
            preview['analysis'] = analyze(rows)
            universe = self.workbench._all()
            roots, groups, snapshots, preview['lineage'] = family_context(rows, universe)
            assignments, report = allocate(rows, universe, body.get('ratios'), body.get('seed'))
            preview['assignments'], preview['split_report'] = assignments, report
            counts, blockers = corpus_export.inspect_projection(rows, assignments, roots)
            preview['corpus_counts'] = counts
            if blockers:
                raise WorkbenchError(' '.join(blockers))
            preview['warnings'].append(corpus_export.WINDOW_WARNING)
            if preview['analysis']['duplicate_content_records']:
                preview['warnings'].append('Exact document repeats remain in one connected split; none are discarded.')
            if preview['analysis']['unknown_rights']:
                preview['warnings'].append('Some selected documents have unknown rights. Review permission before training or sharing.')
            preview['warnings'].append('Explicit corpus review and protected families do not establish semantic independence, training quality or permission.')
            prepared = dict(preview=preview, rows=rows, roots=roots, groups=groups, snapshots=snapshots)
            total = 0
            for _, value, expected in corpus_export.entries(prepared, body):
                total += len(value)
                if total > MAX_SELECTED_TEXT_BYTES:
                    raise WorkbenchError('Corpus archive exceeds the 40 MiB complete logical archive bound, including duplicated assets and metadata.')
                if expected and hashlib.sha256(value).hexdigest() != expected:
                    raise WorkbenchError('Source bytes changed outside Tuldok.', 'conflict', 409)
            preview['artifact_bytes'] = total
            preview['preview_token'] = hashlib.sha256(encode({
                'format': corpus_export.FORMAT, 'schema': 1, 'ratios': body['ratios'], 'seed': body['seed'],
                'records': rows, 'protected_components': snapshots, 'assignments': assignments,
                'consumer': corpus_export.CONSUMER, 'text_contract': corpus_export.TEXT_CONTRACT}).encode()).hexdigest()
            preview['eligible'] = True
            return prepared
        except WorkbenchError as error:
            blocker = {'message': str(error), 'code': error.code, 'status': error.status}
            if record_id is not None:
                blocker['record_id'] = record_id
            preview['blockers'].append(blocker)
            return {'preview': preview}

    def _create_corpus(self, body):
        with self.workbench.lock, self.workbench.db:
            prepared = self._checked(body)
            fd, temporary = tempfile.mkstemp(prefix='.building-', suffix='.zip', dir=self.path)
            try:
                with os.fdopen(fd, 'w+b') as target:
                    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                        stream, total = None, 0
                        try:
                            for filename, value, expected in corpus_export.entries(prepared, body):
                                total += len(value)
                                if total > MAX_SELECTED_TEXT_BYTES:
                                    raise WorkbenchError('Corpus archive exceeds the 40 MiB complete logical archive bound.')
                                if expected and hashlib.sha256(value).hexdigest() != expected:
                                    raise WorkbenchError('Source bytes changed outside Tuldok.', 'conflict', 409)
                                if filename is not None:
                                    if stream is not None:
                                        stream.close(); stream = None
                                    if filename in ('train.txt', 'validation.txt', 'test.txt'):
                                        stream = archive.open(zipfile.ZipInfo(filename), 'w')
                                    else:
                                        archive_asset(archive, value, filename, expected or hashlib.sha256(value).hexdigest())
                                else:
                                    stream.write(value)
                        finally:
                            if stream is not None:
                                stream.close()
                    target.flush(); os.fsync(target.fileno())
                release_id = file_hash(Path(temporary))
                os.replace(temporary, self.path / (release_id + '.zip'))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            preview = prepared['preview']
            return {'id': release_id, 'url': '/api/workbench/releases/' + release_id + '.zip',
                    'format': corpus_export.FORMAT, 'records': len(prepared['rows']),
                    'split_report': preview['split_report'], 'corpus_counts': preview['corpus_counts'],
                    'artifact_bytes': preview['artifact_bytes'], 'warnings': preview['warnings']}

    def _prepare_responses(self, body):
        preview = {'format': INSTRUCTION_FORMAT, 'eligible': False, 'selected_count': 0,
                   'example_count': 0, 'unique_prompt_count': 0, 'blockers': [], 'warnings': [],
                   'lineage': [], 'assignments': {}, 'split_report': None, 'preview_token': None}
        try:
            if set(body) - {'format', 'items', 'ratios', 'seed', 'preview_token'}:
                raise WorkbenchError('Unknown instruction release fields.')
            responses, parents = self.workbench.response_selection(body.get('items'))
            preview.update(selected_count=len(responses), example_count=len(responses), unique_prompt_count=len(parents))
            universe = self.workbench._all()
            roots, groups, snapshots, preview['lineage'] = family_context(parents, universe)
            weights = Counter(response['prompt_id'] for response in responses)
            assignments, report = allocate(parents, universe, body.get('ratios'), body.get('seed'), weights)
            preview['assignments'] = {response['id']: assignments[response['prompt_id']] for response in responses}
            report.update(example_count=len(responses), unique_prompt_count=len(parents),
                          actual_unique_prompt_counts=dict(Counter(assignments.values())))
            preview['split_report'] = report
            for parent in parents:
                asset, _ = self.workbench.asset(parent['id'])
                if hashlib.sha256(asset).hexdigest() != parent['content_hash']:
                    raise WorkbenchError('Prompt bytes changed outside Tuldok.', 'conflict', 409)
            prepared = {'preview': preview, 'rows': responses, 'parents': parents, 'roots': roots,
                        'groups': groups, 'snapshots': snapshots}
            # The exact logical artifact, including duplicate consumer projection, is bounded.
            total = 0
            for _, value, expected in self._instruction_entries(prepared, body):
                total += len(value)
                if total > MAX_SELECTED_TEXT_BYTES:
                    raise WorkbenchError('Instruction archive exceeds the 40 MiB synchronous resource bound.')
                if expected and hashlib.sha256(value).hexdigest() != expected:
                    raise WorkbenchError('Prompt bytes changed outside Tuldok.', 'conflict', 409)
            preview['artifact_bytes'] = total
            preview['preview_token'] = hashlib.sha256(encode({
                'format': INSTRUCTION_FORMAT, 'schema': 1, 'ratios': body['ratios'], 'seed': body['seed'],
                'responses': responses, 'parents': parents, 'protected_components': snapshots,
                'assignments': preview['assignments']}).encode()).hexdigest()
            preview['eligible'] = True
            if any(rights_note(parent) == 'unknown' for parent in parents):
                preview['warnings'].append('Some selected prompts have unknown rights. Review permission before training or sharing.')
            preview['warnings'].append('Human review and protected families do not establish semantic quality or permission.')
            return prepared
        except WorkbenchError as error:
            preview['blockers'].append({'message': str(error), 'code': error.code, 'status': error.status})
            return {'preview': preview}

    def _instruction_entries(self, prepared, body):
        """One deterministic projection owns preview sizing and archive publication."""
        preview = prepared['preview']
        responses, parents = prepared['rows'], prepared['parents']
        prompts = {parent['id']: parent for parent in parents}
        mapping = []
        for split in SPLITS:
            filename = split + '/data.jsonl'
            for index, response in enumerate(r for r in responses if preview['assignments'][r['id']] == split):
                parent = prompts[response['prompt_id']]
                pair = {'id': response['id'], 'revision': response['revision'], 'prompt_id': parent['id'],
                        'parent_revision': parent['revision'], 'source_revision': parent['source_revision']}
                mapping.append(dict(pair, split=split, file=filename, row=index,
                                    family=prepared['groups'][prepared['roots'][parent['id']]]))
        manifest = {'schema_version': 1, 'format': INSTRUCTION_FORMAT, 'consumer': INSTRUCTION_CONSUMER,
                    'seed': body['seed'], 'split_report': preview['split_report'], 'prompts': parents,
                    'responses': responses, 'protected_components': prepared['snapshots'],
                    'text_contract': 'Prompt: existing NFC/LF. Completion: exact Unicode and whitespace.',
                    'limits': {'response_code_points': MAX_TEXT, 'selected_responses': 5000,
                               'archive_uncompressed_bytes': MAX_SELECTED_TEXT_BYTES}}
        yield 'manifest.json', encode(manifest).encode('utf-8'), None
        yield 'rows.jsonl', ''.join(encode(row) + '\n' for row in mapping).encode('utf-8'), None
        for parent in parents:
            yield 'prompts/' + parent['id'] + '.txt', parent['text'].encode('utf-8'), parent['content_hash']
        for split in SPLITS:
            # Emit bounded rows individually; an empty split has a declared empty file.
            yield split + '/data.jsonl', b'', None
            for response in responses:
                if preview['assignments'][response['id']] == split:
                    value = {'prompt': prompts[response['prompt_id']]['text'], 'completion': response['completion']}
                    yield None, (encode(value) + '\n').encode('utf-8'), None
        yield 'README.txt', (b'Tuldok text_instruction_v1. Consumer rows have only prompt/completion.\n'
                            b'Load the nonempty train/validation/test data.jsonl files with explicit split mappings.\n'
                            b'rows.jsonl maps zero-based rows to fixed response/parent/source revisions and family IDs.\n'
                            b'manifest.json preserves canonical evidence. Completion text is never trimmed or normalized.\n'
                            b'Consumer token limits/EOS/loss configuration are explicit training choices.\n'), None

    def _prepare_preferences(self, body):
        preview = {'format': PREFERENCE_FORMAT, 'eligible': False, 'selected_count': 0,
                   'example_count': 0, 'unique_prompt_count': 0, 'blockers': [], 'warnings': [],
                   'lineage': [], 'assignments': {}, 'split_report': None, 'preview_token': None, 'excluded': []}
        try:
            if set(body) - {'format', 'items', 'ratios', 'seed', 'preview_token'}:
                raise WorkbenchError('Unknown preference release fields.')
            judgments, parents, answers, excluded = self.workbench.preferences.selection(body.get('items'))
            rows = [row for row in judgments if row['outcome'] in ('left', 'right')]
            preview.update(selected_count=len(judgments), example_count=len(rows), excluded=excluded,
                           unique_prompt_count=len({row['prompt_id'] for row in rows}))
            universe = self.workbench._all()
            roots, groups, snapshots, preview['lineage'] = family_context(parents, universe)
            weights = Counter(row['prompt_id'] for row in rows)
            export_parents = [parent for parent in parents if parent['id'] in weights]
            assignments, report = allocate(export_parents, universe, body.get('ratios'), body.get('seed'), weights)
            preview['assignments'] = {row['id']: assignments[row['prompt_id']] for row in rows}
            report.update(example_count=len(rows), unique_prompt_count=preview['unique_prompt_count'],
                          actual_unique_prompt_counts=dict(Counter(assignments.values())))
            preview['split_report'] = report
            for parent in parents:
                asset, _ = self.workbench.asset(parent['id'])
                if hashlib.sha256(asset).hexdigest() != parent['content_hash']:
                    raise WorkbenchError('Prompt bytes changed outside Tuldok.', 'conflict', 409)
            competing = self.workbench.preferences.competing(judgments)
            prepared = {'preview': preview, 'rows': judgments, 'parents': parents, 'answers': answers,
                        'roots': roots, 'groups': groups, 'snapshots': snapshots, 'competing': competing}
            total = 0
            for _, value, _ in self._preference_entries(prepared, body):
                total += len(value)
                if total > MAX_SELECTED_TEXT_BYTES:
                    raise WorkbenchError('Preference archive exceeds the 40 MiB synchronous resource bound.')
            preview['artifact_bytes'] = total
            preview['preview_token'] = hashlib.sha256(encode({
                'format': PREFERENCE_FORMAT, 'schema': 1, 'ratios': body['ratios'], 'seed': body['seed'],
                'judgments': judgments, 'parents': parents, 'answers': answers, 'competing': competing,
                'protected_components': snapshots, 'assignments': preview['assignments']}).encode()).hexdigest()
            if any(rights_note(parent) == 'unknown' for parent in parents):
                preview['warnings'].append('Some selected prompts have unknown rights. Review permission before training or sharing.')
            preview['warnings'].extend('Excluded judgment ' + row['id'] + ': ' + row['reason'] for row in excluded)
            answer_map = {row['id']: row for row in answers}
            if any(answer_map[row['left_id']]['completion'] == answer_map[row['right_id']]['completion'] for row in rows):
                preview['warnings'].append('Distinct answer identities contain identical strings: degenerate DPO pairs retained explicitly.')
            if any(row['outcome'] in ('tie', 'abstain') for row in competing):
                preview['warnings'].append('Current reviewed tie/abstain judgments also exist for selected evidence; they do not veto directional judgments.')
            preview['warnings'].append('Judgment review is independent of answer/target review; it does not establish rights or training quality.')
            preview['eligible'] = True
            return prepared
        except WorkbenchError as error:
            preview['blockers'].append({'message': str(error), 'code': error.code, 'status': error.status})
            return {'preview': preview}

    def _text_entries(self, prepared, body):
        return (self._preference_entries(prepared, body) if body['format'] == PREFERENCE_FORMAT
                else self._instruction_entries(prepared, body))

    def _preference_entries(self, prepared, body):
        preview = prepared['preview']
        parents = {row['id']: row for row in prepared['parents']}
        answers = {row['id']: row for row in prepared['answers']}
        rows = [row for row in prepared['rows'] if row['outcome'] in ('left', 'right')]
        mapping = []
        for split in SPLITS:
            for index, row in enumerate(r for r in rows if preview['assignments'][r['id']] == split):
                parent = parents[row['prompt_id']]
                binding = {key: row[key] for key in ('id', 'revision', 'prompt_id', 'parent_revision', 'source_revision',
                                                   'left_id', 'left_revision', 'right_id', 'right_revision')}
                binding.update(chosen_id=row[row['outcome'] + '_id'],
                               rejected_id=row['right_id'] if row['outcome'] == 'left' else row['left_id'])
                mapping.append(dict(binding, split=split, file=split + '/data.jsonl', row=index,
                                    family=prepared['groups'][prepared['roots'][parent['id']]]))
        manifest = {'schema_version': 1, 'format': PREFERENCE_FORMAT,
                    'consumer': {'trl': '0.23.1', 'datasets': '4.1.1', 'type': 'explicit prompt/chosen/rejected'},
                    'seed': body['seed'], 'split_report': preview['split_report'], 'prompts': prepared['parents'],
                    'responses': prepared['answers'], 'judgments': prepared['rows'], 'excluded': preview['excluded'],
                    'competing_reviewed_judgments': prepared['competing'], 'protected_components': prepared['snapshots'],
                    'text_contract': 'Prompt: existing NFC/LF. Answers: exact Unicode and whitespace.',
                    'limits': {'answer_code_points': MAX_TEXT, 'selected_judgments': 5000,
                               'archive_uncompressed_bytes': MAX_SELECTED_TEXT_BYTES}}
        yield 'manifest.json', encode(manifest).encode('utf-8'), None
        yield 'rows.jsonl', ''.join(encode(row) + '\n' for row in mapping).encode('utf-8'), None
        for parent in prepared['parents']:
            yield 'prompts/' + parent['id'] + '.txt', parent['text'].encode('utf-8'), parent['content_hash']
        for split in SPLITS:
            yield split + '/data.jsonl', b'', None
            for row in rows:
                if preview['assignments'][row['id']] == split:
                    chosen = row[row['outcome'] + '_id']
                    rejected = row['right_id'] if row['outcome'] == 'left' else row['left_id']
                    value = {'prompt': parents[row['prompt_id']]['text'], 'chosen': answers[chosen]['completion'],
                             'rejected': answers[rejected]['completion']}
                    yield None, (encode(value) + '\n').encode('utf-8'), None
        yield 'README.txt', (b'Tuldok text_preference_v1. Explicit prompt/chosen/rejected strings.\n'
                            b'Only independently human-reviewed directional judgments yield rows.\n'
                            b'Ties/abstentions are excluded with reasons in manifest.json.\n'
                            b'rows.jsonl binds exact judgment/prompt/answer revisions and whole source family.\n'
                            b'Answer review is evidence, not a preference. EOS/padding/truncation are consumer settings.\n'), None

    def _create_responses(self, body):
        workbench = self.workbench
        with workbench.lock, workbench.db:
            prepared = self._checked(body)
            fd, temporary = tempfile.mkstemp(prefix='.building-', suffix='.zip', dir=self.path)
            try:
                with os.fdopen(fd, 'w+b') as target:
                    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                        stream = None
                        try:
                            for filename, value, expected in self._text_entries(prepared, body):
                                if filename is not None:
                                    if stream is not None:
                                        stream.close(); stream = None
                                    if filename.endswith('/data.jsonl'):
                                        stream = archive.open(zipfile.ZipInfo(filename), 'w')
                                    else:
                                        archive_asset(archive, value, filename, expected or hashlib.sha256(value).hexdigest())
                                else:
                                    stream.write(value)
                        finally:
                            if stream is not None:
                                stream.close()
                    target.flush(); os.fsync(target.fileno())
                release_id = file_hash(Path(temporary))
                os.replace(temporary, self.path / (release_id + '.zip'))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            preview = prepared['preview']
            return {'id': release_id, 'url': '/api/workbench/releases/' + release_id + '.zip',
                    'format': body['format'], 'records': preview['example_count'],
                    'example_count': preview['example_count'], 'unique_prompt_count': preview['unique_prompt_count'],
                    'split_report': preview['split_report']}

    def create(self, body):
        format_name = body.get('format', 'canonical_v1')
        if format_name == detection_export.FORMAT:
            if not isinstance(body.get('preview_token'), str) or not RELEASE_ID.fullmatch(body['preview_token']):
                raise WorkbenchError('Preview the exact detection selection before exporting.', 'conflict', 409)
            return self._create_detection(body)
        if format_name == corpus_export.FORMAT:
            if not isinstance(body.get('preview_token'), str) or not RELEASE_ID.fullmatch(body['preview_token']):
                raise WorkbenchError('Preview the exact corpus selection before exporting.', 'conflict', 409)
            return self._create_corpus(body)
        if format_name in (INSTRUCTION_FORMAT, PREFERENCE_FORMAT):
            if not isinstance(body.get('preview_token'), str) or not RELEASE_ID.fullmatch(body['preview_token']):
                raise WorkbenchError('Preview the exact responses before exporting.', 'conflict', 409)
            return self._create_responses(body)
        if format_name not in ('canonical_v1', CAPTION_FORMAT, classification_export.FORMAT):
            raise WorkbenchError('Unknown release format.')
        if format_name == classification_export.FORMAT:
            if not isinstance(body.get('preview_token'), str) or not RELEASE_ID.fullmatch(body['preview_token']):
                raise WorkbenchError('Preview the exact classification selection before exporting.', 'conflict', 409)
            return self._create_classification(body)
        if format_name == CAPTION_FORMAT:
            return self._create_captions(body)
        workbench = self.workbench
        with workbench.lock, workbench.db:
            prepared = self._checked(body)
            rows = prepared['rows']
            assignments = prepared['preview']['assignments']
            report = prepared['preview']['split_report']
            manifest = {'schema_version': 1, 'seed': body['seed'], 'split_report': report,
                        'coordinate_contract': 'Oriented image pixel-edge xywh; text spans are NFC/LF Unicode code-point [start,end). Sequence bundles preserve original named staggered fields and accepted intervals; each whole trajectory is indivisible. Static mesh bundles preserve native xyz/topology and declared units/frame; each whole mesh is indivisible.',
                        'limitations': ['Review status is evidence, not a quality guarantee.', 'Rights and semantic source independence require human judgment.'],
                        'records': []}
            sequence_only = all(row['kind'] == 'sequence' for row in rows)
            if sequence_only:
                manifest['protected_components'] = prepared['snapshots']
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
                            filename = 'assets/' + row['id'] + {'image': '.png', 'text': '.txt', 'sequence': '.zip', 'mesh': '.zip'}[row['kind']]
                            digest = archive_asset(archive, asset, filename, row['content_hash'])
                            record = dict(row, split=split, asset=filename, asset_sha256=digest)
                            if sequence_only:
                                record['export_group'] = prepared['groups'][prepared['roots'][row['id']]]
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

    def _create_classification(self, body):
        """Publish every reviewed selected image through a trainer-specific view."""
        workbench = self.workbench
        with workbench.lock, workbench.db:
            prepared = self._checked(body)
            preview, rows = prepared['preview'], prepared['rows']
            vocabulary = preview['class_vocabulary']
            by_label = {item['label']: item for item in vocabulary}
            manifest = {'schema_version': 1, 'format': classification_export.FORMAT,
                        'consumer': classification_export.CONSUMER, 'seed': body['seed'],
                        'split_mapping': classification_export.SPLIT_MAPPING,
                        'split_report': preview['split_report'], 'class_vocabulary': vocabulary,
                        'class_coverage': preview['class_coverage'],
                        'class_to_idx': {item['folder']: item['index'] for item in vocabulary},
                        'protected_components': prepared['snapshots'], 'records': [],
                        'warnings': preview['warnings'],
                        'limitations': ['Human review is evidence, not a quality guarantee.',
                                       'The consumer predicts opaque folders; map these back to exact labels with class_vocabulary.',
                                       'Rights, semantic independence and fitness for training require human judgment.']}
            fd, temporary = tempfile.mkstemp(prefix='.building-', suffix='.zip', dir=self.path)
            try:
                with os.fdopen(fd, 'w+b') as target:
                    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                        for row in rows:
                            split = preview['assignments'][row['id']]
                            exported_split = classification_export.SPLIT_MAPPING[split]
                            category = by_label[row['annotation']['label']]
                            filename = exported_split + '/' + category['folder'] + '/' + row['id'] + '.png'
                            asset, _ = workbench.asset(row['id'])
                            digest = archive_asset(archive, asset, filename, row['content_hash'])
                            manifest['records'].append(dict(row, split=split, export_split=exported_split,
                                export_group=prepared['groups'][prepared['roots'][row['id']]],
                                class_index=category['index'], class_folder=category['folder'],
                                asset=filename, asset_sha256=digest,
                                exported_pixel_sha256=prepared['pixel_hashes'][row['id']]))
                        archive.writestr(zipfile.ZipInfo('manifest.json'), encode(manifest))
                        archive.writestr(zipfile.ZipInfo('README.txt'),
                            'Tuldok image_classification_v1 for the pinned Chapter 8 image trainer.\n'
                            'Extract; pass the archive root as --data to the named consumer.\n'
                            'train/val/test contain class_000000-style folders and unchanged normalized PNGs.\n'
                            'manifest.json class_vocabulary maps opaque folder/index to exact Unicode label.\n'
                            'Predictions and consumer class_to_idx use folder names; preserve this mapping with the model.\n'
                            'All selected records are retained, including same-split pixel repeats with a warning.\n'
                            'Canonical revisions, provenance, hashes and connected lineage are frozen in manifest.json.\n')
                    target.flush(); os.fsync(target.fileno())
                release_id = file_hash(Path(temporary))
                os.replace(temporary, self.path / (release_id + '.zip'))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {'id': release_id, 'url': '/api/workbench/releases/' + release_id + '.zip',
                    'format': classification_export.FORMAT, 'records': len(rows),
                    'split_report': preview['split_report'], 'class_vocabulary': vocabulary,
                    'warnings': preview['warnings']}
