"""Complete connected-family proof for frozen text and audio classification.

The release owner allocates families. This independent reader verifies frozen
member identities, retained lineage and cross-split bridges before consumption.
"""
import hashlib
import json
from image_training import IDENTIFIER, _invalid

SPLITS = ('train', 'validation', 'test')


def validate_families(manifest, noun="text"):
    components = manifest.get('protected_components')
    if not isinstance(components, dict) or not components:
        _invalid(noun.title() + ' release must freeze its complete protected components.')
    members, links, component_splits = {}, {}, {}
    for component, rows in components.items():
        if not isinstance(rows, list) or not rows:
            _invalid('Frozen protected component must contain members.')
        ids = [row.get('id') if isinstance(row, dict) else None for row in rows]
        if any(not isinstance(key, str) or not IDENTIFIER.fullmatch(key) for key in ids) or len(set(ids)) != len(ids):
            _invalid('Frozen family member identifiers must be canonical and unique.')
        expected = 'component:' + hashlib.sha256(json.dumps(sorted(ids), ensure_ascii=True, separators=(',', ':'), sort_keys=True).encode()).hexdigest()
        if component != expected:
            _invalid('Frozen component identity differs from its member IDs.')
        for row in rows:
            key = row['id']
            if key in members:
                _invalid('Frozen member appears in multiple protected components.')
            members[key] = (component, row)
            if (row.get('kind') not in ('image', 'text', 'audio', 'sequence', 'mesh')
                    or type(row.get('revision')) is not int or row['revision'] < 1
                    or type(row.get('source_available')) is not bool or type(row.get('source_lineage_known')) is not bool
                    or not row['source_lineage_known']
                    or not (type(row.get('source_revision')) is int and row['source_revision'] > 0
                            or row.get('source_revision') is None and not row['source_available'])
                    or not isinstance(row.get('groups'), list) or not isinstance(row.get('parents'), list)
                    or any(not isinstance(value, str) for value in row['groups'] + row['parents'])
                    or row.get('source_split') not in (*SPLITS, 'unassigned')):
                _invalid('Frozen family metadata is invalid or unavailable.')
            tokens = ['id:' + key] + ['group:' + value for value in row['groups']] + ['id:' + value for value in row['parents']]
            if row.get('content_hash'):
                tokens.append('content:' + row['kind'] + ':' + row['content_hash'])
            if row.get('pixel_hash'):
                tokens.append('pixels:' + row['pixel_hash'])
            if row['kind'] == 'image' and row.get('source_lineage_known', row.get('source_available')):
                tokens.append('legacy:' + ('book:' + row['book_id'] if row.get('book_id') else 'session:' + row['session_id']))
            for token in tokens:
                if token in links and links[token] != component:
                    _invalid('Frozen protected family bridge crosses declared components.')
                links[token] = component
            split = row['source_split']
            if split in SPLITS:
                if component in component_splits and component_splits[component] != split:
                    _invalid('Frozen family has conflicting fixed source splits.')
                component_splits[component] = split
    for row in manifest['records']:
        membership = members.get(row['id'])
        if membership is None or membership[0] != row.get('export_group'):
            _invalid('Frozen ' + noun + ' is missing its complete protected family evidence.')
        component, member = membership
        if any(member.get(key) != row.get(key) for key in ('kind', 'revision', 'source_revision', 'source_sha256', 'content_hash', 'groups', 'parents', 'source_available', 'source_lineage_known', 'source_split')):
            _invalid('Frozen ' + noun + ' source reference differs from its family snapshot.')
        if component in component_splits and component_splits[component] != row['split']:
            _invalid('Frozen protected family crosses train, validation or test.')
        component_splits[component] = row['split']
