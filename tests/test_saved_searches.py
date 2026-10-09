"""Saved criteria against actual SQLite/HTTP; fixed membership remains independent."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
from saved_searches import SavedSearches, criteria, parse_request
from workbench import WorkbenchError


class SavedSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.w, self.s = self.dataset.workbench, self.dataset.searches

    def filters(self, **changes):
        return dict(dict(q='', kind='', task='', review='', sort='newest', label='', group='', rights=''), **changes)

    def save(self, **changes):
        return self.s.create({'name': 'Current search', 'criteria': self.filters(**changes)})

    def row(self, name='Alpha', label='chosen', group='source', rights='owned'):
        row = self.w.import_asset({'kind': 'text', 'text': name, 'name': name, 'groups': [group], 'rights': rights})
        return self.w.save(row['id'], dict(row, annotation={'label': label}, review='human_reviewed'))

    def test_pure_validation_and_lifecycle_do_not_enrol_or_mutate_records(self):
        row = self.row(); before = self.w.get(row['id']); history = self.w.history(row['id'])
        with patch.object(self.w, '_sync_images', side_effect=AssertionError('No enrollment')), patch.object(self.w, '_all', side_effect=AssertionError('No query')), patch.object(self.w, '_get', side_effect=AssertionError('No record reads')):
            saved = self.save(q='Alpha'); self.assertEqual(saved['mode'], 'dynamic'); self.assertEqual(saved['schema_version'], 1)
            self.assertEqual(self.s.get(saved['id']), saved); self.assertEqual(self.s.list()['searches'], [saved])
            renamed = self.s.mutate(saved['id'], 'rename', {'revision': 1, 'name': 'Renamed'})
            self.assertEqual(renamed['criteria'], saved['criteria'])
            self.s.mutate(saved['id'], 'delete', {'revision': 2})
        self.assertEqual(self.w.get(row['id']), before); self.assertEqual(self.w.history(row['id']), history)

    def test_reopen_and_dynamic_growth_never_refresh_fixed_pairs(self):
        first = self.row(); refs = [{k: first[k] for k in ('id', 'revision', 'source_revision')}]
        fixed = self.dataset.selections.create({'name': 'Fixed', 'items': refs}); saved = self.save(label='chosen')
        self.assertEqual(self.w.query(saved['criteria'])['total'], 1)
        second = self.row('Beta'); self.assertEqual(self.w.query(self.s.get(saved['id'])['criteria'])['total'], 2)
        self.assertEqual(self.dataset.selections.load(fixed['id'])['selection'], fixed)
        self.w.save(first['id'], dict(first, annotation={'label': 'other'}, review='draft'))
        self.assertEqual(self.w.query(saved['criteria'])['total'], 1)
        self.assertFalse(self.dataset.selections.load(fixed['id'])['current'])
        self.dataset.close(); self.dataset = Dataset(self.tmp.name); self.w, self.s = self.dataset.workbench, self.dataset.searches
        self.assertEqual(self.s.get(saved['id']), saved); self.assertEqual(self.w.query(saved['criteria'])['items'][0]['id'], second['id'])

    def test_exact_metadata_and_existing_query_normalization_equivalence(self):
        for index, value in enumerate(['first\nsecond', 'first\rsecond', 'first\r\nsecond', r'first\nsecond', 'two "quoted" values']):
            row = self.row('Metadata '+str(index), value, value, value)
            entered = self.filters(q='  '+value.replace('\r', '').replace('\n', '')+'  ', kind='text', task='text_classification', review='human_reviewed', sort='name', label=value, group=value, rights=value)
            entered['q'] = ''
            saved = self.s.create({'name': 'Exact', 'criteria': entered})
            self.assertEqual(self.w.query(entered), self.w.query(saved['criteria']))
            self.assertEqual([r['id'] for r in self.w.query(saved['criteria'])['items']], [row['id']])
        sharp = self.save(q='ß'*200); self.assertEqual(sharp['criteria']['q'], 'ß'*200)
        self.assertEqual(self.w.query(sharp['criteria'])['criteria']['q'], 'ss'*200)
        self.assertEqual(criteria(self.filters(q='  ALPHA ', label=' chosen '))['q'], 'ALPHA')
        self.assertEqual(self.w.query(self.filters(q='  ALPHA '))['criteria']['q'], 'alpha')

    def test_strict_criteria_rejection_is_atomic(self):
        valid = self.filters()
        invalid = [None, [], dict(valid, offset=0), {k: v for k, v in valid.items() if k != 'sort'}]
        for key in valid:
            invalid.extend([dict(valid, **{key: value}) for value in [None, [], {}, True, 1]])
        invalid.extend([dict(valid, q='a\nb'), dict(valid, q='a\rb'), dict(valid, q='ß'*201), dict(valid, q='\ud800'), dict(valid, kind='volume'), dict(valid, review='accepted'), dict(valid, sort='random'), dict(valid, task='segmentation'), dict(valid, label='a'*81), dict(valid, group='a'*121), dict(valid, rights='a'*1001)])
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertRaises(WorkbenchError):
                self.s.create({'name': 'Rejected', 'criteria': value})
        for body in [{}, {'name': 'x', 'criteria': valid, 'items': []}, {'name': ' ', 'criteria': valid}]:
            with self.assertRaises(WorkbenchError): self.s.create(body)
        self.assertEqual(self.s.list(), {'searches': []})

    def test_cap_cas_and_failed_writes_keep_criteria(self):
        first = self.save()
        for revision in [True, '1', 0, 2]:
            with self.assertRaises(WorkbenchError): self.s.mutate(first['id'], 'rename', {'revision': revision, 'name': 'no'})
        for action, body in [('update', {'revision': 1}), ('delete', {'revision': 1, 'criteria': {}}), ('rename', {'revision': 1, 'name': ''})]:
            with self.assertRaises(WorkbenchError): self.s.mutate(first['id'], action, body)
        self.assertEqual(self.s.get(first['id']), first)
        for _ in range(99): self.save()
        with self.assertRaises(WorkbenchError): self.save()
        self.assertEqual(len(self.s.list()['searches']), 100)
        renamed = self.s.mutate(first['id'], 'rename', {'revision': 1, 'name': 'Renamed'})
        self.assertEqual(renamed['revision'], 2); self.assertEqual(renamed['criteria'], first['criteria'])
        with self.assertRaises(WorkbenchError): self.s.mutate(first['id'], 'delete', {'revision': 1})
        self.s.mutate(first['id'], 'delete', {'revision': 2}); self.save()

    def test_future_schema_trigger_and_malformed_storage_fail_closed(self):
        saved = self.save()
        with self.dataset.db:
            self.dataset.db.execute('UPDATE saved_searches SET criteria_json=? WHERE id=?', ('{"q":"x"}', saved['id']))
        with self.assertRaises(WorkbenchError): self.s.get(saved['id'])
        with self.dataset.db:
            self.dataset.db.execute('CREATE TRIGGER unsupported_search AFTER UPDATE ON saved_searches BEGIN SELECT 1; END')
        with self.assertRaises(WorkbenchError): SavedSearches(self.w)

        with self.dataset.db:
            self.dataset.db.execute('DROP TRIGGER unsupported_search'); self.dataset.db.execute('ALTER TABLE saved_searches ADD COLUMN future_version INTEGER')
        with self.assertRaises(WorkbenchError): SavedSearches(self.w)

    def test_finite_json_and_unexpected_storage_constraints(self):
        for raw in [b'{"q":1e999}', b'{"q":NaN}', b'{"q":0,"q":1}', b'', b'\xff', b'['*16000+b']'*16000]:
            with self.assertRaises(WorkbenchError): parse_request(raw)
        saved = self.save()
        with self.dataset.db:
            self.dataset.db.execute('CREATE UNIQUE INDEX unsupported_name ON saved_searches(name)')
        with self.assertRaises(WorkbenchError): SavedSearches(self.w)
        with self.dataset.db:
            self.dataset.db.execute('DROP INDEX unsupported_name')
            self.dataset.db.execute('UPDATE saved_searches SET created_at=? WHERE id=?', ('future', saved['id']))
        with self.assertRaises(WorkbenchError): self.s.get(saved['id'])

    def test_actual_http_routes_and_strict_json(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset)); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(lambda: (server.shutdown(), thread.join()))
        def request(route='', body=None, raw=None):
            if body is not None: raw = json.dumps(body).encode()
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/searches'+route, data=raw, headers={'Content-Type': 'application/json'})
            try: response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as error: response = error
            with response: return response.status, json.loads(response.read())
        status, saved = request(body={'name': 'HTTP', 'criteria': self.filters()}); self.assertEqual(status, 201)
        self.assertEqual(request('/'+saved['id']), (200, saved)); self.assertEqual(request()[1]['searches'], [saved])
        for raw in [b'{"name":"a","name":"b","criteria":{}}', b'{"name":NaN}', b'\xff', b'[]', b' '*32769, b'['*16000+b']'*16000]: self.assertEqual(request(raw=raw)[0], 400)
        self.assertEqual(request()[1]['searches'], [saved])
        for route in ['/bad', '/'+saved['id']+'/extra']:
            self.assertEqual(request(route)[0], 400)
        self.assertEqual(request('/'+saved['id']+'/rename', body={'revision': True, 'name': 'no'})[0], 409)
        self.assertEqual(request('/'+saved['id']+'/rename', body={'revision': 1, 'name': 'New'})[1]['revision'], 2)
        self.assertEqual(request('/'+saved['id']+'/delete', body={'revision': 2}), (200, {'deleted': saved['id']}))
        self.assertEqual(request('/'+saved['id'])[0], 404)


if __name__ == '__main__': unittest.main()
