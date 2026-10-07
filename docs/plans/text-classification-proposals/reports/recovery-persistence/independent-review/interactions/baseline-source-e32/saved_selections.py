"""Named fixed membership, independent of filters, review and frozen releases."""
import json
import uuid

from workbench import IDENTIFIER, WorkbenchError, encode, file_hash, text_value, timestamp


class SavedSelections:
    def __init__(self, workbench):
        self.workbench = workbench
        self.db, self.lock = workbench.db, workbench.lock
        with self.lock, self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS saved_selections (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,
                members_json TEXT NOT NULL, member_count INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')

    def _get(self, selection_id):
        if not isinstance(selection_id, str) or not IDENTIFIER.fullmatch(selection_id):
            raise WorkbenchError('Invalid saved selection ID.')
        row = self.db.execute('SELECT * FROM saved_selections WHERE id=?', (selection_id,)).fetchone()
        if row is None:
            raise WorkbenchError('Saved selection not found.', 'unavailable', 404)
        result = dict(row)
        result['items'] = json.loads(result.pop('members_json'))
        result['mode'] = 'fixed'
        result['schema_version'] = 1
        return result

    def list(self):
        with self.lock:
            return {'selections': [dict(row, mode='fixed', schema_version=1) for row in self.db.execute(
                '''SELECT id,name,revision,member_count,created_at,updated_at
                   FROM saved_selections ORDER BY updated_at DESC,id''')]}

    def create(self, body):
        if set(body) != {'name', 'items'}:
            raise WorkbenchError('Save a name and exact record revision pairs; filters are not membership.')
        name = text_value(body.get('name'), 'Selection name', 120)
        items = body.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 5000:
            raise WorkbenchError('Select 1–5,000 records per saved selection.')
        with self.lock, self.db:
            for item in items:
                if not isinstance(item, dict) or set(item) != {'id', 'revision', 'source_revision'}:
                    raise WorkbenchError('Provide only record ID, revision and source revision.')
                if not isinstance(item['id'], str) or not IDENTIFIER.fullmatch(item['id']):
                    raise WorkbenchError('Invalid record ID.')
            rows = self.workbench.selection(items)
            members = []
            for row in rows:
                asset, _ = self.workbench.asset(row['id'])
                try:
                    changed = row['kind'] == 'image' and file_hash(asset) != row['content_hash']
                except OSError:
                    raise WorkbenchError('Source bytes are unavailable.', 'unavailable', 404) from None
                if changed:
                    raise WorkbenchError('Source bytes changed. Restore the original before saving a selection.', 'conflict', 409)
                members.append({key: row[key] for key in ('id', 'name', 'kind', 'revision', 'source_revision',
                               'source_sha256', 'content_hash', 'pixel_hash')})
            selection_id, now = uuid.uuid4().hex, timestamp()
            self.db.execute('INSERT INTO saved_selections VALUES (?,?,?,?,?,?,?)',
                            (selection_id, name, 1, encode(members), len(members), now, now))
            return self._get(selection_id)

    def load(self, selection_id):
        """Keep every saved reference; current metadata never replaces a saved pair."""
        with self.lock, self.db:
            saved = self._get(selection_id)
            self.workbench._sync_images()
            members = []
            for item in saved['items']:
                status, message, current = 'ok', 'Saved revisions and source are current.', None
                try:
                    row = self.workbench._get(item['id'])
                except WorkbenchError as error:
                    if error.status != 404:
                        raise
                    status, message = 'missing_record', 'Record no longer exists.'
                else:
                    current = {key: row[key] for key in ('revision', 'source_revision')}
                    if not row['source_available']:
                        status, message = 'deleted_source', 'Source image was deleted.'
                    else:
                        try:
                            asset, _ = self.workbench.asset(item['id'])
                            changed = row['kind'] == 'image' and file_hash(asset) != item['content_hash']
                        except (OSError, WorkbenchError):
                            status, message = 'missing_source', 'Source bytes are unavailable.'
                        else:
                            if changed or any(row[key] != item[key] for key in ('kind', 'source_sha256', 'content_hash', 'pixel_hash')):
                                status, message = 'changed_source', 'Source identity differs from the saved selection.'
                            elif any(row[key] != item[key] for key in ('revision', 'source_revision')):
                                status, message = 'stale', 'Record or source revision changed; saved revisions are retained.'
                members.append({'item': item, 'status': status, 'message': message, 'current': current})
            return {'selection': saved, 'members': members,
                    'current': all(member['status'] == 'ok' for member in members)}

    def mutate(self, selection_id, action, body):
        expected = {'revision', 'name'} if action == 'rename' else {'revision'}
        if action not in ('rename', 'delete') or set(body) != expected:
            raise WorkbenchError('Invalid saved selection action.')
        with self.lock, self.db:
            saved = self._get(selection_id)
            if type(body.get('revision')) is not int or body['revision'] != saved['revision']:
                raise WorkbenchError('Saved selection changed. Refresh before renaming or deleting.', 'conflict', 409)
            if action == 'delete':
                self.db.execute('DELETE FROM saved_selections WHERE id=?', (selection_id,))
                return {'deleted': selection_id}
            name = text_value(body.get('name'), 'Selection name', 120)
            self.db.execute('UPDATE saved_selections SET name=?,revision=revision+1,updated_at=? WHERE id=?',
                            (name, timestamp(), selection_id))
            return self._get(selection_id)
