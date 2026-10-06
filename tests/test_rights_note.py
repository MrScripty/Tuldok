"""Note-only correction traverses HTTP, CAS, SQLite and frozen source/history contracts."""
import base64
import hashlib
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from PIL import Image
from app import Dataset, make_handler
from workbench import encode, rights_note


class RightsNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dataset=Dataset(self.tmp.name);self.w=self.dataset.workbench
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever,daemon=True).start();self.addCleanup(self.close)
        self.root=f'http://127.0.0.1:{self.server.server_port}'

    def close(self):self.server.shutdown();self.server.server_close();self.dataset.close()

    def row(self,name='fictional',rights='Declared origin note'):
        return self.w.import_asset(dict(kind='text',name=name,text='Fictional café source '+name,groups=['family'],rights=rights))

    def request(self,row,note,**extra):
        body=dict(revision=row['revision'],source_revision=row['source_revision'],note=note,**extra)
        req=urllib.request.Request(self.root+'/api/workbench/rights/'+row['id'],data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            with error:return error.code,json.load(error)

    @staticmethod
    def ref(row):return {key:row[key] for key in ('id','revision','source_revision')}

    def state(self):
        with sqlite3.connect(self.dataset.path/'dataset.sqlite3') as db:
            return {t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

    def test_changed_note_one_revision_preserves_original_origin_and_every_source_target_field(self):
        row=self.row();row=self.w.save(row['id'],dict(row,annotation={'label':'intent'},review='human_reviewed'))
        origin=self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?',(row['id'],)).fetchone()[0]
        history=self.w.history(row['id']);status,result=self.request(row,'Corrected owner note')
        self.assertEqual(status,200);self.assertTrue(result['changed']);after=result['record']
        self.assertEqual(after['revision'],row['revision']+1);self.assertNotEqual(after['updated_at'],row['updated_at'])
        for key in set(row)-{'revision','updated_at','provenance'}:self.assertEqual(after[key],row[key],key)
        self.assertEqual(after['provenance']['rights'],row['provenance']['rights'])
        self.assertEqual({k:v for k,v in after['provenance'].items() if k!='rights_note_correction'},row['provenance'])
        self.assertEqual(after['provenance']['rights_note_correction'],{'note':'Corrected owner note','revision':after['revision']})
        self.assertEqual(self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?',(row['id'],)).fetchone()[0],origin)
        self.assertEqual(self.w.history(row['id']),[after]+history);self.assertEqual(rights_note(after),'Corrected owner note')
        self.assertEqual(self.w.query({'rights':'Corrected owner note'})['total'],1)
        self.assertEqual(self.w.query({'rights':'Declared origin note'})['total'],0)
        self.assertEqual(self.request(row,'Corrected owner note')[0],409,'Replay is stale even if note now matches')
        # Subsequent annotation saves retain both original JSON and separate owned correction.
        edited=self.w.save(row['id'],dict(after,annotation={'label':'new'},review='draft'))
        self.assertEqual(edited['provenance'],after['provenance']);self.assertEqual(rights_note(edited),'Corrected owner note')
        self.assertEqual(self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?',(row['id'],)).fetchone()[0],origin)

    def test_unchanged_and_projected_unknown_are_true_noops(self):
        row=self.row();before=self.state();status,result=self.request(row,'  Declared origin note \n')
        self.assertEqual(status,200);self.assertFalse(result['changed']);self.assertEqual(result['record'],row);self.assertEqual(self.state(),before)
        unknown=self.row('unknown',rights='unknown');before=self.state()
        self.assertFalse(self.request(unknown,' \r\n ')[1]['changed']);self.assertEqual(self.state(),before)

    def test_real_concurrent_compare_and_swap_admits_exactly_one(self):
        row=self.row();barrier=threading.Barrier(2)
        def edit(note):barrier.wait();return self.request(row,note)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(edit,['first correction','second correction']))
        self.assertEqual(sorted(status for status,_ in results),[200,409]);self.assertEqual(self.w.get(row['id'])['revision'],2)
        self.assertEqual(len(self.w.history(row['id'])),2);self.assertFalse(self.w.db.in_transaction)

    def test_unicode_and_internal_cr_lf_are_preserved_but_invalid_input_has_no_effect(self):
        row=self.row();note='café e\u0301 😀\nline two\rline three\r\nfinal'
        status,result=self.request(row,note);self.assertEqual(status,200);self.assertEqual(rights_note(result['record']),note)
        before=self.state()
        for bad in [None,True,{},'😀'*1001,'lone\ud800']:
            self.assertEqual(self.request(result['record'],bad)[0],400);self.assertEqual(self.state(),before)
        status,large=self.request(result['record'],'😀'*1000);self.assertEqual(status,200);self.assertEqual(len(rights_note(large['record'])),1000)
        self.assertEqual(self.request(large['record'],'note',review='human_reviewed')[0],400)

    def test_image_bytes_hashes_source_revision_and_review_unchanged_deleted_source_rejects(self):
        out=io.BytesIO();Image.new('RGB',(16,12),'green').save(out,'PNG')
        row=self.w.import_asset(dict(kind='image',name='fixture.png',image=base64.b64encode(out.getvalue()).decode(),groups=['images']))
        path=self.dataset.path/'images'/row['id'];hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}
        sample=dict(self.w.db.execute('SELECT * FROM samples WHERE id=?',(row['id'],)).fetchone())
        status,result=self.request(row,'Permission claimed by operator');self.assertEqual(status,200)
        self.assertEqual(result['record']['review'],'draft');self.assertIsNone(result['record']['annotation'])
        self.assertEqual(dict(self.w.db.execute('SELECT * FROM samples WHERE id=?',(row['id'],)).fetchone()),sample)
        self.assertEqual({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()},hashes)
        # A corner-source revision change independently rejects a current Workbench revision.
        with self.w.db:self.w.db.execute('UPDATE samples SET revision=revision+1 WHERE id=?',(row['id'],))
        before=self.state();self.assertEqual(self.request(result['record'],'stale source note')[0],409);self.assertEqual(self.state(),before)
        latest=self.w.get(row['id']);self.dataset.delete(row['id'],{'revision':latest['source_revision']})
        before=self.state();self.assertEqual(self.request(latest,'deleted')[0],409);self.assertEqual(self.state(),before)

    def test_fixed_sets_and_release_proofs_stale_for_selected_and_unselected_lineage(self):
        row=self.row();row=self.w.save(row['id'],dict(row,annotation={'label':'known'},review='human_reviewed'))
        sibling=self.row('unselected')
        saved=self.dataset.selections.create(dict(name='Fixed',items=[self.ref(row)]))
        body=dict(items=[self.ref(row)],ratios={'train':100,'validation':0,'test':0},seed=42)
        preview=self.dataset.releases.preview(body);self.assertTrue(preview['eligible'])
        self.request(sibling,'Related context correction')
        with self.assertRaisesRegex(ValueError,'preview changed'):self.dataset.releases.create(dict(body,preview_token=preview['preview_token']))
        self.assertTrue(self.dataset.selections.load(saved['id'])['current'],'Unselected sibling does not change saved selected pair')
        _,result=self.request(row,'Selected correction');loaded=self.dataset.selections.load(saved['id'])
        self.assertEqual(loaded['selection'],saved);self.assertEqual(loaded['members'][0]['status'],'stale')
        self.assertFalse(self.dataset.releases.preview(body)['eligible'])
        fresh=dict(body,items=[self.ref(result['record'])]);self.assertTrue(self.dataset.releases.preview(fresh)['eligible'])

    def test_history_failure_rolls_back_note_revision_and_preserves_origin_collision(self):
        row=self.row();before=self.state()
        with patch.object(self.w,'_history',side_effect=ValueError('fixture history failure')):
            status,_=self.request(row,'failed');self.assertEqual(status,400)
        self.assertEqual(self.state(),before);self.assertFalse(self.w.db.in_transaction)
        with self.w.db:self.w.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?',(encode(dict(row['provenance'],rights_note_correction={'declared':'foreign evidence'})),row['id']))
        before=self.state();self.assertEqual(self.request(row,'cannot replace evidence')[0],409);self.assertEqual(self.state(),before)

    def test_restart_retains_note_and_migration_leaves_prior_history_intact(self):
        row=self.row();prior=self.w.history(row['id']);_,result=self.request(row,'Persistent correction')
        # Separate connection and fresh Dataset instance exercise actual persistent owners.
        reopened=Dataset(self.tmp.name)
        try:
            self.assertEqual(reopened.workbench.get(row['id']),result['record'])
            self.assertEqual(reopened.workbench.history(row['id']),[result['record']]+prior)
        finally:reopened.close()

    def test_upgrade_from_prior_schema_keeps_existing_records_and_history(self):
        row=self.row();prior=self.w.history(row['id'])
        with self.w.db:self.w.db.execute('DROP TABLE workbench_rights_notes')
        reopened=Dataset(self.tmp.name)
        try:
            self.assertEqual(reopened.workbench.get(row['id']),row)
            self.assertEqual(reopened.workbench.history(row['id']),prior)
            self.assertEqual(reopened.db.execute('SELECT COUNT(*) FROM workbench_rights_notes').fetchone()[0],0)
        finally:reopened.close()

    def test_owned_programmatic_review_evidence_is_retained_without_a_new_grant(self):
        import dataset_recipes
        created=dataset_recipes.generate(self.w,dict(recipe='intent-requests-v1',seed=19,count=1))['created'][0]
        row=self.w.get(created['id']);self.assertEqual(row['review'],'programmatically_verified')
        status,result=self.request(row,'Changed declared note')
        self.assertEqual(status,200);self.assertEqual(result['record']['review'],'programmatically_verified')
        self.assertEqual({k:v for k,v in result['record']['provenance'].items() if k!='rights_note_correction'},row['provenance'])
