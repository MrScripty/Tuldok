"""Actual HTTP and SQL facts, including rollback-only legacy enrollment."""
import base64
import io
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from PIL import Image, PngImagePlugin
from app import Dataset, make_handler
from workbench import encode


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name); self.w = self.dataset.workbench
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.close)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.dataset.close()

    def request(self, body):
        req = urllib.request.Request(self.root+'/api/workbench/curation', data=json.dumps(body).encode(),
                                     headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as response: return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error: return error.code, json.load(error)

    def report(self, category='unlabeled', **extra):
        status, result = self.request({'scope':'filtered','category':category,**extra})
        self.assertEqual(status, 200, result); return result

    def text(self, name, **extra):
        return self.w.import_asset(dict(kind='text', name=name, text='Fictional source '+name,
                                       groups=['shared'], **extra))

    @staticmethod
    def ref(row): return {key:row[key] for key in ('id','revision','source_revision')}

    def state(self):
        with sqlite3.connect(self.dataset.path/'dataset.sqlite3') as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {table: db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall() for table in tables}

    def image(self, tag, legacy=False):
        out = io.BytesIO(); info=PngImagePlugin.PngInfo(); info.add_text('fixture',tag)
        Image.new('RGB',(12,12),'red').save(out,'PNG',pnginfo=info)
        body=dict(image=base64.b64encode(out.getvalue()).decode(),filename=tag+'.png',session_id=tag)
        if legacy: return self.dataset.add(body)
        return self.w.import_asset(dict(kind='image',image=body['image'],name=tag+'.png',groups=['shared']))

    def test_all_filtered_contributors_before_pagination_share_collection_owner(self):
        rows=[self.text(str(i),rights='unknown') for i in range(43)]
        self.text('outside',rights='Declared note')
        options=dict(q='Fictional',kind='text',review='draft',task='text_classification',group='shared',rights='unknown',sort='name')
        before=self.state(); result=self.report(filters=options,limit=40)
        collection=self.w.query(dict(options,limit=100))
        self.assertEqual(result['analysis'],collection['analysis'])
        self.assertEqual(result['filters'],collection['criteria']); self.assertEqual(result['total'],43)
        status, second=self.request(dict(scope='filtered',category='unlabeled',filters=options,offset=40,limit=40,view_token=result['view_token']))
        self.assertEqual(status,200); self.assertEqual(len(second['items']),3)
        self.assertEqual({r['id'] for r in result['items']+second['items']},{r['id'] for r in rows})
        self.assertEqual(self.state(),before); self.assertFalse(self.w.db.in_transaction)

    def test_duplicates_are_actual_scoped_pixel_members_and_legacy_reads_roll_back(self):
        a=self.image('a'); b=self.image('b',legacy=True)
        before=self.state(); result=self.report('duplicates')
        self.assertEqual({r['id'] for r in result['items']},{a['id'],b['id']})
        self.assertEqual({r['duplicate_members'] for r in result['items']},{2})
        self.assertEqual(len({r['duplicate_hash'] for r in result['items']}),1)
        self.assertEqual(self.report('duplicates',filters={'group':'shared'})['total'],0)
        self.assertEqual(self.state(),before); self.assertFalse(self.w.db.in_transaction)
        self.assertEqual(self.w.db.execute('SELECT COUNT(*) FROM workbench_records').fetchone()[0],1)

    def test_selected_current_facts_report_stale_deleted_missing_without_replacing_set(self):
        a=self.text('selected'); b=self.image('deleted')
        refs=[self.ref(a),self.ref(b)]
        saved=self.dataset.selections.create(dict(name='Fixed set',items=refs))
        self.w.save(a['id'],dict(a,annotation={'label':'known'},review='human_reviewed'))
        self.dataset.delete(b['id'], {'revision':b['source_revision']})
        missing={'id':'f'*32,'revision':1,'source_revision':1}
        before=self.state(); result=self.report('references',scope='selected',items=refs+[missing])
        self.assertEqual(result['reference_counts'],{'stale':2,'source_deleted':1,'missing_record':1})
        self.assertEqual(result['requested'],3); self.assertEqual(result['analysis']['records'],2)
        self.assertEqual(result['analysis']['unlabeled'],1)
        self.assertEqual({r['id'] for r in result['items']},{a['id'],b['id'],missing['id']})
        byid={r['id']:r for r in result['items']}; self.assertEqual(byid[a['id']]['reference']['requested'],refs[0])
        self.assertEqual(byid[missing['id']]['reference']['current'],None)
        self.assertEqual(self.dataset.selections.load(saved['id'])['selection'],saved)
        self.assertEqual(self.state(),before); self.assertFalse(self.w.db.in_transaction)

    def test_none_is_unlabeled_empty_negative_is_labeled_and_unknown_projection_is_existing_fact(self):
        a=self.text('none'); b=self.text('empty'); c=self.text('uppercase',rights='UNKNOWN')
        self.w.save(b['id'],dict(b,task='text_entities',annotation={'spans':[]},review='human_reviewed'))
        with self.w.db:
            self.w.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?',(encode({'rights':None}),a['id']))
        result=self.report();self.assertEqual({r['id'] for r in result['items']},{a['id'],c['id']})
        self.assertEqual(result['analysis']['empty_targets'],1)
        self.assertEqual({r['id'] for r in self.report('unknown_rights')['items']},{a['id'],b['id']})

    def test_freshness_changes_for_revision_source_and_scope_then_refresh_recovers(self):
        a=self.text('first'); initial=self.report(); self.w.save(a['id'],dict(a,annotation={'label':'x'},review='human_reviewed'))
        body=dict(scope='filtered',category='unlabeled',view_token=initial['view_token'])
        self.assertEqual(self.request(body)[0],409); self.assertEqual(self.report()['total'],0)
        self.assertEqual(self.request(dict(body,filters={'q':'nothing'}))[0],409)
        b=self.image('source'); initial=self.report('missing_sources'); self.dataset.delete(b['id'], {'revision':b['source_revision']})
        self.assertEqual(self.request(dict(body,category='missing_sources',view_token=initial['view_token']))[0],409)
        self.assertEqual(self.report('missing_sources')['total'],1)

    def test_invalid_requests_and_exception_roll_back_without_history_or_membership(self):
        self.image('legacy',legacy=True); before=self.state()
        for extra in ({'offset':True},{'limit':0},{'category':'quality_score'},{'filters':{'permission':True}},
                      {'scope':'selected','items':[{'id':'x','revision':1,'source_revision':1}]},
                      {'scope':'selected','items':[{'id':'a'*32,'revision':True,'source_revision':1}]},
                      {'scope':'selected','items':{},'filters':{}},{'view_token':'bad'}, {'review':'human_reviewed'}):
            status,_=self.request({'scope':'filtered','category':'unlabeled',**extra}); self.assertEqual(status,400,extra)
        import curation
        with patch.object(curation,'analyze',side_effect=ValueError('fixture failure')):
            with self.assertRaisesRegex(ValueError,'fixture failure'): curation.inspect(self.w,dict(scope='filtered',category='unlabeled'))
        self.assertEqual(self.state(),before); self.assertFalse(self.w.db.in_transaction)

    def test_selected_scope_decodes_only_requested_records_and_enrolls_only_selected_legacy(self):
        rows=[self.text(str(i)) for i in range(36)]
        selected_legacy=self.image('selected-legacy',legacy=True)
        self.image('unrelated-legacy',legacy=True)
        refs=[self.ref(rows[0]),dict(id=selected_legacy['id'],revision=1,source_revision=selected_legacy['revision']),
              dict(id='f'*32,revision=1,source_revision=1)]
        before=self.state()
        with patch.object(self.w,'_get',wraps=self.w._get) as get, patch.object(self.w,'_history',wraps=self.w._history) as history:
            result=self.report('references',scope='selected',items=refs)
        requested={ref['id'] for ref in refs}
        self.assertLessEqual({call.args[0] for call in get.call_args_list},requested,
                             'Selected scope must not decode unrelated records')
        self.assertEqual([call.args[0]['id'] for call in history.call_args_list],[selected_legacy['id']],
                         'Only the requested legacy image may be temporarily enrolled')
        self.assertEqual(result['analysis']['records'],2)
        self.assertEqual(result['reference_counts'],dict(stale=0,source_deleted=0,missing_record=1))
        self.assertEqual(self.state(),before); self.assertFalse(self.w.db.in_transaction)
        import curation
        with patch.object(curation,'analyze',side_effect=ValueError('selected fixture failure')):
            with self.assertRaisesRegex(ValueError,'selected fixture failure'):
                curation.inspect(self.w,dict(scope='selected',items=refs,category='references'))
        self.assertEqual(self.state(),before); self.assertFalse(self.w.db.in_transaction)

    def test_freshness_streams_canonical_filtered_facts_without_full_json_encoding(self):
        for i in range(36):
            self.w.import_asset(dict(kind='text',name=str(i),text='x'*99_990+f'\n{i}é🧪',groups=['shared']))
        with self.w.lock:
            rows,filters=self.w._filtered({})
        facts=dict(scope='filtered',filters=filters,items=[],rows=sorted(rows,key=lambda row:row['id']),references=[])
        canonical=encode(facts).encode(); expected=hashlib.sha256(canonical).hexdigest()
        largest_row=max(len(encode(row).encode()) for row in rows)
        whole_encodes=[]; writes=[]; original_encode=json.JSONEncoder.encode
        def observe_encode(encoder,value):
            if isinstance(value,dict) and 'rows' in value: whole_encodes.append(len(value['rows']))
            return original_encode(encoder,value)
        class ObservedHash:
            def __init__(self,data=b''):
                self.hash=hashlib.sha256(data); writes.append(len(data))
            def update(self,data): self.hash.update(data); writes.append(len(data))
            def hexdigest(self): return self.hash.hexdigest()
        import curation
        with patch.object(curation,'hashlib') as hashes, patch.object(json.JSONEncoder,'encode',observe_encode):
            hashes.sha256.side_effect=ObservedHash
            result=self.report(limit=1)
        self.assertEqual(result['view_token'],expected)
        self.assertEqual(result['total'],36); self.assertEqual(len(result['items']),1)
        self.assertEqual(whole_encodes,[],'Do not materialize the complete freshness JSON')
        self.assertEqual(sum(writes),len(canonical))
        self.assertLessEqual(max(writes),largest_row,'Hash writes must be bounded by a record, not collection size')
        status,page=self.request(dict(scope='filtered',category='unknown_rights',limit=1,offset=1,view_token=expected))
        self.assertEqual(status,200); self.assertEqual(page['view_token'],expected)

    def test_selected_freshness_matches_canonical_stale_and_missing_reference_facts(self):
        row=self.text('unicode-é🧪')
        refs=[dict(self.ref(row),revision=row['revision']+1),dict(id='f'*32,revision=1,source_revision=1)]
        result=self.report('references',scope='selected',items=refs)
        references=sorted([item['reference'] for item in result['items']],key=lambda ref:ref['id'])
        facts=dict(scope='selected',filters={},items=sorted(refs,key=lambda ref:ref['id']),
                   rows=[self.w.get(row['id'])],references=references)
        self.assertEqual(result['view_token'],hashlib.sha256(encode(facts).encode()).hexdigest())
        reordered=self.report('references',scope='selected',items=list(reversed(refs)),view_token=result['view_token'])
        self.assertEqual(reordered['view_token'],result['view_token'])
