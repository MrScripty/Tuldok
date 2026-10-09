"""Named dynamic criteria; independent of fixed membership and review authority."""
import json
import math
import re
import uuid
from datetime import datetime

from workbench import IDENTIFIER, WorkbenchError, encode, query_criteria, text_value, timestamp

MAX_SEARCHES = 100
MAX_REQUEST = 32 * 1024
CRITERIA = {'q', 'kind', 'review', 'sort', 'task', 'label', 'group', 'rights'}
SCHEMA = '''CREATE TABLE saved_searches (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,
    criteria_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)'''


def parse_request(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_REQUEST:
        raise WorkbenchError('Saved-search JSON must contain 1–32768 bytes.')
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise WorkbenchError('Duplicate saved-search JSON key.')
            result[key] = value
        return result

    def constant(value):
        raise WorkbenchError('Saved-search JSON must be finite.')

    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            constant(value)
        return parsed

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs, parse_constant=constant, parse_float=number)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise WorkbenchError('Invalid saved-search JSON: ' + str(error)) from None


def criteria(value):
    if not isinstance(value, dict) or set(value) != CRITERIA:
        raise WorkbenchError('Provide exactly the eight metadata search criteria, without membership or pagination.')
    result = query_criteria(value)
    if '\r' in result['q'] or '\n' in result['q']:
        raise WorkbenchError('Saved search text must be single-line; exact metadata values may contain line breaks.')
    return result


class SavedSearches:
    def __init__(self, workbench):
        self.db, self.lock = workbench.db, workbench.lock
        with self.lock, self.db:
            existing = self.db.execute("SELECT sql FROM sqlite_master WHERE name='saved_searches'").fetchone()
            if existing is None:
                self.db.execute(SCHEMA)
            else:
                normalized = lambda sql: re.sub(r'\s+', ' ', sql or '').strip().casefold()
                if normalized(existing[0]) != normalized(SCHEMA):
                    raise WorkbenchError('Unsupported saved-search storage schema.')
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='saved_searches'").fetchone():
                raise WorkbenchError('Unsupported saved-search storage trigger.')
            columns = [row['name'] for row in self.db.execute('PRAGMA table_info(saved_searches)')]
            indexes = self.db.execute('PRAGMA index_list(saved_searches)').fetchall()
            if columns != ['id', 'name', 'revision', 'criteria_json', 'created_at', 'updated_at'] or len(indexes) != 1 or indexes[0]['origin'] != 'pk' or indexes[0]['partial']:
                raise WorkbenchError('Unsupported saved-search storage columns or indexes.')

    def _get(self, search_id):
        if not isinstance(search_id, str) or not IDENTIFIER.fullmatch(search_id):
            raise WorkbenchError('Invalid saved search ID.')
        row = self.db.execute('SELECT * FROM saved_searches WHERE id=?', (search_id,)).fetchone()
        if row is None:
            raise WorkbenchError('Saved search not found.', 'unavailable', 404)
        result = dict(row)
        try:
            raw = result.pop('criteria_json')
            if not isinstance(raw, str):
                raise TypeError('Invalid stored criteria.')
            stored = parse_request(raw.encode('utf-8'))
            result['criteria'] = criteria(stored)
            if stored != result['criteria'] or type(result['revision']) is not int or result['revision'] < 1 or text_value(result['name'], 'Search name', 120) != result['name']:
                raise ValueError('Invalid stored search.')
            for key in ('created_at', 'updated_at'):
                value = text_value(result[key], 'Search timestamp', 64)
                if value != result[key] or datetime.fromisoformat(value).utcoffset() is None:
                    raise ValueError('Invalid stored timestamp.')
        except (ValueError, TypeError):
            raise WorkbenchError('Unsupported or malformed saved-search state.') from None
        result.update(mode='dynamic', schema_version=1)
        return result

    def get(self, search_id):
        with self.lock:
            return self._get(search_id)

    def list(self):
        with self.lock:
            ids = self.db.execute('SELECT id FROM saved_searches ORDER BY updated_at DESC,id LIMIT 101').fetchall()
            if len(ids) > MAX_SEARCHES:
                raise WorkbenchError('Saved-search storage exceeds the supported count.')
            return {'searches': [self._get(row[0]) for row in ids]}

    def create(self, body):
        if not isinstance(body, dict) or set(body) != {'name', 'criteria'}:
            raise WorkbenchError('Save a name and entered metadata criteria only.')
        name = text_value(body['name'], 'Search name', 120)
        value = criteria(body['criteria'])
        with self.lock, self.db:
            if self.db.execute('SELECT count(*) FROM saved_searches').fetchone()[0] >= MAX_SEARCHES:
                raise WorkbenchError('At most 100 saved searches; delete one before saving another.')
            search_id, created = uuid.uuid4().hex, timestamp()
            self.db.execute('INSERT INTO saved_searches VALUES (?,?,?,?,?,?)',
                            (search_id, name, 1, encode(value), created, created))
            return self._get(search_id)

    def mutate(self, search_id, action, body):
        expected = {'revision', 'name'} if action == 'rename' else {'revision'}
        if action not in ('rename', 'delete') or not isinstance(body, dict) or set(body) != expected:
            raise WorkbenchError('Invalid saved search action.')
        with self.lock, self.db:
            before = self._get(search_id)
            if type(body['revision']) is not int or body['revision'] != before['revision']:
                raise WorkbenchError('Saved search changed. Refresh before renaming or deleting.', 'conflict', 409)
            if action == 'delete':
                self.db.execute('DELETE FROM saved_searches WHERE id=?', (search_id,))
                return {'deleted': search_id}
            name = text_value(body['name'], 'Search name', 120)
            self.db.execute('UPDATE saved_searches SET name=?,revision=revision+1,updated_at=? WHERE id=?',
                            (name, timestamp(), search_id))
            return self._get(search_id)
