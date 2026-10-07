"""Ephemeral current metadata diagnostics; no saved membership or review writes."""
import hashlib
import json

from workbench import IDENTIFIER, WorkbenchError, analyze, diagnostic_members, rights_note

CATEGORIES = ('duplicates', 'unlabeled', 'missing_sources', 'unknown_rights', 'references')
FILTERS = ('q', 'kind', 'review', 'sort', 'task', 'label', 'group', 'rights')


def inspect(workbench, body):
    if not isinstance(body, dict) or set(body) - {'scope', 'filters', 'items', 'category', 'offset', 'limit', 'view_token'}:
        raise WorkbenchError('Invalid diagnostic request.')
    scope, category = body.get('scope'), body.get('category')
    if scope not in ('filtered', 'selected') or category not in CATEGORIES:
        raise WorkbenchError('Choose a diagnostic scope and category.')
    offset, limit = body.get('offset', 0), body.get('limit', 40)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise WorkbenchError('Diagnostic page size must be 1–100 and offset nonnegative.')
    token = body.get('view_token')
    if token is not None and (not isinstance(token, str) or len(token) != 64):
        raise WorkbenchError('Invalid diagnostic freshness token.')
    filters, items = body.get('filters', {}), body.get('items', [])
    if not isinstance(filters, dict) or not isinstance(items, list):
        raise WorkbenchError('Diagnostic criteria and references have invalid types.')
    if scope == 'filtered':
        if not isinstance(filters, dict) or set(filters) - set(FILTERS) or items:
            raise WorkbenchError('Filtered diagnostics require collection criteria only.')
    else:
        if filters or not isinstance(items, list) or len(items) > 5000:
            raise WorkbenchError('Selected diagnostics require at most 5,000 exact references.')
        seen = set()
        for item in items:
            if (not isinstance(item, dict) or set(item) != {'id', 'revision', 'source_revision'}
                    or not isinstance(item['id'], str) or not IDENTIFIER.fullmatch(item['id'])
                    or item['id'] in seen or type(item['revision']) is not int or item['revision'] < 1
                    or (item['source_revision'] is not None and
                        (type(item['source_revision']) is not int or item['source_revision'] < 1))):
                raise WorkbenchError('Invalid or repeated selected reference.')
            seen.add(item['id'])
        items = sorted(items, key=lambda row: row['id'])
    # Existing lazy legacy enrollment is needed to observe records, but never persisted.
    with workbench.lock:
        workbench.db.execute('SAVEPOINT curation_view')
        try:
            if scope == 'filtered':
                rows, filters = workbench._filtered(filters)
                references = []
            else:
                rows = []
                references = []
                for item in items:
                    workbench._sync_images(item['id'])
                    try:
                        row = workbench._get(item['id'])
                    except WorkbenchError as error:
                        if error.status != 404 or error.code != 'unavailable':
                            raise
                        row = None
                    issues = []
                    if row is None:
                        issues.append('missing_record')
                    else:
                        rows.append(row)
                        if any(item[key] != row[key] for key in ('revision', 'source_revision')):
                            issues.append('stale')
                        if not row['source_available']:
                            issues.append('source_deleted')
                    references.append(dict(requested=item, current={key: row[key] for key in item} if row else None,
                                           issues=issues, id=item['id']))
            facts = dict(scope=scope, filters=filters, items=items,
                         rows=sorted(rows, key=lambda row: row['id']), references=references)
            fingerprint = hashlib.sha256()
            # Emit the existing canonical JSON bytes without a collection-sized string.
            encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
            for chunk in encoder.iterencode(facts):
                fingerprint.update(chunk.encode())
            fingerprint = fingerprint.hexdigest()
            if token is not None and token != fingerprint:
                raise WorkbenchError('Diagnostic facts changed. Refresh diagnostics before paging.', 'conflict', 409)
            members, hashes = diagnostic_members(rows)
            ref_by_id = {ref['id']: ref for ref in references}
            contributors = ([row for row in rows if ref_by_id.get(row['id'], {}).get('issues')]
                            if category == 'references' else members[category])
            diagnostic = []
            for row in contributors:
                digest = row['pixel_hash'] or row['content_hash']
                record = {key: row[key] for key in ('id', 'name', 'kind', 'task', 'review',
                    'revision', 'source_revision', 'source_available', 'groups')}
                record.update(rights_note=rights_note(row), reference=ref_by_id.get(row['id']),
                              duplicate_hash=digest if category == 'duplicates' else None,
                              duplicate_members=hashes[digest] if category == 'duplicates' else None)
                diagnostic.append(record)
            if category == 'references':
                diagnostic.extend(dict(id=ref['id'], name='Missing record', reference=ref,
                                       source_available=False) for ref in references if ref['current'] is None)
            return dict(scope=scope, filters=filters, requested=len(items) if scope == 'selected' else None,
                analysis=analyze(rows), reference_counts={issue: sum(issue in ref['issues'] for ref in references)
                    for issue in ('stale', 'source_deleted', 'missing_record')},
                items=diagnostic[offset:offset+limit], total=len(diagnostic), offset=offset, limit=limit,
                category=category, view_token=fingerprint)
        finally:
            workbench.db.execute('ROLLBACK TO curation_view')
            workbench.db.execute('RELEASE curation_view')
